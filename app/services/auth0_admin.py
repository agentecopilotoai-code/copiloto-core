"""M59 — Cliente Auth0 Management API.

Re-introducido tras la purga del branch core (M2 borró
`app/services/auth0_admin.py`). Necesario para:

  - invite_user(): crear el user en Auth0 + mandarle email con magic
    link de password setup, de modo que `add_tenant_member` no quede
    como "registro local huérfano".
  - block_user() / unblock_user(): suspender o reanudar el login del
    user (PATCH blocked=true|false) — el JWT en flight expira, próximo
    login bloqueado.
  - reset_mfa(): borrar todos los factores MFA registrados del user
    (DELETE /users/{id}/multifactor/{provider}). El user re-enrola
    al próximo login si MFA enforcement está activo.
  - delete_user(): borrar el user de Auth0 (lo último — usualmente
    queremos solo block).
  - get_user_by_email(): chequeo previo + idempotencia.

Pre-requisitos
==============
Settings (en `app/core/config.py::Settings`):
  - auth0_domain                    (ya existía)
  - auth0_service_client_id         (M2M app — M59)
  - auth0_service_client_secret     (M59, plaintext) OR
  - auth0_service_client_secret_file (M59, path al file)

Setup Auth0:
  1. Crear app M2M con permisos Management API.
     `scripts/configure-auth0.sh` lo hace si seteás `MGMT_CLIENT_ID`
     + `MGMT_CLIENT_SECRET` en el env.
  2. La app M2M debe tener estos scopes habilitados:
       read:users, create:users, update:users, delete:users,
       read:user_idp_tokens, create:user_tickets,
       read:roles, update:users_app_metadata, blacklist:tokens
     `scripts/configure-auth0.sh` los habilita automáticamente.

Modo "best-effort"
==================
Si las settings Auth0 NO están configuradas, todas las funciones
levantan `Auth0NotConfiguredError`. Los handlers que invitan
(`add_tenant_member`) lo CATCHEAN y caen al modo LOCAL ONLY: crean
el placeholder pending en `app.users` + la membresía, audit-loggean
`auth0_skipped=true`, y la UI muestra "agregado en panel; el user
debe signuparse a mano en Auth0".

Auth disponible → flow "real": Auth0 crea el user + manda el email
de welcome. La membresía local matchea por email al primer login del
user (M57 reconciliation).
"""
from __future__ import annotations

import asyncio
import hashlib
import secrets
import time
from pathlib import Path
from typing import Any

import httpx
import structlog

from app.core.config import get_settings

log = structlog.get_logger(__name__)


class Auth0NotConfiguredError(RuntimeError):
    """Settings Auth0 Management API ausentes — el caller debe caer
    a modo LOCAL ONLY o devolver error claro al user."""


class Auth0ApiError(RuntimeError):
    """Auth0 devolvió 4xx/5xx. El mensaje incluye el status + body."""
    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f'Auth0 API {status_code}: {body[:200]}')


# Cache del Management API access token. Auth0 los emite con 24h por
# default; refrescamos cuando faltan <1h.
_mgmt_token_cache: dict[str, Any] = {'token': None, 'expires_at': 0.0}
_mgmt_token_lock = asyncio.Lock()


def _service_client_secret() -> str:
    """Lee el secret del M2M client (plaintext setting o file)."""
    settings = get_settings()
    if settings.auth0_service_client_secret:
        return settings.auth0_service_client_secret
    if settings.auth0_service_client_secret_file:
        path = Path(settings.auth0_service_client_secret_file)
        if path.exists():
            return path.read_text(encoding='utf-8').strip()
    raise Auth0NotConfiguredError(
        'auth0_service_client_secret no configurado (ni plaintext ni file)',
    )


def _require_configured() -> tuple[str, str, str]:
    """Devuelve (domain, client_id, client_secret) o levanta."""
    settings = get_settings()
    if not settings.auth0_domain:
        raise Auth0NotConfiguredError('auth0_domain no configurado')
    if not settings.auth0_service_client_id:
        raise Auth0NotConfiguredError('auth0_service_client_id no configurado')
    return settings.auth0_domain, settings.auth0_service_client_id, _service_client_secret()


