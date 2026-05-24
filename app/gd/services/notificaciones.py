"""Services SQL para GD-API-0040 — Notificaciones."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg


async def crear_notificacion(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    destinatario_user_id: UUID,
    tipo_notificacion: str,
    titulo: str,
    mensaje: str,
    entidad_origen_tipo: str | None = None,
    entidad_origen_id: UUID | None = None,
    canales: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Inserta notificación. Worker reactivo a eventos puede llamar esto."""
    row = await conn.fetchrow(
        """
        insert into gd.notificacion (
            tenant_id, destinatario_user_id, tipo_notificacion,
            titulo, mensaje,
            entidad_origen_tipo, entidad_origen_id,
            enviada_por_canal, metadata
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8::text[], $9::jsonb)
        returning id, destinatario_user_id, tipo_notificacion, titulo, mensaje,
                  entidad_origen_tipo, entidad_origen_id,
                  enviada_por_canal, leida, fecha_lectura, created_at
        """,
        tenant_id, destinatario_user_id, tipo_notificacion, titulo, mensaje,
        entidad_origen_tipo, entidad_origen_id,
        canales or ['in_app'],
        json.dumps(metadata or {}, default=str),
    )
    return dict(row)


async def listar_notificaciones(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    destinatario_user_id: UUID,
    solo_no_leidas: bool = False,
    limit: int = 50,
) -> list[dict[str, Any]]:
    if solo_no_leidas:
        rows = await conn.fetch(
            """
            select id, destinatario_user_id, tipo_notificacion, titulo, mensaje,
                   entidad_origen_tipo, entidad_origen_id,
                   enviada_por_canal, leida, fecha_lectura, created_at
            from gd.notificacion
            where tenant_id = $1 and destinatario_user_id = $2 and leida = false
            order by created_at desc
            limit $3
            """,
            tenant_id, destinatario_user_id, limit,
        )
    else:
        rows = await conn.fetch(
            """
            select id, destinatario_user_id, tipo_notificacion, titulo, mensaje,
                   entidad_origen_tipo, entidad_origen_id,
                   enviada_por_canal, leida, fecha_lectura, created_at
            from gd.notificacion
            where tenant_id = $1 and destinatario_user_id = $2
            order by created_at desc
            limit $3
            """,
            tenant_id, destinatario_user_id, limit,
        )
    return [dict(r) for r in rows]


async def contar_no_leidas(
    conn: asyncpg.Connection, *, tenant_id: UUID, destinatario_user_id: UUID,
) -> int:
    row = await conn.fetchrow(
        """
        select count(*) as c from gd.notificacion
        where tenant_id = $1 and destinatario_user_id = $2 and leida = false
        """,
        tenant_id, destinatario_user_id,
    )
    return int(row['c']) if row else 0


async def contar_total(
    conn: asyncpg.Connection, *, tenant_id: UUID, destinatario_user_id: UUID,
) -> int:
    row = await conn.fetchrow(
        """
        select count(*) as c from gd.notificacion
        where tenant_id = $1 and destinatario_user_id = $2
        """,
        tenant_id, destinatario_user_id,
    )
    return int(row['c']) if row else 0


async def marcar_leida(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    notificacion_id: UUID,
    destinatario_user_id: UUID,
) -> dict[str, Any] | None:
    """Marca como leída. Validates ownership (destinatario_user_id)."""
    row = await conn.fetchrow(
        """
        update gd.notificacion
        set leida = true, fecha_lectura = now()
        where id = $1 and tenant_id = $2 and destinatario_user_id = $3
          and leida = false
        returning id, leida, fecha_lectura
        """,
        notificacion_id, tenant_id, destinatario_user_id,
    )
    return dict(row) if row else None


# =============================================================================
# Preferencias
# =============================================================================

async def obtener_preferencias_usuario(
    conn: asyncpg.Connection, *, tenant_id: UUID, user_id: UUID,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select tipo_notificacion, in_app_habilitado, correo_habilitado
        from gd.notificacion_preferencia
        where tenant_id = $1 and user_id = $2
        order by tipo_notificacion
        """,
        tenant_id, user_id,
    )
    return [dict(r) for r in rows]


async def upsert_preferencias(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    user_id: UUID,
    preferencias: list[dict[str, Any]],
) -> int:
    """Upsert masivo de preferencias. Retorna # filas afectadas."""
    count = 0
    for p in preferencias:
        await conn.execute(
            """
            insert into gd.notificacion_preferencia (
                tenant_id, user_id, tipo_notificacion,
                in_app_habilitado, correo_habilitado
            )
            values ($1, $2, $3, $4, $5)
            on conflict (tenant_id, user_id, tipo_notificacion)
            do update set
                in_app_habilitado = excluded.in_app_habilitado,
                correo_habilitado = excluded.correo_habilitado
            """,
            tenant_id, user_id, p['tipo_notificacion'],
            p['in_app_habilitado'], p['correo_habilitado'],
        )
        count += 1
    return count


__all__ = [
    'crear_notificacion', 'listar_notificaciones',
    'contar_no_leidas', 'contar_total',
    'marcar_leida',
    'obtener_preferencias_usuario', 'upsert_preferencias',
]
