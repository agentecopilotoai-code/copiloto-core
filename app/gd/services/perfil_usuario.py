"""Servicios SQL para GD-API-0003 — Gestión de `gd.perfil_usuario`.

Encapsula los queries asyncpg para que los handlers HTTP se mantengan delgados.
"""
from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import asyncpg


async def crear_perfil(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    user_id: UUID,
    tipo_vinculacion: str,
    fecha_inicio_vinculacion: date,
    fecha_fin_vinculacion: date | None,
    dependencia_actual_id: UUID,
    cargo_actual_id: UUID | None,
    created_by_user_id: UUID | None,
) -> dict[str, Any]:
    """Inserta perfil GD. Retorna la fila completa.

    Errores SQL transformados por el handler en HTTPException apropiada.
    """
    row = await conn.fetchrow(
        """
        insert into gd.perfil_usuario (
            tenant_id, user_id, tipo_vinculacion,
            fecha_inicio_vinculacion, fecha_fin_vinculacion,
            dependencia_actual_id, cargo_actual_id, created_by_user_id
        ) values ($1, $2, $3, $4, $5, $6, $7, $8)
        returning
            id as perfil_id, tenant_id, user_id, tipo_vinculacion, estado_gd,
            fecha_inicio_vinculacion, fecha_fin_vinculacion,
            dependencia_actual_id, cargo_actual_id, ultimo_acceso,
            created_at, created_by_user_id
        """,
        tenant_id, user_id, tipo_vinculacion,
        fecha_inicio_vinculacion, fecha_fin_vinculacion,
        dependencia_actual_id, cargo_actual_id, created_by_user_id,
    )
    return dict(row)


async def actualizar_perfil(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    user_id: UUID,
    cambios: dict[str, Any],
) -> dict[str, Any] | None:
    """PATCH de perfil GD. `cambios` solo incluye campos a actualizar.

    Retorna la fila actualizada o None si no existe.
    """
    if not cambios:
        # Sin cambios — devolver fila tal cual.
        row = await conn.fetchrow(
            'select * from gd.perfil_usuario where tenant_id=$1 and user_id=$2',
            tenant_id, user_id,
        )
        if row is None:
            return None
        return _row_to_perfil_dict(row)

    # Construir UPDATE dinámico con parámetros nombrados (asyncpg usa $N).
    set_parts: list[str] = []
    params: list[Any] = [tenant_id, user_id]
    for col, val in cambios.items():
        params.append(val)
        set_parts.append(f'{col} = ${len(params)}')

    sql = (
        f"update gd.perfil_usuario set {', '.join(set_parts)} "
        'where tenant_id=$1 and user_id=$2 '
        'returning id as perfil_id, tenant_id, user_id, tipo_vinculacion, estado_gd, '
        'fecha_inicio_vinculacion, fecha_fin_vinculacion, '
        'dependencia_actual_id, cargo_actual_id, ultimo_acceso, '
        'created_at, created_by_user_id'
    )
    row = await conn.fetchrow(sql, *params)
    if row is None:
        return None
    return dict(row)


# Mapeo accion → estado_gd nuevo. 'desbloquear' regresa a 'activo'.
ACCION_A_ESTADO: dict[str, str] = {
    'inactivar': 'inactivo',
    'bloquear': 'bloqueado',
    'desbloquear': 'activo',
    'retirar': 'retirado',
    'suspender': 'suspendido',
}


async def cambiar_estado(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    user_id: UUID,
    accion: str,
) -> tuple[str, str] | None:
    """Cambia estado_gd. Retorna (estado_anterior, estado_nuevo) o None si no existe.

    Usa CTE para capturar el valor PRE-UPDATE atomicamente sin necesidad de
    dos roundtrips a Postgres.
    """
    if accion not in ACCION_A_ESTADO:
        raise ValueError(f'accion inválida: {accion!r}. Permitidas: {list(ACCION_A_ESTADO)}.')
    estado_nuevo = ACCION_A_ESTADO[accion]

    row = await conn.fetchrow(
        """
        with anterior as (
            select estado_gd as estado_anterior
            from gd.perfil_usuario
            where tenant_id=$1 and user_id=$2
            for update
        ),
        actualizado as (
            update gd.perfil_usuario
            set estado_gd = $3
            where tenant_id=$1 and user_id=$2
            returning estado_gd as estado_nuevo
        )
        select a.estado_anterior, u.estado_nuevo
        from anterior a, actualizado u
        """,
        tenant_id, user_id, estado_nuevo,
    )
    if row is None:
        return None
    return (row['estado_anterior'], row['estado_nuevo'])


