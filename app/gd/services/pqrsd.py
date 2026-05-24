"""Services SQL para EP-007 PQRSD — bloque 7.

Funciones clave:
- crear_desde_radicado: handler reactivo a RadicadoClasificado(tipo='pqrsd').
- asignar_dependencia / asignar_funcionario / reasignar
- proyectar_respuesta
- suspender_termino / reanudar_termino con cálculo de fecha
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

import asyncpg


# =============================================================================
# Creación reactiva
# =============================================================================

async def crear_desde_radicado(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    radicado_id: UUID,
    tipo_pqrsd_id: UUID | None,
    sub_tipo: str | None = None,
) -> dict[str, Any] | None:
    """Crea gd.pqrsd a partir de un radicado clasificado como tipo='pqrsd'.

    Idempotente: si ya existe PQRSD para ese radicado, retorna None (no
    duplica). El handler de clasificar debe tolerar esto.

    fecha_limite_respuesta = gd.calcular_fecha_limite(tipo_pqrsd.termino_dias).
    """
    # Verificar idempotencia.
    existing = await conn.fetchval(
        """
        select 1 from gd.pqrsd
        where tenant_id = $1 and radicado_entrada_id = $2
        """,
        tenant_id, radicado_id,
    )
    if existing:
        return None

    # Leer datos del radicado.
    rad = await conn.fetchrow(
        """
        select id, asunto, descripcion, tercero_id, fecha_radicacion,
               actor_snapshot
        from gd.radicado where id = $1 and tenant_id = $2
        """,
        radicado_id, tenant_id,
    )
    if rad is None:
        raise ValueError(f'Radicado {radicado_id} no existe')

    # Calcular fecha_limite con calendario default si hay tipo_pqrsd.
    fecha_limite = None
    if tipo_pqrsd_id is not None:
        row = await conn.fetchrow(
            'select termino_dias, tipo_dias from gd.tipo_pqrsd where id = $1',
            tipo_pqrsd_id,
        )
        if row is not None:
            calc_row = await conn.fetchrow(
                'select gd.calcular_fecha_limite($1, $2, $3, $4) as fecha_limite',
                tenant_id, rad['fecha_radicacion'],
                row['termino_dias'], row['tipo_dias'],
            )
            fecha_limite = calc_row['fecha_limite']

    actor_snapshot = rad['actor_snapshot']
    if isinstance(actor_snapshot, str):
        actor_snapshot = json.loads(actor_snapshot or '{}')

    inserted = await conn.fetchrow(
        """
        insert into gd.pqrsd (
            tenant_id, radicado_entrada_id, tipo_pqrsd_id, tercero_id,
            asunto, descripcion, fecha_recepcion, fecha_limite_respuesta,
            estado, actor_snapshot
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, 'clasificada', $9::jsonb)
        returning id, radicado_entrada_id, tipo_pqrsd_id, tercero_id,
                  asunto, descripcion, dependencia_responsable_id,
                  usuario_responsable_id, fecha_recepcion, fecha_limite_respuesta,
                  estado, prioridad, reserva
        """,
        tenant_id, radicado_id, tipo_pqrsd_id, rad['tercero_id'],
        rad['asunto'], rad['descripcion'],
        rad['fecha_radicacion'], fecha_limite,
        json.dumps(actor_snapshot, default=str),
    )
    return dict(inserted)


# =============================================================================
# Lectura
# =============================================================================

async def obtener_pqrsd(
    conn: asyncpg.Connection, *, tenant_id: UUID, pqrsd_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, radicado_entrada_id, tipo_pqrsd_id, tercero_id,
               asunto, descripcion, dependencia_responsable_id,
               usuario_responsable_id, fecha_recepcion, fecha_limite_respuesta,
               estado, prioridad, reserva
        from gd.pqrsd
        where id = $1 and tenant_id = $2
        """,
        pqrsd_id, tenant_id,
    )
    return dict(row) if row else None


