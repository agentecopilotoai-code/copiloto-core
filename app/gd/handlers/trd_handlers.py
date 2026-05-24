"""Handlers HTTP de EP-015 TRD/TVD (bloque 16).

Endpoints (16):
TRD (GD-API-0095/0096):
- POST /api/v1/gd/trd/versiones
- GET  /api/v1/gd/trd/versiones
- GET  /api/v1/gd/trd/versiones/{id}
- POST /api/v1/gd/trd/versiones/{id}/activar

Series / subseries / tipos (GD-API-0095):
- POST /api/v1/gd/trd/series
- GET  /api/v1/gd/trd/versiones/{id}/series
- POST /api/v1/gd/trd/subseries
- GET  /api/v1/gd/trd/series/{id}/subseries
- POST /api/v1/gd/trd/tipos-documentales
- GET  /api/v1/gd/trd/subseries/{id}/tipos-documentales

TVD (GD-API-0095/0096):
- POST /api/v1/gd/tvd/versiones
- GET  /api/v1/gd/tvd/versiones
- POST /api/v1/gd/tvd/versiones/{id}/activar

Asociación dep ↔ código (GD-API-0097):
- POST /api/v1/gd/dependencias/{dep_id}/codigos-documentales
- GET  /api/v1/gd/dependencias/{dep_id}/codigos-documentales

Clasificación (GD-API-0098/0099/0100):
- POST /api/v1/gd/clasificacion-documental
- GET  /api/v1/gd/clasificacion-documental?entidad_tipo=&entidad_id=
"""
from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.trd import (
    ActivarVersionTRDRequest,
    AsociarDepCodigoRequest,
    ClasificacionDocumentalResponse,
    ClasificarDocumentalRequest,
    CrearSerieRequest,
    CrearSubserieRequest,
    CrearTipoDocumentalRequest,
    CrearVersionTRDRequest,
    CrearVersionTVDRequest,
    DepCodigoResponse,
    HistorialClasificacionResponse,
    SerieResponse,
    SubserieResponse,
    TipoDocumentalResponse,
    VersionTRDListResponse,
    VersionTRDResponse,
    VersionTVDResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil
from app.gd.services import trd as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router_trd = APIRouter(prefix='/trd', tags=['gd:trd'])
router_tvd = APIRouter(prefix='/tvd', tags=['gd:tvd'])
router_dep = APIRouter(prefix='/dependencias', tags=['gd:trd:dependencias'])
router_clasif = APIRouter(prefix='/clasificacion-documental',
                           tags=['gd:clasificacion'])


def _err_estado(e: ValueError) -> HTTPException:
    return HTTPException(409, detail={'error': 'conflict', 'code': str(e)})


def _err_not_found(e: LookupError) -> HTTPException:
    return HTTPException(404, detail={'error': 'not_found', 'code': str(e)})


# =============================================================================
# TRD
# =============================================================================

@router_trd.post(
    '/versiones',
    response_model=VersionTRDResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def crear_trd(
    body: CrearVersionTRDRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> VersionTRDResponse:
    try:
        row = await svc.crear_version_trd(
            conn, tenant_id=perfil.tenant_id,
            codigo=body.codigo, nombre=body.nombre,
            descripcion=body.descripcion,
            fecha_aprobacion=body.fecha_aprobacion,
            fecha_inicio_vigencia=body.fecha_inicio_vigencia,
            fecha_fin_vigencia=body.fecha_fin_vigencia,
            created_by_user_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e

    await emit_gd_event(
        conn, tipo_evento='TRDVersionada', accion='crear_version',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='version_trd', entidad_afectada_id=row['id'],
        valor_nuevo={'codigo': body.codigo, 'estado': 'borrador'},
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return VersionTRDResponse(**row)


@router_trd.get(
    '/versiones',
    response_model=VersionTRDListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_trd(
    estado: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> VersionTRDListResponse:
    rows = await svc.listar_versiones_trd(
        conn, tenant_id=perfil.tenant_id, estado=estado, limit=limit,
    )
    items = [VersionTRDResponse(**r) for r in rows]
    return VersionTRDListResponse(items=items, total=len(items))


@router_trd.get(
    '/versiones/{version_id}',
    response_model=VersionTRDResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def detalle_trd(
    version_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> VersionTRDResponse:
    row = await svc.obtener_version_trd(
        conn, tenant_id=perfil.tenant_id, version_id=version_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return VersionTRDResponse(**row)


@router_trd.post(
    '/versiones/{version_id}/activar',
    response_model=VersionTRDResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def activar_trd(
    body: ActivarVersionTRDRequest, request: Request,
    version_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> VersionTRDResponse:
    try:
        row = await svc.activar_version_trd(
            conn, tenant_id=perfil.tenant_id, version_id=version_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='TRDVersionada', accion='activar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='version_trd', entidad_afectada_id=version_id,
        valor_nuevo={'estado': 'vigente'},
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return VersionTRDResponse(**row)


# =============================================================================
# Series
# =============================================================================

@router_trd.post(
    '/series',
    response_model=SerieResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def crear_serie(
    body: CrearSerieRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> SerieResponse:
    try:
        row = await svc.crear_serie(
            conn, tenant_id=perfil.tenant_id,
            version_trd_id=body.version_trd_id,
            codigo=body.codigo, nombre=body.nombre,
            descripcion=body.descripcion,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_estado(e) from e
    return SerieResponse(**row)


@router_trd.get(
    '/versiones/{version_id}/series',
    response_model=list[SerieResponse],
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_series_v(
    version_id: UUID = Path(...),
    estado: str | None = Query(default=None),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> list[SerieResponse]:
    rows = await svc.listar_series(
        conn, tenant_id=perfil.tenant_id,
        version_trd_id=version_id, estado=estado,
    )
    return [SerieResponse(**r) for r in rows]


# =============================================================================
# Subseries
# =============================================================================

@router_trd.post(
    '/subseries',
    response_model=SubserieResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def crear_subserie(
    body: CrearSubserieRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> SubserieResponse:
    try:
        row = await svc.crear_subserie(
            conn, tenant_id=perfil.tenant_id, serie_id=body.serie_id,
            codigo=body.codigo, nombre=body.nombre,
            descripcion=body.descripcion,
            tiempo_archivo_gestion_anos=body.tiempo_archivo_gestion_anos,
            tiempo_archivo_central_anos=body.tiempo_archivo_central_anos,
            disposicion_final=body.disposicion_final,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_estado(e) from e
    return SubserieResponse(**row)


@router_trd.get(
    '/series/{serie_id}/subseries',
    response_model=list[SubserieResponse],
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_subseries_s(
    serie_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> list[SubserieResponse]:
    rows = await svc.listar_subseries(
        conn, tenant_id=perfil.tenant_id, serie_id=serie_id,
    )
    return [SubserieResponse(**r) for r in rows]


# =============================================================================
# Tipos documentales
# =============================================================================

@router_trd.post(
    '/tipos-documentales',
    response_model=TipoDocumentalResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def crear_tipo_doc(
    body: CrearTipoDocumentalRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TipoDocumentalResponse:
    try:
        row = await svc.crear_tipo_documental(
            conn, tenant_id=perfil.tenant_id,
            subserie_id=body.subserie_id,
            codigo=body.codigo, nombre=body.nombre,
            descripcion=body.descripcion,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_estado(e) from e
    return TipoDocumentalResponse(**row)


@router_trd.get(
    '/subseries/{subserie_id}/tipos-documentales',
    response_model=list[TipoDocumentalResponse],
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_tipos_doc(
    subserie_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> list[TipoDocumentalResponse]:
    rows = await svc.listar_tipos_documentales(
        conn, tenant_id=perfil.tenant_id, subserie_id=subserie_id,
    )
    return [TipoDocumentalResponse(**r) for r in rows]


# =============================================================================
# TVD
# =============================================================================

@router_tvd.post(
    '/versiones',
    response_model=VersionTVDResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def crear_tvd(
    body: CrearVersionTVDRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> VersionTVDResponse:
    try:
        row = await svc.crear_version_tvd(
            conn, tenant_id=perfil.tenant_id,
            codigo=body.codigo, nombre=body.nombre,
            descripcion=body.descripcion,
            version_trd_id=body.version_trd_id,
            fecha_aprobacion=body.fecha_aprobacion,
            fecha_inicio_vigencia=body.fecha_inicio_vigencia,
            fecha_fin_vigencia=body.fecha_fin_vigencia,
            created_by_user_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e

    await emit_gd_event(
        conn, tipo_evento='TVDVersionada', accion='crear_version',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='version_tvd', entidad_afectada_id=row['id'],
        valor_nuevo={'codigo': body.codigo, 'estado': 'borrador'},
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return VersionTVDResponse(**row)


@router_tvd.get(
    '/versiones',
    response_model=list[VersionTVDResponse],
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_tvd(
    estado: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> list[VersionTVDResponse]:
    rows = await svc.listar_versiones_tvd(
        conn, tenant_id=perfil.tenant_id, estado=estado, limit=limit,
    )
    return [VersionTVDResponse(**r) for r in rows]


@router_tvd.post(
    '/versiones/{version_id}/activar',
    response_model=VersionTVDResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def activar_tvd(
    request: Request,
    version_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> VersionTVDResponse:
    try:
        row = await svc.activar_version_tvd(
            conn, tenant_id=perfil.tenant_id, version_id=version_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='TVDVersionada', accion='activar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='version_tvd', entidad_afectada_id=version_id,
        valor_nuevo={'estado': 'vigente'},
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return VersionTVDResponse(**row)


# =============================================================================
# Asociación dependencia ↔ código documental
# =============================================================================

@router_dep.post(
    '/{dependencia_id}/codigos-documentales',
    response_model=DepCodigoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def asociar_dep_codigo(
    body: AsociarDepCodigoRequest, request: Request,
    dependencia_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> DepCodigoResponse:
    if body.dependencia_id != dependencia_id:
        raise HTTPException(
            422,
            detail={'error': 'validation_error',
                     'code': 'dependencia_id_mismatch'},
        )
    try:
        row = await svc.asociar_dep_codigo(
            conn, tenant_id=perfil.tenant_id,
            dependencia_id=dependencia_id,
            version_trd_id=body.version_trd_id,
            serie_id=body.serie_id, subserie_id=body.subserie_id,
            creado_por_user_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    return DepCodigoResponse(**row)


@router_dep.get(
    '/{dependencia_id}/codigos-documentales',
    response_model=list[DepCodigoResponse],
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_dep_codigos(
    dependencia_id: UUID = Path(...),
    version_trd_id: UUID | None = Query(default=None),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> list[DepCodigoResponse]:
    rows = await svc.listar_dep_codigos(
        conn, tenant_id=perfil.tenant_id,
        dependencia_id=dependencia_id, version_trd_id=version_trd_id,
    )
    return [DepCodigoResponse(**r) for r in rows]


# =============================================================================
# Clasificación documental
# =============================================================================

@router_clasif.post(
    '',
    response_model=ClasificacionDocumentalResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def clasificar(
    body: ClasificarDocumentalRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ClasificacionDocumentalResponse:
    try:
        row = await svc.clasificar(
            conn, tenant_id=perfil.tenant_id,
            entidad_tipo=body.entidad_tipo, entidad_id=body.entidad_id,
            version_trd_id=body.version_trd_id,
            serie_id=body.serie_id, subserie_id=body.subserie_id,
            tipo_documental_id=body.tipo_documental_id,
            justificacion=body.justificacion,
            clasificado_por_user_id=perfil.user_id,
        )
    except LookupError as e:
        raise _err_not_found(e) from e

    await emit_gd_event(
        conn, tipo_evento='ClasificacionDocumentalRegistrada',
        accion='clasificar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='clasificacion_documental',
        entidad_afectada_id=row['id'],
        valor_nuevo={'entidad_tipo': body.entidad_tipo,
                      'entidad_id': str(body.entidad_id),
                      'version_trd_id': str(body.version_trd_id),
                      'subserie_id': str(body.subserie_id) if body.subserie_id else None},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ClasificacionDocumentalResponse(**row)


@router_clasif.get(
    '',
    response_model=HistorialClasificacionResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def consultar_clasificacion(
    entidad_tipo: str = Query(..., pattern='^(radicado|documento|pqrsd|correspondencia|expediente)$'),
    entidad_id: UUID = Query(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> HistorialClasificacionResponse:
    vigente = await svc.obtener_vigente(
        conn, tenant_id=perfil.tenant_id,
        entidad_tipo=entidad_tipo, entidad_id=entidad_id,
    )
    historial = await svc.historial_clasificacion(
        conn, tenant_id=perfil.tenant_id,
        entidad_tipo=entidad_tipo, entidad_id=entidad_id,
    )
    return HistorialClasificacionResponse(
        entidad_tipo=entidad_tipo, entidad_id=entidad_id,
        vigente=ClasificacionDocumentalResponse(**vigente) if vigente else None,
        historial=[ClasificacionDocumentalResponse(**h) for h in historial],
    )


__all__ = ['router_trd', 'router_tvd', 'router_dep', 'router_clasif']
