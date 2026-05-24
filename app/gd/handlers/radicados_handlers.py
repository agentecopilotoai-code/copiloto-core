"""GD-API-0024..0029 — Endpoints de Ventanilla Única (radicados).

El handler más grande del módulo. Orquesta:
- POST entrada/salida: tercero inline opcional + consecutivo + código verificación
- Clasificación / reclasificación con historial
- Anulación con separación de funciones (RNF-008)
- Búsqueda multi-criterio + detalle
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.radicados import (
    ClasificacionResponse,
    ClasificarRadicadoRequest,
    ClasificarResponse,
    RadicadoActorSnapshot,
    RadicadoAnuladoResponse,
    RadicadoCanalSummary,
    RadicadoConstancia,
    RadicadoCreatedResponse,
    RadicadoDetalleResponse,
    RadicadoEntradaCreate,
    RadicadoListItem,
    RadicadoListResponse,
    RadicadoPagina,
    RadicadoSalidaCreate,
    RadicadoTerceroSummary,
    ReclasificarRadicadoRequest,
    SolicitudAnulacionCreate,
    SolicitudAnulacionDecisionRequest,
    SolicitudAnulacionResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil, require_gd_permission
from app.gd.services import radicados as svc
from app.gd.services import terceros as svc_terceros
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event
from app.gd.services.snapshots import capturar_snapshot


router_ventanilla = APIRouter(prefix='/ventanilla', tags=['gd:ventanilla'])


def _enmascarar_documento(numero: str | None) -> str | None:
    """Enmascara documento: '12345678' → '***45678'."""
    if not numero or len(numero) < 4:
        return numero
    return '***' + numero[-5:]


def _tercero_to_summary(t: dict | None) -> RadicadoTerceroSummary | None:
    if t is None:
        return None
    return RadicadoTerceroSummary(
        id=t['id'],
        tipo_tercero=t['tipo_tercero'],
        tipo_documento=t.get('tipo_documento'),
        numero_documento_enmascarado=_enmascarar_documento(t.get('numero_documento')),
        nombres_razon_social=t['nombres_razon_social'],
    )


def _build_constancia(numero_radicado: str, codigo: str) -> RadicadoConstancia:
    # TODO(human): cuando exista perfil_organizacion, leer sitio_web para
    # construir URL personalizada. Por ahora usamos placeholder genérico.
    return RadicadoConstancia(
        codigo_verificacion=codigo,
        url_publica=f'/gd/verificar/{codigo}',
        qr_archivo_digital_id=None,  # generación QR a EP-021/EP-010
        constancia_pdf_archivo_digital_id=None,  # PDF a EP-010
    )


# =============================================================================
# POST radicado entrada
# =============================================================================

@router_ventanilla.post(
    '/radicados/entrada',
    response_model=RadicadoCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_permission('PERM-VU-001', alcance='institucional'))],
)
async def crear_radicado_entrada(
    body: RadicadoEntradaCreate,
    request: Request,
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RadicadoCreatedResponse:
    # 1. Validar canal existe + reglas requiere_punto_atencion.
    canal_row = await conn.fetchrow(
        """
        select id, codigo, nombre, requiere_punto_atencion
        from gd.canal where id = $1 and tenant_id = $2 and estado = 'activo'
        """,
        body.canal_id, perfil_actor.tenant_id,
    )
    if canal_row is None:
        raise HTTPException(
            404,
            detail={
                'error': 'not_found',
                'code': 'canal_no_existe_o_inactivo',
                'message': 'El canal_id no existe o está inactivo.',
            },
        )
    if canal_row['requiere_punto_atencion'] and body.punto_atencion_id is None:
        raise HTTPException(
            422,
            detail={
                'error': 'validation_error',
                'code': 'punto_atencion_requerido',
                'message': f'Canal {canal_row["codigo"]} exige punto_atencion_id.',
            },
        )

    # 2. Resolver tercero (existente o crear inline).
    tercero_id: UUID | None = body.tercero_id
    if body.tercero_nuevo is not None:
        try:
            tercero_row = await svc_terceros.crear_tercero(
                conn, tenant_id=perfil_actor.tenant_id,
                datos=body.tercero_nuevo.model_dump(),
                created_by_user_id=perfil_actor.user_id,
            )
        except asyncpg.UniqueViolationError:
            raise HTTPException(
                409,
                detail={
                    'error': 'conflict',
                    'code': 'tercero_duplicado',
                    'message': 'Ya existe un tercero con ese documento. Use tercero_id en su lugar.',
                },
            )
        tercero_id = tercero_row['id']
        tercero_full = tercero_row
    elif tercero_id:
        tercero_full = await svc_terceros.obtener_tercero(
            conn, tenant_id=perfil_actor.tenant_id, tercero_id=tercero_id,
        )
        if tercero_full is None:
            raise HTTPException(
                404,
                detail={'error': 'not_found', 'message': 'tercero_id no existe'},
            )
    else:
        tercero_full = None

    # 3. Capturar snapshot del actor.
    try:
        snapshot = await capturar_snapshot(conn, user_id=perfil_actor.user_id)
    except ValueError:
        snapshot = {'usuario_id': str(perfil_actor.user_id)}

    # 4. Crear radicado (genera consecutivo + código_verificacion).
    radicado_row = await svc.crear_radicado(
        conn, tenant_id=perfil_actor.tenant_id,
        tipo_radicado='entrada',
        canal_id=body.canal_id,
        asunto=body.asunto, descripcion=body.descripcion,
        tercero_id=tercero_id,
        tercero_destinatario_id=None,
        dependencia_origen_id=body.dependencia_origen_id,
        dependencia_destino_id=None,  # se setea al clasificar
        documento_principal_id=None,
        usuario_radicador_id=perfil_actor.user_id,
        actor_snapshot=snapshot,
        punto_atencion_id=body.punto_atencion_id,
        metadata={
            'sugerencia_ia_id': str(body.sugerencia_ia_id) if body.sugerencia_ia_id else None,
            'es_radicacion_externa_desde_dependencia': body.es_radicacion_externa_desde_dependencia,
        },
    )

    # 5. Si hay clasificacion_sugerida, clasificar inline.
    if body.clasificacion_sugerida is not None:
        sug = body.clasificacion_sugerida
        # No exige tipo_pqrsd_id aquí (validación se hace en /clasificar formal).
        await svc.clasificar_radicado(
            conn, tenant_id=perfil_actor.tenant_id,
            radicado_id=radicado_row['id'],
            tipo_clasificacion=sug.tipo_clasificacion,
            sub_tipo=sug.sub_tipo,
            dependencia_destino_id=sug.dependencia_destino_id,
            tipo_pqrsd_id=None,
            justificacion=None,
            sugerencia_ia_id=body.sugerencia_ia_id,
            clasificado_por_user_id=perfil_actor.user_id,
        )

    # 6. Emitir evento auditable.
    await emit_gd_event(
        conn,
        tipo_evento='RadicadoCreado',
        accion='crear_radicado_entrada',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='radicado',
        entidad_afectada_id=radicado_row['id'],
        entidad_afectada_identificador=radicado_row['numero_radicado'],
        actor_snapshot=snapshot,
        valor_nuevo={
            'numero_radicado': radicado_row['numero_radicado'],
            'canal_id': str(body.canal_id),
            'asunto': body.asunto,
        },
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )

    # 7. Construir response.
    return RadicadoCreatedResponse(
        id=radicado_row['id'],
        numero_radicado=radicado_row['numero_radicado'],
        tipo_radicado='entrada',
        fecha_radicacion=radicado_row['fecha_radicacion'],
        canal=RadicadoCanalSummary(
            id=canal_row['id'], codigo=canal_row['codigo'], nombre=canal_row['nombre'],
        ),
        asunto=body.asunto, descripcion=body.descripcion,
        tercero=_tercero_to_summary(tercero_full),
        dependencia_origen=None,
        estado='registrado',
        anexos_count=len(body.anexos),  # TODO(human): persistir anexos en gd.anexo cuando EP-009
        constancia=_build_constancia(
            radicado_row['numero_radicado'], radicado_row['codigo_verificacion'],
        ),
        actor_snapshot=RadicadoActorSnapshot(
            usuario_id=perfil_actor.user_id,
            nombre_completo=snapshot.get('nombre_completo'),
            rol_codigo=snapshot.get('rol_codigo'),
            dependencia_codigo=snapshot.get('dependencia_codigo'),
            cargo=snapshot.get('cargo_nombre'),
        ),
        creado_en=radicado_row['created_at'],
    )


# =============================================================================
# POST radicado salida
# =============================================================================

@router_ventanilla.post(
    '/radicados/salida',
    response_model=RadicadoCreatedResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_permission('PERM-VU-002', alcance='dependencia'))],
)
async def crear_radicado_salida(
    body: RadicadoSalidaCreate, request: Request,
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RadicadoCreatedResponse:
    # 1. Validar canal de envío.
    canal_row = await conn.fetchrow(
        """
        select id, codigo, nombre, requiere_punto_atencion
        from gd.canal where id = $1 and tenant_id = $2 and estado = 'activo'
        """,
        body.canal_envio_id, perfil_actor.tenant_id,
    )
    if canal_row is None:
        raise HTTPException(
            404, detail={'error': 'not_found', 'code': 'canal_envio_no_existe'},
        )

    # 2. Validar radicado de entrada relacionado (si aplica).
    if body.radicado_entrada_relacionado_id is not None:
        rel = await conn.fetchrow(
            """
            select estado, tipo_radicado from gd.radicado
            where id = $1 and tenant_id = $2
            """,
            body.radicado_entrada_relacionado_id, perfil_actor.tenant_id,
        )
        if rel is None:
            raise HTTPException(
                404, detail={'error': 'not_found', 'message': 'radicado_entrada_relacionado_id no existe'},
            )
        if rel['estado'] == 'anulado':
            raise HTTPException(
                409,
                detail={
                    'error': 'conflict',
                    'code': 'radicado_entrada_anulado',
                    'message': 'El radicado de entrada relacionado está anulado.',
                },
            )

    # 3. Resolver destinatario.
    tercero_destinatario_id: UUID | None = body.tercero_destinatario_id
    if body.tercero_destinatario_nuevo is not None:
        try:
            tercero_row = await svc_terceros.crear_tercero(
                conn, tenant_id=perfil_actor.tenant_id,
                datos=body.tercero_destinatario_nuevo.model_dump(),
                created_by_user_id=perfil_actor.user_id,
            )
            tercero_destinatario_id = tercero_row['id']
            tercero_full = tercero_row
        except asyncpg.UniqueViolationError:
            raise HTTPException(409, detail={'error': 'conflict', 'code': 'tercero_duplicado'})
    elif tercero_destinatario_id:
        tercero_full = await svc_terceros.obtener_tercero(
            conn, tenant_id=perfil_actor.tenant_id, tercero_id=tercero_destinatario_id,
        )
    else:
        tercero_full = None

    # 4. TODO(human): cuando exista gd.documento, validar que
    # documento_principal_id está en estado 'firmado'. Por ahora aceptamos
    # cualquier UUID o NULL.

    # 5. Snapshot + crear radicado.
    try:
        snapshot = await capturar_snapshot(conn, user_id=perfil_actor.user_id)
    except ValueError:
        snapshot = {'usuario_id': str(perfil_actor.user_id)}

    radicado_row = await svc.crear_radicado(
        conn, tenant_id=perfil_actor.tenant_id,
        tipo_radicado='salida', canal_id=body.canal_envio_id,
        asunto=body.asunto, descripcion=body.descripcion,
        tercero_id=None, tercero_destinatario_id=tercero_destinatario_id,
        dependencia_origen_id=body.dependencia_origen_id,
        dependencia_destino_id=None,
        documento_principal_id=body.documento_principal_id,
        usuario_radicador_id=perfil_actor.user_id,
        actor_snapshot=snapshot,
        radicado_relacionado_id=body.radicado_entrada_relacionado_id,
    )

    await emit_gd_event(
        conn,
        tipo_evento='RadicadoCreado',
        accion='crear_radicado_salida',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='radicado',
        entidad_afectada_id=radicado_row['id'],
        entidad_afectada_identificador=radicado_row['numero_radicado'],
        actor_snapshot=snapshot,
        valor_nuevo={'numero_radicado': radicado_row['numero_radicado']},
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )

    return RadicadoCreatedResponse(
        id=radicado_row['id'],
        numero_radicado=radicado_row['numero_radicado'],
        tipo_radicado='salida',
        fecha_radicacion=radicado_row['fecha_radicacion'],
        canal=RadicadoCanalSummary(
            id=canal_row['id'], codigo=canal_row['codigo'], nombre=canal_row['nombre'],
        ),
        asunto=body.asunto, descripcion=body.descripcion,
        tercero=_tercero_to_summary(tercero_full),
        dependencia_origen=None,
        estado='registrado',
        anexos_count=len(body.anexos),
        constancia=_build_constancia(
            radicado_row['numero_radicado'], radicado_row['codigo_verificacion'],
        ),
        actor_snapshot=RadicadoActorSnapshot(
            usuario_id=perfil_actor.user_id,
            nombre_completo=snapshot.get('nombre_completo'),
            rol_codigo=snapshot.get('rol_codigo'),
            dependencia_codigo=snapshot.get('dependencia_codigo'),
            cargo=snapshot.get('cargo_nombre'),
        ),
        creado_en=radicado_row['created_at'],
    )


# =============================================================================
# GET listar/buscar + detalle
# =============================================================================

@router_ventanilla.get(
    '/radicados',
    response_model=RadicadoListResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def buscar_radicados(
    numero_radicado: str | None = Query(default=None),
    q: str | None = Query(default=None),
    tipo_radicado: str | None = Query(default=None),
    estado: str | None = Query(default=None),
    canal_id: UUID | None = Query(default=None),
    dependencia_destino_id: UUID | None = Query(default=None),
    tercero_id: UUID | None = Query(default=None),
    fecha_radicacion_desde: datetime | None = Query(default=None),
    fecha_radicacion_hasta: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RadicadoListResponse:
    tipo_list = tipo_radicado.split(',') if tipo_radicado else None
    estado_list = estado.split(',') if estado else None

    rows = await svc.buscar_radicados(
        conn, tenant_id=perfil.tenant_id,
        numero_radicado=numero_radicado, q=q,
        tipo_radicado=tipo_list, estado=estado_list,
        canal_id=canal_id, dependencia_destino_id=dependencia_destino_id,
        tercero_id=tercero_id,
        fecha_desde=fecha_radicacion_desde, fecha_hasta=fecha_radicacion_hasta,
        limit=limit,
    )
    total = await svc.contar_radicados(conn, tenant_id=perfil.tenant_id)

    items: list[RadicadoListItem] = []
    for r in rows:
        items.append(RadicadoListItem(
            id=r['id'],
            numero_radicado=r['numero_radicado'],
            tipo_radicado=r['tipo_radicado'],
            fecha_radicacion=r['fecha_radicacion'],
            asunto=r['asunto'],
            estado=r['estado'],
            canal=RadicadoCanalSummary(
                id=r['canal_id'], codigo=r['canal_codigo'], nombre=r['canal_nombre'],
            ),
            tercero=None,  # enriquecimiento bajo demanda en /{id}
            dependencia_destino=(
                {'id': str(r['dependencia_destino_id'])}
                if r.get('dependencia_destino_id') else None
            ),
            clasificacion_vigente=(
                {'tipo_clasificacion': r['clasificacion_tipo']}
                if r.get('clasificacion_tipo') else None
            ),
            anexos_count=int(r.get('anexos_count') or 0),
        ))

    return RadicadoListResponse(
        items=items,
        pagina=RadicadoPagina(
            siguiente_cursor=None, total_estimado=total, limit_aplicado=limit,
        ),
    )


@router_ventanilla.get(
    '/radicados/{radicado_id}',
    response_model=RadicadoDetalleResponse,
    dependencies=[Depends(require_gd_perfil)],
)
async def detalle_radicado(
    radicado_id: UUID = Path(...),
    perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RadicadoDetalleResponse:
    row = await svc.obtener_radicado(
        conn, tenant_id=perfil.tenant_id, radicado_id=radicado_id,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    # Enriquecer tercero si existe.
    tercero_summary = None
    if row.get('tercero_id'):
        t = await svc_terceros.obtener_tercero(
            conn, tenant_id=perfil.tenant_id, tercero_id=row['tercero_id'],
        )
        tercero_summary = _tercero_to_summary(t)

    # Actor snapshot puede venir como str (jsonb) o dict.
    actor = row.get('actor_snapshot')
    if isinstance(actor, str):
        import json
        actor = json.loads(actor)
    actor = actor or {}

    return RadicadoDetalleResponse(
        id=row['id'],
        numero_radicado=row['numero_radicado'],
        tipo_radicado=row['tipo_radicado'],
        fecha_radicacion=row['fecha_radicacion'],
        canal=RadicadoCanalSummary(
            id=row['canal_id'], codigo=row['canal_codigo'], nombre=row['canal_nombre'],
        ),
        asunto=row['asunto'], descripcion=row.get('descripcion'),
        tercero=tercero_summary,
        actor_snapshot=RadicadoActorSnapshot(
            usuario_id=actor.get('usuario_id') or row['usuario_radicador_id'],
            nombre_completo=actor.get('nombre_completo'),
            rol_codigo=actor.get('rol_codigo'),
            dependencia_codigo=actor.get('dependencia_codigo'),
            cargo=actor.get('cargo_nombre'),
        ) if actor else None,
        estado=row['estado'],
        radicado_relacionado_id=row.get('radicado_relacionado_id'),
        codigo_verificacion=row['codigo_verificacion'],
        es_radicacion_contingencia=row.get('es_radicacion_contingencia', False),
    )


# =============================================================================
# Clasificación
# =============================================================================

@router_ventanilla.post(
    '/radicados/{radicado_id}/clasificar',
    response_model=ClasificarResponse,
    dependencies=[Depends(require_gd_permission('PERM-VU-005', alcance='institucional'))],
)
async def clasificar_radicado(
    body: ClasificarRadicadoRequest, request: Request,
    radicado_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ClasificarResponse:
    clasif = await svc.clasificar_radicado(
        conn, tenant_id=perfil_actor.tenant_id, radicado_id=radicado_id,
        tipo_clasificacion=body.tipo_clasificacion,
        sub_tipo=body.sub_tipo,
        dependencia_destino_id=body.dependencia_destino_id,
        tipo_pqrsd_id=body.tipo_pqrsd_id,
        justificacion=body.justificacion,
        sugerencia_ia_id=body.sugerencia_ia_id,
        clasificado_por_user_id=perfil_actor.user_id,
    )
    if clasif is None:
        raise HTTPException(
            409,
            detail={
                'error': 'conflict',
                'code': 'radicado_ya_clasificado',
                'message': 'El radicado ya tiene clasificación vigente. Use /reclasificar.',
            },
        )

    evento_id = await emit_gd_event(
        conn,
        tipo_evento='RadicadoClasificado',
        accion='clasificar',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='radicado',
        entidad_afectada_id=radicado_id,
        valor_nuevo={
            'tipo_clasificacion': body.tipo_clasificacion,
            'sub_tipo': body.sub_tipo,
        },
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )

    # Handler reactivo (GD-API-0043): si tipo='pqrsd', crear gd.pqrsd
    # automáticamente. Idempotente (svc retorna None si ya existe).
    pqrsd_id: UUID | None = None
    if body.tipo_clasificacion == 'pqrsd':
        from app.gd.services import pqrsd as svc_pqrsd
        pqrsd_row = await svc_pqrsd.crear_desde_radicado(
            conn, tenant_id=perfil_actor.tenant_id,
            radicado_id=radicado_id,
            tipo_pqrsd_id=body.tipo_pqrsd_id,
            sub_tipo=body.sub_tipo,
        )
        if pqrsd_row is not None:
            pqrsd_id = pqrsd_row['id']
            await emit_gd_event(
                conn,
                tipo_evento='PQRSDCreada',
                accion='crear_pqrsd_desde_radicado',
                tenant_id=perfil_actor.tenant_id,
                usuario_id=perfil_actor.user_id,
                entidad_afectada_tipo='pqrsd',
                entidad_afectada_id=pqrsd_id,
                valor_nuevo={
                    'radicado_entrada_id': str(radicado_id),
                    'sub_tipo': body.sub_tipo,
                    'fecha_limite_respuesta': (
                        pqrsd_row.get('fecha_limite_respuesta').isoformat()
                        if pqrsd_row.get('fecha_limite_respuesta') else None
                    ),
                },
                criticidad=AuditCriticidad.ALTA,
                request_id=getattr(request.state, 'request_id', None),
            )

    # Handler reactivo (GD-API-0053): si tipo='correspondencia_externa',
    # crear gd.correspondencia externa_recibida (idempotente).
    correspondencia_id: UUID | None = None
    if body.tipo_clasificacion == 'correspondencia_externa':
        from app.gd.services import correspondencia as svc_corresp
        corr_row = await svc_corresp.crear_desde_radicado_externa(
            conn, tenant_id=perfil_actor.tenant_id,
            radicado_id=radicado_id, sub_tipo=body.sub_tipo,
        )
        if corr_row is not None:
            correspondencia_id = corr_row['id']
            await emit_gd_event(
                conn,
                tipo_evento='CorrespondenciaExternaRecibidaCreada',
                accion='crear_correspondencia_desde_radicado',
                tenant_id=perfil_actor.tenant_id,
                usuario_id=perfil_actor.user_id,
                entidad_afectada_tipo='correspondencia',
                entidad_afectada_id=correspondencia_id,
                valor_nuevo={
                    'radicado_entrada_id': str(radicado_id),
                    'sub_tipo': body.sub_tipo,
                },
                criticidad=AuditCriticidad.MEDIA,
                request_id=getattr(request.state, 'request_id', None),
            )

    return ClasificarResponse(
        radicado_id=radicado_id,
        clasificacion=ClasificacionResponse(**clasif),
        recursos_creados={
            'pqrsd_id': pqrsd_id,
            'correspondencia_id': correspondencia_id,
            'expediente_id': None,
        },
        evento_auditoria_id=evento_id,
    )


@router_ventanilla.post(
    '/radicados/{radicado_id}/reclasificar',
    response_model=ClasificarResponse,
    dependencies=[Depends(require_gd_permission('PERM-VU-006', alcance='institucional'))],
)
async def reclasificar_radicado(
    body: ReclasificarRadicadoRequest, request: Request,
    radicado_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> ClasificarResponse:
    clasif = await svc.reclasificar_radicado(
        conn, tenant_id=perfil_actor.tenant_id, radicado_id=radicado_id,
        tipo_clasificacion=body.tipo_clasificacion,
        sub_tipo=body.sub_tipo,
        dependencia_destino_id=body.dependencia_destino_id,
        tipo_pqrsd_id=body.tipo_pqrsd_id,
        justificacion=body.justificacion,
        sugerencia_ia_id=body.sugerencia_ia_id,
        motivo=body.motivo,
        clasificado_por_user_id=perfil_actor.user_id,
    )
    if clasif is None:
        raise HTTPException(
            404,
            detail={
                'error': 'not_found',
                'code': 'sin_clasificacion_previa',
                'message': 'El radicado no tiene clasificación vigente. Use /clasificar.',
            },
        )

    evento_id = await emit_gd_event(
        conn,
        tipo_evento='RadicadoReclasificado',
        accion='reclasificar',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='radicado',
        entidad_afectada_id=radicado_id,
        valor_nuevo={
            'tipo_clasificacion': body.tipo_clasificacion,
            'sub_tipo': body.sub_tipo,
        },
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )

    return ClasificarResponse(
        radicado_id=radicado_id,
        clasificacion=ClasificacionResponse(**clasif),
        recursos_creados={'pqrsd_id': None, 'correspondencia_id': None, 'expediente_id': None},
        evento_auditoria_id=evento_id,
    )


# =============================================================================
# Anulación
# =============================================================================

@router_ventanilla.post(
    '/radicados/{radicado_id}/solicitar-anulacion',
    response_model=SolicitudAnulacionResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_permission('PERM-VU-015', alcance='institucional'))],
)
async def solicitar_anulacion(
    body: SolicitudAnulacionCreate, request: Request,
    radicado_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> SolicitudAnulacionResponse:
    # Verificar que radicado existe y no está ya anulado.
    rad = await conn.fetchrow(
        'select estado from gd.radicado where id = $1 and tenant_id = $2',
        radicado_id, perfil_actor.tenant_id,
    )
    if rad is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    if rad['estado'] == 'anulado':
        raise HTTPException(
            409,
            detail={'error': 'conflict', 'code': 'radicado_ya_anulado'},
        )

    sol = await svc.crear_solicitud_anulacion(
        conn, tenant_id=perfil_actor.tenant_id,
        tipo_entidad='radicado',
        entidad_afectada_id=radicado_id,
        solicitante_user_id=perfil_actor.user_id,
        motivo=body.motivo,
        evidencia_archivo_digital_id=body.evidencia_archivo_digital_id,
    )
    if sol is None:
        raise HTTPException(
            422,
            detail={
                'error': 'validation_error',
                'code': 'solicitud_anulacion_duplicada',
                'message': 'Ya hay una solicitud pendiente para este radicado.',
            },
        )

    await emit_gd_event(
        conn,
        tipo_evento='RadicadoAnulacionSolicitada',
        accion='solicitar_anulacion',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='radicado',
        entidad_afectada_id=radicado_id,
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )

    return SolicitudAnulacionResponse(
        solicitud_id=sol['id'],
        tipo_entidad='radicado',
        entidad_afectada_id=radicado_id,
        solicitante_user_id=perfil_actor.user_id,
        motivo=body.motivo,
        decision='pendiente',
        fecha_solicitud=sol['fecha_solicitud'],
    )


@router_ventanilla.post(
    '/anulaciones/{solicitud_id}/aprobar',
    response_model=RadicadoAnuladoResponse,
    dependencies=[Depends(require_gd_permission('PERM-VU-016', alcance='institucional'))],
)
async def aprobar_anulacion(
    body: SolicitudAnulacionDecisionRequest, request: Request,
    solicitud_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> RadicadoAnuladoResponse:
    # Validar separación de funciones RNF-008: solicitante != aprobador.
    sol = await svc.obtener_solicitud_anulacion(
        conn, tenant_id=perfil_actor.tenant_id, solicitud_id=solicitud_id,
    )
    if sol is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    if sol['decision'] != 'pendiente':
        raise HTTPException(
            409,
            detail={'error': 'conflict', 'code': 'solicitud_ya_decidida'},
        )
    if sol['solicitante_user_id'] == perfil_actor.user_id:
        raise HTTPException(
            403,
            detail={
                'error': 'forbidden',
                'code': 'solicitante_no_puede_aprobar',
                'message': 'Separación de funciones (RNF-008): el solicitante no puede aprobar.',
            },
        )

    resultado = await svc.aprobar_solicitud(
        conn, tenant_id=perfil_actor.tenant_id, solicitud_id=solicitud_id,
        aprobador_user_id=perfil_actor.user_id,
        observacion_decision=body.observacion_decision,
    )

    await emit_gd_event(
        conn,
        tipo_evento='RadicadoAnulado',
        accion='anular_radicado',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='radicado',
        entidad_afectada_id=sol['entidad_afectada_id'],
        justificacion=body.observacion_decision,
        criticidad=AuditCriticidad.CRITICA,
        request_id=getattr(request.state, 'request_id', None),
    )

    # Re-leer radicado para responder estado actualizado.
    rad = await conn.fetchrow(
        """
        select id, numero_radicado, estado, anulado_en
        from gd.radicado where id = $1
        """,
        sol['entidad_afectada_id'],
    )

    return RadicadoAnuladoResponse(
        solicitud_id=solicitud_id,
        decision='aprobada',
        aprobador_user_id=perfil_actor.user_id,
        fecha_decision=resultado['fecha_decision'],
        radicado={
            'id': str(rad['id']),
            'numero_radicado': rad['numero_radicado'],
            'estado': rad['estado'],
            'anulado_en': rad['anulado_en'].isoformat() if rad['anulado_en'] else None,
        },
    )


@router_ventanilla.post(
    '/anulaciones/{solicitud_id}/rechazar',
    response_model=SolicitudAnulacionResponse,
    dependencies=[Depends(require_gd_permission('PERM-VU-016', alcance='institucional'))],
)
async def rechazar_anulacion(
    body: SolicitudAnulacionDecisionRequest, request: Request,
    solicitud_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> SolicitudAnulacionResponse:
    if not body.observacion_decision or len(body.observacion_decision) < 10:
        raise HTTPException(
            422,
            detail={
                'error': 'validation_error',
                'message': 'observacion_decision es obligatoria para rechazar (mín. 10 chars).',
            },
        )

    sol = await svc.obtener_solicitud_anulacion(
        conn, tenant_id=perfil_actor.tenant_id, solicitud_id=solicitud_id,
    )
    if sol is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    if sol['decision'] != 'pendiente':
        raise HTTPException(409, detail={'error': 'conflict', 'code': 'solicitud_ya_decidida'})
    if sol['solicitante_user_id'] == perfil_actor.user_id:
        raise HTTPException(
            403,
            detail={
                'error': 'forbidden',
                'code': 'solicitante_no_puede_decidir',
            },
        )

    resultado = await svc.rechazar_solicitud(
        conn, tenant_id=perfil_actor.tenant_id, solicitud_id=solicitud_id,
        aprobador_user_id=perfil_actor.user_id,
        observacion_decision=body.observacion_decision,
    )

    await emit_gd_event(
        conn,
        tipo_evento='RadicadoAnulacionRechazada',
        accion='rechazar_anulacion',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='radicado',
        entidad_afectada_id=sol['entidad_afectada_id'],
        justificacion=body.observacion_decision,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )

    return SolicitudAnulacionResponse(
        solicitud_id=solicitud_id,
        tipo_entidad=sol['tipo_entidad'],
        entidad_afectada_id=sol['entidad_afectada_id'],
        solicitante_user_id=sol['solicitante_user_id'],
        motivo=sol['motivo'],
        decision='rechazada',
        fecha_solicitud=sol['fecha_solicitud'],
        aprobador_user_id=perfil_actor.user_id,
        observacion_decision=body.observacion_decision,
        fecha_decision=resultado['fecha_decision'],
    )


__all__ = ['router_ventanilla']
