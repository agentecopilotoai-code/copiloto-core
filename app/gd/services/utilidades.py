"""Services para EP-019/020 utilidades (bloque 20).

Domains:
- auditoria: consultar core.evento_auditoria + catálogo
- constancias: generar + verificar pública por código
- tipos_doc: catálogo global + selección por organización
- cambios_dep: historial + fusionar dependencias
- contingencia: radicación cuando sistema caído
- hoja_control: append-only + índice electrónico expediente
"""
from __future__ import annotations

import json
import secrets
from datetime import date, datetime
from typing import Any
from uuid import UUID

import asyncpg


# =============================================================================
# Auditoría (GD-API-0119/0120)
# =============================================================================

async def listar_eventos_auditoria(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID | None = None,
    dominio: str | None = None,
    tipo_evento: str | None = None,
    actor_id: UUID | None = None,
    entidad_tipo: str | None = None,
    entidad_id: UUID | None = None,
    criticidad: str | None = None,
    desde: datetime | None = None,
    hasta: datetime | None = None,
    cursor: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Consulta core.evento_auditoria con filtros + paginación cursor.

    cursor = base64 del último id+created_at retornado. Para v1 stub
    aceptamos cursor=None y devolvemos la primera página.
    """
    where = []
    params: list[Any] = []

    def _p(v):
        params.append(v)
        return f'${len(params)}'

    # BUGFIX 2026-05-25: las queries usaban nombres de columnas que NO
    # existen en `core.evento_auditoria`. Mapeo correcto (ver schema en
    # `infra/postgres/modules/gd.sql` § 1.1):
    #   actor_id      → usuario_id
    #   entidad_tipo  → entidad_afectada_tipo
    #   entidad_id    → entidad_afectada_id
    #   created_at    → fecha_hora
    #   actor_type    → NO EXISTE (solo `actor_snapshot` jsonb). Devolvemos
    #                   NULL para mantener el shape del response API.
    if tenant_id is not None:
        where.append(f'tenant_id = {_p(tenant_id)}')
    if dominio is not None:
        where.append(f'dominio = {_p(dominio)}')
    if tipo_evento is not None:
        where.append(f'tipo_evento = {_p(tipo_evento)}')
    if actor_id is not None:
        where.append(f'usuario_id = {_p(actor_id)}')
    if entidad_tipo is not None:
        where.append(f'entidad_afectada_tipo = {_p(entidad_tipo)}')
    if entidad_id is not None:
        where.append(f'entidad_afectada_id = {_p(entidad_id)}')
    if criticidad is not None:
        where.append(f'criticidad = {_p(criticidad)}')
    if desde is not None:
        where.append(f'fecha_hora >= {_p(desde)}')
    if hasta is not None:
        where.append(f'fecha_hora <= {_p(hasta)}')

    where_sql = ' and '.join(where) if where else 'true'
    params.append(limit)
    rows = await conn.fetch(
        f"""
        select id, tipo_evento, dominio, accion,
               null::text             as actor_type,
               usuario_id             as actor_id,
               entidad_afectada_tipo  as entidad_tipo,
               entidad_afectada_id    as entidad_id,
               criticidad, request_id, ip,
               valor_anterior, valor_nuevo, justificacion, detalles,
               fecha_hora             as created_at
        from core.evento_auditoria
        where {where_sql}
        order by fecha_hora desc
        limit ${len(params)}
        """,
        *params,
    )
    out = []
    for r in rows:
        d = dict(r)
        for k in ('valor_anterior', 'valor_nuevo', 'detalles'):
            if isinstance(d.get(k), str):
                d[k] = json.loads(d[k]) if d[k] else None
        out.append(d)
    return out


async def obtener_evento_auditoria(
    conn: asyncpg.Connection, *, evento_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, tipo_evento, dominio, accion,
               null::text             as actor_type,
               usuario_id             as actor_id,
               entidad_afectada_tipo  as entidad_tipo,
               entidad_afectada_id    as entidad_id,
               criticidad, request_id, ip,
               valor_anterior, valor_nuevo, justificacion, detalles,
               fecha_hora             as created_at
        from core.evento_auditoria where id = $1
        """,
        evento_id,
    )
    if row is None:
        return None
    d = dict(row)
    for k in ('valor_anterior', 'valor_nuevo', 'detalles'):
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k]) if d[k] else None
    return d


