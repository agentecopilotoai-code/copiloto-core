"""Servicios SQL para GD-API-0005 — Asignación de rol con alcance.

D9: NO toca `app.user_tenant_roles`. Solo inserta/cierra en `gd.asignacion_alcance`.
"""
from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import asyncpg


async def asignar_rol(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    user_id: UUID,
    rol_codigo: str,
    dependencia_id: UUID | None,
    alcance: str,
    fecha_inicio: date,
    fecha_fin: date | None,
    motivo: str,
    asignado_por_user_id: UUID,
) -> dict[str, Any]:
    """Inserta asignación en gd.asignacion_alcance."""
    row = await conn.fetchrow(
        """
        insert into gd.asignacion_alcance (
            tenant_id, user_id, rol_codigo, dependencia_id, alcance,
            fecha_inicio, fecha_fin, motivo, asignado_por_user_id, estado
        ) values ($1, $2, $3, $4, $5, $6, $7, $8, $9, 'activa')
        returning
            id as asignacion_alcance_id, user_id, rol_codigo, dependencia_id,
            alcance, fecha_inicio, fecha_fin, estado, asignado_por_user_id, motivo
        """,
        tenant_id, user_id, rol_codigo, dependencia_id, alcance,
        fecha_inicio, fecha_fin, motivo, asignado_por_user_id,
    )
    return dict(row)


async def cerrar_asignacion(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    user_id: UUID,
    asignacion_alcance_id: UUID,
    motivo: str,
    cerrado_por_user_id: UUID,
) -> dict[str, Any] | None:
    """Marca la asignación como cerrada (estado='cerrada', fecha_fin=hoy)."""
    row = await conn.fetchrow(
        """
        update gd.asignacion_alcance
        set estado = 'cerrada',
            fecha_fin = current_date,
            motivo_cierre = $4,
            cerrado_por_user_id = $5,
            cerrado_en = now()
        where id = $3
          and tenant_id = $1
          and user_id = $2
          and estado = 'activa'
        returning id as asignacion_alcance_id, cerrado_en as fecha_fin, estado
        """,
        tenant_id, user_id, asignacion_alcance_id, motivo, cerrado_por_user_id,
    )
    return dict(row) if row else None


async def listar_roles_usuario(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    user_id: UUID,
    incluir_historicas: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """Devuelve {'vigentes': [...], 'historicas': [...]}.

    Vigentes = estado='activa' y (fecha_fin IS NULL OR fecha_fin >= today).
    Históricas = cualquier otra (solo si incluir_historicas=True).
    """
    rows = await conn.fetch(
        """
        select
            aa.id as asignacion_alcance_id,
            aa.user_id, aa.rol_codigo, r.nombre as rol_nombre,
            aa.dependencia_id, aa.alcance,
            aa.fecha_inicio, aa.fecha_fin, aa.estado,
            aa.asignado_por_user_id, aa.motivo,
            (aa.estado = 'activa'
             and (aa.fecha_fin is null or aa.fecha_fin >= current_date)
            ) as vigente
        from gd.asignacion_alcance aa
        join gd.rol r on r.codigo = aa.rol_codigo
        where aa.tenant_id = $1 and aa.user_id = $2
        order by aa.fecha_inicio desc
        """,
        tenant_id, user_id,
    )
    vigentes: list[dict[str, Any]] = []
    historicas: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        vigente = d.pop('vigente')
        if vigente:
            vigentes.append(d)
        elif incluir_historicas:
            historicas.append(d)
    return {'vigentes': vigentes, 'historicas': historicas}


__all__ = [
    'asignar_rol',
    'cerrar_asignacion',
    'listar_roles_usuario',
]
