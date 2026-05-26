"""Platform admin handlers — operaciones cross-tenant del platform_owner.

Endpoints expuestos bajo `/v1/platform/*` (todos requieren
`platform_owner` + MFA, gating ya aplicado por el router):

  ─ Tenants:
      GET    /v1/tenants                       — listado con filtros
      POST   /v1/tenants                       — crear (admin lo gestiona)
      GET    /v1/tenants/{id}                  — detalle
      PATCH  /v1/tenants/{id}                  — editar metadata
      PATCH  /v1/tenants/{id}/status           — lifecycle (trial→active→…)

  ─ Membresía de tenants (gestión cross-tenant de usuarios):
      GET    /v1/tenants/{id}/members          — listar miembros del tenant
      POST   /v1/tenants/{id}/members          — agregar miembro con rol
      PATCH  /v1/tenants/{id}/members/{uid}    — cambiar rol del miembro
      DELETE /v1/tenants/{id}/members/{uid}    — revocar membresía

  ─ Observability:
      GET    /v1/platform/metrics/health       — KPIs de salud cross-tenant
      GET    /v1/platform/billing/mrr          — MRR consolidado
      GET    /v1/platform/incidents            — alertas operativas
      GET    /v1/platform/outbound-dlq         — DLQ outbound + reintento
      POST   /v1/platform/outbound-dlq/retry
      GET    /v1/platform/runbooks             — catálogo de runbooks
      GET    /v1/platform/feature-flags        — catálogo
      PATCH  /v1/platform/feature-flags/{key}  — toggle (Fase 2 write)

El listado/admin de tenants se monta bajo `tenant_signup_router` (que ya
exige autenticación) PERO con `require_platform_owner` adicional por
handler.  Más limpio: usar el `platform_admin_router` directamente.
"""
from __future__ import annotations

import json
from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.routes import platform_admin_router
from app.api.v1.schemas import TenantCreate, TenantUpdate
from app.db.pool import get_db, record_to_dict
from app.services import locale as locale_service
from app.services.audit import audit


# ═══════════════════════════════════════════════════════════════════════════
# Tenants CRUD
# ═══════════════════════════════════════════════════════════════════════════


class TenantStatusUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    status: Literal['trial', 'active', 'suspended', 'churned']


