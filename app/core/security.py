import hmac
from datetime import UTC, datetime
from time import monotonic
from uuid import UUID

import httpx
import structlog
from fastapi import Header, HTTPException, Request, status
from jose import JWTError, jwt

from app.core.config import get_settings
from app.core.signed_cookies import unpack_signed_payload

_security_log = structlog.get_logger()


def _service_token_match(token: str, settings) -> bool:
    """AUDIT-48 (2026-05-18): dual-secret service_token comparator.

    Accept either `service_token` (current) or `service_token_next` (incoming).
    Uses `hmac.compare_digest` for constant-time comparison so we don't leak
    which of the two matched via timing. When `service_token_next` is set
    and matches, log a structured event so operators can verify rotation
    progress before promoting it.
    """
    if not token:
        return False
    current = getattr(settings, 'service_token', None) or ''
    nxt = getattr(settings, 'service_token_next', None) or ''
    matched_current = current and hmac.compare_digest(token, current)
    matched_next = nxt and hmac.compare_digest(token, nxt)
    if matched_next and not matched_current:
        # During rotation, knowing that the new secret is actually used is
        # critical to decide when to promote. Do NOT log either secret.
        _security_log.info(
            'service_token.rotation_next_in_use',
            hint='client autenticó con SERVICE_TOKEN_NEXT — listo para promoverlo a SERVICE_TOKEN',
        )
    return bool(matched_current or matched_next)

# BUG-008 — `POST /v1/me/support-mode/{tenant_id}` emite este cookie HTTP-only
# firmado para activar support_mode OPT-IN TEMPORAL scoped a un tenant
# específico. `authenticate_request` lo lee al validar la request y, si
# matchea el `X-Tenant-Id` y el `sub` del JWT y no expiró, OR-ea con
# `support_mode` del JWT. Esto reemplaza el workaround de setear
# `app_metadata.support_mode=true` permanente en Auth0 (que daba acceso
# cross-tenant siempre, sin opt-in).
SUPPORT_MODE_COOKIE_NAME = 'copilotoia_support_mode'

_jwks_cache: dict[str, tuple[float, dict]] = {}
# TASK-0077: shared role ranking used by both JWT-session checks
# (``require_min_role``) and per-tenant DB checks (``ensure_tenant_role``).  The
# ``platform_owner`` rank tops the ladder so that the same helper can express
# "this endpoint requires platform_owner" without a separate code path.
# BUG-133: `support` no es un rol — es un modo (`support_mode` flag/cookie
# scoped a un tenant). Antes lo poníamos en el ladder con nivel 50 (entre
# owner y platform_owner), lo que significaba que un JWT con `support` en
# `roles[]` (misconfig de Auth0 o claim heredado) pasaba `require_min_role`
# por encima de admin/owner SIN haber activado support_mode. La activación
# de support_mode es por endpoint dedicado (cookie firmada + audit), no por
# rol. Removemos `support` del ladder; cualquier elevación cross-tenant pasa
# por `support_mode` (verificado en `authenticate_request`).
# M13 — fuente única de verdad del ladder de roles. Antes vivía duplicada
# en `app/admin/routes.py` con la misma rationale; ahora el BFF re-importa
# desde aquí (`from app.core.security import ROLE_LEVELS, PRIVILEGED_ROLES`).
# Mantener `_ROLE_LEVELS` / `_PRIVILEGED_ROLES` como aliases internos para
# no romper call sites históricos dentro de este módulo.
ROLE_LEVELS = {
    'viewer': 5,
    'agent': 10,
    'manager': 20,
    'admin': 30,
    'owner': 40,
    'platform_owner': 60,
}
PRIVILEGED_ROLES = frozenset({'admin', 'owner', 'platform_owner'})
_ROLE_LEVELS = ROLE_LEVELS  # backwards compat dentro del módulo
_PRIVILEGED_ROLES = PRIVILEGED_ROLES


def clear_jwks_cache() -> None:
    _jwks_cache.clear()


