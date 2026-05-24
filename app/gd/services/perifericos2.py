"""Services para EP-021 periféricos parte 2 (bloque 21b — CIERRE backlog).

Cubre GD-API-0136..0142:
- Digitalización por lote (iniciar/get progreso/finalizar)
- Contexto activo (UPSERT con TTL)
- Mantenimiento + eventos + dashboard salud + auto-protección
- Agente local (emparejar/revocar)
- Historial unificado + export
- Reemplazo de digitalización (RFP-005)

Convenciones (heredadas del bloque 21a):
- asyncpg raw SQL + RLS por tenant.
- Gate por módulo activo se aplica en handlers (no aquí).
- emit_gd_event en handlers; services NO emiten para mantener pureza.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import asyncpg


# =============================================================================
# Digitalización por lote (GD-API-0136)
# =============================================================================

async def iniciar_lote_digitalizacion(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, periferico_id: UUID, usuario_id: UUID,
    modo_separacion: str, radicado_id_default: UUID | None,
    calidad_dpi: int, observacion: str | None, timeout_min: int,
) -> dict[str, Any]:
    # Validar periférico activo.
    perif = await conn.fetchrow(
        """
        select id, estado from gd.periferico
        where tenant_id = $1 and id = $2
        """,
        tenant_id, periferico_id,
    )
    if perif is None:
        raise LookupError('periferico_no_existe')
    if perif['estado'] != 'activo':
        raise ValueError('periferico_no_disponible')

    timeout_en = datetime.now(timezone.utc) + timedelta(minutes=timeout_min)
    row = await conn.fetchrow(
        """
        insert into gd.digitalizacion_lote (
            tenant_id, periferico_id, usuario_id, modo_separacion,
            radicado_id_default, calidad_dpi, observacion, timeout_en
        ) values ($1, $2, $3, $4, $5, $6, $7, $8)
        returning id, periferico_id, usuario_id, modo_separacion,
                  radicado_id_default, estado, calidad_dpi, observacion,
                  total_documentos, iniciado_en, finalizado_en, timeout_en
        """,
        tenant_id, periferico_id, usuario_id, modo_separacion,
        radicado_id_default, calidad_dpi, observacion, timeout_en,
    )
    return dict(row)


async def obtener_lote(
    conn: asyncpg.Connection, *, tenant_id: UUID, lote_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, periferico_id, usuario_id, modo_separacion,
               radicado_id_default, estado, calidad_dpi, observacion,
               total_documentos, iniciado_en, finalizado_en, timeout_en
        from gd.digitalizacion_lote
        where tenant_id = $1 and id = $2
        """,
        tenant_id, lote_id,
    )
    return dict(row) if row else None


async def progreso_lote(
    conn: asyncpg.Connection, *, tenant_id: UUID, lote_id: UUID,
) -> dict[str, Any] | None:
    base = await obtener_lote(conn, tenant_id=tenant_id, lote_id=lote_id)
    if base is None:
        return None
    items = await conn.fetch(
        """
        select id, radicado_id, archivo_digital_id, numero_paginas,
               estado, mensaje_error, fecha_digitalizacion
        from gd.digitalizacion_documento
        where tenant_id = $1 and lote_id = $2
        order by fecha_digitalizacion
        """,
        tenant_id, lote_id,
    )
    base['digitalizaciones'] = [dict(r) for r in items]
    return base


async def finalizar_lote(
    conn: asyncpg.Connection, *, tenant_id: UUID, lote_id: UUID,
    observacion_final: str | None,
) -> dict[str, Any]:
    existente = await obtener_lote(conn, tenant_id=tenant_id, lote_id=lote_id)
    if existente is None:
        raise LookupError('lote_no_existe')
    if existente['estado'] != 'abierto':
        raise ValueError('lote_no_actualizable')

    obs = existente.get('observacion') or ''
    if observacion_final:
        obs = (obs + '\n' + observacion_final).strip()

    row = await conn.fetchrow(
        """
        update gd.digitalizacion_lote
        set estado = 'finalizado', finalizado_en = now(),
            observacion = $3, updated_at = now()
        where tenant_id = $1 and id = $2
        returning id, periferico_id, usuario_id, modo_separacion,
                  radicado_id_default, estado, calidad_dpi, observacion,
                  total_documentos, iniciado_en, finalizado_en, timeout_en
        """,
        tenant_id, lote_id, obs or None,
    )
    return dict(row)


