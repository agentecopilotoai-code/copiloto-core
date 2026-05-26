"""Handlers `/v1/me/*` — perfil, preferencias, notificaciones, sesiones.

Endpoints user-scoped: cada uno opera SIEMPRE sobre el usuario
autenticado (`request.state.actor_id` → `app.users.id`). El path NO
acepta `user_id` como parámetro: imposible editar perfil ajeno.

Branch `core`: reescrito sin cross-imports al monolítico routes.py viejo.
Los helpers compartidos viven en `app.api.v1._helpers.me_utils`.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1._helpers.me_utils import (
    _load_user_preferences_row,
    _require_current_user,
    _session_id_from_request,
    record_auth_session,
)
from app.api.v1._helpers.normalizers import _serialize_profile
from app.api.v1.routes import me_router
from app.core.config import get_settings
from app.core.security import SUPPORT_MODE_COOKIE_NAME
from app.core.signed_cookies import pack_signed_payload
from app.db.pool import get_db
from app.services.audit import audit


# ─── Schemas ────────────────────────────────────────────────────────────────


class ProfilePatchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=40)


class PreferencesPatchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    locale: str | None = Field(default=None, min_length=2, max_length=10)
    timezone: str | None = Field(default=None, max_length=80)
    theme_override: str | None = Field(default=None)


class NotificationsPatchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    notification_matrix: dict[str, Any]


class SessionRow(BaseModel):
    id: str
    device: str | None = None
    user_agent: str | None = None
    ip: str | None = None
    location: str | None = None
    created_at: str
    last_seen_at: str
    current: bool = False


class SessionListResponse(BaseModel):
    items: list[SessionRow]


# ─── /me/profile ────────────────────────────────────────────────────────────


@me_router.get('/me/profile')
async def get_my_profile(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    user_id = await _require_current_user(request, conn)
    user_row = await conn.fetchrow(
        'select email, display_name, mfa_enabled, last_login_at from app.users where id=$1',
        user_id,
    )
    if user_row is None:
        raise HTTPException(404, 'user_not_found')
    prefs = await _load_user_preferences_row(conn, user_id)
    return _serialize_profile(prefs, user_row, user_id)


@me_router.patch('/me/profile')
async def patch_my_profile(
    body: ProfilePatchRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    user_id = await _require_current_user(request, conn)
    patch = body.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(400, 'empty_patch')
    await _load_user_preferences_row(conn, user_id)
    sets, params = [], []
    for field in ('display_name', 'phone'):
        if field in patch:
            params.append(patch[field])
            sets.append(f'{field} = ${len(params)}')
    if sets:
        params.append(user_id)
        await conn.execute(
            f'update app.user_preferences set {", ".join(sets)}, updated_at = now() '
            f'where user_id = ${len(params)}',
            *params,
        )
    await audit(
        conn, tenant_id=None, actor_type='user', actor_id=str(user_id),
        action='user.profile_updated', entity_type='user', entity_id=str(user_id),
        metadata={'fields': list(patch.keys())},
    )
    user_row = await conn.fetchrow(
        'select email, display_name, mfa_enabled, last_login_at from app.users where id=$1',
        user_id,
    )
    prefs = await _load_user_preferences_row(conn, user_id)
    return _serialize_profile(prefs, user_row, user_id)


# ─── /me/preferences ───────────────────────────────────────────────────────


@me_router.get('/me/preferences')
async def get_my_preferences(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    user_id = await _require_current_user(request, conn)
    prefs = await _load_user_preferences_row(conn, user_id)
    return {
        'locale': prefs['locale'],
        'timezone': prefs['timezone'],
        'theme_override': prefs['theme_override'],
    }


_ALLOWED_THEMES = {None, 'auto', 'light', 'dark'}


@me_router.patch('/me/preferences')
async def patch_my_preferences(
    body: PreferencesPatchRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    user_id = await _require_current_user(request, conn)
    patch = body.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(400, 'empty_patch')
    if 'theme_override' in patch and patch['theme_override'] not in _ALLOWED_THEMES:
        raise HTTPException(422, 'invalid_theme')
    await _load_user_preferences_row(conn, user_id)
    sets, params = [], []
    for field in ('locale', 'timezone', 'theme_override'):
        if field in patch:
            params.append(patch[field])
            sets.append(f'{field} = ${len(params)}')
    if sets:
        params.append(user_id)
        await conn.execute(
            f'update app.user_preferences set {", ".join(sets)}, updated_at = now() '
            f'where user_id = ${len(params)}',
            *params,
        )
    await audit(
        conn, tenant_id=None, actor_type='user', actor_id=str(user_id),
        action='user.preferences_updated', entity_type='user', entity_id=str(user_id),
        metadata={'fields': list(patch.keys())},
    )
    prefs = await _load_user_preferences_row(conn, user_id)
    return {
        'locale': prefs['locale'],
        'timezone': prefs['timezone'],
        'theme_override': prefs['theme_override'],
    }


# ─── /me/notifications ─────────────────────────────────────────────────────


@me_router.get('/me/notifications')
async def get_my_notifications(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    user_id = await _require_current_user(request, conn)
    prefs = await _load_user_preferences_row(conn, user_id)
    matrix = prefs['notification_matrix']
    if isinstance(matrix, str):
        matrix = json.loads(matrix)
    return {'notification_matrix': matrix or {}}


@me_router.patch('/me/notifications')
async def patch_my_notifications(
    body: NotificationsPatchRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    user_id = await _require_current_user(request, conn)
    matrix = body.notification_matrix
    if not isinstance(matrix, dict):
        raise HTTPException(422, 'notification_matrix_must_be_object')
    await _load_user_preferences_row(conn, user_id)
    await conn.execute(
        'update app.user_preferences set notification_matrix = $1::jsonb, '
        'updated_at = now() where user_id = $2',
        json.dumps(matrix), user_id,
    )
    await audit(
        conn, tenant_id=None, actor_type='user', actor_id=str(user_id),
        action='user.notifications_updated', entity_type='user', entity_id=str(user_id),
    )
    return {'notification_matrix': matrix}


# ─── /me/sessions ──────────────────────────────────────────────────────────


@me_router.get('/me/sessions', response_model=SessionListResponse)
async def list_my_sessions(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> SessionListResponse:
    user_id = await _require_current_user(request, conn)
    current_sid = await record_auth_session(request, conn, user_id)
    rows = await conn.fetch(
        '''
        select id, device, user_agent, ip::text as ip, location, created_at, last_seen_at
        from app.auth_sessions
        where user_id = $1 and revoked_at is null
        order by last_seen_at desc
        ''',
        user_id,
    )
    return SessionListResponse(items=[
        SessionRow(
            id=r['id'],
            device=r['device'],
            user_agent=r['user_agent'],
            ip=r['ip'],
            location=r['location'],
            created_at=r['created_at'].isoformat(),
            last_seen_at=r['last_seen_at'].isoformat(),
            current=(r['id'] == current_sid),
        )
        for r in rows
    ])


@me_router.delete('/me/sessions/{session_id}', status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def revoke_my_session(
    session_id: str,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> None:
    user_id = await _require_current_user(request, conn)
    # Forzar pertenencia: el WHERE incluye user_id para que un atacante no
    # pueda revocar sesiones de otro usuario aunque adivine el session_id.
    result = await conn.execute(
        '''
        update app.auth_sessions
           set revoked_at = now()
         where id = $1 and user_id = $2 and revoked_at is null
        ''',
        session_id, user_id,
    )
    if result.endswith(' 0'):
        raise HTTPException(404, 'session_not_found')
    await audit(
        conn, tenant_id=None, actor_type='user', actor_id=str(user_id),
        action='user.session_revoked', entity_type='auth_session', entity_id=session_id,
    )


# ─── /me/support-mode/{tenant_id} ──────────────────────────────────────────
# BUG-008 — opt-in temporal de support_mode por tenant.
#
# El platform_owner (o `owner` global con su `app_metadata.support_mode=true`)
# puede activar support_mode UN tenant ajeno a la vez. Sin esto, la única
# alternativa histórica era marcar `support_mode=true` permanente en Auth0,
# lo cual amplía el blast-radius más allá del problema concreto.
#
# Diseño:
#   - POST emite una cookie `copilotoia_support_mode` firmada HMAC
#     (jwt_secret) con `{tid, sub, exp}`. TTL: 1h por default.
#   - DELETE limpia la cookie (mismo nombre, max_age=0).
#   - `authenticate_request` lee la cookie en cada request que envíe
#     `X-Tenant-Id` matcheando `tid`; si todo coincide y el `sub` matchea
#     el del JWT, bumpea `support_mode=True` para esa request.
#   - Sin `X-Tenant-Id`, la cookie se ignora (el opt-in es per-tenant).

SUPPORT_MODE_TTL_SECONDS = 3600
SUPPORT_MODE_MIN_JUSTIFICATION_LEN = 8

_SUPPORT_MODE_ROLES = {'platform_owner', 'owner'}


class SupportModeActivateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    justification: str | None = Field(
        default=None,
        min_length=SUPPORT_MODE_MIN_JUSTIFICATION_LEN,
        max_length=500,
    )


class SupportModeActivateResponse(BaseModel):
    tenant_id: str
    expires_at: str
    ttl_seconds: int


def _caller_can_use_support_mode(roles: list[str]) -> bool:
    """Solo roles globales (platform_owner / owner) pueden activar support_mode."""
    return any(r in _SUPPORT_MODE_ROLES for r in roles or [])


@me_router.post(
    '/me/support-mode/{tenant_id}',
    response_model=SupportModeActivateResponse,
)
async def activate_support_mode(
    tenant_id: UUID,
    request: Request,
    response: Response,
    body: SupportModeActivateRequest | None = None,
    conn: asyncpg.Connection = Depends(get_db),
) -> SupportModeActivateResponse:
    """Activa support_mode opt-in para `tenant_id` durante TTL segundos.

    Defensas:
      - Caller debe estar autenticado (`authenticate_request` ya corrió).
      - Caller debe tener rol global elevable (platform_owner / owner).
      - Tenant target debe existir.
      - Cookie firmada con jwt_secret + sub + exp; sin esos campos
        matcheando el JWT, `authenticate_request` la ignora.
      - Audit log con `metadata.justification` para forensia.
    """
    actor_id = getattr(request.state, 'actor_id', None)
    roles = list(getattr(request.state, 'roles', None) or [])
    if not actor_id:
        raise HTTPException(401, 'authentication_required')
    if not _caller_can_use_support_mode(roles):
        raise HTTPException(403, 'support_mode_requires_global_role')

    # Verificar que el tenant existe (sin RLS — tabla platform-scoped).
    exists = await conn.fetchval(
        'select 1 from app.tenants where id = $1 and deleted_at is null',
        tenant_id,
    )
    if not exists:
        raise HTTPException(404, 'tenant_not_found')

    settings = get_settings()
    if not settings.jwt_secret:
        raise HTTPException(500, 'jwt_secret_not_configured')

    expires_at = datetime.now(UTC) + timedelta(seconds=SUPPORT_MODE_TTL_SECONDS)
    payload = {
        'tid': str(tenant_id),
        'sub': actor_id,
        'exp': int(expires_at.timestamp()),
    }
    cookie_value = pack_signed_payload(settings.jwt_secret, payload)
    response.set_cookie(
        SUPPORT_MODE_COOKIE_NAME,
        cookie_value,
        httponly=True,
        samesite='strict',
        secure=settings.app_env != 'local',
        max_age=SUPPORT_MODE_TTL_SECONDS,
        path='/',
    )

    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type='user',
        actor_id=actor_id,
        action='platform.support_mode.activated',
        entity_type='tenant',
        entity_id=str(tenant_id),
        metadata={
            'roles': roles,
            'justification_provided': bool(body and body.justification),
            'ttl_seconds': SUPPORT_MODE_TTL_SECONDS,
        },
    )
    return SupportModeActivateResponse(
        tenant_id=str(tenant_id),
        expires_at=expires_at.isoformat(),
        ttl_seconds=SUPPORT_MODE_TTL_SECONDS,
    )


@me_router.delete(
    '/me/support-mode/{tenant_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def deactivate_support_mode(
    tenant_id: UUID,
    request: Request,
    response: Response,
    conn: asyncpg.Connection = Depends(get_db),
) -> None:
    """Limpia la cookie de support_mode.

    Idempotente: 204 incluso si la cookie no estaba activa. Audit log
    siempre se emite (para que el ciclo activate→deactivate quede en
    forensia).
    """
    actor_id = getattr(request.state, 'actor_id', None)
    if not actor_id:
        raise HTTPException(401, 'authentication_required')

    response.delete_cookie(SUPPORT_MODE_COOKIE_NAME, path='/')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type='user',
        actor_id=actor_id,
        action='platform.support_mode.deactivated',
        entity_type='tenant',
        entity_id=str(tenant_id),
    )