def _claim(payload: dict, namespace: str, name: str):
    normalized_namespace = namespace.rstrip('/')
    return payload.get(
        f'{normalized_namespace}/{name}', payload.get(f'{namespace}{name}', payload.get(name))
    )


def _coerce_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {'1', 'true', 'yes', 'on'}
    return bool(value)


def _extract_mfa_verified(payload: dict, namespace: str = '') -> bool:
    """Return True if the token includes evidence of completed MFA.

    Auth0 sets ``amr=['mfa']`` in the id_token when MFA was used, but access
    tokens never carry ``amr``.  The post-login Action forwards the evidence
    into the access token as the namespaced ``mfa_verified`` custom claim, so
    that claim is the authoritative source for API requests.
    """
    if _coerce_bool(_claim(payload, namespace, 'mfa_verified')):
        return True
    amr = payload.get('amr') or []
    if isinstance(amr, str):
        amr = [amr]
    return 'mfa' in amr


def _normalize_auth0_domain(domain: str) -> str:
    return domain.removeprefix('https://').removeprefix('http://').rstrip('/')


def _normalize_issuer(issuer: str) -> str:
    return issuer.rstrip('/') + '/'


def _auth0_issuer(domain: str, configured_issuer: str | None = None) -> str:
    if configured_issuer:
        return _normalize_issuer(configured_issuer)
    return f'https://{_normalize_auth0_domain(domain)}/'


async def _fetch_auth0_jwks(domain: str, ttl_seconds: int) -> dict:
    issuer = _auth0_issuer(domain)
    cached = _jwks_cache.get(issuer)
    now = monotonic()
    if cached and cached[0] > now:
        return cached[1]

    url = f'{issuer}.well-known/jwks.json'
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.get(url)
        response.raise_for_status()
    jwks = response.json()
    _jwks_cache[issuer] = (now + ttl_seconds, jwks)
    return jwks


def _select_jwk(jwks: dict, kid: str | None) -> dict:
    keys = jwks.get('keys', [])
    if not kid and len(keys) == 1:
        return keys[0]
    for key in keys:
        if key.get('kid') == kid:
            return key
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Unknown token key id')


async def decode_auth0_id_token(
    token: str,
    *,
    audience: str,
    auth0_domain: str,
    auth0_issuer: str | None = None,
    jwks_cache_ttl_seconds: int = 300,
) -> dict:
    """Valida un Auth0 id_token con su firma (RS256 + JWKS).

    Usado por el BFF admin (`app.admin.routes`) para extraer claims del
    id_token tras el OAuth callback. SIN esto, decodear el id_token con
    base64 raw permite que un atacante con un access_token válido forje un
    id_token con `amr=['mfa']` y bypassee el MFA enforcement del BFF.

    Args:
        token: JWT id_token recibido del `/oauth/token` endpoint.
        audience: el client_id del admin app (ese es el aud del id_token).
        auth0_domain: dominio Auth0 sin scheme.
        auth0_issuer: override opcional del issuer.
        jwks_cache_ttl_seconds: TTL del cache JWKS.

    Returns:
        Dict con los claims del id_token validado.

    Raises:
        HTTPException 401 si el token es inválido / firma rota / aud mismatch.
    """
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid id_token'
        ) from exc
    if header.get('alg') != 'RS256':
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid id_token algorithm'
        )

    jwks = await _fetch_auth0_jwks(auth0_domain, jwks_cache_ttl_seconds)
    key = _select_jwk(jwks, header.get('kid'))
    try:
        return jwt.decode(
            token,
            key,
            algorithms=['RS256'],
            audience=audience,
            issuer=_auth0_issuer(auth0_domain, auth0_issuer),
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid id_token'
        ) from exc


async def _decode_auth0_token(token: str, settings) -> dict:
    if not settings.auth0_domain or not settings.auth0_audience:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Auth0 is not configured'
        )
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token'
        ) from exc
    if header.get('alg') != 'RS256':
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token algorithm'
        )

    jwks = await _fetch_auth0_jwks(settings.auth0_domain, settings.auth0_jwks_cache_ttl_seconds)
    key = _select_jwk(jwks, header.get('kid'))
    try:
        return jwt.decode(
            token,
            key,
            algorithms=['RS256'],
            audience=settings.auth0_audience,
            issuer=_auth0_issuer(settings.auth0_domain, settings.auth0_issuer),
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token'
        ) from exc


