"""GD-API-0002 — Middleware/dependencies de seguridad del módulo GD.

NO duplica la autenticación del producto principal. Reusa `app.core.security`
(Auth0/JWT/session) y agrega validaciones específicas de GD:

- `require_gd_perfil`: verifica que el usuario autenticado tenga
  `gd.perfil_usuario` activo en el tenant; si no, 403 con código claro
  `gd_profile_missing_or_inactive`.
- `require_gd_permission(permiso, alcance)`: valida que el perfil GD tenga el
  permiso solicitado con alcance suficiente, evaluado contra el catálogo
  `gd.rol_permiso` y las asignaciones activas en `gd.asignacion_alcance`.
  Emite evento `gd.acceso.denegado` con criticidad `media` cuando falla.

Convención clave (D9): los roles GD viven SOLO en `gd.asignacion_alcance`, NO
en `app.user_tenant_roles` (que tiene CHECK restrictivo a los 6 roles del
producto principal). Las queries de permisos consultan únicamente
`gd.asignacion_alcance` ∩ `gd.rol_permiso`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import Depends, HTTPException, Request, status

from app.db.pool import get_db


Alcance = Literal['propio', 'dependencia', 'dependencias_autorizadas', 'institucional', 'global']

_ALCANCE_RANK: dict[str, int] = {
    'propio': 10,
    'dependencia': 20,
    'dependencias_autorizadas': 30,
    'institucional': 40,
    'global': 50,
}


@dataclass(frozen=True)
class GdPerfilContext:
    """Snapshot mínimo del perfil GD del usuario para validaciones en request.

    Se construye una vez por request al pasar por `require_gd_perfil` y se
    guarda en `request.state.gd_perfil` para evitar consultas repetidas.
    """

    user_id: UUID
    tenant_id: UUID
    perfil_id: UUID
    tipo_vinculacion: str
    estado_gd: str
    dependencia_actual_id: UUID | None
    cargo_actual_id: UUID | None


async def _load_perfil(
    conn: asyncpg.Connection, *, user_id: UUID, tenant_id: UUID
) -> GdPerfilContext | None:
    """Carga el perfil GD del usuario para el tenant activo o None si no existe."""
    row = await conn.fetchrow(
        """
        select
            id            as perfil_id,
            user_id,
            tenant_id,
            tipo_vinculacion,
            estado_gd,
            dependencia_actual_id,
            cargo_actual_id
        from gd.perfil_usuario
        where user_id = $1 and tenant_id = $2
        """,
        user_id,
        tenant_id,
    )
    if row is None:
        return None
    return GdPerfilContext(
        user_id=row['user_id'],
        tenant_id=row['tenant_id'],
        perfil_id=row['perfil_id'],
        tipo_vinculacion=row['tipo_vinculacion'],
        estado_gd=row['estado_gd'],
        dependencia_actual_id=row['dependencia_actual_id'],
        cargo_actual_id=row['cargo_actual_id'],
    )


async def require_gd_perfil(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),  # noqa: B008 — FastAPI dependency pattern
) -> GdPerfilContext:
    """FastAPI dependency: exige perfil GD activo en el tenant.

    Cómo se obtiene `user_id` y `tenant_id` de la request:
    - `request.state.user_id`: lo setea el middleware Auth0/JWT del producto
      principal (ver `app/core/security.py:authenticate_request`).
    - `request.state.tenant_id`: lo setea el mismo middleware al resolver el
      header `X-Tenant-Id` contra el JWT.

    Raises:
        HTTPException 401: si la request no tiene contexto de usuario/tenant
          (el middleware de auth ya debería haberlo rechazado, pero defensivo).
        HTTPException 403 (code 'gd_profile_missing_or_inactive'): si no hay
          perfil GD o no está en estado 'activo'. El cliente puede mostrar al
          usuario el mensaje "Solicite a su administrador activarlo en
          Gestión Documental".
    """
    user_id: UUID | None = getattr(request.state, 'user_id', None)
    tenant_id: UUID | None = getattr(request.state, 'tenant_id', None)
    if user_id is None or tenant_id is None:
        # Defensive — el middleware Auth0 debió haber rechazado antes.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                'error': 'unauthenticated',
                'message': 'Token o tenant no resuelto.',
            },
        )

    perfil = await _load_perfil(conn, user_id=user_id, tenant_id=tenant_id)
    if perfil is None or perfil.estado_gd != 'activo':
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                'error': 'forbidden',
                'code': 'gd_profile_missing_or_inactive',
                'message': (
                    'El usuario no tiene perfil activo en Gestión Documental. '
                    'Solicite a su administrador activarlo.'
                ),
            },
        )

    # Cachear en request.state para que dependencias subsecuentes (permisos) no
    # vuelvan a consultar. Inmutable por dataclass(frozen=True).
    request.state.gd_perfil = perfil
    return perfil


async def get_permisos_efectivos(
    conn: asyncpg.Connection,
    *,
    user_id: UUID,
    tenant_id: UUID,
) -> dict[str, str]:
    """Devuelve `{permiso_codigo: alcance_máximo}` de las asignaciones vigentes.

    Implementa la resolución que valida `require_gd_permission`. Se expone
    también como helper público porque `GET /api/v1/gd/me` retorna la lista de
    permisos efectivos al cliente.

    Estrategia:
      - Para cada `gd.asignacion_alcance` activa (sin fecha_fin o futura):
        - Resolver permisos del rol vía `gd.rol_permiso`.
        - Calcular el alcance efectivo como min(alcance asignado, alcance_default
          del permiso) — el más restrictivo manda (RNF-008 principio de menor
          privilegio).
      - Agregar por permiso_codigo quedándose con el alcance MÁXIMO de todas
        las asignaciones (el usuario puede tener mismo permiso en varias
        dependencias).
    """
    rows = await conn.fetch(
        """
        select
            rp.permiso_codigo,
            aa.alcance         as alcance_asignacion,
            rp.alcance_default as alcance_default_permiso
        from gd.asignacion_alcance aa
        join gd.rol_permiso rp on rp.rol_codigo = aa.rol_codigo
        join gd.rol r          on r.codigo = aa.rol_codigo
        join gd.permiso p      on p.codigo = rp.permiso_codigo
        where aa.user_id = $1
          and aa.tenant_id = $2
          and aa.estado = 'activa'
          and (aa.fecha_fin is null or aa.fecha_fin >= current_date)
          and r.estado = 'activo'
          and rp.estado = 'activo'
          and p.estado = 'activo'
        """,
        user_id,
        tenant_id,
    )

    # Agregar en Python para evitar window functions complejas + permitir
    # incorporar la lógica de "alcance más restrictivo" de forma legible.
    efectivos: dict[str, str] = {}
    for row in rows:
        permiso = row['permiso_codigo']
        alcance_asign = row['alcance_asignacion']
        alcance_default = row['alcance_default_permiso']

        # Alcance efectivo de esta asignación: el más restrictivo (menor rango).
        rank_asign = _ALCANCE_RANK.get(alcance_asign, 0)
        rank_default = _ALCANCE_RANK.get(alcance_default, 0)
        alcance_efectivo = alcance_asign if rank_asign < rank_default else alcance_default

        # Agregar por permiso quedándose con el alcance MÁXIMO entre asignaciones.
        if permiso not in efectivos:
            efectivos[permiso] = alcance_efectivo
        else:
            actual = efectivos[permiso]
            if _ALCANCE_RANK.get(alcance_efectivo, 0) > _ALCANCE_RANK.get(actual, 0):
                efectivos[permiso] = alcance_efectivo

    return efectivos


def _alcance_es_suficiente(alcance_usuario: str | None, alcance_requerido: str) -> bool:
    """True si el alcance del usuario cubre el requerido."""
    if alcance_usuario is None:
        return False
    return _ALCANCE_RANK.get(alcance_usuario, 0) >= _ALCANCE_RANK.get(alcance_requerido, 0)


def require_gd_permission(permiso_codigo: str, *, alcance: Alcance = 'propio'):
    """Factory de FastAPI dependency: exige un permiso GD con alcance suficiente.

    Uso típico::

        @router.post('/api/v1/gd/perfil-usuario', dependencies=[
            Depends(require_gd_permission('PERM-USR-001', alcance='institucional'))
        ])
        async def crear_perfil(...): ...

    Implementación: encadena `require_gd_perfil` (carga perfil) y luego consulta
    `get_permisos_efectivos` para evaluar.

    Raises:
        HTTPException 403 (code 'forbidden'): si el permiso falta o el alcance
          es insuficiente. **No revela** si el recurso existe ni datos del
          mismo (RNF-047).
    """

    async def _check(
        request: Request,
        perfil: GdPerfilContext = Depends(require_gd_perfil),  # noqa: B008
        conn: asyncpg.Connection = Depends(get_db),  # noqa: B008
    ) -> None:
        efectivos = await get_permisos_efectivos(
            conn, user_id=perfil.user_id, tenant_id=perfil.tenant_id
        )
        alcance_usuario = efectivos.get(permiso_codigo)
        if not _alcance_es_suficiente(alcance_usuario, alcance):
            # GD-API-0006: emitir evento auditado de denegación ANTES de devolver
            # el 403. Si la emisión falla, NO bloqueamos la respuesta (auditoría
            # nunca debe ser causa de UX degradada) — solo logueamos y seguimos.
            try:
                from app.gd.services.audit_emitter import (
                    AuditCriticidad,
                    emit_gd_event,
                )
                await emit_gd_event(
                    conn,
                    tipo_evento='gd.acceso.denegado',
                    accion='denegar_acceso',
                    tenant_id=perfil.tenant_id,
                    usuario_id=perfil.user_id,
                    actor_snapshot={'estado_gd': perfil.estado_gd},
                    detalles={
                        'permiso_requerido': permiso_codigo,
                        'alcance_requerido': alcance,
                        'alcance_usuario': alcance_usuario,
                        'path': str(getattr(request, 'url', '')),
                    },
                    criticidad=AuditCriticidad.MEDIA,
                    request_id=getattr(request.state, 'request_id', None),
                )
            except Exception as exc:  # noqa: BLE001
                import structlog
                structlog.get_logger().warning(
                    'gd.acceso_denegado.audit_failed',
                    permiso=permiso_codigo,
                    alcance=alcance,
                    error=str(exc),
                )

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    'error': 'forbidden',
                    'message': 'Permiso insuficiente para esta operación.',
                    'permiso_requerido': permiso_codigo,
                    'alcance_requerido': alcance,
                },
            )

    return _check


__all__ = [
    'Alcance',
    'GdPerfilContext',
    'get_permisos_efectivos',
    'require_gd_perfil',
    'require_gd_permission',
]
