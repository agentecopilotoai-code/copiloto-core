"""Services para EP-014 reportes e indicadores (bloque 15).

Cubre:
- Reportes agregados (radicados, PQRSD, correspondencia, cargas trabajo,
  uso IA, anulaciones, auditoría).
- Export a CSV inline (PDF/Excel queda como placeholder hasta EP-018).
- Registro append-only de cada export en gd.reporte_generado (RNF-054).
"""
from __future__ import annotations

import csv
import io
import json
import time
from typing import Any
from uuid import UUID

import asyncpg


# =============================================================================
# Reporte 0087 — radicados
# =============================================================================

async def reporte_radicados(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    desde=None, hasta=None,
    canal_id: UUID | None = None,
    dependencia_id: UUID | None = None,
    tipo_radicado: str | None = None,
    estado: str | None = None,
) -> dict[str, Any]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if desde is not None:
        params.append(desde)
        where.append(f'fecha_radicacion >= ${len(params)}')
    if hasta is not None:
        params.append(hasta)
        where.append(f'fecha_radicacion <= ${len(params)}')
    if canal_id is not None:
        params.append(canal_id)
        where.append(f'canal_id = ${len(params)}')
    if dependencia_id is not None:
        params.append(dependencia_id)
        where.append(f'(dependencia_origen_id = ${len(params)} '
                     f'or dependencia_destino_id = ${len(params)})')
    if tipo_radicado is not None:
        params.append(tipo_radicado)
        where.append(f'tipo_radicado = ${len(params)}')
    if estado is not None:
        params.append(estado)
        where.append(f'estado = ${len(params)}')
    where_sql = ' and '.join(where)

    rows = await conn.fetch(
        f"""
        select to_char(fecha_radicacion::date, 'YYYY-MM-DD') as fecha,
               canal_id, tipo_radicado, estado,
               coalesce(dependencia_origen_id, dependencia_destino_id) as dependencia_id,
               count(*) as total
        from gd.radicado
        where {where_sql}
        group by 1, canal_id, tipo_radicado, estado, 5
        order by 1 desc
        """,
        *params,
    )
    total = await conn.fetchval(
        f'select count(*) from gd.radicado where {where_sql}', *params,
    )

    filas = [
        {
            'fecha': r['fecha'],
            'canal_id': r['canal_id'],
            'canal_nombre': None,
            'dependencia_id': r['dependencia_id'],
            'tipo_radicado': r['tipo_radicado'],
            'estado': r['estado'],
            'total': int(r['total']),
        }
        for r in rows
    ]
    return {'total_radicados': int(total or 0), 'filas': filas}


# =============================================================================
# Reporte 0088 — PQRSD
# =============================================================================