def _decode_local_token(token: str, settings) -> dict:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=['HS256'],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token'
        ) from exc


async def _decode_user_token(token: str, settings) -> dict:
    if settings.auth0_domain:
        return await _decode_auth0_token(token, settings)
    return _decode_local_token(token, settings)


async def authenticate_request(
    request: Request,
    authorization: str | None = Header(default=None),
    x_tenant_id: UUID | None = Header(default=None, alias='X-Tenant-Id'),
) -> None:
    settings = get_settings()
    request.state.tenant_id = None
    request.state.requested_tenant_id = x_tenant_id
    request.state.actor_type = 'anonymous'
    request.state.actor_id = None
    request.state.roles = []
    request.state.support_mode = False
    # BUG-008 — `support_mode_source` distingue cómo se activó: 'jwt' (claim
    # permanente), 'cookie' (opt-in temporal vía /v1/me/support-mode/{tid}),
    # 'service' (service token interno con support_mode auto-true), o None.
    # Permite filtrar audit logs y detectar abuso del modo permanente.
    request.state.support_mode_source = None
    request.state.mfa_verified = False
    request.state.email = None
    request.state.name = None
    # UI-016.7-FU-SESSIONS: session id derivable desde el JWT, usado por
    # `record_auth_session(...)` para upsertear `app.auth_sessions`. Si Auth0
    # emite `jti` (default en la mayoría de tenants), lo usamos directo. Si no,
    # los handlers caen a un fallback determinístico (`sub + iat` hash) — ver
    # `_session_id_from_request` en `app/api/v1/routes.py`.
    request.state.session_jti = None
    request.state.token_iat = None

    if not authorization:
        if x_tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail='X-Tenant-Id requires Authorization',
            )
        return
    scheme, _, token = authorization.partition(' ')
    if scheme.lower() != 'bearer' or not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid Authorization header'
        )

    # AUDIT-48 (security quick win #3, 2026-05-18): dual-secret service_token
    # para rotación sin downtime. Aceptamos `settings.service_token` (current)
    # O `settings.service_token_next` (incoming) cuando esté seteado.
    # Comparación constante-tiempo (hmac.compare_digest) para evitar timing
    # oracle sobre cuál de los dos matcheó.
    if _service_token_match(token, settings):
        request.state.actor_type = 'service'
        request.state.support_mode = True
        request.state.support_mode_source = 'service'
        return

    payload = await _decode_user_token(token, settings)

    exp = payload.get('exp')
    if exp and datetime.fromtimestamp(exp, UTC) < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Expired token')

    namespace = settings.auth0_claims_namespace
    token_tenant_claim = _claim(payload, namespace, 'tenant_id')
    try:
        token_tenant_id = UUID(token_tenant_claim) if token_tenant_claim else None
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token tenant_id'
        ) from exc
    support_mode = _coerce_bool(_claim(payload, namespace, 'support_mode'))
    roles = _claim(payload, namespace, 'roles') or []
    if isinstance(roles, str):
        roles = [roles]

    # BUG-008 — cookie scoped puede bumpear support_mode SOLO si matchea
    # `X-Tenant-Id` Y el `sub` del JWT. El cookie no escala roles globales
    # (esos siguen viniendo del JWT firmado por Auth0); solo permite que el
    # rol global `platform_owner` aplique dentro de un tenant específico
    # durante el TTL del cookie. Una request sin `X-Tenant-Id` ignora el
    # cookie — el opt-in es per-tenant por diseño (anti-blast-radius).
    support_mode_source = 'jwt' if support_mode else None
    if not support_mode and x_tenant_id:
        cookie_value = request.cookies.get(SUPPORT_MODE_COOKIE_NAME)
        if cookie_value:
            cookie_payload = unpack_signed_payload(settings.jwt_secret, cookie_value)
            if cookie_payload:
                cookie_tid = cookie_payload.get('tid')
                cookie_sub = cookie_payload.get('sub')
                cookie_exp = cookie_payload.get('exp')
                now_ts = int(datetime.now(UTC).timestamp())
                if (
                    isinstance(cookie_tid, str)
                    and cookie_tid == str(x_tenant_id)
                    and isinstance(cookie_sub, str)
                    and cookie_sub == payload.get('sub')
                    and isinstance(cookie_exp, int)
                    and cookie_exp > now_ts
                ):
                    support_mode = True
                    support_mode_source = 'cookie'

    if token_tenant_id and x_tenant_id and x_tenant_id != token_tenant_id and not support_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='X-Tenant-Id does not match token tenant_id',
        )
    # A5 hardening: caller SIN token_tenant_id (típicamente platform_owner)
    # NO puede acceder a endpoints tenant-scoped vía X-Tenant-Id sin haber
    # activado support_mode. Sin esto, un platform_owner con MFA verified
    # pero sin support_mode podía mandar X-Tenant-Id=acme y obtener acceso
    # silencioso al tenant, saltándose el audit que support_mode genera.
    if x_tenant_id and not token_tenant_id and not support_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Cross-tenant access requires support_mode',
        )
    request.state.actor_type = 'user'
    request.state.actor_id = payload.get('sub')
    request.state.roles = roles
    request.state.support_mode = support_mode
    # BUG-008 — debug-friendly: el resto de la app puede distinguir
    # support_mode permanente (JWT) de support_mode temporal (cookie) sin
    # tener que re-parsear el cookie. Útil para audit (sabremos si la
    # acción ocurrió bajo opt-in temporal o bajo el modo legacy).
    request.state.support_mode_source = support_mode_source
    request.state.mfa_verified = _extract_mfa_verified(payload, namespace)
    request.state.email = payload.get('email')
    request.state.name = payload.get('name') or payload.get('nickname')
    request.state.tenant_id = x_tenant_id if support_mode and x_tenant_id else token_tenant_id
    # UI-016.7-FU-SESSIONS: capturamos los claims que identifican esta sesión
    # del JWT. `jti` es el identificador canónico; `iat` se usa como fallback
    # cuando jti no está presente (algunos tenants Auth0 pueden no emitirlo).
    request.state.session_jti = payload.get('jti')
    request.state.token_iat = payload.get('iat')

    # BUG-199 (codex HIGH) — enforce session revocation.
    #
    # UI-016.7-FU-SESSIONS introdujo `app.auth_sessions` y el endpoint
    # `DELETE /v1/me/sessions/{sid}` que escribe `revoked_at`. Pero
    # `authenticate_request` NUNCA consultaba ese campo: validaba el JWT
    # firmado, las roles y los claims de tenant, y retornaba autorizado.
    # Resultado: una sesión "revocada" desde la UI seguía aceptando requests
    # hasta que expiraba el JWT (típicamente 8-24h). El user creía haber
    # cerrado la sesión comprometida y la API seguía pasándola.
    #
    # Fix: si el JWT trae un identificador de sesión y la conn pool del Core
    # está disponible, consultamos `auth_sessions.revoked_at` y rechazamos
    # 401 si está set. Solo aplica cuando la sesión fue previamente
    # registrada (vía hit a `/me/sessions`); para users que nunca abrieron
    # el listado, no hay row y el check pasa (la revocación per-jti requiere
    # que el row exista, lo que `revoke_my_session` garantiza porque la UI
    # lista antes de revocar).
    #
    # Fail-open en caso de pool down / DB transient — la availability de la
    # API es más importante que cerrar una revocación segundos antes; el
    # próximo request retry hará el check de nuevo.
    session_id = _derive_session_id(payload)
    if session_id:
        await _enforce_session_not_revoked(session_id)


