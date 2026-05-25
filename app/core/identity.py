"""Helpers transversales de identidad — mapeo Auth0 `sub` ↔ `app.users.id`.

Vive en `app.core` porque es **compartido por TODOS los módulos** (chatbot,
influencer, gd, knowledge, etc.). Cualquier módulo que necesite el UUID
interno del usuario (`app.users.id`) en lugar del `sub` del JWT lo
resuelve acá. No duplicar la query en cada módulo.

Diseño:
    `authenticate_request` (en `app.core.security`) setea
    `request.state.actor_id` con el `sub` del JWT Auth0 (string como
    `'google-oauth2|103442...'`). Para hacer JOINs contra tablas que
    referencian `app.users.id` (UUID), hay que resolver el `sub` al UUID
    interno. La query es simple — pero ANTES de este helper estaba
    duplicada en `app/influencer/admin_routes.py:227` y `app/gd/security.py`,
    y los módulos nuevos solían olvidarla → 401 espurios.

Cache: NO cacheamos en memoria. El lookup es O(1) sobre el índice único de
    `app.users.auth_subject` (~1ms). Cachear sería prematura optimización
    y arriesgaría servir el UUID viejo si un user se re-registra con el
    mismo email.

Uso típico desde un handler::

    from app.core.identity import resolve_user_id_from_request

    async def my_handler(request: Request, conn = Depends(get_db)):
        user_id = await resolve_user_id_from_request(request, conn)
        if user_id is None:
            raise HTTPException(401, 'user not registered')
        # ... usa user_id (UUID) para queries que joineen contra app.users
"""
from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import Request


async def resolve_user_id(
    conn: asyncpg.Connection,
    actor_id: str | None,
) -> UUID | None:
    """Mapea Auth0 `sub` → `app.users.id` (UUID interno).

    Args:
        conn: conexión asyncpg activa (típicamente del pool, con RLS
            ya seteado por `get_db`).
        actor_id: el `sub` del JWT (típicamente `request.state.actor_id`).
            Puede ser `None` (request sin auth) → devuelve `None`.

    Returns:
        UUID de `app.users.id` si existe un usuario con ese `auth_subject`;
        `None` si no.
    """
    if not actor_id:
        return None
    row = await conn.fetchrow(
        'select id from app.users where auth_subject = $1',
        str(actor_id),
    )
    return row['id'] if row else None


async def resolve_user_id_from_request(
    request: Request,
    conn: asyncpg.Connection,
) -> UUID | None:
    """Conveniencia: lee `request.state.actor_id` y resuelve el UUID.

    Cachea el resultado en `request.state.user_id` para que llamadas
    subsecuentes en el mismo request (e.g. múltiples deps que necesiten
    el UUID) NO re-consulten.

    Args:
        request: Starlette request. `authenticate_request` debió haber
            seteado `request.state.actor_id` antes.
        conn: conexión asyncpg.

    Returns:
        UUID o `None`.
    """
    cached = getattr(request.state, 'user_id', None)
    if cached is not None:
        return cached
    actor_id = getattr(request.state, 'actor_id', None)
    user_id = await resolve_user_id(conn, actor_id)
    if user_id is not None:
        request.state.user_id = user_id
    return user_id


__all__ = ['resolve_user_id', 'resolve_user_id_from_request']
