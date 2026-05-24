"""Services SQL para GD-API-0015 — Parámetros institucionales versionados."""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg


async def listar_parametros_vigentes(
    conn: asyncpg.Connection, *, tenant_id: UUID,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select id, clave, valor, tipo, descripcion,
               vigente_desde, vigente_hasta, estado
        from gd.parametro
        where tenant_id = $1 and estado = 'activo'
        order by clave
        """,
        tenant_id,
    )
    return [dict(r) for r in rows]


async def obtener_parametro(
    conn: asyncpg.Connection, *, tenant_id: UUID, clave: str,
) -> dict[str, Any] | None:
    """Devuelve {vigente, historial[]} o None si la clave nunca existió."""
    rows = await conn.fetch(
        """
        select id, clave, valor, tipo, descripcion,
               vigente_desde, vigente_hasta, estado
        from gd.parametro
        where tenant_id = $1 and clave = $2
        order by vigente_desde desc
        """,
        tenant_id, clave,
    )
    if not rows:
        return None

    historial = [dict(r) for r in rows]
    vigente = next((r for r in historial if r['estado'] == 'activo'), None)
    return {'clave': clave, 'vigente': vigente, 'historial': historial}


async def upsert_parametros(
    conn: asyncpg.Connection, *, tenant_id: UUID,
    parametros: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Versionamiento RNF-009: por cada parámetro, marca el activo como
    reemplazado e inserta uno nuevo. Idempotente: si el valor no cambia,
    NO crea fila nueva.
    """
    resultados: list[dict[str, Any]] = []
    for p in parametros:
        # Buscar el activo actual.
        actual = await conn.fetchrow(
            """
            select id, valor, tipo, descripcion
            from gd.parametro
            where tenant_id = $1 and clave = $2 and estado = 'activo'
            """,
            tenant_id, p['clave'],
        )
        nuevo_valor = p['valor']
        # Sin cambio → return actual.
        if actual and actual['valor'] == nuevo_valor and actual['tipo'] == p.get('tipo', 'string'):
            # Reusar el activo, no crear nueva fila.
            row_actual = await conn.fetchrow(
                """
                select id, clave, valor, tipo, descripcion,
                       vigente_desde, vigente_hasta, estado
                from gd.parametro where id = $1
                """,
                actual['id'],
            )
            resultados.append(dict(row_actual))
            continue

        # Marcar activo como reemplazado.
        if actual:
            await conn.execute(
                """
                update gd.parametro
                set estado = 'reemplazado', vigente_hasta = now()
                where id = $1
                """,
                actual['id'],
            )

        # Insertar nueva fila activa.
        row_nuevo = await conn.fetchrow(
            """
            insert into gd.parametro (
                tenant_id, clave, valor, tipo, descripcion, estado
            )
            values ($1, $2, $3, $4, $5, 'activo')
            returning id, clave, valor, tipo, descripcion,
                      vigente_desde, vigente_hasta, estado
            """,
            tenant_id, p['clave'], nuevo_valor,
            p.get('tipo', 'string'),
            p.get('descripcion'),
        )
        resultados.append(dict(row_nuevo))

    return resultados


__all__ = [
    'listar_parametros_vigentes',
    'obtener_parametro',
    'upsert_parametros',
]
