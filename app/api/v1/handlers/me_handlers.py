"""Handlers extracted from routes.py for me_router.

Original location: app/api/v1/routes.py (refactor step 3).
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import asyncpg
from fastapi import Depends, HTTPException, Request, Response, status

from app.api.v1._helpers.sessions import AUTH_SESSION_ACTIVE_HOURS
from app.api.v1._helpers.support_mode import (
    SUPPORT_MODE_TTL_SECONDS,
)
from app.api.v1._helpers.normalizers import _serialize_profile
from app.api.v1._helpers.validators import _validate_notification_matrix, _validate_timezone
from app.api.v1.routes import (
    _load_user_preferences_row,
    _require_current_user,
    _session_id_from_request,
    me_router,
    record_auth_session,
)
from app.core.config import get_settings
from app.core.security import SUPPORT_MODE_COOKIE_NAME, require_mfa_for_privileged
from app.core.signed_cookies import pack_signed_payload, unpack_signed_payload
from app.db.pool import get_db
from app.services.audit import audit, audit_durably


@me_router.get('/me/profile')
async def get_my_profile(request: Request, conn: asyncpg.Connection = Depends(get_db)):
    """Return the canonical profile shape consumed by `/account/profile`.

    Merges the Auth0-synced fields on `app.users` (email/display_name/mfa)
    with the user-managed overrides in `app.user_preferences` (phone,
    locale, timezone).
    """
    user_id = await _require_current_user(request, conn)
    prefs_row = await _load_user_preferences_row(conn, user_id)
    user_row = await conn.fetchrow(
        'select email, display_name, status, mfa_enabled, last_login_at from app.users where id=$1',
        user_id,
    )
    if user_row is None:
        raise HTTPException(status_code=404, detail='User row missing')
    return _serialize_profile(prefs_row, user_row, user_id)


@me_router.patch('/me/profile')
async def patch_my_profile(
    payload: dict, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    """PATCH `/me/profile`. Allowed keys: display_name, phone, locale, timezone.

    Email is intentionally NOT writable here — it is owned by Auth0 (the
    identity provider) and would diverge from the JWT subject. Validation:
      - `display_name`: str ≤ 200 chars or null.
      - `phone`: str ≤ 32 chars or null.
      - `locale`: must appear in the SUPPORTED_COUNTRIES locale catalog (or null).
      - `timezone`: must parse as a valid IANA zone via `ZoneInfo(...)` (or null).
    """
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail='Body must be an object')
    user_id = await _require_current_user(request, conn)

    allowed_keys = ('display_name', 'phone', 'locale', 'timezone')
    updates = {key: payload[key] for key in allowed_keys if key in payload}

    if 'display_name' in updates and updates['display_name'] is not None:
        if not isinstance(updates['display_name'], str) or len(updates['display_name']) > 200:
            raise HTTPException(status_code=422, detail='display_name must be a string ≤ 200 chars')
    if 'phone' in updates and updates['phone'] is not None:
        if not isinstance(updates['phone'], str) or len(updates['phone']) > 32:
            raise HTTPException(status_code=422, detail='phone must be a string ≤ 32 chars')
    if 'locale' in updates and updates['locale'] is not None:
        if not isinstance(updates['locale'], str):
            raise HTTPException(status_code=422, detail='locale must be a string')
        # codex P1 (UI-016.7-FU review): SUPPORTED_COUNTRIES is a tuple of
        # country codes ('CO', 'MX', ...), NOT a dict of profiles. Calling
        # .values() on it AttributeErrors and every PATCH /me/profile with
        # `locale` returns 500 instead of persisting.
        #
        # BUG-075 (codex P2 follow-up): la validación anterior solo aceptaba
        # los locales "default" por país (`es-CO`, `es-MX`, etc. — UNO por
        # país). Pero el frontend (`ACCOUNT_LOCALES` en accountData.js)
        # expone también `es-ES`, `en-US`, `pt-BR` que el usuario puede
        # elegir explícitamente. Sin la whitelist extendida, esos selects
        # respondían 422. Usamos `SUPPORTED_USER_LOCALES` (frozenset
        # canónico en app/services/locale.py) para que ambos lados queden
        # en sync.
        from app.services.locale import SUPPORTED_USER_LOCALES  # noqa: PLC0415
        if updates['locale'] not in SUPPORTED_USER_LOCALES:
            raise HTTPException(status_code=422, detail=f'Unsupported locale: {updates["locale"]}')
    if 'timezone' in updates:
        _validate_timezone(updates['timezone'])

    # Ensure the row exists before UPDATE.
    await _load_user_preferences_row(conn, user_id)

    if updates:
        # Build the SET clause dynamically; user_id is $1, fields start at $2.
        set_clause = ', '.join(f'{key}=${idx + 2}' for idx, key in enumerate(updates.keys()))
        params = [user_id, *updates.values()]
        await conn.execute(
            f'update app.user_preferences set {set_clause} where user_id=$1',
            *params,
        )
        await audit(
            conn,
            tenant_id=None,
            actor_type=request.state.actor_type,
            actor_id=request.state.actor_id,
            action='user.preferences_updated',
            entity_type='user_preferences',
            entity_id=str(user_id),
            metadata={'fields': list(updates.keys()), 'scope': 'profile'},
        )

    return await get_my_profile(request, conn)


@me_router.get('/me/preferences')
async def get_my_preferences(request: Request, conn: asyncpg.Connection = Depends(get_db)):
    """Return the per-user UI preferences (currently: `theme_override`)."""
    user_id = await _require_current_user(request, conn)
    prefs_row = await _load_user_preferences_row(conn, user_id)
    return {
        'user_id': str(user_id),
        'theme_override': prefs_row['theme_override'],
        'locale': prefs_row['locale'],
        'timezone': prefs_row['timezone'],
    }


@me_router.patch('/me/preferences')
async def patch_my_preferences(
    payload: dict, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    """PATCH `/me/preferences`. Currently only `theme_override` is writable.

    Valid values: `'auto' | 'light' | 'dark' | null`. The schema check enforces
    this at the DB level too, so a malformed payload would 500 — we validate
    here to return a clean 422.
    """
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail='Body must be an object')
    user_id = await _require_current_user(request, conn)

    if 'theme_override' in payload:
        value = payload['theme_override']
        if value is not None and value not in ('auto', 'light', 'dark'):
            raise HTTPException(
                status_code=422,
                detail="theme_override must be one of 'auto', 'light', 'dark' or null",
            )
        await _load_user_preferences_row(conn, user_id)
        await conn.execute(
            'update app.user_preferences set theme_override=$2 where user_id=$1',
            user_id,
            value,
        )
        await audit(
            conn,
            tenant_id=None,
            actor_type=request.state.actor_type,
            actor_id=request.state.actor_id,
            action='user.preferences_updated',
            entity_type='user_preferences',
            entity_id=str(user_id),
            metadata={'fields': ['theme_override'], 'scope': 'preferences'},
        )

    return await get_my_preferences(request, conn)


@me_router.get('/me/notifications')
async def get_my_notifications(request: Request, conn: asyncpg.Connection = Depends(get_db)):
    """Return the `notification_matrix` (event_id → channel toggles) for this user."""
    user_id = await _require_current_user(request, conn)
    prefs_row = await _load_user_preferences_row(conn, user_id)
    matrix = prefs_row['notification_matrix']
    if isinstance(matrix, str):
        # asyncpg returns jsonb as text when no codec is registered; defensive parse.
        matrix = json.loads(matrix)
    return {
        'user_id': str(user_id),
        'notification_matrix': matrix or {},
    }


@me_router.patch('/me/notifications')
async def patch_my_notifications(
    payload: dict, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    """PATCH `/me/notifications` — replaces the entire matrix atomically.

    The frontend `AccountNotifications` form submits the FULL matrix on every
    save (so we do not need partial diffing here). The payload shape is
    `{notification_matrix: {event_id: {channel_id: bool}}}`.
    """
    if not isinstance(payload, dict):
        raise HTTPException(status_code=422, detail='Body must be an object')
    user_id = await _require_current_user(request, conn)

    if 'notification_matrix' not in payload:
        raise HTTPException(status_code=422, detail='notification_matrix is required')

    matrix = _validate_notification_matrix(payload['notification_matrix'])

    await _load_user_preferences_row(conn, user_id)
    await conn.execute(
        'update app.user_preferences set notification_matrix=$2::jsonb where user_id=$1',
        user_id,
        json.dumps(matrix),
    )
    await audit(
        conn,
        tenant_id=None,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='user.preferences_updated',
        entity_type='user_preferences',
        entity_id=str(user_id),
        metadata={
            'fields': ['notification_matrix'],
            'scope': 'notifications',
            'event_count': len(matrix),
        },
    )

    return await get_my_notifications(request, conn)


@me_router.get('/me/sessions')
async def list_my_sessions(request: Request, conn: asyncpg.Connection = Depends(get_db)):
    """UI-016.7-FU-SESSIONS: devuelve las sesiones activas del usuario.

    Cada request a este endpoint upsertea su propia sesión via
    `record_auth_session(...)` antes de listar, lo que garantiza:
      1. Si la UI muestra "esta sesión", al menos hay una fila (la actual).
      2. `last_seen_at` se refresca con cada hit del frontend al endpoint.

    El campo `current: true` se marca por igualdad con el `session_id` que
    `record_auth_session` acaba de upsertear, sin depender de heurísticas
    sobre `last_seen_at` (que podrían marcar como current una sesión vieja
    si dos pestañas con el mismo JWT hacen request casi simultáneo).
    """
    user_id = await _require_current_user(request, conn)
    current_sid = await record_auth_session(request, conn, user_id)
    # BUG-168: filtrar sesiones cuyo JWT ya expiró. `auth_sessions` no tiene
    # `expires_at` (la expiración vive en el `exp` del JWT), así que usamos
    # `last_seen_at` como proxy: sesiones que no han hecho hit al endpoint
    # en `AUTH_SESSION_ACTIVE_HOURS` (default 24h) son efectivamente
    # muertas — su token ya expiró o la pestaña se cerró hace tiempo. Antes
    # devolvíamos TODO lo que tuviera `revoked_at is null`, lo que mostraba
    # al usuario sesiones fantasmas que ya no podían hacer nada y le hacía
    # creer que alguien estaba conectado.
    rows = await conn.fetch(
        """
        select id, user_agent, ip::text as ip, location, device,
               created_at, last_seen_at
        from app.auth_sessions
        where user_id = $1
          and revoked_at is null
          and last_seen_at >= now() - ($2 || ' hours')::interval
        order by last_seen_at desc
        """,
        user_id,
        str(AUTH_SESSION_ACTIVE_HOURS),
    )
    sessions = []
    for row in rows:
        sessions.append(
            {
                'id': row['id'],
                'current': row['id'] == current_sid,
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                'last_seen_at': row['last_seen_at'].isoformat() if row['last_seen_at'] else None,
                'device': row['device'],
                'user_agent': row['user_agent'],
                'ip': row['ip'],
                'location': row['location'],
            }
        )
    return {'user_id': str(user_id), 'sessions': sessions}


@me_router.delete('/me/sessions/{session_id}', status_code=status.HTTP_204_NO_CONTENT)
async def revoke_my_session(
    session_id: str, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    """UI-016.7-FU-SESSIONS: marca una sesión como revocada.

    El frontend puede pasar el alias `current` para revocar la sesión
    asociada al JWT que viene en la request; resolvemos contra
    `_session_id_from_request` y delegamos al mismo path del id explícito.

    El UPDATE filtra por `user_id` para impedir que un usuario revoque
    sesiones ajenas (el endpoint no permite indicar otro `user_id` en path —
    todos los `/me/*` derivan el `user_id` del JWT). Devuelve 404 si el
    `session_id` no pertenece a este usuario o si ya estaba revocado.

    Notas sobre Auth0:
      - Este endpoint marca `revoked_at` en nuestra tabla pero NO invalida
        el JWT (es stateless). El backend ignora sesiones revocadas en los
        listados; para forzar logout efectivo, el cliente debe seguir el
        flow `/admin/logout` (que clava la cookie HTTP-only de Auth0).
      - Revocar el refresh token vía Auth0 Management API queda como
        follow-up; documentado en la entrada `UI-016.7-FU-SESSIONS` del
        backlog (sección "Notas / limitaciones").
    """
    user_id = await _require_current_user(request, conn)
    target_id = session_id
    if session_id == 'current':
        derived = _session_id_from_request(request)
        if not derived:
            raise HTTPException(status_code=404, detail='Session not found')
        target_id = derived

    result = await conn.execute(
        """
        update app.auth_sessions
        set revoked_at = now()
        where id = $1 and user_id = $2 and revoked_at is null
        """,
        target_id,
        user_id,
    )
    # asyncpg returns 'UPDATE 0' when no rows matched.
    if result.endswith(' 0'):
        raise HTTPException(status_code=404, detail='Session not found')

    await audit(
        conn,
        tenant_id=None,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='user.session_revoked',
        entity_type='user_session',
        entity_id=target_id,
        metadata={
            'scope': 'sessions',
            'action': 'revoke',
            'user_id': str(user_id),
            'alias_used': session_id == 'current',
        },
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@me_router.post(
    '/me/support-mode/{tenant_id}',
    status_code=status.HTTP_201_CREATED,
    # BUG-197 (codex HIGH): `activate_support_mode` permite que un
    # `platform_owner` opte temporalmente al modo cross-tenant. Por la matriz
    # de riesgos (TASK-0080) el cross-tenant access es uno de los privilegios
    # más sensibles del sistema → MFA debe ser obligatorio. El router base
    # `me_router` no fuerza MFA (la mayoría de `/me/*` es para usuarios
    # normales), así que la dependency se ata por-endpoint.
    dependencies=[Depends(require_mfa_for_privileged)],
)
async def activate_support_mode(
    tenant_id: UUID,
    request: Request,
    response: Response,
    payload: dict | None = None,
    conn: asyncpg.Connection = Depends(get_db),
):
    """BUG-008 — activa support_mode opt-in temporal para `tenant_id`.

    Requiere:
      - JWT validado como user (no service token).
      - Rol global `platform_owner` (sin esto, el rol no tiene scope
        cross-tenant y el toggle es vacío).
      - `tenant_id` existe y no está borrado.
      - body opcional `{"justification": "<≥8 chars>"}` — recomendado por
        forensia, requerido si lo dejas vacío para no fomentar logging
        sin contexto (la API NO falla si está vacío, solo registra
        'unspecified' en el audit — pero el frontend lo prompt en el modal).

    Side effects:
      - Emite cookie HTTP-only firmado con payload {sub, tid, iat, exp}.
      - Audit log durable `support_mode.activated` con metadata completa.

    El cookie es scoped al tenant_id por construcción: el JWT que sigue
    llegando puede tener `support_mode=false` pero `authenticate_request`
    lo OR-ea con el cookie SOLO si matchea el `X-Tenant-Id` que el caller
    manda. Otros tenant_ids no se ven afectados aunque el cookie esté en
    el browser (anti-blast-radius).
    """
    actor_type = getattr(request.state, 'actor_type', None)
    if actor_type != 'user':
        raise HTTPException(status_code=401, detail='Authentication required')
    actor_id = getattr(request.state, 'actor_id', None)
    if not actor_id:
        raise HTTPException(status_code=401, detail='Authentication required')
    if 'platform_owner' not in (getattr(request.state, 'roles', []) or []):
        raise HTTPException(
            status_code=403,
            detail='platform_owner role required to activate support_mode',
        )

    # Validar que el tenant existe — el cookie scoped a un UUID inexistente
    # no es exploitable, pero el 404 evita confusión operacional.
    tenant_exists = await conn.fetchval(
        'select 1 from app.tenants where id=$1 and deleted_at is null',
        tenant_id,
    )
    if not tenant_exists:
        raise HTTPException(status_code=404, detail='Tenant not found')

    justification = ''
    if isinstance(payload, dict):
        raw_just = payload.get('justification')
        if isinstance(raw_just, str):
            justification = raw_just.strip()[:512]

    settings = get_settings()
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=SUPPORT_MODE_TTL_SECONDS)
    cookie_payload = {
        'sub': actor_id,
        'tid': str(tenant_id),
        'iat': int(now.timestamp()),
        'exp': int(expires_at.timestamp()),
    }
    cookie_value = pack_signed_payload(settings.jwt_secret, cookie_payload)
    # `samesite='lax'` permite que la navegación desde la vista platform
    # mande el cookie cuando el usuario hace click en "Ver como tenant".
    # `secure=True` en prod — en localhost dev http no se setea (cookie
    # `secure` no se envía en http). Sin esa toggle el flow dev se rompe.
    response.set_cookie(
        SUPPORT_MODE_COOKIE_NAME,
        cookie_value,
        httponly=True,
        samesite='lax',
        max_age=SUPPORT_MODE_TTL_SECONDS,
        secure=settings.app_env != 'local',
    )

    await audit_durably(
        tenant_id=tenant_id,
        actor_type='user',
        actor_id=actor_id,
        action='support_mode.activated',
        entity_type='tenant',
        entity_id=str(tenant_id),
        metadata={
            'expires_at': expires_at.isoformat(),
            'ttl_seconds': SUPPORT_MODE_TTL_SECONDS,
            'justification': justification or 'unspecified',
            'justification_length': len(justification),
        },
    )

    return {
        'tenant_id': str(tenant_id),
        'expires_at': expires_at.isoformat(),
        'ttl_seconds': SUPPORT_MODE_TTL_SECONDS,
    }


@me_router.delete('/me/support-mode/{tenant_id}', status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_support_mode(
    tenant_id: UUID,
    request: Request,
    response: Response,
):
    """BUG-008 — revoca el cookie de support_mode antes del TTL.

    No requiere que el cookie matchee exactamente el `tenant_id` del path
    — borramos el cookie sea cual sea. Si el caller no tiene un cookie
    activo, igual devolvemos 204 (idempotente — el cliente no necesita
    diferenciar "no había nada que borrar" de "borrado exitoso").

    BUG-198 (codex HIGH) — el audit_durably debe llamarse SOLO si el cookie
    matchea el `tenant_id` del path. Antes el endpoint escribía un audit
    `support_mode.deactivated` con `tenant_id=<path>` para CUALQUIER user
    autenticado, sin chequear que esa persona tuviera support_mode activo
    para ese tenant. Resultado: cualquier auth user (no platform_owner)
    podía polucionar el audit log del tenant víctima con falsas
    "deactivation" entries — el `audit_durably` setea
    `app.tenant_id=<victim>` en una conn fresca y el INSERT pasa la RLS
    porque la policy `audit_logs_tenant_insert` solo exige
    `tenant_id = app.current_tenant_id()`, no que el actor tenga rol en
    ese tenant.

    Fix: leer el cookie ANTES del audit; si no matchea (o no hay cookie),
    devolvemos 204 con cookie clear pero SIN audit log — la deactivation
    es vacua, no hay nada que auditar.
    """
    actor_type = getattr(request.state, 'actor_type', None)
    if actor_type != 'user':
        raise HTTPException(status_code=401, detail='Authentication required')
    actor_id = getattr(request.state, 'actor_id', None)
    if not actor_id:
        raise HTTPException(status_code=401, detail='Authentication required')

    # BUG-198: verificar que el cookie matchea el tenant del path Y el sub
    # del JWT antes de auditar. El cookie tiene `{sub, tid, iat, exp}` firmado.
    settings = get_settings()
    cookie_value = request.cookies.get(SUPPORT_MODE_COOKIE_NAME)
    cookie_matches_request = False
    if cookie_value:
        cookie_payload = unpack_signed_payload(settings.jwt_secret, cookie_value)
        if cookie_payload:
            cookie_tid = cookie_payload.get('tid')
            cookie_sub = cookie_payload.get('sub')
            # BUG-229 (codex P2 follow-up sobre BUG-198): además del tid/sub
            # match, verificar `exp > now`. Sin esto, un client replaying un
            # cookie viejo signed con el mismo `sub`+`tid` después del TTL
            # original (1h) seguía contando como "match" y triggereaba audit
            # `support_mode.deactivated` en el tenant víctima. El cookie ya
            # expiró → no representa una sesión activa de support-mode →
            # el audit no debe registrarse.
            cookie_exp = cookie_payload.get('exp')
            now_ts = int(datetime.now(UTC).timestamp())
            if (
                isinstance(cookie_tid, str)
                and cookie_tid == str(tenant_id)
                and cookie_sub == actor_id
                and isinstance(cookie_exp, int)
                and cookie_exp > now_ts
            ):
                cookie_matches_request = True

    response.delete_cookie(
        SUPPORT_MODE_COOKIE_NAME,
        httponly=True,
        samesite='lax',
    )

    if cookie_matches_request:
        await audit_durably(
            tenant_id=tenant_id,
            actor_type='user',
            actor_id=actor_id,
            action='support_mode.deactivated',
            entity_type='tenant',
            entity_id=str(tenant_id),
            metadata={},
        )
    # codex P2 fix: NO retornar un Response nuevo — eso descarta los
    # headers que `response.delete_cookie(...)` puso en el response
    # inyectado por FastAPI (incluido el `Set-Cookie` con `Max-Age=0` que
    # el browser necesita para expirar el cookie). Mutamos el status_code
    # en el response inyectado y lo devolvemos tal cual.
    response.status_code = status.HTTP_204_NO_CONTENT
    return response

