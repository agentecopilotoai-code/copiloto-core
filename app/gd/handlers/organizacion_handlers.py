"""GD-API-0011 + 0011.b + 0011.c — Perfil organización + módulos activables."""
from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.db.pool import get_db
from app.gd.schemas.organizacion import (
    ModuloActivacionItem,
    ModulosActivacionPatch,
    ModulosActivacionResponse,
    PerfilOrganizacionCreate,
    PerfilOrganizacionPatch,
    PerfilOrganizacionResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil, require_gd_permission
from app.gd.services import organizacion as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router = APIRouter(prefix='/organizacion', tags=['gd:organizacion'])


@router.get(
    '',
    response_model=PerfilOrganizacionResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def obtener_perfil(
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PerfilOrganizacionResponse:
    row = await svc.obtener_perfil_organizacion(conn, tenant_id=perfil.tenant_id)
    if row is None:
        raise HTTPException(
            404,
            detail={
                'error': 'not_found',
                'code': 'perfil_organizacion_no_existe',
                'message': 'La organización aún no tiene perfil GD configurado.',
            },
        )
    # Adaptar el logo (UUID → objeto). FK real se difiere a EP-018.
    response_data = dict(row)
    logo_id = response_data.pop('logo_archivo_digital_id', None)
    response_data['logo'] = {'archivo_digital_id': logo_id} if logo_id else None
    return PerfilOrganizacionResponse(**response_data)


@router.post(
    '',
    response_model=PerfilOrganizacionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_permission('PERM-USR-001', alcance='institucional'))],
)
async def crear_perfil(
    body: PerfilOrganizacionCreate,
    request: Request,
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PerfilOrganizacionResponse:
    datos = body.model_dump()
    try:
        row = await svc.crear_perfil_organizacion(
            conn,
            tenant_id=perfil_actor.tenant_id,
            datos=datos,
            created_by_user_id=perfil_actor.user_id,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            409,
            detail={
                'error': 'conflict',
                'code': 'perfil_organizacion_ya_existe',
                'message': 'Ya existe un perfil GD para esta organización. Use PATCH.',
            },
        )

    # GD-API-0011.c: aplicar defaults de módulos según tipo_organizacion.
    insertados = await svc.aplicar_defaults_modulos(
        conn, tenant_id=perfil_actor.tenant_id
    )

    await emit_gd_event(
        conn,
        tipo_evento='gd.organizacion.creada',
        accion='crear',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='perfil_organizacion',
        entidad_afectada_id=perfil_actor.tenant_id,
        valor_nuevo={
            'tipo_organizacion': datos['tipo_organizacion'],
            'modulos_default_insertados': insertados,
        },
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )

    response_data = dict(row)
    logo_id = response_data.pop('logo_archivo_digital_id', None)
    response_data['logo'] = {'archivo_digital_id': logo_id} if logo_id else None
    return PerfilOrganizacionResponse(**response_data)


@router.patch(
    '',
    response_model=PerfilOrganizacionResponse,
    dependencies=[Depends(require_gd_permission('PERM-USR-001', alcance='institucional'))],
)
async def patch_perfil(
    body: PerfilOrganizacionPatch,
    request: Request,
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PerfilOrganizacionResponse:
    cambios = body.model_dump(exclude_unset=True)
    row = await svc.actualizar_perfil_organizacion(
        conn, tenant_id=perfil_actor.tenant_id, cambios=cambios
    )
    if row is None:
        raise HTTPException(
            404,
            detail={
                'error': 'not_found',
                'code': 'perfil_organizacion_no_existe',
            },
        )

    if cambios:
        await emit_gd_event(
            conn,
            tipo_evento='gd.organizacion.modificada',
            accion='actualizar',
            tenant_id=perfil_actor.tenant_id,
            usuario_id=perfil_actor.user_id,
            entidad_afectada_tipo='perfil_organizacion',
            entidad_afectada_id=perfil_actor.tenant_id,
            valor_nuevo=cambios,
            criticidad=AuditCriticidad.ALTA,
            request_id=getattr(request.state, 'request_id', None),
        )

    response_data = dict(row)
    logo_id = response_data.pop('logo_archivo_digital_id', None)
    response_data['logo'] = {'archivo_digital_id': logo_id} if logo_id else None
    return PerfilOrganizacionResponse(**response_data)


# =============================================================================
# Módulos activables
# =============================================================================

@router.get(
    '/modulos',
    response_model=ModulosActivacionResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_modulos(
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ModulosActivacionResponse:
    rows = await svc.listar_modulos(conn, tenant_id=perfil.tenant_id)
    return ModulosActivacionResponse(
        modulos=[ModuloActivacionItem(**r) for r in rows],
    )


@router.patch(
    '/modulos',
    response_model=ModulosActivacionResponse,
    dependencies=[Depends(require_gd_permission('PERM-USR-001', alcance='institucional'))],
)
async def patch_modulos(
    body: ModulosActivacionPatch,
    request: Request,
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ModulosActivacionResponse:
    cambios = [m.model_dump() for m in body.modulos]
    afectados = await svc.upsert_modulos(
        conn, tenant_id=perfil_actor.tenant_id, cambios=cambios
    )

    if afectados:
        # Auditar como evento crítico (activar/desactivar módulos cambia
        # comportamiento de la organización completa).
        await emit_gd_event(
            conn,
            tipo_evento='gd.modulo.modificado',
            accion='upsert_modulos',
            tenant_id=perfil_actor.tenant_id,
            usuario_id=perfil_actor.user_id,
            entidad_afectada_tipo='organizacion_modulo_activacion',
            entidad_afectada_id=perfil_actor.tenant_id,
            valor_nuevo={'cambios': cambios, 'afectados': afectados},
            criticidad=AuditCriticidad.ALTA,
            request_id=getattr(request.state, 'request_id', None),
        )

    rows = await svc.listar_modulos(conn, tenant_id=perfil_actor.tenant_id)
    return ModulosActivacionResponse(
        modulos=[ModuloActivacionItem(**r) for r in rows],
    )


__all__ = ['router']
