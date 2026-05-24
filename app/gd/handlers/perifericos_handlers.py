"""Handlers HTTP para EP-021 periféricos parte 1 (bloque 21a).

Endpoints (GD-API-0128..0135):

Puntos de atención (GD-API-0130):
- POST   /api/v1/gd/puntos-atencion
- GET    /api/v1/gd/puntos-atencion
- GET    /api/v1/gd/puntos-atencion/{id}
- PATCH  /api/v1/gd/puntos-atencion/{id}
- POST   /api/v1/gd/puntos-atencion/{id}/activar | inactivar | cerrar
- GET    /api/v1/gd/puntos-atencion/{id}/perifericos

Periféricos (GD-API-0129):
- POST   /api/v1/gd/perifericos
- GET    /api/v1/gd/perifericos
- GET    /api/v1/gd/perifericos/{id}
- PATCH  /api/v1/gd/perifericos/{id}
- POST   /api/v1/gd/perifericos/{id}/activar | inactivar | poner-mantenimiento | retirar

Códigos barras/QR (GD-API-0131):
- POST   /api/v1/gd/radicados/{id}/codigo-barras
- GET    /api/v1/gd/radicados/{id}/codigo-barras
- POST   /api/v1/gd/radicados/{id}/codigo-barras/{cod_id}/anular

Impresión (GD-API-0132/0133/0134):
- POST   /api/v1/gd/perifericos/{id}/imprimir-etiqueta
- POST   /api/v1/gd/perifericos/{id}/reimprimir-etiqueta
- POST   /api/v1/gd/perifericos/{id}/imprimir-constancia
- POST   /api/v1/gd/perifericos/{p_id}/impresiones/{op_id}/resultado

Digitalización (GD-API-0135):
- POST   /api/v1/gd/perifericos/{id}/digitalizar
- POST   /api/v1/gd/perifericos/{p_id}/digitalizaciones/{op_id}/resultado

Gate: todos los endpoints chequean `assert_modulo_perifericos_activo` antes
de operar (404 si organización no tiene módulo activo — Doc 6 § neutralidad
sectorial).
"""
from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.perifericos import (
    AnularCodigoBarrasRequest,
    CambiarEstadoPerifericoRequest,
    CambiarEstadoPuntoRequest,
    CodigoBarrasResponse,
    CrearPerifericoRequest,
    CrearPuntoAtencionRequest,
    DigitalizacionResponse,
    DigitalizarRequest,
    GenerarCodigoBarrasRequest,
    ImprimirConstanciaRequest,
    ImprimirEtiquetaRequest,
    ImpresionResponse,
    PatchPerifericoRequest,
    PatchPuntoAtencionRequest,
    PerifericoDetalleResponse,
    PerifericoListResponse,
    PerifericoResponse,
    PuntoAtencionResponse,
    ReimprimirEtiquetaRequest,
    ReportarResultadoDigitalizacionRequest,
    ReportarResultadoImpresionRequest,
)
from app.gd.security import GdPerfilContext, require_gd_perfil
from app.gd.services import perifericos as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router_puntos = APIRouter(
    prefix='/puntos-atencion', tags=['gd:perifericos:puntos'],
)
router_perif = APIRouter(
    prefix='/perifericos', tags=['gd:perifericos'],
)
router_codigos = APIRouter(
    prefix='/radicados', tags=['gd:perifericos:codigos'],
)


# =============================================================================
# Helpers comunes
# =============================================================================

async def _gate_modulo(conn: asyncpg.Connection, tenant_id: UUID) -> None:
    try:
        await svc.assert_modulo_perifericos_activo(conn, tenant_id=tenant_id)
    except svc.ModuloNoActivoError as e:
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
# Puntos de atención
# =============================================================================

