"""Services SQL para catálogos institucionales del bloque 4.

Cubre cargos, canales, calendarios, tipos PQRSD, tipos correspondencia,
reglas comunicación entre dependencias.

Estilo: funciones CRUD directas; los handlers HTTP las orquestan.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any
from uuid import UUID

import asyncpg


# =============================================================================
# Cargos (GD-API-0013)
# =============================================================================

async def crear_cargo(
    conn: asyncpg.Connection, *, tenant_id: UUID,
    nombre: str, dependencia_id: UUID | None,
    fecha_inicio_vigencia: date | None,
) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        insert into gd.cargo (
            tenant_id, nombre, dependencia_id, fecha_inicio_vigencia
        )
        values ($1, $2, $3, coalesce($4, current_date))
        returning id, tenant_id, nombre, dependencia_id, estado,
                  fecha_inicio_vigencia, fecha_fin_vigencia
        """,
        tenant_id, nombre, dependencia_id, fecha_inicio_vigencia,
    )
    return dict(row)


async def listar_cargos(
    conn: asyncpg.Connection, *, tenant_id: UUID,
    dependencia_id: UUID | None = None,
    estado: str | None = None,
) -> list[dict[str, Any]]:
    where_parts = ['tenant_id = $1']
    params: list[Any] = [tenant_id]

    if dependencia_id:
        params.append(dependencia_id)
        where_parts.append(f'dependencia_id = ${len(params)}')

    if estado:
        params.append(estado)
        where_parts.append(f'estado = ${len(params)}')

    rows = await conn.fetch(
        f"""
        select id, tenant_id, nombre, dependencia_id, estado,
               fecha_inicio_vigencia, fecha_fin_vigencia
        from gd.cargo
        where {' and '.join(where_parts)}
        order by nombre
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def patch_cargo(
    conn: asyncpg.Connection, *, tenant_id: UUID, cargo_id: UUID,
    cambios: dict[str, Any],
) -> dict[str, Any] | None:
    if not cambios:
        row = await conn.fetchrow(
            'select * from gd.cargo where id = $1 and tenant_id = $2',
            cargo_id, tenant_id,
        )
        if row is None:
            return None
        # Renombrar 'id' → 'id' (no cambia), pero forzamos shape consistente.
        return _row_to_cargo_dict(row)

    set_parts: list[str] = []
    params: list[Any] = [tenant_id, cargo_id]
    for col, val in cambios.items():
        params.append(val)
        set_parts.append(f'{col} = ${len(params)}')

    sql = (
        f"update gd.cargo set {', '.join(set_parts)} "
        'where id = $2 and tenant_id = $1 '
        'returning id, tenant_id, nombre, dependencia_id, estado, '
        'fecha_inicio_vigencia, fecha_fin_vigencia'
    )
    row = await conn.fetchrow(sql, *params)
    return dict(row) if row else None


def _row_to_cargo_dict(row: asyncpg.Record) -> dict[str, Any]:
    return {
        'id': row['id'],
        'tenant_id': row['tenant_id'],
        'nombre': row['nombre'],
        'dependencia_id': row['dependencia_id'],
        'estado': row['estado'],
        'fecha_inicio_vigencia': row['fecha_inicio_vigencia'],
        'fecha_fin_vigencia': row['fecha_fin_vigencia'],
    }


# =============================================================================
# Canales (GD-API-0014)
# =============================================================================

async def crear_canal(
    conn: asyncpg.Connection, *, tenant_id: UUID, datos: dict[str, Any],
) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        insert into gd.canal (
            tenant_id, codigo, nombre, descripcion,
            requiere_punto_atencion, requiere_digitalizacion, permite_acuse
        )
        values ($1, $2, $3, $4, $5, $6, $7)
        returning id, tenant_id, codigo, nombre, descripcion,
                  requiere_punto_atencion, requiere_digitalizacion,
                  permite_acuse, estado
        """,
        tenant_id, datos['codigo'], datos['nombre'], datos.get('descripcion'),
        datos.get('requiere_punto_atencion', False),
        datos.get('requiere_digitalizacion', False),
        datos.get('permite_acuse', True),
    )
    return dict(row)


async def listar_canales(
    conn: asyncpg.Connection, *, tenant_id: UUID, estado: str | None = None,
) -> list[dict[str, Any]]:
    if estado:
        rows = await conn.fetch(
            """
            select id, tenant_id, codigo, nombre, descripcion,
                   requiere_punto_atencion, requiere_digitalizacion,
                   permite_acuse, estado
            from gd.canal
            where tenant_id = $1 and estado = $2
            order by nombre
            """,
            tenant_id, estado,
        )
    else:
        rows = await conn.fetch(
            """
            select id, tenant_id, codigo, nombre, descripcion,
                   requiere_punto_atencion, requiere_digitalizacion,
                   permite_acuse, estado
            from gd.canal
            where tenant_id = $1
            order by nombre
            """,
            tenant_id,
        )
    return [dict(r) for r in rows]


