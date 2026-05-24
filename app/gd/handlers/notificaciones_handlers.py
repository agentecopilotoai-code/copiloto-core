"""GD-API-0040 — Notificaciones in-app + preferencias."""
from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from app.db.pool import get_db
from app.gd.schemas.notificaciones import (
    NotificacionMarcarLeidaResponse,
    NotificacionPreferenciaItem,
    NotificacionPreferenciasPatch,
    NotificacionPreferenciasResponse,
    NotificacionResponse,
    NotificacionesListResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil
from app.gd.services import notificaciones as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router_notif = APIRouter(prefix='/notificaciones', tags=['gd:notificaciones'])
router_pref = APIRouter(prefix='/notificaciones/preferencias', tags=['gd:notificaciones'])


@router_notif.get(
    '',
    response_model=NotificacionesListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_notificaciones(
    solo_no_leidas: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> NotificacionesListResponse:
    rows = await svc.listar_notificaciones(
        conn, tenant_id=perfil.tenant_id,
        destinatario_user_id=perfil.user_id,
        solo_no_leidas=solo_no_leidas, limit=limit,
    )
    no_leidas = await svc.contar_no_leidas(
        conn, tenant_id=perfil.tenant_id, destinatario_user_id=perfil.user_id,
    )
    total = await svc.contar_total(
        conn, tenant_id=perfil.tenant_id, destinatario_user_id=perfil.user_id,
    )
    return NotificacionesListResponse(
        items=[NotificacionResponse(**r) for r in rows],
        no_leidas=no_leidas,
        total=total,
    )


@router_notif.post(
    '/{notificacion_id}/marcar-leida',
    response_model=NotificacionMarcarLeidaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def marcar_leida(
    request: Request,
    notificacion_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> NotificacionMarcarLeidaResponse:
    row = await svc.marcar_leida(
        conn, tenant_id=perfil.tenant_id,
        notificacion_id=notificacion_id,
        destinatario_user_id=perfil.user_id,
    )
    if row is None:
        raise HTTPException(
            404,
            detail={
                'error': 'not_found',
                'message': 'Notificación no existe, ya leída, o no pertenece al usuario.',
            },
        )
    return NotificacionMarcarLeidaResponse(**row)


# =============================================================================
# /notificaciones/preferencias
# =============================================================================

@router_pref.get(
    '',
    response_model=NotificacionPreferenciasResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def obtener_preferencias(
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> NotificacionPreferenciasResponse:
    rows = await svc.obtener_preferencias_usuario(
        conn, tenant_id=perfil.tenant_id, user_id=perfil.user_id,
    )
    return NotificacionPreferenciasResponse(
        preferencias=[NotificacionPreferenciaItem(**r) for r in rows],
    )


@router_pref.patch(
    '',
    response_model=NotificacionPreferenciasResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def patch_preferencias(
    body: NotificacionPreferenciasPatch, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> NotificacionPreferenciasResponse:
    cambios = [p.model_dump() for p in body.preferencias]
    afectados = await svc.upsert_preferencias(
        conn, tenant_id=perfil.tenant_id, user_id=perfil.user_id,
        preferencias=cambios,
    )

    if afectados:
        await emit_gd_event(
            conn,
            tipo_evento='gd.notificacion_preferencia.modificada',
            accion='upsert_preferencias',
            tenant_id=perfil.tenant_id,
            usuario_id=perfil.user_id,
            entidad_afectada_tipo='notificacion_preferencia',
            entidad_afectada_id=perfil.user_id,
            valor_nuevo={'afectados': afectados},
            criticidad=AuditCriticidad.BAJA,
            request_id=getattr(request.state, 'request_id', None),
        )

    rows = await svc.obtener_preferencias_usuario(
        conn, tenant_id=perfil.tenant_id, user_id=perfil.user_id,
    )
    return NotificacionPreferenciasResponse(
        preferencias=[NotificacionPreferenciaItem(**r) for r in rows],
    )


__all__ = ['router_notif', 'router_pref']