@router_puntos.post(
    '', response_model=PuntoAtencionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def crear_punto(
    body: CrearPuntoAtencionRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PuntoAtencionResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    row = await svc.crear_punto_atencion(
        conn, tenant_id=perfil.tenant_id, nombre=body.nombre,
        direccion=body.direccion,
        dependencia_responsable_id=body.dependencia_responsable_id,
        metadata=body.metadata, creado_por_user_id=perfil.user_id,
    )
    await emit_gd_event(
        conn, tipo_evento='gd.punto_atencion.creado', accion='crear',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='punto_atencion',
        entidad_afectada_id=row['id'],
        valor_nuevo={'nombre': body.nombre},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return PuntoAtencionResponse(**row)


@router_puntos.get(
    '', response_model=list[PuntoAtencionResponse],
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_puntos(
    estado: str | None = Query(default=None),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> list[PuntoAtencionResponse]:
    await _gate_modulo(conn, perfil.tenant_id)
    rows = await svc.listar_puntos(
        conn, tenant_id=perfil.tenant_id, estado=estado,
    )
    return [PuntoAtencionResponse(**r) for r in rows]


@router_puntos.get(
    '/{punto_id}', response_model=PuntoAtencionResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def obtener_punto(
    punto_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PuntoAtencionResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    row = await svc.obtener_punto(
        conn, tenant_id=perfil.tenant_id, punto_id=punto_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return PuntoAtencionResponse(**row)


@router_puntos.patch(
    '/{punto_id}', response_model=PuntoAtencionResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def patch_punto(
    body: PatchPuntoAtencionRequest, request: Request,
    punto_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PuntoAtencionResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    row = await svc.patch_punto(
        conn, tenant_id=perfil.tenant_id, punto_id=punto_id,
        nombre=body.nombre, direccion=body.direccion,
        dependencia_responsable_id=body.dependencia_responsable_id,
        metadata=body.metadata,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    await emit_gd_event(
        conn, tipo_evento='gd.punto_atencion.actualizado', accion='actualizar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='punto_atencion',
        entidad_afectada_id=punto_id,
        criticidad=AuditCriticidad.BAJA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return PuntoAtencionResponse(**row)


def _make_cambio_punto(nuevo_estado: str, tipo_evento: str):
    async def _handler(
        body: CambiarEstadoPuntoRequest, request: Request,
        punto_id: UUID = Path(...),
        perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
        conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
    ) -> PuntoAtencionResponse:
        await _gate_modulo(conn, perfil.tenant_id)
        try:
            row = await svc.cambiar_estado_punto(
                conn, tenant_id=perfil.tenant_id, punto_id=punto_id,
                nuevo_estado=nuevo_estado, motivo=body.motivo,
            )
        except LookupError as e:
            raise _err_not_found(e) from e
        except ValueError as e:
            raise _err_conflict(e) from e
        await emit_gd_event(
            conn, tipo_evento=tipo_evento, accion='cambiar_estado',
            tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
            entidad_afectada_tipo='punto_atencion',
            entidad_afectada_id=punto_id,
            valor_nuevo={'estado': nuevo_estado},
            justificacion=body.motivo,
            criticidad=AuditCriticidad.MEDIA,
            request_id=getattr(request.state, 'request_id', None),
        )
        return PuntoAtencionResponse(**row)
    return _handler


router_puntos.add_api_route(
    '/{punto_id}/activar', _make_cambio_punto(
        'activo', 'gd.punto_atencion.activado',
    ),
    methods=['POST'], response_model=PuntoAtencionResponse,
    dependencies=[Depends(require_gd_perfil)],
)
router_puntos.add_api_route(
    '/{punto_id}/inactivar', _make_cambio_punto(
        'inactivo', 'gd.punto_atencion.inactivado',
    ),
    methods=['POST'], response_model=PuntoAtencionResponse,
    dependencies=[Depends(require_gd_perfil)],
)
router_puntos.add_api_route(
    '/{punto_id}/cerrar', _make_cambio_punto(
        'cerrado', 'gd.punto_atencion.cerrado',
    ),
    methods=['POST'], response_model=PuntoAtencionResponse,
    dependencies=[Depends(require_gd_perfil)],
)


@router_puntos.get(
    '/{punto_id}/perifericos',
    response_model=list[PerifericoResponse],
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_perif_punto(
    punto_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> list[PerifericoResponse]:
    await _gate_modulo(conn, perfil.tenant_id)
    rows = await svc.listar_perifericos_de_punto(
        conn, tenant_id=perfil.tenant_id, punto_id=punto_id,
    )
    return [PerifericoResponse(**r) for r in rows]


# =============================================================================
# Periféricos
# =============================================================================

@router_perif.post(
    '', response_model=PerifericoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def crear_perif(
    body: CrearPerifericoRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PerifericoResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    try:
        row = await svc.crear_periferico(
            conn, tenant_id=perfil.tenant_id,
            tipo_periferico=body.tipo_periferico, nombre=body.nombre,
            marca=body.marca, modelo=body.modelo, serial=body.serial,
            dependencia_id=body.dependencia_id,
            punto_atencion_id=body.punto_atencion_id,
            configuracion=body.configuracion,
            registrado_por_user_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_conflict(e) from e
    await emit_gd_event(
        conn, tipo_evento='gd.periferico.registrado', accion='crear',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='periferico', entidad_afectada_id=row['id'],
        valor_nuevo={'serial': body.serial, 'tipo': body.tipo_periferico},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return PerifericoResponse(**row)


@router_perif.get(
    '', response_model=PerifericoListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_perif(
    dependencia_id: UUID | None = Query(default=None),
    punto_atencion_id: UUID | None = Query(default=None),
    estado: str | None = Query(default=None),
    tipo_periferico: str | None = Query(default=None),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PerifericoListResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    rows = await svc.listar_perifericos(
        conn, tenant_id=perfil.tenant_id,
        dependencia_id=dependencia_id, punto_atencion_id=punto_atencion_id,
        estado=estado, tipo_periferico=tipo_periferico,
    )
    items = [PerifericoResponse(**r) for r in rows]
    return PerifericoListResponse(items=items, total=len(items))


@router_perif.get(
    '/{periferico_id}', response_model=PerifericoDetalleResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def detalle_perif(
    periferico_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PerifericoDetalleResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    row = await svc.detalle_periferico(
        conn, tenant_id=perfil.tenant_id, periferico_id=periferico_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return PerifericoDetalleResponse(**row)


@router_perif.patch(
    '/{periferico_id}', response_model=PerifericoResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def patch_perif(
    body: PatchPerifericoRequest, request: Request,
    periferico_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PerifericoResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    row = await svc.patch_periferico(
        conn, tenant_id=perfil.tenant_id, periferico_id=periferico_id,
        nombre=body.nombre, marca=body.marca, modelo=body.modelo,
        dependencia_id=body.dependencia_id,
        punto_atencion_id=body.punto_atencion_id,
        configuracion=body.configuracion,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    await emit_gd_event(
        conn, tipo_evento='gd.periferico.configuracion_modificada',
        accion='patch',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='periferico',
        entidad_afectada_id=periferico_id,
        criticidad=AuditCriticidad.BAJA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return PerifericoResponse(**row)


_ESTADOS_PERIF: dict[str, tuple[str, str]] = {
    'activar': ('activo', 'gd.periferico.activado'),
    'inactivar': ('inactivo', 'gd.periferico.inactivado'),
    'poner-mantenimiento': ('mantenimiento', 'gd.periferico.mantenimiento'),
    'retirar': ('retirado', 'gd.periferico.retirado'),
}


def _make_cambio_perif(accion: str):
    nuevo_estado, tipo_evento = _ESTADOS_PERIF[accion]

    async def _handler(
        body: CambiarEstadoPerifericoRequest, request: Request,
        periferico_id: UUID = Path(...),
        perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
        conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
    ) -> PerifericoResponse:
        await _gate_modulo(conn, perfil.tenant_id)
        try:
            row = await svc.cambiar_estado_periferico(
                conn, tenant_id=perfil.tenant_id,
                periferico_id=periferico_id,
                nuevo_estado=nuevo_estado, motivo=body.motivo,
                forzar=body.forzar,
            )
        except LookupError as e:
            raise _err_not_found(e) from e
        except ValueError as e:
            raise _err_conflict(e) from e
        await emit_gd_event(
            conn, tipo_evento=tipo_evento, accion='cambiar_estado',
            tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
            entidad_afectada_tipo='periferico',
            entidad_afectada_id=periferico_id,
            valor_nuevo={'estado': nuevo_estado, 'forzar': body.forzar},
            justificacion=body.motivo,
            criticidad=(AuditCriticidad.ALTA if body.forzar
                        else AuditCriticidad.MEDIA),
            request_id=getattr(request.state, 'request_id', None),
        )
        return PerifericoResponse(**row)
    return _handler


for _accion in _ESTADOS_PERIF:
    router_perif.add_api_route(
        f'/{{periferico_id}}/{_accion}', _make_cambio_perif(_accion),
        methods=['POST'], response_model=PerifericoResponse,
        dependencies=[Depends(require_gd_perfil)],
    )


# =============================================================================
# Impresión etiqueta + reimpresión + constancia (GD-API-0132/0133/0134)
# =============================================================================

@router_perif.post(
    '/{periferico_id}/imprimir-etiqueta',
    response_model=ImpresionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def imprimir_etiqueta(
    body: ImprimirEtiquetaRequest, request: Request,
    periferico_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ImpresionResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    try:
        row = await svc.imprimir_etiqueta(
            conn, tenant_id=perfil.tenant_id, periferico_id=periferico_id,
            radicado_id=body.radicado_id, formato=body.formato_etiqueta,
            incluir_qr=body.incluir_qr,
            incluir_codigo_barras=body.incluir_codigo_barras,
            usuario_id=perfil.user_id,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_conflict(e) from e
    await emit_gd_event(
        conn, tipo_evento='gd.impresion.encolada',
        accion='imprimir_etiqueta',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='impresion_radicado',
        entidad_afectada_id=row['id'],
        valor_nuevo={'radicado_id': str(body.radicado_id),
                      'formato': body.formato_etiqueta},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ImpresionResponse(**row)


@router_perif.post(
    '/{periferico_id}/reimprimir-etiqueta',
    response_model=ImpresionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def reimprimir_etiqueta(
    body: ReimprimirEtiquetaRequest, request: Request,
    periferico_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ImpresionResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    try:
        row = await svc.reimprimir_etiqueta(
            conn, tenant_id=perfil.tenant_id, periferico_id=periferico_id,
            radicado_id=body.radicado_id, motivo=body.motivo,
            impresion_original_id=body.impresion_original_id,
            usuario_id=perfil.user_id,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_conflict(e) from e
    criticidad = (
        AuditCriticidad.ALTA if row['intentos_reimpresion'] > 1
        else AuditCriticidad.MEDIA
    )
    await emit_gd_event(
        conn, tipo_evento='gd.impresion.reimpresion', accion='reimprimir',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='impresion_radicado',
        entidad_afectada_id=row['id'],
        valor_nuevo={'radicado_id': str(body.radicado_id),
                      'intentos': row['intentos_reimpresion']},
        justificacion=body.motivo, criticidad=criticidad,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ImpresionResponse(**row)


@router_perif.post(
    '/{periferico_id}/imprimir-constancia',
    response_model=ImpresionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def imprimir_constancia(
    body: ImprimirConstanciaRequest, request: Request,
    periferico_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ImpresionResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    try:
        row = await svc.imprimir_constancia(
            conn, tenant_id=perfil.tenant_id, periferico_id=periferico_id,
            radicado_id=body.radicado_id, formato=body.formato,
            incluir_qr=body.incluir_qr, usuario_id=perfil.user_id,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_conflict(e) from e
    await emit_gd_event(
        conn, tipo_evento='gd.impresion.constancia',
        accion='imprimir_constancia',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='impresion_radicado',
        entidad_afectada_id=row['id'],
        valor_nuevo={'radicado_id': str(body.radicado_id),
                      'formato': body.formato},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ImpresionResponse(**row)


@router_perif.post(
    '/{periferico_id}/impresiones/{impresion_id}/resultado',
    response_model=ImpresionResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def reportar_resultado_impresion(
    body: ReportarResultadoImpresionRequest, request: Request,
    periferico_id: UUID = Path(...),
    impresion_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ImpresionResponse:
    """Webhook desde agente local. Notifica resultado de impresión."""
    await _gate_modulo(conn, perfil.tenant_id)
    try:
        row = await svc.reportar_resultado_impresion(
            conn, tenant_id=perfil.tenant_id, periferico_id=periferico_id,
            impresion_id=impresion_id, estado=body.estado,
            mensaje_error=body.mensaje_error, latencia_ms=body.latencia_ms,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_conflict(e) from e
    tipo_evento = ('gd.impresion.generada' if body.estado == 'generada'
                   else 'gd.impresion.fallida')
    criticidad = (AuditCriticidad.MEDIA if body.estado == 'generada'
                   else AuditCriticidad.ALTA)
    await emit_gd_event(
        conn, tipo_evento=tipo_evento, accion='reportar_resultado',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='impresion_radicado',
        entidad_afectada_id=impresion_id,
        valor_nuevo={'estado': body.estado,
                      'latencia_ms': body.latencia_ms},
        criticidad=criticidad,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ImpresionResponse(**row)


# =============================================================================
# Digitalización individual (GD-API-0135)
# =============================================================================

@router_perif.post(
    '/{periferico_id}/digitalizar',
    response_model=DigitalizacionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def digitalizar(
    body: DigitalizarRequest, request: Request,
    periferico_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> DigitalizacionResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    try:
        row = await svc.encolar_digitalizacion(
            conn, tenant_id=perfil.tenant_id, periferico_id=periferico_id,
            radicado_id=body.radicado_id,
            tipo_digitalizacion=body.tipo_digitalizacion,
            calidad_dpi=body.calidad_dpi, observacion=body.observacion,
            usuario_id=perfil.user_id,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_conflict(e) from e
    await emit_gd_event(
        conn, tipo_evento='gd.digitalizacion.encolada',
        accion='digitalizar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='digitalizacion_documento',
        entidad_afectada_id=row['id'],
        valor_nuevo={'radicado_id': str(body.radicado_id),
                      'dpi': body.calidad_dpi},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return DigitalizacionResponse(**row)


@router_perif.post(
    '/{periferico_id}/digitalizaciones/{digitalizacion_id}/resultado',
    response_model=DigitalizacionResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def reportar_resultado_digit(
    body: ReportarResultadoDigitalizacionRequest, request: Request,
    periferico_id: UUID = Path(...),
    digitalizacion_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> DigitalizacionResponse:
    """Webhook agente local. Notifica resultado de digitalización."""
    await _gate_modulo(conn, perfil.tenant_id)
    try:
        row = await svc.reportar_resultado_digitalizacion(
            conn, tenant_id=perfil.tenant_id, periferico_id=periferico_id,
            digitalizacion_id=digitalizacion_id, estado=body.estado,
            archivo_digital_id=body.archivo_digital_id,
            numero_paginas=body.numero_paginas,
            mensaje_error=body.mensaje_error, observacion=body.observacion,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_conflict(e) from e
    tipos = {
        'correcta': ('gd.digitalizacion.completada', AuditCriticidad.MEDIA),
        'fallida': ('gd.digitalizacion.fallida', AuditCriticidad.ALTA),
        'incompleta': ('gd.digitalizacion.incompleta', AuditCriticidad.MEDIA),
    }
    tipo_evento, criticidad = tipos[body.estado]
    await emit_gd_event(
        conn, tipo_evento=tipo_evento, accion='reportar_resultado',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='digitalizacion_documento',
        entidad_afectada_id=digitalizacion_id,
        valor_nuevo={'estado': body.estado,
                      'paginas': body.numero_paginas},
        criticidad=criticidad,
        request_id=getattr(request.state, 'request_id', None),
    )
    return DigitalizacionResponse(**row)


# =============================================================================
# Códigos de barras / QR (GD-API-0131)
# =============================================================================

@router_codigos.post(
    '/{radicado_id}/codigo-barras',
    response_model=CodigoBarrasResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def generar_codigo(
    body: GenerarCodigoBarrasRequest, request: Request,
    radicado_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CodigoBarrasResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    try:
        row = await svc.generar_codigo_barras_radicado(
            conn, tenant_id=perfil.tenant_id, radicado_id=radicado_id,
            tipo_codigo=body.tipo_codigo,
            generado_por_user_id=perfil.user_id,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    await emit_gd_event(
        conn, tipo_evento='gd.codigo_barras.generado', accion='generar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='codigo_barras_radicado',
        entidad_afectada_id=row['id'],
        valor_nuevo={'tipo': body.tipo_codigo,
                      'radicado_id': str(radicado_id)},
        criticidad=AuditCriticidad.BAJA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return CodigoBarrasResponse(**row)


@router_codigos.get(
    '/{radicado_id}/codigo-barras',
    response_model=CodigoBarrasResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def obtener_codigo_vigente(
    radicado_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CodigoBarrasResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    row = await svc.obtener_codigo_vigente_radicado(
        conn, tenant_id=perfil.tenant_id, radicado_id=radicado_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return CodigoBarrasResponse(**row)


@router_codigos.post(
    '/{radicado_id}/codigo-barras/{codigo_id}/anular',
    response_model=CodigoBarrasResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def anular_codigo(
    body: AnularCodigoBarrasRequest, request: Request,
    radicado_id: UUID = Path(...),
    codigo_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CodigoBarrasResponse:
    await _gate_modulo(conn, perfil.tenant_id)
    try:
        row = await svc.anular_codigo_barras(
            conn, tenant_id=perfil.tenant_id, radicado_id=radicado_id,
            codigo_id=codigo_id, motivo=body.motivo,
            generar_reemplazo=body.generar_reemplazo,
            tipo_codigo_reemplazo=body.tipo_codigo_reemplazo,
            user_id=perfil.user_id,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_conflict(e) from e
    await emit_gd_event(
        conn, tipo_evento='gd.codigo_barras.anulado', accion='anular',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='codigo_barras_radicado',
        entidad_afectada_id=codigo_id,
        justificacion=body.motivo, criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return CodigoBarrasResponse(**row)


__all__ = ['router_puntos', 'router_perif', 'router_codigos']
