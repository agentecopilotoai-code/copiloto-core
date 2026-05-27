from __future__ import annotations

import asyncio
import json
import os
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
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.admin.config import get_admin_settings
from app.admin.ws_fanout import fanout as ws_fanout
from app.core.security import (
    PRIVILEGED_ROLES as _PRIVILEGED_ROLES,
    decode_auth0_id_token,
)
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
# M65 — cookie efímero seteado por `GET /i/<token>` cuando el invitado
# clickea el link del email. Sobrevive el OAuth redirect (samesite=lax)
# para que el `/admin/callback` lo lea y dispare el `POST /v1/invitations/
# {token}/redeem` automáticamente, sin pasarle el token al SPA. TTL corto
# (10 min) — el invitado tiene que loguearse rápido o repetir el link.
PENDING_INVITATION_COOKIE = 'copilotoia_pending_invitation'
PENDING_INVITATION_TTL_SECONDS = 10 * 60
# M60/B-002 — TTL del cookie + del session dict. Antes hardcoded 8h, pero
# el `access_token` de Auth0 vive 2h por default (configure-auth0.sh
# emite `lifetime_in_seconds=7200`). El desalineamiento causaba:
# user con cookie válido pero token expirado → proxy upstream 401 → SPA
# rota sin diagnóstico claro. Ahora capturamos `expires_in` del response
# de /oauth/token y usamos ESO como TTL real. SESSION_TTL_SECONDS_DEFAULT
# es el fallback si Auth0 no incluye el campo (no debería pasar).
SESSION_TTL_SECONDS_DEFAULT = 2 * 60 * 60  # 2h matches Auth0 default
# Backwards-compat alias for tests that imported el nombre histórico.
SESSION_TTL_SECONDS = SESSION_TTL_SECONDS_DEFAULT

router = APIRouter()
# P0-3 (M70, audit 2026-05-27) — sessions ahora viven en un store
# pluggeable (InMemory por default, Redis si REDIS_URL está configurado).
# Multi-worker safe cuando se usa Redis.
#
# `_sessions` se mantiene como alias al dict subyacente del InMemory
# store para back-compat con tests que inyectan sessions directo
# (`_sessions[sid] = payload`). El alias se popula lazy en
# `_get_inmemory_raw_for_tests()` — si el store activo es Redis, el dict
# queda vacío y los tests que dependen de él fallan apropiadamente.
_sessions: dict[str, dict[str, Any]] = {}


def _get_inmemory_raw_for_tests() -> dict[str, dict[str, Any]]:
    """Back-compat para tests que mutan `_sessions` directo. Si el store
    activo es InMemory, retorna su dict interno y lo aliasea a `_sessions`
    para que `_sessions[sid] = X` siga funcionando. Si es Redis, retorna
    el `_sessions` original (los tests que dependen del dict deberían
    usar `set_session_store_for_tests(InMemorySessionStore())` explícito)."""
    global _sessions
    from app.admin.session_store import (  # noqa: PLC0415
        InMemorySessionStore, get_session_store,
    )
    store = get_session_store()
    if isinstance(store, InMemorySessionStore):
        _sessions = store._raw  # noqa: SLF001
    return _sessions
# M13 — `_PRIVILEGED_ROLES` se importa desde `app/core/security.py`
# (fuente única de verdad). `_ROLE_LEVELS` queda LOCAL al BFF a propósito:
# excluye `platform_owner` porque el BFF nunca debe tratarlo como un rol
# tenant-scoped — el platform_owner cruza tenants vía cookie `support_mode`,
# no escalando rol. Ver `_session_can_stream_tenant` para el contrato.
# BUG-133: `support` no es un rol — es un modo. No se incluye en el ladder.
_ROLE_LEVELS = {'agent': 10, 'manager': 20, 'admin': 30, 'owner': 40}


# ─── M47 — DEBUG instrumentation ──────────────────────────────────────────
# `print(..., flush=True)` aparece inmediato en `docker compose logs
# admin-panel`. Lo activamos sólo cuando `BFF_DEBUG=1` para no ensuciar
# producción. En dev local (.env arranca con BFF_DEBUG=1) cada paso del
# OAuth/session flow imprime una línea legible prefijada `[BFF-DEBUG]`.
_BFF_DEBUG = os.environ.get('BFF_DEBUG', '0') == '1'


# M52 — whitelist EXACTO de keys a redactar. Antes el matcher era
# substring → `id_token_keys` o `redirect_to` se redactaban perdiendo
# info diagnóstica. Ahora SOLO se trunca si la key matchea EXACTO uno
# de estos identificadores. Si agregás un parámetro sensible al log,
# tiene que llamarse igual que la entrada de la lista.
_REDACT_EXACT_KEYS = frozenset({
    'secret', 'client_secret', 'jwt_secret', 'auth0_admin_client_secret',
    'token', 'access_token', 'id_token', 'refresh_token', 'id_token_hint',
    'code', 'state', 'nonce',
    'sid', 'session_id', 'cookie',
})


def _should_redact(key: str) -> bool:
    """True si la key debe redactarse (match EXACTO contra whitelist)."""
    return key.lower() in _REDACT_EXACT_KEYS


def _debug(stage: str, **kwargs: Any) -> None:
    """Imprime una línea `[BFF-DEBUG] stage key=val key=val ...`.

    No usa logging porque queremos algo super visible en `docker compose
    logs` sin tocar la config del logger. `flush=True` evita que uvicorn
    bufferee la línea hasta el siguiente flush — la ves al instante.

    Cualquier valor cuya key matchee EXACT-WORD una de
    `_REDACT_EXACT_WORDS` se trunca a `<8 chars>…` para no dejar
    credenciales en los logs. Ver `_should_redact` para el detalle.
    """
    if not _BFF_DEBUG:
        return
    parts: list[str] = []
    for k, v in kwargs.items():
        if v is None:
            display = '∅'
        elif _should_redact(k):
            s = str(v)
            display = (s[:8] + '…') if len(s) > 8 else s
        else:
            display = str(v)
        parts.append(f'{k}={display}')
    print(f'[BFF-DEBUG] {stage:<28} ' + ' '.join(parts), flush=True)


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