# =============================================================================
# Contexto activo (GD-API-0137)
# =============================================================================

async def upsert_contexto_activo(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, user_id: UUID, periferico_id: UUID,
    radicado_activo_id: UUID, expira_en_segundos: int,
) -> dict[str, Any]:
    expira = datetime.now(timezone.utc) + timedelta(seconds=expira_en_segundos)
    row = await conn.fetchrow(
        """
        insert into gd.contexto_periferico_usuario (
            tenant_id, user_id, periferico_id, radicado_activo_id, expira_en
        ) values ($1, $2, $3, $4, $5)
        on conflict (user_id, periferico_id) do update set
            radicado_activo_id = excluded.radicado_activo_id,
            expira_en = excluded.expira_en,
            updated_at = now()
        returning id, user_id, periferico_id, radicado_activo_id,
                  expira_en, created_at
        """,
        tenant_id, user_id, periferico_id, radicado_activo_id, expira,
    )
    return dict(row)


async def eliminar_contexto_activo(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, user_id: UUID, periferico_id: UUID,
) -> bool:
    result = await conn.execute(
        """
        delete from gd.contexto_periferico_usuario
        where tenant_id = $1 and user_id = $2 and periferico_id = $3
        """,
        tenant_id, user_id, periferico_id,
    )
    # asyncpg.execute devuelve 'DELETE N'.
    try:
        n = int(str(result).split()[-1])
    except (ValueError, IndexError):
        n = 0
    return n > 0


