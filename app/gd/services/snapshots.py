"""GD-API-0009 — Wrapper Python para `gd.capturar_snapshot_actuacion()` SQL.

Uso típico desde un handler::

    snapshot = await capturar_snapshot(conn, user_id=request.state.user_id)
    await emit_gd_event(
        conn, ...,
        actor_snapshot=snapshot,
        ...
    )
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg


async def capturar_snapshot(
    conn: asyncpg.Connection, *, user_id: UUID
) -> dict[str, Any]:
    """Llama a la función SQL `gd.capturar_snapshot_actuacion`.

    Retorna dict ya parseado desde jsonb. La función SQL lanza P0002 si el
    usuario no existe.
    """
    row = await conn.fetchrow(
        'select gd.capturar_snapshot_actuacion($1) as snapshot', user_id
    )
    if row is None or row['snapshot'] is None:
        raise ValueError(f'snapshot vacío para user_id={user_id}')
    snapshot = row['snapshot']
    # asyncpg puede devolver jsonb como str o dict según versión; normalizamos.
    if isinstance(snapshot, str):
        import json
        snapshot = json.loads(snapshot)
    return snapshot


__all__ = ['capturar_snapshot']
