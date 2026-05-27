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

    Si el usuario nunca existió en `app.users`, lo crea on-the-fly desde
    los claims (email + display_name). Solo se aplica a `actor_type='user'`
    (no a service tokens ni anónimos).
    """
    cached = getattr(request.state, 'user_id', None)
    if cached is not None:
        return cached

    actor_id = getattr(request.state, 'actor_id', None)
    actor_type = getattr(request.state, 'actor_type', None)
    if not actor_id or actor_type != 'user':
        return None

    # Lookup primero por auth_subject (path normal).
    row = await conn.fetchrow(
        'select id from app.users where auth_subject=$1', actor_id,
    )
    if row is not None:
        request.state.user_id = row['id']
        return row['id']

    # M57 — reconciliación de invitación pendiente.
    #
    # `add_tenant_member` (cuando el invitado no existe en `app.users`)
    # crea una fila placeholder con `auth_subject = 'pending|<sha256(email)>'`.
    # Antes este lookup ignoraba ese placeholder y creaba un user NUEVO
    # al primer login del invitado → quedaba un user huérfano (el pending)
    # con la membresía, y un user real sin membresía con el mismo email.
    #
    # Fix: antes de insert, buscar un pending por email (case-insensitive
    # — `app.users.email` es `citext`). Si existe, UPDATE su `auth_subject`
    # al real → la membresía queda vinculada al user que se acaba de
    # loguear con su identidad Auth0 real.
    email = getattr(request.state, 'email', None) or f'{actor_id}@auth.local'
    display = _user_display_name_from_request(request)
    pending_row = await conn.fetchrow(
        '''
        select id from app.users
        where email = $1 and auth_subject like 'pending|%'
        limit 1
        ''',
        email,
    )
    if pending_row is not None:
        # Reconcilia el pending → adopta el auth_subject real del JWT.
        await conn.execute(
            '''
            update app.users
               set auth_subject = $1,
                   display_name = coalesce(nullif($2, ''), display_name),
                   status = case when status = 'invited' then 'active' else status end,
                   updated_at = now()
             where id = $3
            ''',
            actor_id, display, pending_row['id'],
        )
        request.state.user_id = pending_row['id']
        return pending_row['id']

    # M67 — email match con auth_subject distinto.
    #
    # Caso real observado: `add_tenant_member` invita a `foo@example.com`,
    # Auth0 `users-by-email` devuelve un identity Database (`auth0|abc`),
    # se graba en `app.users.auth_subject`. El invitado se loguea con
    # Google OAuth (mismo email) → Auth0 emite sub distinto
    # (`google-oauth2|xyz`). El INSERT lazy de abajo violaba
    # `users_email_key` (unique on email).
    #
    # Fix: si existe un user con el mismo email pero auth_subject !=
    # actor_id, reconciliamos adoptando el sub del JWT actual. Esto NO
    # introduce vulnerabilidad: el email del JWT ya está validado por
    # `authenticate_request` (A-003 — namespaced claim del access_token).
    #
    # Idealmente Auth0 linkearía las 2 identities (script
    # `account_linking.js` lo hace para verified emails), pero acá
    # cubrimos el caso donde el linking no ocurrió o el invite creó al
    # user antes del linking.
    email_match_row = await conn.fetchrow(
        'select id, auth_subject from app.users where email = $1', email,
    )
    if email_match_row is not None:
        # `auth_subject` distinto al JWT → reconciliar.
        if email_match_row['auth_subject'] != actor_id:
            await conn.execute(
                '''
                update app.users
                   set auth_subject = $1,
                       display_name = coalesce(nullif($2, ''), display_name),
                       status = case when status = 'invited' then 'active' else status end,
                       updated_at = now()
                 where id = $3
                ''',
                actor_id, display, email_match_row['id'],
            )
        request.state.user_id = email_match_row['id']
        return email_match_row['id']

    # No existe ningún user con este email → crear lazy desde claims del JWT.
    row = await conn.fetchrow(
        '''
        insert into app.users (auth_subject, email, display_name)
        values ($1, $2, $3)
        on conflict (auth_subject) do update set
          email = excluded.email
        returning id
        ''',
        actor_id, email, display,
    )
    request.state.user_id = row['id']
    return row['id']


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