async def listar_perfiles(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    dependencia_id: UUID | None = None,
    estado_gd: list[str] | None = None,
    tipo_vinculacion: list[str] | None = None,
    q: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Listado paginado. Devuelve hasta `limit` filas (sin cursor por simplicidad
    en v1 — paginación real se introduce cuando haya volumen > 1000)."""
    where_parts: list[str] = ['p.tenant_id = $1']
    params: list[Any] = [tenant_id]

    if dependencia_id:
        params.append(dependencia_id)
        where_parts.append(f'p.dependencia_actual_id = ${len(params)}')

    if estado_gd:
        params.append(estado_gd)
        where_parts.append(f'p.estado_gd = any(${len(params)}::text[])')

    if tipo_vinculacion:
        params.append(tipo_vinculacion)
        where_parts.append(f'p.tipo_vinculacion = any(${len(params)}::text[])')

    if q:
        params.append(f'%{q}%')
        where_parts.append(
            f'(u.email::text ilike ${len(params)} or u.display_name ilike ${len(params)})'
        )

    params.append(limit)
    sql = f"""
        select
            p.user_id, u.email::text as email, u.display_name,
            p.tipo_vinculacion, p.estado_gd,
            p.dependencia_actual_id, p.cargo_actual_id,
            (
                select count(*) from gd.asignacion_alcance aa
                where aa.user_id = p.user_id and aa.tenant_id = p.tenant_id
                  and aa.estado = 'activa'
                  and (aa.fecha_fin is null or aa.fecha_fin >= current_date)
            ) as roles_gd_count,
            p.ultimo_acceso
        from gd.perfil_usuario p
        join app.users u on u.id = p.user_id
        where {' and '.join(where_parts)}
        order by p.created_at desc
        limit ${len(params)}
    """
    rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]


async def contar_perfiles(conn: asyncpg.Connection, *, tenant_id: UUID) -> int:
    """Conteo total (para total_estimado de paginación)."""
    row = await conn.fetchrow(
        'select count(*) as c from gd.perfil_usuario where tenant_id = $1',
        tenant_id,
    )
    return int(row['c']) if row else 0


async def obtener_historial(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    user_id: UUID,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Eventos de `core.evento_auditoria` que afectaron este perfil."""
    rows = await conn.fetch(
        """
        select
            id as evento_auditoria_id,
            tipo_evento, accion, valor_anterior, valor_nuevo,
            usuario_id as ejecutado_por_user_id,
            actor_snapshot->>'nombre_completo' as ejecutado_por_nombre,
            justificacion as motivo,
            fecha_hora as fecha
        from core.evento_auditoria
        where dominio = 'gd'
          and entidad_afectada_tipo = 'perfil_usuario'
          and entidad_afectada_identificador = $2::text
          and tenant_id = $1
        order by fecha_hora desc
        limit $3
        """,
        tenant_id, str(user_id), limit,
    )
    return [dict(r) for r in rows]


def _row_to_perfil_dict(row: asyncpg.Record) -> dict[str, Any]:
    """Normaliza una fila completa de gd.perfil_usuario al dict del servicio."""
    return {
        'perfil_id': row['id'],
        'tenant_id': row['tenant_id'],
        'user_id': row['user_id'],
        'tipo_vinculacion': row['tipo_vinculacion'],
        'estado_gd': row['estado_gd'],
        'fecha_inicio_vinculacion': row['fecha_inicio_vinculacion'],
        'fecha_fin_vinculacion': row['fecha_fin_vinculacion'],
        'dependencia_actual_id': row['dependencia_actual_id'],
        'cargo_actual_id': row['cargo_actual_id'],
        'ultimo_acceso': row['ultimo_acceso'],
        'created_at': row['created_at'],
        'created_by_user_id': row['created_by_user_id'],
    }


__all__ = [
    'ACCION_A_ESTADO',
    'crear_perfil',
    'actualizar_perfil',
    'cambiar_estado',
    'listar_perfiles',
    'contar_perfiles',
    'obtener_historial',
]
