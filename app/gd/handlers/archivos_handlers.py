"""Handlers HTTP de EP-018 archivos transversal (bloque 19).

Endpoints (11) montados en /api/v1/core (transversal, no /gd):
- POST /api/v1/core/archivos                (multipart upload)
- GET  /api/v1/core/archivos                (listar con filtros)
- GET  /api/v1/core/archivos/duplicados     (GD-API-0113, antes de {id})
- POST /api/v1/core/archivos/aplicar-retencion  (worker admin)
- GET  /api/v1/core/archivos/{id}
- POST /api/v1/core/archivos/{id}/attach-proposito
- POST /api/v1/core/archivos/{id}/descargar
- POST /api/v1/core/archivos/{id}/anular
- POST /api/v1/core/archivos/{id}/reextraer
- GET  /api/v1/core/archivos/{id}/extraccion
- GET  /api/v1/core/archivos/{id}/descarga-logs
"""
from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import (
    APIRouter, Depends, File, Form, HTTPException, Path, Query,
    Request, UploadFile, status,
)

from app.db.pool import get_db
from app.gd.schemas.archivos import (
    AnularArchivoRequest,
    AplicarRetencionRequest,
    ArchivoDigitalResponse,
    ArchivoListResponse,
    AttachPropositoRequest,
    DescargaArchivoResponse,
    DuplicadosResponse,
    ExtraccionResultadoResponse,
    ReextraerRequest,
    RetencionExecResult,
)
from app.gd.security import GdPerfilContext, require_gd_perfil
from app.gd.services import archivos as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


# Router transversal — vive bajo /api/v1/core/archivos.
# Se monta vía gd/routes.router_core (prefix '/api/v1/core') por simplicidad
# de deployment unitario.
router = APIRouter(prefix='/archivos', tags=['core:archivos'])


def _err_estado(e: ValueError) -> HTTPException:
    return HTTPException(409, detail={'error': 'conflict', 'code': str(e)})


def _err_not_found(e: LookupError) -> HTTPException:
    return HTTPException(404, detail={'error': 'not_found', 'code': str(e)})


# =============================================================================
# Listar / dedupe / retención (antes de /{id} para que matchee)
# =============================================================================

