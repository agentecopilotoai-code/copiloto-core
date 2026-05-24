"""Services SQL para GD-API-0024..0029 — Radicado + clasificación + anulación.

Es el archivo de service más grande del módulo. Orquesta:
- gd.siguiente_radicado (consecutivos)
- generar_codigo_verificacion (helper Python)
- INSERT en gd.radicado + clasificacion + audit snapshot
- Búsqueda multi-criterio
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg

from app.gd.services import codigo_verificacion as cv_helper
from app.gd.services import consecutivos as svc_consec


# Máximo de reintentos para resolver colisión de codigo_verificacion (~1 en 1B).
_MAX_CODIGO_RETRIES = 5


# =============================================================================
# Crear radicado (entrada/salida)
# =============================================================================

async def crear_radicado(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    tipo_radicado: str,
    canal_id: UUID,
    asunto: str,
    descripcion: str | None,
    tercero_id: UUID | None,
    tercero_destinatario_id: UUID | None,
    dependencia_origen_id: UUID | None,
    dependencia_destino_id: UUID | None,
    documento_principal_id: UUID | None,
    usuario_radicador_id: UUID,
    actor_snapshot: dict[str, Any],
    radicado_relacionado_id: UUID | None = None,
    punto_atencion_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Crea radicado generando consecutivo + código_verificacion."""
    vigencia = datetime.now().year

    # 1. Generar número de radicado vía función SQL atómica.
    numero_radicado = await svc_consec.siguiente_radicado(
        conn, tenant_id=tenant_id,
        vigencia=vigencia, tipo_radicado=tipo_radicado,
    )

    # 2. Generar código de verificación único (reintentar si colisión).
    codigo = None
    for _ in range(_MAX_CODIGO_RETRIES):
        candidato = cv_helper.generar_codigo_verificacion()
        colision = await conn.fetchval(
            """
            select 1 from gd.radicado
            where tenant_id = $1 and codigo_verificacion = $2
            limit 1
            """,
            tenant_id, candidato,
        )
        if not colision:
            codigo = candidato
            break
    if codigo is None:
        raise RuntimeError(
            f'No se pudo generar código de verificación único tras {_MAX_CODIGO_RETRIES} intentos'
        )

    # 3. INSERT del radicado.
    row = await conn.fetchrow(
        """
        insert into gd.radicado (
            tenant_id, numero_radicado, tipo_radicado,
            canal_id, punto_atencion_id, asunto, descripcion,
            tercero_id, tercero_destinatario_id,
            dependencia_origen_id, dependencia_destino_id,
            documento_principal_id, usuario_radicador_id,
            radicado_relacionado_id, codigo_verificacion,
            actor_snapshot, metadata, estado
        )
        values (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
            $11, $12, $13, $14, $15, $16::jsonb, $17::jsonb, 'registrado'
        )
        returning id, tenant_id, numero_radicado, tipo_radicado,
                  fecha_radicacion, canal_id, punto_atencion_id,
                  asunto, descripcion, tercero_id, tercero_destinatario_id,
                  dependencia_origen_id, dependencia_destino_id,
                  documento_principal_id, usuario_radicador_id, estado,
                  radicado_relacionado_id, codigo_verificacion,
                  es_radicacion_contingencia, actor_snapshot, created_at
        """,
        tenant_id, numero_radicado, tipo_radicado,
        canal_id, punto_atencion_id, asunto, descripcion,
        tercero_id, tercero_destinatario_id,
        dependencia_origen_id, dependencia_destino_id,
        documento_principal_id, usuario_radicador_id,
        radicado_relacionado_id, codigo,
        json.dumps(actor_snapshot, default=str),
        json.dumps(metadata or {}, default=str),
    )
    return dict(row)


# =============================================================================
# Consultar
# =============================================================================

