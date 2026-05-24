"""Handlers HTTP de EP-011 firmas (bloque 12).

Endpoints (11):
- POST /api/v1/gd/firmas/escaneadas                                  GD-API-0068
- GET  /api/v1/gd/firmas/escaneadas                                  GD-API-0068
- POST /api/v1/gd/firmas/escaneadas/{id}/autorizar                   GD-API-0068
- POST /api/v1/gd/firmas/escaneadas/{id}/revocar                     GD-API-0068
- POST /api/v1/gd/documentos/{id}/firmar-electronica                 GD-API-0069
- POST /api/v1/gd/documentos/{id}/firmar-digital                     GD-API-0070
- POST /api/v1/gd/documentos/{id}/firmar-escaneada                   GD-API-0068+0069
- POST /api/v1/gd/firmas/{id}/rechazar                               GD-API-0071
- POST /api/v1/gd/firmas/{id}/revocar                                GD-API-0071
- GET  /api/v1/gd/firmas/{id}/evidencia                              GD-API-0072
- GET  /api/v1/gd/firmas                                              (listar)
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.firmas import (
    AutorizarFirmaEscaneadaRequest,
    EvidenciaFirmaResponse,
    FirmaDocumentoListResponse,
    FirmaDocumentoResponse,
    FirmaEscaneadaListResponse,
    FirmaEscaneadaResponse,
    FirmarDigitalRequest,
    FirmarElectronicaRequest,
    RechazarFirmaRequest,
    RegistrarFirmaEscaneadaRequest,
    RevocarFirmaConsumadaRequest,
    RevocarFirmaEscaneadaRequest,
)
from app.gd.security import GdPerfilContext, require_gd_perfil
from app.gd.services import firmas as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router_firmas_esc = APIRouter(prefix='/firmas/escaneadas',
                               tags=['gd:firmas:escaneadas'])
router_docs_firma = APIRouter(prefix='/documentos', tags=['gd:firmas:documentos'])
router_firmas = APIRouter(prefix='/firmas', tags=['gd:firmas'])


def _err_estado(e: ValueError) -> HTTPException:
    return HTTPException(409, detail={'error': 'conflict', 'code': str(e)})


def _err_not_found(e: LookupError) -> HTTPException:
    return HTTPException(404, detail={'error': 'not_found', 'code': str(e)})


def _esc_to_response(row: dict[str, Any]) -> FirmaEscaneadaResponse:
    return FirmaEscaneadaResponse(**row)


def _doc_to_response(row: dict[str, Any]) -> FirmaDocumentoResponse:
    # Filter only keys recognized by the schema.
    keys = {
        'id', 'documento_id', 'version_documento_id', 'firmante_user_id',
        'tipo_firma', 'estado', 'firma_escaneada_id', 'certificado_id',
        'proveedor_firma_digital', 'hash_archivo', 'hash_algoritmo',
        'snapshot_firmante', 'ip', 'user_agent', 'fecha_firma',
        'fecha_rechazo', 'fecha_revocacion', 'observaciones_rechazo',
        'motivo_revocacion', 'step_up_requerido', 'created_at',
    }
    return FirmaDocumentoResponse(**{k: row[k] for k in keys if k in row})


# =============================================================================
# Firma escaneada (GD-API-0068)
# =============================================================================

@router_firmas_esc.post(
    '',
    response_model=FirmaEscaneadaResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def registrar_escaneada(
    body: RegistrarFirmaEscaneadaRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> FirmaEscaneadaResponse:
    try:
        row = await svc.registrar_firma_escaneada(
            conn, tenant_id=perfil.tenant_id, user_id=perfil.user_id,
            archivo_digital_id=body.archivo_digital_id,
            mime_type=body.mime_type, tamano_bytes=body.tamano_bytes,
            hash_sha256=body.hash_sha256,
        )
    except ValueError as e:
        raise _err_estado(e) from e

    await emit_gd_event(
        conn, tipo_evento='FirmaEscaneadaRegistrada', accion='registrar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='firma_escaneada', entidad_afectada_id=row['id'],
        valor_nuevo={'archivo_digital_id': str(body.archivo_digital_id)},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _esc_to_response(row)


@router_firmas_esc.get(
    '',
    response_model=FirmaEscaneadaListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_escaneadas(
    user_id: UUID | None = Query(default=None),
    estado: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> FirmaEscaneadaListResponse:
    rows = await svc.listar_firmas_escaneadas(
        conn, tenant_id=perfil.tenant_id,
        user_id=user_id, estado=estado, limit=limit,
    )
    items = [_esc_to_response(r) for r in rows]
    return FirmaEscaneadaListResponse(items=items, total=len(items))


@router_firmas_esc.post(
    '/{firma_id}/autorizar',
    response_model=FirmaEscaneadaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def autorizar_escaneada(
    body: AutorizarFirmaEscaneadaRequest, request: Request,
    firma_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> FirmaEscaneadaResponse:
    try:
        row = await svc.autorizar_firma_escaneada(
            conn, tenant_id=perfil.tenant_id, firma_id=firma_id,
            autorizada_por_user_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='FirmaEscaneadaAutorizada', accion='autorizar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='firma_escaneada', entidad_afectada_id=firma_id,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _esc_to_response(row)


@router_firmas_esc.post(
    '/{firma_id}/revocar',
    response_model=FirmaEscaneadaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def revocar_escaneada(
    body: RevocarFirmaEscaneadaRequest, request: Request,
    firma_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> FirmaEscaneadaResponse:
    try:
        row = await svc.revocar_firma_escaneada(
            conn, tenant_id=perfil.tenant_id, firma_id=firma_id,
            motivo=body.motivo,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='FirmaEscaneadaRevocada', accion='revocar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='firma_escaneada', entidad_afectada_id=firma_id,
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _esc_to_response(row)


# =============================================================================
# Firma electrónica / digital / escaneada sobre documento
# =============================================================================

@router_docs_firma.post(
    '/{documento_id}/firmar-electronica',
    response_model=FirmaDocumentoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def firmar_electronica(
    body: FirmarElectronicaRequest, request: Request,
    documento_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> FirmaDocumentoResponse:
    try:
        row = await svc.firmar_documento_electronica(
            conn, tenant_id=perfil.tenant_id, documento_id=documento_id,
            version_documento_id=body.version_documento_id,
            firmante_user_id=perfil.user_id,
            sesion_iniciada_en=body.sesion_iniciada_en,
            step_up_satisfecho=body.step_up_satisfecho,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get('user-agent'),
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_estado(e) from e

    await emit_gd_event(
        conn, tipo_evento='DocumentoFirmado', accion='firmar_electronica',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='firma_documento', entidad_afectada_id=row['id'],
        valor_nuevo={'documento_id': str(documento_id),
                      'tipo_firma': 'electronica',
                      'estado': row['estado']},
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _doc_to_response(row)


@router_docs_firma.post(
    '/{documento_id}/firmar-digital',
    response_model=FirmaDocumentoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def firmar_digital(
    body: FirmarDigitalRequest, request: Request,
    documento_id: UUID = Path(...),
    x_signing_pin: str | None = Header(default=None,
                                          description='PIN del certificado'),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> FirmaDocumentoResponse:
    if not x_signing_pin:
        raise HTTPException(
            422,
            detail={'error': 'validation_error',
                     'code': 'pin_requerido',
                     'message': 'Header X-Signing-Pin requerido para firma digital'},
        )
    try:
        row = await svc.firmar_documento_digital(
            conn, tenant_id=perfil.tenant_id, documento_id=documento_id,
            version_documento_id=body.version_documento_id,
            firmante_user_id=perfil.user_id,
            certificado_id=body.certificado_id, proveedor=body.proveedor,
            pin=x_signing_pin, provider=None,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get('user-agent'),
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_estado(e) from e

    await emit_gd_event(
        conn, tipo_evento='DocumentoFirmado', accion='firmar_digital',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='firma_documento', entidad_afectada_id=row['id'],
        valor_nuevo={'documento_id': str(documento_id),
                      'tipo_firma': 'digital',
                      'proveedor': body.proveedor},
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _doc_to_response(row)


@router_docs_firma.post(
    '/{documento_id}/firmar-escaneada',
    response_model=FirmaDocumentoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def firmar_escaneada(
    request: Request,
    documento_id: UUID = Path(...),
    version_documento_id: UUID = Query(...),
    firma_escaneada_id: UUID = Query(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> FirmaDocumentoResponse:
    try:
        row = await svc.firmar_documento_escaneada(
            conn, tenant_id=perfil.tenant_id, documento_id=documento_id,
            version_documento_id=version_documento_id,
            firmante_user_id=perfil.user_id,
            firma_escaneada_id=firma_escaneada_id,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get('user-agent'),
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_estado(e) from e

    await emit_gd_event(
        conn, tipo_evento='DocumentoFirmado', accion='firmar_escaneada',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='firma_documento', entidad_afectada_id=row['id'],
        valor_nuevo={'documento_id': str(documento_id),
                      'tipo_firma': 'escaneada'},
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _doc_to_response(row)


# =============================================================================
# Rechazo / revocación / evidencia
# =============================================================================

@router_firmas.post(
    '/{firma_id}/rechazar',
    response_model=FirmaDocumentoResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def rechazar(
    body: RechazarFirmaRequest, request: Request,
    firma_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> FirmaDocumentoResponse:
    try:
        row = await svc.rechazar_firma(
            conn, tenant_id=perfil.tenant_id, firma_id=firma_id,
            observacion=body.observacion, actor_user_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='FirmaRechazada', accion='rechazar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='firma_documento', entidad_afectada_id=firma_id,
        justificacion=body.observacion,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _doc_to_response(row)


@router_firmas.post(
    '/{firma_id}/revocar',
    response_model=FirmaDocumentoResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def revocar(
    body: RevocarFirmaConsumadaRequest, request: Request,
    firma_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> FirmaDocumentoResponse:
    try:
        row = await svc.revocar_firma_consumada(
            conn, tenant_id=perfil.tenant_id, firma_id=firma_id,
            motivo=body.motivo, actor_user_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='FirmaRevocada', accion='revocar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='firma_documento', entidad_afectada_id=firma_id,
        justificacion=body.motivo,
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _doc_to_response(row)


@router_firmas.get(
    '/{firma_id}/evidencia',
    response_model=EvidenciaFirmaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def evidencia(
    firma_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> EvidenciaFirmaResponse:
    row = await svc.obtener_evidencia(
        conn, tenant_id=perfil.tenant_id, firma_id=firma_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    firma = _doc_to_response(row)
    return EvidenciaFirmaResponse(
        firma=firma,
        hash_referencia=row['hash_archivo'],
        hash_algoritmo=row['hash_algoritmo'],
        documento_titulo=row.get('documento_titulo'),
        documento_version=row.get('documento_version'),
    )


@router_firmas.get(
    '',
    response_model=FirmaDocumentoListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_firmas(
    documento_id: UUID | None = Query(default=None),
    firmante_user_id: UUID | None = Query(default=None),
    estado: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> FirmaDocumentoListResponse:
    rows = await svc.listar_firmas_documento(
        conn, tenant_id=perfil.tenant_id,
        documento_id=documento_id, firmante_user_id=firmante_user_id,
        estado=estado, limit=limit,
    )
    items = [_doc_to_response(r) for r in rows]
    return FirmaDocumentoListResponse(items=items, total=len(items))


__all__ = ['router_firmas_esc', 'router_docs_firma', 'router_firmas']
