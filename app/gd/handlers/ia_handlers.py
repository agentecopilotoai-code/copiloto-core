"""Handlers HTTP de EP-013 agentes IA asistidos (bloque 14).

Endpoints (11):
- POST /api/v1/gd/ia/clasificar                           GD-API-0078
- POST /api/v1/gd/ia/extraer                              GD-API-0079
- POST /api/v1/gd/ia/resumir                              GD-API-0080
- POST /api/v1/gd/ia/sugerir-dependencia                  GD-API-0081
- POST /api/v1/gd/ia/detectar-duplicados                  GD-API-0082
- POST /api/v1/gd/ia/borrador-respuesta                   GD-API-0083
- POST /api/v1/gd/ia/sugerir-termino                      GD-API-0077
- GET  /api/v1/gd/ia/solicitudes/{id}                     (detalle)
- GET  /api/v1/gd/ia/resultados/{id}                      (detalle)
- POST /api/v1/gd/ia/sugerencias/{resultado_id}/decidir   GD-API-0084
- GET  /api/v1/gd/ia/trazabilidad                         GD-API-0085

NOTA: el "encolar" y "ejecutar" se hacen sync en el mismo request por
simplicidad (worker in-process). En producción el ejecutar va a un job
queue y el endpoint devuelve solicitud_id inmediatamente con estado=pending.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.ia import (
    BorradorRespuestaRequest,
    ClasificarRequest,
    DecidirSugerenciaRequest,
    DecisionIAResponse,
    DetectarDuplicadosRequest,
    ExtraerDatosRequest,
    ResultadoIAResponse,
    ResumirRequest,
    SolicitudIACompleta,
    SolicitudIAResponse,
    SugerirDependenciaRequest,
    SugerirTerminoRequest,
    TrazabilidadIAResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil
from app.gd.services import ia as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router = APIRouter(prefix='/ia', tags=['gd:ia'])


def _err_estado(e: ValueError) -> HTTPException:
    return HTTPException(409, detail={'error': 'conflict', 'code': str(e)})


async def _orquestar_solicitud(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    tipo_asistencia: str,
    entidad_origen_tipo: str,
    entidad_origen_id: UUID,
    payload: dict[str, Any],
    extra_kwargs: dict[str, Any] | None,
    solicitante_user_id: UUID,
    request_id: UUID | None,
) -> dict[str, Any]:
    """Helper que encola + ejecuta + emite eventos."""
    sol = await svc.encolar_solicitud(
        conn, tenant_id=tenant_id, tipo_asistencia=tipo_asistencia,
        entidad_origen_tipo=entidad_origen_tipo,
        entidad_origen_id=entidad_origen_id,
        payload_original=payload, solicitante_user_id=solicitante_user_id,
    )
    await emit_gd_event(
        conn, tipo_evento='IASolicitada', accion='encolar',
        tenant_id=tenant_id, usuario_id=solicitante_user_id,
        entidad_afectada_tipo='solicitud_ia', entidad_afectada_id=sol['id'],
        valor_nuevo={'tipo_asistencia': tipo_asistencia,
                      'entidad_origen_tipo': entidad_origen_tipo,
                      'redacciones': len(sol['redacciones_aplicadas'])},
        criticidad=AuditCriticidad.BAJA,
        request_id=request_id,
    )

    # Ejecutar (sync para tests; async/queue en prod).
    exec_result = await svc.ejecutar_solicitud(
        conn, tenant_id=tenant_id, solicitud_id=sol['id'],
        extra_kwargs=extra_kwargs, provider=None,
    )

    resultado = exec_result.get('resultado') if exec_result else None
    if resultado:
        await emit_gd_event(
            conn, tipo_evento='IASugerenciaGenerada', accion='sugerir',
            tenant_id=tenant_id, usuario_id=solicitante_user_id,
            entidad_afectada_tipo='resultado_ia',
            entidad_afectada_id=resultado['id'],
            valor_nuevo={'tipo_asistencia': tipo_asistencia,
                          'confianza': resultado.get('confianza')},
            criticidad=AuditCriticidad.MEDIA,
            request_id=request_id,
        )

    # Refrescar solicitud para devolver estado final.
    sol_final = await svc.obtener_solicitud(
        conn, tenant_id=tenant_id, solicitud_id=sol['id'],
    )
    return {
        'solicitud': sol_final,
        'resultado': resultado,
        'decision': None,
    }


# =============================================================================
# Endpoints por tipo de asistencia (GD-API-0078..0083, 0077-sugerir-termino)
# =============================================================================

@router.post(
    '/clasificar',
    response_model=SolicitudIACompleta,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def clasificar(
    body: ClasificarRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> SolicitudIACompleta:
    # Buscar texto del radicado/entidad. Stub: usamos id como hint.
    payload = {'entidad_origen_id': str(body.entidad_origen_id),
                'texto': body.model_dump().get('texto', '')}
    r = await _orquestar_solicitud(
        conn, tenant_id=perfil.tenant_id, tipo_asistencia='clasificacion',
        entidad_origen_tipo=body.entidad_origen_tipo,
        entidad_origen_id=body.entidad_origen_id,
        payload=payload, extra_kwargs=None,
        solicitante_user_id=perfil.user_id,
        request_id=getattr(request.state, 'request_id', None),
    )
    return SolicitudIACompleta(
        solicitud=SolicitudIAResponse(**r['solicitud']),
        resultado=ResultadoIAResponse(**r['resultado']) if r['resultado'] else None,
    )


@router.post(
    '/extraer',
    response_model=SolicitudIACompleta,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def extraer(
    body: ExtraerDatosRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> SolicitudIACompleta:
    payload = {'entidad_origen_id': str(body.entidad_origen_id), 'texto': ''}
    r = await _orquestar_solicitud(
        conn, tenant_id=perfil.tenant_id, tipo_asistencia='extraccion',
        entidad_origen_tipo=body.entidad_origen_tipo,
        entidad_origen_id=body.entidad_origen_id,
        payload=payload, extra_kwargs=None,
        solicitante_user_id=perfil.user_id,
        request_id=getattr(request.state, 'request_id', None),
    )
    return SolicitudIACompleta(
        solicitud=SolicitudIAResponse(**r['solicitud']),
        resultado=ResultadoIAResponse(**r['resultado']) if r['resultado'] else None,
    )


@router.post(
    '/resumir',
    response_model=SolicitudIACompleta,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def resumir(
    body: ResumirRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> SolicitudIACompleta:
    payload = {'entidad_origen_id': str(body.entidad_origen_id), 'texto': ''}
    r = await _orquestar_solicitud(
        conn, tenant_id=perfil.tenant_id, tipo_asistencia='resumen',
        entidad_origen_tipo=body.entidad_origen_tipo,
        entidad_origen_id=body.entidad_origen_id,
        payload=payload,
        extra_kwargs={'max_caracteres': body.max_caracteres},
        solicitante_user_id=perfil.user_id,
        request_id=getattr(request.state, 'request_id', None),
    )
    return SolicitudIACompleta(
        solicitud=SolicitudIAResponse(**r['solicitud']),
        resultado=ResultadoIAResponse(**r['resultado']) if r['resultado'] else None,
    )


@router.post(
    '/sugerir-dependencia',
    response_model=SolicitudIACompleta,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def sugerir_dependencia(
    body: SugerirDependenciaRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> SolicitudIACompleta:
    payload = {'entidad_origen_id': str(body.entidad_origen_id)}
    r = await _orquestar_solicitud(
        conn, tenant_id=perfil.tenant_id,
        tipo_asistencia='sugerencia_dependencia',
        entidad_origen_tipo=body.entidad_origen_tipo,
        entidad_origen_id=body.entidad_origen_id,
        payload=payload, extra_kwargs=None,
        solicitante_user_id=perfil.user_id,
        request_id=getattr(request.state, 'request_id', None),
    )
    return SolicitudIACompleta(
        solicitud=SolicitudIAResponse(**r['solicitud']),
        resultado=ResultadoIAResponse(**r['resultado']) if r['resultado'] else None,
    )


@router.post(
    '/detectar-duplicados',
    response_model=SolicitudIACompleta,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def detectar_duplicados(
    body: DetectarDuplicadosRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> SolicitudIACompleta:
    payload = {'entidad_origen_id': str(body.entidad_origen_id),
                'candidatos_recientes': []}
    r = await _orquestar_solicitud(
        conn, tenant_id=perfil.tenant_id,
        tipo_asistencia='deteccion_duplicados',
        entidad_origen_tipo=body.entidad_origen_tipo,
        entidad_origen_id=body.entidad_origen_id,
        payload=payload,
        extra_kwargs={'top_k': body.top_k},
        solicitante_user_id=perfil.user_id,
        request_id=getattr(request.state, 'request_id', None),
    )
    return SolicitudIACompleta(
        solicitud=SolicitudIAResponse(**r['solicitud']),
        resultado=ResultadoIAResponse(**r['resultado']) if r['resultado'] else None,
    )


@router.post(
    '/borrador-respuesta',
    response_model=SolicitudIACompleta,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def borrador_respuesta(
    body: BorradorRespuestaRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> SolicitudIACompleta:
    payload = {'entidad_origen_id': str(body.entidad_origen_id),
                'plantilla_id': str(body.plantilla_id) if body.plantilla_id else None}
    r = await _orquestar_solicitud(
        conn, tenant_id=perfil.tenant_id,
        tipo_asistencia='borrador_respuesta',
        entidad_origen_tipo=body.entidad_origen_tipo,
        entidad_origen_id=body.entidad_origen_id,
        payload=payload, extra_kwargs=None,
        solicitante_user_id=perfil.user_id,
        request_id=getattr(request.state, 'request_id', None),
    )
    return SolicitudIACompleta(
        solicitud=SolicitudIAResponse(**r['solicitud']),
        resultado=ResultadoIAResponse(**r['resultado']) if r['resultado'] else None,
    )


@router.post(
    '/sugerir-termino',
    response_model=SolicitudIACompleta,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def sugerir_termino(
    body: SugerirTerminoRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> SolicitudIACompleta:
    payload = {'entidad_origen_id': str(body.entidad_origen_id),
                'tipo_pqrsd_codigo': ''}
    r = await _orquestar_solicitud(
        conn, tenant_id=perfil.tenant_id,
        tipo_asistencia='sugerencia_termino',
        entidad_origen_tipo=body.entidad_origen_tipo,
        entidad_origen_id=body.entidad_origen_id,
        payload=payload, extra_kwargs=None,
        solicitante_user_id=perfil.user_id,
        request_id=getattr(request.state, 'request_id', None),
    )
    return SolicitudIACompleta(
        solicitud=SolicitudIAResponse(**r['solicitud']),
        resultado=ResultadoIAResponse(**r['resultado']) if r['resultado'] else None,
    )


# =============================================================================
# Lectura
# =============================================================================

@router.get(
    '/solicitudes/{solicitud_id}',
    response_model=SolicitudIAResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def detalle_solicitud(
    solicitud_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> SolicitudIAResponse:
    row = await svc.obtener_solicitud(
        conn, tenant_id=perfil.tenant_id, solicitud_id=solicitud_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return SolicitudIAResponse(**row)


@router.get(
    '/resultados/{resultado_id}',
    response_model=ResultadoIAResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def detalle_resultado(
    resultado_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ResultadoIAResponse:
    row = await svc.obtener_resultado(
        conn, tenant_id=perfil.tenant_id, resultado_id=resultado_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return ResultadoIAResponse(**row)


# =============================================================================
# Decisión humana (GD-API-0084)
# =============================================================================

@router.post(
    '/sugerencias/{resultado_id}/decidir',
    response_model=DecisionIAResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def decidir(
    body: DecidirSugerenciaRequest, request: Request,
    resultado_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> DecisionIAResponse:
    try:
        row = await svc.decidir_sugerencia(
            conn, tenant_id=perfil.tenant_id, resultado_id=resultado_id,
            decision=body.decision,
            contenido_modificado=body.contenido_modificado,
            observaciones=body.observaciones,
            decided_by_user_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    tipo_evento_map = {
        'aceptar': 'IASugerenciaAceptada',
        'modificar': 'IASugerenciaModificada',
        'rechazar': 'IASugerenciaRechazada',
    }
    await emit_gd_event(
        conn, tipo_evento=tipo_evento_map[body.decision], accion='decidir',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='decision_ia', entidad_afectada_id=row['id'],
        valor_nuevo={'resultado_id': str(resultado_id),
                      'decision': body.decision},
        justificacion=body.observaciones,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return DecisionIAResponse(**row)


# =============================================================================
# Trazabilidad (GD-API-0085)
# =============================================================================

@router.get(
    '/trazabilidad',
    response_model=TrazabilidadIAResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def trazabilidad(
    entidad_tipo: str = Query(..., pattern='^(radicado|pqrsd|correspondencia|documento|correo_importado)$'),
    entidad_id: UUID = Query(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TrazabilidadIAResponse:
    historial = await svc.obtener_trazabilidad(
        conn, tenant_id=perfil.tenant_id,
        entidad_origen_tipo=entidad_tipo, entidad_origen_id=entidad_id,
    )
    items = [
        SolicitudIACompleta(
            solicitud=SolicitudIAResponse(**h['solicitud']),
            resultado=ResultadoIAResponse(**h['resultado']) if h['resultado'] else None,
            decision=DecisionIAResponse(**h['decision']) if h['decision'] else None,
        )
        for h in historial
    ]
    return TrazabilidadIAResponse(
        entidad_origen_tipo=entidad_tipo,
        entidad_origen_id=entidad_id,
        historial=items, total=len(items),
    )


__all__ = ['router']
