"""GD-API-0003 — Endpoints de gestión institucional del perfil GD del usuario.

POST/PATCH/GET /api/v1/gd/perfil-usuario(+/{user_id}) + acciones de estado.
Documentado en INTEGRACION_E1_IDENTIDAD.md sección 2.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, status

from app.db.pool import get_db
from app.gd.schemas.perfil_usuario import (
    AccionEstadoPerfil,
    Paginacion,
    PerfilUsuarioCambioEstadoRequest,
    PerfilUsuarioCambioEstadoResponse,
    PerfilUsuarioCreate,
    PerfilUsuarioHistorialEvento,
    PerfilUsuarioHistorialResponse,
    PerfilUsuarioListItem,
    PerfilUsuarioListResponse,
    PerfilUsuarioPatch,
    PerfilUsuarioResponse,
)
from app.gd.security import GdPerfilContext, require_gd_perfil, require_gd_permission
from app.gd.services import perfil_usuario as svc
from app.gd.services.audit_emitter import AuditCriticidad, emit_gd_event


router = APIRouter(prefix='/perfil-usuario', tags=['gd:perfil-usuario'])
log = structlog.get_logger()


def _split_display_name(display_name: str | None) -> tuple[str, str]:
    """Reusa la heurística del handler /me (duplicación intencional para no crear ciclo)."""
    if not display_name or not display_name.strip():
        return ('', '')
    parts = display_name.strip().split()
    if len(parts) == 1:
        return (parts[0], '')
    if len(parts) >= 4:
        return (' '.join(parts[:-2]), ' '.join(parts[-2:]))
    return (' '.join(parts[:-1]), parts[-1])


@router.post(
    '',
    response_model=PerfilUsuarioResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_gd_permission('PERM-USR-001', alcance='institucional'))],
)
async def crear_perfil_usuario(
    body: PerfilUsuarioCreate,
    request: Request,
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PerfilUsuarioResponse:
    # Validar que el user_id ya existe en app.users.
    existe = await conn.fetchval('select 1 from app.users where id = $1', body.user_id)
    if not existe:
        raise HTTPException(
            status_code=404,
            detail={
                'error': 'not_found',
                'code': 'user_not_in_tenant',
                'message': 'El user_id no existe. Debe invitarse primero desde el tenant admin.',
            },
        )

    # Validar fecha_fin para tipos temporales.
    if body.tipo_vinculacion in ('ops', 'provisional', 'supernumerario', 'practicante') \
            and body.fecha_fin_vinculacion is None:
        raise HTTPException(
            status_code=422,
            detail={
                'error': 'validation_error',
                'code': 'fecha_fin_requerida',
                'message': f'tipo_vinculacion={body.tipo_vinculacion} requiere fecha_fin_vinculacion.',
            },
        )

    try:
        row = await svc.crear_perfil(
            conn,
            tenant_id=perfil_actor.tenant_id,
            user_id=body.user_id,
            tipo_vinculacion=body.tipo_vinculacion,
            fecha_inicio_vinculacion=body.fecha_inicio_vinculacion,
            fecha_fin_vinculacion=body.fecha_fin_vinculacion,
            dependencia_actual_id=body.dependencia_actual_id,
            cargo_actual_id=body.cargo_actual_id,
            created_by_user_id=perfil_actor.user_id,
        )
    except asyncpg.UniqueViolationError:
        raise HTTPException(
            status_code=409,
            detail={
                'error': 'conflict',
                'code': 'perfil_ya_existe',
                'message': 'El usuario ya tiene perfil GD en este tenant.',
            },
        )

    await emit_gd_event(
        conn,
        tipo_evento='gd.perfil_usuario.creado',
        accion='crear',
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='perfil_usuario',
        entidad_afectada_id=body.user_id,
        valor_nuevo={'tipo_vinculacion': body.tipo_vinculacion, 'estado_gd': 'activo'},
        criticidad=AuditCriticidad.MEDIA,
        request_id=getattr(request.state, 'request_id', None),
    )

    return PerfilUsuarioResponse(**row)


@router.patch(
    '/{user_id}',
    response_model=PerfilUsuarioResponse,
    dependencies=[Depends(require_gd_permission('PERM-USR-002', alcance='institucional'))],
)
async def patch_perfil_usuario(
    body: PerfilUsuarioPatch,
    request: Request,
    user_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PerfilUsuarioResponse:
    cambios = body.model_dump(exclude_unset=True)
    row = await svc.actualizar_perfil(
        conn,
        tenant_id=perfil_actor.tenant_id,
        user_id=user_id,
        cambios=cambios,
    )
    if row is None:
        raise HTTPException(404, detail={'error': 'not_found'})

    if cambios:
        await emit_gd_event(
            conn,
            tipo_evento='gd.perfil_usuario.modificado',
            accion='actualizar',
            tenant_id=perfil_actor.tenant_id,
            usuario_id=perfil_actor.user_id,
            entidad_afectada_tipo='perfil_usuario',
            entidad_afectada_id=user_id,
            valor_nuevo=cambios,
            criticidad=AuditCriticidad.MEDIA,
            request_id=getattr(request.state, 'request_id', None),
        )

    return PerfilUsuarioResponse(**row)


@router.post(
    '/{user_id}/{accion}',
    response_model=PerfilUsuarioCambioEstadoResponse,
    dependencies=[Depends(require_gd_permission('PERM-USR-004', alcance='institucional'))],
)
async def cambiar_estado_perfil(
    body: PerfilUsuarioCambioEstadoRequest,
    request: Request,
    user_id: UUID = Path(...),
    accion: AccionEstadoPerfil = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PerfilUsuarioCambioEstadoResponse:
    # GD-API-0008 hook: si la acción es inactivar/retirar/suspender, verificar
    # tareas pendientes ANTES de cambiar estado. Como las tablas de tareas aún
    # no existen en este bloque, asumimos 0 pendientes y dejamos un TODO.
    # TODO(human): cuando EP-006/EP-007 introduzca gd.tarea, ejecutar aquí
    # SELECT count(*) FROM gd.tarea WHERE asignado_a=user_id AND estado='pendiente'
    # y retornar 409 pending_tasks si > 0.

    resultado = await svc.cambiar_estado(
        conn,
        tenant_id=perfil_actor.tenant_id,
        user_id=user_id,
        accion=accion,
    )
    if resultado is None:
        raise HTTPException(404, detail={'error': 'not_found'})
    estado_anterior, estado_nuevo = resultado

    ejecutado_en = datetime.now(UTC)
    await emit_gd_event(
        conn,
        tipo_evento=f'gd.perfil_usuario.{accion}do' if accion != 'desbloquear' else 'gd.perfil_usuario.desbloqueado',
        accion=accion,
        tenant_id=perfil_actor.tenant_id,
        usuario_id=perfil_actor.user_id,
        entidad_afectada_tipo='perfil_usuario',
        entidad_afectada_id=user_id,
        valor_anterior={'estado_gd': estado_anterior},
        valor_nuevo={'estado_gd': estado_nuevo},
        justificacion=body.motivo,
        criticidad=AuditCriticidad.ALTA,
        request_id=getattr(request.state, 'request_id', None),
    )

    return PerfilUsuarioCambioEstadoResponse(
        user_id=user_id,
        estado_gd_anterior=estado_anterior,
        estado_gd_nuevo=estado_nuevo,
        motivo=body.motivo,
        ejecutado_por_user_id=perfil_actor.user_id,
        ejecutado_en=ejecutado_en,
    )


@router.get(
    '',
    response_model=PerfilUsuarioListResponse,
    dependencies=[Depends(require_gd_permission('PERM-USR-010', alcance='institucional'))],
)
async def listar_perfiles_usuario(
    dependencia_id: UUID | None = Query(default=None),
    estado_gd: str | None = Query(default=None),
    tipo_vinculacion: str | None = Query(default=None),
    q: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PerfilUsuarioListResponse:
    estado_list = estado_gd.split(',') if estado_gd else None
    tipo_list = tipo_vinculacion.split(',') if tipo_vinculacion else None

    rows = await svc.listar_perfiles(
        conn,
        tenant_id=perfil_actor.tenant_id,
        dependencia_id=dependencia_id,
        estado_gd=estado_list,
        tipo_vinculacion=tipo_list,
        q=q,
        limit=limit,
    )
    total = await svc.contar_perfiles(conn, tenant_id=perfil_actor.tenant_id)
    items: list[PerfilUsuarioListItem] = []
    for r in rows:
        nombres, apellidos = _split_display_name(r.get('display_name'))
        items.append(PerfilUsuarioListItem(
            user_id=r['user_id'],
            email=r['email'],
            nombres=nombres,
            apellidos=apellidos,
            tipo_vinculacion=r['tipo_vinculacion'],
            estado_gd=r['estado_gd'],
            dependencia_actual_id=r['dependencia_actual_id'],
            cargo_actual_id=r['cargo_actual_id'],
            roles_gd_count=r['roles_gd_count'],
            ultimo_acceso=r['ultimo_acceso'],
        ))
    return PerfilUsuarioListResponse(
        items=items,
        pagina=Paginacion(siguiente_cursor=None, total_estimado=total, limit_aplicado=limit),
    )


@router.get(
    '/{user_id}/historial',
    response_model=PerfilUsuarioHistorialResponse,
    dependencies=[Depends(require_gd_permission('PERM-USR-010', alcance='institucional'))],
)
async def historial_perfil_usuario(
    user_id: UUID = Path(...),
    perfil_actor: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
) -> PerfilUsuarioHistorialResponse:
    rows = await svc.obtener_historial(
        conn, tenant_id=perfil_actor.tenant_id, user_id=user_id
    )
    eventos = [PerfilUsuarioHistorialEvento(**r) for r in rows]
    return PerfilUsuarioHistorialResponse(user_id=user_id, eventos=eventos)


__all__ = ['router']