def is_configured() -> bool:
    """True si todas las settings necesarias para Management API están
    presentes. Usalo en handlers para decidir LOCAL ONLY vs Auth0-enabled."""
    try:
        _require_configured()
        return True
    except Auth0NotConfiguredError:
        return False


async def _get_management_token() -> str:
    """Obtiene un access_token con `audience=https://{domain}/api/v2/`.

    Cachea hasta 20h (settings.auth0_mgmt_token_cache_ttl_seconds).
    Lock para evitar thundering herd de N requests intentando refresh
    al mismo tiempo.
    """
    settings = get_settings()
    now = time.time()
    if _mgmt_token_cache['token'] and _mgmt_token_cache['expires_at'] > now:
        return _mgmt_token_cache['token']
    async with _mgmt_token_lock:
        # Double-check inside lock (otro request pudo haber refrescado).
        if _mgmt_token_cache['token'] and _mgmt_token_cache['expires_at'] > now:
            return _mgmt_token_cache['token']
        domain, client_id, client_secret = _require_configured()
        audience = f'https://{domain}/api/v2/'
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f'https://{domain}/oauth/token',
                json={
                    'grant_type': 'client_credentials',
                    'client_id': client_id,
                    'client_secret': client_secret,
                    'audience': audience,
                },
            )
        if resp.status_code >= 400:
            raise Auth0ApiError(resp.status_code, resp.text)
        body = resp.json()
        token = body['access_token']
        # Auth0 devuelve `expires_in` (segundos). Restamos 60s safety.
        ttl = min(int(body.get('expires_in', 86400)) - 60,
                  settings.auth0_mgmt_token_cache_ttl_seconds)
        _mgmt_token_cache['token'] = token
        _mgmt_token_cache['expires_at'] = now + max(ttl, 60)
        log.info('auth0.mgmt_token_refreshed', ttl=ttl)
        return token


def _clear_token_cache() -> None:
    """Test-only: limpia el cache para que el próximo call refresque."""
    _mgmt_token_cache['token'] = None
    _mgmt_token_cache['expires_at'] = 0.0


async def _mgmt_api(
    method: str, path: str,
    *, json_body: dict | None = None, params: dict | None = None,
) -> Any:
    """Wrapper genérico para Auth0 Management API. Path empieza con `/`
    (ej. `/users`, `/users/{id}/multifactor/google-authenticator`)."""
    domain, _client_id, _secret = _require_configured()
    token = await _get_management_token()
    url = f'https://{domain}/api/v2{path}'
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.request(
            method, url,
            headers={'authorization': f'Bearer {token}'},
            json=json_body, params=params,
        )
    if resp.status_code == 401:
        # Token expired entre el cache check y el call → un retry con
        # cache invalidada.
        _clear_token_cache()
        token = await _get_management_token()
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.request(
                method, url,
                headers={'authorization': f'Bearer {token}'},
                json=json_body, params=params,
            )
    if resp.status_code >= 400:
        raise Auth0ApiError(resp.status_code, resp.text)
    if resp.status_code == 204 or not resp.content:
        return None
    return resp.json()


# ─── User management ─────────────────────────────────────────────────────


async def get_user_by_email(email: str) -> dict | None:
    """GET /users-by-email?email=... → primer match o None.

    Útil para idempotencia: antes de `invite_user`, chequeamos si ya
    existe. Si existe en Auth0, solo creamos la membresía local +
    devolvemos `reused_existing=True`.
    """
    users = await _mgmt_api('GET', '/users-by-email', params={'email': email})
    if not users:
        return None
    return users[0]