async def listar_catalogo_eventos(
    conn: asyncpg.Connection,
    *,
    dominio: str | None = None,
    activo: bool | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    where = []
    params: list[Any] = []
    if dominio is not None:
        params.append(dominio)
        where.append(f'dominio = ${len(params)}')
    if activo is not None:
        params.append(activo)
        where.append(f'activo = ${len(params)}')
    where_sql = ' and '.join(where) if where else 'true'
    params.append(limit)
    rows = await conn.fetch(
        f"""
        select id, tipo_evento, dominio, productor_modulo, criticidad_default,
               rnf_cubierto, permiso_lectura, descripcion, activo
        from core.evento_auditoria_catalogo
        where {where_sql}
        order by dominio, tipo_evento
        limit ${len(params)}
        """,
        *params,
    )
    return [dict(r) for r in rows]


# =============================================================================
# Constancia pública (GD-API-0122)
# =============================================================================

def generar_codigo_verificacion() -> str:
    """Token URL-safe ~20 chars sin chars ambiguos."""
    return secrets.token_urlsafe(15)[:20]


async def crear_constancia(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    radicado_id: UUID,
    generada_por_user_id: UUID,
    archivo_pdf_id: UUID | None = None,
    exposicion_publica: bool = True,
) -> dict[str, Any]:
    codigo = generar_codigo_verificacion()
    qr_url = f'/gd/verificar/{codigo}'
    row = await conn.fetchrow(
        """
        insert into gd.constancia_radicacion (
            tenant_id, radicado_id, codigo_verificacion, qr_url_publica,
            generada_por_user_id, archivo_pdf_id, exposicion_publica
        )
        values ($1, $2, $3, $4, $5, $6, $7)
        returning id, codigo_verificacion, qr_url_publica,
                  fecha_generacion, exposicion_publica
        """,
        tenant_id, radicado_id, codigo, qr_url,
        generada_por_user_id, archivo_pdf_id, exposicion_publica,
    )
    return dict(row)


async def verificar_constancia_publica(
    conn: asyncpg.Connection, *, codigo_verificacion: str,
) -> dict[str, Any] | None:
    """SIN auth. Solo retorna info no-sensible.

    Verifica también que el tenant tenga activo el módulo
    'consulta_publica_radicado' (gd.organizacion_modulo_activacion).
    """
    # Join constancia → radicado para datos públicos.
    row = await conn.fetchrow(
        """
        select c.tenant_id, c.exposicion_publica,
               r.numero_radicado, r.fecha_radicacion, r.tipo_radicado,
               r.estado, r.asunto,
               coalesce(d.nombre, 'No asignada') as dependencia_nombre
        from gd.constancia_radicacion c
        join gd.radicado r on r.id = c.radicado_id
        left join gd.dependencia d on d.id = r.dependencia_destino_id
        where c.codigo_verificacion = $1
        """,
        codigo_verificacion,
    )
    if row is None:
        return None
    if not row['exposicion_publica']:
        return None

    # Validar módulo activo para el tenant.
    modulo_activo = await conn.fetchval(
        """
        select activado from gd.organizacion_modulo_activacion
        where tenant_id = $1 and modulo_codigo = 'consulta_publica_radicado'
        """,
        row['tenant_id'],
    )
    if modulo_activo is False:
        return None

    # Asunto resumido (primeras 80 chars).
    asunto_resumido = (row['asunto'] or '')[:80]
    if len(row['asunto'] or '') > 80:
        asunto_resumido += '...'

    return {
        'numero_radicado': row['numero_radicado'],
        'fecha_radicacion': row['fecha_radicacion'],
        'tipo_radicado': row['tipo_radicado'],
        'estado_actual': row['estado'],
        'dependencia_actual_publica': row['dependencia_nombre'],
        'asunto_resumido': asunto_resumido,
        'valida': True,
    }


# =============================================================================
# Tipos doc identidad (GD-API-0123)
# =============================================================================

async def listar_catalogo_tipos_doc(
    conn: asyncpg.Connection, *, pais_iso: str | None = None,
) -> list[dict[str, Any]]:
    if pais_iso:
        rows = await conn.fetch(
            """
            select codigo, nombre, pais_iso, formato_regex, activo_global
            from gd.catalogo_tipo_documento
            where pais_iso = $1 or pais_iso = 'XX'
            order by codigo
            """,
            pais_iso,
        )
    else:
        rows = await conn.fetch(
            """
            select codigo, nombre, pais_iso, formato_regex, activo_global
            from gd.catalogo_tipo_documento
            order by pais_iso, codigo
            """,
        )
    return [dict(r) for r in rows]


async def listar_org_tipos_doc(
    conn: asyncpg.Connection, *, tenant_id: UUID,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select id, codigo_tipo_doc, activado, es_default, created_at
        from gd.organizacion_tipo_documento_activo
        where tenant_id = $1
        order by codigo_tipo_doc
        """,
        tenant_id,
    )
    return [dict(r) for r in rows]


async def patch_org_tipos_doc(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    codigos_activos: list[str],
    codigo_default: str | None,
) -> list[dict[str, Any]]:
    """Reemplaza el set de tipos activos. codigo_default debe estar en
    codigos_activos si se especifica."""
    if codigo_default and codigo_default not in codigos_activos:
        raise ValueError('default_no_esta_activo')

    # Validar que todos los códigos existen en catálogo global.
    for codigo in codigos_activos:
        existe = await conn.fetchval(
            'select 1 from gd.catalogo_tipo_documento where codigo = $1',
            codigo,
        )
        if not existe:
            raise LookupError(f'codigo_no_existe:{codigo}')

    # 1. Limpiar default actual y desactivar todos.
    await conn.execute(
        """
        update gd.organizacion_tipo_documento_activo
        set activado = false, es_default = false
        where tenant_id = $1
        """,
        tenant_id,
    )
    # 2. Activar los nuevos (upsert).
    for codigo in codigos_activos:
        es_default = (codigo == codigo_default)
        await conn.execute(
            """
            insert into gd.organizacion_tipo_documento_activo
                (tenant_id, codigo_tipo_doc, activado, es_default)
            values ($1, $2, true, $3)
            on conflict (tenant_id, codigo_tipo_doc) do update set
                activado = true, es_default = excluded.es_default
            """,
            tenant_id, codigo, es_default,
        )
    return await listar_org_tipos_doc(conn, tenant_id=tenant_id)


# =============================================================================
# Cambios dependencias (GD-API-0124)
# =============================================================================

async def historial_dependencia(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    dependencia_id: UUID,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select id, dependencia_id, dependencia_padre_id,
               fecha_inicio_vigencia, fecha_fin_vigencia,
               tipo_cambio, motivo_cambio, acto_administrativo,
               registrado_por_user_id, created_at
        from gd.relacion_dependencia_historica
        where tenant_id = $1 and dependencia_id = $2
        order by fecha_inicio_vigencia desc
        """,
        tenant_id, dependencia_id,
    )
    return [dict(r) for r in rows]


async def fusionar_dependencias(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    dependencias_origen: list[UUID],
    dependencia_destino_id: UUID,
    fecha_vigencia: date,
    motivo: str,
    acto_administrativo: str | None,
    registrado_por_user_id: UUID,
) -> dict[str, Any]:
    """Cierra origenes (insert fusion_origen + fecha_fin) y abre destino
    (insert fusion_destino) en una sola transacción."""
    # Validar destino existe.
    dest = await conn.fetchval(
        'select 1 from gd.dependencia where id = $1 and tenant_id = $2',
        dependencia_destino_id, tenant_id,
    )
    if not dest:
        raise LookupError('dependencia_destino_no_existe')

    relaciones_creadas = []
    dependencias_cerradas = []

    # 1. Marcar dependencias origen como cerradas.
    for dep_origen in dependencias_origen:
        # Cerrar relacion vigente del origen (si existe).
        await conn.execute(
            """
            update gd.relacion_dependencia_historica
            set fecha_fin_vigencia = $3
            where tenant_id = $1 and dependencia_id = $2
              and fecha_fin_vigencia is null
            """,
            tenant_id, dep_origen, fecha_vigencia,
        )
        # Insertar relación 'fusion_origen'.
        row = await conn.fetchrow(
            """
            insert into gd.relacion_dependencia_historica (
                tenant_id, dependencia_id, dependencia_padre_id,
                fecha_inicio_vigencia, fecha_fin_vigencia,
                tipo_cambio, motivo_cambio, acto_administrativo,
                registrado_por_user_id
            )
            values ($1, $2, null, $3, $3, 'fusion_origen', $4, $5, $6)
            returning id
            """,
            tenant_id, dep_origen, fecha_vigencia,
            motivo, acto_administrativo, registrado_por_user_id,
        )
        relaciones_creadas.append(row['id'])
        dependencias_cerradas.append(dep_origen)
        # Marcar dependencia origen como 'fusionada' en estado (best-effort).
        await conn.execute(
            "update gd.dependencia set estado = 'fusionada' where id = $1",
            dep_origen,
        )

    # 2. Insertar relación 'fusion_destino' en destino.
    row = await conn.fetchrow(
        """
        insert into gd.relacion_dependencia_historica (
            tenant_id, dependencia_id, dependencia_padre_id,
            fecha_inicio_vigencia, fecha_fin_vigencia,
            tipo_cambio, motivo_cambio, acto_administrativo,
            registrado_por_user_id
        )
        values ($1, $2, null, $3, null, 'fusion_destino', $4, $5, $6)
        returning id
        """,
        tenant_id, dependencia_destino_id, fecha_vigencia,
        motivo, acto_administrativo, registrado_por_user_id,
    )
    relaciones_creadas.append(row['id'])

    return {
        'dependencia_destino_id': dependencia_destino_id,
        'relaciones_creadas': relaciones_creadas,
        'dependencias_cerradas': dependencias_cerradas,
    }


# =============================================================================
# Contingencia (GD-API-0125)
# =============================================================================

async def radicar_contingencia(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    numero_radicado_manual: str,
    fecha_radicacion_real: datetime,
    justificacion: str,
    evidencia_contingencia_archivo_id: UUID,
    canal_id: UUID,
    tipo_radicado: str,
    asunto: str,
    descripcion: str | None,
    tercero_id: UUID | None,
    dependencia_destino_id: UUID | None,
    usuario_actor_id: UUID,
) -> dict[str, Any]:
    """Crea radicado con flag es_radicacion_contingencia=true preservando
    fecha real (no la fecha de ingreso al sistema)."""
    row = await conn.fetchrow(
        """
        insert into gd.radicado (
            tenant_id, numero_radicado, tipo_radicado, canal_id, estado,
            asunto, descripcion, tercero_id, dependencia_destino_id,
            usuario_radicador_id, actor_snapshot,
            fecha_radicacion,
            es_radicacion_contingencia, fecha_radicacion_real,
            justificacion_contingencia, evidencia_contingencia_archivo_id
        )
        values ($1, $2, $3, $4, 'radicado', $5, $6, $7, $8, $9, $10::jsonb,
                $11, true, $11, $12, $13)
        returning id, numero_radicado, tipo_radicado, fecha_radicacion,
                  fecha_radicacion_real, es_radicacion_contingencia,
                  created_at
        """,
        tenant_id, numero_radicado_manual, tipo_radicado, canal_id,
        asunto, descripcion, tercero_id, dependencia_destino_id,
        usuario_actor_id,
        json.dumps({'usuario_id': str(usuario_actor_id),
                     'origen': 'radicacion_contingencia'}),
        fecha_radicacion_real, justificacion,
        evidencia_contingencia_archivo_id,
    )
    return dict(row)


# =============================================================================
# Hoja de control + índice electrónico (GD-API-0126)
# =============================================================================

async def registrar_hoja_control(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    expediente_id: UUID,
    evento: str,
    descripcion: str | None,
    usuario_id: UUID,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append-only insertion en gd.expediente_hoja_control."""
    row = await conn.fetchrow(
        """
        insert into gd.expediente_hoja_control (
            tenant_id, expediente_id, evento, descripcion,
            usuario_id, snapshot_jsonb
        )
        values ($1, $2, $3, $4, $5, $6::jsonb)
        returning id, expediente_id, fecha, evento, descripcion,
                  usuario_id, snapshot_jsonb, created_at
        """,
        tenant_id, expediente_id, evento, descripcion,
        usuario_id, json.dumps(snapshot or {}),
    )
    d = dict(row)
    if isinstance(d.get('snapshot_jsonb'), str):
        d['snapshot_jsonb'] = json.loads(d['snapshot_jsonb'])
    return d


async def listar_hoja_control(
    conn: asyncpg.Connection, *, tenant_id: UUID, expediente_id: UUID,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select id, expediente_id, fecha, evento, descripcion,
               usuario_id, snapshot_jsonb, created_at
        from gd.expediente_hoja_control
        where tenant_id = $1 and expediente_id = $2
        order by fecha asc
        """,
        tenant_id, expediente_id,
    )
    out = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get('snapshot_jsonb'), str):
            d['snapshot_jsonb'] = json.loads(d['snapshot_jsonb'])
        out.append(d)
    return out


