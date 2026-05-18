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


def _service_client_secret(settings) -> str | None:
    """M2M client secret (env first, then file). ``None`` if unconfigured."""
    if settings.auth0_service_client_secret:
        return settings.auth0_service_client_secret
    if settings.auth0_service_client_secret_file:
        return _read_secret_file(settings.auth0_service_client_secret_file)
    return None


def _legacy_admin_client_secret(settings) -> str | None:
    """Pre-BUG-001 fallback: legacy ``AUTH0_ADMIN_CLIENT_SECRET[_FILE]``."""
    if settings.auth0_admin_client_secret:
        return settings.auth0_admin_client_secret
    if settings.auth0_admin_client_secret_file:
        return _read_secret_file(settings.auth0_admin_client_secret_file)
    return None


def _management_credentials(settings) -> tuple[str | None, str | None]:
    """BUG-001: ``(client_id, client_secret)`` for ``client_credentials``.

    Prefers ``AUTH0_SERVICE_*`` (M2M, ``app_type=non_interactive``).
    Falls back to legacy ``AUTH0_ADMIN_*`` (regular_web) with a deprecation
    warning. Returns ``(None, None)`` if neither pair is configured.
    """
    service_id = settings.auth0_service_client_id
    service_secret = _service_client_secret(settings)
    if service_id and service_secret:
        return service_id, service_secret

    admin_id = settings.auth0_admin_client_id
    admin_secret = _legacy_admin_client_secret(settings)
    if admin_id and admin_secret:
        log.warning(
            'auth0_admin.legacy_admin_credentials_used_for_m2m',
            hint=(
                'AUTH0_ADMIN_* normalmente NO autoriza grant_type=client_credentials. '
                'Re-corre scripts/configure-auth0.sh para regenerar AUTH0_SERVICE_* '
                '(app M2M non_interactive) o el flow devolverá 403 en /oauth/token.'
            ),
            ticket='BUG-001',
        )
        return admin_id, admin_secret

    return None, None


def _management_client_secret(settings) -> str | None:
    """Backward-compatible accessor for older callers/tests."""
    _, secret = _management_credentials(settings)
    return secret