def derive_session_id(*, jti: str | None, sub: str | None, iat: int | None) -> str | None:
    """M43 — fuente única de verdad para derivar un `session_id` estable.

    Antes esto vivía duplicado en `_derive_session_id(payload)` (acá, leído
    desde el JWT durante `authenticate_request`) y `_session_id_from_request
    (request)` (en `_helpers/me_utils.py`, leído desde `request.state`).
    Cualquier divergencia rompe BUG-199 (revoke check): el row insertado por
    el handler nunca matchearía el row consultado por `authenticate_request`.

    Contrato:
    - Si `jti` está presente → usarlo (siempre lo emite Auth0).
    - Si no, hash determinístico `sha256(sub|iat)[:32]` con prefijo
      `iat-` para distinguir fallback de jti real.
    - Si faltan `sub` o `iat` también → `None` (sin tracking de revoke).
    """
    if jti:
        return str(jti)
    if not sub or iat is None:
        return None
    import hashlib  # noqa: PLC0415

    digest = hashlib.sha256(f'{sub}|{iat}'.encode()).hexdigest()
    return f'iat-{digest[:32]}'


def _derive_session_id(payload: dict) -> str | None:
    """Compat wrapper sobre `derive_session_id` para call sites internos
    que ya tenían el `payload` del JWT en mano."""
    return derive_session_id(
        jti=payload.get('jti'),
        sub=payload.get('sub'),
        iat=payload.get('iat'),
    )


