from __future__ import annotations

import asyncio
import json
import secrets
import time
from pathlib import Path
from typing import Any
from uuid import UUID
from urllib.parse import urlencode

import httpx
from fastapi import (
    APIRouter,
    HTTPException,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from fastapi.responses import FileResponse, RedirectResponse

from app.admin.config import get_admin_settings
from app.admin.ws_fanout import fanout as ws_fanout
from app.core.security import decode_auth0_id_token
from app.core.signed_cookies import (
    _sign as _signed_cookies_sign,
    pack_signed_payload,
    unpack_signed_payload,
)
from app.db.pool import db

STATIC_DIR = Path(__file__).parent / 'static'
DIST_DIR = STATIC_DIR / 'dist'
SESSION_COOKIE = 'copilotoia_admin_session'
STATE_COOKIE = 'copilotoia_admin_oauth_state'
SESSION_TTL_SECONDS = 8 * 60 * 60

router = APIRouter()
_sessions: dict[str, dict[str, Any]] = {}
# BUG-133: `support` no es un rol — es un modo (`support_mode` flag/cookie).
# Ver `app/core/security.py::_ROLE_LEVELS` para la racional completa.
_ROLE_LEVELS = {'agent': 10, 'manager': 20, 'admin': 30, 'owner': 40}
_PRIVILEGED_ROLES = {'admin', 'owner', 'platform_owner'}


# BUG-008: el wire format del cookie (HMAC-SHA256 + base64url) se extrajo a
# `app/core/signed_cookies.py` para que el endpoint nuevo /v1/me/support-mode
# pueda reusarlo sin duplicación. Estos wrappers locales preservan la API
# anterior (`_sign(value)` / `_pack_state(payload)` / `_unpack_state(value)`)
# que el resto del módulo usaba; solo cambia que el secret se inyecta a
# través del helper en vez de leerse implícitamente.
def _sign(value: str) -> str:
    settings = get_admin_settings()
    return _signed_cookies_sign(settings.state_secret, value)


def _pack_state(payload: dict[str, Any]) -> str:
    settings = get_admin_settings()
    return pack_signed_payload(settings.state_secret, payload)


def _unpack_state(value: str) -> dict[str, Any] | None:
    settings = get_admin_settings()
    return unpack_signed_payload(settings.state_secret, value)


def _auth0_base_url() -> str:
    settings = get_admin_settings()
    if not settings.auth0_domain:
        raise HTTPException(status_code=503, detail='Auth0/OIDC is not configured')
    return f"https://{settings.auth0_domain.rstrip('/')}"


def _admin_client_secret() -> str:
    settings = get_admin_settings()
    if settings.auth0_admin_client_secret:
        return settings.auth0_admin_client_secret
    if settings.auth0_admin_client_secret_file:
        secret_path = Path(settings.auth0_admin_client_secret_file)
        if secret_path.exists():
            return secret_path.read_text(encoding='utf-8').strip()
    raise HTTPException(status_code=503, detail='Auth0 admin client secret is not configured')


def _callback_url(request: Request) -> str:
    settings = get_admin_settings()
    urls = [url.strip() for url in settings.auth0_callback_urls.split(',') if url.strip()]
    for url in urls:
        if url.startswith('http://localhost:3000/') or url.startswith('https://'):
            return url
    return str(request.url_for('admin_auth0_callback'))


def _logout_return_to(request: Request) -> str:
    settings = get_admin_settings()
    urls = [url.strip() for url in settings.auth0_logout_urls.split(',') if url.strip()]
    for url in urls:
        normalized_url = url.rstrip('/')
        if normalized_url.endswith('/admin'):
            return f'{normalized_url}/'
    if urls:
        return urls[0]
    return str(request.url_for('admin_index'))


def _active_session_id(session_id: str | None) -> dict[str, Any] | None:
    if not session_id:
        return None
    session = _sessions.get(session_id)
    if not session or session['expires_at'] < time.time():
        if session_id:
            _sessions.pop(session_id, None)
        return None
    return session


def _role_at_least(role: str, minimum_role: str) -> bool:
    return _ROLE_LEVELS.get(role, 0) >= _ROLE_LEVELS[minimum_role]


def _has_admin_role(session: dict[str, Any], minimum_role: str) -> bool:
    roles = session.get('profile', {}).get('roles') or []
    return any(_role_at_least(role, minimum_role) for role in roles)


def _session_claim_matches_tenant(session: dict[str, Any], tenant_id: UUID) -> bool:
    profile = session.get('profile') or {}
    try:
        return UUID(str(profile.get('tenant_id'))) == tenant_id
    except (TypeError, ValueError):
        return False


async def _session_can_stream_tenant(
    session: dict[str, Any],
    tenant_id: UUID,
    *,
    support_cookie_tid: str | None = None,
) -> bool:
    """Authorize a WS stream subscription with a tenant DB-check.

    A2 fix sobre BUG-196: el shortcut histórico aceptaba el WS cuando la
    sesión cacheada tenía `profile.support_mode=true` Y rol admin. Pero el
    claim `support_mode` viene del JWT y NO se invalida si Auth0 RBAC
    revoca al user — la sesión cacheada lo seguía permitiendo hasta el
    próximo login. Ahora el shortcut SOLO aplica si:
      1. Hay una cookie firmada `copilotoia_support_mode` activa Y
      2. Su `tid` matchea el `tenant_id` del WS Y
      3. El cache de sesión tiene rol admin (defense-in-depth).
    Sin la cookie firmada, caemos al DB-check de membresía
    (`app.user_tenant_roles`) que es source-of-truth para tenant access.

    Para revocar acceso WS cross-tenant: el platform_owner debe
    DELETE /v1/me/support-mode/{tid} (limpia cookie) O ser removido de
    Auth0 RBAC (próximo refresh del JWT invalida claim).
    """
    profile = session.get('profile') or {}
    # Shortcut endurecido: cookie firmada activa para ESTE tenant + rol admin
    # cacheado. Sin la cookie no aplica — la prueba está en `pack_signed_payload`
    # firmado con jwt_secret, no en el claim del JWT cacheado.
    if (
        support_cookie_tid is not None
        and support_cookie_tid == str(tenant_id)
        and _has_admin_role(session, 'agent')
    ):
        return True
    sub = profile.get('sub')
    if not db.pool or not sub:
        return False
    async with db.pool.acquire() as conn:
        roles = await conn.fetch(
            """
            select utr.role
            from app.users u
            join app.user_tenant_roles utr on utr.user_id = u.id
            where u.auth_subject=$1 and utr.tenant_id=$2
            """,
            sub,
            tenant_id,
        )
    return any(_role_at_least(row['role'], 'agent') for row in roles)


def _active_session(request: Request) -> dict[str, Any] | None:
    return _active_session_id(request.cookies.get(SESSION_COOKIE))


def _core_api_url(path: str, query: str = '') -> str:
    base_url = get_admin_settings().admin_core_api_base_url.rstrip('/')
    normalized_path = path.lstrip('/')
    url = f'{base_url}/{normalized_path}'
    if query:
        return f'{url}?{query}'
    return url


# BUG-008 (codex P1 fix): cookies que el browser puede mandar al BFF y
# que SÍ queremos forwardear al Core. Es un allowlist deliberado — NO
# forwardamos `copilotoia_admin_session` (es opaco al Core y daría info
# innecesaria al cluster productivo). Solo `copilotoia_support_mode` que
# el Core necesita leer para bumpear `request.state.support_mode` en
# `authenticate_request`.
_CORE_API_FORWARDED_COOKIES = ('copilotoia_support_mode',)


def _is_platform_scoped_path(path: str) -> bool:
    """Decide si el path upstream requiere un token UNSCOPED (sin tenant).

    Estos endpoints están gateados por `require_platform_owner` que
    explícitamente rechaza requests con `request.state.tenant_id != None`
    (porque la operación es cross-tenant, no de un tenant particular).
    Por lo tanto el BFF NO debe inyectarles `X-Tenant-Id` desde el cookie
    de support_mode — quedarían bloqueadas con 403 "requires an unscoped
    token" aunque el platform_owner tenga sesión válida.

    El cookie de support_mode SÍ debe seguir forwardeándose (en el
    header `cookie`) — `authenticate_request` lo usa para bumpear
    `support_mode=True` cuando el header X-Tenant-Id está presente,
    pero IGNORA el cookie si el header no llega, exactamente el
    comportamiento que necesitamos para endpoints platform-scoped.

    `path` viene SIN el prefijo `/admin/api/core/` (el proxy ya lo
    strippeó). Ej: `v1/tenants`, `v1/platform/incidents`, `v1/me/tenants`.
    """
    # Normaliza para comparar (puede o no empezar con slash).
    p = path.lstrip('/')
    if p.startswith('v1/tenants'):
        return True
    if p.startswith('v1/platform/'):
        return True
    if p.startswith('v1/me/') or p == 'v1/me':
        return True
    return False


def _tenant_id_from_support_cookie(request: Request) -> str | None:
    """Lee el `tid` del cookie `copilotoia_support_mode` firmado.

    El cookie es un payload firmado por `jwt_secret` (ver `app.core.signed_cookies`).
    Devuelve el `tid` (UUID str) si el cookie está presente Y la firma es
    válida; `None` en cualquier otro caso (sin cookie, firma inválida,
    expirado). El backend `authenticate_request` re-valida sub+tid+exp,
    así que este lookup es solo "best-effort" para popular el header.
    """
    from app.core.config import get_settings  # noqa: PLC0415
    from app.core.security import SUPPORT_MODE_COOKIE_NAME  # noqa: PLC0415
    from app.core.signed_cookies import unpack_signed_payload  # noqa: PLC0415

    raw = request.cookies.get(SUPPORT_MODE_COOKIE_NAME)
    if not raw:
        return None
    payload = unpack_signed_payload(get_settings().jwt_secret, raw)
    if not payload:
        return None
    tid = payload.get('tid')
    if isinstance(tid, str) and tid:
        return tid
    return None


def _core_api_headers(
    request: Request,
    session: dict[str, Any],
    has_body: bool,
    *,
    path: str = '',  # path upstream (sin /admin/api/core/) — usado para
                     # decidir si inyectar X-Tenant-Id desde cookie o no.
) -> dict[str, str]:
    # The admin proxy is a backend-for-frontend protected by the HttpOnly
    # session cookie. Never trust or forward a browser-supplied Authorization
    # header here: stale tokens from previous sessions or tokens minted for a
    # different audience make the Core API reject otherwise valid panel calls.
    headers = {
        'authorization': f"Bearer {session['access_token']}",
        'accept': request.headers.get('accept', 'application/json'),
    }
    if has_body and request.headers.get('content-type'):
        headers['content-type'] = request.headers['content-type']
    # X-Tenant-Id: 1) si el browser lo manda explícito (caso POST/PATCH de
    # endpoints tenant-scoped), respetarlo. 2) si NO lo manda pero hay un
    # cookie de support_mode con `tid`, extraerlo del cookie. Sin (2),
    # cualquier GET del SPA que no incluya el header (la mayoría — los
    # fetches de coreApi.js no agregan X-Tenant-Id automáticamente) llega
    # al backend sin tenant → `authenticate_request` no resuelve
    # `tenant_id` → cualquier dep que lo requiera devuelve 401/404.
    #
    # EXCEPCIÓN — endpoints platform-scoped: `/v1/tenants`, `/v1/platform/*`,
    # `/v1/me/*` requieren un token UNSCOPED (sin tenant_id). Si inyectáramos
    # el header desde la cookie, `require_platform_owner` los rechazaría con
    # 403 "Platform administration requires an unscoped token". El SPA del
    # platform_owner navegando en /admin/platform/* DEBE poder listar tenants
    # aunque tenga cookie de support_mode activa para un tenant específico.
    if request.headers.get('x-tenant-id'):
        headers['x-tenant-id'] = request.headers['x-tenant-id']
    elif not _is_platform_scoped_path(path):
        # Fallback: leer `tid` del cookie support_mode firmado. SOLO para
        # endpoints tenant-scoped (módulos opt-in). Para platform-scoped
        # endpoints (`/v1/tenants`, `/v1/platform/*`, `/v1/me/*`), NO
        # inyectamos — esos requieren un token UNSCOPED.
        cookie_tid = _tenant_id_from_support_cookie(request)
        if cookie_tid:
            headers['x-tenant-id'] = cookie_tid
    if request.headers.get('idempotency-key'):
        headers['idempotency-key'] = request.headers['idempotency-key']
    profile = session.get('profile') or {}
    if profile.get('email'):
        headers['x-admin-user-email'] = profile['email']
    if profile.get('name'):
        headers['x-admin-user-name'] = profile['name']
    # BUG-228 (codex P1 follow-up sobre BUG-195): el Core API necesita un
    # email "confiable" para upsertear `app.users.email` (los access tokens
    # Auth0 no traen claim `email` en esta config). El header
    # `X-Admin-User-Email` solo es informativo — un caller con bearer token
    # directo puede spoofearlo. Acá emitimos `X-Admin-Identity` con
    # `pack_signed_payload(jwt_secret, {sub, email, exp})` que el Core
    # valida para confirmar que (a) la firma matchea (caller tiene
    # `jwt_secret` = solo el BFF), (b) `sub` matchea el JWT, (c) no expiró.
    sub = profile.get('sub')
    email = profile.get('email')
    if sub and email:
        from app.core.config import get_settings  # noqa: PLC0415
        from app.core.signed_cookies import pack_signed_payload  # noqa: PLC0415

        jwt_secret = get_settings().jwt_secret
        # TTL corto (1h) — el header solo se usa en requests Core que el BFF
        # acaba de proxiar, no se cachea client-side.
        exp_ts = int(time.time()) + 3600
        identity_payload = {'sub': sub, 'email': email, 'exp': exp_ts}
        headers['x-admin-identity'] = pack_signed_payload(jwt_secret, identity_payload)
    # BUG-008 (codex P1 fix): el endpoint `/v1/me/support-mode/{tenant_id}`
    # emite una cookie `copilotoia_support_mode` que `authenticate_request`
    # lee en cada request al Core para bumpear `support_mode`. Sin forwarding,
    # el browser nunca recibe la cookie y la próxima request del panel sigue
    # con `support_mode=false` → el toggle no aplica.
    forwarded_cookies = []
    for name in _CORE_API_FORWARDED_COOKIES:
        value = request.cookies.get(name)
        if value:
            forwarded_cookies.append(f'{name}={value}')
    if forwarded_cookies:
        headers['cookie'] = '; '.join(forwarded_cookies)
    return headers


def _namespaced_claim(claims: dict[str, Any], name: str, default: Any = None) -> Any:
    namespace = get_admin_settings().auth0_claims_namespace.rstrip('/')
    return claims.get(f'{namespace}/{name}', default)


def _dist_file(path: str = 'index.html') -> FileResponse:
    file_path = (DIST_DIR / path).resolve()
    if not file_path.is_relative_to(DIST_DIR.resolve()) or not file_path.exists():
        raise HTTPException(
            status_code=503,
            detail=(
                'Admin Panel React build is missing. Run '
                './scripts/bootstrap-admin-panel.sh --skip-docker '
                'or build the admin-panel Docker image.'
            ),
        )
    return FileResponse(file_path)


@router.get('/', include_in_schema=False)
async def admin_root() -> RedirectResponse:
    return RedirectResponse('/admin/', status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get('/admin', include_in_schema=False)
@router.get('/admin/', include_in_schema=False)
async def admin_index() -> FileResponse:
    return _dist_file()


@router.get('/admin/assets/{asset_path:path}', include_in_schema=False)
async def admin_assets(asset_path: str) -> FileResponse:
    return _dist_file(f'assets/{asset_path}')


@router.get('/favicon.ico', include_in_schema=False)
async def admin_favicon() -> Response:
    return Response(status_code=204)


@router.get('/admin/login', include_in_schema=False)
async def admin_login(request: Request) -> RedirectResponse:
    if _active_session(request):
        return RedirectResponse('/admin/', status_code=status.HTTP_303_SEE_OTHER)

    settings = get_admin_settings()
    if not settings.auth0_admin_client_id or not settings.auth0_audience:
        raise HTTPException(
            status_code=503,
            detail='Auth0 admin client ID or audience is not configured',
        )

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    callback_url = _callback_url(request)
    state_cookie = _pack_state({'state': state, 'nonce': nonce, 'created_at': int(time.time())})
    authorization_params = {
        'response_type': 'code',
        'client_id': settings.auth0_admin_client_id,
        'redirect_uri': callback_url,
        'scope': 'openid profile email offline_access',
        'audience': settings.auth0_audience,
        'state': state,
        'nonce': nonce,
    }
    authorization_url = f'{_auth0_base_url()}/authorize?{urlencode(authorization_params)}'
    response = RedirectResponse(authorization_url)
    response.set_cookie(
        STATE_COOKIE,
        state_cookie,
        httponly=True,
        samesite='lax',
        secure=settings.cookies_secure,
        max_age=600,
    )
    return response


@router.get('/callback', include_in_schema=False, name='admin_auth0_callback')
@router.get('/admin/callback', include_in_schema=False)
async def admin_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> RedirectResponse:
    if error:
        raise HTTPException(
            status_code=400,
            detail=f'{error}: {error_description or "Auth0 login failed"}',
        )
    if not code or not state:
        raise HTTPException(status_code=400, detail='Missing OAuth code or state')

    state_payload = _unpack_state(request.cookies.get(STATE_COOKIE, ''))
    if (
        not state_payload
        or state_payload.get('state') != state
        or state_payload.get('created_at', 0) < time.time() - 600
    ):
        raise HTTPException(status_code=400, detail='Invalid or expired OAuth state')

    settings = get_admin_settings()
    callback_url = _callback_url(request)
    async with httpx.AsyncClient(timeout=10) as client:
        token_response = await client.post(
            f'{_auth0_base_url()}/oauth/token',
            headers={'content-type': 'application/json'},
            json={
                'grant_type': 'authorization_code',
                'client_id': settings.auth0_admin_client_id,
                'client_secret': _admin_client_secret(),
                'code': code,
                'redirect_uri': callback_url,
            },
        )
        if token_response.status_code >= 400:
            raise HTTPException(
                status_code=401,
                detail='Could not exchange Auth0 authorization code',
            )
        tokens = token_response.json()

        userinfo_response = await client.get(
            f'{_auth0_base_url()}/userinfo',
            headers={'authorization': f"Bearer {tokens['access_token']}"},
        )
        if userinfo_response.status_code >= 400:
            raise HTTPException(status_code=401, detail='Could not fetch Auth0 user profile')
        userinfo = userinfo_response.json()

    # SEC: validamos la firma del id_token contra el JWKS de Auth0. ANTES
    # decodificábamos con base64 raw (sin firma) → un atacante con un
    # access_token válido podía forjar un id_token con `amr=['mfa']` y
    # bypassear el MFA enforcement del BFF. Ahora exigimos firma RS256
    # válida + audience = admin client_id + issuer = nuestro tenant Auth0.
    id_token_claims: dict[str, Any] = {}
    id_token = tokens.get('id_token')
    if id_token:
        if not settings.auth0_domain or not settings.auth0_admin_client_id:
            raise HTTPException(
                status_code=500,
                detail='Auth0 admin client_id no configurado; no se puede validar id_token',
            )
        id_token_claims = await decode_auth0_id_token(
            id_token,
            audience=settings.auth0_admin_client_id,
            auth0_domain=settings.auth0_domain,
            auth0_issuer=settings.auth0_issuer,
        )

    claims = {**id_token_claims, **userinfo}

    # Auth0 sets amr=['mfa'] in the id_token when a second factor was used.
    # El claim AHORA viene del id_token con firma verificada — no es forgeable.
    amr = id_token_claims.get('amr') or claims.get('amr') or []
    if isinstance(amr, str):
        amr = [amr]
    mfa_verified = 'mfa' in amr

    session_id = secrets.token_urlsafe(32)
    _sessions[session_id] = {
        'expires_at': time.time() + SESSION_TTL_SECONDS,
        'access_token': tokens['access_token'],
        'id_token': id_token,
        'profile': {
            'sub': claims.get('sub'),
            'name': claims.get('name') or claims.get('nickname') or claims.get('email'),
            'email': claims.get('email'),
            'picture': claims.get('picture'),
            'tenant_id': _namespaced_claim(claims, 'tenant_id'),
            'tenant_slug': _namespaced_claim(claims, 'tenant_slug'),
            'roles': _namespaced_claim(claims, 'roles', []),
            'permissions': _namespaced_claim(claims, 'permissions', []),
            'support_mode': _namespaced_claim(claims, 'support_mode', False),
            'mfa_verified': mfa_verified,
        },
    }
    response = RedirectResponse('/admin/')
    response.delete_cookie(STATE_COOKIE)
    # `samesite='strict'` para la session cookie es defensa contra CSRF
    # cross-origin (el browser NO la adjunta en navegación cross-site, ni
    # siquiera en top-level POSTs). `secure=True` cuando no estamos en
    # `local` para forzar HTTPS-only.
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        samesite='strict',
        secure=settings.cookies_secure,
        max_age=SESSION_TTL_SECONDS,
    )
    return response


@router.post('/admin/logout', include_in_schema=False)
async def admin_logout(request: Request) -> RedirectResponse:
    # CSRF gate: el form POST debe venir del mismo origin. Sin esto, un
    # sitio externo podría disparar el logout del usuario con un form
    # cross-origin (aunque la cookie SameSite=strict ya lo previene, esto
    # es defensa-en-profundidad y evita falsos positivos por cookies de
    # navegadores viejos).
    if not _csrf_origin_ok(request):
        raise HTTPException(status_code=403, detail='csrf_check_failed')
    settings = get_admin_settings()
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_id:
        _sessions.pop(session_id, None)
    return_to = _logout_return_to(request)
    logout_params = {'client_id': settings.auth0_admin_client_id or '', 'returnTo': return_to}
    logout_url = (
        f'{_auth0_base_url()}/v2/logout?{urlencode(logout_params)}'
        if settings.auth0_domain and settings.auth0_admin_client_id
        else '/admin/'
    )
    response = RedirectResponse(logout_url, status_code=status.HTTP_303_SEE_OTHER)
    response.delete_cookie(SESSION_COOKIE)
    return response


def _session_mfa_required(session: dict[str, Any]) -> bool:
    """Return True only when Auth0 is active, the session has a privileged role
    and MFA was not completed.  In local/dev mode (no AUTH0_DOMAIN) the check
    is always skipped so the panel remains accessible without MFA.  It is also
    skipped when ``mfa_enforcement_enabled`` is False (Auth0 plans without the
    MFA add-on cannot serve the challenge flow).
    """
    settings = get_admin_settings()
    if not settings.mfa_enforcement_enabled:
        return False
    if not settings.auth0_domain:
        return False
    profile = session.get('profile') or {}
    roles = set(profile.get('roles') or [])
    if not roles.intersection(_PRIVILEGED_ROLES):
        return False
    return not profile.get('mfa_verified', False)


@router.get('/admin/api/session')
async def admin_session(request: Request) -> Response:
    session = _active_session(request)
    if not session:
        return Response(status_code=401)
    profile = session['profile']
    return Response(
        json.dumps(
            {
                'authenticated': True,
                'profile': profile,
                'mfa_required': _session_mfa_required(session),
                'api': {
                    'baseUrl': '/admin/api/core/v1',
                    'audience': get_admin_settings().auth0_audience,
                },
                'modules': [
                    {'id': 'tenant-setup', 'label': 'Tenant Setup'},
                    {'id': 'team', 'label': 'Equipo'},
                ],
            }
        ),
        media_type='application/json',
    )


@router.get('/admin/api/mfa-status')
async def admin_mfa_status(request: Request) -> Response:
    session = _active_session(request)
    if not session:
        return Response(status_code=401)
    profile = session.get('profile') or {}
    roles = set(profile.get('roles') or [])
    is_privileged = bool(roles.intersection(_PRIVILEGED_ROLES))
    mfa_verified = profile.get('mfa_verified', False)
    return Response(
        json.dumps(
            {
                'mfa_verified': mfa_verified,
                'is_privileged': is_privileged,
                'mfa_required': is_privileged and not mfa_verified,
                'privileged_roles': sorted(roles.intersection(_PRIVILEGED_ROLES)),
            }
        ),
        media_type='application/json',
    )


def _support_cookie_tid_from_ws(websocket: WebSocket) -> str | None:
    """A2: lee el `tid` del cookie firmado de support_mode desde un WebSocket."""
    from app.core.config import get_settings  # noqa: PLC0415
    from app.core.security import SUPPORT_MODE_COOKIE_NAME  # noqa: PLC0415
    from app.core.signed_cookies import unpack_signed_payload  # noqa: PLC0415

    raw = websocket.cookies.get(SUPPORT_MODE_COOKIE_NAME)
    if not raw:
        return None
    payload = unpack_signed_payload(get_settings().jwt_secret, raw)
    if not payload:
        return None
    tid = payload.get('tid')
    return tid if isinstance(tid, str) and tid else None


@router.websocket('/admin/api/core/v1/conversations/stream')
async def admin_conversations_stream(websocket: WebSocket) -> None:
    session = _active_session_id(websocket.cookies.get(SESSION_COOKIE))
    if not session:
        await websocket.close(code=1008, reason='admin_session_required')
        return
    tenant_id_param = websocket.query_params.get('tenant_id')
    try:
        tenant_id = UUID(str(tenant_id_param))
    except (TypeError, ValueError):
        await websocket.close(code=1008, reason='invalid_tenant_id')
        return
    if not db.pool:
        await websocket.close(code=1011, reason='database_pool_unavailable')
        return
    support_cookie_tid = _support_cookie_tid_from_ws(websocket)
    if not await _session_can_stream_tenant(
        session, tenant_id, support_cookie_tid=support_cookie_tid,
    ):
        await websocket.close(code=1008, reason='tenant_agent_role_required')
        return

    await websocket.accept()

    # AUDIT-47 / BUG-50 (2026-05-18): antes acquire-eábamos UN pool conn POR
    # socket y lo manteníamos durante todo el ciclo del WS — 10 sockets
    # simultáneos = pool agotado = app caída para toda la flota. Ahora todos
    # los WS comparten UNA sola conn vía `ws_fanout` (LISTEN + fanout
    # in-memory). El operador puede abrir 100 tabs sin tocar el pool más
    # allá del primer subscriber.
    # AUDIT-49: si el supervisor murió 2 veces seguidas (DB down), subscribe
    # levanta RuntimeError — cerramos con 1011 (Internal Error) en vez de
    # colgar el socket o devolver 200.
    try:
        queue = await ws_fanout.subscribe(db.pool, tenant_id)
    except RuntimeError:
        await websocket.close(code=1011, reason='listen_unavailable')
        return
    try:
        await websocket.send_json({'type': 'connected', 'tenant_id': str(tenant_id)})
        while True:
            try:
                payload = await asyncio.wait_for(queue.get(), timeout=25)
                await websocket.send_text(payload)
            except asyncio.TimeoutError:
                await websocket.send_json({'type': 'heartbeat', 'tenant_id': str(tenant_id)})
    except WebSocketDisconnect:
        return
    finally:
        await ws_fanout.unsubscribe(tenant_id, queue)


_SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})


