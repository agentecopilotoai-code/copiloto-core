"""Servicios SQL para GD-API-0012 — Estructura orgánica versionada."""
from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

import asyncpg


# =============================================================================
# Versión de estructura orgánica
# =============================================================================

async def crear_version_estructura(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    numero_version: str,
    descripcion: str | None,
    acto_administrativo: str | None,
    fecha_inicio_vigencia: date,
    created_by_user_id: UUID,
) -> dict[str, Any]:
    """Crea versión en estado 'borrador'. La activación es endpoint separado.

    Clona dependencias de la versión vigente actual (si existe) como punto
    de partida para edición.
    """
    # Buscar versión vigente actual para clonar.
    vigente = await conn.fetchrow(
        """
        select id from gd.version_estructura_organica
        where tenant_id = $1 and estado = 'vigente'
        """,
        tenant_id,
    )

    row = await conn.fetchrow(
        """
        insert into gd.version_estructura_organica (
            tenant_id, numero_version, descripcion, acto_administrativo,
            fecha_inicio_vigencia, estado, created_by_user_id
        ) values ($1, $2, $3, $4, $5, 'borrador', $6)
        returning id, tenant_id, numero_version, descripcion,
                  acto_administrativo, fecha_inicio_vigencia, fecha_fin_vigencia,
                  estado
        """,
        tenant_id, numero_version, descripcion, acto_administrativo,
        fecha_inicio_vigencia, created_by_user_id,
    )
    nueva = dict(row)

    clonadas = 0
    if vigente is not None:
        # Clonar dependencias de la versión vigente a la nueva.
        clon_rows = await conn.fetch(
            """
            insert into gd.dependencia (
                tenant_id, codigo_organico, nombre, dependencia_padre_id,
                version_estructura_id, estado, fecha_inicio_vigencia
            )
            select
                d.tenant_id, d.codigo_organico, d.nombre, d.dependencia_padre_id,
                $1, 'activa', $2
            from gd.dependencia d
            where d.tenant_id = $3 and d.version_estructura_id = $4
              and d.estado = 'activa'
            returning id
            """,
            nueva['id'], fecha_inicio_vigencia, tenant_id, vigente['id'],
        )
        clonadas = len(clon_rows)

    nueva['dependencias_clonadas'] = clonadas
    return nueva


async def obtener_version_vigente(
    conn: asyncpg.Connection, *, tenant_id: UUID
) -> dict[str, Any] | None:
    """Retorna la versión vigente actual + count de dependencias."""
    row = await conn.fetchrow(
        """
        select
            v.id as version_estructura_id,
            v.numero_version,
            v.fecha_inicio_vigencia,
            (select count(*) from gd.dependencia d
             where d.version_estructura_id = v.id and d.estado = 'activa'
            ) as dependencias_count
        from gd.version_estructura_organica v
        where v.tenant_id = $1 and v.estado = 'vigente'
        """,
        tenant_id,
    )
    return dict(row) if row else None


async def obtener_version_en_fecha(
    conn: asyncpg.Connection, *, tenant_id: UUID, fecha: date
) -> dict[str, Any] | None:
    """Versión que estaba vigente en una fecha histórica."""
    row = await conn.fetchrow(
        """
        select
            v.id as version_estructura_id,
            v.numero_version,
            v.fecha_inicio_vigencia,
            (select count(*) from gd.dependencia d
             where d.version_estructura_id = v.id
            ) as dependencias_count
        from gd.version_estructura_organica v
        where v.tenant_id = $1
          and v.fecha_inicio_vigencia <= $2
          and (v.fecha_fin_vigencia is null or v.fecha_fin_vigencia >= $2)
        order by v.fecha_inicio_vigencia desc
        limit 1
        """,
        tenant_id, fecha,
    )
    return dict(row) if row else None


# =============================================================================
# Dependencia
# =============================================================================

