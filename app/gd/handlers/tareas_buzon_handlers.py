"""GD-API-0036..0039 — Tareas + Buzón agregado.

Sustituye el stub de tareas_handlers.py para los nuevos endpoints.
El archivo tareas_handlers.py original sigue manejando el endpoint
`/perfil-usuario/{user_id}/tareas-pendientes` (GD-API-0008 — reactivado).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.tareas import (
    AccionTarea,
    BuzonContador,
    BuzonDependenciaCargaItem,
    BuzonDependenciaResponse,
    BuzonResponse,
    TareaAccionRequest,
    TareaCreate,
    TareaReasignarRequest,
    TareaResponse,
    TareasListResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil, require_gd_permission
from app.gd.services import notificaciones as svc_notif
from app.gd.services import tareas as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router_tareas = APIRouter(prefix='/tareas', tags=['gd:tareas'])
router_buzon = APIRouter(prefix='/buzon', tags=['gd:buzon'])


# =============================================================================
# /tareas
# =============================================================================

@router_tareas.post(
    '',
    response_model=TareaResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_permission('PERM-USR-001', alcance='institucional'))],
)
async def crear_tarea(
    body: TareaCreate, request: Request,
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TareaResponse:
    if body.asignado_a_user_id is None and body.asignado_a_dependencia_id is None:
        raise HTTPException(
            422,
            detail={
                'error': 'validation_error',
                'message': 'Debe asignarse a un usuario o una dependencia',
            },
        )
    try:
        row = await svc.crear_tarea(
            conn, tenant_id=perfil_actor.tenant_id,
            datos=body.model_dump(),
            asignado_por_user_id=perfil_actor.user_id,
        )
    except asyncpg.IntegrityConstraintViolationError as exc:
        raise HTTPException(422, detail={'error': 'validation_error', 'detail': str(exc)})

    await emit_gd_event(
        conn,
        tipo_evento='gd.tarea.creada',
        accion='crear_tarea',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='tarea',
        entidad_afectada_id=row['id'],
        valor_nuevo={'titulo': body.titulo, 'tipo_tarea': body.tipo_tarea},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return TareaResponse(**row)


@router_tareas.get(
    '',
    response_model=TareasListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_tareas(
    asignadas_a: str | None = Query(default=None, description='"me" = filtro a usuario actual'),
    estado: str | None = Query(default=None, description='Coma-separado'),
    fecha_limite_antes: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TareasListResponse:
    user_id = perfil.user_id if asignadas_a == 'me' else None
    estado_list = estado.split(',') if estado else None

    rows = await svc.listar_tareas(
        conn, tenant_id=perfil.tenant_id,
        asignado_a_user_id=user_id,
        estado=estado_list,
        fecha_limite_antes=fecha_limite_antes,
        limit=limit,
    )
    return TareasListResponse(
        items=[TareaResponse(**r) for r in rows],
        pagina={'limit_aplicado': limit, 'total_estimado': len(rows)},
    )


# IMPORTANTE: /{tarea_id}/reasignar DEBE definirse ANTES que
# /{tarea_id}/{accion} para evitar que FastAPI matche 'reasignar' como una
# acción (no está en AccionTarea Literal → 422). El orden de declaración
# importa en FastAPI: el primero registrado gana.
@router_tareas.post(
    '/{tarea_id}/reasignar',
    response_model=TareaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def reasignar_tarea_endpoint(
    body: TareaReasignarRequest, request: Request,
    tarea_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TareaResponse:
    if body.usuario_destino_id is None and body.dependencia_destino_id is None:
        raise HTTPException(
            422,
            detail={
                'error': 'validation_error',
                'message': 'Debe especificar usuario_destino_id o dependencia_destino_id',
            },
        )
    # Validar usuario destino activo si se especifica.
    if body.usuario_destino_id is not None:
        estado = await conn.fetchval(
            """
            select estado_gd from gd.perfil_usuario
            where user_id = $1 and tenant_id = $2
            """,
            body.usuario_destino_id, perfil_actor.tenant_id,
        )
        if estado != 'activo':
            raise HTTPException(
                422,
                detail={
                    'error': 'validation_error',
                    'code': 'usuario_destino_inactivo',
                },
            )

    row = await svc.reasignar_tarea(
        conn, tenant_id=perfil_actor.tenant_id,
        tarea_id=tarea_id,
        usuario_destino_id=body.usuario_destino_id,
        dependencia_destino_id=body.dependencia_destino_id,
        motivo=body.motivo,
        ejecutado_por_user_id=perfil_actor.user_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn,
        tipo_evento='gd.tarea.reasignada',
        accion='reasignar_tarea',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='tarea',
        entidad_afectada_id=tarea_id,
        valor_nuevo={
            'usuario_destino_id': str(body.usuario_destino_id) if body.usuario_destino_id else None,
            'dependencia_destino_id': str(body.dependencia_destino_id) if body.dependencia_destino_id else None,
        },
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return TareaResponse(**row)


@router_tareas.post(
    '/{tarea_id}/{accion}',
    response_model=TareaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def aplicar_accion_tarea(
    body: TareaAccionRequest,
    request: Request,
    tarea_id: UUID = Path(...),
    accion: AccionTarea = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TareaResponse:
    # devolver y finalizar requieren observación.
    if accion in ('devolver', 'anular') and (not body.observacion or len(body.observacion) < 5):
        raise HTTPException(
            422,
            detail={
                'error': 'validation_error',
                'message': f'accion={accion!r} requiere observacion (min 5 chars).',
            },
        )

    row = await svc.aplicar_accion(
        conn, tenant_id=perfil_actor.tenant_id,
        tarea_id=tarea_id, accion=accion,
        ejecutado_por_user_id=perfil_actor.user_id,
        observacion=body.observacion,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    tipo_evento_map = {
        'iniciar': 'gd.tarea.iniciada', 'devolver': 'gd.tarea.devuelta',
        'finalizar': 'gd.tarea.finalizada', 'escalar': 'gd.tarea.escalada',
        'anular': 'gd.tarea.anulada',
    }
    criticidad = (
        AuditCriticidad.ALTA if accion in ('anular', 'devolver', 'escalar')
        else AuditCriticidad.MEDIA
    )
    await emit_gd_event(
        conn,
        tipo_evento=tipo_evento_map[accion],
        accion=accion,
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='tarea',
        entidad_afectada_id=tarea_id,
        justificacion=body.observacion,
        criticidad=criticidad,
        request_id=getattr(request.state, 'request_id', None),
    )
    return TareaResponse(**row)


# =============================================================================
# /buzon
# =============================================================================

@router_buzon.get(
    '',
    response_model=BuzonResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def buzon_usuario(
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> BuzonResponse:
    """GET /api/v1/gd/buzon — agregado del usuario actual."""
    # Conteos por estado.
    counts = await svc.contar_tareas_por_estado(
        conn, tenant_id=perfil.tenant_id,
        asignado_a_user_id=perfil.user_id,
    )

    # Primera página por sección.
    pendientes = await svc.listar_tareas(
        conn, tenant_id=perfil.tenant_id,
        asignado_a_user_id=perfil.user_id,
        estado=['pendiente'], limit=10,
    )
    en_proceso = await svc.listar_tareas(
        conn, tenant_id=perfil.tenant_id,
        asignado_a_user_id=perfil.user_id,
        estado=['en_proceso'], limit=10,
    )
    devueltas = await svc.listar_tareas(
        conn, tenant_id=perfil.tenant_id,
        asignado_a_user_id=perfil.user_id,
        estado=['devuelta'], limit=10,
    )
    # Vencimientos próximos (7 días).
    fecha_corte = datetime.now() + timedelta(days=7)
    proximos = await svc.listar_tareas(
        conn, tenant_id=perfil.tenant_id,
        asignado_a_user_id=perfil.user_id,
        estado=['pendiente', 'en_proceso'],
        fecha_limite_antes=fecha_corte, limit=10,
    )

    # Notificaciones no leídas + alertas (placeholder hasta GD-API-0041).
    no_leidas = await svc_notif.contar_no_leidas(
        conn, tenant_id=perfil.tenant_id,
        destinatario_user_id=perfil.user_id,
    )

    return BuzonResponse(
        usuario_id=perfil.user_id,
        tareas_pendientes=BuzonContador(
            total=counts.get('pendiente', 0),
            items=[TareaResponse(**r) for r in pendientes],
        ),
        tareas_en_proceso=BuzonContador(
            total=counts.get('en_proceso', 0),
            items=[TareaResponse(**r) for r in en_proceso],
        ),
        tareas_devueltas=BuzonContador(
            total=counts.get('devuelta', 0),
            items=[TareaResponse(**r) for r in devueltas],
        ),
        vencimientos_proximos=BuzonContador(
            total=len(proximos),
            items=[TareaResponse(**r) for r in proximos],
        ),
        notificaciones_no_leidas=no_leidas,
        alertas_activas=0,  # GD-API-0041 todavía no implementado
    )


@router_buzon.get(
    '/dependencia/{dependencia_id}',
    response_model=BuzonDependenciaResponse,
    dependencies=[Depends(require_gd_permission('PERM-USR-010', alcance='dependencia'))],
)
async def buzon_dependencia(
    dependencia_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> BuzonDependenciaResponse:
    """GET /api/v1/gd/buzon/dependencia/{id} — jefe ve su dependencia."""
    counts = await svc.contar_tareas_por_estado(
        conn, tenant_id=perfil.tenant_id,
        asignado_a_dependencia_id=dependencia_id,
    )

    pendientes = await svc.listar_tareas(
        conn, tenant_id=perfil.tenant_id,
        asignado_a_dependencia_id=dependencia_id,
        estado=['pendiente'], limit=10,
    )

    carga = await svc.carga_por_usuario_dependencia(
        conn, tenant_id=perfil.tenant_id, dependencia_id=dependencia_id,
    )

    return BuzonDependenciaResponse(
        dependencia_id=dependencia_id,
        totales=counts,
        carga_por_usuario=[BuzonDependenciaCargaItem(**c) for c in carga],
        tareas_pendientes=BuzonContador(
            total=counts.get('pendiente', 0),
            items=[TareaResponse(**r) for r in pendientes],
        ),
    )


__all__ = ['router_tareas', 'router_buzon']
