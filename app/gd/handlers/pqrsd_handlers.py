"""Handlers HTTP de EP-007 PQRSD — bloque 7 (GD-API-0042..0046) + bloque 8 (0047..0051).

Endpoints implementados (bloque 7):
- GET /api/v1/gd/pqrsd?...  (lista + filtros)
- GET /api/v1/gd/pqrsd/{id}
- POST /api/v1/gd/pqrsd/{id}/asignar-dependencia
- POST /api/v1/gd/pqrsd/{id}/asignar-funcionario
- POST /api/v1/gd/pqrsd/{id}/reasignar
- POST /api/v1/gd/pqrsd/{id}/respuestas
- POST /api/v1/gd/pqrsd/{id}/suspender-termino
- POST /api/v1/gd/pqrsd/{id}/reanudar-termino
- GET  /api/v1/gd/pqrsd/{id}/historial-terminos

Endpoints implementados (bloque 8):
- POST /api/v1/gd/respuestas/{id}/enviar-a-revision   (GD-API-0047)
- POST /api/v1/gd/respuestas/{id}/revisar
- POST /api/v1/gd/respuestas/{id}/aprobar
- POST /api/v1/gd/respuestas/{id}/firmar
- POST /api/v1/gd/respuestas/{id}/radicar-salida
- POST /api/v1/gd/respuestas/{id}/enviar
- POST /api/v1/gd/pqrsd/{id}/cerrar                   (GD-API-0048)
- POST /api/v1/gd/pqrsd/{id}/reabrir
- POST /api/v1/gd/pqrsd/{id}/trasladar-competencia    (GD-API-0049)
- POST /api/v1/gd/pqrsd/{id}/solicitar-info-adicional (GD-API-0050)
- GET  /api/v1/gd/pqrsd/dashboard                     (GD-API-0051)
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.pqrsd import (
    AprobarRespuestaRequest,
    AsignacionPqrsdResponse,
    AsignarDependenciaRequest,
    AsignarFuncionarioRequest,
    CerrarPqrsdRequest,
    DashboardPqrsdBucket,
    DashboardPqrsdResponse,
    EnviarRespuestaRequest,
    EnviarRevisionRequest,
    EventoTerminoResponse,
    FirmarRespuestaRequest,
    HistorialTerminoResponse,
    PqrsdListItem,
    PqrsdListResponse,
    PqrsdResponse,
    ProyectarRespuestaRequest,
    RadicarSalidaRequest,
    ReabrirPqrsdRequest,
    ReanudarTerminoRequest,
    ReasignarPqrsdRequest,
    RespuestaPqrsdDetalleResponse,
    RespuestaPqrsdResponse,
    RevisarRespuestaRequest,
    SolicitarInfoAdicionalRequest,
    SuspenderTerminoRequest,
    TrasladarCompetenciaRequest,
)
from app.gd.security import GdPerfilContext, require_gd_perfil
from app.gd.services import pqrsd as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


# Router separado para /pqrsd/dashboard — debe registrarse ANTES que el
# router principal en routes.py para que no choque con /pqrsd/{id}.
router_dashboard = APIRouter(prefix='/pqrsd', tags=['gd:pqrsd:dashboard'])

router = APIRouter(prefix='/pqrsd', tags=['gd:pqrsd'])

# Router separado para /respuestas/{id}/... (workflow de respuesta).
router_respuestas = APIRouter(prefix='/respuestas', tags=['gd:respuestas'])


def _calc_semaforo(fecha_limite: datetime | None) -> str:
    if fecha_limite is None:
        return 'verde'
    now = datetime.now(timezone.utc)
    dias = (fecha_limite - now).days
    if dias < 0:
        return 'vencido'
    if dias <= 2:
        return 'rojo'
    if dias <= 5:
        return 'ambar'
    return 'verde'


# =============================================================================
# GET listar + detalle
# =============================================================================

@router.get(
    '',
    response_model=PqrsdListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_pqrsd(
    estado: str | None = Query(default=None),
    dependencia_id: UUID | None = Query(default=None),
    usuario_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PqrsdListResponse:
    estado_list = estado.split(',') if estado else None
    rows = await svc.listar_pqrsd(
        conn, tenant_id=perfil.tenant_id,
        estado=estado_list, dependencia_id=dependencia_id,
        usuario_id=usuario_id, limit=limit,
    )
    total = await svc.contar_pqrsd(conn, tenant_id=perfil.tenant_id)

    now = datetime.now(timezone.utc)
    items: list[PqrsdListItem] = []
    for r in rows:
        fecha_lim = r.get('fecha_limite_respuesta')
        dias = (fecha_lim - now).days if fecha_lim else None
        items.append(PqrsdListItem(
            id=r['id'], radicado_entrada_id=r['radicado_entrada_id'],
            numero_radicado=r.get('numero_radicado'),
            asunto=r['asunto'], estado=r['estado'],
            fecha_recepcion=r['fecha_recepcion'],
            fecha_limite_respuesta=fecha_lim,
            dependencia_responsable_id=r.get('dependencia_responsable_id'),
            usuario_responsable_id=r.get('usuario_responsable_id'),
            dias_para_vencimiento=dias,
            semaforo=_calc_semaforo(fecha_lim),
        ))
    return PqrsdListResponse(items=items, total=total)


@router.get(
    '/{pqrsd_id}',
    response_model=PqrsdResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def obtener_pqrsd(
    pqrsd_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PqrsdResponse:
    row = await svc.obtener_pqrsd(
        conn, tenant_id=perfil.tenant_id, pqrsd_id=pqrsd_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return PqrsdResponse(**row)


# =============================================================================
# Asignación
# =============================================================================

@router.post(
    '/{pqrsd_id}/asignar-dependencia',
    response_model=AsignacionPqrsdResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def asignar_dependencia(
    body: AsignarDependenciaRequest, request: Request,
    pqrsd_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> AsignacionPqrsdResponse:
    row = await svc.asignar_a_dependencia(
        conn, tenant_id=perfil_actor.tenant_id, pqrsd_id=pqrsd_id,
        dependencia_id=body.dependencia_id,
        asignado_por_user_id=perfil_actor.user_id, motivo=body.motivo,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn,
        tipo_evento='PQRSDAsignada',
        accion='asignar_dependencia',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='pqrsd',
        entidad_afectada_id=pqrsd_id,
        valor_nuevo={'dependencia_id': str(body.dependencia_id)},
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return AsignacionPqrsdResponse(**row)


@router.post(
    '/{pqrsd_id}/asignar-funcionario',
    response_model=AsignacionPqrsdResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def asignar_funcionario(
    body: AsignarFuncionarioRequest, request: Request,
    pqrsd_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> AsignacionPqrsdResponse:
    # Validar usuario destino activo.
    estado = await conn.fetchval(
        'select estado_gd from gd.perfil_usuario where user_id = $1 and tenant_id = $2',
        body.usuario_id, perfil_actor.tenant_id,
    )
    if estado != 'activo':
        raise HTTPException(
            422,
            detail={'error': 'validation_error', 'code': 'usuario_inactivo'},
        )

    row = await svc.asignar_a_funcionario(
        conn, tenant_id=perfil_actor.tenant_id, pqrsd_id=pqrsd_id,
        usuario_id=body.usuario_id,
        asignado_por_user_id=perfil_actor.user_id, motivo=body.motivo,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn,
        tipo_evento='PQRSDAsignada',
        accion='asignar_funcionario',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='pqrsd',
        entidad_afectada_id=pqrsd_id,
        valor_nuevo={'usuario_id': str(body.usuario_id)},
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return AsignacionPqrsdResponse(**row)


@router.post(
    '/{pqrsd_id}/reasignar',
    response_model=AsignacionPqrsdResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def reasignar_pqrsd(
    body: ReasignarPqrsdRequest, request: Request,
    pqrsd_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> AsignacionPqrsdResponse:
    if body.dependencia_id is None and body.usuario_id is None:
        raise HTTPException(
            422,
            detail={
                'error': 'validation_error',
                'message': 'Debe especificar dependencia_id o usuario_id',
            },
        )

    if body.usuario_id is not None:
        estado = await conn.fetchval(
            'select estado_gd from gd.perfil_usuario where user_id = $1 and tenant_id = $2',
            body.usuario_id, perfil_actor.tenant_id,
        )
        if estado != 'activo':
            raise HTTPException(
                422,
                detail={'error': 'validation_error', 'code': 'usuario_inactivo'},
            )

    row = await svc.reasignar_pqrsd(
        conn, tenant_id=perfil_actor.tenant_id, pqrsd_id=pqrsd_id,
        dependencia_id=body.dependencia_id, usuario_id=body.usuario_id,
        motivo=body.motivo, asignado_por_user_id=perfil_actor.user_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn,
        tipo_evento='PQRSDReasignada',
        accion='reasignar',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='pqrsd',
        entidad_afectada_id=pqrsd_id,
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return AsignacionPqrsdResponse(**row)


# =============================================================================
# Respuesta — proyectar
# =============================================================================

@router.post(
    '/{pqrsd_id}/respuestas',
    response_model=RespuestaPqrsdResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def proyectar_respuesta(
    body: ProyectarRespuestaRequest, request: Request,
    pqrsd_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RespuestaPqrsdResponse:
    if not (body.documento_id or body.plantilla_id or body.contenido_borrador):
        raise HTTPException(
            422,
            detail={
                'error': 'validation_error',
                'message': 'Debe proveer documento_id, plantilla_id o contenido_borrador',
            },
        )

    row = await svc.proyectar_respuesta(
        conn, tenant_id=perfil_actor.tenant_id, pqrsd_id=pqrsd_id,
        documento_id=body.documento_id, plantilla_id=body.plantilla_id,
        contenido_borrador=body.contenido_borrador,
        usuario_proyecta_id=perfil_actor.user_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn,
        tipo_evento='RespuestaProyectada',
        accion='proyectar_respuesta',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='respuesta_pqrsd',
        entidad_afectada_id=row['id'],
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return RespuestaPqrsdResponse(**row)


# =============================================================================
# Suspensión / reanudación de término (GD-API-0042 + 0127)
# =============================================================================

@router.post(
    '/{pqrsd_id}/suspender-termino',
    response_model=EventoTerminoResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def suspender_termino(
    body: SuspenderTerminoRequest, request: Request,
    pqrsd_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> EventoTerminoResponse:
    row = await svc.suspender_termino(
        conn, tenant_id=perfil_actor.tenant_id, pqrsd_id=pqrsd_id,
        motivo=body.motivo, justificacion_legal=body.justificacion_legal,
        dias_estimados=body.dias_estimados_suspension,
        usuario_id=perfil_actor.user_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn,
        tipo_evento='gd.pqrsd.termino_suspendido',
        accion='suspender_termino',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='pqrsd',
        entidad_afectada_id=pqrsd_id,
        justificacion=body.justificacion_legal or body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return EventoTerminoResponse(**row)


@router.post(
    '/{pqrsd_id}/reanudar-termino',
    response_model=EventoTerminoResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def reanudar_termino(
    body: ReanudarTerminoRequest, request: Request,
    pqrsd_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> EventoTerminoResponse:
    row = await svc.reanudar_termino(
        conn, tenant_id=perfil_actor.tenant_id, pqrsd_id=pqrsd_id,
        motivo=body.motivo, usuario_id=perfil_actor.user_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn,
        tipo_evento='gd.pqrsd.termino_reanudado',
        accion='reanudar_termino',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='pqrsd',
        entidad_afectada_id=pqrsd_id,
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return EventoTerminoResponse(**row)


@router.get(
    '/{pqrsd_id}/historial-terminos',
    response_model=HistorialTerminoResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def historial_terminos(
    pqrsd_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> HistorialTerminoResponse:
    eventos = await svc.listar_eventos_termino(
        conn, tenant_id=perfil.tenant_id, pqrsd_id=pqrsd_id,
    )
    # fecha_limite_vigente lookup.
    pqrsd_row = await svc.obtener_pqrsd(
        conn, tenant_id=perfil.tenant_id, pqrsd_id=pqrsd_id,
    )
    if pqrsd_row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    return HistorialTerminoResponse(
        pqrsd_id=pqrsd_id,
        eventos=[EventoTerminoResponse(**e) for e in eventos],
        fecha_limite_vigente=pqrsd_row.get('fecha_limite_respuesta'),
    )


# =============================================================================
# BLOQUE 8 — EP-007 cierre PQRSD (GD-API-0047..0051)
# =============================================================================

# IMPORTANTE sobre orden de rutas:
# - /pqrsd/dashboard DEBE registrarse ANTES que /pqrsd/{pqrsd_id} para que
#   FastAPI no la interprete como detalle. Por eso aquí, al usar @router.get,
#   FastAPI matchea en orden de registro y la ruta de detalle ya está arriba,
#   pero como 'dashboard' no es un UUID válido, la validación de Path(UUID)
#   en obtener_pqrsd rechazaría con 422 y bloquearía el flujo. Solución: usar
#   un prefix distinto. La ruta dashboard la registramos como /dashboard en
#   un sub-router que se monta primero (más abajo).
# - Idéntico tratamiento para /pqrsd/{id}/cerrar, /reabrir, etc.: como esos
#   sí incluyen un UUID seguido de literal, NO chocan con /{pqrsd_id}.


def _validar_separacion(e: PermissionError) -> HTTPException:
    """Convierte PermissionError de separación de funciones en HTTP 403."""
    msg = str(e)
    return HTTPException(
        403,
        detail={'error': 'forbidden', 'code': 'separacion_funciones',
                'message': msg},
    )


def _validar_estado(e: ValueError) -> HTTPException:
    """Convierte ValueError 'estado_invalido:X' o 'sin_respuesta_enviada' en 409."""
    code = str(e)
    return HTTPException(
        409,
        detail={'error': 'conflict', 'code': code},
    )


# --- GD-API-0047: workflow de respuesta ---

@router_respuestas.post(
    '/{respuesta_id}/enviar-a-revision',
    response_model=RespuestaPqrsdDetalleResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def respuesta_enviar_a_revision(
    body: EnviarRevisionRequest, request: Request,
    respuesta_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RespuestaPqrsdDetalleResponse:
    try:
        row = await svc.enviar_respuesta_a_revision(
            conn, tenant_id=perfil.tenant_id, respuesta_id=respuesta_id,
            usuario_actor_id=perfil.user_id,
            observaciones=body.observaciones,
        )
    except ValueError as e:
        raise _validar_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn,
        tipo_evento='RespuestaEnviadaARevision',
        accion='enviar_a_revision',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='respuesta_pqrsd',
        entidad_afectada_id=respuesta_id,
        justificacion=body.observaciones,
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return RespuestaPqrsdDetalleResponse(**row)


@router_respuestas.post(
    '/{respuesta_id}/revisar',
    response_model=RespuestaPqrsdDetalleResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def respuesta_revisar(
    body: RevisarRespuestaRequest, request: Request,
    respuesta_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RespuestaPqrsdDetalleResponse:
    try:
        row = await svc.revisar_respuesta(
            conn, tenant_id=perfil.tenant_id, respuesta_id=respuesta_id,
            resultado=body.resultado, observaciones=body.observaciones,
            usuario_actor_id=perfil.user_id,
        )
    except PermissionError as e:
        raise _validar_separacion(e) from e
    except ValueError as e:
        raise _validar_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    tipo = 'RespuestaDevuelta' if body.resultado == 'devolver' else 'RespuestaAprobada'
    await emit_gd_event(
        conn,
        tipo_evento=tipo,
        accion='revisar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='respuesta_pqrsd',
        entidad_afectada_id=respuesta_id,
        valor_nuevo={'resultado': body.resultado},
        justificacion=body.observaciones,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return RespuestaPqrsdDetalleResponse(**row)


@router_respuestas.post(
    '/{respuesta_id}/aprobar',
    response_model=RespuestaPqrsdDetalleResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def respuesta_aprobar(
    body: AprobarRespuestaRequest, request: Request,
    respuesta_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RespuestaPqrsdDetalleResponse:
    try:
        row = await svc.aprobar_respuesta(
            conn, tenant_id=perfil.tenant_id, respuesta_id=respuesta_id,
            usuario_actor_id=perfil.user_id, observaciones=body.observaciones,
        )
    except PermissionError as e:
        raise _validar_separacion(e) from e
    except ValueError as e:
        raise _validar_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn,
        tipo_evento='RespuestaAprobada',
        accion='aprobar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='respuesta_pqrsd',
        entidad_afectada_id=respuesta_id,
        justificacion=body.observaciones,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return RespuestaPqrsdDetalleResponse(**row)


@router_respuestas.post(
    '/{respuesta_id}/firmar',
    response_model=RespuestaPqrsdDetalleResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def respuesta_firmar(
    body: FirmarRespuestaRequest, request: Request,
    respuesta_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RespuestaPqrsdDetalleResponse:
    try:
        row = await svc.firmar_respuesta(
            conn, tenant_id=perfil.tenant_id, respuesta_id=respuesta_id,
            usuario_actor_id=perfil.user_id, firma_id=body.firma_id,
        )
    except PermissionError as e:
        raise _validar_separacion(e) from e
    except ValueError as e:
        raise _validar_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn,
        tipo_evento='RespuestaFirmada',
        accion='firmar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='respuesta_pqrsd',
        entidad_afectada_id=respuesta_id,
        valor_nuevo={'firma_id': str(body.firma_id) if body.firma_id else None},
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return RespuestaPqrsdDetalleResponse(**row)


@router_respuestas.post(
    '/{respuesta_id}/radicar-salida',
    response_model=RespuestaPqrsdDetalleResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def respuesta_radicar_salida(
    body: RadicarSalidaRequest, request: Request,
    respuesta_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RespuestaPqrsdDetalleResponse:
    try:
        row = await svc.radicar_salida_respuesta(
            conn, tenant_id=perfil.tenant_id, respuesta_id=respuesta_id,
            usuario_actor_id=perfil.user_id, canal_envio_id=body.canal_envio_id,
        )
    except ValueError as e:
        raise _validar_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn,
        tipo_evento='RespuestaRadicada',
        accion='radicar_salida',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='respuesta_pqrsd',
        entidad_afectada_id=respuesta_id,
        valor_nuevo={'radicado_salida_id': str(row.get('radicado_salida_id'))},
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return RespuestaPqrsdDetalleResponse(**row)


@router_respuestas.post(
    '/{respuesta_id}/enviar',
    response_model=RespuestaPqrsdDetalleResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def respuesta_enviar(
    body: EnviarRespuestaRequest, request: Request,
    respuesta_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RespuestaPqrsdDetalleResponse:
    try:
        row = await svc.enviar_respuesta(
            conn, tenant_id=perfil.tenant_id, respuesta_id=respuesta_id,
            usuario_actor_id=perfil.user_id,
            canal_envio_id=body.canal_envio_id,
            constancia_envio_uri=body.constancia_envio_uri,
        )
    except ValueError as e:
        raise _validar_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn,
        tipo_evento='RespuestaEnviada',
        accion='enviar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='respuesta_pqrsd',
        entidad_afectada_id=respuesta_id,
        valor_nuevo={'canal_envio_id': str(body.canal_envio_id) if body.canal_envio_id else None,
                      'constancia_uri': body.constancia_envio_uri},
        justificacion=body.observaciones,
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return RespuestaPqrsdDetalleResponse(**row)


# --- GD-API-0051: dashboard (router_dashboard se monta ANTES de router en
# routes.py para que no colisione con /{pqrsd_id}) ---

@router_dashboard.get(
    '/dashboard',
    response_model=DashboardPqrsdResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def get_dashboard_pqrsd(
    request: Request,
    dependencia_id: UUID | None = Query(default=None),
    desde: datetime | None = Query(default=None),
    hasta: datetime | None = Query(default=None),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> DashboardPqrsdResponse:
    data = await svc.dashboard_pqrsd(
        conn, tenant_id=perfil.tenant_id, dependencia_id=dependencia_id,
        desde=desde, hasta=hasta,
    )
    return DashboardPqrsdResponse(
        total_global=data['total_global'],
        total_vencidas=data['total_vencidas'],
        total_proximas_vencer=data['total_proximas_vencer'],
        total_cerradas=data['total_cerradas'],
        buckets=[DashboardPqrsdBucket(**b) for b in data['buckets']],
        desde=desde, hasta=hasta, dependencia_id_filtro=dependencia_id,
    )


# --- GD-API-0048: cerrar / reabrir ---

@router.post(
    '/{pqrsd_id}/cerrar',
    response_model=PqrsdResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def cerrar_pqrsd(
    body: CerrarPqrsdRequest, request: Request,
    pqrsd_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PqrsdResponse:
    try:
        row = await svc.cerrar_pqrsd(
            conn, tenant_id=perfil.tenant_id, pqrsd_id=pqrsd_id,
            motivo=body.motivo, usuario_actor_id=perfil.user_id,
            forzar_sin_respuesta=body.forzar_sin_respuesta,
        )
    except ValueError as e:
        raise _validar_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn,
        tipo_evento='PQRSDCerrada',
        accion='cerrar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='pqrsd', entidad_afectada_id=pqrsd_id,
        valor_nuevo={'forzar_sin_respuesta': body.forzar_sin_respuesta},
        justificacion=body.motivo,
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return PqrsdResponse(**row)


@router.post(
    '/{pqrsd_id}/reabrir',
    response_model=PqrsdResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def reabrir_pqrsd(
    body: ReabrirPqrsdRequest, request: Request,
    pqrsd_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PqrsdResponse:
    try:
        row = await svc.reabrir_pqrsd(
            conn, tenant_id=perfil.tenant_id, pqrsd_id=pqrsd_id,
            motivo=body.motivo, dias_adicionales=body.dias_adicionales,
            usuario_actor_id=perfil.user_id,
        )
    except ValueError as e:
        raise _validar_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn,
        tipo_evento='PQRSDReabierta',
        accion='reabrir',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='pqrsd', entidad_afectada_id=pqrsd_id,
        valor_nuevo={'dias_adicionales': body.dias_adicionales},
        justificacion=body.motivo,
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return PqrsdResponse(**row)


# --- GD-API-0049: traslado por competencia ---

@router.post(
    '/{pqrsd_id}/trasladar-competencia',
    response_model=PqrsdResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def trasladar_competencia(
    body: TrasladarCompetenciaRequest, request: Request,
    pqrsd_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PqrsdResponse:
    try:
        row = await svc.trasladar_competencia(
            conn, tenant_id=perfil.tenant_id, pqrsd_id=pqrsd_id,
            entidad_competente_destino=body.entidad_competente_destino,
            motivo=body.motivo, usuario_actor_id=perfil.user_id,
            oficio_traslado_radicado_id=body.oficio_traslado_radicado_id,
        )
    except ValueError as e:
        raise _validar_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn,
        tipo_evento='PQRSDTrasladada',
        accion='trasladar_competencia',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='pqrsd', entidad_afectada_id=pqrsd_id,
        valor_nuevo={'entidad_competente_destino': body.entidad_competente_destino,
                      'oficio_traslado_radicado_id': str(body.oficio_traslado_radicado_id)
                                                      if body.oficio_traslado_radicado_id else None},
        justificacion=body.motivo,
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return PqrsdResponse(**row)


# --- GD-API-0050: solicitar información adicional ---

@router.post(
    '/{pqrsd_id}/solicitar-info-adicional',
    response_model=EventoTerminoResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def solicitar_info_adicional(
    body: SolicitarInfoAdicionalRequest, request: Request,
    pqrsd_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> EventoTerminoResponse:
    try:
        row = await svc.solicitar_info_adicional(
            conn, tenant_id=perfil.tenant_id, pqrsd_id=pqrsd_id,
            motivo=body.motivo,
            informacion_solicitada=body.informacion_solicitada,
            dias_estimados_suspension=body.dias_estimados_suspension,
            usuario_actor_id=perfil.user_id,
        )
    except ValueError as e:
        raise _validar_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn,
        tipo_evento='gd.pqrsd.solicitud_info_adicional',
        accion='solicitar_info_adicional',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='pqrsd', entidad_afectada_id=pqrsd_id,
        valor_nuevo={'dias_estimados': body.dias_estimados_suspension,
                      'informacion': body.informacion_solicitada},
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return EventoTerminoResponse(**row)


__all__ = ['router', 'router_respuestas', 'router_dashboard']