async def crear_dependencia(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    codigo_organico: str,
    nombre: str,
    dependencia_padre_id: UUID | None,
    version_estructura_id: UUID,
    fecha_inicio_vigencia: date,
    created_by_user_id: UUID,
) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        insert into gd.dependencia (
            tenant_id, codigo_organico, nombre, dependencia_padre_id,
            version_estructura_id, fecha_inicio_vigencia, estado, created_by_user_id
        ) values ($1, $2, $3, $4, $5, $6, 'activa', $7)
        returning id, tenant_id, codigo_organico, nombre, dependencia_padre_id,
                  version_estructura_id, estado, fecha_inicio_vigencia, fecha_fin_vigencia
        """,
        tenant_id, codigo_organico, nombre, dependencia_padre_id,
        version_estructura_id, fecha_inicio_vigencia, created_by_user_id,
    )
    return dict(row)


async def listar_dependencias(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    estado: str | None = None,
    version_estructura_id: UUID | None = None,
    q: str | None = None,
) -> list[dict[str, Any]]:
    where_parts: list[str] = ['tenant_id = $1']
    params: list[Any] = [tenant_id]

    if estado:
        params.append(estado)
        where_parts.append(f'estado = ${len(params)}')

    if version_estructura_id:
        params.append(version_estructura_id)
        where_parts.append(f'version_estructura_id = ${len(params)}')
    else:
        # Default: filtrar solo a la versión vigente.
        where_parts.append(
            'version_estructura_id = ('
            '  select id from gd.version_estructura_organica'
            "  where tenant_id = $1 and estado = 'vigente'"
            ')'
        )

    if q:
        params.append(f'%{q}%')
        where_parts.append(
            f'(nombre ilike ${len(params)} or codigo_organico ilike ${len(params)})'
        )

    rows = await conn.fetch(
        f"""
        select id, tenant_id, codigo_organico, nombre, dependencia_padre_id,
               version_estructura_id, estado, fecha_inicio_vigencia, fecha_fin_vigencia
        from gd.dependencia
        where {' and '.join(where_parts)}
        order by codigo_organico
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def patch_dependencia(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    dependencia_id: UUID,
    cambios: dict[str, Any],
) -> dict[str, Any] | None:
    """PATCH solo permite cambios menores. Verifica que la dependencia no
    tenga 'actuaciones' (radicados) — por ahora ese check es stub porque
    `gd.radicado` no existe aún. Cuando exista (EP-004), agregar verificación.
    """
    if not cambios:
        row = await conn.fetchrow(
            'select * from gd.dependencia where id = $1 and tenant_id = $2',
            dependencia_id, tenant_id,
        )
        return dict(row) if row else None

    set_parts: list[str] = []
    params: list[Any] = [tenant_id, dependencia_id]
    for col, val in cambios.items():
        params.append(val)
        set_parts.append(f'{col} = ${len(params)}')

    sql = (
        f"update gd.dependencia set {', '.join(set_parts)} "
        'where id = $2 and tenant_id = $1 '
        'returning id, tenant_id, codigo_organico, nombre, dependencia_padre_id, '
        'version_estructura_id, estado, fecha_inicio_vigencia, fecha_fin_vigencia'
    )
    row = await conn.fetchrow(sql, *params)
    return dict(row) if row else None


async def cerrar_vigencia_dependencia(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    dependencia_id: UUID,
    fecha_fin: date,
    motivo: str,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        update gd.dependencia
        set estado = 'cerrada',
            fecha_fin_vigencia = $3,
            motivo_cierre = $4
        where id = $2 and tenant_id = $1 and estado = 'activa'
        returning id, tenant_id, codigo_organico, nombre, dependencia_padre_id,
                  version_estructura_id, estado, fecha_inicio_vigencia, fecha_fin_vigencia
        """,
        tenant_id, dependencia_id, fecha_fin, motivo,
    )
    return dict(row) if row else None


def construir_jerarquia(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convierte lista plana de dependencias en árbol jerárquico.

    Cada nodo tiene 'hijos' (lista). Las raíces son las que tienen
    `dependencia_padre_id` IS NULL.
    """
    # Index por id, agregar campo 'hijos'.
    index: dict[UUID, dict[str, Any]] = {}
    for item in items:
        index[item['id']] = {
            'id': item['id'],
            'codigo_organico': item['codigo_organico'],
            'nombre': item['nombre'],
            'hijos': [],
        }

    # Construir árbol.
    raiz: list[dict[str, Any]] = []
    for item in items:
        nodo = index[item['id']]
        padre_id = item.get('dependencia_padre_id')
        if padre_id is None or padre_id not in index:
            raiz.append(nodo)
        else:
            index[padre_id]['hijos'].append(nodo)

    return raiz


__all__ = [
    'crear_version_estructura',
    'obtener_version_vigente',
    'obtener_version_en_fecha',
    'crear_dependencia',
    'listar_dependencias',
    'patch_dependencia',
    'cerrar_vigencia_dependencia',
    'construir_jerarquia',
]