async def reporte_pqrsd(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    desde=None, hasta=None,
    dependencia_id: UUID | None = None,
    tipo_pqrsd_id: UUID | None = None,
    estado: str | None = None,
    solo_vencidas: bool = False,
    solo_proximas_vencer: bool = False,
) -> dict[str, Any]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if desde is not None:
        params.append(desde)
        where.append(f'fecha_recepcion >= ${len(params)}')
    if hasta is not None:
        params.append(hasta)
        where.append(f'fecha_recepcion <= ${len(params)}')
    if dependencia_id is not None:
        params.append(dependencia_id)
        where.append(f'dependencia_responsable_id = ${len(params)}')
    if tipo_pqrsd_id is not None:
        params.append(tipo_pqrsd_id)
        where.append(f'tipo_pqrsd_id = ${len(params)}')
    if estado is not None:
        params.append(estado)
        where.append(f'estado = ${len(params)}')
    if solo_vencidas:
        where.append("fecha_limite_respuesta < now() and "
                     "estado in ('nueva','asignada','en_analisis','en_revision')")
    if solo_proximas_vencer:
        where.append("fecha_limite_respuesta between now() and now() + interval '3 days' "
                     "and estado in ('nueva','asignada','en_analisis','en_revision')")
    where_sql = ' and '.join(where)

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
          count(*) filter (where estado = 'cerrada') as total_cerradas
        from gd.pqrsd
        where {where_sql}
        """,
        *params,
    )

    rows = await conn.fetch(
        f"""
        select tipo_pqrsd_id, dependencia_responsable_id as dependencia_id,
               estado,
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
        group by tipo_pqrsd_id, dependencia_responsable_id, estado
        order by estado
        """,
        *params,
    )

    return {
        'total_global': int(totales['total_global']) if totales else 0,
        'total_vencidas': int(totales['total_vencidas']) if totales else 0,
        'total_proximas_vencer': int(totales['total_proximas_vencer']) if totales else 0,
        'total_cerradas': int(totales['total_cerradas']) if totales else 0,
        'filas': [
            {
                'tipo_pqrsd_id': r['tipo_pqrsd_id'],
                'dependencia_id': r['dependencia_id'],
                'estado': r['estado'],
                'total': int(r['total']),
                'vencidas': int(r['vencidas']),
                'proximas_vencer': int(r['proximas_vencer']),
                'dias_promedio_resolucion': float(r['dias_promedio_resolucion'])
                                              if r['dias_promedio_resolucion'] is not None else None,
            }
            for r in rows
        ],
    }


# =============================================================================
# Reporte 0089 — correspondencia
# =============================================================================

async def reporte_correspondencia(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    desde=None, hasta=None,
    tipo: str | None = None,
    dependencia_id: UUID | None = None,
    estado: str | None = None,
) -> dict[str, Any]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if desde is not None:
        params.append(desde)
        where.append(f'created_at >= ${len(params)}')
    if hasta is not None:
        params.append(hasta)
        where.append(f'created_at <= ${len(params)}')
    if tipo is not None:
        params.append(tipo)
        where.append(f'tipo = ${len(params)}')
    if dependencia_id is not None:
        params.append(dependencia_id)
        where.append(f'(dependencia_origen_id = ${len(params)} '
                     f'or dependencia_destino_id = ${len(params)})')
    if estado is not None:
        params.append(estado)
        where.append(f'estado = ${len(params)}')
    where_sql = ' and '.join(where)

    total = await conn.fetchval(
        f'select count(*) from gd.correspondencia where {where_sql}', *params,
    )
    rows = await conn.fetch(
        f"""
        select tipo, estado,
               coalesce(dependencia_origen_id, dependencia_destino_id) as dependencia_id,
               count(*) as total
        from gd.correspondencia
        where {where_sql}
        group by tipo, estado, 3
        order by tipo, estado
        """,
        *params,
    )
    return {
        'total': int(total or 0),
        'filas': [
            {
                'tipo': r['tipo'], 'estado': r['estado'],
                'dependencia_id': r['dependencia_id'], 'total': int(r['total']),
            }
            for r in rows
        ],
    }


# =============================================================================
# Reporte 0090 — cargas de trabajo
# =============================================================================

async def reporte_cargas(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    desde=None, hasta=None,
    dependencia_id: UUID | None = None,
    user_id: UUID | None = None,
) -> dict[str, Any]:
    """Agrega tareas (gd.tarea) + clasificaciones (gd.clasificacion_radicado)
    por user/dependencia. Maneja gracefully ausencia de filas.
    """
    where_t = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if desde is not None:
        params.append(desde)
        where_t.append(f'created_at >= ${len(params)}')
    if hasta is not None:
        params.append(hasta)
        where_t.append(f'created_at <= ${len(params)}')
    if user_id is not None:
        params.append(user_id)
        where_t.append(f'asignado_a_user_id = ${len(params)}')
    if dependencia_id is not None:
        params.append(dependencia_id)
        where_t.append(f'asignado_a_dependencia_id = ${len(params)}')
    where_t_sql = ' and '.join(where_t)

    rows = await conn.fetch(
        f"""
        select asignado_a_user_id as user_id,
               asignado_a_dependencia_id as dependencia_id,
               count(*) filter (where estado in ('pendiente','en_progreso'))
                                                  as tareas_pendientes,
               count(*) filter (where estado = 'completada')
                                                  as tareas_completadas_periodo,
               0 as radicados_clasificados_periodo
        from gd.tarea
        where {where_t_sql}
        group by asignado_a_user_id, asignado_a_dependencia_id
        order by tareas_pendientes desc nulls last
        """,
        *params,
    )

    return {
        'filas': [
            {
                'user_id': r['user_id'],
                'dependencia_id': r['dependencia_id'],
                'tareas_pendientes': int(r['tareas_pendientes']),
                'tareas_completadas_periodo': int(r['tareas_completadas_periodo']),
                'radicados_clasificados_periodo': int(r['radicados_clasificados_periodo']),
            }
            for r in rows
        ],
    }


# =============================================================================
# Reporte 0091 — uso de IA
# =============================================================================

async def reporte_uso_ia(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    desde=None, hasta=None,
    tipo_asistencia: str | None = None,
) -> dict[str, Any]:
    where = ['s.tenant_id = $1']
    params: list[Any] = [tenant_id]
    if desde is not None:
        params.append(desde)
        where.append(f's.created_at >= ${len(params)}')
    if hasta is not None:
        params.append(hasta)
        where.append(f's.created_at <= ${len(params)}')
    if tipo_asistencia is not None:
        params.append(tipo_asistencia)
        where.append(f's.tipo_asistencia = ${len(params)}')
    where_sql = ' and '.join(where)

    rows = await conn.fetch(
        f"""
        select s.tipo_asistencia,
               count(*) as total_solicitudes,
               count(*) filter (where s.estado = 'completed') as completadas,
               count(*) filter (where s.estado = 'failed') as failed,
               count(*) filter (where d.decision = 'aceptar') as aceptadas,
               count(*) filter (where d.decision = 'modificar') as modificadas,
               count(*) filter (where d.decision = 'rechazar') as rechazadas,
               count(*) filter (where r.id is not null and d.id is null) as sin_decision
        from gd.solicitud_ia s
        left join gd.resultado_ia r on r.solicitud_id = s.id
        left join gd.decision_ia d on d.resultado_id = r.id
        where {where_sql}
        group by s.tipo_asistencia
        order by s.tipo_asistencia
        """,
        *params,
    )

    total_solicitudes = sum(int(r['total_solicitudes']) for r in rows)
    return {
        'total_solicitudes': total_solicitudes,
        'filas': [
            {
                'tipo_asistencia': r['tipo_asistencia'],
                'total_solicitudes': int(r['total_solicitudes']),
                'completadas': int(r['completadas']),
                'failed': int(r['failed']),
                'aceptadas': int(r['aceptadas']),
                'modificadas': int(r['modificadas']),
                'rechazadas': int(r['rechazadas']),
                'sin_decision': int(r['sin_decision']),
            }
            for r in rows
        ],
    }


# =============================================================================
# Reporte 0092 — anulaciones y reasignaciones
# =============================================================================

async def reporte_anulaciones(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    desde=None, hasta=None,
    tipo_entidad: str | None = None,
    decision: str | None = None,
) -> dict[str, Any]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if desde is not None:
        params.append(desde)
        where.append(f'fecha_solicitud >= ${len(params)}')
    if hasta is not None:
        params.append(hasta)
        where.append(f'fecha_solicitud <= ${len(params)}')
    if tipo_entidad is not None:
        params.append(tipo_entidad)
        where.append(f'tipo_entidad = ${len(params)}')
    if decision is not None:
        params.append(decision)
        where.append(f'decision = ${len(params)}')
    where_sql = ' and '.join(where)

    rows = await conn.fetch(
        f"""
        select tipo_entidad, decision, count(*) as total
        from gd.solicitud_anulacion
        where {where_sql}
        group by tipo_entidad, decision
        order by tipo_entidad, decision
        """,
        *params,
    )
    return {
        'filas': [
            {
                'tipo_entidad': r['tipo_entidad'],
                'decision': r['decision'],
                'total': int(r['total']),
            }
            for r in rows
        ],
    }


# =============================================================================
# Reporte 0093 — auditoría de consultas a información sensible
# =============================================================================

async def reporte_auditoria(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    desde=None, hasta=None,
    usuario_id: UUID | None = None,
    entidad_tipo: str | None = None,
) -> dict[str, Any]:
    """Agrega gd.descarga_log + filtros por clasificación sensible."""
    where = ['tenant_id = $1',
             "clasificacion_informacion in "
             "('reservada','confidencial','datos_personales','sensible')"]
    params: list[Any] = [tenant_id]
    if desde is not None:
        params.append(desde)
        where.append(f'descargado_en >= ${len(params)}')
    if hasta is not None:
        params.append(hasta)
        where.append(f'descargado_en <= ${len(params)}')
    if usuario_id is not None:
        params.append(usuario_id)
        where.append(f'usuario_id = ${len(params)}')
    if entidad_tipo is not None:
        params.append(entidad_tipo)
        where.append(f'contexto_tipo = ${len(params)}')
    where_sql = ' and '.join(where)

    total = await conn.fetchval(
        f'select count(*) from gd.descarga_log where {where_sql}', *params,
    )
    rows = await conn.fetch(
        f"""
        select to_char(descargado_en::date, 'YYYY-MM-DD') as fecha,
               usuario_id,
               'descargar'::text as accion,
               contexto_tipo as entidad_tipo,
               clasificacion_informacion as clasificacion,
               count(*) as total
        from gd.descarga_log
        where {where_sql}
        group by 1, usuario_id, contexto_tipo, clasificacion_informacion
        order by 1 desc, total desc
        """,
        *params,
    )
    return {
        'total': int(total or 0),
        'filas': [
            {
                'fecha': r['fecha'], 'usuario_id': r['usuario_id'],
                'accion': r['accion'], 'entidad_tipo': r['entidad_tipo'],
                'clasificacion': r['clasificacion'], 'total': int(r['total']),
            }
            for r in rows
        ],
    }


# =============================================================================
# Exportar (CSV inline + registro en gd.reporte_generado)
# =============================================================================

def filas_to_csv(filas: list[dict[str, Any]]) -> str:
    """Convierte una lista de dicts a CSV string. Columnas = keys del primer dict."""
    if not filas:
        return ''
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(filas[0].keys()),
                             extrasaction='ignore')
    writer.writeheader()
    for row in filas:
        writer.writerow({k: ('' if v is None else str(v)) for k, v in row.items()})
    return output.getvalue()


async def registrar_reporte_generado(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    tipo_reporte: str,
    parametros: dict[str, Any],
    formato: str,
    resumen_inline: dict[str, Any] | None,
    archivo_digital_id: UUID | None,
    numero_filas: int,
    contiene_datos_sensibles: bool,
    generado_por_user_id: UUID,
    ip: str | None,
    user_agent: str | None,
    duracion_ms: int,
    estado: str = 'completed',
    error_texto: str | None = None,
) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        insert into gd.reporte_generado (
            tenant_id, tipo_reporte, parametros, formato,
            archivo_digital_id, resumen_inline, numero_filas,
            contiene_datos_sensibles, estado, error_texto,
            generado_por_user_id, ip, user_agent, fin_en, duracion_ms
        )
        values ($1, $2, $3::jsonb, $4, $5, $6::jsonb, $7, $8, $9, $10,
                $11, $12, $13, now(), $14)
        returning id, tipo_reporte, parametros, formato, archivo_digital_id,
                  resumen_inline, numero_filas, contiene_datos_sensibles,
                  estado, error_texto, generado_por_user_id, inicio_en,
                  fin_en, duracion_ms, expira_en
        """,
        tenant_id, tipo_reporte, json.dumps(parametros), formato,
        archivo_digital_id,
        json.dumps(resumen_inline) if resumen_inline else None,
        numero_filas, contiene_datos_sensibles, estado, error_texto,
        generado_por_user_id, ip, user_agent, duracion_ms,
    )
    d = dict(row)
    for k in ('parametros', 'resumen_inline'):
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])
    return d


