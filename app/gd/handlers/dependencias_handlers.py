"""GD-API-0012 — Estructura orgánica versionada + dependencias."""
from __future__ import annotations

from datetime import date as date_type
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.dependencias import (
    DependenciaCerrarVigenciaRequest,
    DependenciaCreate,
    DependenciaJerarquicaItem,
    DependenciaJerarquicaResponse,
    DependenciaListResponse,
    DependenciaPatch,
    DependenciaResponse,
    VersionEstructuraCreate,
    VersionEstructuraResponse,
    VersionEstructuraVigenteResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil, require_gd_permission
from app.gd.services import dependencias as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


# Two routers: /dependencias y /estructura. Se montan ambos desde routes.py.
router_dependencias = APIRouter(prefix='/dependencias', tags=['gd:dependencias'])
router_estructura = APIRouter(prefix='/estructura', tags=['gd:estructura'])


# =============================================================================
# /dependencias
# =============================================================================

@router_dependencias.get(
    '',
    response_model=DependenciaListResponse | DependenciaJerarquicaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_dependencias(
    estado: str | None = Query(default=None),
    version_estructura_id: UUID | None = Query(default=None),
    incluir_jerarquia: bool = Query(default=False),
    q: str | None = Query(default=None),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
):
    rows = await svc.listar_dependencias(
        conn,
        tenant_id=perfil.tenant_id,
        estado=estado,
        version_estructura_id=version_estructura_id,
        q=q,
    )

    if incluir_jerarquia:
        arbol = svc.construir_jerarquia(rows)
        return DependenciaJerarquicaResponse(
            raiz=[DependenciaJerarquicaItem(**n) for n in arbol],
        )

    return DependenciaListResponse(
        items=[DependenciaResponse(**r) for r in rows],
    )


@router_dependencias.post(
    '',
    response_model=DependenciaResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_permission('PERM-USR-001', alcance='institucional'))],
)
async def crear_dependencia(
    body: DependenciaCreate,
    request: Request,
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> DependenciaResponse:
    try:
        row = await svc.crear_dependencia(
            conn,
            tenant_id=perfil_actor.tenant_id,
            codigo_organico=body.codigo_organico,
            nombre=body.nombre,
            dependencia_padre_id=body.dependencia_padre_id,
            version_estructura_id=body.version_estructura_id,
            fecha_inicio_vigencia=body.fecha_inicio_vigencia,
            created_by_user_id=perfil_actor.user_id,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            409,
            detail={
                'error': 'conflict',
                'code': 'codigo_organico_duplicado',
                'message': 'Ya existe una dependencia con ese código en esa versión.',
            },
        )
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(
            404,
            detail={
                'error': 'not_found',
                'message': 'version_estructura_id o dependencia_padre_id no existen.',
            },
        )

    await emit_gd_event(
        conn,
        tipo_evento='gd.dependencia.creada',
        accion='crear',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='dependencia',
        entidad_afectada_id=row['id'],
        entidad_afectada_identificador=body.codigo_organico,
        valor_nuevo={'nombre': body.nombre, 'codigo_organico': body.codigo_organico},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return DependenciaResponse(**row)


@router_dependencias.patch(
    '/{dependencia_id}',
    response_model=DependenciaResponse,
    dependencies=[Depends(require_gd_permission('PERM-USR-001', alcance='institucional'))],
)
async def patch_dependencia(
    body: DependenciaPatch,
    request: Request,
    dependencia_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> DependenciaResponse:
    cambios = body.model_dump(exclude_unset=True)
    row = await svc.patch_dependencia(
        conn,
        tenant_id=perfil_actor.tenant_id,
        dependencia_id=dependencia_id,
        cambios=cambios,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    if cambios:
        await emit_gd_event(
            conn,
            tipo_evento='gd.dependencia.modificada',
            accion='actualizar',
            tenant_id=perfil_actor.tenant_id,
            usuario_id=perfil_actor.user_id,
            entidad_afectada_tipo='dependencia',
            entidad_afectada_id=dependencia_id,
            valor_nuevo=cambios,
            criticidad=AuditCriticidad.ALTA,
            request_id=getattr(request.state, 'request_id', None),
        )
    return DependenciaResponse(**row)


@router_dependencias.post(
    '/{dependencia_id}/cerrar-vigencia',
    response_model=DependenciaResponse,
    dependencies=[Depends(require_gd_permission('PERM-USR-001', alcance='institucional'))],
)
async def cerrar_vigencia_dependencia(
    body: DependenciaCerrarVigenciaRequest,
    request: Request,
    dependencia_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> DependenciaResponse:
    row = await svc.cerrar_vigencia_dependencia(
        conn,
        tenant_id=perfil_actor.tenant_id,
        dependencia_id=dependencia_id,
        fecha_fin=body.fecha_fin,
        motivo=body.motivo,
    )
    if row is None:
        raise HTTPException(
            404,
            detail={'error': 'not_found', 'message': 'Dependencia no existe o ya está cerrada.'},
        )

    await emit_gd_event(
        conn,
        tipo_evento='gd.dependencia.cerrada',
        accion='cerrar_vigencia',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='dependencia',
        entidad_afectada_id=dependencia_id,
        valor_nuevo={
            'fecha_fin': body.fecha_fin.isoformat(),
            'acto_administrativo': body.acto_administrativo,
        },
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return DependenciaResponse(**row)


# =============================================================================
# /estructura
# =============================================================================

@router_estructura.post(
    '/versiones',
    response_model=VersionEstructuraResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_permission('PERM-USR-001', alcance='institucional'))],
)
async def crear_version_estructura(
    body: VersionEstructuraCreate,
    request: Request,
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> VersionEstructuraResponse:
    try:
        row = await svc.crear_version_estructura(
            conn,
            tenant_id=perfil_actor.tenant_id,
            numero_version=body.numero_version,
            descripcion=body.descripcion,
            acto_administrativo=body.acto_administrativo,
            fecha_inicio_vigencia=body.fecha_inicio_vigencia,
            created_by_user_id=perfil_actor.user_id,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            409,
            detail={
                'error': 'conflict',
                'code': 'numero_version_duplicado',
            },
        )

    await emit_gd_event(
        conn,
        tipo_evento='gd.estructura_organica.versionada',
        accion='crear_version',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='version_estructura_organica',
        entidad_afectada_id=row['id'],
        entidad_afectada_identificador=body.numero_version,
        valor_nuevo={'descripcion': body.descripcion, 'acto': body.acto_administrativo},
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return VersionEstructuraResponse(**row)


@router_estructura.get(
    '/vigente',
    response_model=VersionEstructuraVigenteResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def obtener_version_vigente(
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> VersionEstructuraVigenteResponse:
    row = await svc.obtener_version_vigente(conn, tenant_id=perfil.tenant_id)
    if row is None:
        raise HTTPException(
            404,
            detail={
                'error': 'not_found',
                'code': 'sin_version_vigente',
                'message': 'No hay versión de estructura orgánica vigente.',
            },
        )
    return VersionEstructuraVigenteResponse(**row)


@router_estructura.get(
    '/historica',
    response_model=VersionEstructuraVigenteResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def obtener_version_historica(
    fecha: date_type = Query(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> VersionEstructuraVigenteResponse:
    row = await svc.obtener_version_en_fecha(
        conn, tenant_id=perfil.tenant_id, fecha=fecha
    )
    if row is None:
        raise HTTPException(
            404,
            detail={
                'error': 'not_found',
                'message': f'No había estructura vigente al {fecha.isoformat()}.',
            },
        )
    return VersionEstructuraVigenteResponse(**row)


__all__ = ['router_dependencias', 'router_estructura']
