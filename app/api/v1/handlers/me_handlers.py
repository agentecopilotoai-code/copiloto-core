"""Handlers `/v1/me/*` — perfil, preferencias, notificaciones, sesiones.

Endpoints user-scoped: cada uno opera SIEMPRE sobre el usuario
autenticado (`request.state.actor_id` → `app.users.id`). El path NO
acepta `user_id` como parámetro: imposible editar perfil ajeno.

Branch `core`: reescrito sin cross-imports al monolítico routes.py viejo.
Los helpers compartidos viven en `app.api.v1._helpers.me_utils`.
"""
from __future__ import annotations

import json
from typing import Any

import asyncpg
from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1._helpers.me_utils import (
    _load_user_preferences_row,
    _require_current_user,
    _session_id_from_request,
    record_auth_session,
)
from app.api.v1._helpers.normalizers import _serialize_profile
from app.api.v1.routes import me_router
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


# ─── Hook que registra la sesión actual en cada GET /me/profile ────────────
# Side-effect: el primer GET de cualquier `/v1/me/*` upsertea la sesión del
# JWT. No es necesario llamarlo manual desde otros lados.
