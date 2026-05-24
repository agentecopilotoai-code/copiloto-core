"""Services para EP-016 expediente electrónico básico (bloque 17)."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg


# =============================================================================
# CRUD expediente
# =============================================================================

async def crear_expediente(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    codigo: str,
    titulo: str,
    descripcion: str | None,
    dependencia_responsable_id: UUID | None,
    serie_id: UUID | None,
    subserie_id: UUID | None,
    metadata: dict[str, Any],
    abierto_por_user_id: UUID,
) -> dict[str, Any]:
    try:
        row = await conn.fetchrow(
            """
            insert into gd.expediente (
                tenant_id, codigo, titulo, descripcion,
                dependencia_responsable_id, serie_id, subserie_id,
                estado, metadata, abierto_por_user_id
            )
            values ($1, $2, $3, $4, $5, $6, $7, 'abierto', $8::jsonb, $9)
            returning id, codigo, titulo, descripcion,
                      dependencia_responsable_id, serie_id, subserie_id,
                      estado, fecha_apertura, fecha_cierre,
                      fecha_reapertura, fecha_transferencia,
                      motivo_cierre, motivo_reapertura, motivo_transferencia,
                      destino_transferencia,
                      abierto_por_user_id, cerrado_por_user_id,
                      reabierto_por_user_id, metadata, created_at, updated_at
            """,
            tenant_id, codigo, titulo, descripcion,
            dependencia_responsable_id, serie_id, subserie_id,
            json.dumps(metadata), abierto_por_user_id,
        )
    except asyncpg.UniqueViolationError as e:
        raise ValueError('codigo_ya_existe') from e
    d = dict(row)
    if isinstance(d.get('metadata'), str):
        d['metadata'] = json.loads(d['metadata'])
    return d


async def obtener_expediente(
    conn: asyncpg.Connection, *, tenant_id: UUID, expediente_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, codigo, titulo, descripcion,
               dependencia_responsable_id, serie_id, subserie_id,
               estado, fecha_apertura, fecha_cierre,
               fecha_reapertura, fecha_transferencia,
               motivo_cierre, motivo_reapertura, motivo_transferencia,
               destino_transferencia,
               abierto_por_user_id, cerrado_por_user_id,
               reabierto_por_user_id, metadata, created_at, updated_at
        from gd.expediente where id = $1 and tenant_id = $2
        """,
        expediente_id, tenant_id,
    )
    if row is None:
        return None
    d = dict(row)
    if isinstance(d.get('metadata'), str):
        d['metadata'] = json.loads(d['metadata'])
    return d