async def _active_session_id(session_id: str | None) -> dict[str, Any] | None:
    """Async — el store puede ser Redis (IO real)."""
    if not session_id:
        _debug('_active_session_id', result='miss', reason='no_cookie')
        return None
    from app.admin.session_store import get_session_store  # noqa: PLC0415
    store = get_session_store()
    session = await store.get(session_id)
    if not session:
        _debug(
            '_active_session_id', result='miss', reason='zombie_or_expired',
            sid=session_id,
        )
        return None
    # `get()` ya filtra expired en el InMemory store; el Redis store
    # delega al TTL del server (no devuelve expired). Redundant check
    # acá por defensa-en-profundidad si el payload tiene expires_at viejo
    # pero el TTL fallback no actuó.
    if session.get('expires_at', 0) < time.time():
        _debug(
            '_active_session_id', result='miss', reason='ttl_expired',
            sid=session_id,
        )
        await store.delete(session_id)
        return None
    _debug(
        '_active_session_id', result='hit',
        sid=session_id, email=session.get('profile', {}).get('email'),
    )
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


async def _active_session(request: Request) -> dict[str, Any] | None:
    return await _active_session_id(request.cookies.get(SESSION_COOKIE))


# M46 — `_sessions` vive en memoria del proceso uvicorn. Cualquier reinicio
# del container (`docker compose restart admin-panel`) las pierde TODAS,
# pero la cookie en el browser queda apuntando a una `sid` que ya no
# existe — el endpoint devolvía 401 silencioso sin limpiar la cookie
# zombie. El usuario se quedaba "atascado" hasta limpiar cookies manual.
#
# Fix: cuando recibimos cookie pero no encontramos sesión, devolvemos
# body explicativo + `Set-Cookie` que elimina la cookie del browser. El
# frontend puede leer `reason` para mostrar mensaje claro tipo "tu
# sesión expiró, volvé a loguearte" en lugar del subtitle genérico.
def _unauthorized_session_response(request: Request) -> Response:
    """401 que indica claramente por qué (no_session vs session_expired)
    y limpia cookie zombie si existe.

    Reasons:
      - 'no_session'      → el browser nunca tuvo cookie (user nuevo).
      - 'session_expired' → cookie presente pero `_sessions` no la tiene
                            (server reiniciado, TTL pasó, o sesión purgada).
    """
    had_cookie = request.cookies.get(SESSION_COOKIE) is not None
    reason = 'session_expired' if had_cookie else 'no_session'
    body = json.dumps({'authenticated': False, 'reason': reason})
    response = Response(content=body, status_code=401, media_type='application/json')
    if had_cookie:
        # Borrar la cookie zombie — sin esto el browser sigue mandando
        # `sid=abc123` en cada request aunque el server ya no la reconozca.
        response.delete_cookie(SESSION_COOKIE, path='/', samesite='strict')
    return response


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


# M63 — atestación HMAC de MFA del BFF hacia el Core.
#
# Problema: Auth0 ejecuta las post-login Actions ANTES del MFA challenge.
# Resultado: el custom claim `mfa_verified` del access_token queda en
# `false` aunque el user haya completado MFA — el flujo Auth0 no re-corre
# las Actions después del MFA. El BFF detecta MFA via `amr=['mfa']` del
# id_token (Auth0 SÍ actualiza el id_token post-MFA), pero el Core valida
# el access_token y no ve evidencia de MFA.
#
# Fix: el BFF firma un assertion HMAC con `jwt_secret` (shared secret
# entre BFF y Core, ya usado para signed cookies). El Core verifica el
# HMAC + match de actor_id + freshness y promueve `mfa_verified=True`
# para esa request. Sin firma válida → comportamiento default (lee del
# JWT solo).
#
# Anti-spoof: el header requiere conocer `jwt_secret` (vive solo en
# containers backend, no expuesto). Un attacker que pegue al Core directo
# sin pasar por BFF NO puede forjar el header → mfa_verified=False → 403
# para roles privilegiados como antes.
#
# Anti-replay: timestamp con tolerancia de 60s. Después el assertion
# expira y hay que regenerarlo (lo hace el BFF en cada request del proxy).
_MFA_ATTESTATION_VALIDITY_SECONDS = 60


