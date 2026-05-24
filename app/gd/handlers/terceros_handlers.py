"""GD-API-0033 — CRUD de terceros con detección de duplicados."""
from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.terceros import (
    TerceroBusquedaResponse, TerceroCreate, TerceroListItem,
    TerceroPatch, TerceroResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil, require_gd_permission
from app.gd.services import terceros as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router = APIRouter(prefix='/terceros', tags=['gd:terceros'])


@router.post(
    '',
    response_model=TerceroResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_permission('PERM-VU-001', alcance='institucional'))],
)
async def crear_tercero(
    body: TerceroCreate, request: Request,
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TerceroResponse:
    try:
        row = await svc.crear_tercero(
            conn, tenant_id=perfil_actor.tenant_id,
            datos=body.model_dump(),
            created_by_user_id=perfil_actor.user_id,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            409,
            detail={
                'error': 'conflict',
                'code': 'tercero_duplicado',
                'message': 'Ya existe un tercero con ese documento.',
            },
        )

    await emit_gd_event(
        conn,
        tipo_evento='gd.tercero.creado',
        accion='crear',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='tercero',
        entidad_afectada_id=row['id'],
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return TerceroResponse(**row)


@router.get(
    '/buscar',
    response_model=TerceroBusquedaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def buscar_terceros(
    documento: str | None = Query(default=None),
    nombre: str | None = Query(default=None),
    email: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TerceroBusquedaResponse:
    resultado = await svc.buscar_tercero(
        conn, tenant_id=perfil.tenant_id,
        documento=documento, nombre=nombre, email=email, limit=limit,
    )
    return TerceroBusquedaResponse(
        items=[TerceroListItem(**r) for r in resultado['items']],
        posibles_duplicados=[TerceroListItem(**r) for r in resultado['posibles_duplicados']],
    )


@router.get(
    '/{tercero_id}',
    response_model=TerceroResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def obtener_tercero(
    tercero_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TerceroResponse:
    row = await svc.obtener_tercero(
        conn, tenant_id=perfil.tenant_id, tercero_id=tercero_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return TerceroResponse(**row)


@router.patch(
    '/{tercero_id}',
    response_model=TerceroResponse,
    dependencies=[Depends(require_gd_permission('PERM-VU-001', alcance='institucional'))],
)
async def patch_tercero(
    body: TerceroPatch, request: Request,
    tercero_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TerceroResponse:
    cambios = body.model_dump(exclude_unset=True)
    row = await svc.actualizar_tercero(
        conn, tenant_id=perfil_actor.tenant_id,
        tercero_id=tercero_id, cambios=cambios,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    if cambios:
        await emit_gd_event(
            conn,
            tipo_evento='gd.tercero.modificado',
            accion='actualizar',
            tenant_id=perfil_actor.tenant_id,
            usuario_id=perfil_actor.user_id,
            entidad_afectada_tipo='tercero',
            entidad_afectada_id=tercero_id,
            valor_nuevo=cambios,
            criticidad=AuditCriticidad.MEDIA,
            request_id=getattr(request.state, 'request_id', None),
        )
    return TerceroResponse(**row)


__all__ = ['router']
