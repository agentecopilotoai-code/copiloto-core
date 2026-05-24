"""GD-API-0005 — Asignación de rol GD con alcance por dependencia.

D9: NO inserta en `app.user_tenant_roles`. Solo en `gd.asignacion_alcance`.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.asignaciones import (
    AsignacionesUsuarioResponse,
    AsignacionRolCerradaResponse,
    AsignacionRolCerrarRequest,
    AsignacionRolCreate,
    AsignacionRolResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil, require_gd_permission
from app.gd.services import asignaciones as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router = APIRouter(prefix='/usuarios', tags=['gd:asignaciones'])


@router.post(
    '/{user_id}/roles',
    response_model=AsignacionRolResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_permission('PERM-USR-011', alcance='institucional'))],
)
async def asignar_rol(
    body: AsignacionRolCreate,
    request: Request,
    user_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> AsignacionRolResponse:
    # Validar usuario destino está activo (RNF-008).
    estado_destino = await conn.fetchval(
        """
        select estado_gd from gd.perfil_usuario
        where user_id = $1 and tenant_id = $2
        """,
        user_id, perfil_actor.tenant_id,
    )
    if estado_destino is None:
        raise HTTPException(
            404,
            detail={
                'error': 'not_found',
                'code': 'perfil_destino_no_existe',
                'message': 'El usuario destino no tiene perfil GD en este tenant.',
            },
        )
    if estado_destino != 'activo':
        raise HTTPException(
            409,
            detail={
                'error': 'conflict',
                'code': 'usuario_inactivo',
                'message': f'No se puede asignar rol a un usuario en estado {estado_destino!r}.',
            },
        )

    try:
        row = await svc.asignar_rol(
            conn,
            tenant_id=perfil_actor.tenant_id,
            user_id=user_id,
            rol_codigo=body.rol_codigo,
            dependencia_id=body.dependencia_id,
            alcance=body.alcance,
            fecha_inicio=body.fecha_inicio,
            fecha_fin=body.fecha_fin,
            motivo=body.motivo,
            asignado_por_user_id=perfil_actor.user_id,
        )
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(
            404,
            detail={
                'error': 'not_found',
                'message': f'Rol {body.rol_codigo!r} o dependencia no existe.',
            },
        )

    await emit_gd_event(
        conn,
        tipo_evento='gd.rol_asignado',
        accion='asignar_rol',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='asignacion_alcance',
        entidad_afectada_id=row['asignacion_alcance_id'],
        valor_nuevo={
            'rol_codigo': body.rol_codigo,
            'user_id': str(user_id),
            'alcance': body.alcance,
            'dependencia_id': str(body.dependencia_id) if body.dependencia_id else None,
        },
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return AsignacionRolResponse(**row)


@router.post(
    '/{user_id}/roles/{asignacion_alcance_id}/cerrar',
    response_model=AsignacionRolCerradaResponse,
    dependencies=[Depends(require_gd_permission('PERM-USR-012', alcance='institucional'))],
)
async def cerrar_asignacion(
    body: AsignacionRolCerrarRequest,
    request: Request,
    user_id: UUID = Path(...),
    asignacion_alcance_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> AsignacionRolCerradaResponse:
    row = await svc.cerrar_asignacion(
        conn,
        tenant_id=perfil_actor.tenant_id,
        user_id=user_id,
        asignacion_alcance_id=asignacion_alcance_id,
        motivo=body.motivo,
        cerrado_por_user_id=perfil_actor.user_id,
    )
    if row is None:
        raise HTTPException(
            404,
            detail={
                'error': 'not_found',
                'message': 'Asignación no encontrada o ya cerrada.',
            },
        )

    await emit_gd_event(
        conn,
        tipo_evento='gd.rol_retirado',
        accion='cerrar_asignacion',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='asignacion_alcance',
        entidad_afectada_id=asignacion_alcance_id,
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )

    return AsignacionRolCerradaResponse(
        asignacion_alcance_id=row['asignacion_alcance_id'],
        fecha_fin=row['fecha_fin'] if isinstance(row['fecha_fin'], datetime) else datetime.now(UTC),
        estado=row['estado'],
    )


@router.get(
    '/{user_id}/roles',
    response_model=AsignacionesUsuarioResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_roles_usuario(
    user_id: UUID = Path(...),
    incluir_historicas: bool = Query(default=False),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> AsignacionesUsuarioResponse:
    # Permiso: PERM-USR-010 (consultar) o el propio usuario.
    if user_id != perfil_actor.user_id:
        # Reuso de require_gd_permission requeriría callable injection;
        # validamos manualmente.
        from app.gd.security import _alcance_es_suficiente, get_permisos_efectivos
        efectivos = await get_permisos_efectivos(
            conn, user_id=perfil_actor.user_id, tenant_id=perfil_actor.tenant_id
        )
        alcance = efectivos.get('PERM-USR-010')
        if not _alcance_es_suficiente(alcance, 'institucional'):
            raise HTTPException(
                403,
                detail={
                    'error': 'forbidden',
                    'permiso_requerido': 'PERM-USR-010',
                    'alcance_requerido': 'institucional',
                },
            )

    resultado = await svc.listar_roles_usuario(
        conn,
        tenant_id=perfil_actor.tenant_id,
        user_id=user_id,
        incluir_historicas=incluir_historicas,
    )
    return AsignacionesUsuarioResponse(
        vigentes=[AsignacionRolResponse(**r) for r in resultado['vigentes']],
        historicas=[AsignacionRolResponse(**r) for r in resultado['historicas']],
    )


__all__ = ['router']
