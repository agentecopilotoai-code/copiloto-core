"""Services SQL para GD-API-0023 — Consecutivos transaccionales radicación."""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg


async def listar_consecutivos(
    conn: asyncpg.Connection, *, tenant_id: UUID,
    vigencia: int | None = None,
) -> list[dict[str, Any]]:
    where_parts = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if vigencia is not None:
        params.append(vigencia)
        where_parts.append(f'vigencia = ${len(params)}')

    rows = await conn.fetch(
        f"""
        select id, tenant_id, vigencia, tipo_radicado, prefijo,
               ultimo_numero, formato, estado
        from gd.consecutivo_radicacion
        where {' and '.join(where_parts)}
        order by vigencia desc, tipo_radicado
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def siguiente_radicado(
    conn: asyncpg.Connection, *, tenant_id: UUID,
    vigencia: int, tipo_radicado: str,
) -> str:
    """Llama la función SQL atómica. Retorna el numero_radicado generado."""
    row = await conn.fetchrow(
        'select gd.siguiente_radicado($1, $2, $3) as numero_radicado',
        tenant_id, vigencia, tipo_radicado,
    )
    if row is None or row['numero_radicado'] is None:
        raise RuntimeError('gd.siguiente_radicado retornó NULL')
    return row['numero_radicado']


__all__ = ['listar_consecutivos', 'siguiente_radicado']
