"""Handlers HTTP de EP-010 plantillas documentales (bloque 11).

Endpoints (12):
- POST   /api/v1/gd/plantillas                                (crear)        GD-API-0064
- GET    /api/v1/gd/plantillas                                (listar)
- GET    /api/v1/gd/plantillas/{id}                           (detalle)
- PATCH  /api/v1/gd/plantillas/{id}                           (editar header)
- POST   /api/v1/gd/plantillas/{id}/versiones                 (nueva versión) GD-API-0064
- POST   /api/v1/gd/plantillas/{id}/activar                                   GD-API-0064
- POST   /api/v1/gd/plantillas/{id}/inactivar                                 GD-API-0064
- POST   /api/v1/gd/plantillas/{id}/generar-documento                         GD-API-0065
- POST   /api/v1/gd/plantillas/{id}/asociar-dependencia/{dep_id}              GD-API-0066
- POST   /api/v1/gd/plantillas/{id}/asociar-tipo-tramite/{tipo}               GD-API-0066
- GET    /api/v1/gd/plantillas/{id}/asociaciones                              GD-API-0066
- POST   /api/v1/gd/plantillas/_seed-institucionales                          GD-API-0067
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.plantillas import (
    ActivarPlantillaRequest,
    AsociacionResponse,
    CrearPlantillaRequest,
    GenerarDocumentoRequest,
    GenerarDocumentoResponse,
    NuevaVersionPlantillaRequest,
    PatchPlantillaRequest,
    PlantillaListItem,
    PlantillaListResponse,
    PlantillaResponse,
    SeedInstitucionalResponse,
    VersionPlantillaResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil
from app.gd.services import plantillas as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


# Router admin para endpoint con underscore prefix; se monta primero.
router_admin = APIRouter(prefix='/plantillas', tags=['gd:plantillas:admin'])
router = APIRouter(prefix='/plantillas', tags=['gd:plantillas'])


def _err_estado(e: ValueError) -> HTTPException:
    return HTTPException(409, detail={'error': 'conflict', 'code': str(e)})


def _to_plantilla_response(row: dict[str, Any]) -> PlantillaResponse:
    versiones = [VersionPlantillaResponse(**v) for v in row.get('versiones', [])]
    return PlantillaResponse(
        id=row['id'], codigo=row['codigo'], nombre=row['nombre'],
        descripcion=row.get('descripcion'),
        tipo_plantilla=row['tipo_plantilla'],
        estado=row['estado'],
        version_vigente_id=row.get('version_vigente_id'),
        numero_version_vigente=row['numero_version_vigente'],
        dependencia_propietaria_id=row.get('dependencia_propietaria_id'),
        es_institucional=row['es_institucional'],
        created_by_user_id=row['created_by_user_id'],
        created_at=row['created_at'], updated_at=row['updated_at'],
        versiones=versiones,
    )


# =============================================================================
# Seed institucional (debe declararse PRIMERO en router_admin para que
# /_seed-institucionales no choque con /{plantilla_id})
# =============================================================================

@router_admin.post(
    '/_seed-institucionales',
    response_model=SeedInstitucionalResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def seed_institucionales(
    request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> SeedInstitucionalResponse:
    r = await svc.seed_plantillas_institucionales(
        conn, tenant_id=perfil.tenant_id, usuario_actor_id=perfil.user_id,
    )
    await emit_gd_event(
        conn, tipo_evento='PlantillasInstitucionalesSeed',
        accion='seed_institucionales',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='plantilla_documental',
        entidad_afectada_id=perfil.tenant_id,
        valor_nuevo={'creadas': len(r['plantillas_creadas']),
                      'existentes': len(r['plantillas_existentes'])},
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return SeedInstitucionalResponse(**r)


# =============================================================================
# CRUD plantillas
# =============================================================================

@router.post(
    '',
    response_model=PlantillaResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def crear_plantilla(
    body: CrearPlantillaRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PlantillaResponse:
    try:
        row = await svc.crear_plantilla(
            conn, tenant_id=perfil.tenant_id,
            codigo=body.codigo, nombre=body.nombre,
            descripcion=body.descripcion, tipo_plantilla=body.tipo_plantilla,
            dependencia_propietaria_id=body.dependencia_propietaria_id,
            es_institucional=body.es_institucional,
            contenido_template=body.contenido_template,
            json_schema_campos=body.json_schema_campos,
            mime_type=body.mime_type,
            created_by_user_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e

    await emit_gd_event(
        conn, tipo_evento='PlantillaCreada', accion='crear_plantilla',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='plantilla_documental',
        entidad_afectada_id=row['id'],
        valor_nuevo={'codigo': body.codigo, 'tipo': body.tipo_plantilla},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _to_plantilla_response(row)


@router.get(
    '',
    response_model=PlantillaListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_plantillas(
    estado: str | None = Query(default=None),
    tipo: str | None = Query(default=None),
    dependencia_id: UUID | None = Query(default=None),
    es_institucional: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PlantillaListResponse:
    estados = estado.split(',') if estado else None
    rows = await svc.listar_plantillas(
        conn, tenant_id=perfil.tenant_id,
        estado=estados, tipo_plantilla=tipo,
        dependencia_id=dependencia_id, es_institucional=es_institucional,
        limit=limit,
    )
    total = await svc.contar_plantillas(conn, tenant_id=perfil.tenant_id)
    return PlantillaListResponse(
        items=[PlantillaListItem(**r) for r in rows], total=total,
    )


@router.get(
    '/{plantilla_id}',
    response_model=PlantillaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def detalle_plantilla(
    plantilla_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PlantillaResponse:
    row = await svc.obtener_plantilla(
        conn, tenant_id=perfil.tenant_id, plantilla_id=plantilla_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return _to_plantilla_response(row)


@router.patch(
    '/{plantilla_id}',
    response_model=PlantillaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def patch_plantilla(
    body: PatchPlantillaRequest, request: Request,
    plantilla_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PlantillaResponse:
    row = await svc.patch_plantilla(
        conn, tenant_id=perfil.tenant_id, plantilla_id=plantilla_id,
        nombre=body.nombre, descripcion=body.descripcion,
        dependencia_propietaria_id=body.dependencia_propietaria_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='PlantillaActualizada', accion='patch',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='plantilla_documental',
        entidad_afectada_id=plantilla_id,
        valor_nuevo=body.model_dump(exclude_none=True),
        criticidad=AuditCriticidad.BAJA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _to_plantilla_response(row)


# =============================================================================
# Versiones
# =============================================================================

@router.post(
    '/{plantilla_id}/versiones',
    response_model=VersionPlantillaResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def nueva_version(
    body: NuevaVersionPlantillaRequest, request: Request,
    plantilla_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> VersionPlantillaResponse:
    # Verificar plantilla existe.
    pl = await conn.fetchval(
        'select 1 from gd.plantilla_documental where id = $1 and tenant_id = $2',
        plantilla_id, perfil.tenant_id,
    )
    if not pl:
        raise HTTPException(404, detail={'error': 'not_found'})

    row = await svc.crear_version_plantilla(
        conn, tenant_id=perfil.tenant_id, plantilla_id=plantilla_id,
        contenido_template=body.contenido_template,
        json_schema_campos=body.json_schema_campos,
        archivo_digital_id=body.archivo_digital_id,
        mime_type=body.mime_type, notas=body.notas,
        created_by_user_id=perfil.user_id,
    )

    await emit_gd_event(
        conn, tipo_evento='PlantillaVersionCreada', accion='nueva_version',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='version_plantilla',
        entidad_afectada_id=row['id'],
        valor_nuevo={'plantilla_id': str(plantilla_id),
                      'numero_version': row['numero_version']},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return VersionPlantillaResponse(**row)


# =============================================================================
# Activar / inactivar
# =============================================================================

@router.post(
    '/{plantilla_id}/activar',
    response_model=PlantillaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def activar(
    body: ActivarPlantillaRequest, request: Request,
    plantilla_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PlantillaResponse:
    try:
        row = await svc.activar_plantilla(
            conn, tenant_id=perfil.tenant_id, plantilla_id=plantilla_id,
            version_id=body.version_id, usuario_actor_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='PlantillaActivada', accion='activar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='plantilla_documental',
        entidad_afectada_id=plantilla_id,
        valor_nuevo={'numero_version': row['numero_version_vigente']},
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _to_plantilla_response(row)


@router.post(
    '/{plantilla_id}/inactivar',
    response_model=PlantillaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def inactivar(
    request: Request,
    plantilla_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PlantillaResponse:
    try:
        row = await svc.inactivar_plantilla(
            conn, tenant_id=perfil.tenant_id, plantilla_id=plantilla_id,
            usuario_actor_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='PlantillaInactivada', accion='inactivar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='plantilla_documental',
        entidad_afectada_id=plantilla_id,
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _to_plantilla_response(row)


# =============================================================================
# Generar documento (GD-API-0065)
# =============================================================================

@router.post(
    '/{plantilla_id}/generar-documento',
    response_model=GenerarDocumentoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def generar_documento(
    body: GenerarDocumentoRequest, request: Request,
    plantilla_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> GenerarDocumentoResponse:
    try:
        r = await svc.generar_documento_desde_plantilla(
            conn, tenant_id=perfil.tenant_id, plantilla_id=plantilla_id,
            titulo=body.titulo,
            clasificacion_informacion=body.clasificacion_informacion,
            radicado_id=body.radicado_id, pqrsd_id=body.pqrsd_id,
            correspondencia_id=body.correspondencia_id,
            datos_adicionales=body.datos_adicionales,
            usuario_actor_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if r is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='DocumentoGeneradoDesdePlantilla',
        accion='generar_documento',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='documento', entidad_afectada_id=r['documento_id'],
        valor_nuevo={'plantilla_id': str(plantilla_id),
                      'radicado_id': str(body.radicado_id) if body.radicado_id else None,
                      'pqrsd_id': str(body.pqrsd_id) if body.pqrsd_id else None},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return GenerarDocumentoResponse(**r)


# =============================================================================
# Asociaciones
# =============================================================================

@router.post(
    '/{plantilla_id}/asociar-dependencia/{dependencia_id}',
    response_model=AsociacionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def asociar_dependencia(
    request: Request,
    plantilla_id: UUID = Path(...),
    dependencia_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> AsociacionResponse:
    try:
        row = await svc.asociar_dependencia(
            conn, tenant_id=perfil.tenant_id, plantilla_id=plantilla_id,
            dependencia_id=dependencia_id, creado_por_user_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='PlantillaAsociadaDependencia', accion='asociar_dep',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='plantilla_asociacion',
        entidad_afectada_id=row['id'],
        valor_nuevo={'plantilla_id': str(plantilla_id),
                      'dependencia_id': str(dependencia_id)},
        criticidad=AuditCriticidad.BAJA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return AsociacionResponse(**row)


@router.post(
    '/{plantilla_id}/asociar-tipo-tramite/{tipo_tramite}',
    response_model=AsociacionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def asociar_tipo_tramite(
    request: Request,
    plantilla_id: UUID = Path(...),
    tipo_tramite: str = Path(..., min_length=2, max_length=80),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> AsociacionResponse:
    try:
        row = await svc.asociar_tipo_tramite(
            conn, tenant_id=perfil.tenant_id, plantilla_id=plantilla_id,
            tipo_tramite=tipo_tramite, creado_por_user_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='PlantillaAsociadaTipoTramite', accion='asociar_tt',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='plantilla_asociacion',
        entidad_afectada_id=row['id'],
        valor_nuevo={'plantilla_id': str(plantilla_id),
                      'tipo_tramite': tipo_tramite},
        criticidad=AuditCriticidad.BAJA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return AsociacionResponse(**row)


@router.get(
    '/{plantilla_id}/asociaciones',
    response_model=list[AsociacionResponse],
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_asociaciones_pl(
    plantilla_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> list[AsociacionResponse]:
    rows = await svc.listar_asociaciones(
        conn, tenant_id=perfil.tenant_id, plantilla_id=plantilla_id,
    )
    return [AsociacionResponse(**r) for r in rows]


__all__ = ['router', 'router_admin']