@router.get(
    '',
    response_model=ArchivoListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar(
    proposito: str | None = Query(default=None),
    estado: str | None = Query(default=None),
    contexto_entidad_tipo: str | None = Query(default=None),
    contexto_entidad_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ArchivoListResponse:
    rows = await svc.listar_archivos(
        conn, tenant_id=perfil.tenant_id,
        proposito=proposito, estado=estado,
        contexto_entidad_tipo=contexto_entidad_tipo,
        contexto_entidad_id=contexto_entidad_id, limit=limit,
    )
    items = [ArchivoDigitalResponse(**r) for r in rows]
    return ArchivoListResponse(items=items, total=len(items))


@router.get(
    '/duplicados',
    response_model=DuplicadosResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def buscar_duplicados(
    hash: str = Query(..., min_length=32, max_length=128),
    limit: int = Query(default=10, ge=1, le=50),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> DuplicadosResponse:
    rows = await svc.buscar_duplicados_por_hash(
        conn, tenant_id=perfil.tenant_id, hash_sha256=hash, limit=limit,
    )
    return DuplicadosResponse(
        hash_sha256=hash,
        coincidencias=[ArchivoDigitalResponse(**r) for r in rows],
        total=len(rows),
    )


@router.post(
    '/aplicar-retencion',
    response_model=RetencionExecResult,
    dependencies=[Depends(require_gd_perfil)],
)
async def aplicar_retencion(
    body: AplicarRetencionRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RetencionExecResult:
    r = await svc.aplicar_politica_retencion(
        conn, tenant_id=perfil.tenant_id,
        dry_run=body.dry_run, limit=body.limit,
    )
    await emit_gd_event(
        conn, tipo_evento='ArchivoRetencionAplicada',
        accion='aplicar_retencion',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='archivo_digital',
        entidad_afectada_id=perfil.tenant_id,  # batch
        valor_nuevo={'purgados': r['purgados'],
                      'evaluados': r['candidatos_evaluados'],
                      'dry_run': body.dry_run},
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return RetencionExecResult(**r)


# =============================================================================
# Upload (multipart)
# =============================================================================

@router.post(
    '',
    response_model=ArchivoDigitalResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def subir(
    request: Request,
    archivo: UploadFile = File(...),
    proposito: str = Form(default='general'),
    contexto_entidad_tipo: str | None = Form(default=None),
    contexto_entidad_id: UUID | None = Form(default=None),
    retencion_politica: str | None = Form(default=None),
    storage_backend: str = Form(default='filesystem'),
    encriptado_at_rest: bool = Form(default=False),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ArchivoDigitalResponse:
    contenido = await archivo.read()
    row = await svc.subir_archivo(
        conn, tenant_id=perfil.tenant_id,
        nombre_original=archivo.filename or 'sin_nombre',
        mime_type=archivo.content_type or 'application/octet-stream',
        contenido=contenido,
        proposito=proposito,
        contexto_entidad_tipo=contexto_entidad_tipo,
        contexto_entidad_id=contexto_entidad_id,
        retencion_politica=retencion_politica,
        storage_backend=storage_backend,
        encriptado_at_rest=encriptado_at_rest,
        cargado_por_user_id=perfil.user_id,
    )

    tipo_evento = ('ArchivoSubido' if row['analisis_antivirus'] == 'limpio'
                   else 'ArchivoBloqueadoAntivirus')
    crit = (AuditCriticidad.MEDIA if row['analisis_antivirus'] == 'limpio'
            else AuditCriticidad.CRITICA)
    await emit_gd_event(
        conn, tipo_evento=tipo_evento, accion='subir',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='archivo_digital',
        entidad_afectada_id=row['id'],
        valor_nuevo={'proposito': proposito,
                      'mime_type': row['mime_type'],
                      'tamano_bytes': row['tamano_bytes'],
                      'antivirus': row['analisis_antivirus']},
        criticidad=crit,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ArchivoDigitalResponse(**row)


@router.get(
    '/{archivo_id}',
    response_model=ArchivoDigitalResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def detalle(
    archivo_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ArchivoDigitalResponse:
    row = await svc.obtener_archivo(
        conn, tenant_id=perfil.tenant_id, archivo_id=archivo_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return ArchivoDigitalResponse(**row)


@router.post(
    '/{archivo_id}/attach-proposito',
    response_model=ArchivoDigitalResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def attach_proposito(
    body: AttachPropositoRequest, request: Request,
    archivo_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ArchivoDigitalResponse:
    try:
        row = await svc.attach_proposito(
            conn, tenant_id=perfil.tenant_id, archivo_id=archivo_id,
            proposito=body.proposito,
            contexto_entidad_tipo=body.contexto_entidad_tipo,
            contexto_entidad_id=body.contexto_entidad_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='ArchivoPropositoActualizado', accion='attach_proposito',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='archivo_digital', entidad_afectada_id=archivo_id,
        valor_nuevo={'proposito': body.proposito,
                      'contexto_tipo': body.contexto_entidad_tipo,
                      'contexto_id': str(body.contexto_entidad_id) if body.contexto_entidad_id else None},
        criticidad=AuditCriticidad.BAJA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ArchivoDigitalResponse(**row)


@router.post(
    '/{archivo_id}/descargar',
    response_model=DescargaArchivoResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def descargar(
    request: Request,
    archivo_id: UUID = Path(...),
    motivo: str | None = Query(default=None, max_length=500),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> DescargaArchivoResponse:
    try:
        r = await svc.descargar_archivo(
            conn, tenant_id=perfil.tenant_id, archivo_id=archivo_id,
            usuario_id=perfil.user_id, motivo=motivo,
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get('user-agent'),
            request_id=getattr(request.state, 'request_id', None),
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if r is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='ArchivoDescargado', accion='descargar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='archivo_digital', entidad_afectada_id=archivo_id,
        valor_nuevo={'descarga_id': str(r['descarga_id'])},
        criticidad=AuditCriticidad.BAJA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return DescargaArchivoResponse(**r)


@router.post(
    '/{archivo_id}/anular',
    response_model=ArchivoDigitalResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def anular(
    body: AnularArchivoRequest, request: Request,
    archivo_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ArchivoDigitalResponse:
    try:
        row = await svc.anular_archivo(
            conn, tenant_id=perfil.tenant_id, archivo_id=archivo_id,
            motivo=body.motivo, usuario_actor_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='ArchivoAnulado', accion='anular',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='archivo_digital', entidad_afectada_id=archivo_id,
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ArchivoDigitalResponse(**row)


@router.post(
    '/{archivo_id}/reextraer',
    response_model=ExtraccionResultadoResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def reextraer(
    body: ReextraerRequest, request: Request,
    archivo_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ExtraccionResultadoResponse:
    try:
        r = await svc.extraer_texto(
            conn, tenant_id=perfil.tenant_id, archivo_id=archivo_id,
            forzar=True, motor_preferido=body.motor,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_estado(e) from e
    if r is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='ArchivoReextraccion', accion='reextraer',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='archivo_digital', entidad_afectada_id=archivo_id,
        valor_nuevo={'motor': r['motor']},
        criticidad=AuditCriticidad.BAJA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ExtraccionResultadoResponse(**r)


@router.get(
    '/{archivo_id}/extraccion',
    response_model=ExtraccionResultadoResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def consultar_extraccion(
    archivo_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ExtraccionResultadoResponse:
    # Buscar la última extracción para este archivo (cualquier motor).
    row = await conn.fetchrow(
        """
        select id, archivo_digital_id, motor, version, texto_completo,
               paginas_jsonb, confianza, warning_baja_confianza,
               truncado, motivo_truncado, extraido_en, duracion_ms
        from core.extraccion_resultado
        where archivo_digital_id = $1 and tenant_id = $2
        order by extraido_en desc limit 1
        """,
        archivo_id, perfil.tenant_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found',
                                          'code': 'sin_extraccion'})
    d = dict(row)
    d['paginas'] = d.pop('paginas_jsonb')
    import json as _json
    if isinstance(d.get('paginas'), str):
        d['paginas'] = _json.loads(d['paginas'])
    return ExtraccionResultadoResponse(**d)


__all__ = ['router']
