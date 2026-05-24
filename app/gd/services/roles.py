"""Servicios SQL para GD-API-0004 — CRUD de roles GD y matriz rol↔permiso."""
from __future__ import annotations

from typing import Any

import asyncpg


async def crear_rol(
    conn: asyncpg.Connection,
    *,
    codigo: str,
    nombre: str,
    descripcion: str | None,
) -> dict[str, Any] | None:
    """Crea rol custom (es_sistema=false). Retorna None si ya existe."""
    row = await conn.fetchrow(
        """
        insert into gd.rol (codigo, nombre, descripcion, es_sistema, estado)
        values ($1, $2, $3, false, 'activo')
        on conflict (codigo) do nothing
        returning codigo, nombre, descripcion, es_sistema, estado
        """,
        codigo, nombre, descripcion,
    )
    if row is None:
        return None
    result = dict(row)
    result['permisos_count'] = 0
    return result


async def listar_roles(
    conn: asyncpg.Connection,
    *,
    estado: str | None = None,
) -> list[dict[str, Any]]:
    """Lista catálogo de roles (es global, sin RLS)."""
    if estado:
        rows = await conn.fetch(
            """
            select
                r.codigo, r.nombre, r.descripcion, r.es_sistema, r.estado,
                (select count(*) from gd.rol_permiso rp
                 where rp.rol_codigo = r.codigo and rp.estado = 'activo'
                ) as permisos_count
            from gd.rol r
            where r.estado = $1
            order by r.es_sistema desc, r.codigo
            """,
            estado,
        )
    else:
        rows = await conn.fetch(
            """
            select
                r.codigo, r.nombre, r.descripcion, r.es_sistema, r.estado,
                (select count(*) from gd.rol_permiso rp
                 where rp.rol_codigo = r.codigo and rp.estado = 'activo'
                ) as permisos_count
            from gd.rol r
            order by r.es_sistema desc, r.codigo
            """,
        )
    return [dict(r) for r in rows]


async def obtener_rol(conn: asyncpg.Connection, *, codigo: str) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select
            r.codigo, r.nombre, r.descripcion, r.es_sistema, r.estado,
            (select count(*) from gd.rol_permiso rp
             where rp.rol_codigo = r.codigo and rp.estado = 'activo'
            ) as permisos_count
        from gd.rol r
        where r.codigo = $1
        """,
        codigo,
    )
    return dict(row) if row else None


async def actualizar_rol(
    conn: asyncpg.Connection,
    *,
    codigo: str,
    cambios: dict[str, Any],
) -> dict[str, Any] | None:
    if not cambios:
        return await obtener_rol(conn, codigo=codigo)

    set_parts: list[str] = []
    params: list[Any] = [codigo]
    for col, val in cambios.items():
        params.append(val)
        set_parts.append(f'{col} = ${len(params)}')

    sql = (
        f"update gd.rol set {', '.join(set_parts)} where codigo = $1 "
        "returning codigo, nombre, descripcion, es_sistema, estado"
    )
    row = await conn.fetchrow(sql, *params)
    if row is None:
        return None
    result = dict(row)
    # Re-leer permisos_count.
    count_row = await conn.fetchrow(
        "select count(*) as c from gd.rol_permiso where rol_codigo = $1 and estado = 'activo'",
        codigo,
    )
    result['permisos_count'] = int(count_row['c']) if count_row else 0
    return result


async def contar_asignaciones_activas(
    conn: asyncpg.Connection, *, rol_codigo: str
) -> int:
    """Cuenta asignaciones activas. Usado por 'inactivar rol' para detectar role_in_use."""
    row = await conn.fetchrow(
        """
        select count(*) as c
        from gd.asignacion_alcance
        where rol_codigo = $1
          and estado = 'activa'
          and (fecha_fin is null or fecha_fin >= current_date)
        """,
        rol_codigo,
    )
    return int(row['c']) if row else 0


async def inactivar_rol(
    conn: asyncpg.Connection, *, codigo: str
) -> dict[str, Any] | None:
    """Marca rol como inactivo. Caller debe haber verificado contar_asignaciones_activas==0."""
    row = await conn.fetchrow(
        """
        update gd.rol
        set estado = 'inactivo'
        where codigo = $1 and estado = 'activo'
        returning codigo, nombre, descripcion, es_sistema, estado
        """,
        codigo,
    )
    if row is None:
        return None
    result = dict(row)
    result['permisos_count'] = 0
    return result


async def agregar_permiso_a_rol(
    conn: asyncpg.Connection,
    *,
    rol_codigo: str,
    permiso_codigo: str,
    alcance_default: str,
) -> dict[str, Any] | None:
    """Inserta entry en gd.rol_permiso. None si la entry ya existe."""
    row = await conn.fetchrow(
        """
        insert into gd.rol_permiso (rol_codigo, permiso_codigo, alcance_default, estado)
        values ($1, $2, $3, 'activo')
        on conflict (rol_codigo, permiso_codigo) do nothing
        returning rol_codigo, permiso_codigo, alcance_default, created_at as agregado_en
        """,
        rol_codigo, permiso_codigo, alcance_default,
    )
    return dict(row) if row else None


async def quitar_permiso_de_rol(
    conn: asyncpg.Connection,
    *,
    rol_codigo: str,
    permiso_codigo: str,
) -> bool:
    """Elimina entry de gd.rol_permiso (revoca de matriz, NO borra el permiso)."""
    result = await conn.execute(
        """
        delete from gd.rol_permiso
        where rol_codigo = $1 and permiso_codigo = $2
        """,
        rol_codigo, permiso_codigo,
    )
    # asyncpg.execute devuelve "DELETE n" — parseamos n.
    return result.startswith('DELETE') and not result.endswith(' 0')


async def listar_permisos(
    conn: asyncpg.Connection,
    *,
    modulo: str | None = None,
    estado: str | None = None,
) -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[Any] = []
    if modulo:
        params.append(modulo)
        where.append(f'modulo = ${len(params)}')
    if estado:
        params.append(estado)
        where.append(f'estado = ${len(params)}')

    where_sql = f'where {" and ".join(where)}' if where else ''
    rows = await conn.fetch(
        f'select codigo, nombre, modulo, descripcion, es_critico, estado '
        f'from gd.permiso {where_sql} order by modulo, codigo',
        *params,
    )
    return [dict(r) for r in rows]


__all__ = [
    'crear_rol',
    'listar_roles',
    'obtener_rol',
    'actualizar_rol',
    'contar_asignaciones_activas',
    'inactivar_rol',
    'agregar_permiso_a_rol',
    'quitar_permiso_de_rol',
    'listar_permisos',
]
