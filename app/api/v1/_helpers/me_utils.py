"""Helpers transversales para handlers `/v1/me/*`.

Antes vivían en el monolítico `app/api/v1/routes.py`. Acá en versión
limpia, sin cross-imports.

Funciones:
  - `current_user_id_from_request(request, conn)` → resuelve el UUID de
    `app.users.id` a partir del JWT (`actor_id` = Auth0 `sub`).
    Si el usuario no existe en `app.users` lo crea on-the-fly desde los
    claims del JWT (email, name).
  - `_require_current_user(request, conn)` → wrapper que levanta 401 si
    `current_user_id_from_request` devuelve None.
  - `_load_user_preferences_row(conn, user_id)` → lazy-creates la fila
    en `app.user_preferences` para que los GET nunca devuelvan 404.
  - `_session_id_from_request(request)` → deriva un session id estable
    desde `jti` del JWT (o fallback hash sha256 de sub+iat).
  - `record_auth_session(request, conn, user_id)` → upsertea
    `app.auth_sessions` (la del JWT actual) refrescando `last_seen_at`.
"""
from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import HTTPException, Request

from app.core.security import derive_session_id


def _user_display_name_from_request(request: Request) -> str:
    """Best-effort display name de los claims del JWT.

    Order: `name` → `nickname` → primera parte del email → `actor_id`.
    """
    for claim in ('name', 'nickname'):
        v = getattr(request.state, claim, None)
        if v:
            return str(v)
    email = getattr(request.state, 'email', None)
    if email:
        return str(email).split('@', 1)[0]
    return str(getattr(request.state, 'actor_id', '') or 'usuario')


async def current_user_id_from_request(
    request: Request, conn: asyncpg.Connection,
) -> UUID | None:
    """Resuelve `actor_id` (Auth0 `sub`) → `app.users.id` (UUID).

    Cachea el resultado en `request.state.user_id` para evitar re-consultas
    dentro del mismo request.

    P1-9 (audit 2026-05-27) — toda la lógica branching (auth_subject lookup,
    M57 pending reconciliation, M67 email-match con A-004 email_verified
    gate, INSERT lazy) está consolidada en la SECURITY DEFINER function
    `app.resolve_or_create_user`. Beneficios:
      - 1 round-trip en lugar de hasta 4 en primer login.
      - Locking atómico intra-function (FOR UPDATE) — no race entre
        paths 2 y 3.
      - Bypass de RLS (si en el futuro se habilita en `app.users`).

    El Python solo decide `email_blocked` → raise 403, todo lo demás
    pasa transparente.
    """
    cached = getattr(request.state, 'user_id', None)
    if cached is not None:
        return cached

    actor_id = getattr(request.state, 'actor_id', None)
    actor_type = getattr(request.state, 'actor_type', None)
    if not actor_id or actor_type != 'user':
        return None

    email = getattr(request.state, 'email', None) or f'{actor_id}@auth.local'
    display = _user_display_name_from_request(request)
    email_verified = bool(getattr(request.state, 'email_verified', False))

    row = await conn.fetchrow(
        'select * from app.resolve_or_create_user($1, $2, $3, $4)',
        actor_id, email, display, email_verified,
    )

    # `branch` solo existe en el shape nuevo (post-P1-9). Tests legacy
    # con stubs `{'id': uid}` no lo tienen → tratamos como 'existing'.
    try:
        branch = row['branch'] if row is not None else None
    except (KeyError, TypeError):
        branch = None
    if branch == 'email_blocked':
        # A-004 fail-closed: identidad nueva con email no verificado
        # intentando adoptar sub existente. Auth0 verification email
        # debe completarse antes.
        raise HTTPException(
            status_code=403,
            detail=(
                'Tu email no está verificado. Completá la '
                'verificación enviada por correo antes de '
                'continuar.'
            ),
        )

    if row is None:
        return None

    # Tolerar shape `{'id': uid}` (tests legacy stubbed). En prod la
    # function devuelve `(user_id, branch)`.
    # SEC-017 (audit #2) — log warning si caemos al shape legacy en prod.
    # Si la SQL function alguna vez retorna columnas renombradas
    # (refactor), antes íbamos silenciosamente al return None. Ahora
    # loggeamos para que el operator vea el drift.
    try:
        user_id = row['user_id']
    except (KeyError, TypeError):
        try:
            user_id = row['id']
            import structlog  # noqa: PLC0415
            structlog.get_logger().warning(
                'me_utils.legacy_row_shape',
                hint=(
                    'Fallback al shape pre-P1-9 (`id` en vez de `user_id`). '
                    'Probable test stub o SQL function out-of-sync. '
                    'Verificar `app.resolve_or_create_user`.'
                ),
            )
        except (KeyError, TypeError):
            import structlog  # noqa: PLC0415
            structlog.get_logger().error(
                'me_utils.row_missing_user_id',
                row_keys=list(row.keys()) if hasattr(row, 'keys') else None,
            )
            return None
    if user_id is None:
        return None

    request.state.user_id = user_id
    return user_id


async def _require_current_user(
    request: Request, conn: asyncpg.Connection,
) -> UUID:
    user_id = await current_user_id_from_request(request, conn)
    if user_id is None:
        raise HTTPException(status_code=401, detail='Authentication required')
    return user_id


async def _load_user_preferences_row(
    conn: asyncpg.Connection, user_id: UUID,
) -> asyncpg.Record:
    """Fetch + lazy-create la fila de `app.user_preferences` del usuario.

    Garantiza que los GET de `/v1/me/*` nunca devuelvan 404 por usuarios
    que jamás llamaron PATCH antes.
    """
    row = await conn.fetchrow(
        'select * from app.user_preferences where user_id=$1', user_id,
    )
    if row is None:
        await conn.execute(
            'insert into app.user_preferences (user_id) values ($1) on conflict do nothing',
            user_id,
        )
        row = await conn.fetchrow(
            'select * from app.user_preferences where user_id=$1', user_id,
        )
    return row


def _session_id_from_request(request: Request) -> str | None:
    """M43 — delega a `app.core.security.derive_session_id` (fuente única).

    Antes este helper duplicaba la lógica de derivación. Drift entre las
    dos copias rompía BUG-199 (revoke check) silenciosamente.
    """
    return derive_session_id(
        jti=getattr(request.state, 'session_jti', None),
        sub=getattr(request.state, 'actor_id', None),
        iat=getattr(request.state, 'token_iat', None),
    )


async def record_auth_session(
    request: Request, conn: asyncpg.Connection, user_id: UUID,
) -> str | None:
    """Upsertea `app.auth_sessions` para la request actual.

    Devuelve el `session_id` registrado para que el handler pueda marcarlo
    como `current` en `GET /v1/me/sessions`. No re-activa sesiones revocadas
    (clause `where revoked_at is null` lo previene). Best-effort sobre
    IP/user_agent.
    """
    session_id = _session_id_from_request(request)
    if not session_id:
        return None
    user_agent = request.headers.get('user-agent') or None
    client = getattr(request, 'client', None)
    client_ip = client.host if client and client.host else None
    await conn.execute(
        '''
        insert into app.auth_sessions (id, user_id, user_agent, ip, last_seen_at)
        values ($1, $2, $3, $4::inet, now())
        on conflict (id) do update set
            user_agent = coalesce(excluded.user_agent, app.auth_sessions.user_agent),
            ip = coalesce(excluded.ip, app.auth_sessions.ip),
            last_seen_at = now()
        where app.auth_sessions.revoked_at is null
        ''',
        session_id, user_id, user_agent, client_ip,
    )
    return session_id
