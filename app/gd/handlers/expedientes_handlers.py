"""Handlers HTTP de EP-016 expediente electrónico (bloque 17).

Endpoints (10):
- POST /api/v1/gd/expedientes
- GET  /api/v1/gd/expedientes
- GET  /api/v1/gd/expedientes/{id}
- PATCH /api/v1/gd/expedientes/{id}
- POST /api/v1/gd/expedientes/{id}/cerrar         GD-API-0101
- POST /api/v1/gd/expedientes/{id}/reabrir        GD-API-0101
- POST /api/v1/gd/expedientes/{id}/transferir     (placeholder fase 2)
- POST /api/v1/gd/expedientes/{id}/items          (GD-API-0102 polimórfico)
- POST /api/v1/gd/expedientes/{id}/items/{tipo}/{item_id}/retirar
- GET  /api/v1/gd/expedientes/{id}/contenido      GD-API-0103
"""
from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.expedientes import (
    AsociarItemRequest,
    CerrarExpedienteRequest,
    ContenidoExpedienteResponse,
    CrearExpedienteRequest,
    ExpedienteItemResponse,
    ExpedienteListItem,
    ExpedienteListResponse,
    ExpedienteResponse,
    PatchExpedienteRequest,
    ReabrirExpedienteRequest,
    RetirarItemRequest,
    TransferirExpedienteRequest,
)
from app.gd.security import GdPerfilContext, require_gd_perfil
from app.gd.services import expedientes as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router = APIRouter(prefix='/expedientes', tags=['gd:expedientes'])


def _err_estado(e: ValueError) -> HTTPException:
    return HTTPException(409, detail={'error': 'conflict', 'code': str(e)})


# =============================================================================
# CRUD
# =============================================================================

