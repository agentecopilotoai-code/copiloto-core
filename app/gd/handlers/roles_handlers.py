"""GD-API-0004 — CRUD de roles GD + matriz rol↔permiso.

POST/GET/PATCH /api/v1/gd/roles + POST inactivar + POST/DELETE permisos + GET /permisos.
"""
from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, status

from app.db.pool import get_db
from app.gd.schemas.roles import (
    PermisoListResponse,
    PermisoResponse,
    RolCreate,
    RolInactivarRequest,
    RolListResponse,
    RolPatch,
    RolPermisoAddRequest,
    RolPermisoResponse,
    RolResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil, require_gd_permission
from app.gd.services import roles as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router = APIRouter(tags=['gd:roles'])


@router.get(
    '/roles',
    response_model=RolListResponse,
    dependencies=[Depends(require_gd_permission('PERM-ROL-001', alcance='institucional'))],
)
async def listar_roles(
    estado: str | None = Query(default=None),
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RolListResponse:
    rows = await svc.listar_roles(conn, estado=estado)
    return RolListResponse(items=[RolResponse(**r) for r in rows])


@router.post(
    '/roles',
    response_model=RolResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_permission('PERM-ROL-002', alcance='institucional'))],
)
async def crear_rol(
    body: RolCreate,
    request: Request,
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RolResponse:
    row = await svc.crear_rol(
        conn, codigo=body.codigo, nombre=body.nombre, descripcion=body.descripcion
    )
    if row is None:
        raise HTTPException(
            status_code=409,
            detail={
                'error': 'conflict',
                'code': 'rol_codigo_reservado',
                'message': f'El código {body.codigo!r} ya existe o está reservado.',
            },
        )

    await emit_gd_event(
        conn,
        tipo_evento='gd.rol.creado',
        accion='crear',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='rol',
        entidad_afectada_identificador=body.codigo,
        valor_nuevo={'nombre': body.nombre, 'es_sistema': False},
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return RolResponse(**row)


@router.patch(
    '/roles/{codigo}',
    response_model=RolResponse,
    dependencies=[Depends(require_gd_permission('PERM-ROL-006', alcance='institucional'))],
)
async def patch_rol(
    body: RolPatch,
    request: Request,
    codigo: str = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RolResponse:
    cambios = body.model_dump(exclude_unset=True)
    row = await svc.actualizar_rol(conn, codigo=codigo, cambios=cambios)
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    if cambios:
        await emit_gd_event(
            conn,
            tipo_evento='gd.rol.modificado',
            accion='actualizar',
            tenant_id=perfil_actor.tenant_id,
            usuario_id=perfil_actor.user_id,
            entidad_afectada_tipo='rol',
            entidad_afectada_identificador=codigo,
            valor_nuevo=cambios,
            criticidad=AuditCriticidad.MEDIA,
            request_id=getattr(request.state, 'request_id', None),
        )
    return RolResponse(**row)


@router.post(
    '/roles/{codigo}/inactivar',
    response_model=RolResponse,
    dependencies=[Depends(require_gd_permission('PERM-ROL-005', alcance='institucional'))],
)
async def inactivar_rol(
    body: RolInactivarRequest,
    request: Request,
    codigo: str = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RolResponse:
    # Verificar no haya asignaciones activas (D9: solo asignacion_alcance).
    activas = await svc.contar_asignaciones_activas(conn, rol_codigo=codigo)
    if activas > 0:
        raise HTTPException(
            status_code=409,
            detail={
                'error': 'conflict',
                'code': 'role_in_use',
                'message': f'El rol está asignado a {activas} usuarios activos.',
                'detalles': {'asignaciones_activas': activas},
            },
        )
    row = await svc.inactivar_rol(conn, codigo=codigo)
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn,
        tipo_evento='gd.rol.inactivado',
        accion='inactivar',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='rol',
        entidad_afectada_identificador=codigo,
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return RolResponse(**row)


@router.post(
    '/roles/{codigo}/permisos',
    response_model=RolPermisoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_permission('PERM-ROL-003', alcance='institucional'))],
)
async def agregar_permiso_a_rol(
    body: RolPermisoAddRequest,
    request: Request,
    codigo: str = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RolPermisoResponse:
    try:
        row = await svc.agregar_permiso_a_rol(
            conn,
            rol_codigo=codigo,
            permiso_codigo=body.permiso_codigo,
            alcance_default=body.alcance_default,
        )
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(
            status_code=404,
            detail={
                'error': 'not_found',
                'message': f'rol {codigo!r} o permiso {body.permiso_codigo!r} no existe.',
            },
        )
    if row is None:
        raise HTTPException(
            status_code=409,
            detail={'error': 'conflict', 'code': 'permiso_ya_asignado'},
        )

    await emit_gd_event(
        conn,
        tipo_evento='gd.rol_permiso.modificado',
        accion='agregar_permiso',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='rol',
        entidad_afectada_identificador=codigo,
        valor_nuevo={
            'permiso_codigo': body.permiso_codigo,
            'alcance_default': body.alcance_default,
        },
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return RolPermisoResponse(**row)


@router.delete(
    '/roles/{codigo}/permisos/{permiso_codigo}',
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    dependencies=[Depends(require_gd_permission('PERM-ROL-004', alcance='institucional'))],
)
async def quitar_permiso_de_rol(
    request: Request,
    codigo: str = Path(...),
    permiso_codigo: str = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> Response:
    encontrado = await svc.quitar_permiso_de_rol(
        conn, rol_codigo=codigo, permiso_codigo=permiso_codigo
    )
    if not encontrado:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn,
        tipo_evento='gd.rol_permiso.modificado',
        accion='quitar_permiso',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='rol',
        entidad_afectada_identificador=codigo,
        valor_anterior={'permiso_codigo': permiso_codigo},
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    '/permisos',
    response_model=PermisoListResponse,
    dependencies=[Depends(require_gd_permission('PERM-ROL-001', alcance='institucional'))],
)
async def listar_permisos(
    modulo: str | None = Query(default=None),
    estado: str | None = Query(default=None),
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PermisoListResponse:
    rows = await svc.listar_permisos(conn, modulo=modulo, estado=estado)
    return PermisoListResponse(items=[PermisoResponse(**r) for r in rows])


__all__ = ['router']