def _csrf_origin_ok(request: Request) -> bool:
    """CSRF defense: para mutaciones exigimos prueba de same-origin.

    Aceptamos cualquiera de:
      - `Sec-Fetch-Site: same-origin` (browsers modernos lo setean automáticamente
        cuando el fetch sale del mismo origin; no se puede falsificar cross-site).
      - `X-Requested-With: XMLHttpRequest` o `fetch` (no es un header simple por
        CORS, browsers solo lo permiten en same-origin sin preflight).
      - `Origin` matching el host del request.

    Esto bloquea el escenario "form HTML cross-origin envía POST a /admin/api/*
    aprovechando el cookie SameSite=lax". La cookie de sesión es ahora
    SameSite=strict (otro fix), pero defensa-en-profundidad.
    """
    sec_fetch_site = request.headers.get('sec-fetch-site', '')
    if sec_fetch_site == 'same-origin' or sec_fetch_site == 'none':
        return True
    requested_with = request.headers.get('x-requested-with', '').lower()
    if requested_with in {'xmlhttprequest', 'fetch'}:
        return True
    origin = request.headers.get('origin', '')
    host = request.headers.get('host', '')
    if origin and host:
        # http://host or https://host
        origin_host = origin.split('://', 1)[-1]
        if origin_host == host:
            return True
    return False


