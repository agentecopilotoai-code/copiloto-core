"""Servicios SQL para GD-API-0007 — Política de contraseñas + historial."""
from __future__ import annotations

import re
from typing import Any
from uuid import UUID

import asyncpg


# Default global (siempre disponible aunque la tabla esté vacía o la migración
# aún no haya corrido en este entorno). Espejo del DEFAULT del DDL.
POLITICA_DEFAULT_GLOBAL: dict[str, Any] = {
    'longitud_minima': 12,
    'complejidad_regex': r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w]).+$',
    'historial_no_reuso': 12,
    'vigencia_dias': 90,
    'intentos_fallidos_max': 5,
    'cooldown_segundos': 300,
}


async def obtener_politica_vigente(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
) -> dict[str, Any]:
    """Devuelve la política activa para el tenant.

    Estrategia:
    1. Buscar política activa con tenant_id == X.
    2. Si no existe, fallback a la global (tenant_id IS NULL).
    3. Si tampoco existe, devolver POLITICA_DEFAULT_GLOBAL con `vigente_desde=now()`
       y `es_global=True`.
    """
    row = await conn.fetchrow(
        """
        select longitud_minima, complejidad_regex, historial_no_reuso,
               vigencia_dias, intentos_fallidos_max, cooldown_segundos,
               vigente_desde, tenant_id
        from gd.politica_contrasena
        where estado = 'activa'
          and (tenant_id = $1 or tenant_id is null)
        order by (tenant_id is not null) desc, vigente_desde desc
        limit 1
        """,
        tenant_id,
    )
    if row is None:
        from datetime import UTC, datetime
        return {
            **POLITICA_DEFAULT_GLOBAL,
            'vigente_desde': datetime.now(UTC),
            'es_global': True,
        }
    d = dict(row)
    d['es_global'] = d.pop('tenant_id') is None
    return d


async def actualizar_politica(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    cambios: dict[str, Any],
    actualizado_por_user_id: UUID,
) -> dict[str, Any]:
    """Crea NUEVA fila de política y marca la anterior como reemplazada.

    Versionamiento por filas (RNF-009): cada cambio queda en histórico.
    """
    politica_actual = await obtener_politica_vigente(conn, tenant_id=tenant_id)
    nueva = {**politica_actual, **cambios}

    # Marcar la política tenant-scoped previa como reemplazada (no toca la global).
    await conn.execute(
        """
        update gd.politica_contrasena
        set estado = 'reemplazada', vigente_hasta = now()
        where tenant_id = $1 and estado = 'activa'
        """,
        tenant_id,
    )

    row = await conn.fetchrow(
        """
        insert into gd.politica_contrasena (
            tenant_id, longitud_minima, complejidad_regex, historial_no_reuso,
            vigencia_dias, intentos_fallidos_max, cooldown_segundos,
            estado, created_by_user_id
        ) values ($1, $2, $3, $4, $5, $6, $7, 'activa', $8)
        returning longitud_minima, complejidad_regex, historial_no_reuso,
                  vigencia_dias, intentos_fallidos_max, cooldown_segundos,
                  vigente_desde
        """,
        tenant_id,
        nueva['longitud_minima'],
        nueva['complejidad_regex'],
        nueva['historial_no_reuso'],
        nueva['vigencia_dias'],
        nueva['intentos_fallidos_max'],
        nueva['cooldown_segundos'],
        actualizado_por_user_id,
    )
    d = dict(row)
    d['es_global'] = False
    return d


def validar_contrasena_contra_politica(
    *,
    contrasena: str,
    longitud_minima: int,
    complejidad_regex: str,
) -> list[str]:
    """Valida una contraseña en CLARO contra reglas de política.

    Retorna lista de errores (vacía si pasa). Solo valida lo que se puede sin DB
    — la verificación de no-reuso histórico requiere `verificar_no_reuso`.
    """
    errores: list[str] = []
    if len(contrasena) < longitud_minima:
        errores.append(f'longitud_insuficiente: requiere >= {longitud_minima} caracteres')
    try:
        if not re.match(complejidad_regex, contrasena):
            errores.append('complejidad_insuficiente: no cumple regex de política')
    except re.error:
        # Política mal configurada — tratamos como error de servidor, no de cliente.
        errores.append('regex_politica_invalida')
    return errores


async def registrar_hash_historico(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    user_id: UUID,
    hash_nuevo: str,
    algoritmo: str = 'bcrypt',
) -> None:
    """Append-only del nuevo hash en gd.historico_contrasena."""
    await conn.execute(
        """
        insert into gd.historico_contrasena (tenant_id, user_id, hash, algoritmo)
        values ($1, $2, $3, $4)
        """,
        tenant_id, user_id, hash_nuevo, algoritmo,
    )


async def listar_hashes_recientes(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    user_id: UUID,
    cantidad: int,
) -> list[str]:
    """Devuelve los N hashes más recientes para validar no-reuso."""
    if cantidad <= 0:
        return []
    rows = await conn.fetch(
        """
        select hash
        from gd.historico_contrasena
        where tenant_id = $1 and user_id = $2
        order by creada_en desc
        limit $3
        """,
        tenant_id, user_id, cantidad,
    )
    return [r['hash'] for r in rows]


__all__ = [
    'POLITICA_DEFAULT_GLOBAL',
    'obtener_politica_vigente',
    'actualizar_politica',
    'validar_contrasena_contra_politica',
    'registrar_hash_historico',
    'listar_hashes_recientes',
]
