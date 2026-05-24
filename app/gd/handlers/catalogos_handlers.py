"""Handlers HTTP para catálogos institucionales del bloque 4.

Cubre: cargos (0013), canales/calendarios/tipos PQRSD/tipos correspondencia
(0014), reglas comunicación (0016). Endpoints CRUD + validar comunicación
+ helper calcular fecha límite.
"""
from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.catalogos import (
    CalcularFechaLimiteRequest, CalcularFechaLimiteResponse,
    CalendarioCreate, CalendarioResponse, CalendariosListResponse,
    CanalCreate, CanalListResponse, CanalResponse,
    CargoCreate, CargoListResponse, CargoPatch, CargoResponse,
    ReglaComunicacionCreate, ReglaComunicacionResponse,
    ReglasComunicacionListResponse, ValidacionComunicacionResponse,
    TipoCorrespondenciaCreate, TipoCorrespondenciaResponse,
    TiposCorrespondenciaListResponse,
    TipoPqrsdCreate, TipoPqrsdResponse, TiposPqrsdListResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil, require_gd_permission
from app.gd.services import catalogos as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


# 5 routers: cargos, canales, calendarios, tipos_pqrsd, tipos_correspondencia,
# reglas. Cada uno con su prefix.
router_cargos = APIRouter(prefix='/cargos', tags=['gd:cargos'])
router_canales = APIRouter(prefix='/canales', tags=['gd:canales'])
router_calendarios = APIRouter(prefix='/calendarios', tags=['gd:calendarios'])
router_tipos_pqrsd = APIRouter(prefix='/tipos-pqrsd', tags=['gd:tipos-pqrsd'])
router_tipos_corresp = APIRouter(prefix='/tipos-correspondencia', tags=['gd:tipos-correspondencia'])
router_reglas = APIRouter(prefix='/reglas/comunicacion', tags=['gd:reglas'])


# =============================================================================
# /cargos (GD-API-0013)
# =============================================================================

@router_cargos.post(
    '',
    response_model=CargoResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_permission('PERM-USR-001', alcance='institucional'))],
)
async def crear_cargo(
    body: CargoCreate, request: Request,
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CargoResponse:
    try:
        row = await svc.crear_cargo(
            conn, tenant_id=perfil_actor.tenant_id,
            nombre=body.nombre, dependencia_id=body.dependencia_id,
            fecha_inicio_vigencia=body.fecha_inicio_vigencia,
        )
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(
            404,
            detail={'error': 'not_found', 'message': 'dependencia_id no existe.'},
        )
    await emit_gd_event(
        conn,
        tipo_evento='gd.cargo.creado',
        accion='crear',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='cargo',
        entidad_afectada_id=row['id'],
        valor_nuevo={'nombre': body.nombre},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return CargoResponse(**row)


@router_cargos.get(
    '',
    response_model=CargoListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_cargos(
    dependencia_id: UUID | None = Query(default=None),
    estado: str | None = Query(default=None),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CargoListResponse:
    rows = await svc.listar_cargos(
        conn, tenant_id=perfil.tenant_id,
        dependencia_id=dependencia_id, estado=estado,
    )
    return CargoListResponse(items=[CargoResponse(**r) for r in rows])


@router_cargos.patch(
    '/{cargo_id}',
    response_model=CargoResponse,
    dependencies=[Depends(require_gd_permission('PERM-USR-001', alcance='institucional'))],
)
async def patch_cargo(
    body: CargoPatch, request: Request,
    cargo_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CargoResponse:
    cambios = body.model_dump(exclude_unset=True)
    row = await svc.patch_cargo(
        conn, tenant_id=perfil_actor.tenant_id,
        cargo_id=cargo_id, cambios=cambios,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    if cambios:
        await emit_gd_event(
            conn,
            tipo_evento='gd.cargo.modificado',
            accion='actualizar',
            tenant_id=perfil_actor.tenant_id,
            usuario_id=perfil_actor.user_id,
            entidad_afectada_tipo='cargo',
            entidad_afectada_id=cargo_id,
            valor_nuevo=cambios,
            criticidad=AuditCriticidad.MEDIA,
            request_id=getattr(request.state, 'request_id', None),
        )
    return CargoResponse(**row)


# =============================================================================
# /canales (GD-API-0014)
# =============================================================================

@router_canales.post(
    '',
    response_model=CanalResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_permission('PERM-USR-001', alcance='institucional'))],
)
async def crear_canal(
    body: CanalCreate, request: Request,
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CanalResponse:
    try:
        row = await svc.crear_canal(
            conn, tenant_id=perfil_actor.tenant_id, datos=body.model_dump(),
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            409,
            detail={
                'error': 'conflict', 'code': 'codigo_duplicado',
                'message': f'Ya existe canal con código {body.codigo!r}.',
            },
        )
    await emit_gd_event(
        conn,
        tipo_evento='gd.canal.creado',
        accion='crear',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='canal',
        entidad_afectada_id=row['id'],
        entidad_afectada_identificador=body.codigo,
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return CanalResponse(**row)


@router_canales.get(
    '',
    response_model=CanalListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_canales(
    estado: str | None = Query(default=None),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CanalListResponse:
    rows = await svc.listar_canales(conn, tenant_id=perfil.tenant_id, estado=estado)
    return CanalListResponse(items=[CanalResponse(**r) for r in rows])


# =============================================================================
# /calendarios (GD-API-0014)
# =============================================================================

@router_calendarios.post(
    '',
    response_model=CalendarioResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_permission('PERM-USR-001', alcance='institucional'))],
)
async def crear_calendario(
    body: CalendarioCreate, request: Request,
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CalendarioResponse:
    try:
        row = await svc.crear_calendario(
            conn, tenant_id=perfil_actor.tenant_id, datos=body.model_dump(),
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            409,
            detail={
                'error': 'conflict',
                'message': 'Ya existe calendario con ese nombre y vigencia.',
            },
        )
    await emit_gd_event(
        conn,
        tipo_evento='gd.calendario.creado',
        accion='crear',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='calendario',
        entidad_afectada_id=row['id'],
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return CalendarioResponse(**row)


@router_calendarios.get(
    '',
    response_model=CalendariosListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_calendarios(
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CalendariosListResponse:
    rows = await svc.listar_calendarios(conn, tenant_id=perfil.tenant_id)
    default_id = await svc.calendario_default_id(conn, tenant_id=perfil.tenant_id)
    return CalendariosListResponse(
        calendario_default_id=default_id,
        items=[CalendarioResponse(**r) for r in rows],
    )


@router_calendarios.post(
    '/calcular-fecha-limite',
    response_model=CalcularFechaLimiteResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def calcular_fecha_limite_endpoint(
    body: CalcularFechaLimiteRequest,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CalcularFechaLimiteResponse:
    fecha_limite = await svc.calcular_fecha_limite(
        conn, tenant_id=perfil.tenant_id,
        fecha_base=body.fecha_base,
        termino_dias=body.termino_dias,
        tipo_dias=body.tipo_dias,
    )
    return CalcularFechaLimiteResponse(
        fecha_base=body.fecha_base,
        termino_dias=body.termino_dias,
        tipo_dias=body.tipo_dias,
        fecha_limite=fecha_limite,
    )


# =============================================================================
# /tipos-pqrsd (GD-API-0014)
# =============================================================================

@router_tipos_pqrsd.post(
    '',
    response_model=TipoPqrsdResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_permission('PERM-USR-001', alcance='institucional'))],
)
async def crear_tipo_pqrsd(
    body: TipoPqrsdCreate, request: Request,
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TipoPqrsdResponse:
    try:
        row = await svc.crear_tipo_pqrsd(
            conn, tenant_id=perfil_actor.tenant_id, datos=body.model_dump(),
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, detail={'error': 'conflict', 'code': 'codigo_duplicado'})
    await emit_gd_event(
        conn,
        tipo_evento='gd.tipo_pqrsd.creado',
        accion='crear',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='tipo_pqrsd',
        entidad_afectada_id=row['id'],
        entidad_afectada_identificador=body.codigo,
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return TipoPqrsdResponse(**row)


@router_tipos_pqrsd.get(
    '',
    response_model=TiposPqrsdListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_tipos_pqrsd(
    estado: str | None = Query(default=None),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TiposPqrsdListResponse:
    rows = await svc.listar_tipos_pqrsd(conn, tenant_id=perfil.tenant_id, estado=estado)
    return TiposPqrsdListResponse(items=[TipoPqrsdResponse(**r) for r in rows])


# =============================================================================
# /tipos-correspondencia (GD-API-0014)
# =============================================================================

@router_tipos_corresp.post(
    '',
    response_model=TipoCorrespondenciaResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_permission('PERM-USR-001', alcance='institucional'))],
)
async def crear_tipo_correspondencia(
    body: TipoCorrespondenciaCreate, request: Request,
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TipoCorrespondenciaResponse:
    try:
        row = await svc.crear_tipo_correspondencia(
            conn, tenant_id=perfil_actor.tenant_id, datos=body.model_dump(),
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(409, detail={'error': 'conflict', 'code': 'codigo_duplicado'})
    await emit_gd_event(
        conn,
        tipo_evento='gd.tipo_correspondencia.creado',
        accion='crear',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='tipo_correspondencia',
        entidad_afectada_id=row['id'],
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return TipoCorrespondenciaResponse(**row)


@router_tipos_corresp.get(
    '',
    response_model=TiposCorrespondenciaListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_tipos_correspondencia(
    ambito: str | None = Query(default=None),
    estado: str | None = Query(default=None),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TiposCorrespondenciaListResponse:
    rows = await svc.listar_tipos_correspondencia(
        conn, tenant_id=perfil.tenant_id, ambito=ambito, estado=estado,
    )
    return TiposCorrespondenciaListResponse(
        items=[TipoCorrespondenciaResponse(**r) for r in rows],
    )


# =============================================================================
# /reglas/comunicacion (GD-API-0016)
# =============================================================================

@router_reglas.post(
    '',
    response_model=ReglaComunicacionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_permission('PERM-USR-001', alcance='institucional'))],
)
async def crear_regla(
    body: ReglaComunicacionCreate, request: Request,
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ReglaComunicacionResponse:
    if body.dependencia_origen_id == body.dependencia_destino_id:
        raise HTTPException(
            422,
            detail={
                'error': 'validation_error',
                'message': 'origen y destino no pueden ser la misma dependencia.',
            },
        )
    try:
        row = await svc.crear_regla_comunicacion(
            conn, tenant_id=perfil_actor.tenant_id,
            datos=body.model_dump(),
            created_by_user_id=perfil_actor.user_id,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            409,
            detail={
                'error': 'conflict',
                'code': 'regla_duplicada',
                'message': 'Ya existe regla para esta combinación origen-destino.',
            },
        )
    except asyncpg.ForeignKeyViolationError:
        raise HTTPException(
            404,
            detail={'error': 'not_found', 'message': 'Alguna dependencia no existe.'},
        )

    await emit_gd_event(
        conn,
        tipo_evento='gd.regla_comunicacion.creada',
        accion='crear',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='regla_comunicacion',
        entidad_afectada_id=row['id'],
        valor_nuevo={
            'origen': str(body.dependencia_origen_id),
            'destino': str(body.dependencia_destino_id),
            'permitido': body.permitido,
        },
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return ReglaComunicacionResponse(**row)


@router_reglas.get(
    '',
    response_model=ReglasComunicacionListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_reglas(
    dependencia_origen_id: UUID | None = Query(default=None),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ReglasComunicacionListResponse:
    rows = await svc.listar_reglas_comunicacion(
        conn, tenant_id=perfil.tenant_id,
        dependencia_origen_id=dependencia_origen_id,
    )
    return ReglasComunicacionListResponse(
        items=[ReglaComunicacionResponse(**r) for r in rows],
    )


@router_reglas.get(
    '/validar',
    response_model=ValidacionComunicacionResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def validar_regla(
    origen: UUID = Query(...),
    destino: UUID = Query(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ValidacionComunicacionResponse:
    resultado = await svc.validar_comunicacion(
        conn, tenant_id=perfil.tenant_id, origen=origen, destino=destino,
    )
    return ValidacionComunicacionResponse(**resultado)


__all__ = [
    'router_cargos', 'router_canales', 'router_calendarios',
    'router_tipos_pqrsd', 'router_tipos_corresp', 'router_reglas',
]