def auth0_management_enabled() -> bool:
    settings = get_settings()
    client_id, secret = _management_credentials(settings)
    return bool(settings.auth0_domain and client_id and secret)


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
        client_id, client_secret = _management_credentials(settings)
        payload = {
            'grant_type': 'client_credentials',
            'client_id': client_id,
            'client_secret': client_secret,
            'audience': _management_audience(settings),
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code == 403:
                # BUG-001: surface a diagnostic without leaking the secret.
                log.error(
                    'auth0_admin.oauth_token_forbidden',
                    status=response.status_code,
                    ticket='BUG-001',
                    hint=(
                        'Auth0 rechazó client_credentials. Verifica que '
                        'AUTH0_SERVICE_CLIENT_ID apunta a la app M2M '
                        '(app_type=non_interactive). Re-corre '
                        'scripts/configure-auth0.sh si es necesario.'
                    ),
                )
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


class Auth0UserAlreadyExists(Exception):
    """Raised when ``POST /api/v2/users`` returns 409 AND the lookup-by-email
    recovery path also fails (so we couldn't find the existing user to reuse).

    BUG-013: el happy path de "email ya existe en Auth0" YA NO es esta
    excepción. ``invite_user`` ahora busca el user existente via
    ``GET /api/v2/users-by-email`` y reutiliza su ``user_id`` para attach al
    nuevo tenant — caso de uso central en SaaS multi-tenant donde un mismo
    email es agente/admin de varias empresas. Esta excepción se levanta SOLO
    cuando el lookup también falla (Auth0 devuelve lista vacía o 5xx).
    """


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
    if response.status_code == 409:
        # Bubble up as a typed exception so the invite flow can refuse to
        # issue a password-reset ticket against an account that already
        # exists in Auth0 (TASK-0085 / BUG06).
        log.warning(
            'auth0_admin.request_conflict',
            method=method,
            path=path,
            detail=response.text[:512],
        )
        raise Auth0UserAlreadyExists(response.text[:512])
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


def _invitation_connection(settings) -> str:
    """Return the Auth0 database connection name used to create new users.

    Defaults to ``Username-Password-Authentication`` (Auth0's out-of-the-box
    DB connection) unless overridden in settings.
    """
    return getattr(settings, 'auth0_invitation_connection', None) or 'Username-Password-Authentication'


async def lookup_auth0_user_by_email(email: str) -> dict[str, Any] | None:
    """BUG-013: GET /api/v2/users-by-email para encontrar el user existente.

    Necesario cuando ``POST /api/v2/users`` devuelve 409 (el email ya tiene
    cuenta Auth0 — típicamente porque fue invitado a otro tenant antes, o
    porque hizo signup user-side). En lugar de propagar 409 al caller,
    buscamos el ``user_id`` real y lo reutilizamos para attach al nuevo
    tenant.

    Devuelve el primer match (Auth0 retorna un array — pueden haber múltiples
    users con el mismo email si hay multiple connections, pero por nuestra
    config siempre usamos `Username-Password-Authentication` y Auth0 dedupea
    dentro de una connection). Si no hay match (Auth0 retorna []) o si el
    Management API no está habilitado (dev local), devuelve None.

    URL-encodea el email — un `+` literal en alias-style emails
    (``foo+bar@gmail.com``) se rompe sin encode.
    """
    if not auth0_management_enabled():
        return None
    from urllib.parse import quote  # noqa: PLC0415

    encoded = quote(email)
    response = await _mgmt_request('GET', f'/users-by-email?email={encoded}')
    # `_mgmt_request` parses JSON; el endpoint devuelve un array, no dict.
    # Cuando el token no está autorizado, _mgmt_request retorna {'disabled': True}.
    if isinstance(response, dict) and response.get('disabled'):
        return None
    if not isinstance(response, list) or not response:
        return None
    return response[0]


async def invite_user(
    *, email: str, role: str, tenant_id: UUID, display_name: str | None = None
) -> dict[str, Any]:
    """TASK-0085 / BUG06: invite a tenant member via a TWO-step Auth0 flow.

    Step 1: ``POST /api/v2/users`` to create a brand-new Auth0 identity in our
    invitation connection, with a random password and ``email_verified=false``.
    If Auth0 returns 409 (the email already belongs to another account, even
    one in a different connection like a platform/support tenant), we abort
    with ``Auth0UserAlreadyExists`` instead of issuing a password-reset ticket
    against it.

    Step 2: ``POST /api/v2/tickets/password-change`` keyed by the **new user_id**
    (NOT by email). This guarantees the ticket can only reset the password of
    the freshly-created tenant-member account, never of an unrelated Auth0
    user. The ticket URL is logged server-side for emergency recovery and is
    NOT returned to the caller — the user receives it via Auth0's own email
    flow (the create-user call triggers the connection's email template when
    ``verify_email=true`` is set).

    Returns ``{'disabled': True}`` when management credentials are missing
    (local dev), or ``{'auth0_user_id': '...', 'invited': True}`` on success.
    """
    if not auth0_management_enabled():
        return {'disabled': True}
    settings = get_settings()
    connection = _invitation_connection(settings)

    user_body: dict[str, Any] = {
        'email': email,
        'email_verified': False,
        'verify_email': True,
        'connection': connection,
        # Random password — the user will overwrite it via the password-change
        # ticket. 32 hex chars meets Auth0's complexity policy in all common
        # configurations.
        'password': _random_initial_password(),
        'user_metadata': {
            'tenant_invitation': {
                'tenant_id': str(tenant_id),
                'role': role,
            },
        },
    }
    if display_name:
        user_body['name'] = display_name
        user_body['user_metadata']['display_name'] = display_name

    reused_existing = False
    try:
        user = await _mgmt_request('POST', '/users', json_body=user_body)
        auth0_user_id = user.get('user_id')
    except Auth0UserAlreadyExists:
        # BUG-013: el email ya tiene cuenta Auth0 (típico en SaaS multi-tenant
        # donde un agente trabaja para varias empresas — el primer invite crea
        # el user; los siguientes lo encuentran). En lugar de propagar 409 al
        # caller (lo que rompía el flow), miramos el user existente por email
        # y lo reutilizamos para attach al nuevo tenant.
        #
        # NO mandamos email de password-change para users existentes — ya
        # tienen credenciales válidas. El user verá el nuevo tenant en el
        # selector la próxima vez que loguee. Esto es seguro porque el caller
        # del endpoint ya pasó `ensure_tenant_access` + `_ensure_caller_can_target_role`
        # — un admin del tenant puede asignar roles, y agregar a un user
        # existente a un tenant nuevo NO compromete credenciales (no resetea
        # password, no afecta otros tenants donde el user ya está).
        log.info(
            'auth0_admin.invite_user_email_exists_looking_up',
            tenant_id=str(tenant_id),
            role=role,
        )
        existing = await lookup_auth0_user_by_email(email)
        if not existing or not existing.get('user_id'):
            # El lookup también falló — no podemos recuperar. Propagamos para
            # que la ruta responda 409 con un mensaje útil al operador.
            log.warning(
                'auth0_admin.invite_user_lookup_failed_after_409',
                tenant_id=str(tenant_id),
            )
            raise
        auth0_user_id = existing['user_id']
        reused_existing = True
    except httpx.HTTPError as exc:
        log.warning('auth0_admin.invite_user_create_failed', error=str(exc), email=email)
        return {'disabled': False, 'error': str(exc)}

    if not auth0_user_id:
        log.warning('auth0_admin.invite_user_missing_user_id', response=user if not reused_existing else existing)
        return {'disabled': False, 'error': 'auth0_create_user_returned_no_id'}

    # BUG-009 fix: propagar tenant_id + rol al user Auth0 ANTES de emitir el
    # ticket de password-change. Sin esto, el invitado loguea con un JWT
    # "pelado" (sin `tenant_id` claim ni `roles` claim) y el panel le dice
    # "Aún no estás asignada a un negocio". Hay que escribir dos cosas:
    #
    #   1. `app_metadata.tenant_id` + `app_metadata.default_tenant_id`:
    #      la PostLogin Action de claims lee de ahí (scripts/configure-auth0.sh
    #      línea 376: `const tenantId = appMetadata.tenant_id || appMetadata.default_tenant_id;`)
    #      y emite el claim `{namespace}/tenant_id` al JWT.
    #
    #   2. **Rol Auth0** asignado al user via `POST /users/{id}/roles`. La
    #      Action lee `event.authorization.roles` (línea 374) que Auth0 pobla
    #      cuando el user tiene roles ASIGNADOS via Management API. `user_metadata.tenant_roles`
    #      que escribía `assign_roles()` históricamente NO lo lee la Action de
    #      claims — es ortogonal y por eso el JWT seguía pelado.
    #
    # BUG-013: estos helpers TAMBIÉN se llaman cuando reusamos un user
    # existente (caso SaaS multi-tenant). El user en Auth0 ya existe pero su
    # `app_metadata.tenant_id` y rol Auth0 apuntan al TENANT VIEJO (donde fue
    # invitado primero). Necesitamos sobrescribir con el tenant nuevo para que
    # el próximo login traiga el claim correcto para esta nueva membresía.
    #
    # Ambas operaciones son best-effort: si fallan, NO abortamos el invite
    # (el user de Auth0 ya existe y el ticket es lo que dispara el email).
    # El operador puede setear los campos a mano si una de las dos falla; el
    # warning del log indica cuál.
    propagation_errors: list[str] = []
    try:
        await set_user_tenant_metadata(auth_subject=auth0_user_id, tenant_id=tenant_id)
    except httpx.HTTPError as exc:
        propagation_errors.append(f'app_metadata: {exc}')
        log.warning(
            'auth0_admin.invite_user_app_metadata_failed',
            auth0_user_id=auth0_user_id,
            tenant_id=str(tenant_id),
            error=str(exc),
        )
    try:
        role_result = await assign_auth0_role_by_name(auth_subject=auth0_user_id, role_name=role)
    except httpx.HTTPError as exc:
        propagation_errors.append(f'role_assignment: {exc}')
        log.warning(
            'auth0_admin.invite_user_role_assign_failed',
            auth0_user_id=auth0_user_id,
            tenant_id=str(tenant_id),
            role=role,
            error=str(exc),
        )
    else:
        # BUG-068: `assign_auth0_role_by_name` también puede devolver
        # `{'error': 'auth0_role_not_found:...'}` como VALOR (no raise) cuando
        # el rol no existe en Auth0. Antes el caller solo capturaba
        # httpx.HTTPError y el `auth0_role_not_found` se tragaba en silencio
        # → la response API decía `invited: True` aunque el invitado no
        # quedó con rol asignado y al loguear iba a recibir 403 en todos
        # los endpoints privilegiados. Ahora chequeamos el dict de retorno.
        if isinstance(role_result, dict) and role_result.get('error'):
            propagation_errors.append(f'role_assignment: {role_result["error"]}')
            log.warning(
                'auth0_admin.invite_user_role_assign_unresolved',
                auth0_user_id=auth0_user_id,
                tenant_id=str(tenant_id),
                role=role,
                error=role_result['error'],
            )

    # BUG-013: skip password-change ticket cuando estamos reusando un user
    # Auth0 existente — ya tiene credenciales válidas. Mandar un nuevo ticket
    # de password-change a un user existente sería: (a) confuso UX (recibe un
    # mail diciendo "resetá tu password" sin haberlo pedido), y (b) bordeline-
    # malicioso desde el admin que está agregando al user (podría usarse como
    # phishing-via-legitimate-channel). Si el operador quiere notificar al
    # user, puede hacerlo por su canal preferido — el user ya tiene cuenta y
    # va a ver el nuevo tenant en el selector la próxima vez que loguee.
    if not reused_existing:
        ticket_body = {
            'user_id': auth0_user_id,
            'result_url': _admin_panel_result_url(settings),
            'mark_email_as_verified': False,
            'includeEmailInRedirect': True,
            'ttl_sec': 60 * 60 * 24 * 7,
        }
        try:
            ticket_response = await _mgmt_request('POST', '/tickets/password-change', json_body=ticket_body)
        except httpx.HTTPError as exc:
            log.warning('auth0_admin.invite_user_ticket_failed', error=str(exc), auth0_user_id=auth0_user_id)
            return {'disabled': False, 'error': str(exc), 'auth0_user_id': auth0_user_id}

        # Server-side log only — the URL is NOT returned to the caller.
        ticket_url = ticket_response.get('ticket')
        if ticket_url:
            log.info(
                'auth0_admin.invite_user_ticket_generated',
                auth0_user_id=auth0_user_id,
                tenant_id=str(tenant_id),
                # log a fingerprint, not the URL itself, to avoid leaking the
                # ticket through aggregated log storage.
                ticket_present=True,
            )
    else:
        log.info(
            'auth0_admin.invite_user_reused_existing',
            auth0_user_id=auth0_user_id,
            tenant_id=str(tenant_id),
            role=role,
        )

    # BUG-009 + BUG-013: el dict literal mantiene `auth0_user_id` + `invited`.
    # `reused_existing` indica al frontend si mostrar "agregado al tenant"
    # vs "invitación enviada por email". Si hubo errores de propagación de
    # tenant_id/role (best-effort), `propagation_errors` los reporta para que
    # la UI muestre warning sin romper el flow.
    return {
        'disabled': False,
        'invited': True,
        'auth0_user_id': auth0_user_id,
        'reused_existing': reused_existing,
        **(
            {'propagation_errors': propagation_errors}
            if propagation_errors
            else {}
        ),
    }


def _random_initial_password() -> str:
    """A high-entropy throwaway password used only to create the Auth0 user.

    The invitee resets it immediately via the password-change ticket; this
    value is never stored or returned.
    """
    import secrets  # noqa: PLC0415

    # 24 bytes (192 bits) → 48 hex chars; meets every Auth0 strength tier.
    # Add an uppercase letter and a symbol to satisfy the strictest policy.
    return f'A!{secrets.token_urlsafe(32)}'


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


# BUG-009 — cache de role_id por nombre. Los roles Auth0 (`platform_owner`,
# `owner`, `admin`, `manager`, `agent`, `viewer`, `support`) son 7 y NO cambian
# durante la vida del proceso (creados por `scripts/configure-auth0.sh`).
# Cachear el lookup evita un `GET /roles` por cada invite.
_AUTH0_ROLE_ID_CACHE: dict[str, str] = {}


def clear_auth0_role_cache() -> None:
    """Test helper — borra el cache para que el siguiente lookup vaya al API."""
    _AUTH0_ROLE_ID_CACHE.clear()


async def _resolve_auth0_role_id(role_name: str) -> str | None:
    """Resuelve `role_name` → role_id consultando `GET /roles` con cache.

    Devuelve `None` si el rol no existe en Auth0 (typo del caller o tenant
    Auth0 sin los roles del script). El caller debe manejar el None.
    """
    if role_name in _AUTH0_ROLE_ID_CACHE:
        return _AUTH0_ROLE_ID_CACHE[role_name]
    # `per_page=100` cubre todos los roles del producto sin paginar.
    response = await _mgmt_request('GET', '/roles?per_page=100')
    roles = response if isinstance(response, list) else response.get('roles', [])
    for entry in roles:
        name = entry.get('name')
        rid = entry.get('id')
        if name and rid:
            _AUTH0_ROLE_ID_CACHE[name] = rid
    return _AUTH0_ROLE_ID_CACHE.get(role_name)


async def set_user_tenant_metadata(
    *, auth_subject: str, tenant_id: UUID
) -> dict[str, Any]:
    """BUG-009: setea `app_metadata.tenant_id` + `app_metadata.default_tenant_id`.

    La PostLogin Action de claims (`scripts/configure-auth0.sh` línea 376) lee
    `event.user.app_metadata.tenant_id` y lo inyecta como `{namespace}/tenant_id`
    claim al access token. Sin esto, el JWT del invitado llega con `tenant_id`
    vacío y `authenticate_request` lo trata como user sin tenant.

    PATCH semantic — preserva otros campos de `app_metadata` (ej. `support_mode`).
    """
    if not auth0_management_enabled():
        return {'disabled': True}
    if not auth_subject:
        return {'disabled': False, 'skipped': 'no_auth_subject'}
    await _mgmt_request(
        'PATCH',
        f'/users/{auth_subject}',
        json_body={
            'app_metadata': {
                'tenant_id': str(tenant_id),
                'default_tenant_id': str(tenant_id),
            },
        },
    )
    return {'disabled': False, 'updated': True}


async def assign_auth0_role_by_name(
    *, auth_subject: str, role_name: str
) -> dict[str, Any]:
    """BUG-009: asigna rol Auth0 al user via `POST /users/{id}/roles`.

    La PostLogin Action lee `event.authorization.roles` (lo que Auth0 propaga
    cuando el user tiene roles asignados via Management API). Sin esta llamada,
    el JWT del invitado llega con `roles=[]` y `ensure_tenant_access` rechaza
    cualquier endpoint privilegiado con 403 "agent role or higher is required".

    Idempotente: `POST /users/{id}/roles` con un role_id ya asignado es no-op
    en Auth0 (no duplica). Si `role_name` no se resuelve, fail-closed:
    devolvemos error explícito sin tocar nada.

    Requiere scopes `read:roles` + `create:role_members` autorizados en la M2M
    (ver `scripts/configure-auth0.sh` `MGMT_API_SCOPES`).
    """
    if not auth0_management_enabled():
        return {'disabled': True}
    if not auth_subject:
        return {'disabled': False, 'skipped': 'no_auth_subject'}
    role_id = await _resolve_auth0_role_id(role_name)
    if not role_id:
        log.warning(
            'auth0_admin.assign_role_by_name_unresolved',
            role_name=role_name,
            auth_subject=auth_subject,
        )
        return {
            'disabled': False,
            'error': f'auth0_role_not_found:{role_name}',
        }
    await _mgmt_request(
        'POST',
        f'/users/{auth_subject}/roles',
        json_body={'roles': [role_id]},
    )
    return {'disabled': False, 'assigned': True, 'role_id': role_id}


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
