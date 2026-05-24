"""Handlers HTTP para EP-019/020 utilidades (bloque 20).

Endpoints (16):
Auditoría (GD-API-0119/0120):
- GET /api/v1/core/auditoria
- GET /api/v1/core/auditoria/catalogo-eventos
- GET /api/v1/core/auditoria/{id}

Constancia pública (GD-API-0122) — sin auth:
- GET /gd/verificar/{codigo}     (NO bajo /api/v1; publica)
- POST /api/v1/gd/radicados/{id}/constancias  (genera + devuelve URL QR)

Tipos doc identidad (GD-API-0123):
- GET /api/v1/gd/catalogos/tipos-documento  (global)
- GET /api/v1/gd/organizacion/tipos-documento  (selección org)
- PATCH /api/v1/gd/organizacion/tipos-documento

Cambios dependencia (GD-API-0124):
- GET  /api/v1/gd/estructura/dependencias/{id}/historial
- POST /api/v1/gd/estructura/fusionar

Contingencia (GD-API-0125):
- POST /api/v1/gd/ventanilla/radicados/contingencia

Hoja control + índice (GD-API-0126):
- GET  /api/v1/gd/expedientes/{id}/hoja-control
- POST /api/v1/gd/expedientes/{id}/indice-electronico
- GET  /api/v1/gd/expedientes/{id}/indice-electronico  (último vigente)
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.utilidades import (
    ConstanciaPublicaResponse,
    EventoAuditoriaListResponse,
    EventoAuditoriaResponse,
    EventoCatalogoItem,
    EventoCatalogoListResponse,
    FusionarRequest,
    FusionarResponse,
    HistorialDepResponse,
    HojaControlEntradaResponse,
    HojaControlListResponse,
    IndiceElectronicoResponse,
    OrgTipoDocResponse,
    PatchOrgTipoDocRequest,
    RadicarContingenciaRequest,
    RadicarContingenciaResponse,
    RelacionDepHistResponse,
    TipoDocIdResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil
from app.gd.services import utilidades as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


# Routers split por dominio.
router_audit = APIRouter(prefix='/auditoria', tags=['core:auditoria'])
router_constancia_pub = APIRouter(prefix='/gd', tags=['publica:constancia'])
router_constancia_priv = APIRouter(prefix='/radicados',
                                    tags=['gd:constancias'])
router_tipos = APIRouter(prefix='/catalogos', tags=['gd:tipos_documento'])
router_org_tipos = APIRouter(prefix='/organizacion',
                              tags=['gd:org_tipos_documento'])
router_estructura = APIRouter(prefix='/estructura', tags=['gd:cambios_dep'])
router_contingencia = APIRouter(prefix='/ventanilla/radicados',
                                 tags=['gd:contingencia'])
router_hoja = APIRouter(prefix='/expedientes', tags=['gd:hoja_control'])


def _err_estado(e: ValueError) -> HTTPException:
    return HTTPException(409, detail={'error': 'conflict', 'code': str(e)})


def _err_not_found(e: LookupError) -> HTTPException:
    return HTTPException(404, detail={'error': 'not_found', 'code': str(e)})


# =============================================================================
# Auditoría (GD-API-0119/0120)
# =============================================================================

@router_audit.get(
    '',
    response_model=EventoAuditoriaListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_auditoria(
    dominio: str | None = Query(default=None),
    tipo_evento: str | None = Query(default=None),
    actor_id: UUID | None = Query(default=None),
    entidad_tipo: str | None = Query(default=None),
    entidad_id: UUID | None = Query(default=None),
    criticidad: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> EventoAuditoriaListResponse:
    rows = await svc.listar_eventos_auditoria(
        conn, tenant_id=perfil.tenant_id,
        dominio=dominio, tipo_evento=tipo_evento,
        actor_id=actor_id, entidad_tipo=entidad_tipo,
        entidad_id=entidad_id, criticidad=criticidad, limit=limit,
    )
    items = [EventoAuditoriaResponse(**r) for r in rows]
    return EventoAuditoriaListResponse(items=items, total=len(items))


@router_audit.get(
    '/catalogo-eventos',
    response_model=EventoCatalogoListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_catalogo(
    dominio: str | None = Query(default=None),
    activo: bool | None = Query(default=None),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> EventoCatalogoListResponse:
    rows = await svc.listar_catalogo_eventos(
        conn, dominio=dominio, activo=activo,
    )
    items = [EventoCatalogoItem(**r) for r in rows]
    return EventoCatalogoListResponse(items=items, total=len(items))


@router_audit.get(
    '/{evento_id}',
    response_model=EventoAuditoriaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def detalle_auditoria(
    request: Request,
    evento_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> EventoAuditoriaResponse:
    row = await svc.obtener_evento_auditoria(conn, evento_id=evento_id)
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    # RNF-059: emit meta-evento si consultó info sensible.
    if row.get('criticidad') == 'alta':
        await emit_gd_event(
            conn, tipo_evento='auditoria.consultada', accion='consultar',
            tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
            entidad_afectada_tipo='evento_auditoria',
            entidad_afectada_id=evento_id,
            criticidad=AuditCriticidad.MEDIA,
            request_id=getattr(request.state, 'request_id', None),
        )
    return EventoAuditoriaResponse(**row)


# =============================================================================
# Constancia pública (GD-API-0122) — SIN auth
# =============================================================================

@router_constancia_pub.get(
    '/verificar/{codigo}',
    response_model=ConstanciaPublicaResponse,
)
async def verificar_constancia(
    codigo: str = Path(..., min_length=8, max_length=80),
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ConstanciaPublicaResponse:
    """SIN auth. Verificación pública de radicado por código QR."""
    data = await svc.verificar_constancia_publica(
        conn, codigo_verificacion=codigo,
    )
    if data is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return ConstanciaPublicaResponse(**data)


@router_constancia_priv.post(
    '/{radicado_id}/constancias',
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def crear_constancia_radicado(
    request: Request,
    radicado_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    """Genera código de verificación + URL QR para un radicado."""
    row = await svc.crear_constancia(
        conn, tenant_id=perfil.tenant_id, radicado_id=radicado_id,
        generada_por_user_id=perfil.user_id,
    )
    await emit_gd_event(
        conn, tipo_evento='ConstanciaGenerada', accion='generar_constancia',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='constancia_radicacion',
        entidad_afectada_id=row['id'],
        valor_nuevo={'radicado_id': str(radicado_id),
                      'codigo': row['codigo_verificacion']},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return {
        'id': str(row['id']),
        'codigo_verificacion': row['codigo_verificacion'],
        'qr_url_publica': row['qr_url_publica'],
        'fecha_generacion': row['fecha_generacion'].isoformat(),
    }


# =============================================================================
# Tipos documento identidad (GD-API-0123)
# =============================================================================

@router_tipos.get(
    '/tipos-documento',
    response_model=list[TipoDocIdResponse],
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_tipos_doc(
    pais_iso: str | None = Query(default=None, min_length=2, max_length=2),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> list[TipoDocIdResponse]:
    rows = await svc.listar_catalogo_tipos_doc(
        conn, pais_iso=pais_iso.upper() if pais_iso else None,
    )
    return [TipoDocIdResponse(**r) for r in rows]


@router_org_tipos.get(
    '/tipos-documento',
    response_model=list[OrgTipoDocResponse],
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_org_tipos(
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> list[OrgTipoDocResponse]:
    rows = await svc.listar_org_tipos_doc(conn, tenant_id=perfil.tenant_id)
    return [OrgTipoDocResponse(**r) for r in rows]


@router_org_tipos.patch(
    '/tipos-documento',
    response_model=list[OrgTipoDocResponse],
    dependencies=[Depends(require_gd_perfil)],
)
async def patch_org_tipos(
    body: PatchOrgTipoDocRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> list[OrgTipoDocResponse]:
    try:
        rows = await svc.patch_org_tipos_doc(
            conn, tenant_id=perfil.tenant_id,
            codigos_activos=body.codigos_activos,
            codigo_default=body.codigo_default,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_estado(e) from e

    await emit_gd_event(
        conn, tipo_evento='OrgTiposDocActualizados', accion='patch',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='organizacion_tipo_documento_activo',
        entidad_afectada_id=perfil.tenant_id,
        valor_nuevo={'activos': body.codigos_activos,
                      'default': body.codigo_default},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return [OrgTipoDocResponse(**r) for r in rows]


# =============================================================================
# Cambios dependencia (GD-API-0124)
# =============================================================================

@router_estructura.get(
    '/dependencias/{dependencia_id}/historial',
    response_model=HistorialDepResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def historial_dep(
    dependencia_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> HistorialDepResponse:
    relaciones = await svc.historial_dependencia(
        conn, tenant_id=perfil.tenant_id, dependencia_id=dependencia_id,
    )
    return HistorialDepResponse(
        dependencia_id=dependencia_id,
        relaciones=[RelacionDepHistResponse(**r) for r in relaciones],
    )


@router_estructura.post(
    '/fusionar',
    response_model=FusionarResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def fusionar(
    body: FusionarRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> FusionarResponse:
    try:
        r = await svc.fusionar_dependencias(
            conn, tenant_id=perfil.tenant_id,
            dependencias_origen=body.dependencias_origen,
            dependencia_destino_id=body.dependencia_destino_id,
            fecha_vigencia=body.fecha_vigencia,
            motivo=body.motivo,
            acto_administrativo=body.acto_administrativo,
            registrado_por_user_id=perfil.user_id,
        )
    except LookupError as e:
        raise _err_not_found(e) from e

    await emit_gd_event(
        conn, tipo_evento='DependenciasFusionadas', accion='fusionar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='dependencia',
        entidad_afectada_id=body.dependencia_destino_id,
        valor_nuevo={'origenes': [str(d) for d in body.dependencias_origen],
                      'destino': str(body.dependencia_destino_id)},
        justificacion=body.motivo,
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return FusionarResponse(**r)


# =============================================================================
# Contingencia (GD-API-0125)
# =============================================================================

@router_contingencia.post(
    '/contingencia',
    response_model=RadicarContingenciaResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def radicar_cont(
    body: RadicarContingenciaRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RadicarContingenciaResponse:
    row = await svc.radicar_contingencia(
        conn, tenant_id=perfil.tenant_id,
        numero_radicado_manual=body.numero_radicado_manual,
        fecha_radicacion_real=body.fecha_radicacion_real,
        justificacion=body.justificacion,
        evidencia_contingencia_archivo_id=body.evidencia_contingencia_archivo_id,
        canal_id=body.canal_id,
        tipo_radicado=body.tipo_radicado,
        asunto=body.asunto, descripcion=body.descripcion,
        tercero_id=body.tercero_id,
        dependencia_destino_id=body.dependencia_destino_id,
        usuario_actor_id=perfil.user_id,
    )

    await emit_gd_event(
        conn, tipo_evento='gd.radicado.contingencia',
        accion='radicar_contingencia',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='radicado', entidad_afectada_id=row['id'],
        valor_nuevo={'numero': body.numero_radicado_manual,
                      'fecha_real': body.fecha_radicacion_real.isoformat()},
        justificacion=body.justificacion,
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return RadicarContingenciaResponse(
        radicado_id=row['id'],
        numero_radicado=row['numero_radicado'],
        fecha_radicacion_real=row['fecha_radicacion_real'],
        fecha_ingreso_sistema=row['created_at'],
        es_contingencia=True,
    )


# =============================================================================
# Hoja control + índice electrónico (GD-API-0126)
# =============================================================================

@router_hoja.get(
    '/{expediente_id}/hoja-control',
    response_model=HojaControlListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def get_hoja_control(
    expediente_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> HojaControlListResponse:
    rows = await svc.listar_hoja_control(
        conn, tenant_id=perfil.tenant_id, expediente_id=expediente_id,
    )
    return HojaControlListResponse(
        expediente_id=expediente_id,
        items=[HojaControlEntradaResponse(**r) for r in rows],
        total=len(rows),
    )


@router_hoja.post(
    '/{expediente_id}/indice-electronico',
    response_model=IndiceElectronicoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def generar_indice(
    request: Request,
    expediente_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> IndiceElectronicoResponse:
    r = await svc.generar_indice_electronico(
        conn, tenant_id=perfil.tenant_id, expediente_id=expediente_id,
        generado_por_user_id=perfil.user_id,
    )
    if r is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='IndiceElectronicoGenerado',
        accion='generar_indice',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='expediente_indice_electronico',
        entidad_afectada_id=r['id'],
        valor_nuevo={'expediente_id': str(expediente_id),
                      'version': r['version_indice']},
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    # Schema field rename: contenido_jsonb → contenido_jsonb (same name OK)
    return IndiceElectronicoResponse(**r)


__all__ = [
    'router_audit', 'router_constancia_pub', 'router_constancia_priv',
    'router_tipos', 'router_org_tipos', 'router_estructura',
    'router_contingencia', 'router_hoja',
]