class TenantMemberAdd(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    email: str = Field(min_length=3, max_length=320)
    display_name: str | None = Field(default=None, max_length=200)
    role: Literal['owner', 'admin', 'manager', 'agent', 'viewer'] = 'admin'
    is_default: bool = False


class TenantMemberPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    role: Literal['owner', 'admin', 'manager', 'agent', 'viewer'] | None = None
    is_default: bool | None = None


@platform_admin_router.get('/tenants')
async def list_all_tenants(
    status_filter: str | None = Query(default=None, alias='status'),
    country_code: str | None = Query(default=None),
    vertical_code: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Listado cross-tenant para Fleet · Tenants."""
    where = ['t.deleted_at is null']
    params: list = []
    if status_filter:
        params.append(status_filter)
        where.append(f't.status = ${len(params)}')
    if country_code:
        params.append(country_code)
        where.append(f't.country_code = ${len(params)}')
    if vertical_code:
        params.append(vertical_code)
        where.append(f't.vertical_code = ${len(params)}')
    if search:
        params.append(f'%{search.lower()}%')
        where.append(
            f'(lower(t.legal_name) like ${len(params)} '
            f'or lower(t.display_name) like ${len(params)} '
            f'or lower(t.slug::text) like ${len(params)})'
        )
    where_sql = ' and '.join(where)
    params.extend([limit, offset])
    rows = await conn.fetch(
        f'''
        select t.id, t.slug, t.legal_name, t.display_name, t.vertical_code,
               t.business_type_label, t.country_code, t.timezone, t.status,
               t.created_at, t.updated_at,
               (select count(*) from app.user_tenant_roles utr
                where utr.tenant_id = t.id) as member_count,
               (select count(*) from app.tenant_modules tm
                where tm.tenant_id = t.id and tm.enabled = true) as active_modules_count
        from app.tenants t
        where {where_sql}
        order by t.created_at desc
        limit ${len(params) - 1} offset ${len(params)}
        ''',
        *params,
    )
    total = await conn.fetchval(
        f'select count(*) from app.tenants t where {where_sql}',
        *params[:-2],
    )
    return {
        'items': [record_to_dict(r) for r in rows],
        'total': total or 0,
        'limit': limit,
        'offset': offset,
    }


@platform_admin_router.post(
    '/tenants',
    status_code=status.HTTP_201_CREATED,
)
async def create_tenant_for_third_party(
    payload: TenantCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Crea un tenant nuevo (platform_owner administra para tercero).

    A diferencia de `POST /v1/tenant-signup` (self-service), este NO
    asigna automáticamente al caller como owner — el caller es el
    platform_owner y NO debe terminar como miembro del tenant nuevo.
    Para agregar miembros, usar `POST /v1/tenants/{id}/members`.
    """
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

    actor_id = getattr(request.state, 'actor_id', None)
    await audit(
        conn, tenant_id=row['id'], actor_type='user', actor_id=actor_id,
        action='tenant.created_by_platform_owner',
        entity_type='tenant', entity_id=str(row['id']),
        metadata={'slug': payload.slug},
    )
    return record_to_dict(row)


@platform_admin_router.get('/tenants/{tenant_id}')
async def get_tenant(
    tenant_id: UUID,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    row = await conn.fetchrow(
        'select * from app.tenants where id = $1 and deleted_at is null',
        tenant_id,
    )
    if not row:
        raise HTTPException(404, 'tenant_not_found')
    return record_to_dict(row)


@platform_admin_router.patch('/tenants/{tenant_id}')
async def patch_tenant(
    tenant_id: UUID,
    payload: TenantUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    patch = payload.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(400, 'empty_patch')
    sets, params = [], []
    for field in ('slug', 'legal_name', 'display_name', 'vertical_code',
                  'business_type_label', 'country_code', 'timezone'):
        if field in patch:
            params.append(patch[field])
            sets.append(f'{field} = ${len(params)}')
    if not sets:
        raise HTTPException(400, 'no_valid_fields')
    sets.append('updated_at = now()')
    params.append(tenant_id)
    try:
        row = await conn.fetchrow(
            f'update app.tenants set {", ".join(sets)} '
            f'where id = ${len(params)} and deleted_at is null returning *',
            *params,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, {'error': 'slug_taken'})
    if not row:
        raise HTTPException(404, 'tenant_not_found')
    await audit(
        conn, tenant_id=tenant_id, actor_type='user',
        actor_id=getattr(request.state, 'actor_id', None),
        action='tenant.updated_by_platform_owner',
        entity_type='tenant', entity_id=str(tenant_id),
        metadata={'fields': list(patch.keys())},
    )
    return record_to_dict(row)


@platform_admin_router.patch('/tenants/{tenant_id}/status')
async def patch_tenant_status(
    tenant_id: UUID,
    payload: TenantStatusUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    row = await conn.fetchrow(
        '''
        update app.tenants
           set status = $1, updated_at = now()
         where id = $2 and deleted_at is null
        returning id, status
        ''',
        payload.status, tenant_id,
    )
    if not row:
        raise HTTPException(404, 'tenant_not_found')
    await audit(
        conn, tenant_id=tenant_id, actor_type='user',
        actor_id=getattr(request.state, 'actor_id', None),
        action='tenant.status_changed',
        entity_type='tenant', entity_id=str(tenant_id),
        metadata={'new_status': payload.status},
    )
    return {'id': str(row['id']), 'status': row['status']}


# ═══════════════════════════════════════════════════════════════════════════
# Membresía del tenant — gestión de usuarios cross-tenant desde admin
# ═══════════════════════════════════════════════════════════════════════════


@platform_admin_router.get('/tenants/{tenant_id}/members')
async def list_tenant_members(
    tenant_id: UUID,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Listar miembros del tenant + sus roles."""
    rows = await conn.fetch(
        '''
        select u.id as user_id, u.email, u.display_name, u.status as user_status,
               u.mfa_enabled, u.last_login_at,
               array_agg(utr.role order by
                   case utr.role
                       when 'owner' then 1 when 'admin' then 2
                       when 'manager' then 3 when 'agent' then 4
                       when 'viewer' then 5 else 6
                   end
               ) as roles,
               bool_or(utr.is_default) as is_default,
               min(utr.created_at) as joined_at
        from app.users u
        join app.user_tenant_roles utr on utr.user_id = u.id
        where utr.tenant_id = $1
        group by u.id
        order by min(utr.created_at) asc
        ''',
        tenant_id,
    )
    items = []
    for r in rows:
        d = record_to_dict(r)
        d['roles'] = list(d.get('roles') or [])
        items.append(d)
    return {'items': items, 'tenant_id': str(tenant_id)}


@platform_admin_router.post(
    '/tenants/{tenant_id}/members',
    status_code=status.HTTP_201_CREATED,
)
async def add_tenant_member(
    tenant_id: UUID,
    payload: TenantMemberAdd,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Agregar miembro al tenant. Si el email no existe en `app.users` se
    crea una fila pending (auth_subject = `pending|<hash>`); cuando ese
    user loguea por primera vez, `current_user_id_from_request` lo
    reconcilia automáticamente.

    BRANCH `core`: el reclamo pending se hace al primer login del invitado
    (ver `app.api.v1._helpers.me_utils.current_user_id_from_request`).
    """
    # ¿Existe el tenant?
    tenant_exists = await conn.fetchval(
        'select 1 from app.tenants where id = $1 and deleted_at is null',
        tenant_id,
    )
    if not tenant_exists:
        raise HTTPException(404, 'tenant_not_found')

    # Lookup user por email (case-insensitive — `app.users.email` es citext).
    user_row = await conn.fetchrow(
        'select id, email from app.users where email = $1', payload.email,
    )
    if user_row is None:
        # Pending: creamos una fila placeholder. El sub real se llena al
        # primer login Auth0 del invitado.
        import hashlib
        pending_sub = f'pending|{hashlib.sha256(payload.email.encode()).hexdigest()[:32]}'
        user_row = await conn.fetchrow(
            '''
            insert into app.users (auth_subject, email, display_name, status)
            values ($1, $2, $3, 'invited')
            returning id, email
            ''',
            pending_sub, payload.email,
            payload.display_name or payload.email.split('@', 1)[0],
        )

    await conn.execute(
        '''
        insert into app.user_tenant_roles (user_id, tenant_id, role, is_default)
        values ($1, $2, $3, $4)
        on conflict (user_id, tenant_id, role) do update set is_default = excluded.is_default
        ''',
        user_row['id'], tenant_id, payload.role, payload.is_default,
    )

    await audit(
        conn, tenant_id=tenant_id, actor_type='user',
        actor_id=getattr(request.state, 'actor_id', None),
        action='tenant.member_added',
        entity_type='user_tenant_role',
        entity_id=f'{user_row["id"]}:{tenant_id}:{payload.role}',
        metadata={'email': payload.email, 'role': payload.role},
    )
    return {
        'user_id': str(user_row['id']),
        'tenant_id': str(tenant_id),
        'email': str(user_row['email']),
        'role': payload.role,
        'is_default': payload.is_default,
    }


@platform_admin_router.patch('/tenants/{tenant_id}/members/{user_id}')
async def patch_tenant_member(
    tenant_id: UUID,
    user_id: UUID,
    payload: TenantMemberPatch,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Cambiar rol o is_default. Cambio de rol = DELETE viejo + INSERT nuevo
    (la PK incluye `role`). Esto preserva audit trail."""
    existing = await conn.fetch(
        'select role, is_default from app.user_tenant_roles '
        'where user_id = $1 and tenant_id = $2',
        user_id, tenant_id,
    )
    if not existing:
        raise HTTPException(404, 'membership_not_found')

    if payload.role is not None:
        # Replace todos los roles del user en este tenant por el nuevo único.
        await conn.execute(
            'delete from app.user_tenant_roles where user_id = $1 and tenant_id = $2',
            user_id, tenant_id,
        )
        await conn.execute(
            '''
            insert into app.user_tenant_roles (user_id, tenant_id, role, is_default)
            values ($1, $2, $3, $4)
            ''',
            user_id, tenant_id, payload.role,
            payload.is_default if payload.is_default is not None else existing[0]['is_default'],
        )
        new_role = payload.role
    elif payload.is_default is not None:
        await conn.execute(
            'update app.user_tenant_roles set is_default = $1 '
            'where user_id = $2 and tenant_id = $3',
            payload.is_default, user_id, tenant_id,
        )
        new_role = existing[0]['role']
    else:
        raise HTTPException(400, 'empty_patch')

    await audit(
        conn, tenant_id=tenant_id, actor_type='user',
        actor_id=getattr(request.state, 'actor_id', None),
        action='tenant.member_updated',
        entity_type='user_tenant_role',
        entity_id=f'{user_id}:{tenant_id}',
        metadata=payload.model_dump(exclude_none=True),
    )
    return {
        'user_id': str(user_id),
        'tenant_id': str(tenant_id),
        'role': new_role,
        'is_default': payload.is_default if payload.is_default is not None else existing[0]['is_default'],
    }


@platform_admin_router.delete(
    '/tenants/{tenant_id}/members/{user_id}',
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def remove_tenant_member(
    tenant_id: UUID,
    user_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> None:
    result = await conn.execute(
        'delete from app.user_tenant_roles where user_id = $1 and tenant_id = $2',
        user_id, tenant_id,
    )
    if result.endswith(' 0'):
        raise HTTPException(404, 'membership_not_found')
    await audit(
        conn, tenant_id=tenant_id, actor_type='user',
        actor_id=getattr(request.state, 'actor_id', None),
        action='tenant.member_removed',
        entity_type='user_tenant_role',
        entity_id=f'{user_id}:{tenant_id}',
    )


# ═══════════════════════════════════════════════════════════════════════════
# Observability (health, billing, incidents, dlq, runbooks)
# ═══════════════════════════════════════════════════════════════════════════


@platform_admin_router.get('/platform/metrics/health')
async def get_platform_health() -> dict:
    """KPIs básicos del sistema — placeholder mínimo.

    Los módulos opt-in pueden enriquecer estos KPIs cuando se instalan.
    """
    return {
        'status': 'ok',
        'services': {
            'api': 'healthy',
            'db': 'healthy',
            'auth0': 'healthy',
        },
        'note': 'Core base. Productos agregan métricas específicas.',
    }


@platform_admin_router.get('/platform/billing/mrr')
async def get_billing_mrr() -> dict:
    """MRR consolidado. Placeholder — el módulo de billing agregará lógica
    real (lookup en app.subscriptions, conversión de moneda, etc.)."""
    return {'mrr_total_usd': 0, 'by_currency': [], 'by_plan': [], 'churn_30d_pct': 0}


@platform_admin_router.get('/platform/incidents')
async def list_platform_incidents(
    status_filter: str | None = Query(default=None, alias='status'),
    limit: int = Query(default=50, ge=1, le=200),
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    """Lista de operator_alerts (incidents cross-tenant)."""
    where = ['1=1']
    params: list = []
    if status_filter:
        params.append(status_filter)
        where.append(f'oa.status = ${len(params)}')
    params.append(limit)
    rows = await conn.fetch(
        f'''
        select oa.id, oa.tenant_id, t.slug as tenant_slug, t.display_name as tenant_name,
               oa.kind, oa.payload, oa.status, oa.attempts, oa.last_error,
               oa.scheduled_for, oa.created_at, oa.sent_at
        from app.operator_alerts oa
        left join app.tenants t on t.id = oa.tenant_id
        where {' and '.join(where)}
        order by oa.created_at desc
        limit ${len(params)}
        ''',
        *params,
    )
    return {'items': [record_to_dict(r) for r in rows]}


@platform_admin_router.get('/platform/outbound-dlq')
async def list_outbound_dlq() -> dict:
    """DLQ outbound — placeholder. Los módulos opt-in que emiten mensajes
    salientes agregan la lógica real (lookup en su tabla de mensajes con
    status='failed'), agrupada por tenant."""
    return {'items': [], 'total': 0, 'note': 'Módulos opt-in agregan lógica.'}


@platform_admin_router.post('/platform/outbound-dlq/retry')
async def retry_outbound_dlq() -> dict:
    """Trigger de reintento masivo. Placeholder — los módulos opt-in lo
    implementan."""
    return {'queued': 0, 'note': 'Módulos opt-in agregan lógica.'}


@platform_admin_router.get('/platform/runbooks')
async def list_runbooks() -> dict:
    """Catálogo de runbooks. Por ahora estático.

    TODO Fase 3: leer desde `docs/runbooks/` o desde una tabla
    `app.runbooks` (key + content_md + category)."""
    return {
        'items': [
            {'key': 'auth0-mfa-error', 'title': 'Auth0 MFA error',
             'category': 'auth', 'summary': 'Diagnóstico de errores MFA.'},
            {'key': 'backup-signature-setup', 'title': 'Backup signature setup',
             'category': 'backups', 'summary': 'Configurar firma GPG de backups.'},
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# Feature flags CRUD (Fase 2 write)
# ═══════════════════════════════════════════════════════════════════════════


class FeatureFlagPatch(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool | None = None
    rollout_pct: int | None = Field(default=None, ge=0, le=100)
    description: str | None = Field(default=None, max_length=2000)
    metadata: dict | None = None


class FeatureFlagCreate(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    key: str = Field(min_length=1, max_length=200, pattern=r'^[a-z][a-z0-9_\.]*$')
    description: str | None = Field(default=None, max_length=2000)
    enabled: bool = False
    rollout_pct: int = Field(default=0, ge=0, le=100)
    metadata: dict = Field(default_factory=dict)


@platform_admin_router.get('/platform/feature-flags')
async def list_feature_flags(
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    rows = await conn.fetch(
        'select key, description, enabled, rollout_pct, metadata, created_at, updated_at '
        'from app.feature_flags order by key'
    )
    return {'items': [record_to_dict(r) for r in rows]}


@platform_admin_router.post(
    '/platform/feature-flags',
    status_code=status.HTTP_201_CREATED,
)
async def create_feature_flag(
    payload: FeatureFlagCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    try:
        row = await conn.fetchrow(
            '''
            insert into app.feature_flags (key, description, enabled, rollout_pct, metadata)
            values ($1, $2, $3, $4, $5::jsonb)
            returning *
            ''',
            payload.key, payload.description, payload.enabled,
            payload.rollout_pct, json.dumps(payload.metadata),
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, {'error': 'key_taken'})
    await audit(
        conn, tenant_id=None, actor_type='user',
        actor_id=getattr(request.state, 'actor_id', None),
        action='platform.feature_flag.created',
        entity_type='feature_flag', entity_id=payload.key,
    )
    return record_to_dict(row)


@platform_admin_router.patch('/platform/feature-flags/{key}')
async def patch_feature_flag(
    key: str,
    payload: FeatureFlagPatch,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict:
    patch = payload.model_dump(exclude_none=True)
    if not patch:
        raise HTTPException(400, 'empty_patch')
    sets, params = [], []
    for field in ('enabled', 'rollout_pct', 'description'):
        if field in patch:
            params.append(patch[field])
            sets.append(f'{field} = ${len(params)}')
    if 'metadata' in patch:
        params.append(json.dumps(patch['metadata']))
        sets.append(f'metadata = ${len(params)}::jsonb')
    sets.append('updated_at = now()')
    params.append(key)
    row = await conn.fetchrow(
        f'update app.feature_flags set {", ".join(sets)} '
        f'where key = ${len(params)} returning *',
        *params,
    )
    if not row:
        raise HTTPException(404, 'flag_not_found')
    await audit(
        conn, tenant_id=None, actor_type='user',
        actor_id=getattr(request.state, 'actor_id', None),
        action='platform.feature_flag.updated',
        entity_type='feature_flag', entity_id=key,
        metadata=patch,
    )
    return record_to_dict(row)


@platform_admin_router.delete(
    '/platform/feature-flags/{key}',
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_feature_flag(
    key: str,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> None:
    result = await conn.execute(
        'delete from app.feature_flags where key = $1', key,
    )
    if result.endswith(' 0'):
        raise HTTPException(404, 'flag_not_found')
    await audit(
        conn, tenant_id=None, actor_type='user',
        actor_id=getattr(request.state, 'actor_id', None),
        action='platform.feature_flag.deleted',
        entity_type='feature_flag', entity_id=key,
    )
