"""CRUD de Roles & Capabilities del core (Fase 2).

Endpoints `/v1/platform/roles/*` y `/v1/platform/capabilities/*` para que
el platform_owner pueda:
  - Listar todos los roles (sistema + custom).
  - Crear roles custom.
  - Editar metadata (nombre, descripción, activo).
  - Listar todas las capabilities + filtrar por grupo.
  - Asignar/revocar capability ↔ role con access_level.

Reglas:
  - `is_system=true` → no se puede borrar, solo desactivar.
  - El catálogo es **platform-scope**: una sola matriz para toda la
    plataforma. Los handlers exigen `require_platform_owner` (igual que
    el resto de `platform_admin_router`).
  - Cambios audit-logged en `app.audit_logs`.

Fuente de verdad: `app.role`, `app.capability`, `app.role_capability`
(seed inicial en `infra/postgres/10-core.sql`).
"""
from __future__ import annotations

from typing import Literal

import asyncpg
from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.api.v1.routes import platform_admin_router
from app.db.pool import get_db
from app.services.audit import audit


# ─── Schemas ────────────────────────────────────────────────────────────────


class RoleRow(BaseModel):
    code: str
    name: str
    description: str | None = None
    is_system: bool
    is_active: bool
    capability_count: int = 0


class RoleListResponse(BaseModel):
    items: list[RoleRow]


class RoleCreateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    code: str = Field(min_length=1, max_length=80, pattern=r'^[a-z][a-z0-9_]*$')
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class RolePatchRequest(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True, extra='forbid')

    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class CapabilityRow(BaseModel):
    code: str
    name: str
    description: str | None = None
    group_label: str | None = None
    is_system: bool
    is_active: bool


class CapabilityListResponse(BaseModel):
    items: list[CapabilityRow]


class CapabilityCreateRequest(BaseModel):
    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    code: str = Field(min_length=1, max_length=200, pattern=r'^[a-z][a-z0-9_\.]*$')
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    group_label: str | None = Field(default=None, max_length=200)


class RoleCapabilityAssignRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    access_level: Literal['RW', 'R', 'partial', 'own_only']


class RoleCapabilityRow(BaseModel):
    role_code: str
    capability_code: str
    access_level: str


class RoleCapabilityListResponse(BaseModel):
    items: list[RoleCapabilityRow]


# ─── Roles ──────────────────────────────────────────────────────────────────


