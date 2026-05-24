"""Services SQL para GD-API-0033 — Terceros."""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg


async def crear_tercero(
    conn: asyncpg.Connection, *, tenant_id: UUID, datos: dict[str, Any],
    created_by_user_id: UUID,
) -> dict[str, Any]:
    """Inserta tercero. Lanza UniqueViolation si duplicado (caller maneja 409)."""
    row = await conn.fetchrow(
        """
        insert into gd.tercero (
            tenant_id, tipo_tercero, tipo_documento, numero_documento,
            nombres_razon_social, correo, telefono, direccion,
            municipio, departamento, pais, created_by_user_id
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
        returning id, tenant_id, tipo_tercero, tipo_documento, numero_documento,
                  nombres_razon_social, correo, telefono, direccion,
                  municipio, departamento, pais, estado
        """,
        tenant_id, datos['tipo_tercero'],
        datos.get('tipo_documento'), datos.get('numero_documento'),
        datos['nombres_razon_social'],
        datos.get('correo'), datos.get('telefono'),
        datos.get('direccion'), datos.get('municipio'),
        datos.get('departamento'), datos.get('pais', 'CO'),
        created_by_user_id,
    )
    return dict(row)


async def obtener_tercero(
    conn: asyncpg.Connection, *, tenant_id: UUID, tercero_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, tenant_id, tipo_tercero, tipo_documento, numero_documento,
               nombres_razon_social, correo, telefono, direccion,
               municipio, departamento, pais, estado
        from gd.tercero
        where id = $1 and tenant_id = $2
        """,
        tercero_id, tenant_id,
    )
    return dict(row) if row else None


async def actualizar_tercero(
    conn: asyncpg.Connection, *, tenant_id: UUID, tercero_id: UUID,
    cambios: dict[str, Any],
) -> dict[str, Any] | None:
    if not cambios:
        return await obtener_tercero(conn, tenant_id=tenant_id, tercero_id=tercero_id)

    set_parts: list[str] = []
    params: list[Any] = [tenant_id, tercero_id]
    for col, val in cambios.items():
        params.append(val)
        set_parts.append(f'{col} = ${len(params)}')

    sql = (
        f"update gd.tercero set {', '.join(set_parts)} "
        'where id = $2 and tenant_id = $1 '
        'returning id, tenant_id, tipo_tercero, tipo_documento, numero_documento, '
        'nombres_razon_social, correo, telefono, direccion, '
        'municipio, departamento, pais, estado'
    )
    row = await conn.fetchrow(sql, *params)
    return dict(row) if row else None


async def buscar_tercero(
    conn: asyncpg.Connection, *, tenant_id: UUID,
    documento: str | None = None, nombre: str | None = None,
    email: str | None = None, limit: int = 10,
) -> dict[str, Any]:
    """Búsqueda de terceros + detección de posibles duplicados.

    `items` = matches estrictos por documento/email exacto.
    `posibles_duplicados` = matches fuzzy por nombre (ts_vector).
    """
    items: list[dict[str, Any]] = []
    duplicados: list[dict[str, Any]] = []

    # Matches exactos.
    if documento:
        rows = await conn.fetch(
            """
            select id, tipo_tercero, tipo_documento, numero_documento,
                   nombres_razon_social, correo
            from gd.tercero
            where tenant_id = $1 and numero_documento = $2
            limit $3
            """,
            tenant_id, documento, limit,
        )
        items.extend(dict(r) for r in rows)

    if email:
        rows = await conn.fetch(
            """
            select id, tipo_tercero, tipo_documento, numero_documento,
                   nombres_razon_social, correo
            from gd.tercero
            where tenant_id = $1 and lower(correo) = lower($2)
            limit $3
            """,
            tenant_id, email, limit,
        )
        for r in rows:
            if not any(i['id'] == r['id'] for i in items):
                items.append(dict(r))

    # Fuzzy nombre (sólo si no se encontró match exacto).
    if nombre:
        rows = await conn.fetch(
            """
            select id, tipo_tercero, tipo_documento, numero_documento,
                   nombres_razon_social, correo
            from gd.tercero
            where tenant_id = $1
              and to_tsvector('spanish', nombres_razon_social) @@ plainto_tsquery('spanish', $2)
            limit $3
            """,
            tenant_id, nombre, limit,
        )
        for r in rows:
            d = dict(r)
            if any(i['id'] == d['id'] for i in items):
                continue
            duplicados.append(d)

    return {'items': items, 'posibles_duplicados': duplicados}


__all__ = [
    'crear_tercero', 'obtener_tercero', 'actualizar_tercero',
    'buscar_tercero',
]
