"""Handlers HTTP de EP-017 RPA + APIs públicas (bloque 18).

Endpoints (16):
Identidades técnicas (GD-API-0105):
- POST /api/v1/gd/identidades-tecnicas
- GET  /api/v1/gd/identidades-tecnicas
- GET  /api/v1/gd/identidades-tecnicas/{id}
- POST /api/v1/gd/identidades-tecnicas/{id}/revocar
- POST /api/v1/gd/identidades-tecnicas/{id}/rotar-key

Tareas RPA (GD-API-0106):
- POST /api/v1/gd/rpa/tareas                (admin crea)
- GET  /api/v1/gd/rpa/tareas-pendientes     (robot lista)
- POST /api/v1/gd/rpa/tareas/reclamar       (robot reclama next)
- POST /api/v1/gd/rpa/tareas/{id}/resultado (robot reporta)
- GET  /api/v1/gd/rpa/tareas                (admin lista todas)

Webhooks (GD-API-0108):
- POST /api/v1/gd/webhooks/suscripciones
- GET  /api/v1/gd/webhooks/suscripciones
- GET  /api/v1/gd/webhooks/suscripciones/{id}
- PATCH /api/v1/gd/webhooks/suscripciones/{id}
- GET  /api/v1/gd/webhooks/deliveries

Rate limit (GD-API-0109):
- GET  /api/v1/gd/rate-limit/identidades-tecnicas/{id}/info
"""
from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.rpa import (
    CrearIdentidadTecnicaRequest,
    CrearTareaRPARequest,
    CrearWebhookSubRequest,
    IdentidadListResponse,
    IdentidadTecnicaCreadaResponse,
    IdentidadTecnicaResponse,
    PatchWebhookSubRequest,
    RateLimitInfo,
    ReclamarTareaRequest,
    ReportarResultadoRequest,
    RevocarIdentidadRequest,
    RotarApiKeyRequest,
    TareaRPAListResponse,
    TareaRPAResponse,
    WebhookDeliveryListResponse,
    WebhookDeliveryResponse,
    WebhookSubCreadaResponse,
    WebhookSubResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil
from app.gd.services import rpa as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router_ident = APIRouter(prefix='/identidades-tecnicas',
                          tags=['gd:rpa:identidades'])
router_rpa = APIRouter(prefix='/rpa', tags=['gd:rpa:tareas'])
router_wh = APIRouter(prefix='/webhooks', tags=['gd:webhooks'])
router_rl = APIRouter(prefix='/rate-limit', tags=['gd:rate-limit'])


def _err_estado(e: ValueError) -> HTTPException:
    return HTTPException(409, detail={'error': 'conflict', 'code': str(e)})


def _err_not_found(e: LookupError) -> HTTPException:
    return HTTPException(404, detail={'error': 'not_found', 'code': str(e)})


# =============================================================================
# Identidades técnicas (GD-API-0105)
# =============================================================================

@router_ident.post(
    '',
    response_model=IdentidadTecnicaCreadaResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def crear_identidad(
    body: CrearIdentidadTecnicaRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> IdentidadTecnicaCreadaResponse:
    try:
        row, api_key = await svc.crear_identidad_tecnica(
            conn, tenant_id=perfil.tenant_id,
            codigo=body.codigo, nombre=body.nombre,
            descripcion=body.descripcion, tipo=body.tipo,
            scopes=body.scopes, rate_limit_rpm=body.rate_limit_rpm,
            dependencia_alcance_id=body.dependencia_alcance_id,
            created_by_user_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e

    await emit_gd_event(
        conn, tipo_evento='IdentidadTecnicaCreada', accion='crear',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='identidad_tecnica',
        entidad_afectada_id=row['id'],
        valor_nuevo={'codigo': body.codigo, 'tipo': body.tipo,
                      'scopes_count': len(body.scopes)},
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return IdentidadTecnicaCreadaResponse(**{**row, 'api_key': api_key})


@router_ident.get(
    '',
    response_model=IdentidadListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_identidades(
    tipo: str | None = Query(default=None),
    estado: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> IdentidadListResponse:
    rows = await svc.listar_identidades(
        conn, tenant_id=perfil.tenant_id,
        tipo=tipo, estado=estado, limit=limit,
    )
    items = [IdentidadTecnicaResponse(**r) for r in rows]
    return IdentidadListResponse(items=items, total=len(items))


@router_ident.get(
    '/{identidad_id}',
    response_model=IdentidadTecnicaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def detalle_identidad(
    identidad_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> IdentidadTecnicaResponse:
    row = await svc.obtener_identidad(
        conn, tenant_id=perfil.tenant_id, identidad_id=identidad_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return IdentidadTecnicaResponse(**row)


@router_ident.post(
    '/{identidad_id}/revocar',
    response_model=IdentidadTecnicaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def revocar_identidad(
    body: RevocarIdentidadRequest, request: Request,
    identidad_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> IdentidadTecnicaResponse:
    try:
        row = await svc.revocar_identidad(
            conn, tenant_id=perfil.tenant_id,
            identidad_id=identidad_id, motivo=body.motivo,
            revocada_por_user_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='IdentidadTecnicaRevocada', accion='revocar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='identidad_tecnica',
        entidad_afectada_id=identidad_id,
        justificacion=body.motivo,
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return IdentidadTecnicaResponse(**row)


@router_ident.post(
    '/{identidad_id}/rotar-key',
    response_model=IdentidadTecnicaCreadaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def rotar_key(
    body: RotarApiKeyRequest, request: Request,
    identidad_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> IdentidadTecnicaCreadaResponse:
    try:
        res = await svc.rotar_api_key(
            conn, tenant_id=perfil.tenant_id, identidad_id=identidad_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if res is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    row, api_key = res

    await emit_gd_event(
        conn, tipo_evento='IdentidadTecnicaKeyRotada', accion='rotar_key',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='identidad_tecnica',
        entidad_afectada_id=identidad_id,
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return IdentidadTecnicaCreadaResponse(**{**row, 'api_key': api_key})


# =============================================================================
# Tareas RPA (GD-API-0106)
# =============================================================================

@router_rpa.post(
    '/tareas',
    response_model=TareaRPAResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def crear_tarea(
    body: CrearTareaRPARequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TareaRPAResponse:
    row = await svc.crear_tarea_rpa(
        conn, tenant_id=perfil.tenant_id,
        tipo=body.tipo, payload=body.payload, prioridad=body.prioridad,
        identidad_tecnica_id=body.identidad_tecnica_id,
        created_by_user_id=perfil.user_id,
    )

    await emit_gd_event(
        conn, tipo_evento='TareaRPACreada', accion='crear_tarea',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='tarea_rpa', entidad_afectada_id=row['id'],
        valor_nuevo={'tipo': body.tipo, 'prioridad': body.prioridad},
        criticidad=AuditCriticidad.BAJA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return TareaRPAResponse(**row)


@router_rpa.get(
    '/tareas-pendientes',
    response_model=TareaRPAListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def tareas_pendientes(
    tipo: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TareaRPAListResponse:
    rows = await svc.listar_tareas_rpa(
        conn, tenant_id=perfil.tenant_id,
        estado='pending', tipo=tipo, limit=limit,
    )
    items = [TareaRPAResponse(**r) for r in rows]
    return TareaRPAListResponse(items=items, total=len(items))


@router_rpa.post(
    '/tareas/reclamar',
    response_model=TareaRPAResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def reclamar_tarea(
    body: ReclamarTareaRequest, request: Request,
    identidad_tecnica_id: UUID = Query(...,
        description='En producción se infiere del API key. Aquí explícito para tests.'),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TareaRPAResponse:
    row = await svc.reclamar_tarea(
        conn, tenant_id=perfil.tenant_id,
        identidad_tecnica_id=identidad_tecnica_id,
        tipo=body.tipo, ttl_segundos=body.ttl_segundos,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found',
                                          'code': 'sin_tareas_pendientes'})

    await emit_gd_event(
        conn, tipo_evento='TareaRPAReclamada', accion='reclamar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='tarea_rpa', entidad_afectada_id=row['id'],
        valor_nuevo={'identidad_tecnica_id': str(identidad_tecnica_id)},
        criticidad=AuditCriticidad.BAJA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return TareaRPAResponse(**row)


@router_rpa.post(
    '/tareas/{tarea_id}/resultado',
    response_model=TareaRPAResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def reportar(
    body: ReportarResultadoRequest, request: Request,
    tarea_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TareaRPAResponse:
    try:
        row = await svc.reportar_resultado(
            conn, tenant_id=perfil.tenant_id, tarea_id=tarea_id,
            claim_token=body.claim_token, estado=body.estado,
            resultado=body.resultado,
            error_texto=body.error_texto, error_codigo=body.error_codigo,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    tipo_evento = 'TareaRPACompletada' if body.estado == 'done' else 'TareaRPAFallida'
    await emit_gd_event(
        conn, tipo_evento=tipo_evento, accion='reportar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='tarea_rpa', entidad_afectada_id=tarea_id,
        valor_nuevo={'estado': body.estado},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return TareaRPAResponse(**row)


@router_rpa.get(
    '/tareas',
    response_model=TareaRPAListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_tareas(
    estado: str | None = Query(default=None),
    tipo: str | None = Query(default=None),
    identidad_tecnica_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TareaRPAListResponse:
    rows = await svc.listar_tareas_rpa(
        conn, tenant_id=perfil.tenant_id,
        estado=estado, tipo=tipo,
        identidad_tecnica_id=identidad_tecnica_id, limit=limit,
    )
    items = [TareaRPAResponse(**r) for r in rows]
    return TareaRPAListResponse(items=items, total=len(items))


# =============================================================================
# Webhooks
# =============================================================================

@router_wh.post(
    '/suscripciones',
    response_model=WebhookSubCreadaResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def crear_sub(
    body: CrearWebhookSubRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> WebhookSubCreadaResponse:
    try:
        row, secret = await svc.crear_webhook_sub(
            conn, tenant_id=perfil.tenant_id,
            identidad_tecnica_id=body.identidad_tecnica_id,
            url=body.url, eventos_suscritos=body.eventos_suscritos,
            descripcion=body.descripcion,
            max_intentos=body.max_intentos,
            backoff_inicial_segundos=body.backoff_inicial_segundos,
            backoff_max_segundos=body.backoff_max_segundos,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_estado(e) from e

    await emit_gd_event(
        conn, tipo_evento='WebhookSuscripcionCreada', accion='crear',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='webhook_subscripcion',
        entidad_afectada_id=row['id'],
        valor_nuevo={'url': body.url,
                      'eventos': len(body.eventos_suscritos)},
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return WebhookSubCreadaResponse(**{**row, 'secret': secret})


@router_wh.get(
    '/suscripciones',
    response_model=list[WebhookSubResponse],
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_subs(
    identidad_tecnica_id: UUID | None = Query(default=None),
    estado: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> list[WebhookSubResponse]:
    rows = await svc.listar_webhook_subs(
        conn, tenant_id=perfil.tenant_id,
        identidad_tecnica_id=identidad_tecnica_id, estado=estado, limit=limit,
    )
    return [WebhookSubResponse(**r) for r in rows]


@router_wh.get(
    '/suscripciones/{sub_id}',
    response_model=WebhookSubResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def detalle_sub(
    sub_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> WebhookSubResponse:
    row = await svc.obtener_webhook_sub(
        conn, tenant_id=perfil.tenant_id, sub_id=sub_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return WebhookSubResponse(**row)


@router_wh.patch(
    '/suscripciones/{sub_id}',
    response_model=WebhookSubResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def patch_sub(
    body: PatchWebhookSubRequest, request: Request,
    sub_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> WebhookSubResponse:
    cambios = body.model_dump(exclude_none=True)
    row = await svc.patch_webhook_sub(
        conn, tenant_id=perfil.tenant_id, sub_id=sub_id, cambios=cambios,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='WebhookSuscripcionActualizada', accion='patch',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='webhook_subscripcion',
        entidad_afectada_id=sub_id,
        valor_nuevo=cambios,
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return WebhookSubResponse(**row)


@router_wh.get(
    '/deliveries',
    response_model=WebhookDeliveryListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_deliveries_h(
    suscripcion_id: UUID | None = Query(default=None),
    estado: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> WebhookDeliveryListResponse:
    rows = await svc.listar_deliveries(
        conn, tenant_id=perfil.tenant_id,
        suscripcion_id=suscripcion_id, estado=estado, limit=limit,
    )
    items = [WebhookDeliveryResponse(**r) for r in rows]
    return WebhookDeliveryListResponse(items=items, total=len(items))


# =============================================================================
# Rate limit info (GD-API-0109)
# =============================================================================

@router_rl.get(
    '/identidades-tecnicas/{identidad_id}/info',
    response_model=RateLimitInfo,
    dependencies=[Depends(require_gd_perfil)],
)
async def rate_limit_info(
    identidad_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RateLimitInfo:
    ident = await svc.obtener_identidad(
        conn, tenant_id=perfil.tenant_id, identidad_id=identidad_id,
    )
    if ident is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    info = await svc.rate_limit_decision(
        conn, tenant_id=perfil.tenant_id,
        identidad_tecnica_id=identidad_id,
        rate_limit_rpm=ident['rate_limit_rpm'],
    )
    return RateLimitInfo(**info)


__all__ = ['router_ident', 'router_rpa', 'router_wh', 'router_rl']
