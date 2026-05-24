"""GD-API-0008 — Reasignación de tareas al inactivar usuario.

⚠️ Stub: las tablas `gd.tarea` y `gd.asignacion_pqrsd` aún no existen (vienen
en bloques posteriores EP-006/EP-007). En este bloque, los endpoints están
implementados con el contrato correcto pero retornan listas vacías / no-op.

El contrato Pydantic ya es estable (documentado en INTEGRACION_E1_IDENTIDAD.md
sección 6); cuando las tablas aparezcan solo se cambia la implementación de
los servicios, no la signature pública.
"""
from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Request

from app.db.pool import get_db
from app.gd.schemas.tareas import (
    ReasignacionTareaResultadoItem,
    ReasignacionTareasRequest,
    ReasignacionTareasResponse,
    TareasPendientesPorTipo,
    TareasPendientesResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil, require_gd_permission
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router = APIRouter(prefix='/perfil-usuario', tags=['gd:tareas-reasignacion'])


@router.get(
    '/{user_id}/tareas-pendientes',
    response_model=TareasPendientesResponse,
    dependencies=[Depends(require_gd_permission('PERM-USR-009', alcance='institucional'))],
)
async def tareas_pendientes(
    user_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TareasPendientesResponse:
    """GD-API-0008 reactivado (bloque 6): consume gd.tarea real.

    Devuelve tareas en estado pendiente|en_proceso|devuelta asignadas al
    user_id. Usado por GD-UI-0019 (reasignación masiva al inactivar usuario).
    """
    from datetime import datetime, timezone

    # Conteos por tipo de origen.
    rows_count = await conn.fetch(
        """
        select entidad_origen_tipo, count(*) as c
        from gd.tarea
        where tenant_id = $1
          and asignado_a_user_id = $2
          and estado in ('pendiente', 'en_proceso', 'devuelta')
        group by entidad_origen_tipo
        """,
        perfil_actor.tenant_id, user_id,
    )
    por_tipo = TareasPendientesPorTipo()
    map_tipos = {
        'pqrsd': 'pqrsd_asignadas',
        'documento': 'documentos_por_revisar',  # default; granularidad fina en EP-009
        'correspondencia': 'correspondencia_recibida',
        'generica': 'tareas_genericas',
    }
    por_tipo_dict: dict = {}
    for r in rows_count:
        attr = map_tipos.get(r['entidad_origen_tipo'], 'tareas_genericas')
        por_tipo_dict[attr] = por_tipo_dict.get(attr, 0) + int(r['c'])
    por_tipo = TareasPendientesPorTipo(**por_tipo_dict)

    # Lista de items (top 100).
    rows = await conn.fetch(
        """
        select id, tipo_tarea, entidad_origen_tipo, entidad_origen_id,
               titulo, fecha_limite, prioridad
        from gd.tarea
        where tenant_id = $1
          and asignado_a_user_id = $2
          and estado in ('pendiente', 'en_proceso', 'devuelta')
        order by fecha_limite asc nulls last
        limit 100
        """,
        perfil_actor.tenant_id, user_id,
    )

    now = datetime.now(timezone.utc)
    items = []
    for r in rows:
        dias = None
        if r['fecha_limite']:
            dias = (r['fecha_limite'] - now).days
        items.append({
            'tarea_id': r['id'],
            'tipo_tarea': r['tipo_tarea'],
            'entidad_origen_tipo': r['entidad_origen_tipo'] or 'generica',
            'entidad_origen_id': r['entidad_origen_id'] or r['id'],
            'titulo': r['titulo'],
            'fecha_limite': r['fecha_limite'],
            'prioridad': r['prioridad'],
            'dias_para_vencimiento': dias,
        })

    total = sum(por_tipo_dict.values())

    return TareasPendientesResponse(
        user_id=user_id,
        total_pendientes=total,
        por_tipo=por_tipo,
        items=items,
    )


@router.post(
    '/{user_id}/tareas/reasignar',
    response_model=ReasignacionTareasResponse,
    dependencies=[Depends(require_gd_permission('PERM-USR-009', alcance='institucional'))],
)
async def reasignar_tareas(
    body: ReasignacionTareasRequest,
    request: Request,
    user_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ReasignacionTareasResponse:
    # Verificar destino activo.
    estado_destino = await conn.fetchval(
        """
        select estado_gd from gd.perfil_usuario
        where user_id = $1 and tenant_id = $2
        """,
        body.user_destino_id, perfil_actor.tenant_id,
    )
    if estado_destino != 'activo':
        raise HTTPException(
            422,
            detail={
                'error': 'validation_error',
                'code': 'usuario_destino_inactivo',
                'message': 'Solo se puede reasignar a usuarios con estado_gd=activo.',
            },
        )

    # GD-API-0008 reactivado (bloque 6): UPDATE masivo de tareas + historial.
    detalles: list[ReasignacionTareaResultadoItem] = []
    for tarea_id in body.tareas:
        try:
            actual = await conn.fetchrow(
                'select asignado_a_user_id from gd.tarea where id = $1 and tenant_id = $2',
                tarea_id, perfil_actor.tenant_id,
            )
            if actual is None:
                detalles.append(ReasignacionTareaResultadoItem(
                    tarea_id=tarea_id, estado='fallida', error='tarea_no_existe',
                ))
                continue

            await conn.execute(
                """
                update gd.tarea
                set asignado_a_user_id = $3,
                    asignado_por_user_id = $4,
                    fecha_asignacion = now(),
                    updated_at = now()
                where id = $1 and tenant_id = $2
                """,
                tarea_id, perfil_actor.tenant_id,
                body.user_destino_id, perfil_actor.user_id,
            )
            await conn.execute(
                """
                insert into gd.tarea_historial (
                    tenant_id, tarea_id, tipo_evento,
                    asignado_a_user_id_anterior, asignado_a_user_id_nuevo,
                    motivo, ejecutado_por_user_id
                )
                values ($1, $2, 'reasignada', $3, $4, $5, $6)
                """,
                perfil_actor.tenant_id, tarea_id,
                actual['asignado_a_user_id'], body.user_destino_id,
                body.motivo, perfil_actor.user_id,
            )
            detalles.append(ReasignacionTareaResultadoItem(
                tarea_id=tarea_id, estado='reasignada',
            ))
        except Exception as exc:  # noqa: BLE001
            detalles.append(ReasignacionTareaResultadoItem(
                tarea_id=tarea_id, estado='fallida', error=str(exc),
            ))

    # Auditar el intento (incluso fallido) — RNF-009.
    await emit_gd_event(
        conn,
        tipo_evento='gd.tarea.reasignacion_solicitada',
        accion='reasignar_tareas',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='perfil_usuario',
        entidad_afectada_id=user_id,
        valor_nuevo={
            'destino_user_id': str(body.user_destino_id),
            'tareas_count': len(body.tareas),
        },
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )

    reasignadas = sum(1 for d in detalles if d.estado == 'reasignada')
    fallidas = sum(1 for d in detalles if d.estado == 'fallida')
    return ReasignacionTareasResponse(
        reasignadas=reasignadas,
        fallidas=fallidas,
        detalles=detalles,
    )


__all__ = ['router']
