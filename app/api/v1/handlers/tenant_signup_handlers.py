"""Handler `POST /v1/tenant-signup` — self-service de creación de tenant.

Usado por el wizard `/onboarding` del admin-panel cuando un usuario
autenticado todavía no pertenece a ningún tenant. El handler:
  1. Verifica que el caller NO tenga membresía previa (sin esto se podría
     "secuestrar" el perfil de otro tenant via el shape unauthenticated).
  2. Crea el tenant.
  3. Crea/upsertea la fila de `app.users` desde los claims del JWT.
  4. Asigna `owner` al caller para el tenant nuevo.
  5. Audit-loggea `tenant.self_service_created`.

Diferencia con `POST /v1/tenants` (platform_admin_handlers): este
endpoint es para AUTO-CREAR el propio tenant; el otro es para que el
platform_owner cree tenants para terceros desde Fleet.

Branch `core`: solo crea la fila en `app.tenants` + asigna `owner` al
caller. Los módulos opt-in agregan sus propios seeds cuando se activan
en el tenant.
"""
from __future__ import annotations

import asyncpg
from fastapi import Depends, HTTPException, Request, status

from app.api.v1._helpers.me_utils import _user_display_name_from_request
from app.api.v1.routes import tenant_signup_router
from app.api.v1.schemas import TenantCreate
from app.db.pool import get_db, record_to_dict
from app.services import locale as locale_service
from app.services.audit import audit


@tenant_signup_router.post('/tenant-signup', status_code=status.HTTP_201_CREATED)
async def create_own_tenant(
    payload: TenantCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    actor_id = getattr(request.state, 'actor_id', None)
    if not actor_id:
        raise HTTPException(status_code=401, detail='Authentication required')

    # TASK-0077: usuarios que ya pertenecen a un tenant NO pueden usar
    # self-service. Para crear tenants para terceros, usar
    # POST /v1/platform/tenants (require platform_owner).
    existing = await conn.fetchval(
        '''
        select utr.tenant_id
        from app.users u
        join app.user_tenant_roles utr on utr.user_id = u.id
        where u.auth_subject = $1
        order by utr.created_at asc
        limit 1
        ''',
        actor_id,
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail='Actor already belongs to a tenant; use the platform admin endpoints.',
        )

    # TASK-0073: derivar timezone del país si no viene explícito.
    try:
        profile = locale_service.profile_for(payload.country_code)
        tz_value = payload.timezone or profile['timezone']
    except (KeyError, AttributeError):
        tz_value = payload.timezone or 'America/Bogota'

    try:
        row = await conn.fetchrow(
            '''
            insert into app.tenants
              (slug, legal_name, display_name, vertical_code,
               business_type_label, country_code, timezone)
            values ($1, $2, $3, $4, $5, $6, $7)
            returning *
            ''',
            payload.slug, payload.legal_name, payload.display_name,
            payload.vertical_code, payload.business_type_label,
            payload.country_code, tz_value,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail={'error': 'slug_taken'})

    tenant_id = row['id']
    await conn.execute(
        "select set_config('app.tenant_id', $1, true)", str(tenant_id),
    )

    # Lazy-upsert del user en app.users desde los claims del JWT.
    email = getattr(request.state, 'email', None) or f'{actor_id}@auth.local'
    display = _user_display_name_from_request(request)
    user_row = await conn.fetchrow(
        '''
        insert into app.users (auth_subject, email, display_name, last_login_at)
        values ($1, $2, $3, now())
        on conflict (auth_subject) do update set
          email = excluded.email,
          display_name = excluded.display_name,
          last_login_at = now(),
          updated_at = now()
        returning id
        ''',
        actor_id, email, display,
    )

    # Asignar owner al caller.
    await conn.execute(
        '''
        insert into app.user_tenant_roles (user_id, tenant_id, role, is_default)
        values ($1, $2, 'owner', true)
        on conflict (user_id, tenant_id, role) do update set is_default = true
        ''',
        user_row['id'], tenant_id,
    )

    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type='user',
        actor_id=actor_id,
        action='tenant.self_service_created',
        entity_type='tenant',
        entity_id=str(tenant_id),
    )

    # BUG-007: el frontend lee `tenant.roles` o `tenant.role` para inferir
    # los permisos. Devolvemos ambos para no romper consumidores que usen
    # cualquiera de los dos.
    response = record_to_dict(row)
    response['user_role'] = 'owner'
    response['role'] = 'owner'
    response['roles'] = ['owner']
    response['is_default'] = True
    return response
