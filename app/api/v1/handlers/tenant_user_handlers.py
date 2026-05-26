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

    rows = await conn.fetch(
        '''
        select t.id, t.slug, t.legal_name, t.display_name, t.vertical_code,
               t.business_type_label, t.country_code, t.timezone, t.status,
               array_agg(utr.role order by
                   case utr.role
                       when 'owner' then 1
                       when 'admin' then 2
                       when 'manager' then 3
                       when 'agent' then 4
                       when 'viewer' then 5
                       else 6
                   end
               ) as roles,
               bool_or(utr.is_default) as is_default,
               min(utr.created_at) as joined_at
        from app.users u
        join app.user_tenant_roles utr on utr.user_id = u.id
        join app.tenants t on t.id = utr.tenant_id
        where u.auth_subject = $1 and t.deleted_at is null
        group by t.id
        order by bool_or(utr.is_default) desc, min(utr.created_at) asc
        ''',
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