@router.api_route(
    '/admin/api/core/{path:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE']
)
async def admin_core_api_proxy(path: str, request: Request) -> Response:
    session = _active_session(request)
    if not session:
        return Response(status_code=401)

    # CSRF gate: para mutaciones (POST/PUT/PATCH/DELETE) exigimos prueba de
    # same-origin. Defensa-en-profundidad sobre la cookie SameSite=strict.
    if request.method not in _SAFE_METHODS and not _csrf_origin_ok(request):
        return Response(
            content=json.dumps({'detail': 'csrf_check_failed'}),
            status_code=403,
            media_type='application/json',
        )

    # TASK-0080 / BUG14: the BFF must refuse to relay any request when the
    # session is privileged but MFA was not completed. Without this gate, the
    # frontend overlay could be bypassed (e.g. by calling the API directly with
    # the session cookie) and the Core API would happily serve the request
    # because the BFF runs as the user.
    if _session_mfa_required(session):
        return Response(
            content=json.dumps({'detail': 'mfa_required'}),
            status_code=403,
            media_type='application/json',
        )

    body = await request.body()
    target_url = _core_api_url(path, request.url.query)
    headers = _core_api_headers(request, session, has_body=bool(body), path=path)
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            upstream_response = await client.request(
                request.method,
                target_url,
                content=body or None,
                headers=headers,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                'Admin proxy could not reach core API at '
                f'{get_admin_settings().admin_core_api_base_url}'
            ),
        ) from exc

    response_headers = {}
    content_type = upstream_response.headers.get('content-type')
    if content_type:
        response_headers['content-type'] = content_type
    proxied = Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
    )
    # BUG-008 (codex P1 fix): forwardear `Set-Cookie` del Core al browser.
    # Sin esto, la cookie `copilotoia_support_mode` que el endpoint
    # `/v1/me/support-mode/{tenant_id}` emite NUNCA llega al browser y el
    # toggle nunca persiste. Una sola response puede tener MÚLTIPLES
    # `Set-Cookie` (POST emite cookie nuevo, DELETE emite cookie expirado),
    # así que usamos `httpx.Headers.get_list('set-cookie')` (`.get` solo
    # devuelve el primero) y `MutableHeaders.append` (Starlette soporta
    # multi-value via append; pasar como dict colapsaría a uno solo).
    for set_cookie in upstream_response.headers.get_list('set-cookie'):
        proxied.headers.append('set-cookie', set_cookie)
    return proxied


# BUG-002 fix: SPA fallback. Any `/admin/<react-router-path>` that the user
# hits via hard refresh, deep link or back-button hits this catch-all. The
# specific routes above (`/admin/login`, `/admin/logout`, `/admin/callback`,
# `/admin/assets/*`, `/admin/api/*`, websocket) match first per FastAPI's
# registration order; everything else (`/admin/no-tenant`, `/admin/onboarding`,
# `/admin/t/<slug>/<module>`, `/admin/account/profile`, ...) returns the SPA
# index.html and React Router takes over client-side. Before this fix a hard
# refresh on any non-root admin path returned `{"detail":"Not Found"}` and
# the user had no way back without re-typing the URL.
#
# MUST be the LAST route registered in this module so that all the specific
# `/admin/*` handlers (auth, proxy, assets) win the match-by-order race.
@router.get('/admin/{spa_path:path}', include_in_schema=False)
async def admin_spa_fallback(spa_path: str) -> FileResponse:
    return _dist_file()