async def _enforce_session_not_revoked(session_id: str) -> None:
    """BUG-199: 401 si `auth_sessions.revoked_at IS NOT NULL` para este sid.

    Import lazy de `app.db.pool` para evitar ciclo (la pool importa security
    indirectamente vía sus consumidores).
    """
    try:
        from app.db.pool import db  # noqa: PLC0415

        if not db.pool:
            return
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow(
                'select revoked_at from app.auth_sessions where id = $1',
                session_id,
            )
    except HTTPException:
        raise
    except Exception:  # noqa: BLE001 — fail-open por availability
        return
    if row and row['revoked_at'] is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Session has been revoked',
        )


def _has_role(roles: list[str], minimum_role: str) -> bool:
    required = _ROLE_LEVELS[minimum_role]
    return any(_ROLE_LEVELS.get(role, 0) >= required for role in roles)


async def require_platform_owner(request: Request) -> None:
    actor_type = getattr(request.state, 'actor_type', 'anonymous')
    if actor_type == 'anonymous':
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Authentication required')
    if actor_type != 'user':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Platform user required')
    if getattr(request.state, 'tenant_id', None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='Platform administration requires an unscoped token',
        )
    if 'platform_owner' not in getattr(request.state, 'roles', []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail='platform_owner role is required'
        )
    # M40 — gap detectado en el delta audit post-fix C9. Las policies de
    # RLS sobre `app.tenants` (C9) exigen `app.support_mode()=true` o
    # `app.current_tenant_id()=id`. El fleet (sin tenant scope) caía a
    # las dos cero → SELECT vacío. Activar `support_mode` aquí garantiza
    # que CUALQUIER handler protegido por `require_platform_owner`
    # opera con la cookie virtual (audit logs registran el `actor_id`
    # del platform_owner correctamente; no es escalación silenciosa).
    request.state.support_mode = True


async def require_service(request: Request) -> None:
    if getattr(request.state, 'actor_type', None) != 'service':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Service token required')


