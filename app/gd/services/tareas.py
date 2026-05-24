"""Services SQL para GD-API-0036..0039 — Tareas + buzón."""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg


# Mapeo accion → estado nuevo.
ACCION_A_ESTADO: dict[str, str] = {
    'iniciar': 'en_proceso',
    'devolver': 'devuelta',
    'finalizar': 'finalizada',
    'escalar': 'pendiente',  # escalar mantiene pendiente pero cambia asignado
    'anular': 'anulada',
}


async def crear_tarea(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    datos: dict[str, Any],
    asignado_por_user_id: UUID,
) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        insert into gd.tarea (
            tenant_id, tipo_tarea, titulo, descripcion,
            entidad_origen_tipo, entidad_origen_id,
            asignado_a_user_id, asignado_a_dependencia_id,
            asignado_por_user_id, fecha_limite, prioridad, estado
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, 'pendiente')
        returning id, tenant_id, tipo_tarea, titulo, descripcion,
                  entidad_origen_tipo, entidad_origen_id,
                  asignado_a_user_id, asignado_a_dependencia_id,
                  asignado_por_user_id, fecha_asignacion, fecha_limite,
                  prioridad, estado
        """,
        tenant_id,
        datos.get('tipo_tarea', 'generica'),
        datos['titulo'], datos.get('descripcion'),
        datos.get('entidad_origen_tipo'), datos.get('entidad_origen_id'),
        datos.get('asignado_a_user_id'), datos.get('asignado_a_dependencia_id'),
        asignado_por_user_id, datos.get('fecha_limite'),
        datos.get('prioridad', 'normal'),
    )
    # Insertar historial 'creada'.
    await conn.execute(
        """
        insert into gd.tarea_historial (
            tenant_id, tarea_id, tipo_evento, estado_nuevo,
            asignado_a_user_id_nuevo, asignado_a_dependencia_id_nuevo,
            ejecutado_por_user_id
        )
        values ($1, $2, 'creada', 'pendiente', $3, $4, $5)
        """,
        tenant_id, row['id'],
        datos.get('asignado_a_user_id'),
        datos.get('asignado_a_dependencia_id'),
        asignado_por_user_id,
    )
    return dict(row)


async def listar_tareas(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    asignado_a_user_id: UUID | None = None,
    asignado_a_dependencia_id: UUID | None = None,
    estado: list[str] | None = None,
    fecha_limite_antes: datetime | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    where_parts = ['tenant_id = $1']
    params: list[Any] = [tenant_id]

    if asignado_a_user_id:
        params.append(asignado_a_user_id)
        where_parts.append(f'asignado_a_user_id = ${len(params)}')

    if asignado_a_dependencia_id:
        params.append(asignado_a_dependencia_id)
        where_parts.append(f'asignado_a_dependencia_id = ${len(params)}')

    if estado:
        params.append(estado)
        where_parts.append(f'estado = any(${len(params)}::text[])')

    if fecha_limite_antes:
        params.append(fecha_limite_antes)
        where_parts.append(f'fecha_limite <= ${len(params)}')

    params.append(limit)
    rows = await conn.fetch(
        f"""
        select id, tenant_id, tipo_tarea, titulo, descripcion,
               entidad_origen_tipo, entidad_origen_id,
               asignado_a_user_id, asignado_a_dependencia_id,
               asignado_por_user_id, fecha_asignacion, fecha_limite,
               prioridad, estado
        from gd.tarea
        where {' and '.join(where_parts)}
        order by
            case prioridad
                when 'urgente' then 1
                when 'alta' then 2
                when 'normal' then 3
                when 'baja' then 4
            end,
            fecha_limite asc nulls last
        limit ${len(params)}
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def contar_tareas_por_estado(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    asignado_a_user_id: UUID | None = None,
    asignado_a_dependencia_id: UUID | None = None,
) -> dict[str, int]:
    where_parts = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if asignado_a_user_id:
        params.append(asignado_a_user_id)
        where_parts.append(f'asignado_a_user_id = ${len(params)}')
    if asignado_a_dependencia_id:
        params.append(asignado_a_dependencia_id)
        where_parts.append(f'asignado_a_dependencia_id = ${len(params)}')

    rows = await conn.fetch(
        f"""
        select estado, count(*) as c
        from gd.tarea
        where {' and '.join(where_parts)}
        group by estado
        """,
        *params,
    )
    return {r['estado']: int(r['c']) for r in rows}


