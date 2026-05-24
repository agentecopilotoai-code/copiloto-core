"""Handlers HTTP para EP-021 periféricos parte 2 (bloque 21b — CIERRE).

Endpoints (GD-API-0136..0142):

Digitalización por lote (GD-API-0136):
- POST   /api/v1/gd/perifericos/{id}/digitalizar-lote
- GET    /api/v1/gd/perifericos/lotes/{lote_id}
- POST   /api/v1/gd/perifericos/lotes/{lote_id}/finalizar

Contexto activo (GD-API-0137):
- POST   /api/v1/gd/perifericos/contexto-activo
- DELETE /api/v1/gd/perifericos/contexto-activo

Mantenimiento + dashboard (GD-API-0138):
- GET    /api/v1/gd/perifericos/{id}/eventos
- GET    /api/v1/gd/perifericos/eventos/fallos
- POST   /api/v1/gd/perifericos/{id}/mantenimiento
- POST   /api/v1/gd/perifericos/{id}/mantenimiento/{mant_id}/finalizar

Agente local (GD-API-0139):
- POST   /api/v1/gd/agentes-locales/emparejar
- POST   /api/v1/gd/agentes-locales/{id}/revocar

Historial (GD-API-0141):
- GET    /api/v1/gd/perifericos/{id}/historial
- GET    /api/v1/gd/perifericos/historial-uso-global
- POST   /api/v1/gd/perifericos/historial/exportar

Reemplazo digitalización (GD-API-0142):
- POST   /api/v1/gd/digitalizaciones/{id}/reemplazar

Gate por módulo `ventanilla_presencial_con_perifericos` aplicado en todos
(404 si no activo).
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.perifericos2 import (
    AgenteLocalResponse,
    ContextoActivoRequest,
    ContextoActivoResponse,
    EmparejarAgenteRequest,
    EmparejarAgenteResponse,
    EventoPerifericoListResponse,
    EventoPerifericoResponse,
    ExportHistorialRequest,
    ExportHistorialResponse,
    FallosAgregadoResponse,
    FinalizarLoteRequest,
    FinalizarMantenimientoRequest,
    HistorialOperacionItem,
    HistorialResponse,
    IniciarLoteRequest,
    IniciarMantenimientoRequest,
    LoteProgresoResponse,
    LoteResponse,
    MantenimientoResponse,
    ReemplazarDigitalizacionRequest,
    ReemplazarDigitalizacionResponse,
    RevocarAgenteRequest,
)
from app.gd.security import GdPerfilContext, require_gd_perfil
from app.gd.services import perifericos as svc_perif
from app.gd.services import perifericos2 as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


# IMPORTANTE (D76): router_perif_literals MONTA RUTAS LITERALES bajo
# `/perifericos/{literal}` y debe registrarse en routes.py ANTES de
# `perifericos_handlers.router_perif` para evitar que el segmento literal
# colisione con el validator UUID de `/{periferico_id}` (ej. /perifericos/lotes
# → si llegara primero a router_perif intentaría coerce 'lotes' → UUID → 422).
router_perif_literals = APIRouter(
    prefix='/perifericos', tags=['gd:perifericos:b:literals'],
)
# router_perif_b agrupa solo rutas con {periferico_id} como primer segmento
# (sin conflicto con literales una vez registrados arriba).
router_perif_b = APIRouter(prefix='/perifericos', tags=['gd:perifericos:b'])
router_agentes = APIRouter(prefix='/agentes-locales',
                            tags=['gd:perifericos:agentes'])
router_digit = APIRouter(prefix='/digitalizaciones',
                          tags=['gd:perifericos:digit'])


async def _gate_modulo(conn: asyncpg.Connection, tenant_id: UUID) -> None:
    try:
        await svc_perif.assert_modulo_perifericos_activo(
            conn, tenant_id=tenant_id,
        )
    except svc_perif.ModuloNoActivoError as e:
        raise HTTPException(
            404, detail={'error': 'not_found',
                          'code': 'modulo_perifericos_no_activo',
                          'message': str(e)},
        ) from e


def _err_not_found(e: LookupError) -> HTTPException:
    return HTTPException(404, detail={'error': 'not_found', 'code': str(e)})


def _err_conflict(e: ValueError) -> HTTPException:
    return HTTPException(409, detail={'error': 'conflict', 'code': str(e)})


# =============================================================================
# Lote
# =============================================================================

@router_perif_b.post(
    '/{periferico_id}/digitalizar-lote',
    response_model=LoteResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def iniciar_lote(
    body: IniciarLoteRequest, request: Request,
    periferico_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> LoteResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    try:
        row = await svc.iniciar_lote_digitalizacion(
            conn, tenant_id=perfil.tenant_id, periferico_id=periferico_id,
            usuario_id=perfil.user_id,
            modo_separacion=body.modo_separacion,
            radicado_id_default=body.radicado_id_default,
            calidad_dpi=body.calidad_dpi, observacion=body.observacion,
            timeout_min=body.timeout_min,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_conflict(e) from e
    await emit_gd_event(
        conn, tipo_evento='gd.digitalizacion.lote_iniciado',
        accion='iniciar_lote',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='digitalizacion_lote',
        entidad_afectada_id=row['id'],
        valor_nuevo={'modo': body.modo_separacion,
                      'timeout_min': body.timeout_min},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return LoteResponse(**row)


@router_perif_literals.get(
    '/lotes/{lote_id}',
    response_model=LoteProgresoResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def get_lote(
    lote_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> LoteProgresoResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    row = await svc.progreso_lote(
        conn, tenant_id=perfil.tenant_id, lote_id=lote_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return LoteProgresoResponse(**row)


@router_perif_literals.post(
    '/lotes/{lote_id}/finalizar',
    response_model=LoteResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def post_finalizar_lote(
    body: FinalizarLoteRequest, request: Request,
    lote_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> LoteResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    try:
        row = await svc.finalizar_lote(
            conn, tenant_id=perfil.tenant_id, lote_id=lote_id,
            observacion_final=body.observacion_final,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_conflict(e) from e
    await emit_gd_event(
        conn, tipo_evento='gd.digitalizacion.lote_finalizado',
        accion='finalizar_lote',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='digitalizacion_lote',
        entidad_afectada_id=lote_id,
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return LoteResponse(**row)


# =============================================================================
# Contexto activo
# =============================================================================

@router_perif_literals.post(
    '/contexto-activo',
    response_model=ContextoActivoResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def upsert_contexto(
    body: ContextoActivoRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ContextoActivoResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    row = await svc.upsert_contexto_activo(
        conn, tenant_id=perfil.tenant_id, user_id=perfil.user_id,
        periferico_id=body.periferico_id,
        radicado_activo_id=body.radicado_activo_id,
        expira_en_segundos=body.expira_en_segundos,
    )
    await emit_gd_event(
        conn, tipo_evento='gd.digitalizacion.contexto_asignado',
        accion='upsert_contexto',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='contexto_periferico_usuario',
        entidad_afectada_id=row['id'],
        valor_nuevo={'radicado_id': str(body.radicado_activo_id),
                      'expira_seg': body.expira_en_segundos},
        criticidad=AuditCriticidad.BAJA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ContextoActivoResponse(**row)


@router_perif_literals.delete(
    '/contexto-activo',
    dependencies=[Depends(require_gd_perfil)],
)
async def del_contexto(
    periferico_id: UUID = Query(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> dict[str, bool]:
    await _gate_modulo(conn, perfil.tenant_id)
    eliminado = await svc.eliminar_contexto_activo(
        conn, tenant_id=perfil.tenant_id, user_id=perfil.user_id,
        periferico_id=periferico_id,
    )
    return {'eliminado': eliminado}


# =============================================================================
# Mantenimiento + dashboard salud
# =============================================================================

@router_perif_b.get(
    '/{periferico_id}/eventos',
    response_model=EventoPerifericoListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_eventos(
    periferico_id: UUID = Path(...),
    desde: datetime | None = Query(default=None),
    hasta: datetime | None = Query(default=None),
    resultado: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> EventoPerifericoListResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    rows = await svc.listar_eventos_periferico(
        conn, tenant_id=perfil.tenant_id, periferico_id=periferico_id,
        desde=desde, hasta=hasta, resultado=resultado, limit=limit,
    )
    items = [EventoPerifericoResponse(**r) for r in rows]
    return EventoPerifericoListResponse(items=items, total=len(items))


@router_perif_literals.get(
    '/eventos/fallos',
    response_model=FallosAgregadoResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def get_fallos(
    desde: datetime = Query(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> FallosAgregadoResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    rows = await svc.agregado_fallos(
        conn, tenant_id=perfil.tenant_id, desde=desde,
    )
    return FallosAgregadoResponse(desde=desde, items=rows)


@router_perif_b.post(
    '/{periferico_id}/mantenimiento',
    response_model=MantenimientoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def post_mantenimiento(
    body: IniciarMantenimientoRequest, request: Request,
    periferico_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> MantenimientoResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    try:
        row = await svc.iniciar_mantenimiento(
            conn, tenant_id=perfil.tenant_id,
            periferico_id=periferico_id, tipo=body.tipo,
            descripcion=body.descripcion,
            fecha_estimada_fin=body.fecha_estimada_fin,
            iniciado_por_user_id=perfil.user_id,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    await emit_gd_event(
        conn, tipo_evento='gd.mantenimiento.programado',
        accion='iniciar_mantenimiento',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='mantenimiento_periferico',
        entidad_afectada_id=row['id'],
        valor_nuevo={'periferico_id': str(periferico_id),
                      'tipo': body.tipo},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return MantenimientoResponse(**row)


@router_perif_b.post(
    '/{periferico_id}/mantenimiento/{mantenimiento_id}/finalizar',
    response_model=MantenimientoResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def post_finalizar_mant(
    body: FinalizarMantenimientoRequest, request: Request,
    periferico_id: UUID = Path(...),
    mantenimiento_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> MantenimientoResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    try:
        row = await svc.finalizar_mantenimiento(
            conn, tenant_id=perfil.tenant_id,
            periferico_id=periferico_id,
            mantenimiento_id=mantenimiento_id,
            observacion_final=body.observacion_final, costo=body.costo,
            repuestos=body.repuestos,
            finalizado_por_user_id=perfil.user_id,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_conflict(e) from e
    await emit_gd_event(
        conn, tipo_evento='gd.mantenimiento.finalizado',
        accion='finalizar_mantenimiento',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='mantenimiento_periferico',
        entidad_afectada_id=mantenimiento_id,
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return MantenimientoResponse(**row)


# =============================================================================
# Agente local
# =============================================================================

@router_agentes.post(
    '/emparejar',
    response_model=EmparejarAgenteResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def emparejar(
    body: EmparejarAgenteRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> EmparejarAgenteResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    try:
        row = await svc.emparejar_agente_local(
            conn, tenant_id=perfil.tenant_id,
            nombre_equipo=body.nombre_equipo,
            version_agente=body.version_agente,
            perifericos=body.perifericos,
            fingerprint_publico_b64=body.fingerprint_publico_b64,
            registrado_por_user_id=perfil.user_id,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_conflict(e) from e
    await emit_gd_event(
        conn, tipo_evento='gd.agente_local.emparejado',
        accion='emparejar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='agente_local_registro',
        entidad_afectada_id=row['id'],
        valor_nuevo={'nombre_equipo': body.nombre_equipo,
                      'periferico_count': len(body.perifericos)},
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return EmparejarAgenteResponse(
        agente_id=row['id'],
        nombre_equipo=row['nombre_equipo'],
        estado=row['estado'],
        token_emparejamiento=row['token_emparejamiento'],
        token_expira_en=row['token_emparejamiento_expira'],
        perifericos=row['periferico_ids'],
    )


@router_agentes.post(
    '/{agente_id}/revocar',
    response_model=AgenteLocalResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def revocar(
    body: RevocarAgenteRequest, request: Request,
    agente_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> AgenteLocalResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    try:
        row = await svc.revocar_agente_local(
            conn, tenant_id=perfil.tenant_id, agente_id=agente_id,
            motivo=body.motivo,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_conflict(e) from e
    await emit_gd_event(
        conn, tipo_evento='gd.agente_local.revocado', accion='revocar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='agente_local_registro',
        entidad_afectada_id=agente_id,
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return AgenteLocalResponse(
        id=row['id'], nombre_equipo=row['nombre_equipo'],
        version_agente=row.get('version_agente'),
        perifericos=row['periferico_ids'],
        estado=row['estado'],
        motivo_revocacion=row.get('motivo_revocacion'),
        ultimo_handshake_en=row.get('ultimo_handshake_en'),
        registrado_por_user_id=row['registrado_por_user_id'],
        fecha_registro=row['fecha_registro'],
    )


# =============================================================================
# Historial
# =============================================================================

@router_perif_b.get(
    '/{periferico_id}/historial',
    response_model=HistorialResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def historial_perif(
    periferico_id: UUID = Path(...),
    desde: datetime | None = Query(default=None),
    hasta: datetime | None = Query(default=None),
    tipo_operacion: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> HistorialResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    rows = await svc.historial_periferico(
        conn, tenant_id=perfil.tenant_id, periferico_id=periferico_id,
        desde=desde, hasta=hasta, tipo_operacion=tipo_operacion, limit=limit,
    )
    items = [HistorialOperacionItem(**r) for r in rows]
    return HistorialResponse(items=items, total=len(items))


@router_perif_literals.get(
    '/historial-uso-global',
    response_model=HistorialResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def historial_global(
    usuario_id: UUID | None = Query(default=None),
    periferico_id: UUID | None = Query(default=None),
    desde: datetime | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> HistorialResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    rows = await svc.historial_uso_global(
        conn, tenant_id=perfil.tenant_id, usuario_id=usuario_id,
        periferico_id=periferico_id, desde=desde, limit=limit,
    )
    items = [HistorialOperacionItem(**r) for r in rows]
    return HistorialResponse(items=items, total=len(items))


@router_perif_literals.post(
    '/historial/exportar',
    response_model=ExportHistorialResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_gd_perfil)],
)
async def exportar_historial(
    body: ExportHistorialRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ExportHistorialResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    row = await svc.export_historial(
        conn, tenant_id=perfil.tenant_id, formato=body.formato,
        desde=body.desde, hasta=body.hasta,
        periferico_id=body.periferico_id, usuario_id=body.usuario_id,
        solicitado_por_user_id=perfil.user_id,
    )
    await emit_gd_event(
        conn, tipo_evento='gd.perifericos.historial_consultado',
        accion='exportar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='periferico_export',
        entidad_afectada_id=row['export_id'],
        valor_nuevo={'formato': body.formato, 'filas': row['total_filas']},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ExportHistorialResponse(**row)


# =============================================================================
# Reemplazo digitalización
# =============================================================================

@router_digit.post(
    '/{digitalizacion_id}/reemplazar',
    response_model=ReemplazarDigitalizacionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def reemplazar_digit(
    body: ReemplazarDigitalizacionRequest, request: Request,
    digitalizacion_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ReemplazarDigitalizacionResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    try:
        row = await svc.reemplazar_digitalizacion(
            conn, tenant_id=perfil.tenant_id,
            digitalizacion_id=digitalizacion_id, motivo=body.motivo,
            archivo_digital_id_nuevo=body.archivo_digital_id_nuevo,
            usuario_id=perfil.user_id,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_conflict(e) from e
    await emit_gd_event(
        conn, tipo_evento='gd.digitalizacion.reemplazada',
        accion='reemplazar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='digitalizacion_documento',
        entidad_afectada_id=digitalizacion_id,
        valor_nuevo={'nueva_id': str(row['digitalizacion_nueva_id'])},
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ReemplazarDigitalizacionResponse(**row)


__all__ = [
    'router_perif_literals', 'router_perif_b',
    'router_agentes', 'router_digit',
]
