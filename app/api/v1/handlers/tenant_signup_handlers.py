"""Handlers extracted from routes.py for tenant_signup_router.

Original location: app/api/v1/routes.py (refactor step 3).
"""
from __future__ import annotations

import asyncpg
from fastapi import Depends, HTTPException, Request, status

from app.api.v1.routes import (
    tenant_signup_router,
    user_display_name_from_request,
    user_email_from_request,
)
from app.api.v1.schemas import TenantCreate
from app.db.pool import get_db, record_to_dict
from app.services import locale as locale_service
from app.services.audit import audit
from app.services.retention import seed_default_retention_policies
from app.services.segments import seed_preconstructed_segments


@tenant_signup_router.post('/tenant-signup', status_code=status.HTTP_201_CREATED)
async def create_own_tenant(
    payload: TenantCreate, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    actor_id = getattr(request.state, 'actor_id', None)
    if not actor_id:
        raise HTTPException(status_code=401, detail='Authentication required')
    # TASK-0077/BUG24: callers that already belong to a tenant must NOT be
    # able to hijack that tenant's profile via the unauthenticated-shape
    # tenant-signup flow.  Self-service signup is reserved for users with no
    # membership yet.  Existing members manage their tenant through the
    # tenant-admin endpoints (which enforce JWT+DB role checks).
    existing_tenant_id = await conn.fetchval(
        """
        select utr.tenant_id
        from app.users u
        join app.user_tenant_roles utr on utr.user_id = u.id
        where u.auth_subject=$1
        order by utr.created_at asc
        limit 1
        """,
        actor_id,
    )
    if existing_tenant_id:
        raise HTTPException(
            status_code=409,
            detail='Actor already belongs to a tenant; use the tenant admin endpoints to update it.',
        )

    # TASK-0073: en el self-service también derivamos tz/locale/currency del país.
    profile = locale_service.profile_for(payload.country_code)
    tz_value = payload.timezone or profile['timezone']
    row = await conn.fetchrow(
        """
        insert into app.tenants (slug, legal_name, display_name, vertical_code, business_type_label, country_code, timezone)
        values ($1, $2, $3, $4, $5, $6, $7)
        returning *
        """,
        payload.slug,
        payload.legal_name,
        payload.display_name,
        payload.vertical_code,
        payload.business_type_label,
        payload.country_code,
        tz_value,
    )
    tenant_id = row['id']
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    await conn.execute(
        'insert into app.tenant_settings (tenant_id, locale, currency) values ($1, $2, $3)',
        tenant_id,
        profile['locale'],
        profile['currency'],
    )
    user_row = await conn.fetchrow(
        """
        insert into app.users (auth_subject, email, display_name, last_login_at)
        values ($1, $2, $3, now())
        on conflict (auth_subject) do update set
          email=excluded.email,
          display_name=excluded.display_name,
          last_login_at=now(),
          updated_at=now()
        returning id
        """,
        actor_id,
        user_email_from_request(request),
        user_display_name_from_request(request),
    )
    await conn.execute(
        """
        insert into app.user_tenant_roles (user_id, tenant_id, role, is_default)
        values ($1, $2, 'owner', true)
        on conflict (user_id, tenant_id, role) do update set is_default=true
        """,
        user_row['id'],
        tenant_id,
    )
    await seed_preconstructed_segments(conn, tenant_id, created_by=user_row['id'])
    await seed_default_retention_policies(conn, tenant_id)
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant.self_service_created',
        entity_type='tenant',
        entity_id=str(tenant_id),
    )
    response = record_to_dict(row)
    response['user_role'] = 'owner'
    # BUG-007 fix: el frontend (TenantProvider.handleTenantCreated +
    # resolveActiveRoles) lee `tenant.roles` o `tenant.role` para inferir
    # los permisos del caller. Antes del fix, este endpoint solo devolvía
    # `user_role` (singular, naming distinto), así que al agregar el
    # tenant recién creado a `tenantOptions` no se propagaba el rol y el
    # caller aterrizaba en "Sin acceso a ningún módulo" hasta que el
    # siguiente `GET /v1/me/tenants` traía la info correcta. Devolver
    # también `roles: ['owner']` matchea exactamente el shape de
    # `/v1/me/tenants` y permite uso inmediato. `user_role` se mantiene
    # por back-compat con consumers viejos.
    response['roles'] = ['owner']
    return response
