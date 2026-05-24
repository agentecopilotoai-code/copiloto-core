"""Services SQL para EP-008 correspondencia (bloque 9).

Cubre correspondencia interna, externa recibida y externa enviada:
- crear_interna / responder / reenviar / marcar_leida (interna)
- crear_desde_radicado_externa (hook reactivo desde clasificar)
- listar_externa_recibida / gestionar_externa_recibida
- crear_externa_enviada_borrador + workflow_*
- registrar_soporte_envio
- solicitar_anulacion / aprobar_anulacion / rechazar_anulacion
- listar_correspondencia (filtros)
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable
from uuid import UUID

import asyncpg


# =============================================================================
# Helpers
# =============================================================================

async def _validar_regla_comunicacion(
    conn: asyncpg.Connection, *, tenant_id: UUID,
    dependencia_origen_id: UUID, dependencia_destino_id: UUID,
) -> None:
    """Valida gd.regla_comunicacion_interdependencia.

    Default permisivo: si NO existe regla explícita, se permite.
    Si existe y permitido=false → ValueError('comunicacion_no_permitida').
    """
    if dependencia_origen_id == dependencia_destino_id:
        # Misma dependencia siempre permitido.
        return
    row = await conn.fetchrow(
        """
        select permitido from gd.regla_comunicacion_interdependencia
        where tenant_id = $1 and dependencia_origen_id = $2
          and dependencia_destino_id = $3 and estado = 'activa'
        """,
        tenant_id, dependencia_origen_id, dependencia_destino_id,
    )
    if row is not None and not row['permitido']:
        raise ValueError('comunicacion_no_permitida')


async def _insertar_destinatarios(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, correspondencia_id: UUID,
    destinatarios: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Inserta múltiples destinatarios en una sola pasada.

    Cada dict debe traer keys: tipo_destinatario, dependencia_id, tercero_id,
    tipo_copia.
    """
    rows = []
    for d in destinatarios:
        row = await conn.fetchrow(
            """
            insert into gd.destinatario_correspondencia (
                tenant_id, correspondencia_id, tipo_destinatario,
                dependencia_id, tercero_id, tipo_copia
            )
            values ($1, $2, $3, $4, $5, $6)
            returning id, correspondencia_id, tipo_destinatario,
                      dependencia_id, tercero_id, tipo_copia,
                      fecha_lectura, leida_por_user_id
            """,
            tenant_id, correspondencia_id, d['tipo_destinatario'],
            d.get('dependencia_id'), d.get('tercero_id'),
            d.get('tipo_copia', 'principal'),
        )
        rows.append(dict(row))
    return rows