async def listar_expedientes(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    estado: str | None = None,
    dependencia_id: UUID | None = None,
    serie_id: UUID | None = None,
    subserie_id: UUID | None = None,
    codigo_like: str | None = None,
    titulo_like: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if estado:
        params.append(estado)
        where.append(f'estado = ${len(params)}')
    if dependencia_id:
        params.append(dependencia_id)
        where.append(f'dependencia_responsable_id = ${len(params)}')
    if serie_id:
        params.append(serie_id)
        where.append(f'serie_id = ${len(params)}')
    if subserie_id:
        params.append(subserie_id)
        where.append(f'subserie_id = ${len(params)}')
    if codigo_like:
        params.append(f'%{codigo_like}%')
        where.append(f'codigo ilike ${len(params)}')
    if titulo_like:
        params.append(f'%{titulo_like}%')
        where.append(f'titulo ilike ${len(params)}')
    params.append(limit)
    rows = await conn.fetch(
        f"""
        select id, codigo, titulo, estado,
               dependencia_responsable_id, serie_id, subserie_id,
               fecha_apertura, fecha_cierre, abierto_por_user_id
        from gd.expediente
        where {' and '.join(where)}
        order by fecha_apertura desc
        limit ${len(params)}
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def contar_expedientes(
    conn: asyncpg.Connection, *, tenant_id: UUID,
) -> int:
    n = await conn.fetchval(
        'select count(*) from gd.expediente where tenant_id = $1',
        tenant_id,
    )
    return int(n or 0)


async def patch_expediente(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    expediente_id: UUID,
    cambios: dict[str, Any],
) -> dict[str, Any] | None:
    exists = await conn.fetchval(
        'select estado from gd.expediente where id = $1 and tenant_id = $2',
        expediente_id, tenant_id,
    )
    if exists is None:
        return None
    # Solo se puede editar metadata si está cerrado/transferido — bloquea
    # campos institucionales.
    if exists in ('cerrado', 'transferido', 'anulado'):
        # Permitir solo metadata.
        allowed = {'metadata'}
        if any(k not in allowed for k in cambios):
            raise ValueError(f"estado_invalido_para_edicion:{exists}")
    if not cambios:
        return await obtener_expediente(
            conn, tenant_id=tenant_id, expediente_id=expediente_id,
        )

    sets, params = [], [expediente_id, tenant_id]
    for k, v in cambios.items():
        if k == 'metadata':
            params.append(json.dumps(v))
            sets.append(f'metadata = ${len(params)}::jsonb')
        else:
            params.append(v)
            sets.append(f'{k} = ${len(params)}')

    await conn.execute(
        f"""
        update gd.expediente set {', '.join(sets)}
        where id = $1 and tenant_id = $2
        """,
        *params,
    )
    return await obtener_expediente(
        conn, tenant_id=tenant_id, expediente_id=expediente_id,
    )


# =============================================================================
# Apertura / cierre / reapertura / transferencia
# =============================================================================

async def cerrar_expediente(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    expediente_id: UUID,
    motivo: str,
    usuario_actor_id: UUID,
) -> dict[str, Any] | None:
    exp = await conn.fetchrow(
        'select estado from gd.expediente where id = $1 and tenant_id = $2',
        expediente_id, tenant_id,
    )
    if exp is None:
        return None
    if exp['estado'] not in ('abierto', 'reabierto'):
        raise ValueError(f"estado_invalido:{exp['estado']}")

    await conn.execute(
        """
        update gd.expediente
        set estado = 'cerrado',
            fecha_cierre = now(),
            cerrado_por_user_id = $3,
            motivo_cierre = $4
        where id = $1 and tenant_id = $2
        """,
        expediente_id, tenant_id, usuario_actor_id, motivo,
    )
    return await obtener_expediente(
        conn, tenant_id=tenant_id, expediente_id=expediente_id,
    )


async def reabrir_expediente(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    expediente_id: UUID,
    motivo: str,
    usuario_actor_id: UUID,
) -> dict[str, Any] | None:
    exp = await conn.fetchrow(
        'select estado, fecha_reapertura from gd.expediente '
        'where id = $1 and tenant_id = $2',
        expediente_id, tenant_id,
    )
    if exp is None:
        return None
    if exp['estado'] != 'cerrado':
        raise ValueError(f"estado_invalido:{exp['estado']}")
    if exp['fecha_reapertura'] is not None:
        # Trigger SQL impide editar fecha_reapertura ya registrada → solo
        # se puede reabrir una vez. Esto enforza una sola reapertura.
        raise ValueError('ya_reabierto_previamente')

    await conn.execute(
        """
        update gd.expediente
        set estado = 'reabierto',
            fecha_reapertura = now(),
            reabierto_por_user_id = $3,
            motivo_reapertura = $4
        where id = $1 and tenant_id = $2
        """,
        expediente_id, tenant_id, usuario_actor_id, motivo,
    )
    return await obtener_expediente(
        conn, tenant_id=tenant_id, expediente_id=expediente_id,
    )


async def transferir_expediente(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    expediente_id: UUID,
    destino: str,
    motivo: str,
    usuario_actor_id: UUID,
) -> dict[str, Any] | None:
    """Placeholder fase 2: registra la transferencia con destino + motivo.
    No mueve documentos físicamente.
    """
    exp = await conn.fetchrow(
        'select estado from gd.expediente where id = $1 and tenant_id = $2',
        expediente_id, tenant_id,
    )
    if exp is None:
        return None
    if exp['estado'] not in ('cerrado',):
        raise ValueError(f"estado_invalido:{exp['estado']}")

    await conn.execute(
        """
        update gd.expediente
        set estado = 'transferido',
            fecha_transferencia = now(),
            destino_transferencia = $3,
            motivo_transferencia = $4
        where id = $1 and tenant_id = $2
        """,
        expediente_id, tenant_id, destino, motivo,
    )
    return await obtener_expediente(
        conn, tenant_id=tenant_id, expediente_id=expediente_id,
    )


# =============================================================================
# Items (GD-API-0102)
# =============================================================================

async def asociar_item(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    expediente_id: UUID,
    item_tipo: str,
    item_id: UUID,
    orden: int,
    vinculado_por_user_id: UUID,
) -> dict[str, Any] | None:
    """Vincula item polimórfico al expediente. Idempotente: si ya hay
    vínculo vigente, raise ValueError('vinculo_duplicado')."""
    exp = await conn.fetchrow(
        'select estado from gd.expediente where id = $1 and tenant_id = $2',
        expediente_id, tenant_id,
    )
    if exp is None:
        return None
    if exp['estado'] not in ('abierto', 'reabierto'):
        raise ValueError(f"expediente_estado_invalido:{exp['estado']}")

    try:
        row = await conn.fetchrow(
            """
            insert into gd.expediente_item (
                tenant_id, expediente_id, item_tipo, item_id, orden,
                estado, vinculado_por_user_id
            )
            values ($1, $2, $3, $4, $5, 'vinculado', $6)
            returning id, expediente_id, item_tipo, item_id, orden, estado,
                      vinculado_por_user_id, fecha_vinculacion,
                      retirado_por_user_id, fecha_retiro, motivo_retiro
            """,
            tenant_id, expediente_id, item_tipo, item_id, orden,
            vinculado_por_user_id,
        )
    except asyncpg.UniqueViolationError as e:
        raise ValueError('vinculo_duplicado') from e
    return dict(row)


async def retirar_item(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    expediente_id: UUID,
    item_tipo: str,
    item_id: UUID,
    motivo: str,
    usuario_actor_id: UUID,
) -> dict[str, Any] | None:
    """Marca el vínculo como 'retirado' con motivo. No borra el item original."""
    vinc = await conn.fetchrow(
        """
        select id from gd.expediente_item
        where expediente_id = $1 and tenant_id = $2
          and item_tipo = $3 and item_id = $4 and estado = 'vinculado'
        """,
        expediente_id, tenant_id, item_tipo, item_id,
    )
    if vinc is None:
        return None

    row = await conn.fetchrow(
        """
        update gd.expediente_item
        set estado = 'retirado',
            fecha_retiro = now(),
            retirado_por_user_id = $3,
            motivo_retiro = $4
        where id = $1 and tenant_id = $2
        returning id, expediente_id, item_tipo, item_id, orden, estado,
                  vinculado_por_user_id, fecha_vinculacion,
                  retirado_por_user_id, fecha_retiro, motivo_retiro
        """,
        vinc['id'], tenant_id, usuario_actor_id, motivo,
    )
    return dict(row)


async def listar_items(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    expediente_id: UUID,
    estado: str | None = None,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1', 'expediente_id = $2']
    params: list[Any] = [tenant_id, expediente_id]
    if estado:
        params.append(estado)
        where.append(f'estado = ${len(params)}')
    rows = await conn.fetch(
        f"""
        select id, expediente_id, item_tipo, item_id, orden, estado,
               vinculado_por_user_id, fecha_vinculacion,
               retirado_por_user_id, fecha_retiro, motivo_retiro
        from gd.expediente_item
        where {' and '.join(where)}
        order by orden asc, fecha_vinculacion asc
        """,
        *params,
    )
    return [dict(r) for r in rows]


# =============================================================================
# Contenido agregado (GD-API-0103)
# =============================================================================

async def obtener_contenido(
    conn: asyncpg.Connection, *, tenant_id: UUID, expediente_id: UUID,
) -> dict[str, Any] | None:
    """Devuelve expediente + items vinculados + retirados + totales por tipo."""
    exp = await obtener_expediente(
        conn, tenant_id=tenant_id, expediente_id=expediente_id,
    )
    if exp is None:
        return None

    items = await listar_items(
        conn, tenant_id=tenant_id, expediente_id=expediente_id,
    )
    vinculados = [i for i in items if i['estado'] == 'vinculado']
    retirados = [i for i in items if i['estado'] == 'retirado']

    # Totales por tipo (solo vinculados).
    totales: dict[str, int] = {}
    for i in vinculados:
        totales[i['item_tipo']] = totales.get(i['item_tipo'], 0) + 1

    return {
        'expediente': exp,
        'items_vinculados': vinculados,
        'items_retirados': retirados,
        'totales_por_tipo': totales,
    }


__all__ = [
    # CRUD
    'crear_expediente', 'obtener_expediente', 'listar_expedientes',
    'contar_expedientes', 'patch_expediente',
    # Lifecycle
    'cerrar_expediente', 'reabrir_expediente', 'transferir_expediente',
    # Items
    'asociar_item', 'retirar_item', 'listar_items',
    # Contenido
    'obtener_contenido',
]