async def obtener_radicado(
    conn: asyncpg.Connection, *, tenant_id: UUID, radicado_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select r.id, r.tenant_id, r.numero_radicado, r.tipo_radicado,
               r.fecha_radicacion, r.canal_id, c.codigo as canal_codigo, c.nombre as canal_nombre,
               r.punto_atencion_id, r.asunto, r.descripcion,
               r.tercero_id, r.tercero_destinatario_id,
               r.dependencia_origen_id, r.dependencia_destino_id,
               r.documento_principal_id, r.usuario_radicador_id, r.estado,
               r.radicado_relacionado_id, r.codigo_verificacion,
               r.es_radicacion_contingencia, r.actor_snapshot
        from gd.radicado r
        join gd.canal c on c.id = r.canal_id
        where r.id = $1 and r.tenant_id = $2
        """,
        radicado_id, tenant_id,
    )
    return dict(row) if row else None


async def obtener_radicado_por_codigo(
    conn: asyncpg.Connection, *, tenant_id: UUID, codigo: str,
) -> dict[str, Any] | None:
    """Lookup público por codigo_verificacion."""
    row = await conn.fetchrow(
        """
        select id, tenant_id, numero_radicado, tipo_radicado,
               fecha_radicacion, asunto, estado, codigo_verificacion
        from gd.radicado
        where tenant_id = $1 and codigo_verificacion = $2
        """,
        tenant_id, codigo,
    )
    return dict(row) if row else None


async def buscar_radicados(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    numero_radicado: str | None = None,
    q: str | None = None,
    tipo_radicado: list[str] | None = None,
    estado: list[str] | None = None,
    canal_id: UUID | None = None,
    dependencia_destino_id: UUID | None = None,
    tercero_id: UUID | None = None,
    fecha_desde: datetime | None = None,
    fecha_hasta: datetime | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Búsqueda multi-criterio. Resultado plano sin JOINs pesados."""
    where_parts: list[str] = ['r.tenant_id = $1']
    params: list[Any] = [tenant_id]

    if numero_radicado:
        params.append(numero_radicado)
        where_parts.append(f'r.numero_radicado = ${len(params)}')

    if tipo_radicado:
        params.append(tipo_radicado)
        where_parts.append(f'r.tipo_radicado = any(${len(params)}::text[])')

    if estado:
        params.append(estado)
        where_parts.append(f'r.estado = any(${len(params)}::text[])')

    if canal_id:
        params.append(canal_id)
        where_parts.append(f'r.canal_id = ${len(params)}')

    if dependencia_destino_id:
        params.append(dependencia_destino_id)
        where_parts.append(f'r.dependencia_destino_id = ${len(params)}')

    if tercero_id:
        params.append(tercero_id)
        where_parts.append(f'r.tercero_id = ${len(params)}')

    if fecha_desde:
        params.append(fecha_desde)
        where_parts.append(f'r.fecha_radicacion >= ${len(params)}')

    if fecha_hasta:
        params.append(fecha_hasta)
        where_parts.append(f'r.fecha_radicacion <= ${len(params)}')

    if q:
        params.append(q)
        where_parts.append(
            f"to_tsvector('spanish', r.asunto || ' ' || coalesce(r.descripcion, '')) "
            f"@@ plainto_tsquery('spanish', ${len(params)})"
        )

    params.append(limit)
    sql = f"""
        select r.id, r.numero_radicado, r.tipo_radicado,
               r.fecha_radicacion, r.asunto, r.estado, r.canal_id,
               c.codigo as canal_codigo, c.nombre as canal_nombre,
               r.tercero_id, r.dependencia_destino_id,
               (select count(*) from gd.anexo a
                where a.radicado_id = r.id) as anexos_count,
               (select cr.tipo_clasificacion from gd.clasificacion_radicado cr
                where cr.radicado_id = r.id and cr.estado = 'vigente'
                limit 1) as clasificacion_tipo
        from gd.radicado r
        join gd.canal c on c.id = r.canal_id
        where {' and '.join(where_parts)}
        order by r.fecha_radicacion desc
        limit ${len(params)}
    """
    # NOTE: gd.anexo no existe aún (EP-009) — la sub-query devuelve 0
    # automáticamente cuando la tabla esté vacía. Cuando EP-009 introduzca
    # gd.anexo, las queries existentes ya están preparadas.
    # TODO(human): cuando gd.anexo exista, validar que el index el FK
    # acelera esta subconsulta — agregar EXPLAIN ANALYZE en test de carga.
    try:
        rows = await conn.fetch(sql, *params)
    except asyncpg.UndefinedTableError:
        # Fallback: si gd.anexo no existe aún, simplificar query.
        sql_fallback = sql.replace(
            "(select count(*) from gd.anexo a\n                where a.radicado_id = r.id)",
            "0",
        )
        rows = await conn.fetch(sql_fallback, *params)
    return [dict(r) for r in rows]


async def contar_radicados(
    conn: asyncpg.Connection, *, tenant_id: UUID,
) -> int:
    row = await conn.fetchrow(
        'select count(*) as c from gd.radicado where tenant_id = $1',
        tenant_id,
    )
    return int(row['c']) if row else 0


# =============================================================================
# Clasificación
# =============================================================================

async def clasificar_radicado(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    radicado_id: UUID,
    tipo_clasificacion: str,
    sub_tipo: str | None,
    dependencia_destino_id: UUID | None,
    tipo_pqrsd_id: UUID | None,
    justificacion: str | None,
    sugerencia_ia_id: UUID | None,
    clasificado_por_user_id: UUID,
) -> dict[str, Any] | None:
    """Crea clasificación vigente. None si el radicado ya tiene una vigente
    (caller debe usar reclasificar en su lugar)."""
    # Verificar que no hay clasificación vigente.
    existing = await conn.fetchval(
        """
        select 1 from gd.clasificacion_radicado
        where radicado_id = $1 and estado = 'vigente'
        """,
        radicado_id,
    )
    if existing:
        return None

    fuente = 'ia_aceptada' if sugerencia_ia_id else 'manual'

    row = await conn.fetchrow(
        """
        insert into gd.clasificacion_radicado (
            tenant_id, radicado_id, tipo_clasificacion, sub_tipo,
            dependencia_destino_id, tipo_pqrsd_id, justificacion,
            sugerencia_ia_id, fuente, clasificado_por_user_id, estado
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'vigente')
        returning id, radicado_id, tipo_clasificacion, sub_tipo,
                  dependencia_destino_id, tipo_pqrsd_id, fuente,
                  clasificado_por_user_id, fecha_clasificacion, estado
        """,
        tenant_id, radicado_id, tipo_clasificacion, sub_tipo,
        dependencia_destino_id, tipo_pqrsd_id, justificacion,
        sugerencia_ia_id, fuente, clasificado_por_user_id,
    )

    # Cambiar estado del radicado a 'clasificado'.
    await conn.execute(
        """
        update gd.radicado set estado = 'clasificado'
        where id = $1 and estado = 'registrado'
        """,
        radicado_id,
    )

    return dict(row)


async def reclasificar_radicado(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    radicado_id: UUID,
    tipo_clasificacion: str,
    sub_tipo: str | None,
    dependencia_destino_id: UUID | None,
    tipo_pqrsd_id: UUID | None,
    justificacion: str | None,
    sugerencia_ia_id: UUID | None,
    motivo: str,
    clasificado_por_user_id: UUID,
) -> dict[str, Any] | None:
    """Crea nueva clasificación vigente + marca anterior como reemplazada.

    None si no había clasificación vigente (caller debe usar clasificar en su lugar).
    """
    # Buscar la vigente actual.
    actual = await conn.fetchrow(
        """
        select id from gd.clasificacion_radicado
        where radicado_id = $1 and estado = 'vigente'
        """,
        radicado_id,
    )
    if actual is None:
        return None

    fuente = 'ia_aceptada' if sugerencia_ia_id else 'manual'

    # Crear nueva vigente.
    row_nueva = await conn.fetchrow(
        """
        insert into gd.clasificacion_radicado (
            tenant_id, radicado_id, tipo_clasificacion, sub_tipo,
            dependencia_destino_id, tipo_pqrsd_id, justificacion,
            sugerencia_ia_id, fuente, clasificado_por_user_id, estado,
            motivo_reclasificacion
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'vigente', $11)
        returning id, radicado_id, tipo_clasificacion, sub_tipo,
                  dependencia_destino_id, tipo_pqrsd_id, fuente,
                  clasificado_por_user_id, fecha_clasificacion, estado
        """,
        tenant_id, radicado_id, tipo_clasificacion, sub_tipo,
        dependencia_destino_id, tipo_pqrsd_id, justificacion,
        sugerencia_ia_id, fuente, clasificado_por_user_id, motivo,
    )

    # Marcar anterior como reemplazada + enlazar.
    await conn.execute(
        """
        update gd.clasificacion_radicado
        set estado = 'reemplazada', reemplazada_por_id = $2
        where id = $1
        """,
        actual['id'], row_nueva['id'],
    )

    return dict(row_nueva)


# =============================================================================
# Anulación
# =============================================================================

async def crear_solicitud_anulacion(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    tipo_entidad: str,
    entidad_afectada_id: UUID,
    solicitante_user_id: UUID,
    motivo: str,
    evidencia_archivo_digital_id: UUID | None,
) -> dict[str, Any] | None:
    """Crea solicitud. None si ya hay una pendiente para la misma entidad."""
    # Verificar no haya pendiente duplicada.
    existing = await conn.fetchval(
        """
        select 1 from gd.solicitud_anulacion
        where tenant_id = $1
          and tipo_entidad = $2
          and entidad_afectada_id = $3
          and decision = 'pendiente'
        """,
        tenant_id, tipo_entidad, entidad_afectada_id,
    )
    if existing:
        return None

    row = await conn.fetchrow(
        """
        insert into gd.solicitud_anulacion (
            tenant_id, tipo_entidad, entidad_afectada_id,
            solicitante_user_id, motivo, evidencia_archivo_digital_id,
            decision
        )
        values ($1, $2, $3, $4, $5, $6, 'pendiente')
        returning id, tipo_entidad, entidad_afectada_id,
                  solicitante_user_id, motivo, decision, fecha_solicitud
        """,
        tenant_id, tipo_entidad, entidad_afectada_id,
        solicitante_user_id, motivo, evidencia_archivo_digital_id,
    )
    return dict(row)


async def obtener_solicitud_anulacion(
    conn: asyncpg.Connection, *, tenant_id: UUID, solicitud_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, tipo_entidad, entidad_afectada_id,
               solicitante_user_id, motivo, decision,
               aprobador_user_id, observacion_decision,
               fecha_solicitud, fecha_decision
        from gd.solicitud_anulacion
        where id = $1 and tenant_id = $2
        """,
        solicitud_id, tenant_id,
    )
    return dict(row) if row else None


async def aprobar_solicitud(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    solicitud_id: UUID,
    aprobador_user_id: UUID,
    observacion_decision: str | None,
) -> dict[str, Any] | None:
    """Aprueba la solicitud + ejecuta la anulación efectiva del radicado.

    Si tipo_entidad != 'radicado' (documento/pqrsd/correspondencia) — solo
    aprueba la solicitud pero la anulación efectiva la maneja el dominio
    correspondiente (handlers de EP-009/EP-007/EP-008 reaccionan al evento).
    """
    row = await conn.fetchrow(
        """
        update gd.solicitud_anulacion
        set decision = 'aprobada',
            aprobador_user_id = $3,
            observacion_decision = $4,
            fecha_decision = now()
        where id = $2 and tenant_id = $1 and decision = 'pendiente'
        returning id, tipo_entidad, entidad_afectada_id,
                  aprobador_user_id, fecha_decision
        """,
        tenant_id, solicitud_id, aprobador_user_id, observacion_decision,
    )
    if row is None:
        return None

    # Si tipo_entidad='radicado', ejecutar anulación efectiva.
    if row['tipo_entidad'] == 'radicado':
        await conn.execute(
            """
            update gd.radicado
            set estado = 'anulado',
                anulado_en = now(),
                anulado_por_user_id = $2
            where id = $1
            """,
            row['entidad_afectada_id'], aprobador_user_id,
        )

    return dict(row)


async def rechazar_solicitud(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    solicitud_id: UUID,
    aprobador_user_id: UUID,
    observacion_decision: str,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        update gd.solicitud_anulacion
        set decision = 'rechazada',
            aprobador_user_id = $3,
            observacion_decision = $4,
            fecha_decision = now()
        where id = $2 and tenant_id = $1 and decision = 'pendiente'
        returning id, tipo_entidad, entidad_afectada_id,
                  aprobador_user_id, fecha_decision
        """,
        tenant_id, solicitud_id, aprobador_user_id, observacion_decision,
    )
    return dict(row) if row else None


__all__ = [
    'crear_radicado', 'obtener_radicado', 'obtener_radicado_por_codigo',
    'buscar_radicados', 'contar_radicados',
    'clasificar_radicado', 'reclasificar_radicado',
    'crear_solicitud_anulacion', 'obtener_solicitud_anulacion',
    'aprobar_solicitud', 'rechazar_solicitud',
]
