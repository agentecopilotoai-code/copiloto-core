"""Handlers `/v1/me/tenants` — listar tenants del usuario autenticado.

Drives el switcher de tenants del admin-panel. Cualquier usuario
autenticado puede llamar este endpoint, independientemente del rol que
tenga en su tenant default (puede tener roles distintos en cada tenant
del que es miembro).

Branch `core`: limpio, sin cross-imports.
"""
from __future__ import annotations

import asyncpg
from fastapi import Depends, HTTPException, Request

from app.api.v1._helpers.me_utils import current_user_id_from_request
from app.api.v1.routes import tenant_user_router
from app.db.pool import get_db, record_to_dict


@tenant_user_router.get('/me/tenants')
async def list_my_tenants(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> list[dict]:
    actor_id = getattr(request.state, 'actor_id', None)
    if not actor_id:
        raise HTTPException(status_code=401, detail='Authentication required')

    # `current_user_id_from_request` lazy-crea la fila en `app.users` si es
    # primer login. Sin esto, el JOIN por auth_subject devuelve vacío y el
    # user aterriza erróneamente en /no-tenant.
    await current_user_id_from_request(request, conn)

    # M68 — usar SECURITY DEFINER function para bypass RLS. La policy
    # `tenants_select` exige `tenant_id = current_tenant_id() OR support_mode`.
    # Un user invitado por primera vez NO tiene `tenant_id` en su JWT
    # (Auth0 lo deriva de app_metadata, vacío hasta que algún proceso
    # lo setee), entonces el JOIN con `app.tenants` filtra TODO →
    # `/me/tenants` retornaba [] aunque la membresía existía en DB.
    # La function `app.list_user_tenants` filtra por `auth_subject` —
    # safe porque el caller (este handler) ya validó el JWT.
    rows = await conn.fetch(
        'select * from app.list_user_tenants($1)',
        actor_id,
    )
    tenants = []
    for row in rows:
        record = record_to_dict(row)
        roles = list(record.get('roles') or [])
        record['roles'] = roles
        # Compat: single-role field con el más alto.
        record['role'] = roles[0] if roles else None
        tenants.append(record)
    return tenants