async def listar_pqrsd(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    estado: list[str] | None = None,
    dependencia_id: UUID | None = None,
    usuario_id: UUID | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    where = ['p.tenant_id = $1']
    params: list[Any] = [tenant_id]
    if estado:
        params.append(estado)
        where.append(f'p.estado = any(${len(params)}::text[])')
    if dependencia_id:
        params.append(dependencia_id)
        where.append(f'p.dependencia_responsable_id = ${len(params)}')
    if usuario_id:
        params.append(usuario_id)
        where.append(f'p.usuario_responsable_id = ${len(params)}')

    params.append(limit)
    rows = await conn.fetch(
        f"""
        select p.id, p.radicado_entrada_id, r.numero_radicado,
               p.asunto, p.estado, p.fecha_recepcion, p.fecha_limite_respuesta,
               p.dependencia_responsable_id, p.usuario_responsable_id
        from gd.pqrsd p
        join gd.radicado r on r.id = p.radicado_entrada_id
        where {' and '.join(where)}
        order by p.fecha_limite_respuesta asc nulls last, p.fecha_recepcion desc
        limit ${len(params)}
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def contar_pqrsd(conn: asyncpg.Connection, *, tenant_id: UUID) -> int:
    row = await conn.fetchrow(
        'select count(*) as c from gd.pqrsd where tenant_id = $1',
        tenant_id,
    )
    return int(row['c']) if row else 0


# =============================================================================
# Asignación
# =============================================================================

async def _cerrar_asignacion_vigente(
    conn: asyncpg.Connection, *, pqrsd_id: UUID, motivo: str,
    estado_cierre: str = 'cerrada',
) -> None:
    """Marca la vigente como cerrada/reasignada."""
    await conn.execute(
        """
        update gd.asignacion_pqrsd
        set estado = $2,
            fecha_fin = now(),
            motivo_cierre = $3
        where pqrsd_id = $1 and estado = 'activa'
        """,
        pqrsd_id, estado_cierre, motivo,
    )


async def asignar_a_dependencia(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    pqrsd_id: UUID,
    dependencia_id: UUID,
    asignado_por_user_id: UUID,
    motivo: str | None,
) -> dict[str, Any] | None:
    """Crea asignación a dependencia + actualiza pqrsd.dependencia_responsable_id."""
    pqrsd = await conn.fetchval(
        'select 1 from gd.pqrsd where id = $1 and tenant_id = $2',
        pqrsd_id, tenant_id,
    )
    if not pqrsd:
        return None

    # Cerrar vigente si existe.
    await _cerrar_asignacion_vigente(
        conn, pqrsd_id=pqrsd_id, motivo=motivo or 'Nueva asignación a dependencia',
    )

    # Crear nueva.
    row = await conn.fetchrow(
        """
        insert into gd.asignacion_pqrsd (
            tenant_id, pqrsd_id, dependencia_id, asignado_por_user_id,
            motivo, estado
        )
        values ($1, $2, $3, $4, $5, 'activa')
        returning id, pqrsd_id, dependencia_id, usuario_asignado_id,
                  asignado_por_user_id, fecha_asignacion, fecha_fin,
                  motivo, estado
        """,
        tenant_id, pqrsd_id, dependencia_id, asignado_por_user_id, motivo,
    )

    # Actualizar dependencia_responsable + estado.
    await conn.execute(
        """
        update gd.pqrsd
        set dependencia_responsable_id = $2,
            estado = case
                when estado in ('nueva', 'clasificada') then 'asignada'
                else estado
            end
        where id = $1
        """,
        pqrsd_id, dependencia_id,
    )
    return dict(row)


async def asignar_a_funcionario(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    pqrsd_id: UUID,
    usuario_id: UUID,
    asignado_por_user_id: UUID,
    motivo: str | None,
) -> dict[str, Any] | None:
    pqrsd = await conn.fetchval(
        'select 1 from gd.pqrsd where id = $1 and tenant_id = $2',
        pqrsd_id, tenant_id,
    )
    if not pqrsd:
        return None

    await _cerrar_asignacion_vigente(
        conn, pqrsd_id=pqrsd_id,
        motivo=motivo or 'Nueva asignación a funcionario',
    )

    row = await conn.fetchrow(
        """
        insert into gd.asignacion_pqrsd (
            tenant_id, pqrsd_id, usuario_asignado_id,
            asignado_por_user_id, motivo, estado
        )
        values ($1, $2, $3, $4, $5, 'activa')
        returning id, pqrsd_id, dependencia_id, usuario_asignado_id,
                  asignado_por_user_id, fecha_asignacion, fecha_fin,
                  motivo, estado
        """,
        tenant_id, pqrsd_id, usuario_id, asignado_por_user_id, motivo,
    )

    await conn.execute(
        """
        update gd.pqrsd
        set usuario_responsable_id = $2,
            estado = case
                when estado in ('nueva', 'clasificada') then 'asignada'
                else estado
            end
        where id = $1
        """,
        pqrsd_id, usuario_id,
    )
    return dict(row)


async def reasignar_pqrsd(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    pqrsd_id: UUID,
    dependencia_id: UUID | None,
    usuario_id: UUID | None,
    motivo: str,
    asignado_por_user_id: UUID,
) -> dict[str, Any] | None:
    pqrsd = await conn.fetchval(
        'select 1 from gd.pqrsd where id = $1 and tenant_id = $2',
        pqrsd_id, tenant_id,
    )
    if not pqrsd:
        return None

    await _cerrar_asignacion_vigente(
        conn, pqrsd_id=pqrsd_id, motivo=motivo, estado_cierre='reasignada',
    )

    row = await conn.fetchrow(
        """
        insert into gd.asignacion_pqrsd (
            tenant_id, pqrsd_id, dependencia_id, usuario_asignado_id,
            asignado_por_user_id, motivo, estado
        )
        values ($1, $2, $3, $4, $5, $6, 'activa')
        returning id, pqrsd_id, dependencia_id, usuario_asignado_id,
                  asignado_por_user_id, fecha_asignacion, fecha_fin,
                  motivo, estado
        """,
        tenant_id, pqrsd_id, dependencia_id, usuario_id,
        asignado_por_user_id, motivo,
    )

    # Actualizar campos resumen en pqrsd según corresponda.
    if dependencia_id is not None:
        await conn.execute(
            'update gd.pqrsd set dependencia_responsable_id = $2 where id = $1',
            pqrsd_id, dependencia_id,
        )
    if usuario_id is not None:
        await conn.execute(
            'update gd.pqrsd set usuario_responsable_id = $2 where id = $1',
            pqrsd_id, usuario_id,
        )

    return dict(row)


# =============================================================================
# Respuesta — proyectar
# =============================================================================

async def proyectar_respuesta(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    pqrsd_id: UUID,
    documento_id: UUID | None,
    plantilla_id: UUID | None,
    contenido_borrador: str | None,
    usuario_proyecta_id: UUID,
) -> dict[str, Any] | None:
    pqrsd = await conn.fetchval(
        'select 1 from gd.pqrsd where id = $1 and tenant_id = $2',
        pqrsd_id, tenant_id,
    )
    if not pqrsd:
        return None

    row = await conn.fetchrow(
        """
        insert into gd.respuesta_pqrsd (
            tenant_id, pqrsd_id, documento_id, plantilla_id,
            contenido_borrador, usuario_proyecta_id, estado
        )
        values ($1, $2, $3, $4, $5, $6, 'borrador')
        returning id, pqrsd_id, documento_id, plantilla_id,
                  contenido_borrador, usuario_proyecta_id,
                  usuario_revisa_id, usuario_aprueba_id, usuario_firma_id,
                  radicado_salida_id, estado,
                  fecha_proyeccion, fecha_revision, fecha_aprobacion,
                  fecha_firma, fecha_radicacion, fecha_envio
        """,
        tenant_id, pqrsd_id, documento_id, plantilla_id,
        contenido_borrador, usuario_proyecta_id,
    )

    # Mover estado pqrsd a en_analisis si era asignada.
    await conn.execute(
        """
        update gd.pqrsd
        set estado = case when estado = 'asignada' then 'en_analisis' else estado end
        where id = $1
        """,
        pqrsd_id,
    )
    return dict(row)


# =============================================================================
# Suspensión / reanudación (GD-API-0042)
# =============================================================================

async def suspender_termino(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    pqrsd_id: UUID,
    motivo: str,
    justificacion_legal: str | None,
    dias_estimados: int | None,
    usuario_id: UUID,
) -> dict[str, Any] | None:
    """Crea evento_termino_pqrsd 'suspension'.

    NO recalcula fecha_limite (la reanudación lo hace). El status quo: durante
    suspensión el reloj se detiene; cuando se reanuda se suman los días
    pendientes desde la fecha de reanudación.
    """
    pqrsd = await conn.fetchrow(
        'select fecha_limite_respuesta from gd.pqrsd where id = $1 and tenant_id = $2',
        pqrsd_id, tenant_id,
    )
    if pqrsd is None:
        return None

    row = await conn.fetchrow(
        """
        insert into gd.evento_termino_pqrsd (
            tenant_id, pqrsd_id, tipo_evento, motivo,
            justificacion_legal, dias_afectados,
            fecha_limite_anterior, usuario_id
        )
        values ($1, $2, 'suspension', $3, $4, $5, $6, $7)
        returning id, pqrsd_id, tipo_evento, fecha_evento, motivo,
                  justificacion_legal, dias_afectados,
                  fecha_limite_anterior, fecha_limite_nueva, usuario_id
        """,
        tenant_id, pqrsd_id, motivo, justificacion_legal,
        dias_estimados, pqrsd['fecha_limite_respuesta'], usuario_id,
    )
    return dict(row)


async def reanudar_termino(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    pqrsd_id: UUID,
    motivo: str,
    usuario_id: UUID,
) -> dict[str, Any] | None:
    """Recalcula fecha_limite sumando los días transcurridos desde la
    última suspensión."""
    pqrsd = await conn.fetchrow(
        'select fecha_limite_respuesta from gd.pqrsd where id = $1 and tenant_id = $2',
        pqrsd_id, tenant_id,
    )
    if pqrsd is None:
        return None

    # Buscar última suspensión sin reanudación.
    ult_susp = await conn.fetchrow(
        """
        select fecha_evento from gd.evento_termino_pqrsd
        where pqrsd_id = $1 and tipo_evento = 'suspension'
        order by fecha_evento desc limit 1
        """,
        pqrsd_id,
    )

    fecha_limite_anterior = pqrsd['fecha_limite_respuesta']
    fecha_limite_nueva = fecha_limite_anterior
    dias_afectados = 0

    if ult_susp is not None and fecha_limite_anterior is not None:
        # Sumar el lapso desde la suspensión hasta ahora.
        delta = datetime.now(ult_susp['fecha_evento'].tzinfo) - ult_susp['fecha_evento']
        dias_afectados = max(delta.days, 0)
        # En implementación rigurosa: usar gd.calcular_fecha_limite con días
        # hábiles. Por ahora suma directa (TODO refinamiento).
        from datetime import timedelta
        fecha_limite_nueva = fecha_limite_anterior + timedelta(days=dias_afectados)
        await conn.execute(
            'update gd.pqrsd set fecha_limite_respuesta = $2 where id = $1',
            pqrsd_id, fecha_limite_nueva,
        )

    row = await conn.fetchrow(
        """
        insert into gd.evento_termino_pqrsd (
            tenant_id, pqrsd_id, tipo_evento, motivo, dias_afectados,
            fecha_limite_anterior, fecha_limite_nueva, usuario_id
        )
        values ($1, $2, 'reanudacion', $3, $4, $5, $6, $7)
        returning id, pqrsd_id, tipo_evento, fecha_evento, motivo,
                  justificacion_legal, dias_afectados,
                  fecha_limite_anterior, fecha_limite_nueva, usuario_id
        """,
        tenant_id, pqrsd_id, motivo, dias_afectados,
        fecha_limite_anterior, fecha_limite_nueva, usuario_id,
    )
    return dict(row)


async def listar_eventos_termino(
    conn: asyncpg.Connection, *, tenant_id: UUID, pqrsd_id: UUID,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select id, pqrsd_id, tipo_evento, fecha_evento, motivo,
               justificacion_legal, dias_afectados,
               fecha_limite_anterior, fecha_limite_nueva, usuario_id
        from gd.evento_termino_pqrsd
        where tenant_id = $1 and pqrsd_id = $2
        order by fecha_evento desc
        """,
        tenant_id, pqrsd_id,
    )
    return [dict(r) for r in rows]


# =============================================================================
# BLOQUE 8 — EP-007 cierre PQRSD (GD-API-0047..0051)
# =============================================================================

# Mapeo: estado actual respuesta → estado destino + columna timestamp.
_WORKFLOW_TRANSICIONES: dict[str, dict[str, str]] = {
    'enviar_revision': {'from': 'borrador', 'to': 'en_revision', 'ts': 'fecha_revision'},
    'aprobar':         {'from': 'en_revision', 'to': 'aprobada', 'ts': 'fecha_aprobacion'},
    'firmar':          {'from': 'aprobada', 'to': 'firmada', 'ts': 'fecha_firma'},
    'radicar':         {'from': 'firmada', 'to': 'radicada', 'ts': 'fecha_radicacion'},
    'enviar':          {'from': 'radicada', 'to': 'enviada', 'ts': 'fecha_envio'},
}


async def _obtener_respuesta(
    conn: asyncpg.Connection, *, tenant_id: UUID, respuesta_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, pqrsd_id, documento_id, plantilla_id, contenido_borrador,
               usuario_proyecta_id, usuario_revisa_id, usuario_aprueba_id,
               usuario_firma_id, radicado_salida_id, estado,
               fecha_proyeccion, fecha_revision, fecha_aprobacion,
               fecha_firma, fecha_radicacion, fecha_envio,
               observaciones_devolucion
        from gd.respuesta_pqrsd
        where id = $1 and tenant_id = $2
        """,
        respuesta_id, tenant_id,
    )
    return dict(row) if row else None


async def enviar_respuesta_a_revision(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    respuesta_id: UUID,
    usuario_actor_id: UUID,
    observaciones: str | None = None,
) -> dict[str, Any] | None:
    """Workflow paso 1: borrador → en_revision.

    Solo el usuario que proyectó (o uno con permiso) puede invocarlo.
    En este punto no asignamos usuario_revisa aún (lo asigna el revisor al revisar).
    """
    resp = await _obtener_respuesta(
        conn, tenant_id=tenant_id, respuesta_id=respuesta_id,
    )
    if resp is None:
        return None
    if resp['estado'] != 'borrador':
        raise ValueError(f"estado_invalido:{resp['estado']}")

    row = await conn.fetchrow(
        """
        update gd.respuesta_pqrsd
        set estado = 'en_revision'
        where id = $1 and tenant_id = $2
        returning id, pqrsd_id, estado, fecha_proyeccion, fecha_revision,
                  fecha_aprobacion, fecha_firma, fecha_radicacion, fecha_envio,
                  usuario_proyecta_id, usuario_revisa_id, usuario_aprueba_id,
                  usuario_firma_id, radicado_salida_id, documento_id,
                  plantilla_id, contenido_borrador, observaciones_devolucion
        """,
        respuesta_id, tenant_id,
    )
    # Mover PQRSD a 'en_revision'.
    await conn.execute(
        """
        update gd.pqrsd set estado = 'en_revision'
        where id = $1 and estado in ('asignada','en_analisis')
        """,
        resp['pqrsd_id'],
    )
    return dict(row)


async def revisar_respuesta(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    respuesta_id: UUID,
    resultado: str,  # 'ok' | 'devolver'
    observaciones: str | None,
    usuario_actor_id: UUID,
) -> dict[str, Any] | None:
    """Workflow paso 2: en_revision → aprobada | devuelta.

    RNF-008 separación de funciones: el revisor NO puede ser el proyectista.
    """
    resp = await _obtener_respuesta(
        conn, tenant_id=tenant_id, respuesta_id=respuesta_id,
    )
    if resp is None:
        return None
    if resp['estado'] != 'en_revision':
        raise ValueError(f"estado_invalido:{resp['estado']}")
    if resp['usuario_proyecta_id'] == usuario_actor_id:
        raise PermissionError('separacion_funciones:proyecta==revisa')

    nuevo_estado = 'aprobada' if resultado == 'ok' else 'devuelta'
    row = await conn.fetchrow(
        """
        update gd.respuesta_pqrsd
        set estado = $3,
            usuario_revisa_id = $4,
            fecha_revision = now(),
            observaciones_devolucion = case when $3 = 'devuelta' then $5
                                            else observaciones_devolucion end
        where id = $1 and tenant_id = $2
        returning id, pqrsd_id, estado, fecha_proyeccion, fecha_revision,
                  fecha_aprobacion, fecha_firma, fecha_radicacion, fecha_envio,
                  usuario_proyecta_id, usuario_revisa_id, usuario_aprueba_id,
                  usuario_firma_id, radicado_salida_id, documento_id,
                  plantilla_id, contenido_borrador, observaciones_devolucion
        """,
        respuesta_id, tenant_id, nuevo_estado, usuario_actor_id, observaciones,
    )
    # Si fue devuelta, mover PQRSD a 'devuelta'; si fue aprobada, mantenerlo
    # en 'en_revision' (estará así hasta firma+envio).
    if nuevo_estado == 'devuelta':
        await conn.execute(
            "update gd.pqrsd set estado = 'devuelta' where id = $1", resp['pqrsd_id'],
        )
    return dict(row)


async def aprobar_respuesta(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    respuesta_id: UUID,
    usuario_actor_id: UUID,
    observaciones: str | None = None,
) -> dict[str, Any] | None:
    """Workflow paso 3: aprobada → aprobada (registro aprobador explícito).

    Nota: 'revisar' con resultado='ok' ya pasa a 'aprobada'. Esta función
    cubre el flujo cuando hay un aprobador distinto del revisor (jefe de
    dependencia, p.ej.).
    """
    resp = await _obtener_respuesta(
        conn, tenant_id=tenant_id, respuesta_id=respuesta_id,
    )
    if resp is None:
        return None
    if resp['estado'] != 'aprobada':
        raise ValueError(f"estado_invalido:{resp['estado']}")
    if resp['usuario_proyecta_id'] == usuario_actor_id:
        raise PermissionError('separacion_funciones:proyecta==aprueba')

    row = await conn.fetchrow(
        """
        update gd.respuesta_pqrsd
        set usuario_aprueba_id = $3,
            fecha_aprobacion = coalesce(fecha_aprobacion, now())
        where id = $1 and tenant_id = $2
        returning id, pqrsd_id, estado, fecha_proyeccion, fecha_revision,
                  fecha_aprobacion, fecha_firma, fecha_radicacion, fecha_envio,
                  usuario_proyecta_id, usuario_revisa_id, usuario_aprueba_id,
                  usuario_firma_id, radicado_salida_id, documento_id,
                  plantilla_id, contenido_borrador, observaciones_devolucion
        """,
        respuesta_id, tenant_id, usuario_actor_id,
    )
    await conn.execute(
        "update gd.pqrsd set estado = 'aprobada' where id = $1", resp['pqrsd_id'],
    )
    return dict(row)


async def firmar_respuesta(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    respuesta_id: UUID,
    usuario_actor_id: UUID,
    firma_id: UUID | None = None,
) -> dict[str, Any] | None:
    """Workflow paso 4: aprobada → firmada (delegado a EP-011).

    Por ahora, EP-011 no existe; este servicio solo registra timestamps.
    Cuando EP-011 entregue, este servicio invocará el módulo de firma real.
    """
    resp = await _obtener_respuesta(
        conn, tenant_id=tenant_id, respuesta_id=respuesta_id,
    )
    if resp is None:
        return None
    if resp['estado'] != 'aprobada':
        raise ValueError(f"estado_invalido:{resp['estado']}")
    if resp['usuario_proyecta_id'] == usuario_actor_id:
        raise PermissionError('separacion_funciones:proyecta==firma')

    row = await conn.fetchrow(
        """
        update gd.respuesta_pqrsd
        set estado = 'firmada',
            usuario_firma_id = $3,
            fecha_firma = now()
        where id = $1 and tenant_id = $2
        returning id, pqrsd_id, estado, fecha_proyeccion, fecha_revision,
                  fecha_aprobacion, fecha_firma, fecha_radicacion, fecha_envio,
                  usuario_proyecta_id, usuario_revisa_id, usuario_aprueba_id,
                  usuario_firma_id, radicado_salida_id, documento_id,
                  plantilla_id, contenido_borrador, observaciones_devolucion
        """,
        respuesta_id, tenant_id, usuario_actor_id,
    )
    await conn.execute(
        "update gd.pqrsd set estado = 'firmada' where id = $1", resp['pqrsd_id'],
    )
    return dict(row)


async def radicar_salida_respuesta(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    respuesta_id: UUID,
    usuario_actor_id: UUID,
    canal_envio_id: UUID | None = None,
) -> dict[str, Any] | None:
    """Workflow paso 5: firmada → radicada.

    Crea un radicado de salida con consecutivo via gd.siguiente_radicado.
    Vincula el radicado_salida_id a la respuesta.
    """
    from app.gd.services import consecutivos as svc_consec

    resp = await _obtener_respuesta(
        conn, tenant_id=tenant_id, respuesta_id=respuesta_id,
    )
    if resp is None:
        return None
    if resp['estado'] != 'firmada':
        raise ValueError(f"estado_invalido:{resp['estado']}")

    # Datos del PQRSD para construir el radicado de salida.
    pqrsd_row = await conn.fetchrow(
        """
        select asunto, descripcion, dependencia_responsable_id, tercero_id,
               radicado_entrada_id
        from gd.pqrsd where id = $1 and tenant_id = $2
        """,
        resp['pqrsd_id'], tenant_id,
    )
    if pqrsd_row is None:
        return None

    from datetime import datetime as _dt
    vigencia = _dt.now().year
    numero_radicado = await svc_consec.siguiente_radicado(
        conn, tenant_id=tenant_id, vigencia=vigencia, tipo_radicado='salida',
    )

    radicado_row = await conn.fetchrow(
        """
        insert into gd.radicado (
            tenant_id, numero_radicado, tipo_radicado, canal_id, estado,
            asunto, descripcion, tercero_destinatario_id, dependencia_origen_id,
            usuario_radicador_id, actor_snapshot, radicado_relacionado_id
        )
        values ($1, $2, 'salida', $3, 'radicado', $4, $5, $6, $7, $8, $9, $10)
        returning id, numero_radicado, fecha_radicacion
        """,
        tenant_id, numero_radicado, canal_envio_id,
        pqrsd_row['asunto'], pqrsd_row['descripcion'], pqrsd_row['tercero_id'],
        pqrsd_row['dependencia_responsable_id'], usuario_actor_id,
        json.dumps({'usuario_id': str(usuario_actor_id),
                    'origen': 'pqrsd_respuesta',
                    'pqrsd_id': str(resp['pqrsd_id'])}),
        pqrsd_row['radicado_entrada_id'],
    )

    row = await conn.fetchrow(
        """
        update gd.respuesta_pqrsd
        set estado = 'radicada',
            radicado_salida_id = $3,
            fecha_radicacion = now()
        where id = $1 and tenant_id = $2
        returning id, pqrsd_id, estado, fecha_proyeccion, fecha_revision,
                  fecha_aprobacion, fecha_firma, fecha_radicacion, fecha_envio,
                  usuario_proyecta_id, usuario_revisa_id, usuario_aprueba_id,
                  usuario_firma_id, radicado_salida_id, documento_id,
                  plantilla_id, contenido_borrador, observaciones_devolucion
        """,
        respuesta_id, tenant_id, radicado_row['id'],
    )
    return dict(row)


async def enviar_respuesta(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    respuesta_id: UUID,
    usuario_actor_id: UUID,
    canal_envio_id: UUID | None = None,
    constancia_envio_uri: str | None = None,
) -> dict[str, Any] | None:
    """Workflow paso 6: radicada → enviada.

    Mueve PQRSD a 'enviada' (lista para cerrar).
    """
    resp = await _obtener_respuesta(
        conn, tenant_id=tenant_id, respuesta_id=respuesta_id,
    )
    if resp is None:
        return None
    if resp['estado'] != 'radicada':
        raise ValueError(f"estado_invalido:{resp['estado']}")

    row = await conn.fetchrow(
        """
        update gd.respuesta_pqrsd
        set estado = 'enviada',
            fecha_envio = now(),
            metadata = metadata || jsonb_build_object(
                'canal_envio_id', $3::text,
                'constancia_envio_uri', $4::text
            )
        where id = $1 and tenant_id = $2
        returning id, pqrsd_id, estado, fecha_proyeccion, fecha_revision,
                  fecha_aprobacion, fecha_firma, fecha_radicacion, fecha_envio,
                  usuario_proyecta_id, usuario_revisa_id, usuario_aprueba_id,
                  usuario_firma_id, radicado_salida_id, documento_id,
                  plantilla_id, contenido_borrador, observaciones_devolucion
        """,
        respuesta_id, tenant_id,
        str(canal_envio_id) if canal_envio_id else None,
        constancia_envio_uri,
    )
    await conn.execute(
        "update gd.pqrsd set estado = 'enviada' where id = $1", resp['pqrsd_id'],
    )
    return dict(row)


# --- GD-API-0048: cerrar y reabrir ---

async def cerrar_pqrsd(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    pqrsd_id: UUID,
    motivo: str,
    usuario_actor_id: UUID,
    forzar_sin_respuesta: bool = False,
) -> dict[str, Any] | None:
    """Cierra una PQRSD.

    Requisitos:
    - Si forzar_sin_respuesta=False (default): debe haber al menos una respuesta
      en estado 'enviada' para esta PQRSD.
    - Si forzar_sin_respuesta=True: cierre por causal sin respuesta (motivo
      obligatorio, p. ej. retiro del solicitante o duplicado).
    """
    pqrsd = await conn.fetchrow(
        'select estado from gd.pqrsd where id = $1 and tenant_id = $2',
        pqrsd_id, tenant_id,
    )
    if pqrsd is None:
        return None
    if pqrsd['estado'] in ('cerrada', 'anulada', 'trasladada'):
        raise ValueError(f"estado_invalido:{pqrsd['estado']}")

    if not forzar_sin_respuesta:
        respuesta_enviada = await conn.fetchval(
            """
            select 1 from gd.respuesta_pqrsd
            where pqrsd_id = $1 and tenant_id = $2 and estado = 'enviada'
            limit 1
            """,
            pqrsd_id, tenant_id,
        )
        if not respuesta_enviada:
            raise ValueError('sin_respuesta_enviada')

    row = await conn.fetchrow(
        """
        update gd.pqrsd
        set estado = 'cerrada',
            cerrada_en = now(),
            cerrada_por_user_id = $3,
            motivo_cierre = $4
        where id = $1 and tenant_id = $2
        returning id, radicado_entrada_id, tipo_pqrsd_id, tercero_id,
                  asunto, descripcion, dependencia_responsable_id,
                  usuario_responsable_id, fecha_recepcion,
                  fecha_limite_respuesta, estado, prioridad, reserva
        """,
        pqrsd_id, tenant_id, usuario_actor_id, motivo,
    )
    return dict(row)


async def reabrir_pqrsd(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    pqrsd_id: UUID,
    motivo: str,
    dias_adicionales: int,
    usuario_actor_id: UUID,
) -> dict[str, Any] | None:
    """Reabre una PQRSD cerrada.

    - Estado pasa a 'asignada' (recupera asignación si existe).
    - fecha_limite_respuesta = now() + dias_adicionales.
    - Registra evento de auditoría con motivo.
    """
    pqrsd = await conn.fetchrow(
        'select estado from gd.pqrsd where id = $1 and tenant_id = $2',
        pqrsd_id, tenant_id,
    )
    if pqrsd is None:
        return None
    if pqrsd['estado'] != 'cerrada':
        raise ValueError(f"estado_invalido:{pqrsd['estado']}")

    row = await conn.fetchrow(
        """
        update gd.pqrsd
        set estado = 'asignada',
            reabierta_en = now(),
            reabierta_por_user_id = $3,
            motivo_reapertura = $4,
            fecha_limite_respuesta = now() + ($5 || ' days')::interval
        where id = $1 and tenant_id = $2
        returning id, radicado_entrada_id, tipo_pqrsd_id, tercero_id,
                  asunto, descripcion, dependencia_responsable_id,
                  usuario_responsable_id, fecha_recepcion,
                  fecha_limite_respuesta, estado, prioridad, reserva
        """,
        pqrsd_id, tenant_id, usuario_actor_id, motivo, str(dias_adicionales),
    )
    return dict(row)


# --- GD-API-0049: traslado por competencia ---

async def trasladar_competencia(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    pqrsd_id: UUID,
    entidad_competente_destino: str,
    motivo: str,
    usuario_actor_id: UUID,
    oficio_traslado_radicado_id: UUID | None = None,
) -> dict[str, Any] | None:
    """Traslada la PQRSD por competencia a otra entidad.

    - Estado pasa a 'trasladada'.
    - Registra evento en gd.evento_termino_pqrsd (tipo='traslado_competencia').
    - Cierra asignaciones vigentes (estado='cerrada', motivo_cierre='traslado').
    """
    pqrsd = await conn.fetchrow(
        """
        select estado, fecha_limite_respuesta
        from gd.pqrsd where id = $1 and tenant_id = $2
        """,
        pqrsd_id, tenant_id,
    )
    if pqrsd is None:
        return None
    if pqrsd['estado'] in ('cerrada', 'anulada', 'trasladada'):
        raise ValueError(f"estado_invalido:{pqrsd['estado']}")

    row = await conn.fetchrow(
        """
        update gd.pqrsd
        set estado = 'trasladada',
            trasladada_en = now(),
            trasladada_por_user_id = $3,
            entidad_competente_destino = $4,
            motivo_traslado = $5,
            oficio_traslado_radicado_id = $6
        where id = $1 and tenant_id = $2
        returning id, radicado_entrada_id, tipo_pqrsd_id, tercero_id,
                  asunto, descripcion, dependencia_responsable_id,
                  usuario_responsable_id, fecha_recepcion,
                  fecha_limite_respuesta, estado, prioridad, reserva
        """,
        pqrsd_id, tenant_id, usuario_actor_id, entidad_competente_destino,
        motivo, oficio_traslado_radicado_id,
    )

    # Registrar evento de término (traslado).
    await conn.execute(
        """
        insert into gd.evento_termino_pqrsd
            (tenant_id, pqrsd_id, tipo_evento, motivo,
             fecha_limite_anterior, fecha_limite_nueva, usuario_id)
        values ($1, $2, 'traslado_competencia', $3, $4, null, $5)
        """,
        tenant_id, pqrsd_id, motivo, pqrsd['fecha_limite_respuesta'],
        usuario_actor_id,
    )

    # Cerrar asignaciones vigentes.
    await conn.execute(
        """
        update gd.asignacion_pqrsd
        set estado = 'cerrada',
            fecha_fin = now(),
            motivo_cierre = 'traslado_competencia'
        where pqrsd_id = $1 and tenant_id = $2 and estado = 'activa'
        """,
        pqrsd_id, tenant_id,
    )

    return dict(row)


# --- GD-API-0050: solicitar información adicional ---

async def solicitar_info_adicional(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    pqrsd_id: UUID,
    motivo: str,
    informacion_solicitada: str,
    dias_estimados_suspension: int,
    usuario_actor_id: UUID,
) -> dict[str, Any] | None:
    """Solicita información adicional al solicitante y pausa el término.

    Internamente se comporta como suspender_termino pero registra
    tipo_evento='solicitud_info_adicional' con la información solicitada
    en justificacion_legal.
    """
    pqrsd = await conn.fetchrow(
        'select estado, fecha_limite_respuesta from gd.pqrsd where id = $1 and tenant_id = $2',
        pqrsd_id, tenant_id,
    )
    if pqrsd is None:
        return None
    if pqrsd['estado'] in ('cerrada', 'anulada', 'trasladada'):
        raise ValueError(f"estado_invalido:{pqrsd['estado']}")

    fecha_anterior = pqrsd['fecha_limite_respuesta']

    row = await conn.fetchrow(
        """
        insert into gd.evento_termino_pqrsd
            (tenant_id, pqrsd_id, tipo_evento, motivo, justificacion_legal,
             dias_afectados, fecha_limite_anterior, fecha_limite_nueva, usuario_id)
        values ($1, $2, 'solicitud_info_adicional', $3, $4, $5, $6, null, $7)
        returning id, pqrsd_id, tipo_evento, fecha_evento, motivo,
                  justificacion_legal, dias_afectados,
                  fecha_limite_anterior, fecha_limite_nueva, usuario_id
        """,
        tenant_id, pqrsd_id, motivo, informacion_solicitada,
        dias_estimados_suspension, fecha_anterior, usuario_actor_id,
    )

    # Marcar fecha_limite_respuesta como null para indicar suspensión.
    await conn.execute(
        """
        update gd.pqrsd
        set fecha_limite_respuesta = null
        where id = $1 and tenant_id = $2
        """,
        pqrsd_id, tenant_id,
    )
    return dict(row)


# --- GD-API-0051: dashboard agregado ---

async def dashboard_pqrsd(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    dependencia_id: UUID | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
) -> dict[str, Any]:
    """Calcula agregaciones para el dashboard PQRSD.

    Retorna {total_global, total_vencidas, total_proximas_vencer,
             total_cerradas, buckets:[{...}]}.
    Filtros opcionales: dependencia_id, desde, hasta (fecha_recepcion).
    """
    where_parts = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if dependencia_id is not None:
        params.append(dependencia_id)
        where_parts.append(f'dependencia_responsable_id = ${len(params)}')
    if desde is not None:
        params.append(desde)
        where_parts.append(f'fecha_recepcion >= ${len(params)}')
    if hasta is not None:
        params.append(hasta)
        where_parts.append(f'fecha_recepcion <= ${len(params)}')

    where_sql = ' and '.join(where_parts)

    # Totales globales (sin agrupar).
    totales = await conn.fetchrow(
        f"""
        select
          count(*) as total_global,
          count(*) filter (where fecha_limite_respuesta is not null
                           and fecha_limite_respuesta < now()
                           and estado in ('nueva','asignada','en_analisis','en_revision'))
                                                  as total_vencidas,
          count(*) filter (where fecha_limite_respuesta is not null
                           and fecha_limite_respuesta >= now()
                           and fecha_limite_respuesta < now() + interval '3 days'
                           and estado in ('nueva','asignada','en_analisis','en_revision'))
                                                  as total_proximas_vencer,
          count(*) filter (where estado = 'cerrada')
                                                  as total_cerradas
        from gd.pqrsd
        where {where_sql}
        """,
        *params,
    )

    buckets_rows = await conn.fetch(
        f"""
        select
          dependencia_responsable_id as dependencia_id,
          estado,
          tipo_pqrsd_id,
          count(*) as total,
          count(*) filter (where fecha_limite_respuesta is not null
                           and fecha_limite_respuesta < now()
                           and estado in ('nueva','asignada','en_analisis','en_revision'))
                                                  as vencidas,
          count(*) filter (where fecha_limite_respuesta is not null
                           and fecha_limite_respuesta >= now()
                           and fecha_limite_respuesta < now() + interval '3 days'
                           and estado in ('nueva','asignada','en_analisis','en_revision'))
                                                  as proximas_vencer,
          avg(extract(epoch from (coalesce(cerrada_en, now()) - fecha_recepcion))/86400)::numeric(10,2)
                                                  as dias_promedio_resolucion
        from gd.pqrsd
        where {where_sql}
        group by dependencia_responsable_id, estado, tipo_pqrsd_id
        order by estado
        """,
        *params,
    )

    return {
        'total_global':           int(totales['total_global']) if totales else 0,
        'total_vencidas':         int(totales['total_vencidas']) if totales else 0,
        'total_proximas_vencer':  int(totales['total_proximas_vencer']) if totales else 0,
        'total_cerradas':         int(totales['total_cerradas']) if totales else 0,
        'buckets': [
            {
                'dependencia_id':            b['dependencia_id'],
                'estado':                    b['estado'],
                'tipo_pqrsd_id':             b['tipo_pqrsd_id'],
                'total':                     int(b['total']),
                'vencidas':                  int(b['vencidas']),
                'proximas_vencer':           int(b['proximas_vencer']),
                'dias_promedio_resolucion':  float(b['dias_promedio_resolucion'])
                                              if b['dias_promedio_resolucion'] is not None else None,
            }
            for b in buckets_rows
        ],
    }


__all__ = [
    'crear_desde_radicado', 'obtener_pqrsd', 'listar_pqrsd', 'contar_pqrsd',
    'asignar_a_dependencia', 'asignar_a_funcionario', 'reasignar_pqrsd',
    'proyectar_respuesta',
    'suspender_termino', 'reanudar_termino', 'listar_eventos_termino',
    # bloque 8
    'enviar_respuesta_a_revision', 'revisar_respuesta', 'aprobar_respuesta',
    'firmar_respuesta', 'radicar_salida_respuesta', 'enviar_respuesta',
    'cerrar_pqrsd', 'reabrir_pqrsd',
    'trasladar_competencia', 'solicitar_info_adicional',
    'dashboard_pqrsd',
]
