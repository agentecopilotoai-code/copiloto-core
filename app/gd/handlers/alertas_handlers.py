"""GD-API-0041 — Alertas críticas."""
from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request

from app.db.pool import get_db
from app.gd.schemas.alertas import (
    AlertaEscalarRequest, AlertaMarcarGestionadaRequest,
    AlertaResponse, AlertasListResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil
from app.gd.services import alertas as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router = APIRouter(prefix='/alertas', tags=['gd:alertas'])


@router.get(
    '',
    response_model=AlertasListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_alertas(
    estado: str | None = Query(default=None),
    severidad: str | None = Query(default=None),
    solo_mis: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> AlertasListResponse:
    rows = await svc.listar_alertas(
        conn, tenant_id=perfil.tenant_id,
        destinatario_user_id=perfil.user_id if solo_mis else None,
        estado=estado, severidad=severidad, limit=limit,
    )
    conteos = await svc.contar_activas(
        conn, tenant_id=perfil.tenant_id,
        destinatario_user_id=perfil.user_id if solo_mis else None,
    )
    return AlertasListResponse(
        items=[AlertaResponse(**r) for r in rows],
        total_activas=conteos['total'],
        total_criticas=conteos['criticas'],
    )


@router.post(
    '/{alerta_id}/escalar',
    response_model=AlertaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def escalar_alerta(
    body: AlertaEscalarRequest, request: Request,
    alerta_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> AlertaResponse:
    row = await svc.escalar_alerta(
        conn, tenant_id=perfil.tenant_id, alerta_id=alerta_id,
        user_destino_id=body.user_destino_id, motivo=body.motivo,
        ejecutado_por_user_id=perfil.user_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn,
        tipo_evento='gd.alerta.escalada',
        accion='escalar',
        tenant_id=perfil.tenant_id,
        usuario_id=perfil.user_id,
        entidad_afectada_tipo='alerta',
        entidad_afectada_id=alerta_id,
        valor_nuevo={'user_destino_id': str(body.user_destino_id)},
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return AlertaResponse(**row)


@router.post(
    '/{alerta_id}/marcar-gestionada',
    response_model=AlertaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def marcar_gestionada(
    body: AlertaMarcarGestionadaRequest, request: Request,
    alerta_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> AlertaResponse:
    row = await svc.marcar_gestionada(
        conn, tenant_id=perfil.tenant_id, alerta_id=alerta_id,
        user_id=perfil.user_id, observacion=body.observacion,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn,
        tipo_evento='gd.alerta.gestionada',
        accion='gestionar',
        tenant_id=perfil.tenant_id,
        usuario_id=perfil.user_id,
        entidad_afectada_tipo='alerta',
        entidad_afectada_id=alerta_id,
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return AlertaResponse(**row)


__all__ = ['router']
