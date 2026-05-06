from datetime import UTC, datetime
from uuid import UUID

from fastapi import Header, HTTPException, Request, status
from jose import JWTError, jwt

from app.core.config import get_settings


async def authenticate_request(
    request: Request,
    authorization: str | None = Header(default=None),
    x_tenant_id: UUID | None = Header(default=None, alias='X-Tenant-Id'),
) -> None:
    settings = get_settings()
    request.state.tenant_id = x_tenant_id
    request.state.actor_type = 'anonymous'
    request.state.actor_id = None
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid Authorization header')

    if token == settings.service_token:
        request.state.actor_type = 'service'
        request.state.support_mode = True
        return

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=['HS256'],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token') from exc

    exp = payload.get('exp')
    if exp and datetime.fromtimestamp(exp, UTC) < datetime.now(UTC):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Expired token')

    try:
        token_tenant_id = UUID(payload['tenant_id']) if payload.get('tenant_id') else None
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid token tenant_id'
        ) from exc
    support_mode = bool(payload.get('support_mode', False))

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
    request.state.support_mode = support_mode
    request.state.tenant_id = x_tenant_id if support_mode and x_tenant_id else token_tenant_id