# M55 — ACL flexible para endpoints "de gestión per-tenant" (members,
# settings, etc) que deben ser accesibles tanto por:
#   - platform_owner (cualquier tenant)
#   - owner/admin del tenant del path (solo su propio tenant)
#
# Necesario porque el reporte del user mostró: el flow `Iniciar sesión
# como otro usuario que es owner de SU tenant` → el SPA intentaba
# `GET /v1/tenants/{tid}/members` → 403 porque ese endpoint estaba
# en platform_admin_router con require_platform_owner hardcoded. Un
# owner regular NO podía gestionar SU PROPIO equipo.
#
# Uso:
#   @tenant_management_router.get('/tenants/{tenant_id}/members')
#   async def list_members(
#       tenant_id: UUID,
#       _acl: None = Depends(require_tenant_management),
#       conn: asyncpg.Connection = Depends(get_db),
#   ): ...
async def require_tenant_management(
    tenant_id: UUID, request: Request,
) -> None:
    """ACL: platform_owner OR owner/admin del tenant_id del path.

    Side-effect: setea `request.state.support_mode=True` (platform_owner)
    O `request.state.tenant_id=<tid>` (owner/admin) para que `get_db`
    abra la conn con las flags RLS correctas. SIN esto, las queries
    contra `app.tenants` (RLS-protected) devolverían vacío.

    `tenant_id` se inyecta automáticamente desde el path param que el
    handler declara (FastAPI matchea por nombre).
    """
    actor_id = getattr(request.state, 'actor_id', None)
    if not actor_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Authentication required',
        )
    roles = list(getattr(request.state, 'roles', None) or [])
    if 'platform_owner' in roles:
        # Cross-tenant: support_mode bypassa RLS de app.tenants.
        request.state.support_mode = True
        return
    # Owner/admin de ESTE tenant. Abrir conn temporal (no la del get_db
    # que aún no corrió) para chequear membresía.
    from app.db.pool import db  # noqa: PLC0415
    if not db.pool:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail='Database pool not initialized',
        )
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow(
            '''
            select utr.role from app.user_tenant_roles utr
            join app.users u on u.id = utr.user_id
            where u.auth_subject = $1 and utr.tenant_id = $2
            ''',
            actor_id, tenant_id,
        )
    if not row or row['role'] not in ('owner', 'admin'):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='must_be_platform_owner_or_tenant_owner_admin',
        )
    # Scope la próxima conn al tenant_id del path → RLS-safe + sin
    # darle privilegios cross-tenant.
    request.state.tenant_id = tenant_id


def require_min_role(minimum_role: str, *, allow_service: bool = False):
    async def dependency(request: Request) -> None:
        actor_type = getattr(request.state, 'actor_type', 'anonymous')
        if actor_type == 'anonymous':
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail='Authentication required'
            )
        # TASK-0077: propagate the router's required role so that
        # ``ensure_tenant_access`` (and ``ensure_tenant_role``) can apply the
        # same threshold to the per-tenant DB membership row.  Without this the
        # router-level JWT check and the tenant DB check disagree on what
        # "admin" means and allow JWT-admin + DB-viewer combinations through.
        request.state.required_tenant_role = minimum_role
        if actor_type == 'service':
            if allow_service:
                return
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='User role required')
        if _has_role(getattr(request.state, 'roles', []), minimum_role):
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f'{minimum_role} role or higher is required',
        )

    return dependency


def has_jwt_role(roles: list[str], minimum_role: str) -> bool:
    """Public wrapper around the internal role-ranking helper.

    ``ensure_tenant_role`` in ``app.api.v1.routes`` uses this to apply the JWT
    half of the double-check (JWT AND DB) without duplicating the role table.
    """
    return _has_role(roles, minimum_role)


def _session_has_privileged_role(roles: list[str]) -> bool:
    return any(role in _PRIVILEGED_ROLES for role in roles)


async def require_mfa_for_privileged(request: Request) -> None:
    """Enforce MFA for requests authenticated with privileged roles.

    Service tokens are exempt (they never go through MFA flows).
    Unprivileged roles (agent, manager) are also exempt.
    Privileged roles (admin, owner, platform_owner) must have mfa_verified=True
    when Auth0 is active; in local-HS256 mode the check is skipped.  The check
    is also skipped when ``mfa_enforcement_enabled`` is False (Auth0 plans
    without the MFA add-on cannot serve the challenge flow).
    """
    actor_type = getattr(request.state, 'actor_type', 'anonymous')
    if actor_type == 'anonymous':
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Authentication required')
    if actor_type == 'service':
        return
    roles = getattr(request.state, 'roles', [])
    if not _session_has_privileged_role(roles):
        return
    settings = get_settings()
    if not settings.mfa_enforcement_enabled:
        return
    if not settings.auth0_domain:
        return
    if not getattr(request.state, 'mfa_verified', False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='MFA is required for privileged roles (admin/owner/platform_owner)',
        )