def _build_mfa_attestation(actor_id: str) -> dict[str, str]:
    """Genera los 4 headers `X-Auth-MFA-*` para que el Core confíe
    en que MFA fue completado por este actor.

    payload firmado: `mfa-verified:<actor_id>:<timestamp_ms>`
    """
    import hashlib  # noqa: PLC0415
    import hmac as _hmac  # noqa: PLC0415

    from app.core.config import get_settings  # noqa: PLC0415

    settings = get_settings()
    timestamp_ms = int(time.time() * 1000)
    payload = f'mfa-verified:{actor_id}:{timestamp_ms}'
    sig = _hmac.new(
        settings.jwt_secret.encode('utf-8'),
        payload.encode('utf-8'),
        hashlib.sha256,
    ).hexdigest()
    return {
        'x-auth-mfa-verified': '1',
        'x-auth-mfa-actor': actor_id,
        'x-auth-mfa-timestamp': str(timestamp_ms),
        'x-auth-mfa-signature': sig,
    }


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
    # M63 — atestación HMAC de MFA. Auth0 ejecuta las post-login Actions
    # ANTES del MFA challenge, entonces el `mfa_verified` custom claim del
    # access_token queda en `false`. El BFF detecta MFA via `amr=['mfa']`
    # del id_token (que SÍ se actualiza post-MFA) y lo asentamos en su
    # sesión cached. Para que el Core también confíe en MFA sin tener que
    # reemitir el access_token, firmamos un assertion HMAC con
    # `jwt_secret` (compartido entre BFF y Core). El Core verifica el
    # HMAC + match de actor + freshness y promueve `mfa_verified=True`.
    #
    # Si attacker pega al Core directo SIN pasar por el BFF, no tiene el
    # `jwt_secret` (vive en el container del BFF + Core) y el HMAC no
    # verifica → mfa_verified queda False → 403 para roles privilegiados.
    if profile.get('mfa_verified') and profile.get('sub'):
        attestation = _build_mfa_attestation(profile['sub'])
        headers.update(attestation)
    # M42 — `X-Admin-Identity` (HMAC-signed `{sub, email, exp}`) se emitía
    # como defense-in-depth contra spoof del `X-Admin-User-Email`, pero NUNCA
    # se montó un consumer en `app/core/security.py` ni en handler alguno.
    # Mejor borrarlo que dejar dead code firmando con secretos en cada
    # request. Si un módulo opt-in quiere re-introducirlo (e.g. para confiar
    # ciegamente del email aguas abajo), debe agregar el verifier primero.
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


# ─── M65 — Invitation landing page ───────────────────────────────────────
#
# `GET /i/<token>` es el link que llega en el email de invitación de Resend.
# El flow del invitado:
#
#   1. Click email → GET /i/<token>
#   2. BFF hace GET al Core /v1/invitations/<token> (público).
#      - Si 404 → muestra HTML "Invitación inválida o expirada".
#      - Si OK → setea cookie `pending_invitation` con SameSite=Lax (que
#        SOBREVIVE el redirect cross-site del OAuth flow — `strict` no)
#        y redirige a /admin/login.
#   3. Auth0 login (signup si el user es nuevo).
#   4. Auth0 callback → BFF crea session → detecta cookie pending →
#      POST /v1/invitations/<token>/redeem al Core con el access_token.
#   5. Borra el cookie, redirige a /admin/.
#
# El token nunca pasa al SPA (queda HttpOnly entre el browser del invitado
# y el BFF). El SPA solo ve un user logueado normal con su membership
# (que ya fue creada por `add_tenant_member` al mandar la invitación).


def _invitation_landing_html(
    *, ok: bool, title: str, message: str, cta_label: str | None,
    cta_url: str | None,
) -> str:
    """HTML mínimo, inline, sin assets externos. Match visual del admin
    panel no necesario (esta página la ve el invitado UNA vez antes del
    primer login).

    CONTRATO XSS: `title` y `message` se asumen HTML-safe (el caller debe
    pasar `_html.escape(...)` sobre cualquier dato no-controlado).
    `cta_label` y `cta_url` SÍ los escapamos acá porque son plain strings
    fijos del código (no del user input). Para `<title>` además
    re-escapamos por defensa-en-profundidad (consume el `<` del payload
    sin riesgo de doble-escape porque viene ya neutralizado).
    """
    import html as _html  # noqa: PLC0415

    cta_block = ''
    if cta_label and cta_url:
        cta_block = (
            f'<a href="{_html.escape(cta_url, quote=True)}" '
            'style="display:inline-block;margin-top:24px;padding:12px 24px;'
            'background:#2563eb;color:#fff;text-decoration:none;'
            'border-radius:8px;font-weight:600">'
            f'{_html.escape(cta_label)}</a>'
        )
    color = '#0f172a' if ok else '#dc2626'
    # `title` puede llevar HTML inline (ej. `<strong>X</strong>`) o texto
    # pre-escapado. NO doble-escapamos. Para el `<title>` del head sí
    # corremos un `strip_tags` cheap (split por `<`) para no romper
    # parseo del header en el browser.
    title_for_head = title.split('<')[0].split('&lt;')[0]
    return (
        '<!doctype html><html lang="es"><head>'
        '<meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<title>{_html.escape(title_for_head).strip() or "CopilotoIA"} · CopilotoIA</title>'
        '</head><body style="margin:0;font-family:-apple-system,'
        'BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;background:#f8fafc;'
        'color:#0f172a">'
        '<div style="max-width:480px;margin:80px auto;padding:32px;'
        'background:#fff;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,0.1);'
        'text-align:center">'
        f'<h1 style="margin:0 0 16px;color:{color};font-size:24px">'
        f'{title}</h1>'
        f'<p style="margin:0;color:#475569;font-size:16px;line-height:1.5">'
        f'{message}</p>'
        f'{cta_block}'
        '</div></body></html>'
    )


