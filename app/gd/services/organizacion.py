"""Servicios SQL para GD-API-0011, 0011.b, 0011.c — Perfil organización."""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg


async def obtener_perfil_organizacion(
    conn: asyncpg.Connection, *, tenant_id: UUID
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select
            tenant_id, tipo_organizacion,
            identificacion_fiscal, tipo_identificacion_fiscal,
            razon_social_legal, nombre_corto,
            direccion_oficial, telefono_oficial, correo_oficial, sitio_web,
            logo_archivo_digital_id,
            politica_firma_default, formato_radicado,
            dias_alerta_vencimiento_default,
            pais_iso, zona_horaria_default
        from gd.perfil_organizacion
        where tenant_id = $1
        """,
        tenant_id,
    )
    return dict(row) if row else None


async def crear_perfil_organizacion(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    datos: dict[str, Any],
    created_by_user_id: UUID,
) -> dict[str, Any]:
    """Inserta perfil. asyncpg.UniqueViolationError si ya existe (PK = tenant_id)."""
    row = await conn.fetchrow(
        """
        insert into gd.perfil_organizacion (
            tenant_id, tipo_organizacion,
            identificacion_fiscal, tipo_identificacion_fiscal,
            razon_social_legal, nombre_corto,
            direccion_oficial, telefono_oficial, correo_oficial, sitio_web,
            logo_archivo_digital_id, politica_firma_default,
            formato_radicado, dias_alerta_vencimiento_default,
            pais_iso, zona_horaria_default, created_by_user_id
        ) values (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
            $11, $12, $13, $14, $15, $16, $17
        )
        returning
            tenant_id, tipo_organizacion,
            identificacion_fiscal, tipo_identificacion_fiscal,
            razon_social_legal, nombre_corto,
            direccion_oficial, telefono_oficial, correo_oficial, sitio_web,
            logo_archivo_digital_id, politica_firma_default,
            formato_radicado, dias_alerta_vencimiento_default,
            pais_iso, zona_horaria_default
        """,
        tenant_id,
        datos['tipo_organizacion'],
        datos['identificacion_fiscal'],
        datos.get('tipo_identificacion_fiscal', 'NIT'),
        datos['razon_social_legal'],
        datos['nombre_corto'],
        datos.get('direccion_oficial'),
        datos.get('telefono_oficial'),
        datos.get('correo_oficial'),
        datos.get('sitio_web'),
        datos.get('logo_archivo_digital_id'),
        datos.get('politica_firma_default', 'electronica'),
        datos.get('formato_radicado', '{prefijo}-{vigencia}-{consecutivo:06d}'),
        datos.get('dias_alerta_vencimiento_default', 3),
        datos.get('pais_iso', 'CO'),
        datos.get('zona_horaria_default', 'America/Bogota'),
        created_by_user_id,
    )
    return dict(row)


async def actualizar_perfil_organizacion(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    cambios: dict[str, Any],
) -> dict[str, Any] | None:
    if not cambios:
        return await obtener_perfil_organizacion(conn, tenant_id=tenant_id)

    set_parts: list[str] = []
    params: list[Any] = [tenant_id]
    for col, val in cambios.items():
        params.append(val)
        set_parts.append(f'{col} = ${len(params)}')

    sql = (
        f"update gd.perfil_organizacion set {', '.join(set_parts)} "
        'where tenant_id = $1 '
        'returning tenant_id, tipo_organizacion, identificacion_fiscal, '
        'tipo_identificacion_fiscal, razon_social_legal, nombre_corto, '
        'direccion_oficial, telefono_oficial, correo_oficial, sitio_web, '
        'logo_archivo_digital_id, politica_firma_default, formato_radicado, '
        'dias_alerta_vencimiento_default, pais_iso, zona_horaria_default'
    )
    row = await conn.fetchrow(sql, *params)
    return dict(row) if row else None


async def aplicar_defaults_modulos(
    conn: asyncpg.Connection, *, tenant_id: UUID
) -> int:
    """Llama a la función SQL gd.aplicar_defaults_modulos. Retorna # módulos
    insertados (los que ya estaban no se cuentan)."""
    row = await conn.fetchrow(
        'select gd.aplicar_defaults_modulos($1) as count', tenant_id
    )
    return int(row['count']) if row else 0


async def listar_modulos(
    conn: asyncpg.Connection, *, tenant_id: UUID
) -> list[dict[str, Any]]:
    """Devuelve todos los 14 módulos (los que no tienen fila se completan como
    activado=false, configuracion=None)."""
    # Lista canónica — espejo del CHECK en SQL.
    todos_modulos = [
        'pqrsd_legal', 'pqrsd_tickets', 'correspondencia_interna',
        'correspondencia_externa', 'firma_escaneada', 'firma_electronica',
        'firma_digital_certificada', 'expedientes', 'trd_tvd',
        'integracion_correo', 'agentes_ia',
        'radicacion_externa_desde_dependencia', 'consulta_publica_radicado',
        'ventanilla_presencial_con_perifericos',
    ]

    rows = await conn.fetch(
        """
        select modulo_codigo, activado, configuracion
        from gd.organizacion_modulo_activacion
        where tenant_id = $1
        """,
        tenant_id,
    )
    existentes = {r['modulo_codigo']: dict(r) for r in rows}

    resultado = []
    for mod in todos_modulos:
        if mod in existentes:
            resultado.append(existentes[mod])
        else:
            resultado.append({
                'modulo_codigo': mod, 'activado': False, 'configuracion': None
            })
    return resultado


async def upsert_modulos(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    cambios: list[dict[str, Any]],
) -> int:
    """Upsert masivo de activaciones. Retorna # filas afectadas."""
    if not cambios:
        return 0
    count = 0
    for c in cambios:
        result = await conn.execute(
            """
            insert into gd.organizacion_modulo_activacion (
                tenant_id, modulo_codigo, activado, configuracion
            ) values ($1, $2, $3, $4::jsonb)
            on conflict (tenant_id, modulo_codigo)
            do update set
                activado = excluded.activado,
                configuracion = excluded.configuracion
            """,
            tenant_id,
            c['modulo_codigo'],
            c['activado'],
            _jsonb(c.get('configuracion') or {}),
        )
        if not result.endswith(' 0'):
            count += 1
    return count


def _jsonb(value: Any) -> str:
    import json
    return json.dumps(value, default=str)


__all__ = [
    'obtener_perfil_organizacion',
    'crear_perfil_organizacion',
    'actualizar_perfil_organizacion',
    'aplicar_defaults_modulos',
    'listar_modulos',
    'upsert_modulos',
]
