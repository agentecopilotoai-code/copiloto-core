from datetime import UTC, datetime
from time import monotonic
from uuid import UUID

import httpx
from fastapi import Header, HTTPException, Request, status
from jose import JWTError, jwt

from app.core.config import get_settings

_jwks_cache: dict[str, tuple[float, dict]] = {}
_ROLE_LEVELS = {'agent': 10, 'manager': 20, 'admin': 30, 'owner': 40, 'support': 50}


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
    request.state.tenant_id = x_tenant_id
    request.state.actor_type = 'anonymous'
    request.state.actor_id = None
    request.state.roles = []
    request.state.support_mode = False

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

    if token == settings.service_token:
        request.state.actor_type = 'service'
        request.state.support_mode = True
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

    if token_tenant_id and x_tenant_id and x_tenant_id != token_tenant_id and not support_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='X-Tenant-Id does not match token tenant_id',
        )
    if x_tenant_id and not token_tenant_id and not support_mode:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='X-Tenant-Id requires a tenant-scoped token',
        )

    request.state.actor_type = 'user'
    request.state.actor_id = payload.get('sub')
    request.state.roles = roles
    request.state.support_mode = support_mode
    request.state.tenant_id = x_tenant_id if support_mode and x_tenant_id else token_tenant_id


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
    if 'owner' not in getattr(request.state, 'roles', []):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='owner role is required')


async def require_service(request: Request) -> None:
    if getattr(request.state, 'actor_type', None) != 'service':
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Service token required')


def require_min_role(minimum_role: str, *, allow_service: bool = False):
    async def dependency(request: Request) -> None:
        actor_type = getattr(request.state, 'actor_type', 'anonymous')
        if actor_type == 'anonymous':
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail='Authentication required'
            )
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