@router.post(
    '',
    response_model=ExpedienteResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def crear_expediente(
    body: CrearExpedienteRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ExpedienteResponse:
    try:
        row = await svc.crear_expediente(
            conn, tenant_id=perfil.tenant_id,
            codigo=body.codigo, titulo=body.titulo,
            descripcion=body.descripcion,
            dependencia_responsable_id=body.dependencia_responsable_id,
            serie_id=body.serie_id, subserie_id=body.subserie_id,
            metadata=body.metadata, abierto_por_user_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e

    await emit_gd_event(
        conn, tipo_evento='ExpedienteAbierto', accion='crear',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='expediente', entidad_afectada_id=row['id'],
        valor_nuevo={'codigo': body.codigo,
                      'serie_id': str(body.serie_id) if body.serie_id else None},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ExpedienteResponse(**row)


@router.get(
    '',
    response_model=ExpedienteListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_expedientes(
    estado: str | None = Query(default=None),
    dependencia_id: UUID | None = Query(default=None),
    serie_id: UUID | None = Query(default=None),
    subserie_id: UUID | None = Query(default=None),
    codigo: str | None = Query(default=None),
    q: str | None = Query(default=None, description='Búsqueda por título'),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ExpedienteListResponse:
    rows = await svc.listar_expedientes(
        conn, tenant_id=perfil.tenant_id,
        estado=estado, dependencia_id=dependencia_id,
        serie_id=serie_id, subserie_id=subserie_id,
        codigo_like=codigo, titulo_like=q, limit=limit,
    )
    total = await svc.contar_expedientes(conn, tenant_id=perfil.tenant_id)
    items = [ExpedienteListItem(**r) for r in rows]
    return ExpedienteListResponse(items=items, total=total)


@router.get(
    '/{expediente_id}',
    response_model=ExpedienteResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def detalle_expediente(
    expediente_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ExpedienteResponse:
    row = await svc.obtener_expediente(
        conn, tenant_id=perfil.tenant_id, expediente_id=expediente_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return ExpedienteResponse(**row)


@router.patch(
    '/{expediente_id}',
    response_model=ExpedienteResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def patch_expediente(
    body: PatchExpedienteRequest, request: Request,
    expediente_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ExpedienteResponse:
    cambios = body.model_dump(exclude_none=True)
    try:
        row = await svc.patch_expediente(
            conn, tenant_id=perfil.tenant_id,
            expediente_id=expediente_id, cambios=cambios,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='ExpedienteActualizado', accion='patch',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='expediente', entidad_afectada_id=expediente_id,
        valor_nuevo={k: 'changed' for k in cambios.keys()},
        criticidad=AuditCriticidad.BAJA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ExpedienteResponse(**row)


# =============================================================================
# Lifecycle
# =============================================================================

@router.post(
    '/{expediente_id}/cerrar',
    response_model=ExpedienteResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def cerrar(
    body: CerrarExpedienteRequest, request: Request,
    expediente_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ExpedienteResponse:
    try:
        row = await svc.cerrar_expediente(
            conn, tenant_id=perfil.tenant_id,
            expediente_id=expediente_id, motivo=body.motivo,
            usuario_actor_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='ExpedienteCerrado', accion='cerrar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='expediente', entidad_afectada_id=expediente_id,
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ExpedienteResponse(**row)


@router.post(
    '/{expediente_id}/reabrir',
    response_model=ExpedienteResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def reabrir(
    body: ReabrirExpedienteRequest, request: Request,
    expediente_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ExpedienteResponse:
    try:
        row = await svc.reabrir_expediente(
            conn, tenant_id=perfil.tenant_id,
            expediente_id=expediente_id, motivo=body.motivo,
            usuario_actor_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='ExpedienteReabierto', accion='reabrir',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='expediente', entidad_afectada_id=expediente_id,
        justificacion=body.motivo,
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ExpedienteResponse(**row)


@router.post(
    '/{expediente_id}/transferir',
    response_model=ExpedienteResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def transferir(
    body: TransferirExpedienteRequest, request: Request,
    expediente_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ExpedienteResponse:
    try:
        row = await svc.transferir_expediente(
            conn, tenant_id=perfil.tenant_id,
            expediente_id=expediente_id,
            destino=body.destino, motivo=body.motivo,
            usuario_actor_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='ExpedienteTransferido', accion='transferir',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='expediente', entidad_afectada_id=expediente_id,
        valor_nuevo={'destino': body.destino},
        justificacion=body.motivo,
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ExpedienteResponse(**row)


# =============================================================================
# Items (GD-API-0102)
# =============================================================================

@router.post(
    '/{expediente_id}/items',
    response_model=ExpedienteItemResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def asociar_item(
    body: AsociarItemRequest, request: Request,
    expediente_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ExpedienteItemResponse:
    try:
        row = await svc.asociar_item(
            conn, tenant_id=perfil.tenant_id,
            expediente_id=expediente_id,
            item_tipo=body.item_tipo, item_id=body.item_id,
            orden=body.orden, vinculado_por_user_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='ExpedienteItemVinculado', accion='asociar_item',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='expediente_item', entidad_afectada_id=row['id'],
        valor_nuevo={'expediente_id': str(expediente_id),
                      'item_tipo': body.item_tipo,
                      'item_id': str(body.item_id)},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ExpedienteItemResponse(**row)


@router.post(
    '/{expediente_id}/items/{item_tipo}/{item_id}/retirar',
    response_model=ExpedienteItemResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def retirar_item(
    body: RetirarItemRequest, request: Request,
    expediente_id: UUID = Path(...),
    item_tipo: str = Path(...,
                           pattern='^(documento|radicado|pqrsd|correspondencia)$'),
    item_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ExpedienteItemResponse:
    row = await svc.retirar_item(
        conn, tenant_id=perfil.tenant_id,
        expediente_id=expediente_id,
        item_tipo=item_tipo, item_id=item_id,
        motivo=body.motivo, usuario_actor_id=perfil.user_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found',
                                          'code': 'vinculo_no_existe'})

    await emit_gd_event(
        conn, tipo_evento='ExpedienteItemRetirado', accion='retirar_item',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='expediente_item', entidad_afectada_id=row['id'],
        valor_nuevo={'expediente_id': str(expediente_id),
                      'item_tipo': item_tipo, 'item_id': str(item_id)},
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ExpedienteItemResponse(**row)


# =============================================================================
# Contenido agregado (GD-API-0103)
# =============================================================================

@router.get(
    '/{expediente_id}/contenido',
    response_model=ContenidoExpedienteResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def contenido(
    expediente_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ContenidoExpedienteResponse:
    data = await svc.obtener_contenido(
        conn, tenant_id=perfil.tenant_id, expediente_id=expediente_id,
    )
    if data is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return ContenidoExpedienteResponse(
        expediente=ExpedienteResponse(**data['expediente']),
        items_vinculados=[ExpedienteItemResponse(**i)
                            for i in data['items_vinculados']],
        items_retirados=[ExpedienteItemResponse(**i)
                           for i in data['items_retirados']],
        totales_por_tipo=data['totales_por_tipo'],
    )


__all__ = ['router']
