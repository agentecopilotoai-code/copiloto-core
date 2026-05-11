from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
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
from app.db.pool import db

STATIC_DIR = Path(__file__).parent / 'static'
DIST_DIR = STATIC_DIR / 'dist'
SESSION_COOKIE = 'copilotoia_admin_session'
STATE_COOKIE = 'copilotoia_admin_oauth_state'
SESSION_TTL_SECONDS = 8 * 60 * 60

router = APIRouter()
_sessions: dict[str, dict[str, Any]] = {}
_ROLE_LEVELS = {'agent': 10, 'manager': 20, 'admin': 30, 'owner': 40, 'support': 50}
_PRIVILEGED_ROLES = {'admin', 'owner', 'platform_owner'}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def _sign(value: str) -> str:
    settings = get_admin_settings()
    digest = hmac.new(
        settings.state_secret.encode('utf-8'),
        value.encode('utf-8'),
        hashlib.sha256,
    ).digest()
    return _b64url(digest)


def _pack_state(payload: dict[str, Any]) -> str:
    raw = _b64url(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
    return f'{raw}.{_sign(raw)}'


def _unpack_state(value: str) -> dict[str, Any] | None:
    raw, separator, signature = value.partition('.')
    if not separator or not hmac.compare_digest(_sign(raw), signature):
        return None
    padding = '=' * (-len(raw) % 4)
    return json.loads(base64.urlsafe_b64decode(raw + padding))


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


async def _session_can_stream_tenant(session: dict[str, Any], tenant_id: UUID) -> bool:
    profile = session.get('profile') or {}
    if profile.get('support_mode') and _has_admin_role(session, 'agent'):
        return True
    if _session_claim_matches_tenant(session, tenant_id) and _has_admin_role(session, 'agent'):
        return True
    if not db.pool or not profile.get('sub'):
        return False
    async with db.pool.acquire() as conn:
        roles = await conn.fetch(
            """
            select utr.role
            from app.users u
            join app.user_tenant_roles utr on utr.user_id = u.id
            where u.auth_subject=$1 and utr.tenant_id=$2
            """,
            profile['sub'],
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


def _core_api_headers(
    request: Request, session: dict[str, Any], has_body: bool
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
    if request.headers.get('x-tenant-id'):
        headers['x-tenant-id'] = request.headers['x-tenant-id']
    if request.headers.get('idempotency-key'):
        headers['idempotency-key'] = request.headers['idempotency-key']
    profile = session.get('profile') or {}
    if profile.get('email'):
        headers['x-admin-user-email'] = profile['email']
    if profile.get('name'):
        headers['x-admin-user-name'] = profile['name']
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
    response.set_cookie(STATE_COOKIE, state_cookie, httponly=True, samesite='lax', max_age=600)
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

    id_token_claims: dict[str, Any] = {}
    id_token = tokens.get('id_token')
    if id_token:
        payload_segment = id_token.split('.')[1]
        padding = '=' * (-len(payload_segment) % 4)
        id_token_claims = json.loads(base64.urlsafe_b64decode(payload_segment + padding))

    claims = {**id_token_claims, **userinfo}

    # Auth0 sets amr=['mfa'] in the id_token when a second factor was used.
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
    response.set_cookie(
        SESSION_COOKIE,
        session_id,
        httponly=True,
        samesite='lax',
        max_age=SESSION_TTL_SECONDS,
    )
    return response


@router.post('/admin/logout', include_in_schema=False)
async def admin_logout(request: Request) -> RedirectResponse:
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
    is always skipped so the panel remains accessible without MFA.
    """
    settings = get_admin_settings()
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
                    {'id': 'whatsapp', 'label': 'WhatsApp'},
                    {'id': 'knowledge-storage', 'label': 'Storage S3'},
                    {'id': 'knowledge-studio', 'label': 'Knowledge Studio'},
                    {'id': 'operations-desk', 'label': 'Operations Desk'},
                    {'id': 'audit', 'label': 'Audit'},
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
    if not await _session_can_stream_tenant(session, tenant_id):
        await websocket.close(code=1008, reason='tenant_agent_role_required')
        return

    await websocket.accept()
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)

    def listener(_connection, _pid, _channel, payload: str) -> None:
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            return
        if event.get('tenant_id') != str(tenant_id):
            return
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            queue.get_nowait()
            queue.put_nowait(payload)

    async with db.pool.acquire() as conn:
        await conn.add_listener('tenant_operations_events', listener)
        await conn.execute('listen tenant_operations_events')
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
            await conn.remove_listener('tenant_operations_events', listener)
            await conn.execute('unlisten tenant_operations_events')


@router.api_route(
    '/admin/api/core/{path:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE']
)
async def admin_core_api_proxy(path: str, request: Request) -> Response:
    session = _active_session(request)
    if not session:
        return Response(status_code=401)

    body = await request.body()
    target_url = _core_api_url(path, request.url.query)
    headers = _core_api_headers(request, session, has_body=bool(body))
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
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=response_headers,
    )
