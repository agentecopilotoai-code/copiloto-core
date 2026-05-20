"""Instagram OAuth flow endpoints — TASK-INFLU-014."""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.core.security import authenticate_request, require_mfa_for_privileged
from app.db.pool import get_db
from app.influencer import ensure_module_enabled
from app.influencer.instagram_oauth import (
    DEFAULT_SCOPES,
    build_authorize_url,
    build_oauth_state,
    verify_oauth_state,
)
from app.influencer.personas_router import _set_tenant_scope

logger = logging.getLogger(__name__)


instagram_router = APIRouter(
    prefix='/v1/influencer/personas/{persona_id}/platforms/instagram',
    tags=['influencer-instagram-oauth'],
    dependencies=[
        Depends(authenticate_request),
        Depends(ensure_module_enabled),
    ],
)


def _state_secret() -> str:
    """JWT_SECRET es shared para todos los HMAC del módulo."""
    return os.environ.get('JWT_SECRET', 'test-jwt-secret-min-length-16-chars')


def _config(name: str, default: str = '') -> str:
    return os.environ.get(name, default)


def _require_tenant_id(request: Request) -> UUID:
    tenant_id = getattr(request.state, 'tenant_id', None)
    if tenant_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'module not available')
    return tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))


# ─── Models ────────────────────────────────────────────────────────────────


class ConnectionResponse(BaseModel):
    id: UUID
    persona_id: UUID
    platform: str
    external_handle: str | None = None
    status: str
    scopes: list[str]
    expires_at: datetime | None = None


# ─── Endpoints ─────────────────────────────────────────────────────────────


@instagram_router.get(
    '/oauth/start',
    summary='Redirige a Meta para autorizar Instagram',
    response_class=RedirectResponse,
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
)
async def oauth_start(
    persona_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> RedirectResponse:
    tenant_id = _require_tenant_id(request)
    await _set_tenant_scope(conn, tenant_id)

    persona = await conn.fetchrow(
        'select id, status from influencer.personas where id = $1', persona_id,
    )
    if persona is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'persona not found')

    client_id = _config('INSTAGRAM_CLIENT_ID')
    redirect_uri = _config('INSTAGRAM_REDIRECT_URI')
    if not client_id or not redirect_uri:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            'instagram oauth not configured',
        )

    state = build_oauth_state(persona_id=persona_id, secret=_state_secret())
    url = build_authorize_url(
        client_id=client_id, redirect_uri=redirect_uri, state=state,
    )
    logger.info(
        'instagram oauth start tenant=%s persona=%s', tenant_id, persona_id,
    )
    return RedirectResponse(url=url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@instagram_router.get(
    '/oauth/callback',
    response_model=ConnectionResponse,
    summary='Callback OAuth — exchange code → tokens → connection row',
)
async def oauth_callback(
    persona_id: UUID,
    request: Request,
    code: str,
    state: str,
    conn: asyncpg.Connection = Depends(get_db),
) -> ConnectionResponse:
    tenant_id = _require_tenant_id(request)
    user_id = getattr(request.state, 'user_id', None)
    await _set_tenant_scope(conn, tenant_id)

    # 1. Verifica el state (HMAC + TTL + persona match).
    try:
        verify_oauth_state(
            state=state,
            secret=_state_secret(),
            expected_persona_id=persona_id,
        )
    except ValueError as exc:
        logger.warning('oauth state invalid persona=%s: %s', persona_id, exc)
        raise HTTPException(status.HTTP_403_FORBIDDEN, f'invalid state: {exc}') from exc

    # 2. Exchange code (en producción se llamaría a INSTAGRAM_TOKEN_URL via
    #    httpx; en tests, esto se mockea via httpx.MockTransport o monkeypatch
    #    de `_exchange_code`). Aquí dejamos el contrato listo con un stub
    #    para que el caller real lo conecte.
    token_data = await _exchange_code(code)
    access_token = token_data['access_token']
    external_account_id = token_data.get('user_id', '')
    expires_in = int(token_data.get('expires_in', 5184000))  # 60 días default

    # 3. Persiste el token en `app.platform_secrets` (opaco).
    secret_ref = f'instagram://persona-{persona_id}/access-token'
    await _store_secret(conn, secret_ref, access_token, user_id)

    # 4. Inserta o update la row en `platform_connections`.
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    row = await conn.fetchrow(
        '''
        insert into influencer.platform_connections
          (tenant_id, persona_id, platform, external_account_id,
           oauth_token_ref, scopes, status, connected_at, expires_at)
        values
          ($1, $2, 'instagram', $3, $4, $5, 'connected', now(), $6)
        on conflict (persona_id, platform)
          where status <> 'disconnected'
          do update set
            external_account_id = excluded.external_account_id,
            oauth_token_ref = excluded.oauth_token_ref,
            scopes = excluded.scopes,
            status = 'connected',
            connected_at = now(),
            expires_at = excluded.expires_at
        returning *
        ''',
        tenant_id, persona_id, external_account_id, secret_ref,
        list(DEFAULT_SCOPES), expires_at,
    )

    return ConnectionResponse(
        id=row['id'],
        persona_id=row['persona_id'],
        platform=row['platform'],
        external_handle=row['external_handle'],
        status=row['status'],
        scopes=list(row['scopes']),
        expires_at=row['expires_at'],
    )


@instagram_router.post(
    '/disconnect',
    response_model=ConnectionResponse,
    summary='Desconecta Instagram (requiere MFA — operación sensible)',
    dependencies=[Depends(require_mfa_for_privileged)],
)
async def oauth_disconnect(
    persona_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> ConnectionResponse:
    tenant_id = _require_tenant_id(request)
    await _set_tenant_scope(conn, tenant_id)
    row = await conn.fetchrow(
        '''
        update influencer.platform_connections
        set status = 'disconnected',
            oauth_token_ref = null,
            refresh_token_ref = null
        where persona_id = $1 and platform = 'instagram' and status <> 'disconnected'
        returning *
        ''',
        persona_id,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'connection not found')
    return ConnectionResponse(
        id=row['id'],
        persona_id=row['persona_id'],
        platform=row['platform'],
        external_handle=row['external_handle'],
        status=row['status'],
        scopes=list(row['scopes']),
        expires_at=row['expires_at'],
    )


# ─── Stubs (caller real swappea con httpx + storage) ───────────────────────


async def _exchange_code(code: str) -> dict:
    """Stub: producción llama a `INSTAGRAM_TOKEN_URL` con `code` y
    devuelve `{access_token, user_id, expires_in}`. Tests monkeypatchean
    esta función para mock del response sin HTTP."""
    raise NotImplementedError(
        'configure INSTAGRAM exchange in entrypoint (TASK-INFLU-018)',
    )


async def _store_secret(
    conn: asyncpg.Connection, secret_ref: str, value: str, user_id: UUID | None,
) -> None:
    """Stub: persiste el secret en `app.platform_secrets`. Producción
    usa backend env/aws_sm/vault; aquí cumplimos el contrato mínimo."""
    hint = value[-4:] if len(value) >= 4 else value
    await conn.execute(
        '''
        insert into app.platform_secrets
          (secret_ref, backend, ciphertext, hint, created_by)
        values ($1, 'env', null, $2, $3)
        on conflict (secret_ref) do update set
          hint = excluded.hint,
          rotated_at = now()
        ''',
        secret_ref, hint, user_id,
    )


__all__ = ['instagram_router']
