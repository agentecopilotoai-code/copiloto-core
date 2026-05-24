"""GD-API-0023 — Endpoints de consecutivos transaccionales radicación.

NOTA: el `siguiente_radicado` POST aquí es para debugging / admin. El uso
operativo real está embebido en GD-API-0024 (crear radicado entrada) y
GD-API-0025 (salida) — esos handlers llaman directamente a la función SQL.
"""
from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.db.pool import get_db
from app.gd.schemas.consecutivos import (
    ConsecutivoResponse,
    ConsecutivosListResponse,
    SiguienteRadicadoRequest,
    SiguienteRadicadoResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil, require_gd_permission
from app.gd.services import consecutivos as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router = APIRouter(prefix='/consecutivos', tags=['gd:consecutivos'])


@router.get(
    '',
    response_model=ConsecutivosListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_consecutivos(
    vigencia: int | None = Query(default=None, ge=2020, le=2100),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ConsecutivosListResponse:
    rows = await svc.listar_consecutivos(
        conn, tenant_id=perfil.tenant_id, vigencia=vigencia,
    )
    return ConsecutivosListResponse(items=[ConsecutivoResponse(**r) for r in rows])


@router.post(
    '/siguiente',
    response_model=SiguienteRadicadoResponse,
    dependencies=[Depends(require_gd_permission('PERM-VU-001', alcance='institucional'))],
)
async def siguiente_radicado(
    body: SiguienteRadicadoRequest, request: Request,
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> SiguienteRadicadoResponse:
    """Genera próximo número (uso debug/admin). Producción usa la función
    embebida en GD-API-0024."""
    try:
        numero = await svc.siguiente_radicado(
            conn, tenant_id=perfil_actor.tenant_id,
            vigencia=body.vigencia, tipo_radicado=body.tipo_radicado,
        )
    except asyncpg.RaiseError as e:
        raise HTTPException(
            409,
            detail={
                'error': 'conflict',
                'code': 'consecutivo_agotado_o_cerrado',
                'message': str(e),
            },
        )

    await emit_gd_event(
        conn,
        tipo_evento='gd.consecutivo.generado',
        accion='generar_numero',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='consecutivo_radicacion',
        entidad_afectada_identificador=numero,
        valor_nuevo={'vigencia': body.vigencia, 'tipo': body.tipo_radicado},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )

    return SiguienteRadicadoResponse(
        numero_radicado=numero,
        vigencia=body.vigencia,
        tipo_radicado=body.tipo_radicado,
    )


__all__ = ['router']
