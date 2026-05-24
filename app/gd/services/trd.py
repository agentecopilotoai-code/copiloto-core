"""Services para EP-015 TRD/TVD (bloque 16).

Cubre:
- CRUD versión TRD / activar (cerrar anterior + activar nueva)
- Series / subseries / tipos documentales
- CRUD versión TVD (mismo patrón)
- Asociación dependencia ↔ código documental
- Clasificación documental polimórfica + historial
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg


# =============================================================================
# Version TRD
# =============================================================================

async def crear_version_trd(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    codigo: str,
    nombre: str,
    descripcion: str | None,
    fecha_aprobacion=None,
    fecha_inicio_vigencia=None,
    fecha_fin_vigencia=None,
    created_by_user_id: UUID,
) -> dict[str, Any]:
    try:
        row = await conn.fetchrow(
            """
            insert into gd.version_trd (
                tenant_id, codigo, nombre, descripcion,
                fecha_aprobacion, fecha_inicio_vigencia, fecha_fin_vigencia,
                estado, created_by_user_id
            )
            values ($1, $2, $3, $4, $5, $6, $7, 'borrador', $8)
            returning id, codigo, nombre, descripcion, fecha_aprobacion,
                      fecha_inicio_vigencia, fecha_fin_vigencia, estado,
                      created_by_user_id, created_at, updated_at
            """,
            tenant_id, codigo, nombre, descripcion,
            fecha_aprobacion, fecha_inicio_vigencia, fecha_fin_vigencia,
            created_by_user_id,
        )
    except asyncpg.UniqueViolationError as e:
        raise ValueError('codigo_ya_existe') from e
    return dict(row)


async def obtener_version_trd(
    conn: asyncpg.Connection, *, tenant_id: UUID, version_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, codigo, nombre, descripcion, fecha_aprobacion,
               fecha_inicio_vigencia, fecha_fin_vigencia, estado,
               created_by_user_id, created_at, updated_at
        from gd.version_trd where id = $1 and tenant_id = $2
        """,
        version_id, tenant_id,
    )
    return dict(row) if row else None


