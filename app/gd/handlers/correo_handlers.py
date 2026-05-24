"""Handlers HTTP de EP-012 correo institucional (bloque 13).

Endpoints (12):
Buzones (GD-API-0073):
- POST   /api/v1/gd/correo/buzones                          (crear)
- GET    /api/v1/gd/correo/buzones                          (listar)
- GET    /api/v1/gd/correo/buzones/{id}                     (detalle)
- PATCH  /api/v1/gd/correo/buzones/{id}                     (editar)
- POST   /api/v1/gd/correo/buzones/{id}/probar-conexion
- POST   /api/v1/gd/correo/buzones/{id}/ejecutar-worker     (GD-API-0074, admin)

Correos importados (GD-API-0074, 0075, 0076):
- GET    /api/v1/gd/correo/correos                          (listar)
- GET    /api/v1/gd/correo/correos/{id}                     (detalle)
- POST   /api/v1/gd/correo/correos/{id}/convertir-a-radicado
- POST   /api/v1/gd/correo/correos/{id}/asociar-radicado/{rad_id}
- POST   /api/v1/gd/correo/correos/{id}/descartar
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.correo import (
    AsociarRadicadoRequest,
    BuzonListResponse,
    BuzonResponse,
    ConvertirCorreoRadicadoRequest,
    CorreoImportadoListResponse,
    CorreoImportadoResponse,
    CrearBuzonRequest,
    DescartarCorreoRequest,
    EjecutarWorkerRequest,
    PatchBuzonRequest,
    ProbarConexionRequest,
    TestConexionResult,
    WorkerExecutionResult,
)
from app.gd.security import GdPerfilContext, require_gd_perfil
from app.gd.services import correo as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router = APIRouter(prefix='/correo', tags=['gd:correo'])


def _err_estado(e: ValueError) -> HTTPException:
    return HTTPException(409, detail={'error': 'conflict', 'code': str(e)})


def _err_not_found(e: LookupError) -> HTTPException:
    return HTTPException(404, detail={'error': 'not_found', 'code': str(e)})


def _bz_to_response(row: dict[str, Any]) -> BuzonResponse:
    return BuzonResponse(**row)


def _correo_to_response(row: dict[str, Any]) -> CorreoImportadoResponse:
    return CorreoImportadoResponse(**row)


# =============================================================================
# Buzones (GD-API-0073)
# =============================================================================

@router.post(
    '/buzones',
    response_model=BuzonResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def crear_buzon(
    body: CrearBuzonRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> BuzonResponse:
    try:
        row = await svc.crear_buzon(
            conn, tenant_id=perfil.tenant_id,
            nombre=body.nombre, direccion_correo=body.direccion_correo,
            proveedor=body.proveedor, dependencia_id=body.dependencia_id,
            host=body.host, port=body.port, usar_tls=body.usar_tls,
            usuario_smtp=body.usuario_smtp, config=body.config,
            secret_vault_ref=body.secret_vault_ref,
            envio_acuse_recibido=body.envio_acuse_recibido,
            plantilla_acuse_id=body.plantilla_acuse_id,
            created_by_user_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e

    await emit_gd_event(
        conn, tipo_evento='BuzonCorreoCreado', accion='crear_buzon',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='buzon_correo_institucional',
        entidad_afectada_id=row['id'],
        valor_nuevo={'direccion': body.direccion_correo,
                      'proveedor': body.proveedor},
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _bz_to_response(row)


@router.get(
    '/buzones',
    response_model=BuzonListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_buzones(
    estado: str | None = Query(default=None),
    dependencia_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> BuzonListResponse:
    rows = await svc.listar_buzones(
        conn, tenant_id=perfil.tenant_id,
        estado=estado, dependencia_id=dependencia_id, limit=limit,
    )
    items = [_bz_to_response(r) for r in rows]
    return BuzonListResponse(items=items, total=len(items))


@router.get(
    '/buzones/{buzon_id}',
    response_model=BuzonResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def detalle_buzon(
    buzon_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> BuzonResponse:
    row = await svc.obtener_buzon(
        conn, tenant_id=perfil.tenant_id, buzon_id=buzon_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return _bz_to_response(row)


@router.patch(
    '/buzones/{buzon_id}',
    response_model=BuzonResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def patch_buzon(
    body: PatchBuzonRequest, request: Request,
    buzon_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> BuzonResponse:
    cambios = body.model_dump(exclude_none=True)
    row = await svc.patch_buzon(
        conn, tenant_id=perfil.tenant_id, buzon_id=buzon_id, cambios=cambios,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='BuzonCorreoActualizado', accion='patch',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='buzon_correo_institucional',
        entidad_afectada_id=buzon_id,
        valor_nuevo=cambios,
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _bz_to_response(row)


@router.post(
    '/buzones/{buzon_id}/probar-conexion',
    response_model=TestConexionResult,
    dependencies=[Depends(require_gd_perfil)],
)
async def probar_conexion(
    body: ProbarConexionRequest, request: Request,
    buzon_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> TestConexionResult:
    result = await svc.probar_conexion(
        conn, tenant_id=perfil.tenant_id, buzon_id=buzon_id, provider=None,
    )
    if result is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='BuzonCorreoProbado', accion='probar_conexion',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='buzon_correo_institucional',
        entidad_afectada_id=buzon_id,
        valor_nuevo={'exitoso': result['exitoso']},
        criticidad=AuditCriticidad.BAJA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return TestConexionResult(**result)


@router.post(
    '/buzones/{buzon_id}/ejecutar-worker',
    response_model=WorkerExecutionResult,
    dependencies=[Depends(require_gd_perfil)],
)
async def ejecutar_worker(
    body: EjecutarWorkerRequest, request: Request,
    buzon_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> WorkerExecutionResult:
    try:
        result = await svc.ejecutar_worker(
            conn, tenant_id=perfil.tenant_id, buzon_id=buzon_id,
            max_correos=body.max_correos, provider=None,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if result is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='BuzonCorreoWorkerEjecutado',
        accion='ejecutar_worker',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='buzon_correo_institucional',
        entidad_afectada_id=buzon_id,
        valor_nuevo={'nuevos': result['correos_nuevos'],
                      'duplicados': result['correos_duplicados_omitidos'],
                      'errores': result['errores']},
        criticidad=AuditCriticidad.BAJA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return WorkerExecutionResult(**result)


# =============================================================================
# Correos importados
# =============================================================================

@router.get(
    '/correos',
    response_model=CorreoImportadoListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_correos(
    buzon_id: UUID | None = Query(default=None),
    estado: str | None = Query(default=None),
    remitente_email: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CorreoImportadoListResponse:
    rows = await svc.listar_correos(
        conn, tenant_id=perfil.tenant_id,
        buzon_id=buzon_id, estado=estado,
        remitente_email=remitente_email, limit=limit,
    )
    total = await svc.contar_correos(
        conn, tenant_id=perfil.tenant_id, buzon_id=buzon_id,
    )
    items = [_correo_to_response(r) for r in rows]
    return CorreoImportadoListResponse(items=items, total=total)


@router.get(
    '/correos/{correo_id}',
    response_model=CorreoImportadoResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def detalle_correo(
    correo_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CorreoImportadoResponse:
    row = await svc.obtener_correo(
        conn, tenant_id=perfil.tenant_id, correo_id=correo_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return _correo_to_response(row)


@router.post(
    '/correos/{correo_id}/convertir-a-radicado',
    dependencies=[Depends(require_gd_perfil)],
    status_code=status.HTTP_201_CREATED,
)
async def convertir_a_radicado(
    body: ConvertirCorreoRadicadoRequest, request: Request,
    correo_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> dict[str, Any]:
    try:
        r = await svc.convertir_a_radicado(
            conn, tenant_id=perfil.tenant_id, correo_id=correo_id,
            canal_id=body.canal_id,
            asunto_override=body.asunto_override,
            descripcion=body.descripcion,
            tercero_id=body.tercero_id, crear_tercero=body.crear_tercero,
            dependencia_destino_id=body.dependencia_destino_id,
            enviar_acuse=body.enviar_acuse,
            usuario_actor_id=perfil.user_id, provider=None,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if r is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='CorreoConvertidoARadicado',
        accion='convertir_a_radicado',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='correo_importado',
        entidad_afectada_id=correo_id,
        valor_nuevo={'radicado_id': str(r['radicado_id']),
                      'radicado_numero': r['radicado_numero'],
                      'acuse_estado': r['acuse_estado']},
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return {
        'correo': _correo_to_response(r['correo']).model_dump(mode='json'),
        'radicado_id': str(r['radicado_id']),
        'radicado_numero': r['radicado_numero'],
        'acuse_estado': r['acuse_estado'],
    }


@router.post(
    '/correos/{correo_id}/asociar-radicado/{radicado_id}',
    response_model=CorreoImportadoResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def asociar_radicado(
    body: AsociarRadicadoRequest, request: Request,
    correo_id: UUID = Path(...),
    radicado_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CorreoImportadoResponse:
    try:
        row = await svc.asociar_a_radicado(
            conn, tenant_id=perfil.tenant_id, correo_id=correo_id,
            radicado_id=radicado_id, observaciones=body.observaciones,
            usuario_actor_id=perfil.user_id,
        )
    except LookupError as e:
        raise _err_not_found(e) from e
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='CorreoAsociadoARadicado', accion='asociar_radicado',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='correo_importado',
        entidad_afectada_id=correo_id,
        valor_nuevo={'radicado_id': str(radicado_id)},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _correo_to_response(row)


@router.post(
    '/correos/{correo_id}/descartar',
    response_model=CorreoImportadoResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def descartar_correo(
    body: DescartarCorreoRequest, request: Request,
    correo_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CorreoImportadoResponse:
    try:
        row = await svc.descartar_correo(
            conn, tenant_id=perfil.tenant_id, correo_id=correo_id,
            motivo=body.motivo, usuario_actor_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='CorreoDescartado', accion='descartar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='correo_importado',
        entidad_afectada_id=correo_id,
        justificacion=body.motivo,
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _correo_to_response(row)


__all__ = ['router']