async def aplicar_accion(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    tarea_id: UUID,
    accion: str,
    ejecutado_por_user_id: UUID,
    observacion: str | None = None,
) -> dict[str, Any] | None:
    """Aplica una acción sobre la tarea + escribe historial. None si tarea no existe."""
    if accion not in ACCION_A_ESTADO:
        raise ValueError(f'accion inválida: {accion!r}')

    estado_nuevo = ACCION_A_ESTADO[accion]

    # Obtener estado actual.
    actual = await conn.fetchrow(
        'select estado from gd.tarea where id = $1 and tenant_id = $2',
        tarea_id, tenant_id,
    )
    if actual is None:
        return None
    estado_anterior = actual['estado']

    # Construir UPDATE según acción.
    set_parts = ['estado = $3', 'updated_at = now()']
    params: list[Any] = [tenant_id, tarea_id, estado_nuevo]

    if accion == 'devolver':
        params.append(observacion)
        set_parts.append(f'observaciones_devolucion = ${len(params)}')
    elif accion == 'finalizar':
        params.extend([observacion, ejecutado_por_user_id])
        set_parts.append(f'observaciones_finalizacion = ${len(params) - 1}')
        set_parts.append('finalizada_en = now()')
        set_parts.append(f'finalizada_por_user_id = ${len(params)}')
    elif accion == 'anular':
        params.append(observacion)
        set_parts.append(f'motivo_anulacion = ${len(params)}')

    sql = (
        f"update gd.tarea set {', '.join(set_parts)} "
        'where id = $2 and tenant_id = $1 '
        'returning id, tenant_id, tipo_tarea, titulo, descripcion, '
        'entidad_origen_tipo, entidad_origen_id, '
        'asignado_a_user_id, asignado_a_dependencia_id, '
        'asignado_por_user_id, fecha_asignacion, fecha_limite, '
        'prioridad, estado'
    )
    row = await conn.fetchrow(sql, *params)

    tipo_evento_map = {
        'iniciar': 'iniciada', 'devolver': 'devuelta',
        'finalizar': 'finalizada', 'escalar': 'escalada', 'anular': 'anulada',
    }
    await conn.execute(
        """
        insert into gd.tarea_historial (
            tenant_id, tarea_id, tipo_evento,
            estado_anterior, estado_nuevo,
            motivo, ejecutado_por_user_id
        )
        values ($1, $2, $3, $4, $5, $6, $7)
        """,
        tenant_id, tarea_id, tipo_evento_map[accion],
        estado_anterior, estado_nuevo, observacion, ejecutado_por_user_id,
    )

    return dict(row)


async def reasignar_tarea(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    tarea_id: UUID,
    usuario_destino_id: UUID | None,
    dependencia_destino_id: UUID | None,
    motivo: str,
    ejecutado_por_user_id: UUID,
) -> dict[str, Any] | None:
    """Reasigna tarea + escribe historial. None si no existe."""
    actual = await conn.fetchrow(
        """
        select asignado_a_user_id, asignado_a_dependencia_id, estado
        from gd.tarea where id = $1 and tenant_id = $2
        """,
        tarea_id, tenant_id,
    )
    if actual is None:
        return None

    row = await conn.fetchrow(
        """
        update gd.tarea
        set asignado_a_user_id = $3,
            asignado_a_dependencia_id = $4,
            asignado_por_user_id = $5,
            fecha_asignacion = now(),
            updated_at = now()
        where id = $2 and tenant_id = $1
        returning id, tenant_id, tipo_tarea, titulo, descripcion,
                  entidad_origen_tipo, entidad_origen_id,
                  asignado_a_user_id, asignado_a_dependencia_id,
                  asignado_por_user_id, fecha_asignacion, fecha_limite,
                  prioridad, estado
        """,
        tenant_id, tarea_id,
        usuario_destino_id, dependencia_destino_id, ejecutado_por_user_id,
    )

    await conn.execute(
        """
        insert into gd.tarea_historial (
            tenant_id, tarea_id, tipo_evento,
            asignado_a_user_id_anterior, asignado_a_user_id_nuevo,
            asignado_a_dependencia_id_anterior, asignado_a_dependencia_id_nuevo,
            motivo, ejecutado_por_user_id
        )
        values ($1, $2, 'reasignada', $3, $4, $5, $6, $7, $8)
        """,
        tenant_id, tarea_id,
        actual['asignado_a_user_id'], usuario_destino_id,
        actual['asignado_a_dependencia_id'], dependencia_destino_id,
        motivo, ejecutado_por_user_id,
    )

    return dict(row)


async def carga_por_usuario_dependencia(
    conn: asyncpg.Connection, *, tenant_id: UUID, dependencia_id: UUID,
) -> list[dict[str, Any]]:
    """KPIs de carga por usuario asignado dentro de una dependencia.

    Agrupa por usuarios cuya dependencia_actual == dependencia_id (consulta
    perfil_usuario) Y tareas asignadas directamente a ellos.
    """
    rows = await conn.fetch(
        """
        select
            t.asignado_a_user_id as user_id,
            count(*) filter (where t.estado = 'pendiente') as pendientes,
            count(*) filter (where t.estado = 'en_proceso') as en_proceso,
            count(*) filter (where t.estado = 'vencida') as vencidas
        from gd.tarea t
        join gd.perfil_usuario p on p.user_id = t.asignado_a_user_id
                                   and p.tenant_id = t.tenant_id
        where t.tenant_id = $1
          and p.dependencia_actual_id = $2
          and t.asignado_a_user_id is not null
        group by t.asignado_a_user_id
        order by pendientes desc
        """,
        tenant_id, dependencia_id,
    )
    return [
        {
            'user_id': r['user_id'],
            'pendientes': int(r['pendientes'] or 0),
            'en_proceso': int(r['en_proceso'] or 0),
            'vencidas': int(r['vencidas'] or 0),
        }
        for r in rows
    ]


__all__ = [
    'ACCION_A_ESTADO',
    'crear_tarea', 'listar_tareas', 'contar_tareas_por_estado',
    'aplicar_accion', 'reasignar_tarea',
    'carga_por_usuario_dependencia',
]
