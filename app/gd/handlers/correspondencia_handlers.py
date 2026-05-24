"""Handlers HTTP de EP-008 correspondencia interna/externa (bloque 9).

Endpoints (15 nuevos):
Interna (GD-API-0052):
- POST   /api/v1/gd/correspondencia/interna
- POST   /api/v1/gd/correspondencia/{id}/marcar-leida
- POST   /api/v1/gd/correspondencia/{id}/responder
- POST   /api/v1/gd/correspondencia/{id}/reenviar

Externa recibida (GD-API-0053):
- GET    /api/v1/gd/correspondencia/externa/recibida
- POST   /api/v1/gd/correspondencia/{id}/gestionar
(creación via hook reactivo en clasificar_radicado tipo='correspondencia_externa')

Externa enviada workflow (GD-API-0054):
- POST   /api/v1/gd/correspondencia/externa/borrador
- POST   /api/v1/gd/correspondencia/{id}/enviar-a-revision
- POST   /api/v1/gd/correspondencia/{id}/revisar
- POST   /api/v1/gd/correspondencia/{id}/aprobar
- POST   /api/v1/gd/correspondencia/{id}/firmar
- POST   /api/v1/gd/correspondencia/{id}/radicar-salida
- POST   /api/v1/gd/correspondencia/{id}/enviar
- POST   /api/v1/gd/correspondencia/{id}/registrar-soporte-envio

Lectura + anulación (GD-API-0056):
- GET    /api/v1/gd/correspondencia               (listar con filtros)
- GET    /api/v1/gd/correspondencia/{id}
- POST   /api/v1/gd/correspondencia/{id}/anular   (solicitar)
- POST   /api/v1/gd/correspondencia/solicitudes-anulacion/{id}/aprobar
- POST   /api/v1/gd/correspondencia/solicitudes-anulacion/{id}/rechazar
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.correspondencia import (
    AnularCorrespondenciaRequest,
    AprobarAnulacionCorrespRequest,
    AprobarCorrespondenciaRequest,
    CorrespondenciaListItem,
    CorrespondenciaListResponse,
    CorrespondenciaResponse,
    CrearExternaEnviadaBorrador,
    CrearInternaRequest,
    DestinatarioResponse,
    EnviarCorrespondenciaRequest,
    EnviarRevisionInRequest,
    FirmarCorrespondenciaRequest,
    GestionarExternaRecibidaRequest,
    MarcarLeidaRequest,
    RadicarSalidaCorrespondenciaRequest,
    RechazarAnulacionCorrespRequest,
    ReenviarRequest,
    RegistrarSoporteEnvioRequest,
    ResponderRequest,
    RevisarCorrespondenciaRequest,
    SolicitudAnulacionCorrespResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil
from app.gd.services import correspondencia as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router = APIRouter(prefix='/correspondencia', tags=['gd:correspondencia'])


# =============================================================================
# Helpers
# =============================================================================

def _to_response(row: dict[str, Any]) -> CorrespondenciaResponse:
    destinatarios = [DestinatarioResponse(**d) for d in row.get('destinatarios', [])]
    return CorrespondenciaResponse(
        id=row['id'], tipo=row['tipo'],
        dependencia_origen_id=row.get('dependencia_origen_id'),
        dependencia_destino_id=row.get('dependencia_destino_id'),
        tercero_remitente_id=row.get('tercero_remitente_id'),
        radicado_entrada_id=row.get('radicado_entrada_id'),
        radicado_salida_id=row.get('radicado_salida_id'),
        documento_principal_id=row.get('documento_principal_id'),
        plantilla_id=row.get('plantilla_id'),
        asunto=row['asunto'], contenido_borrador=row.get('contenido_borrador'),
        prioridad=row.get('prioridad', 'normal'),
        requiere_respuesta=row.get('requiere_respuesta', False),
        fecha_limite_respuesta=row.get('fecha_limite_respuesta'),
        estado=row['estado'],
        usuario_proyecta_id=row['usuario_proyecta_id'],
        usuario_revisa_id=row.get('usuario_revisa_id'),
        usuario_aprueba_id=row.get('usuario_aprueba_id'),
        usuario_firma_id=row.get('usuario_firma_id'),
        usuario_envio_id=row.get('usuario_envio_id'),
        fecha_envio=row.get('fecha_envio'),
        fecha_aprobacion=row.get('fecha_aprobacion'),
        fecha_firma=row.get('fecha_firma'),
        fecha_radicacion=row.get('fecha_radicacion'),
        observaciones_devolucion=row.get('observaciones_devolucion'),
        canal_envio_id=row.get('canal_envio_id'),
        soporte_envio_uri=row.get('soporte_envio_uri'),
        soporte_envio_codigo_rastreo=row.get('soporte_envio_codigo_rastreo'),
        fecha_registro_soporte=row.get('fecha_registro_soporte'),
        anulada_en=row.get('anulada_en'),
        motivo_anulacion=row.get('motivo_anulacion'),
        correspondencia_padre_id=row.get('correspondencia_padre_id'),
        created_at=row['created_at'],
        destinatarios=destinatarios,
    )


def _err_estado(e: ValueError) -> HTTPException:
    return HTTPException(409, detail={'error': 'conflict', 'code': str(e)})


def _err_perm(e: PermissionError) -> HTTPException:
    return HTTPException(
        403, detail={'error': 'forbidden', 'code': 'separacion_funciones',
                     'message': str(e)},
    )


# =============================================================================
# Listado + detalle (GET)
# =============================================================================

@router.get(
    '',
    response_model=CorrespondenciaListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar(
    tipo: str | None = Query(default=None,
                              pattern='^(interna|externa_recibida|externa_enviada)$'),
    estado: str | None = Query(default=None),
    dependencia_id: UUID | None = Query(default=None),
    tercero_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CorrespondenciaListResponse:
    estados = estado.split(',') if estado else None
    rows = await svc.listar_correspondencia(
        conn, tenant_id=perfil.tenant_id,
        tipo=tipo, estado=estados,
        dependencia_id=dependencia_id, tercero_id=tercero_id, limit=limit,
    )
    total = await svc.contar_correspondencia(
        conn, tenant_id=perfil.tenant_id, tipo=tipo,
    )
    items = [CorrespondenciaListItem(**r) for r in rows]
    return CorrespondenciaListResponse(items=items, total=total)


# GET listado externa recibida (atajo con filtro pre-aplicado).
@router.get(
    '/externa/recibida',
    response_model=CorrespondenciaListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def listar_externa_recibida(
    dependencia: UUID | None = Query(default=None),
    estado: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CorrespondenciaListResponse:
    estados = estado.split(',') if estado else None
    rows = await svc.listar_correspondencia(
        conn, tenant_id=perfil.tenant_id,
        tipo='externa_recibida', estado=estados,
        dependencia_id=dependencia, limit=limit,
    )
    total = await svc.contar_correspondencia(
        conn, tenant_id=perfil.tenant_id, tipo='externa_recibida',
    )
    items = [CorrespondenciaListItem(**r) for r in rows]
    return CorrespondenciaListResponse(items=items, total=total)


# =============================================================================
# Interna (GD-API-0052)
# =============================================================================

@router.post(
    '/interna',
    response_model=CorrespondenciaResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def crear_interna(
    body: CrearInternaRequest, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CorrespondenciaResponse:
    try:
        row = await svc.crear_interna(
            conn, tenant_id=perfil.tenant_id,
            dependencia_origen_id=body.dependencia_origen_id,
            asunto=body.asunto, contenido_borrador=body.contenido_borrador,
            prioridad=body.prioridad, requiere_respuesta=body.requiere_respuesta,
            fecha_limite_respuesta=body.fecha_limite_respuesta,
            documento_principal_id=body.documento_principal_id,
            plantilla_id=body.plantilla_id,
            destinatarios=[d.model_dump() for d in body.destinatarios],
            usuario_proyecta_id=perfil.user_id,
            enviar_inmediato=body.enviar_inmediato,
        )
    except ValueError as e:
        raise _err_estado(e) from e

    await emit_gd_event(
        conn, tipo_evento='CorrespondenciaInternaCreada', accion='crear_interna',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='correspondencia', entidad_afectada_id=row['id'],
        valor_nuevo={'destinatarios_n': len(row['destinatarios']),
                      'enviar_inmediato': body.enviar_inmediato},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    if body.enviar_inmediato:
        await emit_gd_event(
            conn, tipo_evento='CorrespondenciaInternaEnviada', accion='enviar_interna',
            tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
            entidad_afectada_tipo='correspondencia', entidad_afectada_id=row['id'],
            criticidad=AuditCriticidad.MEDIA,
            request_id=getattr(request.state, 'request_id', None),
        )
    return _to_response(row)


@router.post(
    '/{correspondencia_id}/marcar-leida',
    response_model=CorrespondenciaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def marcar_leida(
    body: MarcarLeidaRequest, request: Request,
    correspondencia_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CorrespondenciaResponse:
    row = await svc.marcar_leida(
        conn, tenant_id=perfil.tenant_id,
        correspondencia_id=correspondencia_id,
        dependencia_id=body.dependencia_id,
        usuario_actor_id=perfil.user_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found',
                                          'code': 'sin_destinatario_pendiente'})

    await emit_gd_event(
        conn, tipo_evento='CorrespondenciaInternaLeida', accion='marcar_leida',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='correspondencia',
        entidad_afectada_id=correspondencia_id,
        valor_nuevo={'dependencia_id': str(body.dependencia_id)},
        criticidad=AuditCriticidad.BAJA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _to_response(row)


@router.post(
    '/{correspondencia_id}/responder',
    response_model=CorrespondenciaResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def responder(
    body: ResponderRequest, request: Request,
    correspondencia_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CorrespondenciaResponse:
    try:
        row = await svc.responder(
            conn, tenant_id=perfil.tenant_id,
            correspondencia_id=correspondencia_id,
            dependencia_origen_id=body.dependencia_origen_id,
            asunto=body.asunto, contenido_borrador=body.contenido_borrador,
            documento_principal_id=body.documento_principal_id,
            usuario_proyecta_id=perfil.user_id,
            enviar_inmediato=body.enviar_inmediato,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='CorrespondenciaInternaCreada', accion='responder',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='correspondencia', entidad_afectada_id=row['id'],
        valor_nuevo={'padre_id': str(correspondencia_id)},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _to_response(row)


@router.post(
    '/{correspondencia_id}/reenviar',
    response_model=CorrespondenciaResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def reenviar(
    body: ReenviarRequest, request: Request,
    correspondencia_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CorrespondenciaResponse:
    try:
        row = await svc.reenviar(
            conn, tenant_id=perfil.tenant_id,
            correspondencia_id=correspondencia_id,
            dependencia_origen_id=body.dependencia_origen_id,
            destinatarios=[d.model_dump() for d in body.destinatarios],
            usuario_proyecta_id=perfil.user_id,
            observaciones=body.observaciones,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='CorrespondenciaInternaCreada', accion='reenviar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='correspondencia', entidad_afectada_id=row['id'],
        valor_nuevo={'padre_id': str(correspondencia_id),
                      'destinatarios_n': len(row['destinatarios'])},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _to_response(row)


# =============================================================================
# Externa recibida (GD-API-0053)
# =============================================================================

@router.post(
    '/{correspondencia_id}/gestionar',
    response_model=CorrespondenciaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def gestionar(
    body: GestionarExternaRecibidaRequest, request: Request,
    correspondencia_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CorrespondenciaResponse:
    try:
        row = await svc.gestionar_externa_recibida(
            conn, tenant_id=perfil.tenant_id,
            correspondencia_id=correspondencia_id,
            observaciones=body.observaciones,
            dependencia_id=body.dependencia_id,
            usuario_actor_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='CorrespondenciaExternaGestionada', accion='gestionar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='correspondencia',
        entidad_afectada_id=correspondencia_id,
        justificacion=body.observaciones,
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _to_response(row)


# =============================================================================
# Externa enviada — workflow (GD-API-0054)
# =============================================================================

@router.post(
    '/externa/borrador',
    response_model=CorrespondenciaResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def crear_externa_borrador(
    body: CrearExternaEnviadaBorrador, request: Request,
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CorrespondenciaResponse:
    row = await svc.crear_externa_enviada_borrador(
        conn, tenant_id=perfil.tenant_id,
        dependencia_origen_id=body.dependencia_origen_id,
        asunto=body.asunto, contenido_borrador=body.contenido_borrador,
        prioridad=body.prioridad,
        documento_principal_id=body.documento_principal_id,
        plantilla_id=body.plantilla_id,
        destinatarios=[d.model_dump() for d in body.destinatarios],
        usuario_proyecta_id=perfil.user_id,
    )
    await emit_gd_event(
        conn, tipo_evento='CorrespondenciaExternaPreparada',
        accion='crear_externa_borrador',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='correspondencia', entidad_afectada_id=row['id'],
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _to_response(row)


@router.post(
    '/{correspondencia_id}/enviar-a-revision',
    response_model=CorrespondenciaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def wf_enviar_revision(
    body: EnviarRevisionInRequest, request: Request,
    correspondencia_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CorrespondenciaResponse:
    try:
        row = await svc.workflow_enviar_a_revision(
            conn, tenant_id=perfil.tenant_id,
            correspondencia_id=correspondencia_id,
            usuario_actor_id=perfil.user_id, observaciones=body.observaciones,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='CorrespondenciaExternaEnviadaRevision',
        accion='enviar_a_revision',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='correspondencia',
        entidad_afectada_id=correspondencia_id,
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _to_response(row)


@router.post(
    '/{correspondencia_id}/revisar',
    response_model=CorrespondenciaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def wf_revisar(
    body: RevisarCorrespondenciaRequest, request: Request,
    correspondencia_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CorrespondenciaResponse:
    try:
        row = await svc.workflow_revisar(
            conn, tenant_id=perfil.tenant_id,
            correspondencia_id=correspondencia_id,
            resultado=body.resultado, observaciones=body.observaciones,
            usuario_actor_id=perfil.user_id,
        )
    except PermissionError as e:
        raise _err_perm(e) from e
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    tipo = ('CorrespondenciaExternaDevuelta'
            if body.resultado == 'devolver' else 'CorrespondenciaExternaAprobada')
    await emit_gd_event(
        conn, tipo_evento=tipo, accion='revisar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='correspondencia',
        entidad_afectada_id=correspondencia_id,
        valor_nuevo={'resultado': body.resultado},
        justificacion=body.observaciones,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _to_response(row)


@router.post(
    '/{correspondencia_id}/aprobar',
    response_model=CorrespondenciaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def wf_aprobar(
    body: AprobarCorrespondenciaRequest, request: Request,
    correspondencia_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CorrespondenciaResponse:
    try:
        row = await svc.workflow_aprobar(
            conn, tenant_id=perfil.tenant_id,
            correspondencia_id=correspondencia_id,
            usuario_actor_id=perfil.user_id, observaciones=body.observaciones,
        )
    except PermissionError as e:
        raise _err_perm(e) from e
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='CorrespondenciaExternaAprobada', accion='aprobar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='correspondencia',
        entidad_afectada_id=correspondencia_id,
        justificacion=body.observaciones,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _to_response(row)


@router.post(
    '/{correspondencia_id}/firmar',
    response_model=CorrespondenciaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def wf_firmar(
    body: FirmarCorrespondenciaRequest, request: Request,
    correspondencia_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CorrespondenciaResponse:
    try:
        row = await svc.workflow_firmar(
            conn, tenant_id=perfil.tenant_id,
            correspondencia_id=correspondencia_id,
            usuario_actor_id=perfil.user_id, firma_id=body.firma_id,
        )
    except PermissionError as e:
        raise _err_perm(e) from e
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='CorrespondenciaExternaFirmada', accion='firmar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='correspondencia',
        entidad_afectada_id=correspondencia_id,
        valor_nuevo={'firma_id': str(body.firma_id) if body.firma_id else None},
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _to_response(row)


@router.post(
    '/{correspondencia_id}/radicar-salida',
    response_model=CorrespondenciaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def wf_radicar(
    body: RadicarSalidaCorrespondenciaRequest, request: Request,
    correspondencia_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CorrespondenciaResponse:
    try:
        row = await svc.workflow_radicar_salida(
            conn, tenant_id=perfil.tenant_id,
            correspondencia_id=correspondencia_id,
            usuario_actor_id=perfil.user_id, canal_envio_id=body.canal_envio_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='CorrespondenciaExternaRadicadaSalida',
        accion='radicar_salida',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='correspondencia',
        entidad_afectada_id=correspondencia_id,
        valor_nuevo={'radicado_salida_id': str(row.get('radicado_salida_id'))},
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _to_response(row)


@router.post(
    '/{correspondencia_id}/enviar',
    response_model=CorrespondenciaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def wf_enviar(
    body: EnviarCorrespondenciaRequest, request: Request,
    correspondencia_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CorrespondenciaResponse:
    try:
        row = await svc.workflow_enviar(
            conn, tenant_id=perfil.tenant_id,
            correspondencia_id=correspondencia_id,
            usuario_actor_id=perfil.user_id, canal_envio_id=body.canal_envio_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='CorrespondenciaExternaEnviada', accion='enviar',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='correspondencia',
        entidad_afectada_id=correspondencia_id,
        valor_nuevo={'canal_envio_id': str(body.canal_envio_id) if body.canal_envio_id else None},
        justificacion=body.observaciones,
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _to_response(row)


@router.post(
    '/{correspondencia_id}/registrar-soporte-envio',
    response_model=CorrespondenciaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def reg_soporte(
    body: RegistrarSoporteEnvioRequest, request: Request,
    correspondencia_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CorrespondenciaResponse:
    try:
        row = await svc.registrar_soporte_envio(
            conn, tenant_id=perfil.tenant_id,
            correspondencia_id=correspondencia_id,
            soporte_envio_uri=body.soporte_envio_uri,
            codigo_rastreo=body.codigo_rastreo,
            usuario_actor_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='CorrespondenciaSoporteRegistrado',
        accion='registrar_soporte_envio',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='correspondencia',
        entidad_afectada_id=correspondencia_id,
        valor_nuevo={'soporte_uri': body.soporte_envio_uri,
                      'codigo_rastreo': body.codigo_rastreo},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return _to_response(row)


# =============================================================================
# Anulación (GD-API-0056)
# =============================================================================

@router.post(
    '/{correspondencia_id}/anular',
    response_model=SolicitudAnulacionCorrespResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_perfil)],
)
async def solicitar_anulacion(
    body: AnularCorrespondenciaRequest, request: Request,
    correspondencia_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> SolicitudAnulacionCorrespResponse:
    try:
        row = await svc.solicitar_anulacion(
            conn, tenant_id=perfil.tenant_id,
            correspondencia_id=correspondencia_id,
            motivo=body.motivo,
            evidencia_archivo_digital_id=body.evidencia_archivo_digital_id,
            solicitante_user_id=perfil.user_id,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='SolicitudAnulacionCorrespondencia',
        accion='solicitar_anulacion',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='correspondencia',
        entidad_afectada_id=correspondencia_id,
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return SolicitudAnulacionCorrespResponse(**row)


@router.post(
    '/solicitudes-anulacion/{solicitud_id}/aprobar',
    response_model=SolicitudAnulacionCorrespResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def aprobar_anulacion(
    body: AprobarAnulacionCorrespRequest, request: Request,
    solicitud_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> SolicitudAnulacionCorrespResponse:
    try:
        row = await svc.aprobar_anulacion(
            conn, tenant_id=perfil.tenant_id, solicitud_id=solicitud_id,
            aprobador_user_id=perfil.user_id, observacion=body.observacion,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='CorrespondenciaAnulada', accion='aprobar_anulacion',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='correspondencia',
        entidad_afectada_id=row['entidad_afectada_id'],
        justificacion=body.observacion,
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return SolicitudAnulacionCorrespResponse(**row)


@router.post(
    '/solicitudes-anulacion/{solicitud_id}/rechazar',
    response_model=SolicitudAnulacionCorrespResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def rechazar_anulacion(
    body: RechazarAnulacionCorrespRequest, request: Request,
    solicitud_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> SolicitudAnulacionCorrespResponse:
    try:
        row = await svc.rechazar_anulacion(
            conn, tenant_id=perfil.tenant_id, solicitud_id=solicitud_id,
            aprobador_user_id=perfil.user_id, observacion=body.observacion,
        )
    except ValueError as e:
        raise _err_estado(e) from e
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    await emit_gd_event(
        conn, tipo_evento='SolicitudAnulacionRechazada',
        accion='rechazar_anulacion',
        tenant_id=perfil.tenant_id, usuario_id=perfil.user_id,
        entidad_afectada_tipo='correspondencia',
        entidad_afectada_id=row['entidad_afectada_id'],
        justificacion=body.observacion,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )
    return SolicitudAnulacionCorrespResponse(**row)


# =============================================================================
# Detalle (definido AL FINAL para evitar shadowing de rutas literales)
# =============================================================================

@router.get(
    '/{correspondencia_id}',
    response_model=CorrespondenciaResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def detalle(
    correspondencia_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> CorrespondenciaResponse:
    row = await svc.obtener_correspondencia(
        conn, tenant_id=perfil.tenant_id,
        correspondencia_id=correspondencia_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    return _to_response(row)


__all__ = ['router']
