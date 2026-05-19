"""Handlers extracted from routes.py for tenant_user_router.

Original location: app/api/v1/routes.py (refactor step 3).
"""
from __future__ import annotations

import asyncpg
from fastapi import Depends, HTTPException, Request

from app.api.v1.routes import (
    current_user_id_from_request,
    tenant_user_router,
)
from app.db.pool import get_db, record_to_dict


@tenant_user_router.get('/me/tenants')
async def list_my_tenants(request: Request, conn: asyncpg.Connection = Depends(get_db)):
    """Return every tenant the authenticated user belongs to with their role.

    Drives the Slack-style tenant switcher in the Admin Panel.  Any
    authenticated user can hit this regardless of which role they hold in
    their current tenant, because they may have a different role in a
    different tenant.
    """
    actor_id = getattr(request.state, 'actor_id', None)
    if not actor_id:
        raise HTTPException(status_code=401, detail='Authentication required')
    # BUG-022: este endpoint es típicamente el primer hit del invitado al
    # loguearse (lo invoca el switcher de tenants del admin-panel ANTES de
    # decidir si mandarlo a `/admin/no-tenant`). Llamar a
    # `current_user_id_from_request` asegura que cualquier fila pendiente
    # (`auth_subject = 'pending|<hex>'`) creada por `invite_tenant_member`
    # quede vinculada al `sub` real de Auth0 ANTES de la query — sin esto,
    # el JOIN por `auth_subject` devuelve vacío y el invitado aterriza
    # erróneamente en la pantalla "sin tenant".
    await current_user_id_from_request(request, conn)
    rows = await conn.fetch(
        """
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
        where u.auth_subject=$1 and t.deleted_at is null
        group by t.id
        order by bool_or(utr.is_default) desc, min(utr.created_at) asc
        """,
        actor_id,
    )
    tenants = []
    for row in rows:
        record = record_to_dict(row)
        roles = list(record.get('roles') or [])
        record['roles'] = roles
        # Keep backwards-compatible single role field (highest role wins).
        record['role'] = roles[0] if roles else None
        tenants.append(record)
    return tenants