# =============================================================================
# Calendarios (GD-API-0014)
# =============================================================================

async def crear_calendario(
    conn: asyncpg.Connection, *, tenant_id: UUID, datos: dict[str, Any],
) -> dict[str, Any]:
    # festivos llega como list[date] desde Pydantic; lo serializamos a jsonb
    # como list de strings ISO para que el SQL pueda hacer `?` matching.
    festivos = datos.get('festivos') or []
    festivos_json = json.dumps([f.isoformat() if isinstance(f, date) else f for f in festivos])

    dias_no_laborales = datos.get('dias_no_laborales') or [0, 6]

    row = await conn.fetchrow(
        """
        insert into gd.calendario_institucional (
            tenant_id, nombre, vigencia_anual, festivos,
            dias_no_laborales, es_default
        )
        values ($1, $2, $3, $4::jsonb, $5::smallint[], $6)
        returning id, tenant_id, nombre, vigencia_anual, festivos,
                  dias_no_laborales, es_default, estado
        """,
        tenant_id, datos['nombre'], datos['vigencia_anual'],
        festivos_json, dias_no_laborales, datos.get('es_default', False),
    )
    return _normalizar_calendario(dict(row))


async def listar_calendarios(
    conn: asyncpg.Connection, *, tenant_id: UUID,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select id, tenant_id, nombre, vigencia_anual, festivos,
               dias_no_laborales, es_default, estado
        from gd.calendario_institucional
        where tenant_id = $1
        order by vigencia_anual desc, nombre
        """,
        tenant_id,
    )
    return [_normalizar_calendario(dict(r)) for r in rows]


async def calendario_default_id(
    conn: asyncpg.Connection, *, tenant_id: UUID,
) -> UUID | None:
    row = await conn.fetchrow(
        """
        select id from gd.calendario_institucional
        where tenant_id = $1 and es_default = true and estado = 'activo'
        limit 1
        """,
        tenant_id,
    )
    return row['id'] if row else None


def _normalizar_calendario(d: dict[str, Any]) -> dict[str, Any]:
    """Convierte festivos (jsonb str | list) a list[date]."""
    festivos = d.get('festivos')
    if isinstance(festivos, str):
        festivos = json.loads(festivos)
    if festivos is None:
        festivos = []
    d['festivos'] = [
        date.fromisoformat(f) if isinstance(f, str) else f for f in festivos
    ]
    # asyncpg trae smallint[] como list[int].
    d['dias_no_laborales'] = list(d.get('dias_no_laborales') or [])
    return d


async def calcular_fecha_limite(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    fecha_base: datetime,
    termino_dias: int,
    tipo_dias: str,
) -> datetime:
    """Wrapper para gd.calcular_fecha_limite() SQL."""
    row = await conn.fetchrow(
        'select gd.calcular_fecha_limite($1, $2, $3, $4) as fecha_limite',
        tenant_id, fecha_base, termino_dias, tipo_dias,
    )
    return row['fecha_limite']


# =============================================================================
# Tipos PQRSD (GD-API-0014)
# =============================================================================

async def crear_tipo_pqrsd(
    conn: asyncpg.Connection, *, tenant_id: UUID, datos: dict[str, Any],
) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        insert into gd.tipo_pqrsd (
            tenant_id, codigo, nombre, descripcion,
            termino_dias, tipo_dias, requiere_respuesta
        )
        values ($1, $2, $3, $4, $5, $6, $7)
        returning id, tenant_id, codigo, nombre, descripcion,
                  termino_dias, tipo_dias, requiere_respuesta, estado
        """,
        tenant_id, datos['codigo'], datos['nombre'], datos.get('descripcion'),
        datos['termino_dias'], datos['tipo_dias'],
        datos.get('requiere_respuesta', True),
    )
    return dict(row)


async def listar_tipos_pqrsd(
    conn: asyncpg.Connection, *, tenant_id: UUID, estado: str | None = None,
) -> list[dict[str, Any]]:
    where_parts = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if estado:
        params.append(estado)
        where_parts.append(f'estado = ${len(params)}')
    rows = await conn.fetch(
        f"""
        select id, tenant_id, codigo, nombre, descripcion,
               termino_dias, tipo_dias, requiere_respuesta, estado
        from gd.tipo_pqrsd
        where {' and '.join(where_parts)}
        order by codigo
        """,
        *params,
    )
    return [dict(r) for r in rows]


# =============================================================================
# Tipos correspondencia (GD-API-0014)
# =============================================================================