async def obtener_contexto_activo(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, user_id: UUID, periferico_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, user_id, periferico_id, radicado_activo_id,
               expira_en, created_at
        from gd.contexto_periferico_usuario
        where tenant_id = $1 and user_id = $2 and periferico_id = $3
          and expira_en > now()
        """,
        tenant_id, user_id, periferico_id,
    )
    return dict(row) if row else None


# =============================================================================
# Mantenimiento + eventos + dashboard salud (GD-API-0138)
# =============================================================================

UMBRAL_AUTO_PROTECCION = 5  # >5 fallos en 1h


async def listar_eventos_periferico(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, periferico_id: UUID,
    desde: datetime | None = None, hasta: datetime | None = None,
    resultado: str | None = None, limit: int = 100,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1', 'periferico_id = $2']
    params: list[Any] = [tenant_id, periferico_id]
    if desde is not None:
        params.append(desde)
        where.append(f'fecha_hora >= ${len(params)}')
    if hasta is not None:
        params.append(hasta)
        where.append(f'fecha_hora <= ${len(params)}')
    if resultado is not None:
        params.append(resultado)
        where.append(f'resultado = ${len(params)}')
    params.append(limit)
    rows = await conn.fetch(
        f"""
        select id, periferico_id, usuario_id, tipo_evento,
               entidad_relacionada_tipo, entidad_relacionada_id,
               resultado, mensaje_error, latencia_ms, fecha_hora
        from gd.evento_periferico
        where {' and '.join(where)}
        order by fecha_hora desc
        limit ${len(params)}
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def agregado_fallos(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, desde: datetime,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select e.periferico_id, p.nombre as periferico_nombre,
               count(*)::int as total_fallos,
               max(e.fecha_hora) as ultimo_fallo
        from gd.evento_periferico e
        join gd.periferico p on p.id = e.periferico_id
        where e.tenant_id = $1
          and e.fecha_hora >= $2
          and e.resultado in ('fallo', 'timeout')
        group by e.periferico_id, p.nombre
        order by total_fallos desc
        """,
        tenant_id, desde,
    )
    return [dict(r) for r in rows]


async def chequear_auto_proteccion(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, periferico_id: UUID, usuario_actor_id: UUID,
) -> dict[str, Any] | None:
    """Si periférico tiene >5 fallos en 1h, lo pasa a mantenimiento y crea
    fila en gd.mantenimiento_periferico con tipo=auto_proteccion. Retorna
    el mantenimiento creado o None si no aplica."""
    desde = datetime.now(timezone.utc) - timedelta(hours=1)
    fallos = await conn.fetchval(
        """
        select count(*) from gd.evento_periferico
        where tenant_id = $1 and periferico_id = $2
          and fecha_hora >= $3 and resultado in ('fallo', 'timeout')
        """,
        tenant_id, periferico_id, desde,
    )
    if (fallos or 0) <= UMBRAL_AUTO_PROTECCION:
        return None

    # Pasar a mantenimiento.
    await conn.execute(
        """
        update gd.periferico
        set estado = 'mantenimiento',
            motivo_cambio_estado = 'auto_proteccion (>5 fallos en 1h)',
            updated_at = now()
        where tenant_id = $1 and id = $2 and estado = 'activo'
        """,
        tenant_id, periferico_id,
    )

    row = await conn.fetchrow(
        """
        insert into gd.mantenimiento_periferico (
            tenant_id, periferico_id, tipo, descripcion,
            iniciado_por_user_id
        ) values ($1, $2, 'auto_proteccion',
                  'Auto-protección: ' || $3::text || ' fallos en 1h.', $4)
        returning id, periferico_id, tipo, descripcion, fecha_estimada_fin,
                  iniciado_por_user_id, iniciado_en, finalizado_en,
                  observacion_final, costo, repuestos,
                  finalizado_por_user_id, estado
        """,
        tenant_id, periferico_id, fallos, usuario_actor_id,
    )
    return _norm_mant(row)


async def iniciar_mantenimiento(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, periferico_id: UUID,
    tipo: str, descripcion: str, fecha_estimada_fin: Any,
    iniciado_por_user_id: UUID,
) -> dict[str, Any]:
    perif = await conn.fetchrow(
        """
        select id, estado from gd.periferico
        where tenant_id = $1 and id = $2
        """,
        tenant_id, periferico_id,
    )
    if perif is None:
        raise LookupError('periferico_no_existe')

    # Pasar el periférico a mantenimiento.
    await conn.execute(
        """
        update gd.periferico
        set estado = 'mantenimiento',
            motivo_cambio_estado = 'mantenimiento programado',
            updated_at = now()
        where tenant_id = $1 and id = $2
        """,
        tenant_id, periferico_id,
    )

    row = await conn.fetchrow(
        """
        insert into gd.mantenimiento_periferico (
            tenant_id, periferico_id, tipo, descripcion,
            fecha_estimada_fin, iniciado_por_user_id
        ) values ($1, $2, $3, $4, $5, $6)
        returning id, periferico_id, tipo, descripcion, fecha_estimada_fin,
                  iniciado_por_user_id, iniciado_en, finalizado_en,
                  observacion_final, costo, repuestos,
                  finalizado_por_user_id, estado
        """,
        tenant_id, periferico_id, tipo, descripcion, fecha_estimada_fin,
        iniciado_por_user_id,
    )
    return _norm_mant(row)


async def finalizar_mantenimiento(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, periferico_id: UUID, mantenimiento_id: UUID,
    observacion_final: str, costo: Any, repuestos: list[Any] | None,
    finalizado_por_user_id: UUID,
) -> dict[str, Any]:
    existente = await conn.fetchrow(
        """
        select id, estado from gd.mantenimiento_periferico
        where tenant_id = $1 and id = $2 and periferico_id = $3
        """,
        tenant_id, mantenimiento_id, periferico_id,
    )
    if existente is None:
        raise LookupError('mantenimiento_no_existe')
    if existente['estado'] != 'en_curso':
        raise ValueError('mantenimiento_no_actualizable')

    row = await conn.fetchrow(
        """
        update gd.mantenimiento_periferico
        set estado = 'finalizado', finalizado_en = now(),
            observacion_final = $3, costo = $4,
            repuestos = $5::jsonb,
            finalizado_por_user_id = $6, updated_at = now()
        where tenant_id = $1 and id = $2
        returning id, periferico_id, tipo, descripcion, fecha_estimada_fin,
                  iniciado_por_user_id, iniciado_en, finalizado_en,
                  observacion_final, costo, repuestos,
                  finalizado_por_user_id, estado
        """,
        tenant_id, mantenimiento_id, observacion_final, costo,
        json.dumps(repuestos) if repuestos is not None else None,
        finalizado_por_user_id,
    )

    # Reactivar periférico.
    await conn.execute(
        """
        update gd.periferico
        set estado = 'activo',
            motivo_cambio_estado = 'mantenimiento finalizado',
            updated_at = now()
        where tenant_id = $1 and id = $2 and estado = 'mantenimiento'
        """,
        tenant_id, periferico_id,
    )

    return _norm_mant(row)


def _norm_mant(row: Any) -> dict[str, Any]:
    if row is None:
        return None  # type: ignore[return-value]
    d = dict(row)
    rep = d.get('repuestos')
    if isinstance(rep, str):
        d['repuestos'] = json.loads(rep) if rep else None
    return d


# =============================================================================
# Agente local (GD-API-0139)
# =============================================================================

def _generar_token_emparejamiento() -> str:
    """Token urlsafe 32 bytes — entrega one-shot."""
    return secrets.token_urlsafe(32)


def _hash_token(token: str) -> str:
    """SHA-256 hex del token. Solo el hash se persiste."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


async def emparejar_agente_local(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, nombre_equipo: str, version_agente: str | None,
    perifericos: list[UUID], fingerprint_publico_b64: str,
    registrado_por_user_id: UUID,
) -> dict[str, Any]:
    """Crea registro con estado=pendiente + devuelve token one-shot.

    Validaciones:
    - Los periféricos deben existir y pertenecer al tenant.
    """
    # Validar periféricos.
    encontrados = await conn.fetchval(
        """
        select count(*) from gd.periferico
        where tenant_id = $1 and id = any($2::uuid[])
        """,
        tenant_id, perifericos,
    )
    if (encontrados or 0) != len(perifericos):
        raise LookupError('perifericos_no_encontrados')

    token = _generar_token_emparejamiento()
    token_hash = _hash_token(token)
    expira = datetime.now(timezone.utc) + timedelta(minutes=10)

    # fingerprint_publico se almacena como bytea — convertimos b64 → bytes.
    import base64
    try:
        fp_bytes = base64.b64decode(fingerprint_publico_b64, validate=True)
    except Exception as e:
        raise ValueError('fingerprint_invalido') from e

    row = await conn.fetchrow(
        """
        insert into gd.agente_local_registro (
            tenant_id, nombre_equipo, version_agente,
            periferico_ids, fingerprint_publico,
            token_emparejamiento_hash, token_emparejamiento_expira,
            estado, registrado_por_user_id
        ) values ($1, $2, $3, $4::uuid[], $5, $6, $7, 'pendiente', $8)
        returning id, nombre_equipo, version_agente, periferico_ids,
                  fingerprint_publico, estado, motivo_revocacion,
                  ultimo_handshake_en, registrado_por_user_id,
                  fecha_registro,
                  token_emparejamiento_expira
        """,
        tenant_id, nombre_equipo, version_agente, perifericos, fp_bytes,
        token_hash, expira, registrado_por_user_id,
    )
    result = dict(row)
    result['token_emparejamiento'] = token  # one-shot, no se persiste claro
    return result


async def revocar_agente_local(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, agente_id: UUID, motivo: str,
) -> dict[str, Any]:
    existente = await conn.fetchrow(
        """
        select id, estado from gd.agente_local_registro
        where tenant_id = $1 and id = $2
        """,
        tenant_id, agente_id,
    )
    if existente is None:
        raise LookupError('agente_no_existe')
    if existente['estado'] == 'revocado':
        raise ValueError('agente_ya_revocado')

    row = await conn.fetchrow(
        """
        update gd.agente_local_registro
        set estado = 'revocado', motivo_revocacion = $3,
            updated_at = now()
        where tenant_id = $1 and id = $2
        returning id, nombre_equipo, version_agente, periferico_ids,
                  estado, motivo_revocacion, ultimo_handshake_en,
                  registrado_por_user_id, fecha_registro
        """,
        tenant_id, agente_id, motivo,
    )
    return dict(row)


async def obtener_agente_local(
    conn: asyncpg.Connection, *, tenant_id: UUID, agente_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, nombre_equipo, version_agente, periferico_ids,
               estado, motivo_revocacion, ultimo_handshake_en,
               registrado_por_user_id, fecha_registro
        from gd.agente_local_registro
        where tenant_id = $1 and id = $2
        """,
        tenant_id, agente_id,
    )
    return dict(row) if row else None


# =============================================================================
# Historial uso (GD-API-0141)
# =============================================================================

async def historial_periferico(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, periferico_id: UUID,
    desde: datetime | None = None, hasta: datetime | None = None,
    tipo_operacion: str | None = None, limit: int = 200,
) -> list[dict[str, Any]]:
    """Historial unificado: impresiones + digitalizaciones + eventos."""
    parts: list[str] = []
    params: list[Any] = []

    def _p(v):
        params.append(v)
        return f'${len(params)}'

    tid_idx = _p(tenant_id)
    pid_idx = _p(periferico_id)

    # Imprimir-fragmento por tabla.
    desde_idx = hasta_idx = None
    if desde is not None:
        desde_idx = _p(desde)
    if hasta is not None:
        hasta_idx = _p(hasta)

    if tipo_operacion in (None, 'impresion'):
        cond_extra = ''
        if desde_idx:
            cond_extra += f' and fecha_impresion >= {desde_idx}'
        if hasta_idx:
            cond_extra += f' and fecha_impresion <= {hasta_idx}'
        parts.append(f"""
            select id, 'impresion'::text as tipo_operacion,
                   tipo_impresion as subtipo, estado, fecha_impresion as fecha,
                   usuario_id, radicado_id, mensaje_error
            from gd.impresion_radicado
            where tenant_id = {tid_idx} and periferico_id = {pid_idx}{cond_extra}
        """)
    if tipo_operacion in (None, 'digitalizacion'):
        cond_extra = ''
        if desde_idx:
            cond_extra += f' and fecha_digitalizacion >= {desde_idx}'
        if hasta_idx:
            cond_extra += f' and fecha_digitalizacion <= {hasta_idx}'
        parts.append(f"""
            select id, 'digitalizacion'::text as tipo_operacion,
                   tipo_digitalizacion as subtipo, estado,
                   fecha_digitalizacion as fecha,
                   usuario_id, radicado_id, mensaje_error
            from gd.digitalizacion_documento
            where tenant_id = {tid_idx} and periferico_id = {pid_idx}{cond_extra}
        """)
    if tipo_operacion in (None, 'evento_periferico'):
        cond_extra = ''
        if desde_idx:
            cond_extra += f' and fecha_hora >= {desde_idx}'
        if hasta_idx:
            cond_extra += f' and fecha_hora <= {hasta_idx}'
        parts.append(f"""
            select id, 'evento_periferico'::text as tipo_operacion,
                   tipo_evento as subtipo, resultado as estado,
                   fecha_hora as fecha,
                   usuario_id, null::uuid as radicado_id, mensaje_error
            from gd.evento_periferico
            where tenant_id = {tid_idx} and periferico_id = {pid_idx}{cond_extra}
        """)

    if not parts:
        return []

    params.append(limit)
    sql = (
        ' union all '.join(parts)
        + f' order by fecha desc limit ${len(params)}'
    )
    rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]


async def historial_uso_global(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, usuario_id: UUID | None = None,
    periferico_id: UUID | None = None,
    desde: datetime | None = None, limit: int = 500,
) -> list[dict[str, Any]]:
    """Vista cruzada para auditor."""
    where_imp = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if usuario_id is not None:
        params.append(usuario_id)
        where_imp.append(f'usuario_id = ${len(params)}')
    if periferico_id is not None:
        params.append(periferico_id)
        where_imp.append(f'periferico_id = ${len(params)}')
    if desde is not None:
        params.append(desde)
        where_imp.append(f'fecha_impresion >= ${len(params)}')
    # Para digit/eventos repetimos los mismos placeholders (orden simple).
    params.append(limit)
    limit_ph = f'${len(params)}'

    cond = ' and '.join(where_imp)
    # Imprimir-fragmento por tabla, mismas condiciones.
    sql = f"""
        select id, 'impresion'::text as tipo_operacion,
               tipo_impresion as subtipo, estado, fecha_impresion as fecha,
               usuario_id, periferico_id, radicado_id, mensaje_error
        from gd.impresion_radicado
        where {cond.replace('fecha_impresion', 'fecha_impresion')}
        union all
        select id, 'digitalizacion'::text as tipo_operacion,
               tipo_digitalizacion as subtipo, estado,
               fecha_digitalizacion as fecha,
               usuario_id, periferico_id, radicado_id, mensaje_error
        from gd.digitalizacion_documento
        where {cond.replace('fecha_impresion', 'fecha_digitalizacion')}
        order by fecha desc limit {limit_ph}
    """
    rows = await conn.fetch(sql, *params)
    return [dict(r) for r in rows]


async def export_historial(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, formato: str,
    desde: datetime | None, hasta: datetime | None,
    periferico_id: UUID | None, usuario_id: UUID | None,
    solicitado_por_user_id: UUID,
) -> dict[str, Any]:
    """Versión stub: cuenta filas + devuelve metadata.

    En producción esto enrutaría a un worker async que genera el CSV/Excel
    real y lo sube a `core.archivo_digital`. Aquí solo registramos la
    solicitud y dejamos `archivo_digital_id=None` (el worker lo llena).
    """
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if usuario_id is not None:
        params.append(usuario_id)
        where.append(f'usuario_id = ${len(params)}')
    if periferico_id is not None:
        params.append(periferico_id)
        where.append(f'periferico_id = ${len(params)}')
    if desde is not None:
        params.append(desde)
        where.append(f'fecha_impresion >= ${len(params)}')

    total = await conn.fetchval(
        f"""
        select (
            (select count(*) from gd.impresion_radicado where {' and '.join(where)})
          + (select count(*) from gd.digitalizacion_documento
             where {' and '.join(where).replace('fecha_impresion','fecha_digitalizacion')})
        )
        """,
        *params,
    )

    from uuid import uuid4
    return {
        'export_id': uuid4(),
        'formato': formato,
        'total_filas': int(total or 0),
        'archivo_digital_id': None,
    }


# =============================================================================
# Reemplazo digitalización (GD-API-0142)
# =============================================================================

async def reemplazar_digitalizacion(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, digitalizacion_id: UUID,
    motivo: str, archivo_digital_id_nuevo: UUID,
    usuario_id: UUID,
) -> dict[str, Any]:
    """Crea nueva digitalización con FK al original. Marca el original
    como `reemplazada`. El original NO se borra (DELETE bloqueado por
    trigger SQL — Doc 6 § 7 RFP-005)."""
    original = await conn.fetchrow(
        """
        select id, radicado_id, periferico_id, tipo_digitalizacion,
               calidad_dpi, estado
        from gd.digitalizacion_documento
        where tenant_id = $1 and id = $2
        """,
        tenant_id, digitalizacion_id,
    )
    if original is None:
        raise LookupError('digitalizacion_no_existe')
    if original['estado'] == 'reemplazada':
        raise ValueError('digitalizacion_ya_reemplazada')

    nueva = await conn.fetchrow(
        """
        insert into gd.digitalizacion_documento (
            tenant_id, radicado_id, archivo_digital_id, periferico_id,
            usuario_id, tipo_digitalizacion, calidad_dpi, estado,
            reemplaza_a_id, motivo_reemplazo
        ) values ($1, $2, $3, $4, $5, $6, $7, 'correcta', $8, $9)
        returning id, fecha_digitalizacion
        """,
        tenant_id, original['radicado_id'], archivo_digital_id_nuevo,
        original['periferico_id'], usuario_id,
        original['tipo_digitalizacion'], original['calidad_dpi'],
        digitalizacion_id, motivo,
    )

    # Marcar original como reemplazada.
    await conn.execute(
        """
        update gd.digitalizacion_documento
        set estado = 'reemplazada', motivo_reemplazo = $3,
            updated_at = now()
        where tenant_id = $1 and id = $2
        """,
        tenant_id, digitalizacion_id, motivo,
    )

    return {
        'digitalizacion_original_id': digitalizacion_id,
        'digitalizacion_nueva_id': nueva['id'],
        'motivo': motivo,
        'fecha': nueva['fecha_digitalizacion'],
    }


__all__ = [
    # Lote
    'iniciar_lote_digitalizacion', 'obtener_lote', 'progreso_lote',
    'finalizar_lote',
    # Contexto
    'upsert_contexto_activo', 'eliminar_contexto_activo',
    'obtener_contexto_activo',
    # Mantenimiento + dashboard
    'UMBRAL_AUTO_PROTECCION', 'listar_eventos_periferico',
    'agregado_fallos', 'chequear_auto_proteccion',
    'iniciar_mantenimiento', 'finalizar_mantenimiento',
    # Agente
    'emparejar_agente_local', 'revocar_agente_local', 'obtener_agente_local',
    # Historial + export
    'historial_periferico', 'historial_uso_global', 'export_historial',
    # Reemplazo
    'reemplazar_digitalizacion',
]
