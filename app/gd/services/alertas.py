"""Services SQL para GD-API-0041 — Alertas críticas."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg


async def crear_alerta(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    tipo_alerta: str,
    severidad: str,
    titulo: str,
    mensaje: str,
    destinatario_user_id: UUID | None = None,
    destinatario_dependencia_id: UUID | None = None,
    entidad_relacionada_tipo: str | None = None,
    entidad_relacionada_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        insert into gd.alerta (
            tenant_id, destinatario_user_id, destinatario_dependencia_id,
            tipo_alerta, severidad, titulo, mensaje,
            entidad_relacionada_tipo, entidad_relacionada_id, metadata
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
        returning id, destinatario_user_id, destinatario_dependencia_id,
                  tipo_alerta, severidad, titulo, mensaje,
                  entidad_relacionada_tipo, entidad_relacionada_id,
                  estado, created_at
        """,
        tenant_id, destinatario_user_id, destinatario_dependencia_id,
        tipo_alerta, severidad, titulo, mensaje,
        entidad_relacionada_tipo, entidad_relacionada_id,
        json.dumps(metadata or {}, default=str),
    )
    return dict(row)


async def listar_alertas(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    destinatario_user_id: UUID | None = None,
    estado: str | None = None,
    severidad: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if destinatario_user_id:
        params.append(destinatario_user_id)
        where.append(f'destinatario_user_id = ${len(params)}')
    if estado:
        params.append(estado)
        where.append(f'estado = ${len(params)}')
    if severidad:
        params.append(severidad)
        where.append(f'severidad = ${len(params)}')

    params.append(limit)
    rows = await conn.fetch(
        f"""
        select id, destinatario_user_id, destinatario_dependencia_id,
               tipo_alerta, severidad, titulo, mensaje,
               entidad_relacionada_tipo, entidad_relacionada_id,
               estado, created_at
        from gd.alerta
        where {' and '.join(where)}
        order by
            case severidad
                when 'critica' then 1 when 'alta' then 2
                when 'media' then 3 else 4
            end,
            created_at desc
        limit ${len(params)}
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def contar_activas(
    conn: asyncpg.Connection, *, tenant_id: UUID,
    destinatario_user_id: UUID | None = None,
) -> dict[str, int]:
    where = ['tenant_id = $1', "estado = 'activa'"]
    params: list[Any] = [tenant_id]
    if destinatario_user_id:
        params.append(destinatario_user_id)
        where.append(f'destinatario_user_id = ${len(params)}')

    row = await conn.fetchrow(
        f"""
        select
            count(*) as total,
            count(*) filter (where severidad = 'critica') as criticas
        from gd.alerta
        where {' and '.join(where)}
        """,
        *params,
    )
    return {
        'total': int(row['total']) if row else 0,
        'criticas': int(row['criticas']) if row else 0,
    }


async def escalar_alerta(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    alerta_id: UUID,
    user_destino_id: UUID,
    motivo: str,
    ejecutado_por_user_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        update gd.alerta
        set estado = 'escalada',
            escalada_a_user_id = $3,
            fecha_escalado = now(),
            motivo_escalado = $4
        where id = $2 and tenant_id = $1 and estado = 'activa'
        returning id, destinatario_user_id, destinatario_dependencia_id,
                  tipo_alerta, severidad, titulo, mensaje,
                  entidad_relacionada_tipo, entidad_relacionada_id,
                  estado, created_at
        """,
        tenant_id, alerta_id, user_destino_id, motivo,
    )
    return dict(row) if row else None


async def marcar_gestionada(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    alerta_id: UUID,
    user_id: UUID,
    observacion: str | None,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        update gd.alerta
        set estado = 'gestionada',
            fecha_gestion = now(),
            gestionada_por_user_id = $3,
            metadata = metadata || jsonb_build_object('observacion_gestion', $4::text)
        where id = $2 and tenant_id = $1 and estado in ('activa', 'escalada')
        returning id, destinatario_user_id, destinatario_dependencia_id,
                  tipo_alerta, severidad, titulo, mensaje,
                  entidad_relacionada_tipo, entidad_relacionada_id,
                  estado, created_at
        """,
        tenant_id, alerta_id, user_id, observacion or '',
    )
    return dict(row) if row else None


__all__ = [
    'crear_alerta', 'listar_alertas', 'contar_activas',
    'escalar_alerta', 'marcar_gestionada',
]