async def crear_tipo_correspondencia(
    conn: asyncpg.Connection, *, tenant_id: UUID, datos: dict[str, Any],
) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        insert into gd.tipo_correspondencia (
            tenant_id, codigo, nombre, descripcion, ambito
        )
        values ($1, $2, $3, $4, $5)
        returning id, tenant_id, codigo, nombre, descripcion, ambito, estado
        """,
        tenant_id, datos['codigo'], datos['nombre'],
        datos.get('descripcion'), datos['ambito'],
    )
    return dict(row)


async def listar_tipos_correspondencia(
    conn: asyncpg.Connection, *, tenant_id: UUID,
    ambito: str | None = None, estado: str | None = None,
) -> list[dict[str, Any]]:
    where_parts = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if ambito:
        params.append(ambito)
        where_parts.append(f'ambito = ${len(params)}')
    if estado:
        params.append(estado)
        where_parts.append(f'estado = ${len(params)}')

    rows = await conn.fetch(
        f"""
        select id, tenant_id, codigo, nombre, descripcion, ambito, estado
        from gd.tipo_correspondencia
        where {' and '.join(where_parts)}
        order by codigo
        """,
        *params,
    )
    return [dict(r) for r in rows]


# =============================================================================
# Reglas comunicación entre dependencias (GD-API-0016)
# =============================================================================

async def crear_regla_comunicacion(
    conn: asyncpg.Connection, *, tenant_id: UUID, datos: dict[str, Any],
    created_by_user_id: UUID,
) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        insert into gd.regla_comunicacion_interdependencia (
            tenant_id, dependencia_origen_id, dependencia_destino_id,
            permitido, requiere_aprobacion_jefe, motivo_restriccion,
            created_by_user_id
        )
        values ($1, $2, $3, $4, $5, $6, $7)
        returning id, tenant_id, dependencia_origen_id, dependencia_destino_id,
                  permitido, requiere_aprobacion_jefe, motivo_restriccion, estado
        """,
        tenant_id, datos['dependencia_origen_id'],
        datos['dependencia_destino_id'],
        datos.get('permitido', True),
        datos.get('requiere_aprobacion_jefe', False),
        datos.get('motivo_restriccion'),
        created_by_user_id,
    )
    return dict(row)


async def listar_reglas_comunicacion(
    conn: asyncpg.Connection, *, tenant_id: UUID,
    dependencia_origen_id: UUID | None = None,
) -> list[dict[str, Any]]:
    where_parts = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if dependencia_origen_id:
        params.append(dependencia_origen_id)
        where_parts.append(f'dependencia_origen_id = ${len(params)}')

    rows = await conn.fetch(
        f"""
        select id, tenant_id, dependencia_origen_id, dependencia_destino_id,
               permitido, requiere_aprobacion_jefe, motivo_restriccion, estado
        from gd.regla_comunicacion_interdependencia
        where {' and '.join(where_parts)}
        order by dependencia_origen_id, dependencia_destino_id
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def validar_comunicacion(
    conn: asyncpg.Connection, *, tenant_id: UUID,
    origen: UUID, destino: UUID,
) -> dict[str, Any]:
    """Validación que consume el handler GET /reglas/comunicacion/validar.

    Default permisivo (RNF-056): si no hay regla explícita activa, se asume
    permitido=true y requiere_aprobacion_jefe=false. Si hay regla activa,
    se respeta. Misma dependencia origen=destino: permitido=true siempre.
    """
    if origen == destino:
        return {
            'origen': origen, 'destino': destino,
            'permitido': True, 'requiere_aprobacion_jefe': False,
            'motivo': 'misma dependencia',
            'tiene_regla_explicita': False,
        }

    row = await conn.fetchrow(
        """
        select permitido, requiere_aprobacion_jefe, motivo_restriccion
        from gd.regla_comunicacion_interdependencia
        where tenant_id = $1
          and dependencia_origen_id = $2
          and dependencia_destino_id = $3
          and estado = 'activa'
        limit 1
        """,
        tenant_id, origen, destino,
    )
    if row is None:
        return {
            'origen': origen, 'destino': destino,
            'permitido': True, 'requiere_aprobacion_jefe': False,
            'motivo': None,
            'tiene_regla_explicita': False,
        }

    return {
        'origen': origen, 'destino': destino,
        'permitido': row['permitido'],
        'requiere_aprobacion_jefe': row['requiere_aprobacion_jefe'],
        'motivo': row['motivo_restriccion'],
        'tiene_regla_explicita': True,
    }


__all__ = [
    'crear_cargo', 'listar_cargos', 'patch_cargo',
    'crear_canal', 'listar_canales',
    'crear_calendario', 'listar_calendarios',
    'calendario_default_id', 'calcular_fecha_limite',
    'crear_tipo_pqrsd', 'listar_tipos_pqrsd',
    'crear_tipo_correspondencia', 'listar_tipos_correspondencia',
    'crear_regla_comunicacion', 'listar_reglas_comunicacion',
    'validar_comunicacion',
]
