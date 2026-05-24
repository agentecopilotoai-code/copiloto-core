"""GD-API-0007 — Política de contraseñas: GET/PATCH."""
from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, Request

from app.db.pool import get_db
from app.gd.schemas.politica_contrasena import (
    PoliticaContrasenaPatch,
    PoliticaContrasenaResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil, require_gd_permission
from app.gd.services import politica_contrasena as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router = APIRouter(prefix='/seguridad/politica', tags=['gd:seguridad'])


@router.get(
    '',
    response_model=PoliticaContrasenaResponse,
    dependencies=[Depends(require_gd_permission('PERM-USR-001', alcance='institucional'))],
)
async def obtener_politica(
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PoliticaContrasenaResponse:
    p = await svc.obtener_politica_vigente(conn, tenant_id=perfil.tenant_id)
    return PoliticaContrasenaResponse(**p)


@router.patch(
    '',
    response_model=PoliticaContrasenaResponse,
    dependencies=[Depends(require_gd_permission('PERM-USR-001', alcance='institucional'))],
)
async def patch_politica(
    body: PoliticaContrasenaPatch,
    request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PoliticaContrasenaResponse:
    cambios = body.model_dump(exclude_unset=True)
    nueva = await svc.actualizar_politica(
        conn,
        tenant_id=perfil.tenant_id,
        cambios=cambios,
        actualizado_por_user_id=perfil.user_id,
    )

    if cambios:
        await emit_gd_event(
            conn,
            tipo_evento='gd.politica_contrasena.modificada',
            accion='actualizar_politica',
            tenant_id=perfil.tenant_id,
            usuario_id=perfil.user_id,
            entidad_afectada_tipo='politica_contrasena',
            valor_nuevo=cambios,
            criticidad=AuditCriticidad.ALTA,
            request_id=getattr(request.state, 'request_id', None),
        )
    return PoliticaContrasenaResponse(**nueva)


__all__ = ['router']