async def _listar_destinatarios(
    conn: asyncpg.Connection, *, correspondencia_id: UUID,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select id, correspondencia_id, tipo_destinatario,
               dependencia_id, tercero_id, tipo_copia,
               fecha_lectura, leida_por_user_id
        from gd.destinatario_correspondencia
        where correspondencia_id = $1
        order by case tipo_copia
                   when 'principal' then 0 when 'copia' then 1 else 2 end,
                 created_at
        """,
        correspondencia_id,
    )
    return [dict(r) for r in rows]


_SELECT_CORRESPONDENCIA = """
select id, tipo, dependencia_origen_id, dependencia_destino_id,
       tercero_remitente_id, radicado_entrada_id, radicado_salida_id,
       documento_principal_id, plantilla_id, asunto, contenido_borrador,
       prioridad, requiere_respuesta, fecha_limite_respuesta, estado,
       usuario_proyecta_id, usuario_revisa_id, usuario_aprueba_id,
       usuario_firma_id, usuario_envio_id,
       fecha_envio, fecha_aprobacion, fecha_firma, fecha_radicacion,
       observaciones_devolucion,
       canal_envio_id, soporte_envio_uri, soporte_envio_codigo_rastreo,
       fecha_registro_soporte,
       anulada_en, motivo_anulacion, correspondencia_padre_id,
       created_at
from gd.correspondencia
"""


async def obtener_correspondencia(
    conn: asyncpg.Connection, *, tenant_id: UUID, correspondencia_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        _SELECT_CORRESPONDENCIA + ' where id = $1 and tenant_id = $2',
        correspondencia_id, tenant_id,
    )
    if row is None:
        return None
    d = dict(row)
    d['destinatarios'] = await _listar_destinatarios(
        conn, correspondencia_id=correspondencia_id,
    )
    return d


# =============================================================================
# Correspondencia interna (GD-API-0052)
# =============================================================================

async def crear_interna(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    dependencia_origen_id: UUID,
    asunto: str,
    contenido_borrador: str | None,
    prioridad: str,
    requiere_respuesta: bool,
    fecha_limite_respuesta: datetime | None,
    documento_principal_id: UUID | None,
    plantilla_id: UUID | None,
    destinatarios: list[dict[str, Any]],
    usuario_proyecta_id: UUID,
    enviar_inmediato: bool = True,
) -> dict[str, Any]:
    """Crea correspondencia interna y opcionalmente la envía.

    Valida regla_comunicacion_interdependencia contra cada destinatario.
    """
    # Validar reglas de comunicación inter-dependencia.
    for d in destinatarios:
        if d['tipo_destinatario'] == 'dependencia':
            await _validar_regla_comunicacion(
                conn, tenant_id=tenant_id,
                dependencia_origen_id=dependencia_origen_id,
                dependencia_destino_id=d['dependencia_id'],
            )

    estado_inicial = 'enviada' if enviar_inmediato else 'borrador'
    fecha_envio = datetime.now() if enviar_inmediato else None
    usuario_envio = usuario_proyecta_id if enviar_inmediato else None

    # dependencia_destino_id se almacena solo si hay UN destinatario tipo
    # dependencia (caso típico interna). Si hay múltiples, queda NULL y se
    # consulta via tabla destinatarios.
    deps_uniq = [d for d in destinatarios if d['tipo_destinatario'] == 'dependencia']
    dependencia_destino_id = deps_uniq[0]['dependencia_id'] if len(deps_uniq) == 1 else None

    row = await conn.fetchrow(
        """
        insert into gd.correspondencia (
            tenant_id, tipo, dependencia_origen_id, dependencia_destino_id,
            asunto, contenido_borrador, prioridad, requiere_respuesta,
            fecha_limite_respuesta, documento_principal_id, plantilla_id,
            estado, usuario_proyecta_id, usuario_envio_id, fecha_envio
        )
        values ($1, 'interna', $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14)
        returning *
        """,
        tenant_id, dependencia_origen_id, dependencia_destino_id,
        asunto, contenido_borrador, prioridad, requiere_respuesta,
        fecha_limite_respuesta, documento_principal_id, plantilla_id,
        estado_inicial, usuario_proyecta_id, usuario_envio, fecha_envio,
    )
    d = dict(row)
    d['destinatarios'] = await _insertar_destinatarios(
        conn, tenant_id=tenant_id,
        correspondencia_id=d['id'], destinatarios=destinatarios,
    )
    return d


async def marcar_leida(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    correspondencia_id: UUID,
    dependencia_id: UUID,
    usuario_actor_id: UUID,
) -> dict[str, Any] | None:
    """Marca como leída por una dependencia destinataria específica.

    Si todos los destinatarios principales tienen fecha_lectura, mueve
    estado de la correspondencia a 'leida'.
    """
    # Verificar que existe destinatario para esa dependencia y aún no leída.
    dest = await conn.fetchrow(
        """
        select id from gd.destinatario_correspondencia
        where correspondencia_id = $1 and tenant_id = $2
          and dependencia_id = $3 and fecha_lectura is null
        """,
        correspondencia_id, tenant_id, dependencia_id,
    )
    if dest is None:
        return None

    await conn.execute(
        """
        update gd.destinatario_correspondencia
        set fecha_lectura = now(), leida_por_user_id = $3
        where id = $1 and tenant_id = $2
        """,
        dest['id'], tenant_id, usuario_actor_id,
    )

    # Verificar si todos los principales están leídos.
    pendientes = await conn.fetchval(
        """
        select count(*) from gd.destinatario_correspondencia
        where correspondencia_id = $1
          and tipo_copia = 'principal' and fecha_lectura is null
        """,
        correspondencia_id,
    )
    if pendientes == 0:
        await conn.execute(
            "update gd.correspondencia set estado = 'leida' "
            "where id = $1 and estado in ('enviada','reenviada')",
            correspondencia_id,
        )

    return await obtener_correspondencia(
        conn, tenant_id=tenant_id, correspondencia_id=correspondencia_id,
    )


async def responder(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    correspondencia_id: UUID,
    dependencia_origen_id: UUID,
    asunto: str,
    contenido_borrador: str | None,
    documento_principal_id: UUID | None,
    usuario_proyecta_id: UUID,
    enviar_inmediato: bool = True,
) -> dict[str, Any] | None:
    """Crea correspondencia de respuesta vinculada por correspondencia_padre_id.

    La nueva correspondencia se dirige a la dependencia_origen original.
    Marca la original como 'respondida'.
    """
    orig = await conn.fetchrow(
        'select dependencia_origen_id, tipo, estado from gd.correspondencia '
        'where id = $1 and tenant_id = $2',
        correspondencia_id, tenant_id,
    )
    if orig is None:
        return None
    if orig['tipo'] != 'interna':
        raise ValueError('solo_interna_admite_respuesta')

    estado_inicial = 'enviada' if enviar_inmediato else 'borrador'
    fecha_envio = datetime.now() if enviar_inmediato else None

    row = await conn.fetchrow(
        """
        insert into gd.correspondencia (
            tenant_id, tipo, dependencia_origen_id, dependencia_destino_id,
            asunto, contenido_borrador, documento_principal_id,
            estado, usuario_proyecta_id, usuario_envio_id, fecha_envio,
            correspondencia_padre_id
        )
        values ($1, 'interna', $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        returning *
        """,
        tenant_id, dependencia_origen_id, orig['dependencia_origen_id'],
        asunto, contenido_borrador, documento_principal_id,
        estado_inicial, usuario_proyecta_id,
        usuario_proyecta_id if enviar_inmediato else None,
        fecha_envio, correspondencia_id,
    )
    d = dict(row)
    d['destinatarios'] = await _insertar_destinatarios(
        conn, tenant_id=tenant_id, correspondencia_id=d['id'],
        destinatarios=[{
            'tipo_destinatario': 'dependencia',
            'dependencia_id': orig['dependencia_origen_id'],
            'tipo_copia': 'principal',
        }],
    )

    # Marcar original como respondida.
    await conn.execute(
        "update gd.correspondencia set estado = 'respondida' where id = $1",
        correspondencia_id,
    )
    return d


async def reenviar(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    correspondencia_id: UUID,
    dependencia_origen_id: UUID,
    destinatarios: list[dict[str, Any]],
    usuario_proyecta_id: UUID,
    observaciones: str | None,
) -> dict[str, Any] | None:
    """Reenvía una correspondencia interna agregando nuevos destinatarios.

    Crea una nueva correspondencia hija (correspondencia_padre_id) con los
    nuevos destinatarios y marca la original como 'reenviada'.
    """
    orig = await conn.fetchrow(
        'select asunto, contenido_borrador, documento_principal_id, tipo '
        'from gd.correspondencia where id = $1 and tenant_id = $2',
        correspondencia_id, tenant_id,
    )
    if orig is None:
        return None
    if orig['tipo'] != 'interna':
        raise ValueError('solo_interna_admite_reenvio')

    # Validar reglas para cada dependencia destino nueva.
    for d in destinatarios:
        if d['tipo_destinatario'] == 'dependencia':
            await _validar_regla_comunicacion(
                conn, tenant_id=tenant_id,
                dependencia_origen_id=dependencia_origen_id,
                dependencia_destino_id=d['dependencia_id'],
            )

    asunto_re = f"RV: {orig['asunto']}"[:500]
    contenido_re = orig['contenido_borrador']
    if observaciones:
        contenido_re = f"{observaciones}\n\n----- Mensaje original -----\n{contenido_re or ''}"

    row = await conn.fetchrow(
        """
        insert into gd.correspondencia (
            tenant_id, tipo, dependencia_origen_id, asunto,
            contenido_borrador, documento_principal_id, estado,
            usuario_proyecta_id, usuario_envio_id, fecha_envio,
            correspondencia_padre_id
        )
        values ($1, 'interna', $2, $3, $4, $5, 'enviada', $6, $6, now(), $7)
        returning *
        """,
        tenant_id, dependencia_origen_id, asunto_re,
        contenido_re, orig['documento_principal_id'],
        usuario_proyecta_id, correspondencia_id,
    )
    d = dict(row)
    d['destinatarios'] = await _insertar_destinatarios(
        conn, tenant_id=tenant_id, correspondencia_id=d['id'],
        destinatarios=destinatarios,
    )

    # Marcar original como reenviada.
    await conn.execute(
        "update gd.correspondencia set estado = 'reenviada' where id = $1",
        correspondencia_id,
    )
    return d


# =============================================================================
# Externa recibida (GD-API-0053)
# =============================================================================

async def crear_desde_radicado_externa(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    radicado_id: UUID,
    sub_tipo: str | None = None,
) -> dict[str, Any] | None:
    """Hook reactivo: crea gd.correspondencia externa_recibida desde radicado.

    Idempotente: si ya existe, retorna None (no duplica).
    """
    existing = await conn.fetchval(
        """
        select id from gd.correspondencia
        where tenant_id = $1 and radicado_entrada_id = $2 and tipo = 'externa_recibida'
        """,
        tenant_id, radicado_id,
    )
    if existing:
        return None

    radicado = await conn.fetchrow(
        """
        select asunto, descripcion, tercero_id, dependencia_destino_id,
               usuario_radicador_id
        from gd.radicado where id = $1 and tenant_id = $2
        """,
        radicado_id, tenant_id,
    )
    if radicado is None:
        return None

    row = await conn.fetchrow(
        """
        insert into gd.correspondencia (
            tenant_id, tipo, dependencia_destino_id, tercero_remitente_id,
            radicado_entrada_id, asunto, contenido_borrador,
            estado, usuario_proyecta_id
        )
        values ($1, 'externa_recibida', $2, $3, $4, $5, $6,
                'derivada', $7)
        returning *
        """,
        tenant_id, radicado['dependencia_destino_id'], radicado['tercero_id'],
        radicado_id, radicado['asunto'], radicado['descripcion'],
        radicado['usuario_radicador_id'],
    )
    d = dict(row)
    # Si hay dependencia_destino, registrar como destinatario.
    if radicado['dependencia_destino_id'] is not None:
        d['destinatarios'] = await _insertar_destinatarios(
            conn, tenant_id=tenant_id, correspondencia_id=d['id'],
            destinatarios=[{
                'tipo_destinatario': 'dependencia',
                'dependencia_id': radicado['dependencia_destino_id'],
                'tipo_copia': 'principal',
            }],
        )
    else:
        d['destinatarios'] = []
    return d


async def gestionar_externa_recibida(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    correspondencia_id: UUID,
    observaciones: str,
    dependencia_id: UUID | None,
    usuario_actor_id: UUID,
) -> dict[str, Any] | None:
    """Marca una correspondencia externa recibida como 'gestionada'.

    Opcionalmente reasigna a otra dependencia.
    """
    corr = await conn.fetchrow(
        'select tipo, estado from gd.correspondencia '
        'where id = $1 and tenant_id = $2',
        correspondencia_id, tenant_id,
    )
    if corr is None:
        return None
    if corr['tipo'] != 'externa_recibida':
        raise ValueError('tipo_invalido_no_externa_recibida')
    if corr['estado'] not in ('derivada', 'gestionada'):
        raise ValueError(f"estado_invalido:{corr['estado']}")

    row = await conn.fetchrow(
        """
        update gd.correspondencia
        set estado = 'gestionada',
            dependencia_destino_id = coalesce($3, dependencia_destino_id),
            metadata = metadata || jsonb_build_object(
                'gestionada_en', now()::text,
                'gestionada_por', $4::text,
                'observaciones_gestion', $5
            )
        where id = $1 and tenant_id = $2
        returning *
        """,
        correspondencia_id, tenant_id, dependencia_id,
        str(usuario_actor_id), observaciones,
    )
    d = dict(row)
    d['destinatarios'] = await _listar_destinatarios(
        conn, correspondencia_id=correspondencia_id,
    )
    return d


# =============================================================================
# Externa enviada — workflow (GD-API-0054)
# =============================================================================

async def crear_externa_enviada_borrador(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    dependencia_origen_id: UUID,
    asunto: str,
    contenido_borrador: str | None,
    prioridad: str,
    documento_principal_id: UUID | None,
    plantilla_id: UUID | None,
    destinatarios: list[dict[str, Any]],
    usuario_proyecta_id: UUID,
) -> dict[str, Any]:
    """Crea un borrador de correspondencia externa enviada."""
    row = await conn.fetchrow(
        """
        insert into gd.correspondencia (
            tenant_id, tipo, dependencia_origen_id, asunto, contenido_borrador,
            prioridad, documento_principal_id, plantilla_id, estado,
            usuario_proyecta_id
        )
        values ($1, 'externa_enviada', $2, $3, $4, $5, $6, $7, 'borrador', $8)
        returning *
        """,
        tenant_id, dependencia_origen_id, asunto, contenido_borrador,
        prioridad, documento_principal_id, plantilla_id, usuario_proyecta_id,
    )
    d = dict(row)
    d['destinatarios'] = await _insertar_destinatarios(
        conn, tenant_id=tenant_id, correspondencia_id=d['id'],
        destinatarios=destinatarios,
    )
    return d


async def _obtener_corresp_workflow(
    conn: asyncpg.Connection, *, tenant_id: UUID, correspondencia_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        'select id, tipo, estado, usuario_proyecta_id '
        'from gd.correspondencia where id = $1 and tenant_id = $2',
        correspondencia_id, tenant_id,
    )
    return dict(row) if row else None


async def workflow_enviar_a_revision(
    conn: asyncpg.Connection, *, tenant_id: UUID, correspondencia_id: UUID,
    usuario_actor_id: UUID, observaciones: str | None = None,
) -> dict[str, Any] | None:
    """borrador → en_revision (externa enviada)."""
    c = await _obtener_corresp_workflow(
        conn, tenant_id=tenant_id, correspondencia_id=correspondencia_id,
    )
    if c is None:
        return None
    if c['tipo'] != 'externa_enviada':
        raise ValueError('tipo_invalido_no_externa_enviada')
    if c['estado'] != 'borrador':
        raise ValueError(f"estado_invalido:{c['estado']}")

    await conn.execute(
        "update gd.correspondencia set estado = 'en_revision' "
        "where id = $1 and tenant_id = $2",
        correspondencia_id, tenant_id,
    )
    return await obtener_correspondencia(
        conn, tenant_id=tenant_id, correspondencia_id=correspondencia_id,
    )


async def workflow_revisar(
    conn: asyncpg.Connection, *, tenant_id: UUID, correspondencia_id: UUID,
    resultado: str, observaciones: str | None, usuario_actor_id: UUID,
) -> dict[str, Any] | None:
    """en_revision → aprobada | devuelta. RNF-008 separación de funciones."""
    c = await _obtener_corresp_workflow(
        conn, tenant_id=tenant_id, correspondencia_id=correspondencia_id,
    )
    if c is None:
        return None
    if c['estado'] != 'en_revision':
        raise ValueError(f"estado_invalido:{c['estado']}")
    if c['usuario_proyecta_id'] == usuario_actor_id:
        raise PermissionError('separacion_funciones:proyecta==revisa')

    nuevo = 'aprobada' if resultado == 'ok' else 'devuelta'
    await conn.execute(
        """
        update gd.correspondencia
        set estado = $3, usuario_revisa_id = $4,
            fecha_aprobacion = case when $3 = 'aprobada' then now()
                                    else fecha_aprobacion end,
            observaciones_devolucion = case when $3 = 'devuelta' then $5
                                            else observaciones_devolucion end
        where id = $1 and tenant_id = $2
        """,
        correspondencia_id, tenant_id, nuevo, usuario_actor_id, observaciones,
    )
    return await obtener_correspondencia(
        conn, tenant_id=tenant_id, correspondencia_id=correspondencia_id,
    )


async def workflow_aprobar(
    conn: asyncpg.Connection, *, tenant_id: UUID, correspondencia_id: UUID,
    usuario_actor_id: UUID, observaciones: str | None = None,
) -> dict[str, Any] | None:
    c = await _obtener_corresp_workflow(
        conn, tenant_id=tenant_id, correspondencia_id=correspondencia_id,
    )
    if c is None:
        return None
    if c['estado'] != 'aprobada':
        raise ValueError(f"estado_invalido:{c['estado']}")
    if c['usuario_proyecta_id'] == usuario_actor_id:
        raise PermissionError('separacion_funciones:proyecta==aprueba')

    await conn.execute(
        "update gd.correspondencia set usuario_aprueba_id = $3, "
        "fecha_aprobacion = coalesce(fecha_aprobacion, now()) "
        "where id = $1 and tenant_id = $2",
        correspondencia_id, tenant_id, usuario_actor_id,
    )
    return await obtener_correspondencia(
        conn, tenant_id=tenant_id, correspondencia_id=correspondencia_id,
    )


async def workflow_firmar(
    conn: asyncpg.Connection, *, tenant_id: UUID, correspondencia_id: UUID,
    usuario_actor_id: UUID, firma_id: UUID | None = None,
) -> dict[str, Any] | None:
    c = await _obtener_corresp_workflow(
        conn, tenant_id=tenant_id, correspondencia_id=correspondencia_id,
    )
    if c is None:
        return None
    if c['estado'] != 'aprobada':
        raise ValueError(f"estado_invalido:{c['estado']}")
    if c['usuario_proyecta_id'] == usuario_actor_id:
        raise PermissionError('separacion_funciones:proyecta==firma')

    await conn.execute(
        """
        update gd.correspondencia
        set estado = 'firmada', usuario_firma_id = $3, fecha_firma = now()
        where id = $1 and tenant_id = $2
        """,
        correspondencia_id, tenant_id, usuario_actor_id,
    )
    return await obtener_correspondencia(
        conn, tenant_id=tenant_id, correspondencia_id=correspondencia_id,
    )


async def workflow_radicar_salida(
    conn: asyncpg.Connection, *, tenant_id: UUID, correspondencia_id: UUID,
    usuario_actor_id: UUID, canal_envio_id: UUID | None = None,
) -> dict[str, Any] | None:
    """firmada → radicada. Crea radicado de salida con consecutivo."""
    from app.gd.services import consecutivos as svc_consec

    c = await conn.fetchrow(
        """
        select tipo, estado, asunto, contenido_borrador,
               dependencia_origen_id, usuario_proyecta_id
        from gd.correspondencia where id = $1 and tenant_id = $2
        """,
        correspondencia_id, tenant_id,
    )
    if c is None:
        return None
    if c['estado'] != 'firmada':
        raise ValueError(f"estado_invalido:{c['estado']}")

    vigencia = datetime.now().year
    numero = await svc_consec.siguiente_radicado(
        conn, tenant_id=tenant_id, vigencia=vigencia, tipo_radicado='salida',
    )

    rad = await conn.fetchrow(
        """
        insert into gd.radicado (
            tenant_id, numero_radicado, tipo_radicado, canal_id, estado,
            asunto, descripcion, dependencia_origen_id,
            usuario_radicador_id, actor_snapshot
        )
        values ($1, $2, 'salida', $3, 'radicado', $4, $5, $6, $7, $8)
        returning id, numero_radicado, fecha_radicacion
        """,
        tenant_id, numero, canal_envio_id, c['asunto'], c['contenido_borrador'],
        c['dependencia_origen_id'], usuario_actor_id,
        json.dumps({'usuario_id': str(usuario_actor_id),
                    'origen': 'correspondencia',
                    'correspondencia_id': str(correspondencia_id)}),
    )

    await conn.execute(
        """
        update gd.correspondencia
        set estado = 'radicada', radicado_salida_id = $3,
            canal_envio_id = coalesce(canal_envio_id, $4),
            fecha_radicacion = now()
        where id = $1 and tenant_id = $2
        """,
        correspondencia_id, tenant_id, rad['id'], canal_envio_id,
    )
    return await obtener_correspondencia(
        conn, tenant_id=tenant_id, correspondencia_id=correspondencia_id,
    )


async def workflow_enviar(
    conn: asyncpg.Connection, *, tenant_id: UUID, correspondencia_id: UUID,
    usuario_actor_id: UUID, canal_envio_id: UUID | None = None,
) -> dict[str, Any] | None:
    """radicada → enviada."""
    c = await _obtener_corresp_workflow(
        conn, tenant_id=tenant_id, correspondencia_id=correspondencia_id,
    )
    if c is None:
        return None
    if c['estado'] != 'radicada':
        raise ValueError(f"estado_invalido:{c['estado']}")

    await conn.execute(
        """
        update gd.correspondencia
        set estado = 'enviada', usuario_envio_id = $3, fecha_envio = now(),
            canal_envio_id = coalesce($4, canal_envio_id)
        where id = $1 and tenant_id = $2
        """,
        correspondencia_id, tenant_id, usuario_actor_id, canal_envio_id,
    )
    return await obtener_correspondencia(
        conn, tenant_id=tenant_id, correspondencia_id=correspondencia_id,
    )


async def registrar_soporte_envio(
    conn: asyncpg.Connection, *, tenant_id: UUID, correspondencia_id: UUID,
    soporte_envio_uri: str, codigo_rastreo: str | None,
    usuario_actor_id: UUID,
) -> dict[str, Any] | None:
    c = await _obtener_corresp_workflow(
        conn, tenant_id=tenant_id, correspondencia_id=correspondencia_id,
    )
    if c is None:
        return None
    if c['estado'] not in ('enviada', 'radicada'):
        raise ValueError(f"estado_invalido:{c['estado']}")

    await conn.execute(
        """
        update gd.correspondencia
        set soporte_envio_uri = $3,
            soporte_envio_codigo_rastreo = $4,
            fecha_registro_soporte = now()
        where id = $1 and tenant_id = $2
        """,
        correspondencia_id, tenant_id, soporte_envio_uri, codigo_rastreo,
    )
    return await obtener_correspondencia(
        conn, tenant_id=tenant_id, correspondencia_id=correspondencia_id,
    )


# =============================================================================
# Anulación (GD-API-0056)
# =============================================================================

async def solicitar_anulacion(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    correspondencia_id: UUID,
    motivo: str,
    evidencia_archivo_digital_id: UUID | None,
    solicitante_user_id: UUID,
) -> dict[str, Any] | None:
    """Crea registro en gd.solicitud_anulacion con tipo_entidad='correspondencia'."""
    corr = await conn.fetchval(
        'select estado from gd.correspondencia where id = $1 and tenant_id = $2',
        correspondencia_id, tenant_id,
    )
    if corr is None:
        return None
    if corr == 'anulada':
        raise ValueError('ya_anulada')

    row = await conn.fetchrow(
        """
        insert into gd.solicitud_anulacion (
            tenant_id, tipo_entidad, entidad_afectada_id, solicitante_user_id,
            motivo, evidencia_archivo_digital_id
        )
        values ($1, 'correspondencia', $2, $3, $4, $5)
        returning id, tipo_entidad, entidad_afectada_id, solicitante_user_id,
                  motivo, decision, aprobador_user_id, observacion_decision,
                  fecha_solicitud, fecha_decision
        """,
        tenant_id, correspondencia_id, solicitante_user_id, motivo,
        evidencia_archivo_digital_id,
    )
    return dict(row)


async def aprobar_anulacion(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    solicitud_id: UUID,
    aprobador_user_id: UUID,
    observacion: str | None,
) -> dict[str, Any] | None:
    """Aprueba la solicitud y anula la correspondencia."""
    sol = await conn.fetchrow(
        """
        select entidad_afectada_id, decision
        from gd.solicitud_anulacion
        where id = $1 and tenant_id = $2 and tipo_entidad = 'correspondencia'
        """,
        solicitud_id, tenant_id,
    )
    if sol is None:
        return None
    if sol['decision'] != 'pendiente':
        raise ValueError(f"solicitud_ya_decidida:{sol['decision']}")

    row = await conn.fetchrow(
        """
        update gd.solicitud_anulacion
        set decision = 'aprobada', aprobador_user_id = $3,
            observacion_decision = $4, fecha_decision = now()
        where id = $1 and tenant_id = $2
        returning id, tipo_entidad, entidad_afectada_id, solicitante_user_id,
                  motivo, decision, aprobador_user_id, observacion_decision,
                  fecha_solicitud, fecha_decision
        """,
        solicitud_id, tenant_id, aprobador_user_id, observacion,
    )

    await conn.execute(
        """
        update gd.correspondencia
        set estado = 'anulada', anulada_en = now(),
            anulada_por_user_id = $3, motivo_anulacion = $4,
            solicitud_anulacion_id = $5
        where id = $1 and tenant_id = $2
        """,
        sol['entidad_afectada_id'], tenant_id, aprobador_user_id,
        observacion or 'Anulación aprobada', solicitud_id,
    )
    return dict(row)


async def rechazar_anulacion(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    solicitud_id: UUID,
    aprobador_user_id: UUID,
    observacion: str,
) -> dict[str, Any] | None:
    sol = await conn.fetchrow(
        """
        select decision from gd.solicitud_anulacion
        where id = $1 and tenant_id = $2 and tipo_entidad = 'correspondencia'
        """,
        solicitud_id, tenant_id,
    )
    if sol is None:
        return None
    if sol['decision'] != 'pendiente':
        raise ValueError(f"solicitud_ya_decidida:{sol['decision']}")

    row = await conn.fetchrow(
        """
        update gd.solicitud_anulacion
        set decision = 'rechazada', aprobador_user_id = $3,
            observacion_decision = $4, fecha_decision = now()
        where id = $1 and tenant_id = $2
        returning id, tipo_entidad, entidad_afectada_id, solicitante_user_id,
                  motivo, decision, aprobador_user_id, observacion_decision,
                  fecha_solicitud, fecha_decision
        """,
        solicitud_id, tenant_id, aprobador_user_id, observacion,
    )
    return dict(row)


# =============================================================================
# Listado / filtros
# =============================================================================

async def listar_correspondencia(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    tipo: str | None = None,
    estado: list[str] | None = None,
    dependencia_id: UUID | None = None,  # origen o destino
    tercero_id: UUID | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if tipo:
        params.append(tipo)
        where.append(f'tipo = ${len(params)}')
    if estado:
        params.append(estado)
        where.append(f'estado = any(${len(params)}::text[])')
    if dependencia_id:
        params.append(dependencia_id)
        where.append(f'(dependencia_origen_id = ${len(params)} '
                     f'or dependencia_destino_id = ${len(params)})')
    if tercero_id:
        params.append(tercero_id)
        where.append(f'(tercero_remitente_id = ${len(params)})')
    params.append(limit)
    where_sql = ' and '.join(where)
    rows = await conn.fetch(
        f"""
        select id, tipo, asunto, estado, prioridad,
               dependencia_origen_id, dependencia_destino_id,
               tercero_remitente_id, fecha_envio, requiere_respuesta,
               created_at
        from gd.correspondencia
        where {where_sql}
        order by created_at desc
        limit ${len(params)}
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def contar_correspondencia(
    conn: asyncpg.Connection, *, tenant_id: UUID, tipo: str | None = None,
) -> int:
    if tipo:
        row = await conn.fetchval(
            'select count(*) from gd.correspondencia '
            'where tenant_id = $1 and tipo = $2',
            tenant_id, tipo,
        )
    else:
        row = await conn.fetchval(
            'select count(*) from gd.correspondencia where tenant_id = $1',
            tenant_id,
        )
    return int(row or 0)


__all__ = [
    # Lectura
    'obtener_correspondencia', 'listar_correspondencia', 'contar_correspondencia',
    # Interna
    'crear_interna', 'marcar_leida', 'responder', 'reenviar',
    # Externa recibida (hook + gestionar)
    'crear_desde_radicado_externa', 'gestionar_externa_recibida',
    # Externa enviada workflow
    'crear_externa_enviada_borrador',
    'workflow_enviar_a_revision', 'workflow_revisar', 'workflow_aprobar',
    'workflow_firmar', 'workflow_radicar_salida', 'workflow_enviar',
    'registrar_soporte_envio',
    # Anulación
    'solicitar_anulacion', 'aprobar_anulacion', 'rechazar_anulacion',
]
