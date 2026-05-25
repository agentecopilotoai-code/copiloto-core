"""Handlers HTTP de EP-014 reportes (bloque 15).

Endpoints (16):
Reportes GET (sin export, vista preliminar):
- GET /api/v1/gd/reportes/radicados                              GD-API-0087
- GET /api/v1/gd/reportes/pqrsd                                  GD-API-0088
- GET /api/v1/gd/reportes/correspondencia                        GD-API-0089
- GET /api/v1/gd/reportes/cargas                                 GD-API-0090
- GET /api/v1/gd/reportes/uso-ia                                 GD-API-0091
- GET /api/v1/gd/reportes/anulaciones                            GD-API-0092
- GET /api/v1/gd/reportes/auditoria                              GD-API-0093

Export con auditoría (GD-API-0094):
- POST /api/v1/gd/reportes/radicados/exportar
- POST /api/v1/gd/reportes/pqrsd/exportar
- POST /api/v1/gd/reportes/correspondencia/exportar
- POST /api/v1/gd/reportes/cargas/exportar
- POST /api/v1/gd/reportes/uso-ia/exportar
- POST /api/v1/gd/reportes/anulaciones/exportar
- POST /api/v1/gd/reportes/auditoria/exportar

Lectura registros:
- GET /api/v1/gd/reportes/generados
- GET /api/v1/gd/reportes/generados/{id}
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.reportes import (
    ExportarRequest,
    ReporteAnulacionesFila,
    ReporteAnulacionesResponse,
    ReporteAuditoriaFila,
    ReporteAuditoriaResponse,
    ReporteCargasFila,
    ReporteCargasResponse,
    ReporteCorrespondenciaFila,
    ReporteCorrespondenciaResponse,
    ReporteGeneradoListResponse,
    ReporteGeneradoResponse,
    ReportePqrsdFila,
    ReportePqrsdResponse,
    ReporteRadicadosFila,
    ReporteRadicadosResponse,
    ReporteUsoIAFila,
    ReporteUsoIAResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil
from app.gd.services import reportes as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router = APIRouter(prefix='/reportes', tags=['gd:reportes'])


def _err_validacion(e: ValueError) -> HTTPException:
    return HTTPException(
        422, detail={'error': 'validation_error', 'code': str(e)},
    )


async def _emit_export(
    conn, *, perfil, request, registro: dict[str, Any], tipo_reporte: str,
):
    """Emite evento RNF-054 al exportar."""
    criticidad = (
        AuditCriticidad.ALTA if registro['contiene_datos_sensibles']
        else AuditCriticidad.MEDIA
    )
    await emit_gd_event(
        conn, tipo_evento='ReporteGenerado', accion='exportar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='reporte_generado',
        entidad_afectada_id=registro['id'],
        valor_nuevo={'tipo': tipo_reporte, 'formato': registro['formato'],
                      'filas': registro['numero_filas'],
                      'sensible': registro['contiene_datos_sensibles']},
        criticidad=criticidad,
        request_id=getattr(request.state, 'request_id', None),
    )


# =============================================================================
# Reportes GET
# =============================================================================

@router.get(
    '/radicados',
    response_model=ReporteRadicadosResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def get_radicados(
    desde: datetime | None = Query(default=None),
    hasta: datetime | None = Query(default=None),
    canal_id: UUID | None = Query(default=None),
    dependencia_id: UUID | None = Query(default=None),
    tipo_radicado: str | None = Query(default=None),
    estado: str | None = Query(default=None),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ReporteRadicadosResponse:
    data = await svc.reporte_radicados(
        conn, tenant_id=perfil.tenant_id,
        desde=desde, hasta=hasta, canal_id=canal_id,
        dependencia_id=dependencia_id, tipo_radicado=tipo_radicado,
        estado=estado,
    )
    return ReporteRadicadosResponse(
        total_radicados=data['total_radicados'],
        filas=[ReporteRadicadosFila(**f) for f in data['filas']],
        filtros_aplicados={'desde': desde.isoformat() if desde else None,
                            'hasta': hasta.isoformat() if hasta else None,
                            'canal_id': str(canal_id) if canal_id else None,
                            'dependencia_id': str(dependencia_id) if dependencia_id else None,
                            'tipo_radicado': tipo_radicado, 'estado': estado},
    )


@router.get(
    '/pqrsd',
    response_model=ReportePqrsdResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def get_pqrsd(
    desde: datetime | None = Query(default=None),
    hasta: datetime | None = Query(default=None),
    dependencia_id: UUID | None = Query(default=None),
    tipo_pqrsd_id: UUID | None = Query(default=None),
    estado: str | None = Query(default=None),
    solo_vencidas: bool = Query(default=False),
    solo_proximas_vencer: bool = Query(default=False),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ReportePqrsdResponse:
    data = await svc.reporte_pqrsd(
        conn, tenant_id=perfil.tenant_id,
        desde=desde, hasta=hasta,
        dependencia_id=dependencia_id, tipo_pqrsd_id=tipo_pqrsd_id,
        estado=estado, solo_vencidas=solo_vencidas,
        solo_proximas_vencer=solo_proximas_vencer,
    )
    return ReportePqrsdResponse(
        total_global=data['total_global'],
        total_vencidas=data['total_vencidas'],
        total_proximas_vencer=data['total_proximas_vencer'],
        total_cerradas=data['total_cerradas'],
        filas=[ReportePqrsdFila(**f) for f in data['filas']],
    )


@router.get(
    '/correspondencia',
    response_model=ReporteCorrespondenciaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def get_correspondencia(
    desde: datetime | None = Query(default=None),
    hasta: datetime | None = Query(default=None),
    tipo: str | None = Query(default=None),
    dependencia_id: UUID | None = Query(default=None),
    estado: str | None = Query(default=None),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ReporteCorrespondenciaResponse:
    data = await svc.reporte_correspondencia(
        conn, tenant_id=perfil.tenant_id,
        desde=desde, hasta=hasta, tipo=tipo,
        dependencia_id=dependencia_id, estado=estado,
    )
    return ReporteCorrespondenciaResponse(
        total=data['total'],
        filas=[ReporteCorrespondenciaFila(**f) for f in data['filas']],
    )


@router.get(
    '/cargas',
    response_model=ReporteCargasResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def get_cargas(
    desde: datetime | None = Query(default=None),
    hasta: datetime | None = Query(default=None),
    dependencia_id: UUID | None = Query(default=None),
    user_id: UUID | None = Query(default=None),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ReporteCargasResponse:
    data = await svc.reporte_cargas(
        conn, tenant_id=perfil.tenant_id,
        desde=desde, hasta=hasta,
        dependencia_id=dependencia_id, user_id=user_id,
    )
    return ReporteCargasResponse(
        filas=[ReporteCargasFila(**f) for f in data['filas']],
    )


@router.get(
    '/uso-ia',
    response_model=ReporteUsoIAResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def get_uso_ia(
    desde: datetime | None = Query(default=None),
    hasta: datetime | None = Query(default=None),
    tipo_asistencia: str | None = Query(default=None),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ReporteUsoIAResponse:
    data = await svc.reporte_uso_ia(
        conn, tenant_id=perfil.tenant_id,
        desde=desde, hasta=hasta, tipo_asistencia=tipo_asistencia,
    )
    return ReporteUsoIAResponse(
        total_solicitudes=data['total_solicitudes'],
        filas=[ReporteUsoIAFila(**f) for f in data['filas']],
    )


@router.get(
    '/anulaciones',
    response_model=ReporteAnulacionesResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def get_anulaciones(
    desde: datetime | None = Query(default=None),
    hasta: datetime | None = Query(default=None),
    tipo_entidad: str | None = Query(default=None),
    decision: str | None = Query(default=None),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ReporteAnulacionesResponse:
    data = await svc.reporte_anulaciones(
        conn, tenant_id=perfil.tenant_id,
        desde=desde, hasta=hasta,
        tipo_entidad=tipo_entidad, decision=decision,
    )
    return ReporteAnulacionesResponse(
        filas=[ReporteAnulacionesFila(**f) for f in data['filas']],
    )


@router.get(
    '/auditoria',
    response_model=ReporteAuditoriaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def get_auditoria(
    desde: datetime | None = Query(default=None),
    hasta: datetime | None = Query(default=None),
    usuario_id: UUID | None = Query(default=None),
    entidad_tipo: str | None = Query(default=None),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ReporteAuditoriaResponse:
    data = await svc.reporte_auditoria(
        conn, tenant_id=perfil.tenant_id,
        desde=desde, hasta=hasta,
        usuario_id=usuario_id, entidad_tipo=entidad_tipo,
    )
    return ReporteAuditoriaResponse(
        total=data['total'],
        filas=[ReporteAuditoriaFila(**f) for f in data['filas']],
    )


# =============================================================================
# Exportar (GD-API-0094)
# =============================================================================

async def _exportar(
    conn, perfil, request, body: ExportarRequest, tipo_reporte: str,
) -> ReporteGeneradoResponse:
    try:
        registro = await svc.exportar_reporte(
            conn, tenant_id=perfil.tenant_id,
            tipo_reporte=tipo_reporte, formato=body.formato,
            filtros=body.filtros,
            incluir_datos_sensibles=body.incluir_datos_sensibles,
            generado_por_user_id=perfil.user_id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get('user-agent'),
        )
    except ValueError as e:
        raise _err_validacion(e) from e
    await _emit_export(
        conn, perfil=perfil, request=request,
        registro=registro, tipo_reporte=tipo_reporte,
    )
    return ReporteGeneradoResponse(**registro)


@router.post(
    '/radicados/exportar',
    response_model=ReporteGeneradoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def exportar_radicados(
    body: ExportarRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ReporteGeneradoResponse:
    return await _exportar(conn, perfil, request, body, 'radicados')


@router.post(
    '/pqrsd/exportar',
    response_model=ReporteGeneradoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def exportar_pqrsd(
    body: ExportarRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ReporteGeneradoResponse:
    return await _exportar(conn, perfil, request, body, 'pqrsd')


@router.post(
    '/correspondencia/exportar',
    response_model=ReporteGeneradoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def exportar_correspondencia(
    body: ExportarRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ReporteGeneradoResponse:
    return await _exportar(conn, perfil, request, body, 'correspondencia')


@router.post(
    '/cargas/exportar',
    response_model=ReporteGeneradoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def exportar_cargas(
    body: ExportarRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ReporteGeneradoResponse:
    return await _exportar(conn, perfil, request, body, 'cargas_trabajo')


@router.post(
    '/uso-ia/exportar',
    response_model=ReporteGeneradoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def exportar_uso_ia(
    body: ExportarRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ReporteGeneradoResponse:
    return await _exportar(conn, perfil, request, body, 'uso_ia')


@router.post(
    '/anulaciones/exportar',
    response_model=ReporteGeneradoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def exportar_anulaciones(
    body: ExportarRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ReporteGeneradoResponse:
    return await _exportar(conn, perfil, request, body,
                            'anulaciones_reasignaciones')


@router.post(
    '/auditoria/exportar',
    response_model=ReporteGeneradoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def exportar_auditoria(
    body: ExportarRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ReporteGeneradoResponse:
    return await _exportar(conn, perfil, request, body,
                            'auditoria_consultas_sensibles')


# =============================================================================
# Lectura de registros generados
# =============================================================================

@router.get(
    '/generados',
    response_model=ReporteGeneradoListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_generados(
    tipo_reporte: str | None = Query(default=None),
    generado_por_user_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ReporteGeneradoListResponse:
    rows = await svc.listar_reportes_generados(
        conn, tenant_id=perfil.tenant_id,
        tipo_reporte=tipo_reporte,
        generado_por_user_id=generado_por_user_id, limit=limit,
    )
    items = [ReporteGeneradoResponse(**r) for r in rows]
    return ReporteGeneradoListResponse(items=items, total=len(items))


@router.get(
    '/generados/{reporte_id}',
    response_model=ReporteGeneradoResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def detalle_generado(
    reporte_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ReporteGeneradoResponse:
    row = await svc.obtener_reporte_generado(
        conn, tenant_id=perfil.tenant_id, reporte_id=reporte_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return ReporteGeneradoResponse(**row)


# ──────────────────────────────────────────────────────────────────────────
# Reportes "consolidados" — vista unificada que agrega los counters de
# cada categoría (anulaciones, auditoria, cargas, correspondencia, pqrsd,
# radicados, uso-ia) en una sola response. Útil para dashboards
# ejecutivos donde no se necesita el detalle de cada tipo.
# Stub mínimo: estructura coherente con counts en 0 cuando no hay data,
# para que el UI no rompa y pueda iterar sin bloquearse en el backend.
# Próxima iteración: query real agregando datos de cada svc.
# ──────────────────────────────────────────────────────────────────────────


@router.get(
    '/consolidados',
    dependencies=[Depends(require_gd_perfil)],
    summary='Vista consolidada de reportes (counts por categoría)',
)
async def reportes_consolidados(
    desde: str | None = Query(default=None, description='YYYY-MM-DD'),
    hasta: str | None = Query(default=None, description='YYYY-MM-DD'),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    """Devuelve counters agregados por categoría — vista ejecutiva.

    Response shape estable que la UI puede consumir aunque el desglose
    interno cambie. Cada `count` es 0 cuando no hay data en la ventana.
    """
    # TODO(GD-API-future): reemplazar con query real cuando se priorice
    # el dashboard ejecutivo. Por ahora respuesta estable + vacía.
    return {
        'desde': desde,
        'hasta': hasta,
        'categorias': {
            'radicados': {'total': 0},
            'pqrsd': {'total': 0},
            'correspondencia': {'total': 0},
            'cargas': {'total': 0},
            'anulaciones': {'total': 0},
            'auditoria': {'total': 0},
            'uso_ia': {'total': 0, 'tokens': 0, 'costo_usd': 0},
        },
    }


@router.post(
    '/consolidados/exportar',
    dependencies=[Depends(require_gd_perfil)],
    summary='Exportar reporte consolidado (XLSX/CSV/PDF) — stub',
)
async def exportar_consolidado(
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
) -> dict[str, str]:
    """Stub — devuelve estructura indicando que la exportación está
    pendiente de implementar. UI debe mostrar mensaje informativo."""
    return {
        'status': 'not_implemented',
        'message': 'Exportación consolidada pendiente. Use los exportadores '
                   'individuales por categoría (anulaciones, pqrsd, etc).',
    }


@router.post(
    '/ejecutivo/pdf',
    dependencies=[Depends(require_gd_perfil)],
    summary='PDF ejecutivo consolidado — stub',
)
async def reporte_ejecutivo_pdf(
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
) -> dict[str, str]:
    """Stub del PDF ejecutivo. Responde 200 con marker para que la UI
    no rompa; renderizado real queda como follow-up."""
    return {
        'status': 'not_implemented',
        'message': 'Generación de PDF ejecutivo pendiente.',
    }


__all__ = ['router']