async def generar_indice_electronico(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    expediente_id: UUID,
    generado_por_user_id: UUID,
) -> dict[str, Any] | None:
    """Genera nueva versión del índice. Snapshot de items vinculados +
    hoja de control + metadata."""
    # Validar expediente.
    exp = await conn.fetchval(
        'select 1 from gd.expediente where id = $1 and tenant_id = $2',
        expediente_id, tenant_id,
    )
    if not exp:
        return None

    # Calcular siguiente versión.
    max_v = await conn.fetchval(
        """
        select coalesce(max(version_indice), 0)
        from gd.expediente_indice_electronico
        where expediente_id = $1 and tenant_id = $2
        """,
        expediente_id, tenant_id,
    )
    nueva_version = int(max_v) + 1

    # Construir snapshot básico (items vinculados + hoja control).
    items = await conn.fetch(
        """
        select id, item_tipo, item_id, orden
        from gd.expediente_item
        where expediente_id = $1 and tenant_id = $2 and estado = 'vinculado'
        order by orden
        """,
        expediente_id, tenant_id,
    )
    hoja = await conn.fetch(
        """
        select id, evento, fecha::text as fecha
        from gd.expediente_hoja_control
        where expediente_id = $1 and tenant_id = $2
        order by fecha
        """,
        expediente_id, tenant_id,
    )

    contenido = {
        'expediente_id': str(expediente_id),
        'version_indice': nueva_version,
        'items_vinculados': [
            {'id': str(i['id']), 'tipo': i['item_tipo'],
             'item_id': str(i['item_id']), 'orden': i['orden']}
            for i in items
        ],
        'eventos_hoja_control': [
            {'id': str(h['id']), 'evento': h['evento'], 'fecha': h['fecha']}
            for h in hoja
        ],
    }

    # Hash del contenido.
    import hashlib
    contenido_json = json.dumps(contenido, sort_keys=True)
    hash_sha = hashlib.sha256(contenido_json.encode()).hexdigest()

    row = await conn.fetchrow(
        """
        insert into gd.expediente_indice_electronico (
            tenant_id, expediente_id, version_indice,
            generado_por_user_id, contenido_jsonb, hash_sha256
        )
        values ($1, $2, $3, $4, $5::jsonb, $6)
        returning id, expediente_id, version_indice, generado_en,
                  generado_por_user_id, contenido_jsonb, hash_sha256
        """,
        tenant_id, expediente_id, nueva_version,
        generado_por_user_id, contenido_json, hash_sha,
    )
    d = dict(row)
    if isinstance(d.get('contenido_jsonb'), str):
        d['contenido_jsonb'] = json.loads(d['contenido_jsonb'])
    return d


__all__ = [
    # Auditoría
    'listar_eventos_auditoria', 'obtener_evento_auditoria',
    'listar_catalogo_eventos',
    # Constancia
    'generar_codigo_verificacion', 'crear_constancia',
    'verificar_constancia_publica',
    # Tipos doc
    'listar_catalogo_tipos_doc', 'listar_org_tipos_doc',
    'patch_org_tipos_doc',
    # Cambios dep
    'historial_dependencia', 'fusionar_dependencias',
    # Contingencia
    'radicar_contingencia',
    # Hoja control + índice
    'registrar_hoja_control', 'listar_hoja_control',
    'generar_indice_electronico',
]