async def listar_versiones_trd(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    estado: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if estado:
        params.append(estado)
        where.append(f'estado = ${len(params)}')
    params.append(limit)
    rows = await conn.fetch(
        f"""
        select id, codigo, nombre, descripcion, fecha_aprobacion,
               fecha_inicio_vigencia, fecha_fin_vigencia, estado,
               created_by_user_id, created_at, updated_at
        from gd.version_trd
        where {' and '.join(where)}
        order by created_at desc
        limit ${len(params)}
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def activar_version_trd(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    version_id: UUID,
) -> dict[str, Any] | None:
    """Activa una versión TRD (borrador → vigente); la anterior vigente
    pasa a histórica. Misma transacción.
    """
    target = await conn.fetchrow(
        'select estado from gd.version_trd where id = $1 and tenant_id = $2',
        version_id, tenant_id,
    )
    if target is None:
        return None
    if target['estado'] != 'borrador':
        raise ValueError(f"estado_invalido:{target['estado']}")

    # Cerrar vigente actual (si hay).
    await conn.execute(
        """
        update gd.version_trd
        set estado = 'historica',
            fecha_fin_vigencia = coalesce(fecha_fin_vigencia, current_date)
        where tenant_id = $1 and estado = 'vigente'
        """,
        tenant_id,
    )
    # Activar nueva.
    row = await conn.fetchrow(
        """
        update gd.version_trd
        set estado = 'vigente',
            fecha_inicio_vigencia = coalesce(fecha_inicio_vigencia, current_date)
        where id = $1 and tenant_id = $2
        returning id, codigo, nombre, descripcion, fecha_aprobacion,
                  fecha_inicio_vigencia, fecha_fin_vigencia, estado,
                  created_by_user_id, created_at, updated_at
        """,
        version_id, tenant_id,
    )
    return dict(row)


# =============================================================================
# Series / subseries / tipos
# =============================================================================

async def crear_serie(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    version_trd_id: UUID,
    codigo: str,
    nombre: str,
    descripcion: str | None,
) -> dict[str, Any]:
    # Validar version_trd existe + activa o borrador.
    vt = await conn.fetchrow(
        'select estado from gd.version_trd where id = $1 and tenant_id = $2',
        version_trd_id, tenant_id,
    )
    if vt is None:
        raise LookupError('version_trd_no_existe')

    try:
        row = await conn.fetchrow(
            """
            insert into gd.serie_documental (
                tenant_id, version_trd_id, codigo, nombre, descripcion, estado
            )
            values ($1, $2, $3, $4, $5, 'activa')
            returning id, version_trd_id, codigo, nombre, descripcion,
                      estado, created_at
            """,
            tenant_id, version_trd_id, codigo, nombre, descripcion,
        )
    except asyncpg.UniqueViolationError as e:
        raise ValueError('serie_codigo_duplicado') from e
    return dict(row)


async def listar_series(
    conn: asyncpg.Connection, *, tenant_id: UUID, version_trd_id: UUID,
    estado: str | None = None,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1', 'version_trd_id = $2']
    params: list[Any] = [tenant_id, version_trd_id]
    if estado:
        params.append(estado)
        where.append(f'estado = ${len(params)}')
    rows = await conn.fetch(
        f"""
        select id, version_trd_id, codigo, nombre, descripcion,
               estado, created_at
        from gd.serie_documental
        where {' and '.join(where)}
        order by codigo
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def crear_subserie(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    serie_id: UUID,
    codigo: str,
    nombre: str,
    descripcion: str | None,
    tiempo_archivo_gestion_anos: int | None,
    tiempo_archivo_central_anos: int | None,
    disposicion_final: str | None,
) -> dict[str, Any]:
    serie = await conn.fetchval(
        'select 1 from gd.serie_documental where id = $1 and tenant_id = $2',
        serie_id, tenant_id,
    )
    if not serie:
        raise LookupError('serie_no_existe')

    try:
        row = await conn.fetchrow(
            """
            insert into gd.subserie_documental (
                tenant_id, serie_id, codigo, nombre, descripcion,
                tiempo_archivo_gestion_anos, tiempo_archivo_central_anos,
                disposicion_final, estado
            )
            values ($1, $2, $3, $4, $5, $6, $7, $8, 'activa')
            returning id, serie_id, codigo, nombre, descripcion,
                      tiempo_archivo_gestion_anos, tiempo_archivo_central_anos,
                      disposicion_final, estado, created_at
            """,
            tenant_id, serie_id, codigo, nombre, descripcion,
            tiempo_archivo_gestion_anos, tiempo_archivo_central_anos,
            disposicion_final,
        )
    except asyncpg.UniqueViolationError as e:
        raise ValueError('subserie_codigo_duplicado') from e
    return dict(row)


async def listar_subseries(
    conn: asyncpg.Connection, *, tenant_id: UUID, serie_id: UUID,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select id, serie_id, codigo, nombre, descripcion,
               tiempo_archivo_gestion_anos, tiempo_archivo_central_anos,
               disposicion_final, estado, created_at
        from gd.subserie_documental
        where tenant_id = $1 and serie_id = $2
        order by codigo
        """,
        tenant_id, serie_id,
    )
    return [dict(r) for r in rows]


async def crear_tipo_documental(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    subserie_id: UUID,
    codigo: str,
    nombre: str,
    descripcion: str | None,
) -> dict[str, Any]:
    sub = await conn.fetchval(
        'select 1 from gd.subserie_documental where id = $1 and tenant_id = $2',
        subserie_id, tenant_id,
    )
    if not sub:
        raise LookupError('subserie_no_existe')

    try:
        row = await conn.fetchrow(
            """
            insert into gd.tipo_documental (
                tenant_id, subserie_id, codigo, nombre, descripcion, estado
            )
            values ($1, $2, $3, $4, $5, 'activo')
            returning id, subserie_id, codigo, nombre, descripcion,
                      estado, created_at
            """,
            tenant_id, subserie_id, codigo, nombre, descripcion,
        )
    except asyncpg.UniqueViolationError as e:
        raise ValueError('tipo_doc_codigo_duplicado') from e
    return dict(row)


async def listar_tipos_documentales(
    conn: asyncpg.Connection, *, tenant_id: UUID, subserie_id: UUID,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select id, subserie_id, codigo, nombre, descripcion, estado, created_at
        from gd.tipo_documental
        where tenant_id = $1 and subserie_id = $2
        order by codigo
        """,
        tenant_id, subserie_id,
    )
    return [dict(r) for r in rows]


# =============================================================================
# Version TVD
# =============================================================================

async def crear_version_tvd(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    codigo: str,
    nombre: str,
    descripcion: str | None,
    version_trd_id: UUID | None,
    fecha_aprobacion=None,
    fecha_inicio_vigencia=None,
    fecha_fin_vigencia=None,
    created_by_user_id: UUID,
) -> dict[str, Any]:
    try:
        row = await conn.fetchrow(
            """
            insert into gd.version_tvd (
                tenant_id, codigo, nombre, descripcion, version_trd_id,
                fecha_aprobacion, fecha_inicio_vigencia, fecha_fin_vigencia,
                estado, created_by_user_id
            )
            values ($1, $2, $3, $4, $5, $6, $7, $8, 'borrador', $9)
            returning id, codigo, nombre, descripcion, version_trd_id,
                      fecha_aprobacion, fecha_inicio_vigencia,
                      fecha_fin_vigencia, estado, created_by_user_id,
                      created_at, updated_at
            """,
            tenant_id, codigo, nombre, descripcion, version_trd_id,
            fecha_aprobacion, fecha_inicio_vigencia, fecha_fin_vigencia,
            created_by_user_id,
        )
    except asyncpg.UniqueViolationError as e:
        raise ValueError('codigo_tvd_ya_existe') from e
    return dict(row)


async def activar_version_tvd(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    version_id: UUID,
) -> dict[str, Any] | None:
    target = await conn.fetchrow(
        'select estado from gd.version_tvd where id = $1 and tenant_id = $2',
        version_id, tenant_id,
    )
    if target is None:
        return None
    if target['estado'] != 'borrador':
        raise ValueError(f"estado_invalido:{target['estado']}")

    await conn.execute(
        """
        update gd.version_tvd
        set estado = 'historica',
            fecha_fin_vigencia = coalesce(fecha_fin_vigencia, current_date)
        where tenant_id = $1 and estado = 'vigente'
        """,
        tenant_id,
    )
    row = await conn.fetchrow(
        """
        update gd.version_tvd
        set estado = 'vigente',
            fecha_inicio_vigencia = coalesce(fecha_inicio_vigencia, current_date)
        where id = $1 and tenant_id = $2
        returning id, codigo, nombre, descripcion, version_trd_id,
                  fecha_aprobacion, fecha_inicio_vigencia,
                  fecha_fin_vigencia, estado, created_by_user_id,
                  created_at, updated_at
        """,
        version_id, tenant_id,
    )
    return dict(row)


async def listar_versiones_tvd(
    conn: asyncpg.Connection, *, tenant_id: UUID,
    estado: str | None = None, limit: int = 50,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if estado:
        params.append(estado)
        where.append(f'estado = ${len(params)}')
    params.append(limit)
    rows = await conn.fetch(
        f"""
        select id, codigo, nombre, descripcion, version_trd_id,
               fecha_aprobacion, fecha_inicio_vigencia, fecha_fin_vigencia,
               estado, created_by_user_id, created_at, updated_at
        from gd.version_tvd
        where {' and '.join(where)}
        order by created_at desc
        limit ${len(params)}
        """,
        *params,
    )
    return [dict(r) for r in rows]


# =============================================================================
# Asociación dependencia ↔ código documental
# =============================================================================

async def asociar_dep_codigo(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    dependencia_id: UUID,
    version_trd_id: UUID,
    serie_id: UUID | None,
    subserie_id: UUID | None,
    creado_por_user_id: UUID,
) -> dict[str, Any]:
    try:
        row = await conn.fetchrow(
            """
            insert into gd.dependencia_codigo_documental (
                tenant_id, dependencia_id, version_trd_id,
                serie_id, subserie_id, creado_por_user_id
            )
            values ($1, $2, $3, $4, $5, $6)
            returning id, dependencia_id, version_trd_id, serie_id,
                      subserie_id, creado_por_user_id, created_at
            """,
            tenant_id, dependencia_id, version_trd_id,
            serie_id, subserie_id, creado_por_user_id,
        )
    except asyncpg.UniqueViolationError as e:
        raise ValueError('asociacion_ya_existe') from e
    return dict(row)


async def listar_dep_codigos(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    dependencia_id: UUID | None = None,
    version_trd_id: UUID | None = None,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if dependencia_id:
        params.append(dependencia_id)
        where.append(f'dependencia_id = ${len(params)}')
    if version_trd_id:
        params.append(version_trd_id)
        where.append(f'version_trd_id = ${len(params)}')
    rows = await conn.fetch(
        f"""
        select id, dependencia_id, version_trd_id, serie_id,
               subserie_id, creado_por_user_id, created_at
        from gd.dependencia_codigo_documental
        where {' and '.join(where)}
        order by created_at desc
        """,
        *params,
    )
    return [dict(r) for r in rows]


# =============================================================================
# Clasificación documental (GD-API-0098/0099)
# =============================================================================

async def clasificar(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    entidad_tipo: str,
    entidad_id: UUID,
    version_trd_id: UUID,
    serie_id: UUID | None,
    subserie_id: UUID | None,
    tipo_documental_id: UUID | None,
    justificacion: str | None,
    clasificado_por_user_id: UUID,
) -> dict[str, Any]:
    """Crea nueva clasificación. Si ya existe una vigente para esa entidad,
    la marca como 'reemplazada' y apunta `reemplazada_por_id` a la nueva.
    """
    # Validar version_trd existe + vigente o histórica.
    vt = await conn.fetchrow(
        'select estado from gd.version_trd where id = $1 and tenant_id = $2',
        version_trd_id, tenant_id,
    )
    if vt is None:
        raise LookupError('version_trd_no_existe')

    # Buscar vigente existente.
    vigente_id = await conn.fetchval(
        """
        select id from gd.clasificacion_documental
        where tenant_id = $1 and entidad_tipo = $2 and entidad_id = $3
          and estado = 'vigente'
        """,
        tenant_id, entidad_tipo, entidad_id,
    )

    # Si hay vigente, marcarla reemplazada PRIMERO (libera índice único parcial).
    if vigente_id is not None:
        await conn.execute(
            """
            update gd.clasificacion_documental
            set estado = 'reemplazada'
            where id = $1
            """,
            vigente_id,
        )

    # Insertar nueva vigente.
    row = await conn.fetchrow(
        """
        insert into gd.clasificacion_documental (
            tenant_id, entidad_tipo, entidad_id, version_trd_id,
            serie_id, subserie_id, tipo_documental_id,
            justificacion, estado, clasificado_por_user_id
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, 'vigente', $9)
        returning id, entidad_tipo, entidad_id, version_trd_id, serie_id,
                  subserie_id, tipo_documental_id, justificacion,
                  estado, clasificado_por_user_id, fecha_clasificacion,
                  reemplazada_por_id, created_at
        """,
        tenant_id, entidad_tipo, entidad_id, version_trd_id,
        serie_id, subserie_id, tipo_documental_id,
        justificacion, clasificado_por_user_id,
    )
    nueva = dict(row)

    # Si había vigente, apuntarla a la nueva.
    if vigente_id is not None:
        await conn.execute(
            "update gd.clasificacion_documental set reemplazada_por_id = $2 "
            "where id = $1",
            vigente_id, nueva['id'],
        )

    return nueva


async def obtener_vigente(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    entidad_tipo: str,
    entidad_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, entidad_tipo, entidad_id, version_trd_id, serie_id,
               subserie_id, tipo_documental_id, justificacion,
               estado, clasificado_por_user_id, fecha_clasificacion,
               reemplazada_por_id, created_at
        from gd.clasificacion_documental
        where tenant_id = $1 and entidad_tipo = $2 and entidad_id = $3
          and estado = 'vigente'
        """,
        tenant_id, entidad_tipo, entidad_id,
    )
    return dict(row) if row else None


async def historial_clasificacion(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    entidad_tipo: str,
    entidad_id: UUID,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select id, entidad_tipo, entidad_id, version_trd_id, serie_id,
               subserie_id, tipo_documental_id, justificacion,
               estado, clasificado_por_user_id, fecha_clasificacion,
               reemplazada_por_id, created_at
        from gd.clasificacion_documental
        where tenant_id = $1 and entidad_tipo = $2 and entidad_id = $3
        order by fecha_clasificacion desc
        """,
        tenant_id, entidad_tipo, entidad_id,
    )
    return [dict(r) for r in rows]


__all__ = [
    # TRD
    'crear_version_trd', 'obtener_version_trd', 'listar_versiones_trd',
    'activar_version_trd',
    # Series / subseries / tipos
    'crear_serie', 'listar_series',
    'crear_subserie', 'listar_subseries',
    'crear_tipo_documental', 'listar_tipos_documentales',
    # TVD
    'crear_version_tvd', 'activar_version_tvd', 'listar_versiones_tvd',
    # Asociación dep ↔ código
    'asociar_dep_codigo', 'listar_dep_codigos',
    # Clasificación
    'clasificar', 'obtener_vigente', 'historial_clasificacion',
]