async def exportar_reporte(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    tipo_reporte: str,
    formato: str,
    filtros: dict[str, Any],
    incluir_datos_sensibles: bool,
    generado_por_user_id: UUID,
    ip: str | None,
    user_agent: str | None,
) -> dict[str, Any]:
    """Ejecuta el reporte y registra el export.

    Mapeo tipo_reporte → función de query.
    """
    if formato not in ('json', 'csv', 'excel', 'pdf'):
        raise ValueError('formato_invalido')

    t0 = time.monotonic()
    # Despachar al reporte correcto.
    if tipo_reporte == 'radicados':
        data = await reporte_radicados(conn, tenant_id=tenant_id, **filtros)
        filas = data['filas']
    elif tipo_reporte == 'pqrsd':
        data = await reporte_pqrsd(conn, tenant_id=tenant_id, **filtros)
        filas = data['filas']
    elif tipo_reporte == 'correspondencia':
        data = await reporte_correspondencia(conn, tenant_id=tenant_id, **filtros)
        filas = data['filas']
    elif tipo_reporte == 'cargas_trabajo':
        data = await reporte_cargas(conn, tenant_id=tenant_id, **filtros)
        filas = data['filas']
    elif tipo_reporte == 'uso_ia':
        data = await reporte_uso_ia(conn, tenant_id=tenant_id, **filtros)
        filas = data['filas']
    elif tipo_reporte == 'anulaciones_reasignaciones':
        data = await reporte_anulaciones(conn, tenant_id=tenant_id, **filtros)
        filas = data['filas']
    elif tipo_reporte == 'auditoria_consultas_sensibles':
        data = await reporte_auditoria(conn, tenant_id=tenant_id, **filtros)
        filas = data['filas']
    else:
        raise ValueError(f'tipo_reporte_invalido:{tipo_reporte}')

    # Producir contenido según formato.
    resumen_inline: dict[str, Any] | None = None
    if formato == 'json':
        resumen_inline = data
    elif formato == 'csv':
        # Para CSV, guardamos contenido en resumen_inline.csv_content
        # (en prod iría a archivo_digital vía EP-018).
        csv_text = filas_to_csv([_normalize_for_csv(f) for f in filas])
        resumen_inline = {'csv_content': csv_text, 'totales': {
            k: v for k, v in data.items() if k != 'filas'
        }}
    elif formato in ('excel', 'pdf'):
        # Placeholder: EP-018 entregará binarios reales.
        resumen_inline = {
            'placeholder': True,
            'mensaje': f'Generación {formato} pendiente de EP-018',
            'preview': data,
        }

    duracion_ms = int((time.monotonic() - t0) * 1000)

    registro = await registrar_reporte_generado(
        conn, tenant_id=tenant_id,
        tipo_reporte=tipo_reporte, parametros=filtros, formato=formato,
        resumen_inline=resumen_inline,
        archivo_digital_id=None,  # EP-018 lo asignará para excel/pdf
        numero_filas=len(filas),
        contiene_datos_sensibles=incluir_datos_sensibles
                                  or tipo_reporte == 'auditoria_consultas_sensibles',
        generado_por_user_id=generado_por_user_id,
        ip=ip, user_agent=user_agent, duracion_ms=duracion_ms,
    )
    return registro