@router.get('/i/{token}', include_in_schema=False)
async def invitation_landing(token: str, request: Request) -> Response:
    """Landing del link de invitación que llega al inbox del invitado."""
    import html as _html  # noqa: PLC0415

    _debug('GET /i/<token>', token_prefix=token[:8] + '…' if token else 'empty')

    # Defensa cheap: el token es 64 hex chars. Cualquier otra forma
    # probablemente es scraping / vuln scanner — devolvemos 404 sin
    # pegarle al Core.
    if not token or len(token) != 64 or not all(c in '0123456789abcdef' for c in token.lower()):
        return HTMLResponse(
            _invitation_landing_html(
                ok=False,
                title='Enlace inválido',
                message='El link no tiene el formato esperado.',
                cta_label=None, cta_url=None,
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # Preview público del Core — sin auth.
    # PERF-001 — singleton compartido.
    from app.services.http_clients import get_core_bff_client  # noqa: PLC0415
    try:
        client = await get_core_bff_client()
        r = await client.get(_core_api_url(f'v1/invitations/{token}'))
    except httpx.RequestError as exc:
        _debug('GET /i/<token>', error='core_unreachable', detail=str(exc))
        return HTMLResponse(
            _invitation_landing_html(
                ok=False,
                title='Error temporal',
                message='No pudimos validar tu invitación. Probá de nuevo en un minuto.',
                cta_label=None, cta_url=None,
            ),
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    if r.status_code == 404:
        return HTMLResponse(
            _invitation_landing_html(
                ok=False,
                title='Invitación no encontrada',
                message=(
                    'El link es inválido o ya fue procesado. '
                    'Si esperabas una invitación, pedile al admin del tenant '
                    'que te re-envíe el email.'
                ),
                cta_label=None, cta_url=None,
            ),
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if r.status_code != 200:
        _debug('GET /i/<token>', error='core_unexpected_status',
               status=r.status_code)
        return HTMLResponse(
            _invitation_landing_html(
                ok=False,
                title='Error temporal',
                message='No pudimos validar tu invitación. Probá de nuevo en un minuto.',
                cta_label=None, cta_url=None,
            ),
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    preview = r.json()
    tenant_name = _html.escape(str(preview.get('tenant_name', 'CopilotoIA')))
    role = _html.escape(str(preview.get('role', 'miembro')))
    invitee_email = _html.escape(str(preview.get('email', '')))

    if preview.get('redeemed'):
        # Ya redeemed: no setear cookie, solo dejar entrar al admin panel
        # si tiene sesión, o login si no.
        return HTMLResponse(
            _invitation_landing_html(
                ok=True,
                title='Ya aceptaste esta invitación',
                message=(
                    f'Ya estás como miembro de <strong>{tenant_name}</strong>. '
                    f'Iniciá sesión con <strong>{invitee_email}</strong> para entrar.'
                ),
                cta_label='Iniciar sesión',
                cta_url='/admin/login',
            ),
        )

    # DiD-5 (audit #3) — antes de setear cookie, validar que el request
    # es navegación top-level (no `<img>`/`<iframe>`/`fetch()` cross-origin).
    # Sin esto, attacker.com puede embed `<img src="https://app/i/EVIL_TOKEN">`
    # que fuerza al browser a hacer GET de la víctima → setea su cookie
    # pending_invitation = EVIL_TOKEN → próximo login redime el EVIL invite.
    #
    # `Sec-Fetch-Dest=document` indica navegación top-level (URL bar, link
    # clickeado). Browsers viejos sin Sec-Fetch headers (raro hoy): no
    # rechazamos para no romper compat, pero loggeamos.
    sec_fetch_dest = request.headers.get('sec-fetch-dest')
    if sec_fetch_dest and sec_fetch_dest != 'document':
        _debug(
            'GET /i/<token>', step='non_document_request_rejected',
            sec_fetch_dest=sec_fetch_dest,
            hint='Probably <img>/<iframe>/fetch — possible CSRF prep',
        )
        # No mostramos HTML — un GET por `<img>` no espera HTML útil. 400
        # silencioso es lo más cercano a "no entender".
        return Response(status_code=status.HTTP_400_BAD_REQUEST)

    # Válida y pending — setear cookie + redirigir al login.
    settings = get_admin_settings()
    response = HTMLResponse(
        _invitation_landing_html(
            ok=True,
            title=f'Te invitaron a {tenant_name}',
            message=(
                f'Vas a entrar como <strong>{role}</strong> con la cuenta '
                f'<strong>{invitee_email}</strong>. '
                'Hacé click en "Continuar" para iniciar sesión.'
            ),
            cta_label='Continuar',
            cta_url='/admin/login',
        ),
    )
    response.set_cookie(
        PENDING_INVITATION_COOKIE,
        token,
        httponly=True,
        # `lax` (no `strict`) para que el cookie se mande en el redirect
        # cross-site del OAuth callback. Sin esto, el callback no lo ve
        # y el redeem nunca se dispara.
        samesite='lax',
        secure=settings.cookies_secure,
        max_age=PENDING_INVITATION_TTL_SECONDS,
        path='/',
    )
    return response


@router.get('/admin/login', include_in_schema=False)
async def admin_login(request: Request) -> RedirectResponse:
    _debug('GET /admin/login', has_cookie=request.cookies.get(SESSION_COOKIE) is not None)
    if await _active_session(request):
        _debug('GET /admin/login', skip='already_authenticated', redirect='/admin/')
        return RedirectResponse('/admin/', status_code=status.HTTP_303_SEE_OTHER)

    settings = get_admin_settings()
    if not settings.auth0_admin_client_id or not settings.auth0_audience:
        _debug(
            'GET /admin/login', error='auth0_not_configured',
            client_id_set=bool(settings.auth0_admin_client_id),
            audience_set=bool(settings.auth0_audience),
        )
        raise HTTPException(
            status_code=503,
            detail='Auth0 admin client ID or audience is not configured',
        )

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    callback_url = _callback_url(request)
    state_cookie = _pack_state({'state': state, 'nonce': nonce, 'created_at': int(time.time())})
    # M50 — `prompt=login` fuerza a Auth0 a re-autenticar SIEMPRE,
    # ignorando la cookie SSO. Sin esto, Auth0 te re-loguea silenciosamente
    # si tenés sesión activa en `auth0.com` (típico cuando hiciste logout
    # del BFF pero la cookie SSO de Auth0 sigue viva). Con `prompt=login`
    # SIEMPRE pide email/contraseña al user — comportamiento esperado de
    # "iniciar sesión".
    # Spec OIDC: https://openid.net/specs/openid-connect-core-1_0.html#AuthRequest
    # Opcional override: `?force=0` en la URL omite el prompt (útil para
    # casos donde sí queremos SSO silencioso — no usado hoy).
    force_relogin = request.query_params.get('force', '1') != '0'
    _debug(
        'GET /admin/login', step='redirect_to_auth0',
        callback_url=callback_url, state=state, auth0=settings.auth0_domain,
        prompt_login=force_relogin,
    )
    authorization_params: dict[str, str] = {
        'response_type': 'code',
        'client_id': settings.auth0_admin_client_id,
        'redirect_uri': callback_url,
        'scope': 'openid profile email offline_access',
        'audience': settings.auth0_audience,
        'state': state,
        'nonce': nonce,
    }
    if force_relogin:
        authorization_params['prompt'] = 'login'
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


def _callback_recover_redirect(reason: str) -> RedirectResponse:
    """M56 — UX fix: en lugar de mostrar `{"detail":"Invalid or expired
    OAuth state"}` como JSON crudo (que deja al user atascado), redirigir
    a `/admin/` con `?login_error=<reason>` para que el SPA muestre un
    banner explicativo + el botón "Iniciar sesión" para reintentar.

    Causas comunes:
      - state_missing:    user re-cargó el URL del callback (la cookie
                          tiene Max-Age=600 y se setea solo durante
                          /admin/login → si el user pega el URL a mano,
                          no hay cookie).
      - state_mismatch:   el user abrió varias pestañas y la cookie se
                          sobreescribió.
      - state_expired:    pasaron más de 10min entre /admin/login y el
                          callback (típico cuando el flow se interrumpe
                          y el user retoma horas después).
      - auth0_error:      Auth0 devolvió un error en el query (e.g.
                          access_denied porque el user canceló).
      - missing_params:   redirect a /callback sin code o state.

    El frontend lee `login_error` y muestra mensaje específico.
    """
    response = RedirectResponse(
        f'/admin/?login_error={reason}',
        status_code=status.HTTP_303_SEE_OTHER,
    )
    # Limpiar la state cookie zombie si existió → próximo login arranca limpio.
    response.delete_cookie(STATE_COOKIE, path='/', samesite='lax')
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
    _debug(
        'GET /callback', step='received',
        has_code=bool(code), has_state=bool(state),
        has_state_cookie=request.cookies.get(STATE_COOKIE) is not None,
        error=error,
    )
    if error:
        # M56 — Auth0 error (access_denied, consent_required, etc).
        # Redirige al landing con el error para mostrar mensaje al user.
        _debug('GET /callback', step='auth0_error', error=error, description=error_description)
        return _callback_recover_redirect(f'auth0_{error}')
    if not code or not state:
        _debug('GET /callback', step='missing_params', has_code=bool(code), has_state=bool(state))
        return _callback_recover_redirect('missing_params')

    state_payload = _unpack_state(request.cookies.get(STATE_COOKIE, ''))
    if not state_payload:
        _debug('GET /callback', step='state_cookie_invalid', reason='cookie_missing_or_unsigned')
        return _callback_recover_redirect('state_missing')
    if state_payload.get('state') != state:
        _debug(
            'GET /callback', step='state_mismatch',
            cookie_state=state_payload.get('state'), url_state=state,
        )
        return _callback_recover_redirect('state_mismatch')
    if state_payload.get('created_at', 0) < time.time() - 600:
        _debug(
            'GET /callback', step='state_expired',
            age_seconds=int(time.time() - state_payload.get('created_at', 0)),
        )
        return _callback_recover_redirect('state_expired')
    # P1-10 (audit 2026-05-27) — single-use enforcement. SET NX en el
    # store atomico (Redis o InMemory). Si retorna False, el state ya
    # fue consumido → rechazar. TTL = 600s (alineado con el window de
    # validación arriba). Sin esto, un attacker que captura el callback
    # URL antes que el browser legítimo puede crear una sesión paralela.
    from app.admin.oauth_state_store import get_oauth_state_store  # noqa: PLC0415
    state_store = get_oauth_state_store()
    if not await state_store.mark_consumed(state, ttl_seconds=600):
        _debug(
            'GET /callback', step='state_replay_rejected',
            hint='state already consumed — possible CSRF/replay attempt',
        )
        return _callback_recover_redirect('state_replay')
    _debug('GET /callback', step='state_validated')

    settings = get_admin_settings()
    callback_url = _callback_url(request)
    # PERF-001 — singleton compartido para Auth0 OIDC (token exchange + userinfo).
    from app.services.http_clients import get_auth0_client  # noqa: PLC0415
    client = await get_auth0_client()
    _debug('GET /callback', step='exchanging_code_for_token', auth0=settings.auth0_domain)
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
        _debug(
            'GET /callback', step='token_exchange_failed',
            status=token_response.status_code, body=token_response.text[:200],
        )
        raise HTTPException(
            status_code=401,
            detail='Could not exchange Auth0 authorization code',
        )
    tokens = token_response.json()
    _debug(
        'GET /callback', step='tokens_received',
        has_id_token=bool(tokens.get('id_token')),
        has_refresh=bool(tokens.get('refresh_token')),
    )

    # M63 — `/userinfo` es OPCIONAL. Auth0 lo rechaza con 401/403
    # cuando el access_token tiene `audience=<custom API>` (la nuestra),
    # porque /userinfo requiere un token con audience del propio Auth0
    # (`https://<tenant>.auth0.com/userinfo`). Como nuestro app pide
    # `audience=<copilotoia-core-api>` para llamar nuestro backend,
    # ese token NO sirve para /userinfo.
    #
    # El id_token validado (firma RS256 + JWKS + nonce A-001) YA
    # contiene sub, email, name, picture — todo lo que /userinfo
    # daría. /userinfo es legacy de OAuth 1.0; con OIDC moderno el
    # id_token es la fuente de truth. Hacemos best-effort: si
    # /userinfo responde 2xx, mergeamos sus claims (override id_token);
    # si falla, seguimos con id_token_claims solo.
    userinfo: dict[str, Any] = {}
    try:
        userinfo_response = await client.get(
            f'{_auth0_base_url()}/userinfo',
            headers={'authorization': f"Bearer {tokens['access_token']}"},
        )
        if userinfo_response.status_code < 400:
            userinfo = userinfo_response.json()
            _debug(
                'GET /callback', step='userinfo_received',
                sub=userinfo.get('sub'), email=userinfo.get('email'),
            )
        else:
            _debug(
                'GET /callback', step='userinfo_skipped_non_2xx',
                status=userinfo_response.status_code,
                body=userinfo_response.text[:200],
                hint=(
                    'access_token con audience custom no aplica para /userinfo. '
                    'Usaremos solo id_token_claims (que ya tiene sub/email/name).'
                ),
            )
    except httpx.HTTPError as exc:
        _debug(
            'GET /callback', step='userinfo_skipped_network_error',
            error=str(exc)[:200],
        )

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
        # A-001 — validamos que el `nonce` del id_token matchee el que
        # mandamos a /authorize (cookie firmada). Sin esto un id_token
        # capturado puede ser inyectado en otro flow del mismo cliente
        # (OIDC §3.1.3.7 step 11: "The Client SHOULD check the nonce
        # value for replay attacks").
        id_token_claims = await decode_auth0_id_token(
            id_token,
            audience=settings.auth0_admin_client_id,
            auth0_domain=settings.auth0_domain,
            auth0_issuer=settings.auth0_issuer,
            expected_nonce=state_payload.get('nonce'),
        )

    claims = {**id_token_claims, **userinfo}

    # M53 — detectar MFA por DOS vías (en orden de preferencia):
    #
    # (1) Custom claim namespaced del Auth0 Action:
    #       `https://copilotoia.local/claims/mfa_verified`  (boolean)
    #     Esto es lo que el Action de Auth0 de este tenant ya emite (vimos
    #     la key en el `auth_flow_claims_inspection` log: M51/M52). Es
    #     más robusto que `amr` porque el Action puede setearlo desde
    #     `event.authentication.methods` con cualquier semantic custom
    #     (factor adaptive, risk-based, etc).
    #
    # (2) Standard OIDC `amr=['mfa']` claim:
    #     Fallback estándar. Auth0 lo emite SOLO si el cliente OAuth pide
    #     `acr_values=mfa` o el Action lo setea explícito.
    #
    # Cualquiera de los dos cuenta como MFA verificado.
    amr = id_token_claims.get('amr') or claims.get('amr') or []
    if isinstance(amr, str):
        amr = [amr]
    mfa_via_amr = 'mfa' in amr
    mfa_via_custom_claim = bool(_namespaced_claim(claims, 'mfa_verified', False))
    mfa_verified = mfa_via_amr or mfa_via_custom_claim

    # M51 — DEBUG: imprimir todos los claims relacionados con autenticación
    # para diagnosticar por qué Auth0 no marca MFA. Sin esto, el handler
    # asume `amr=['mfa']` pero Auth0 puede:
    #   - emitir un claim distinto (acr=urn:mace:incommon:iap:silver)
    #   - poner amr=['mfa'] solo si el factor MFA está en el flow OAuth
    #     (no en el "challenge after login" de Auth0 Actions)
    #   - no incluir amr porque el cliente OAuth no lo pidió en `scope`
    # Las claves listadas acá NO son secrets — son metadata del flow OAuth.
    _AUTH_FLOW_CLAIMS = (
        'amr', 'acr', 'auth_time', 'nonce', 'iss', 'aud', 'sub',
        'iat', 'exp', 'azp', 'sid', 'at_hash',
    )
    id_token_flow_claims = {
        k: id_token_claims.get(k) for k in _AUTH_FLOW_CLAIMS
        if k in id_token_claims
    }
    userinfo_flow_claims = {
        k: userinfo.get(k) for k in _AUTH_FLOW_CLAIMS
        if k in userinfo
    }
    _debug(
        'GET /callback', step='auth_flow_claims_inspection',
        id_token_keys=sorted(id_token_claims.keys()),
        id_token_flow_claims=id_token_flow_claims,
        userinfo_flow_claims=userinfo_flow_claims,
        amr_resolved=amr,
        mfa_via_amr=mfa_via_amr,
        mfa_via_custom_claim=mfa_via_custom_claim,
        mfa_verified=mfa_verified,
    )

    session_id = secrets.token_urlsafe(32)
    profile_email = claims.get('email')
    profile_roles = _namespaced_claim(claims, 'roles', [])
    # B-002 — usar el `expires_in` REAL del token response (Auth0 default
    # 7200s = 2h). Sin esto el cookie sobrevivía al access_token y la SPA
    # se rompía silenciosa. Clamp [60, 24h] por seguridad.
    raw_expires_in = tokens.get('expires_in')
    try:
        token_ttl = int(raw_expires_in) if raw_expires_in is not None else SESSION_TTL_SECONDS_DEFAULT
    except (TypeError, ValueError):
        token_ttl = SESSION_TTL_SECONDS_DEFAULT
    session_ttl = max(60, min(token_ttl, 24 * 60 * 60))
    _debug(
        'GET /callback', step='creating_session',
        sid=session_id, email=profile_email, roles=profile_roles,
        mfa_verified=mfa_verified,
        session_ttl_seconds=session_ttl,
        raw_expires_in=raw_expires_in,
    )
    session_payload = {
        'access_token': tokens['access_token'],
        'id_token': id_token,
        # B-002 — guardar refresh_token para implementación futura del
        # silent-refresh flow. Hoy NO se usa; el SPA re-loguea cuando el
        # proxy detecta 401 upstream (ver `_purge_session_for_expired_
        # token` abajo).
        'refresh_token': tokens.get('refresh_token'),
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
    # P0-3 — session store async (InMemory o Redis según REDIS_URL).
    # SEC-024 (audit #3) — el state ya fue mark_consumed arriba. Si el
    # session.set falla acá (Redis flap), state queda consumido sin
    # sesión → user trapped hasta que su cookie pending_invitation
    # expire (~10min) y/o el state cookie (~10min). Catch + redirect
    # a recovery con motivo claro — el user reintenta el login y Auth0
    # emite nuevo state.
    from app.admin.session_store import get_session_store  # noqa: PLC0415
    try:
        await get_session_store().set(session_id, session_payload, session_ttl)
    except RuntimeError as exc:
        _debug(
            'GET /callback', step='session_store_failed_after_state_consumed',
            error=str(exc)[:200],
            hint='Redis flap mid-callback. State already consumed; user should re-login.',
        )
        return _callback_recover_redirect('session_store_down')
    # M65 — antes de armar el response, chequeamos si hay cookie
    # `pending_invitation` (el invitado vino de `/i/<token>`). Si está,
    # disparamos el redeem AHORA — el access_token recién emitido tiene
    # el email del invitado en el claim namespaced, así que el Core
    # puede validar email-match.
    pending_token = request.cookies.get(PENDING_INVITATION_COOKIE)
    redeem_status: str | None = None
    # SEC-020 (audit #2) — validar formato del token ANTES del path-
    # injection en el URL del Core. La cookie es HTTP-only + sólo la
    # setea `GET /i/{token}` (que ya valida hex 64), pero defense-in-
    # depth: doble-check acá previene un attacker que vuelva a setear
    # la cookie a `..%2Fadmin%2Fapi%2Fother` o similar.
    if pending_token and not (
        len(pending_token) == 64
        and all(c in '0123456789abcdef' for c in pending_token.lower())
    ):
        _debug(
            'GET /callback', step='pending_invitation_cookie_malformed',
            length=len(pending_token), prefix=pending_token[:8],
        )
        pending_token = None  # ignorar — no caer en path injection
    if pending_token:
        # PERF-001 — singleton compartido para BFF→Core.
        from app.services.http_clients import get_core_bff_client  # noqa: PLC0415
        try:
            bff_client = await get_core_bff_client()
            rr = await bff_client.post(
                _core_api_url(f'v1/invitations/{pending_token}/redeem'),
                headers={'Authorization': f'Bearer {tokens["access_token"]}'},
            )
            redeem_status = f'core_status_{rr.status_code}'
            _debug(
                'GET /callback', step='invitation_redeem',
                status=rr.status_code,
                # Body puede contener tenant_name pero no es secret.
                body_preview=rr.text[:200] if rr.text else None,
            )
        except httpx.RequestError as exc:
            redeem_status = 'request_error'
            _debug(
                'GET /callback', step='invitation_redeem_error',
                error=str(exc),
            )
        # Cualquier fallo del redeem NO debe tumbar el login. El user
        # entra al panel igual (ya tiene membership desde
        # `add_tenant_member`); el redeem es solo audit + UX.

    response = RedirectResponse('/admin/')
    response.delete_cookie(STATE_COOKIE)
    if pending_token:
        response.delete_cookie(PENDING_INVITATION_COOKIE, path='/')
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
        max_age=session_ttl,
    )
    _debug(
        'GET /callback', step='session_cookie_set',
        sid=session_id, ttl_seconds=session_ttl,
        secure=settings.cookies_secure, samesite='strict',
        redirect='/admin/',
        pending_invitation_redeem=redeem_status,
    )
    return response


@router.post('/admin/logout', include_in_schema=False)
async def admin_logout(request: Request) -> RedirectResponse:
    _debug(
        'POST /admin/logout', step='received',
        has_cookie=request.cookies.get(SESSION_COOKIE) is not None,
    )
    # CSRF gate: el form POST debe venir del mismo origin. Sin esto, un
    # sitio externo podría disparar el logout del usuario con un form
    # cross-origin (aunque la cookie SameSite=strict ya lo previene, esto
    # es defensa-en-profundidad y evita falsos positivos por cookies de
    # navegadores viejos).
    if not _csrf_origin_ok(request):
        _debug(
            'POST /admin/logout', step='csrf_rejected',
            origin=request.headers.get('origin'),
            sec_fetch_site=request.headers.get('sec-fetch-site'),
        )
        raise HTTPException(status_code=403, detail='csrf_check_failed')
    settings = get_admin_settings()
    session_id = request.cookies.get(SESSION_COOKIE)
    # M49 — leer id_token ANTES de purgar la sesión para pasarlo como
    # `id_token_hint` a Auth0 OIDC logout. Sin hint, Auth0 puede
    # mostrar una pantalla de confirmación al user ("¿salir?") en lugar
    # de terminar la sesión silenciosa.
    id_token_hint: str | None = None
    if session_id:
        from app.admin.session_store import get_session_store  # noqa: PLC0415
        store = get_session_store()
        cached_session = await store.get(session_id)
        if cached_session:
            id_token_hint = cached_session.get('id_token')
        existed = await store.delete(session_id)
        _debug(
            'POST /admin/logout', step='session_purged',
            sid=session_id, found_in_store=existed,
            had_id_token=id_token_hint is not None,
        )
    return_to = _logout_return_to(request)
    # M49 — Auth0 deprecó `/v2/logout` (devuelve 404 desde 2024). El
    # endpoint OIDC estándar es `/oidc/logout` con parámetros distintos:
    #   - `client_id`               (igual que antes)
    #   - `post_logout_redirect_uri` (en lugar de `returnTo`)
    #   - `id_token_hint`           (opcional pero evita pantalla de
    #                                confirmación + termina SSO silencioso)
    # `post_logout_redirect_uri` debe estar registrado en
    # Application Settings → "Allowed Logout URLs" del dashboard Auth0.
    if settings.auth0_domain and settings.auth0_admin_client_id:
        oidc_params: dict[str, str] = {
            'client_id': settings.auth0_admin_client_id,
            'post_logout_redirect_uri': return_to,
        }
        if id_token_hint:
            oidc_params['id_token_hint'] = id_token_hint
        logout_url = f'{_auth0_base_url()}/oidc/logout?{urlencode(oidc_params)}'
    else:
        logout_url = '/admin/'
    _debug(
        'POST /admin/logout', step='redirect_decided',
        redirect_to=logout_url[:100] + ('…' if len(logout_url) > 100 else ''),
        post_logout_redirect_uri=return_to,
        with_id_token_hint=bool(id_token_hint),
        auth0_oidc_logout=settings.auth0_domain is not None,
        client_header_sec_fetch=request.headers.get('sec-fetch-mode'),
        client_header_x_req=request.headers.get('x-requested-with'),
        client_header_origin=request.headers.get('origin'),
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
    _debug(
        'GET /admin/api/session', step='received',
        has_cookie=request.cookies.get(SESSION_COOKIE) is not None,
    )
    session = await _active_session(request)
    if not session:
        # M46: 401 explícito con reason + delete-cookie. Antes era un
        # `Response(status_code=401)` plano y el frontend no podía
        # distinguir "nunca tuvo sesión" de "sesión expiró por restart".
        _debug('GET /admin/api/session', step='returning_401', store_size=len(_sessions))
        return _unauthorized_session_response(request)
    _debug(
        'GET /admin/api/session', step='returning_200',
        email=session['profile'].get('email'),
        roles=session['profile'].get('roles'),
    )
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


# M42 — `/admin/api/mfa-status` se borró en el audit pass. Su único caller
# (`admin-panel/src/components/domain/MfaRequiredBlocker.jsx`) fue eliminado
# durante la purga del branch core; el flujo MFA ahora vive en
# `MfaAutoLogout` (cierre forzado de sesión por el BFF + redirect a login).
# El endpoint dead exponía `is_privileged` + `privileged_roles` sin uso
# real — superficie de info disclosure sin justificación.


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
    session = await _active_session_id(websocket.cookies.get(SESSION_COOKIE))
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
    _debug(
        f'{request.method} /admin/api/core/{path}', step='proxy_received',
        has_cookie=request.cookies.get(SESSION_COOKIE) is not None,
    )
    session = await _active_session(request)
    if not session:
        # M46: mismo patrón que /admin/api/session — body explicativo
        # con `reason` + delete-cookie zombie. El SPA puede leer el JSON
        # para mostrar "tu sesión expiró" en lugar de un 401 mudo.
        _debug(f'{request.method} /admin/api/core/{path}', step='proxy_401_no_session')
        return _unauthorized_session_response(request)
    _debug(
        f'{request.method} /admin/api/core/{path}', step='proxy_authorized',
        email=session['profile'].get('email'),
    )

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
    # PERF-001 — singleton compartido para el proxy BFF→Core (caller más
    # caliente: cada request del SPA pasa por acá). Timeout subido a 20s
    # via override del call.
    from app.services.http_clients import get_core_bff_client  # noqa: PLC0415
    try:
        proxy_client = await get_core_bff_client()
        upstream_response = await proxy_client.request(
            request.method,
            target_url,
            content=body or None,
            headers=headers,
            timeout=20.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                'Admin proxy could not reach core API at '
                f'{get_admin_settings().admin_core_api_base_url}'
            ),
        ) from exc

    # B-002 — si el Core responde 401 con detail típico de token expirado/
    # revocado, purgamos la sesión local + delete-cookie ANTES de
    # devolverle el 401 al SPA. Sin esto, el SPA quedaba con cookie
    # válida pero todos los proxy requests fallando hasta que el user
    # cerrara browser. Ahora el SPA recibe el body con
    # `reason: 'token_expired'` y puede redirigir a /admin/login.
    if upstream_response.status_code == 401:
        try:
            upstream_body = upstream_response.json() if upstream_response.content else {}
            detail = (upstream_body.get('detail') or '').lower() if isinstance(upstream_body, dict) else ''
        except (ValueError, TypeError):
            detail = ''
        token_expired_markers = (
            'expired token', 'session has been revoked',
            'invalid token', 'token missing required claim',
            'id_token nonce mismatch',
        )
        if any(marker in detail for marker in token_expired_markers):
            cookie_session_id = request.cookies.get(SESSION_COOKIE)
            if cookie_session_id:
                from app.admin.session_store import get_session_store  # noqa: PLC0415
                await get_session_store().delete(cookie_session_id)
            _debug(
                f'{request.method} /admin/api/core/{path}',
                step='proxy_token_expired_purged',
                upstream_detail=detail[:80],
            )
            cleared = Response(
                content=json.dumps({
                    'detail': 'session_expired',
                    'reason': 'token_expired',
                    'message': 'La sesión expiró — vuelve a iniciar sesión.',
                }),
                status_code=401,
                media_type='application/json',
            )
            cleared.delete_cookie(
                SESSION_COOKIE, path='/', samesite='strict',
            )
            return cleared

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
