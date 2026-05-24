"""Services SQL para GD-API-0034 (contactos) + GD-API-0035 (historial tercero)."""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg


# =============================================================================
# Contactos
# =============================================================================

async def crear_contacto(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    tercero_id: UUID,
    tipo_contacto: str,
    valor: str,
    es_principal: bool,
) -> dict[str, Any]:
    # Si es_principal=True, desmarcar otros del mismo tipo.
    if es_principal:
        await conn.execute(
            """
            update gd.contacto_tercero
            set es_principal = false
            where tercero_id = $1 and tipo_contacto = $2 and es_principal = true
            """,
            tercero_id, tipo_contacto,
        )

    row = await conn.fetchrow(
        """
        insert into gd.contacto_tercero (
            tenant_id, tercero_id, tipo_contacto, valor, es_principal
        )
        values ($1, $2, $3, $4, $5)
        returning id, tenant_id, tercero_id, tipo_contacto, valor,
                  es_principal, estado
        """,
        tenant_id, tercero_id, tipo_contacto, valor, es_principal,
    )
    return dict(row)


async def listar_contactos(
    conn: asyncpg.Connection, *, tenant_id: UUID, tercero_id: UUID,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select id, tenant_id, tercero_id, tipo_contacto, valor,
               es_principal, estado
        from gd.contacto_tercero
        where tenant_id = $1 and tercero_id = $2
        order by es_principal desc, tipo_contacto, valor
        """,
        tenant_id, tercero_id,
    )
    return [dict(r) for r in rows]


async def inactivar_contacto(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    contacto_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        update gd.contacto_tercero
        set estado = 'inactivo'
        where id = $1 and tenant_id = $2 and estado = 'activo'
        returning id, tenant_id, tercero_id, tipo_contacto, valor,
                  es_principal, estado
        """,
        contacto_id, tenant_id,
    )
    return dict(row) if row else None


# =============================================================================
# Historial unificado del tercero
# =============================================================================

async def obtener_historial_tercero(
    conn: asyncpg.Connection, *, tenant_id: UUID, tercero_id: UUID,
    limit: int = 100,
) -> dict[str, Any]:
    """Devuelve radicados + PQRSD + correspondencia del tercero.

    Por ahora solo radicados (gd.pqrsd y gd.correspondencia no existen aún).
    TODO(human): UNION con pqrsd + correspondencia cuando EP-007/EP-008 las creen.
    """
    rows = await conn.fetch(
        """
        select id, numero_radicado, fecha_radicacion, asunto, estado
        from gd.radicado
        where tenant_id = $1
          and (tercero_id = $2 or tercero_destinatario_id = $2)
        order by fecha_radicacion desc
        limit $3
        """,
        tenant_id, tercero_id, limit,
    )
    items = [
        {
            'tipo': 'radicado',
            'id': r['id'],
            'identificador': r['numero_radicado'],
            'fecha': r['fecha_radicacion'],
            'asunto': r['asunto'],
            'estado': r['estado'],
        }
        for r in rows
    ]
    totales = {
        'radicados': len(items),
        'pqrsd': 0,  # diferido a EP-007
        'correspondencia': 0,  # diferido a EP-008
    }
    return {'tercero_id': tercero_id, 'items': items, 'totales': totales}


__all__ = [
    'crear_contacto', 'listar_contactos', 'inactivar_contacto',
    'obtener_historial_tercero',
]