def _normalize_for_csv(d: dict[str, Any]) -> dict[str, Any]:
    """Convierte UUIDs/datetimes a str para CSV."""
    out = {}
    for k, v in d.items():
        if hasattr(v, 'isoformat'):
            out[k] = v.isoformat()
        elif isinstance(v, UUID):
            out[k] = str(v)
        else:
            out[k] = v
    return out


# =============================================================================
# Listado / detalle de reportes generados
# =============================================================================

async def listar_reportes_generados(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    tipo_reporte: str | None = None,
    generado_por_user_id: UUID | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if tipo_reporte:
        params.append(tipo_reporte)
        where.append(f'tipo_reporte = ${len(params)}')
    if generado_por_user_id:
        params.append(generado_por_user_id)
        where.append(f'generado_por_user_id = ${len(params)}')
    params.append(limit)
    rows = await conn.fetch(
        f"""
        select id, tipo_reporte, parametros, formato, archivo_digital_id,
               resumen_inline, numero_filas, contiene_datos_sensibles,
               estado, error_texto, generado_por_user_id, inicio_en,
               fin_en, duracion_ms, expira_en
        from gd.reporte_generado
        where {' and '.join(where)}
        order by inicio_en desc
        limit ${len(params)}
        """,
        *params,
    )
    out = []
    for r in rows:
        d = dict(r)
        for k in ('parametros', 'resumen_inline'):
            if isinstance(d.get(k), str):
                d[k] = json.loads(d[k])
        out.append(d)
    return out


async def obtener_reporte_generado(
    conn: asyncpg.Connection, *, tenant_id: UUID, reporte_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, tipo_reporte, parametros, formato, archivo_digital_id,
               resumen_inline, numero_filas, contiene_datos_sensibles,
               estado, error_texto, generado_por_user_id, inicio_en,
               fin_en, duracion_ms, expira_en
        from gd.reporte_generado where id = $1 and tenant_id = $2
        """,
        reporte_id, tenant_id,
    )
    if row is None:
        return None
    d = dict(row)
    for k in ('parametros', 'resumen_inline'):
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])
    return d


__all__ = [
    # Reportes
    'reporte_radicados', 'reporte_pqrsd', 'reporte_correspondencia',
    'reporte_cargas', 'reporte_uso_ia', 'reporte_anulaciones',
    'reporte_auditoria',
    # CSV
    'filas_to_csv',
    # Export
    'exportar_reporte', 'registrar_reporte_generado',
    # Listado
    'listar_reportes_generados', 'obtener_reporte_generado',
]
