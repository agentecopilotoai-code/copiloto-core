"""GD-API-0034 + GD-API-0035 — Contactos del tercero + historial."""
from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Request, status

from app.db.pool import get_db
from app.gd.schemas.contactos import (
    ContactosListResponse, ContactoTerceroCreate,
    ContactoTerceroInactivarRequest, ContactoTerceroResponse,
    HistorialItemTercero, HistorialTerceroResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil, require_gd_permission
from app.gd.services import contactos as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router = APIRouter(prefix='/terceros/{tercero_id}', tags=['gd:contactos'])


@router.post(
    '/contactos',
    response_model=ContactoTerceroResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_permission('PERM-VU-001', alcance='institucional'))],
)
async def crear_contacto(
    body: ContactoTerceroCreate, request: Request,
    tercero_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ContactoTerceroResponse:
    try:
        row = await svc.crear_contacto(
            conn, tenant_id=perfil_actor.tenant_id, tercero_id=tercero_id,
            tipo_contacto=body.tipo_contacto, valor=body.valor,
            es_principal=body.es_principal,
        )
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(
            404,
            detail={'error': 'not_found', 'message': 'tercero_id no existe'},
        )

    await emit_gd_event(
        conn,
        tipo_evento='gd.contacto_tercero.creado',
        accion='crear',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='contacto_tercero',
        entidad_afectada_id=row['id'],
        valor_nuevo={
            'tercero_id': str(tercero_id), 'tipo_contacto': body.tipo_contacto,
        },
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ContactoTerceroResponse(**row)


@router.get(
    '/contactos',
    response_model=ContactosListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_contactos(
    tercero_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ContactosListResponse:
    rows = await svc.listar_contactos(
        conn, tenant_id=perfil.tenant_id, tercero_id=tercero_id,
    )
    return ContactosListResponse(items=[ContactoTerceroResponse(**r) for r in rows])


@router.post(
    '/contactos/{contacto_id}/inactivar',
    response_model=ContactoTerceroResponse,
    dependencies=[Depends(require_gd_permission('PERM-VU-001', alcance='institucional'))],
)
async def inactivar_contacto(
    body: ContactoTerceroInactivarRequest, request: Request,
    tercero_id: UUID = Path(...),
    contacto_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ContactoTerceroResponse:
    row = await svc.inactivar_contacto(
        conn, tenant_id=perfil_actor.tenant_id, contacto_id=contacto_id,
    )
    if row is None:
        raise HTTPException(
            404,
            detail={'error': 'not_found', 'message': 'Contacto no existe o ya está inactivo'},
        )

    await emit_gd_event(
        conn,
        tipo_evento='gd.contacto_tercero.inactivado',
        accion='inactivar',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='contacto_tercero',
        entidad_afectada_id=contacto_id,
        justificacion=body.motivo,
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ContactoTerceroResponse(**row)


@router.get(
    '/historial',
    response_model=HistorialTerceroResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def historial_tercero(
    tercero_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> HistorialTerceroResponse:
    resultado = await svc.obtener_historial_tercero(
        conn, tenant_id=perfil.tenant_id, tercero_id=tercero_id,
    )
    return HistorialTerceroResponse(
        tercero_id=resultado['tercero_id'],
        items=[HistorialItemTercero(**i) for i in resultado['items']],
        totales=resultado['totales'],
    )


__all__ = ['router']
