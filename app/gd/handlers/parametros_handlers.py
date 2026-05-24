"""GD-API-0015 — Endpoints de parámetros institucionales versionados."""
from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Request

from app.db.pool import get_db
from app.gd.schemas.parametros import (
    ParametroDetalleResponse,
    ParametroResponse,
    ParametrosListResponse,
    ParametrosPatch,
)
from app.gd.security import GdPerfilContext, require_gd_perfil, require_gd_permission
from app.gd.services import parametros as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router = APIRouter(prefix='/parametros', tags=['gd:parametros'])


@router.get(
    '',
    response_model=ParametrosListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_parametros(
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ParametrosListResponse:
    rows = await svc.listar_parametros_vigentes(conn, tenant_id=perfil.tenant_id)
    return ParametrosListResponse(items=[ParametroResponse(**r) for r in rows])


@router.get(
    '/{clave}',
    response_model=ParametroDetalleResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def obtener_parametro(
    clave: str = Path(..., min_length=2, max_length=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ParametroDetalleResponse:
    result = await svc.obtener_parametro(conn, tenant_id=perfil.tenant_id, clave=clave)
    if result is None:
        raise HTTPException(
            404,
            detail={'error': 'not_found', 'message': f'Parámetro {clave!r} no encontrado.'},
        )
    vigente = ParametroResponse(**result['vigente']) if result['vigente'] else None
    historial = [ParametroResponse(**r) for r in result['historial']]
    return ParametroDetalleResponse(
        clave=clave, vigente=vigente, historial=historial,
    )


@router.patch(
    '',
    response_model=ParametrosListResponse,
    dependencies=[Depends(require_gd_permission('PERM-USR-001', alcance='institucional'))],
)
async def patch_parametros(
    body: ParametrosPatch, request: Request,
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ParametrosListResponse:
    parametros_data = [p.model_dump() for p in body.parametros]
    resultados = await svc.upsert_parametros(
        conn, tenant_id=perfil_actor.tenant_id, parametros=parametros_data,
    )

    # Auditar como ALTA — los parámetros afectan comportamiento global.
    await emit_gd_event(
        conn,
        tipo_evento='gd.parametro.modificado',
        accion='upsert_parametros',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='parametro',
        valor_nuevo={
            'claves': [p['clave'] for p in parametros_data],
            'motivos': [p.get('motivo') for p in parametros_data],
        },
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )

    return ParametrosListResponse(items=[ParametroResponse(**r) for r in resultados])


__all__ = ['router']