async def invite_user(
    *, email: str, name: str | None = None,
    connection: str = 'Username-Password-Authentication',
    user_metadata: dict | None = None,
    app_metadata: dict | None = None,
) -> dict:
    """Crea el user en Auth0 + emite ticket de password reset (= email
    de welcome con magic link).

    Idempotente: si el email ya existe, NO crea uno nuevo (devuelve el
    user existente con `reused_existing=True`). El caller decide qué
    hacer (típicamente: solo agregar la membresía local).

    Returns:
        {
          'user': {... Auth0 user object ...},
          'reused_existing': bool,
          'invitation_ticket_url': str | None,
        }
    """
    existing = await get_user_by_email(email)
    if existing:
        log.info('auth0.invite_user.reused_existing', email=email, user_id=existing.get('user_id'))
        return {
            'user': existing,
            'reused_existing': True,
            'invitation_ticket_url': None,
        }

    # Password aleatoria fuerte. El user nunca la usa — la setea via el
    # ticket emitido abajo.
    random_password = secrets.token_urlsafe(32) + 'A1!'
    user_body: dict = {
        'email': email,
        'password': random_password,
        'connection': connection,
        'verify_email': False,  # el ticket de password-change ya verifica
        'email_verified': False,
    }
    if name:
        user_body['name'] = name
    if user_metadata:
        user_body['user_metadata'] = user_metadata
    if app_metadata:
        user_body['app_metadata'] = app_metadata
    user = await _mgmt_api('POST', '/users', json_body=user_body)

    # Ticket de password change. Auth0 manda el email automáticamente si
    # `mark_email_as_verified=true` + el connection tiene email enabled.
    # Devuelve `{'ticket': 'https://.../u/reset-password/...'}` por si el
    # caller quiere mostrar el link al admin (útil cuando Auth0 NO
    # manda email — pasa en algunos tiers gratuitos o si SMTP no está
    # configurado).
    ticket = await _mgmt_api(
        'POST', '/tickets/password-change',
        json_body={
            'user_id': user['user_id'],
            'mark_email_as_verified': True,
            'ttl_sec': 7 * 24 * 3600,  # 7 días
        },
    )
    log.info('auth0.invite_user.created', email=email, user_id=user['user_id'])
    return {
        'user': user,
        'reused_existing': False,
        'invitation_ticket_url': ticket.get('ticket') if ticket else None,
    }


async def block_user(user_id: str) -> None:
    """PATCH /users/{id} con blocked=true. Suspende todo login del user
    (Auth0 rechaza inmediatamente al próximo /authorize). Los JWT en
    flight siguen valid hasta su expiración natural — para cancelar
    sesiones activas, también borramos `app.auth_sessions.revoked_at`
    desde el caller. user_id es el de Auth0 (ej. `auth0|abc...`)."""
    await _mgmt_api('PATCH', f'/users/{user_id}', json_body={'blocked': True})
    log.info('auth0.block_user', user_id=user_id)


async def unblock_user(user_id: str) -> None:
    """PATCH /users/{id} con blocked=false. Reanuda el login."""
    await _mgmt_api('PATCH', f'/users/{user_id}', json_body={'blocked': False})
    log.info('auth0.unblock_user', user_id=user_id)


async def reset_mfa(user_id: str) -> None:
    """DELETE /users/{id}/multifactor/{provider} para los providers
    estándar (Auth0 los expone como sub-recursos del user). El user
    re-enrola MFA al próximo login si el enforcement está activo.

    `provider` valores válidos: 'google-authenticator', 'duo',
    'guardian', 'authenticator', 'sms'. Borramos todos para limpiar
    completo. Auth0 devuelve 204 incluso si no había nada que borrar.
    """
    # Lista de providers comunes. Si el user no tiene uno específico
    # registrado, el DELETE devuelve 204 (idempotente).
    providers = ('google-authenticator', 'guardian', 'authenticator', 'duo', 'sms')
    for provider in providers:
        try:
            await _mgmt_api('DELETE', f'/users/{user_id}/multifactor/{provider}')
        except Auth0ApiError as exc:
            # 404 = no había MFA con ese provider — ok.
            if exc.status_code != 404:
                raise
    log.info('auth0.reset_mfa', user_id=user_id)


async def delete_user(user_id: str) -> None:
    """DELETE /users/{id}. Borra el user de Auth0 (irreversible).

    Usualmente preferimos `block_user` — `delete` borra audit history
    de Auth0 y rompe links históricos. Solo usarlo cuando el user
    explícitamente pide GDPR-style deletion.
    """
    await _mgmt_api('DELETE', f'/users/{user_id}')
    log.info('auth0.delete_user', user_id=user_id)


# ─── Pending sub helper ──────────────────────────────────────────────────


def make_pending_auth_subject(email: str) -> str:
    """Determinístico, hash del email lowercase. Lo usa
    `add_tenant_member` en el FALLBACK LOCAL ONLY (cuando Auth0 no
    está configurado). M57 reconcilia el pending al primer login real
    del user matcheando por email."""
    digest = hashlib.sha256(email.lower().encode('utf-8')).hexdigest()[:32]
    return f'pending|{digest}'
