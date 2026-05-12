"""Auth0 Management API helpers used by the tenant team module.

Wraps the small subset of the Management API needed to invite users,
assign per-tenant roles via custom claims and revoke access when an
admin removes a member from a tenant.

When the Auth0 management credentials are not configured (typical for
local development) all calls are no-ops and return ``disabled=True``.
The route layer surfaces that flag in the response so the Admin Panel
can warn operators that they need to sync Auth0 manually.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import UUID

import httpx
import structlog

from app.core.config import get_settings

log = structlog.get_logger()


_TOKEN_LOCK = asyncio.Lock()
_CACHED_TOKEN: dict[str, Any] = {'token': None, 'expires_at': 0.0}


def _read_secret_file(path: str) -> str | None:
    try:
        candidate = Path(path)
        if not candidate.is_absolute():
            for base in (Path('/app'), Path.cwd()):
                resolved = base / candidate
                if resolved.exists():
                    return resolved.read_text(encoding='utf-8').strip()
            return None
        if candidate.exists():
            return candidate.read_text(encoding='utf-8').strip()
    except OSError as exc:
        log.warning('auth0_admin.secret_file_read_failed', error=str(exc))
    return None


def _management_client_secret(settings) -> str | None:
    if settings.auth0_admin_client_secret:
        return settings.auth0_admin_client_secret
    if settings.auth0_admin_client_secret_file:
        return _read_secret_file(settings.auth0_admin_client_secret_file)
    return None


def auth0_management_enabled() -> bool:
    settings = get_settings()
    return bool(
        settings.auth0_domain
        and settings.auth0_admin_client_id
        and _management_client_secret(settings)
    )


def _management_audience(settings) -> str:
    domain = settings.auth0_domain.removeprefix('https://').rstrip('/')
    return f'https://{domain}/api/v2/'


def _admin_panel_result_url(settings) -> str:
    raw = settings.auth0_callback_urls or 'http://localhost:3000/callback'
    return raw.split(',', 1)[0].strip()


def clear_management_token_cache() -> None:
    _CACHED_TOKEN['token'] = None
    _CACHED_TOKEN['expires_at'] = 0.0


async def get_management_token() -> str | None:
    """Fetch (and cache) an Auth0 Management API token.

    Returns ``None`` when management credentials are not configured.
    The cache TTL is driven by Auth0's ``expires_in``.
    """
    if not auth0_management_enabled():
        return None

    settings = get_settings()
    now = monotonic()
    cached_token = _CACHED_TOKEN.get('token')
    cached_exp = _CACHED_TOKEN.get('expires_at') or 0.0
    if cached_token and cached_exp > now + 30:
        return cached_token

    async with _TOKEN_LOCK:
        now = monotonic()
        cached_token = _CACHED_TOKEN.get('token')
        cached_exp = _CACHED_TOKEN.get('expires_at') or 0.0
        if cached_token and cached_exp > now + 30:
            return cached_token

        domain = settings.auth0_domain.removeprefix('https://').rstrip('/')
        url = f'https://{domain}/oauth/token'
        payload = {
            'grant_type': 'client_credentials',
            'client_id': settings.auth0_admin_client_id,
            'client_secret': _management_client_secret(settings),
            'audience': _management_audience(settings),
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

        token = data.get('access_token')
        expires_in = float(data.get('expires_in') or 3600)
        if not token:
            log.warning('auth0_admin.no_access_token_in_response')
            return None
        _CACHED_TOKEN['token'] = token
        _CACHED_TOKEN['expires_at'] = monotonic() + max(expires_in - 60, 60)
        return token


async def _mgmt_request(
    method: str,
    path: str,
    *,
    json_body: Any | None = None,
) -> dict[str, Any]:
    token = await get_management_token()
    if not token:
        return {'disabled': True}
    settings = get_settings()
    domain = settings.auth0_domain.removeprefix('https://').rstrip('/')
    url = f'https://{domain}/api/v2{path}'
    headers = {'authorization': f'Bearer {token}', 'accept': 'application/json'}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.request(method, url, headers=headers, json=json_body)
    if response.status_code >= 400:
        log.warning(
            'auth0_admin.request_failed',
            method=method,
            path=path,
            status=response.status_code,
            detail=response.text[:512],
        )
        response.raise_for_status()
    if response.status_code == 204 or not response.content:
        return {}
    return response.json()


async def invite_user(
    *, email: str, role: str, tenant_id: UUID, display_name: str | None = None
) -> dict[str, Any]:
    """Create a password-change ticket so the new user can set their password.

    Auth0 docs:
      POST /api/v2/tickets/password-change

    Returns a dict with either ``ticket_url`` or ``disabled=True`` when
    management credentials are missing.  Caller is responsible for
    showing the URL to the operator and/or sending the email.
    """
    if not auth0_management_enabled():
        return {'disabled': True}
    settings = get_settings()
    body = {
        'email': email,
        'result_url': _admin_panel_result_url(settings),
        'mark_email_as_verified': False,
        'includeEmailInRedirect': True,
        'ttl_sec': 60 * 60 * 24 * 7,
        'connection_id': None,
    }
    if display_name:
        body['user_metadata'] = {'display_name': display_name}
    # Auth0 rejects null connection_id; drop it when not specified.
    body.pop('connection_id', None)
    try:
        response = await _mgmt_request('POST', '/tickets/password-change', json_body=body)
    except httpx.HTTPError as exc:
        log.warning('auth0_admin.invite_user_failed', error=str(exc), email=email)
        return {'disabled': False, 'error': str(exc)}
    return {'disabled': False, 'ticket_url': response.get('ticket')}


async def assign_roles(*, auth_subject: str | None, roles: list[str]) -> dict[str, Any]:
    """Persist the user's tenant role into Auth0 user_metadata.

    The actual role injection into the JWT is performed by the post-login
    Action that reads ``user_metadata.tenant_roles`` and emits the
    ``{namespace}/roles`` claim.  Storing a list of ``{tenant_id, role}``
    entries keeps multi-tenant assignments coherent.
    """
    if not auth0_management_enabled():
        return {'disabled': True}
    if not auth_subject:
        return {'disabled': False, 'skipped': 'no_auth_subject'}
    try:
        await _mgmt_request(
            'PATCH',
            f'/users/{auth_subject}',
            json_body={'user_metadata': {'tenant_roles': roles}},
        )
    except httpx.HTTPError as exc:
        log.warning('auth0_admin.assign_roles_failed', error=str(exc))
        return {'disabled': False, 'error': str(exc)}
    return {'disabled': False, 'synced': True}


async def revoke_tenant_roles(*, auth_subject: str | None, tenant_id: UUID) -> dict[str, Any]:
    """Mark the user as revoked from this tenant in Auth0 user_metadata.

    The post-login Action drops any tenant role pointing at this tenant
    before issuing the next token.
    """
    if not auth0_management_enabled():
        return {'disabled': True}
    if not auth_subject:
        return {'disabled': False, 'skipped': 'no_auth_subject'}
    try:
        await _mgmt_request(
            'PATCH',
            f'/users/{auth_subject}',
            json_body={
                'app_metadata': {
                    'tenant_revocations': {str(tenant_id): True},
                }
            },
        )
    except httpx.HTTPError as exc:
        log.warning('auth0_admin.revoke_roles_failed', error=str(exc))
        return {'disabled': False, 'error': str(exc)}
    return {'disabled': False, 'revoked': True}
