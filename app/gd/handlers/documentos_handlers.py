"""Handlers HTTP de EP-009 documentos, anexos y versiones (bloque 10).

Endpoints (11 nuevos):
- POST /api/v1/gd/documentos                          (crear)         GD-API-0057+0059
- GET  /api/v1/gd/documentos                          (listar/buscar) GD-API-0063
- GET  /api/v1/gd/documentos/{id}                     (detalle)
- POST /api/v1/gd/documentos/{id}/versiones           (nueva versión) GD-API-0059
- GET  /api/v1/gd/documentos/{id}/versiones           (listar v.)
- POST /api/v1/gd/documentos/{id}/anular              GD-API-0062
- POST /api/v1/gd/documentos/{id}/reemplazar          GD-API-0062
- POST /api/v1/gd/documentos/{id}/relacionar          (relación polim.)
- POST /api/v1/gd/anexos                              (crear anexo)   GD-API-0060
- GET  /api/v1/gd/anexos                              (listar/filtrar)
- POST /api/v1/gd/archivos/{archivo_digital_id}/descargar  (audit)    GD-API-0061
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.documentos import (
    AnexoListResponse,
    AnexoResponse,
    AnularDocumentoRequest,
    CrearAnexoRequest,
    CrearDocumentoRequest,
    DescargaResponse,
    DocumentoListItem,
    DocumentoListResponse,
    DocumentoResponse,
    NuevaVersionRequest,
    ReemplazarDocumentoRequest,
    RelacionResponse,
    RelacionarDocumentoRequest,
    VersionDocumentoResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil
from app.gd.services import documentos as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router_docs = APIRouter(prefix='/documentos', tags=['gd:documentos'])
router_anexos = APIRouter(prefix='/anexos', tags=['gd:anexos'])
router_archivos = APIRouter(prefix='/archivos', tags=['gd:archivos'])


def _err_estado(e: ValueError) -> HTTPException:
    return HTTPException(409, detail={'error': 'conflict', 'code': str(e)})


def _err_validacion_archivo(e: ValueError) -> HTTPException:
    code = str(e)
    # 415 si es MIME, 413 si es tamaño.
    status_code = 415 if code == 'mime_no_permitido' else 413
    return HTTPException(
        status_code, detail={'error': 'validation_error', 'code': code},
    )


def _to_doc_response(row: dict[str, Any]) -> DocumentoResponse:
    versiones = [VersionDocumentoResponse(**v) for v in row.get('versiones', [])]
    return DocumentoResponse(
        id=row['id'], titulo=row['titulo'],
        descripcion=row.get('descripcion'),
        clasificacion_informacion=row['clasificacion_informacion'],
        trd_serie_codigo=row.get('trd_serie_codigo'),
        trd_subserie_codigo=row.get('trd_subserie_codigo'),
        trd_tipo_documental=row.get('trd_tipo_documental'),
        estado=row['estado'],
        version_vigente_id=row.get('version_vigente_id'),
        numero_version_vigente=row['numero_version_vigente'],
        anulado_en=row.get('anulado_en'),
        motivo_anulacion=row.get('motivo_anulacion'),
        reemplazado_por_documento_id=row.get('reemplazado_por_documento_id'),
        creado_por_user_id=row['creado_por_user_id'],
        created_at=row['created_at'], updated_at=row['updated_at'],
        versiones=versiones,
    )


# =============================================================================
# Documentos
# =============================================================================

@router_docs.post(
    '',
    response_model=DocumentoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def crear_documento(
    body: CrearDocumentoRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> DocumentoResponse:
    try:
        row = await svc.crear_documento(
            conn, tenant_id=perfil.tenant_id,
            titulo=body.titulo, descripcion=body.descripcion,
            clasificacion_informacion=body.clasificacion_informacion,
            trd_serie_codigo=body.trd_serie_codigo,
            trd_subserie_codigo=body.trd_subserie_codigo,
            trd_tipo_documental=body.trd_tipo_documental,
            archivo_digital_id=body.archivo_digital_id,
            mime_type=body.mime_type, tamano_bytes=body.tamano_bytes,
            hash_sha256=body.hash_sha256,
            observaciones=body.observaciones,
            creado_por_user_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_validacion_archivo(e) from e

    await emit_gd_event(
        conn, tipo_evento='DocumentoCreado', accion='crear_documento',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='documento', entidad_afectada_id=row['id'],
        valor_nuevo={'clasificacion': body.clasificacion_informacion,
                      'archivo_digital_id': str(body.archivo_digital_id)},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _to_doc_response(row)


@router_docs.get(
    '',
    response_model=DocumentoListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_documentos(
    estado: str | None = Query(default=None),
    clasificacion: str | None = Query(default=None),
    trd_serie: str | None = Query(default=None, max_length=50),
    q: str | None = Query(default=None, description='Búsqueda por título'),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> DocumentoListResponse:
    estados = estado.split(',') if estado else None
    clasifs = clasificacion.split(',') if clasificacion else None
    rows = await svc.listar_documentos(
        conn, tenant_id=perfil.tenant_id,
        estado=estados, clasificacion=clasifs, trd_serie=trd_serie,
        titulo_like=q, limit=limit,
    )
    total = await svc.contar_documentos(conn, tenant_id=perfil.tenant_id)
    items = [DocumentoListItem(**r) for r in rows]
    return DocumentoListResponse(items=items, total=total)


@router_docs.get(
    '/{documento_id}',
    response_model=DocumentoResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def detalle_documento(
    documento_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> DocumentoResponse:
    row = await svc.obtener_documento(
        conn, tenant_id=perfil.tenant_id, documento_id=documento_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return _to_doc_response(row)


@router_docs.post(
    '/{documento_id}/versiones',
    response_model=VersionDocumentoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def nueva_version(
    body: NuevaVersionRequest, request: Request,
    documento_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> VersionDocumentoResponse:
    try:
        row = await svc.nueva_version(
            conn, tenant_id=perfil.tenant_id, documento_id=documento_id,
            archivo_digital_id=body.archivo_digital_id,
            mime_type=body.mime_type, tamano_bytes=body.tamano_bytes,
            hash_sha256=body.hash_sha256,
            observaciones=body.observaciones,
            creado_por_user_id=perfil.user_id,
        )
    except ValueError as e:
        code = str(e)
        if code in ('mime_no_permitido', 'tamano_excedido'):
            raise _err_validacion_archivo(e) from e
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='DocumentoVersionCreada', accion='nueva_version',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='version_documento', entidad_afectada_id=row['id'],
        valor_nuevo={'numero_version': row['numero_version'],
                      'documento_id': str(documento_id)},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return VersionDocumentoResponse(**row)


@router_docs.get(
    '/{documento_id}/versiones',
    response_model=list[VersionDocumentoResponse],
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_versiones(
    documento_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> list[VersionDocumentoResponse]:
    rows = await svc.listar_versiones(
        conn, tenant_id=perfil.tenant_id, documento_id=documento_id,
    )
    return [VersionDocumentoResponse(**r) for r in rows]


@router_docs.post(
    '/{documento_id}/anular',
    response_model=DocumentoResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def anular_documento(
    body: AnularDocumentoRequest, request: Request,
    documento_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> DocumentoResponse:
    try:
        row = await svc.anular_documento(
            conn, tenant_id=perfil.tenant_id, documento_id=documento_id,
            motivo=body.motivo, usuario_actor_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='DocumentoAnulado', accion='anular',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='documento', entidad_afectada_id=documento_id,
        justificacion=body.motivo,
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _to_doc_response(row)


@router_docs.post(
    '/{documento_id}/reemplazar',
    response_model=VersionDocumentoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def reemplazar_documento(
    body: ReemplazarDocumentoRequest, request: Request,
    documento_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> VersionDocumentoResponse:
    try:
        row = await svc.reemplazar_documento(
            conn, tenant_id=perfil.tenant_id, documento_id=documento_id,
            archivo_digital_id=body.archivo_digital_id, motivo=body.motivo,
            mime_type=body.mime_type, tamano_bytes=body.tamano_bytes,
            hash_sha256=body.hash_sha256,
            usuario_actor_id=perfil.user_id,
        )
    except ValueError as e:
        code = str(e)
        if code in ('mime_no_permitido', 'tamano_excedido'):
            raise _err_validacion_archivo(e) from e
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='DocumentoReemplazado', accion='reemplazar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='version_documento', entidad_afectada_id=row['id'],
        valor_nuevo={'documento_id': str(documento_id),
                      'numero_version': row['numero_version']},
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return VersionDocumentoResponse(**row)


@router_docs.post(
    '/{documento_id}/relacionar',
    response_model=RelacionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def relacionar_documento(
    body: RelacionarDocumentoRequest, request: Request,
    documento_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RelacionResponse:
    try:
        row = await svc.relacionar_documento(
            conn, tenant_id=perfil.tenant_id, documento_id=documento_id,
            entidad_tipo=body.entidad_tipo, entidad_id=body.entidad_id,
            rol=body.rol, creado_por_user_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='DocumentoRelacionado', accion='relacionar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='documento', entidad_afectada_id=documento_id,
        valor_nuevo={'entidad_tipo': body.entidad_tipo,
                      'entidad_id': str(body.entidad_id), 'rol': body.rol},
        criticidad=AuditCriticidad.BAJA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return RelacionResponse(**row)


# =============================================================================
# Anexos
# =============================================================================

@router_anexos.post(
    '',
    response_model=AnexoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def crear_anexo(
    body: CrearAnexoRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> AnexoResponse:
    row = await svc.crear_anexo(
        conn, tenant_id=perfil.tenant_id,
        archivo_digital_id=body.archivo_digital_id,
        entidad_relacionada_tipo=body.entidad_relacionada_tipo,
        entidad_relacionada_id=body.entidad_relacionada_id,
        titulo=body.titulo, descripcion=body.descripcion,
        mime_type=body.mime_type, tamano_bytes=body.tamano_bytes,
        creado_por_user_id=perfil.user_id,
    )

    await emit_gd_event(
        conn, tipo_evento='AnexoCreado', accion='crear_anexo',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='anexo', entidad_afectada_id=row['id'],
        valor_nuevo={'entidad_tipo': body.entidad_relacionada_tipo,
                      'entidad_id': str(body.entidad_relacionada_id),
                      'archivo_digital_id': str(body.archivo_digital_id)},
        criticidad=AuditCriticidad.BAJA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return AnexoResponse(**row)


@router_anexos.get(
    '',
    response_model=AnexoListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_anexos(
    entidad_tipo: str | None = Query(default=None),
    entidad_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> AnexoListResponse:
    rows = await svc.listar_anexos(
        conn, tenant_id=perfil.tenant_id,
        entidad_tipo=entidad_tipo, entidad_id=entidad_id, limit=limit,
    )
    total = await svc.contar_anexos(
        conn, tenant_id=perfil.tenant_id,
        entidad_tipo=entidad_tipo, entidad_id=entidad_id,
    )
    items = [AnexoResponse(**r) for r in rows]
    return AnexoListResponse(items=items, total=total)


# =============================================================================
# Descarga auditada
# =============================================================================

@router_archivos.post(
    '/{archivo_digital_id}/descargar',
    response_model=DescargaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def descargar_archivo(
    request: Request,
    archivo_digital_id: UUID = Path(...),
    documento_id: UUID | None = Query(default=None),
    version_documento_id: UUID | None = Query(default=None),
    contexto_tipo: str | None = Query(default=None),
    contexto_id: UUID | None = Query(default=None),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> DescargaResponse:
    """Registra descarga + retorna URL placeholder.

    Si documento_id se provee, la clasificación se toma del documento;
    si no, se asume 'interna'. Esto permite descargar anexos o archivos
    sueltos sin documento.
    """
    clasificacion = 'interna'
    if documento_id is not None:
        doc = await conn.fetchrow(
            'select clasificacion_informacion from gd.documento '
            'where id = $1 and tenant_id = $2',
            documento_id, perfil.tenant_id,
        )
        if doc is None:
            raise HTTPException(404, detail={'error': 'not_found',
                                              'code': 'documento_no_existe'})
        clasificacion = doc['clasificacion_informacion']

    request_id = getattr(request.state, 'request_id', None)
    log = await svc.registrar_descarga(
        conn, tenant_id=perfil.tenant_id,
        archivo_digital_id=archivo_digital_id,
        documento_id=documento_id, version_documento_id=version_documento_id,
        contexto_tipo=contexto_tipo, contexto_id=contexto_id,
        clasificacion_informacion=clasificacion,
        usuario_id=perfil.user_id,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get('user-agent'),
        request_id=request_id,
    )

    # Criticidad alta para reservada/confidencial/datos_personales/sensible.
    criticidad = (
        AuditCriticidad.ALTA if log['criticidad'] == 'alta'
        else AuditCriticidad.BAJA
    )
    await emit_gd_event(
        conn, tipo_evento='DocumentoDescargado', accion='descargar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='archivo_digital',
        entidad_afectada_id=archivo_digital_id,
        valor_nuevo={'clasificacion': clasificacion,
                      'documento_id': str(documento_id) if documento_id else None,
                      'descarga_log_id': str(log['id'])},
        criticidad=criticidad,
        request_id=request_id,
    )

    return DescargaResponse(
        archivo_digital_id=archivo_digital_id,
        descarga_id=log['id'],
        clasificacion_informacion=clasificacion,
        descargado_en=log['descargado_en'],
        # Placeholder hasta que EP-018 entregue URLs pre-firmadas reales.
        download_url=f'/_ep018-pending/{archivo_digital_id}',
    )


__all__ = ['router_docs', 'router_anexos', 'router_archivos']