@platform_admin_router.get('/platform/roles', response_model=RoleListResponse)
async def list_roles(
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RoleListResponse:
    rows = await conn.fetch(
        '''
        select r.code, r.name, r.description, r.is_system, r.is_active,
               coalesce((select count(*) from app.role_capability rc
                         where rc.role_code = r.code), 0) as capability_count
        from app.role r
        order by r.is_system desc, r.code
        '''
    )
    return RoleListResponse(items=[RoleRow(**dict(r)) for r in rows])


@platform_admin_router.post(
    '/platform/roles',
    response_model=RoleRow,
    status_code=status.HTTP_201_CREATED,
)
async def create_role(
    body: RoleCreateRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RoleRow:
    actor_id = getattr(request.state, 'actor_id', None)
    try:
        row = await conn.fetchrow(
            '''
            insert into app.role (code, name, description, is_system, is_active)
            values ($1, $2, $3, false, true)
            returning code, name, description, is_system, is_active
            ''',
            body.code, body.name, body.description,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, {'error': 'conflict', 'code': 'role_code_duplicado'})

    await audit(
        conn, tenant_id=None, actor_type='user',
        actor_id=str(actor_id) if actor_id else None,
        action='platform.role.created',
        entity_type='role', entity_id=body.code,
        metadata={'name': body.name},
    )
    return RoleRow(**dict(row), capability_count=0)


@platform_admin_router.patch('/platform/roles/{role_code}', response_model=RoleRow)
async def patch_role(
    role_code: str,
    body: RolePatchRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RoleRow:
    actor_id = getattr(request.state, 'actor_id', None)
    sets = []
    params: list = []
    if body.name is not None:
        params.append(body.name); sets.append(f'name = ${len(params)}')
    if body.description is not None:
        params.append(body.description); sets.append(f'description = ${len(params)}')
    if body.is_active is not None:
        params.append(body.is_active); sets.append(f'is_active = ${len(params)}')
    if not sets:
        raise HTTPException(400, {'error': 'empty_patch'})
    sets.append(f'updated_at = now()')
    params.append(role_code)
    sql = (
        f'update app.role set {", ".join(sets)} '
        f'where code = ${len(params)} '
        f'returning code, name, description, is_system, is_active'
    )
    row = await conn.fetchrow(sql, *params)
    if not row:
        raise HTTPException(404, {'error': 'not_found'})

    count = await conn.fetchval(
        'select count(*) from app.role_capability where role_code = $1',
        role_code,
    )
    await audit(
        conn, tenant_id=None, actor_type='user',
        actor_id=str(actor_id) if actor_id else None,
        action='platform.role.updated',
        entity_type='role', entity_id=role_code,
        metadata={k: v for k, v in body.model_dump(exclude_none=True).items()},
    )
    return RoleRow(**dict(row), capability_count=count or 0)


@platform_admin_router.delete(
    '/platform/roles/{role_code}',
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,  # 204 no debe declarar response model.
)
async def delete_role(
    role_code: str,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> None:
    actor_id = getattr(request.state, 'actor_id', None)
    row = await conn.fetchrow(
        'select is_system from app.role where code = $1', role_code,
    )
    if not row:
        raise HTTPException(404, {'error': 'not_found'})
    if row['is_system']:
        raise HTTPException(
            409,
            {'error': 'conflict', 'code': 'role_is_system',
             'message': 'Los roles del sistema no se pueden borrar. Desactívalo en su lugar.'},
        )
    await conn.execute('delete from app.role where code = $1', role_code)
    await audit(
        conn, tenant_id=None, actor_type='user',
        actor_id=str(actor_id) if actor_id else None,
        action='platform.role.deleted',
        entity_type='role', entity_id=role_code,
    )


# ─── Capabilities ───────────────────────────────────────────────────────────


@platform_admin_router.get('/platform/capabilities', response_model=CapabilityListResponse)
async def list_capabilities(
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CapabilityListResponse:
    rows = await conn.fetch(
        '''
        select code, name, description, group_label, is_system, is_active
        from app.capability
        order by group_label nulls last, code
        '''
    )
    return CapabilityListResponse(items=[CapabilityRow(**dict(r)) for r in rows])


@platform_admin_router.post(
    '/platform/capabilities',
    response_model=CapabilityRow,
    status_code=status.HTTP_201_CREATED,
)
async def create_capability(
    body: CapabilityCreateRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CapabilityRow:
    actor_id = getattr(request.state, 'actor_id', None)
    try:
        row = await conn.fetchrow(
            '''
            insert into app.capability (code, name, description, group_label, is_system, is_active)
            values ($1, $2, $3, $4, false, true)
            returning code, name, description, group_label, is_system, is_active
            ''',
            body.code, body.name, body.description, body.group_label,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, {'error': 'conflict', 'code': 'capability_code_duplicado'})

    await audit(
        conn, tenant_id=None, actor_type='user',
        actor_id=str(actor_id) if actor_id else None,
        action='platform.capability.created',
        entity_type='capability', entity_id=body.code,
        metadata={'name': body.name, 'group': body.group_label},
    )
    return CapabilityRow(**dict(row))


# ─── Role × Capability (asignación) ─────────────────────────────────────────


@platform_admin_router.get(
    '/platform/roles/{role_code}/capabilities',
    response_model=RoleCapabilityListResponse,
)
async def list_role_capabilities(
    role_code: str,
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RoleCapabilityListResponse:
    rows = await conn.fetch(
        '''
        select role_code, capability_code, access_level
        from app.role_capability
        where role_code = $1
        order by capability_code
        ''',
        role_code,
    )
    return RoleCapabilityListResponse(
        items=[RoleCapabilityRow(**dict(r)) for r in rows],
    )


@platform_admin_router.put(
    '/platform/roles/{role_code}/capabilities/{capability_code}',
    response_model=RoleCapabilityRow,
    status_code=status.HTTP_200_OK,
)
async def assign_capability_to_role(
    role_code: str,
    capability_code: str,
    body: RoleCapabilityAssignRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RoleCapabilityRow:
    actor_id = getattr(request.state, 'actor_id', None)
    # Verifica que ambos existan (FK lo haría también, pero damos mejor error).
    role_exists = await conn.fetchval('select 1 from app.role where code = $1', role_code)
    if not role_exists:
        raise HTTPException(404, {'error': 'role_not_found', 'role_code': role_code})
    cap_exists = await conn.fetchval('select 1 from app.capability where code = $1', capability_code)
    if not cap_exists:
        raise HTTPException(404, {'error': 'capability_not_found', 'capability_code': capability_code})

    await conn.execute(
        '''
        insert into app.role_capability (role_code, capability_code, access_level, granted_by)
        values ($1, $2, $3, $4)
        on conflict (role_code, capability_code) do update
          set access_level = excluded.access_level,
              granted_at = now(),
              granted_by = excluded.granted_by
        ''',
        role_code, capability_code, body.access_level,
        actor_id if actor_id else None,
    )
    await audit(
        conn, tenant_id=None, actor_type='user',
        actor_id=str(actor_id) if actor_id else None,
        action='platform.role_capability.assigned',
        entity_type='role_capability', entity_id=f'{role_code}:{capability_code}',
        metadata={'access_level': body.access_level},
    )
    return RoleCapabilityRow(
        role_code=role_code, capability_code=capability_code,
        access_level=body.access_level,
    )


@platform_admin_router.delete(
    '/platform/roles/{role_code}/capabilities/{capability_code}',
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def revoke_capability_from_role(
    role_code: str,
    capability_code: str,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> None:
    actor_id = getattr(request.state, 'actor_id', None)
    result = await conn.execute(
        'delete from app.role_capability where role_code = $1 and capability_code = $2',
        role_code, capability_code,
    )
    # `result` es algo como "DELETE 1" o "DELETE 0".
    if result.endswith(' 0'):
        raise HTTPException(404, {'error': 'not_found'})
    await audit(
        conn, tenant_id=None, actor_type='user',
        actor_id=str(actor_id) if actor_id else None,
        action='platform.role_capability.revoked',
        entity_type='role_capability', entity_id=f'{role_code}:{capability_code}',
    )
