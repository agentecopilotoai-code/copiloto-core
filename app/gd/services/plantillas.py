"""Services SQL para EP-010 plantillas documentales (bloque 11).

Cubre:
- CRUD plantillas + versionado
- activar / inactivar (transiciones de estado)
- generar documento desde plantilla (resuelve contexto + invoca svc_documentos)
- asociaciones (dependencia / tipo_trámite)
- seed plantillas institucionales (7 mínimas)
"""
from __future__ import annotations

import json
import re
from typing import Any
from uuid import UUID

import asyncpg


# Plantillas seed institucionales — codigos canónicos.
SEED_PLANTILLAS = [
    {
        'codigo': 'OFICIO_RESPUESTA',
        'nombre': 'Oficio de respuesta',
        'tipo_plantilla': 'oficio_respuesta',
        'descripcion': 'Plantilla institucional para oficios de respuesta.',
        'contenido_template': (
            '{{org.nombre}}\n{{org.nit}}\n{{org.direccion}}\n\n'
            '{{org.ciudad}}, {{fecha_actual}}\n\n'
            'Señor(a) {{destinatario.nombre}}\n'
            '{{destinatario.cargo}}\n{{destinatario.direccion}}\n\n'
            'Asunto: {{asunto}}\nReferencia: {{radicado_referencia}}\n\n'
            '{{cuerpo}}\n\nAtentamente,\n\n'
            '{{firmante.nombre}}\n{{firmante.cargo}} — {{firmante.dependencia}}'
        ),
        'json_schema_campos': {
            'type': 'object',
            'properties': {
                'asunto': {'type': 'string'},
                'cuerpo': {'type': 'string'},
            },
            'required': ['asunto', 'cuerpo'],
        },
    },
    {
        'codigo': 'MEMORANDO_INTERNO',
        'nombre': 'Memorando interno',
        'tipo_plantilla': 'memorando_interno',
        'descripcion': 'Memorando para comunicación interna entre dependencias.',
        'contenido_template': (
            'MEMORANDO INTERNO\n\n'
            'Para: {{destinatario.dependencia}}\n'
            'De: {{remitente.dependencia}}\n'
            'Fecha: {{fecha_actual}}\nAsunto: {{asunto}}\n\n'
            '{{cuerpo}}\n\n{{firmante.nombre}}\n{{firmante.cargo}}'
        ),
        'json_schema_campos': {
            'type': 'object',
            'properties': {'asunto': {'type': 'string'}, 'cuerpo': {'type': 'string'}},
            'required': ['asunto', 'cuerpo'],
        },
    },
    {
        'codigo': 'CONSTANCIA_RADICACION',
        'nombre': 'Constancia de radicación',
        'tipo_plantilla': 'constancia_radicacion',
        'descripcion': 'Constancia de radicación de documento.',
        'contenido_template': (
            'CONSTANCIA DE RADICACIÓN\n\n'
            'La {{org.nombre}} hace constar que el día {{fecha_radicacion}} '
            'fue radicado el documento con número {{radicado.numero}}.\n\n'
            'Asunto: {{radicado.asunto}}\n'
            'Remitente: {{radicado.remitente}}\nCanal: {{radicado.canal}}\n\n'
            '{{org.ciudad}}, {{fecha_actual}}'
        ),
        'json_schema_campos': {
            'type': 'object',
            'properties': {},
        },
    },
    {
        'codigo': 'TRASLADO_COMPETENCIA',
        'nombre': 'Traslado por competencia',
        'tipo_plantilla': 'traslado_competencia',
        'descripcion': 'Oficio de traslado por competencia a otra entidad.',
        'contenido_template': (
            '{{org.nombre}}\n\n{{org.ciudad}}, {{fecha_actual}}\n\n'
            'Señores\n{{entidad_competente.nombre}}\n'
            '{{entidad_competente.direccion}}\n\n'
            'Asunto: Traslado por competencia\n'
            'Referencia: {{radicado_referencia}}\n\n'
            'Por considerarse de su competencia, trasladamos la solicitud '
            'recibida bajo el radicado {{radicado.numero}} con el siguiente '
            'asunto: {{radicado.asunto}}.\n\nMotivo del traslado: {{motivo}}\n\n'
            'Atentamente,\n\n{{firmante.nombre}}\n{{firmante.cargo}}'
        ),
        'json_schema_campos': {
            'type': 'object',
            'properties': {
                'entidad_competente': {'type': 'object'},
                'motivo': {'type': 'string'},
            },
            'required': ['entidad_competente', 'motivo'],
        },
    },
    {
        'codigo': 'SOLICITUD_INFO_ADICIONAL',
        'nombre': 'Solicitud de información adicional',
        'tipo_plantilla': 'solicitud_info_adicional',
        'descripcion': 'Solicitud de información adicional al solicitante de PQRSD.',
        'contenido_template': (
            '{{org.nombre}}\n\n{{org.ciudad}}, {{fecha_actual}}\n\n'
            'Señor(a) {{solicitante.nombre}}\n\n'
            'Asunto: Solicitud de información adicional\n'
            'Referencia: PQRSD {{pqrsd.codigo}}\n\n'
            'En el marco de su solicitud {{pqrsd.codigo}}, requerimos la '
            'siguiente información para continuar el trámite:\n\n'
            '{{informacion_solicitada}}\n\n'
            'El término de respuesta se suspende mientras recibimos su '
            'documentación.\n\nAtentamente,\n\n{{firmante.nombre}}'
        ),
        'json_schema_campos': {
            'type': 'object',
            'properties': {'informacion_solicitada': {'type': 'string'}},
            'required': ['informacion_solicitada'],
        },
    },
    {
        'codigo': 'RESPUESTA_PQRSD',
        'nombre': 'Respuesta a PQRSD',
        'tipo_plantilla': 'respuesta_pqrsd',
        'descripcion': 'Plantilla institucional para respuesta a PQRSD.',
        'contenido_template': (
            '{{org.nombre}}\n{{org.nit}}\n\n'
            '{{org.ciudad}}, {{fecha_actual}}\n\n'
            'Señor(a) {{solicitante.nombre}}\n{{solicitante.direccion}}\n\n'
            'Asunto: Respuesta a su PQRSD\n'
            'Referencia: {{pqrsd.codigo}} — Radicado {{radicado.numero}}\n\n'
            'En atención a su {{pqrsd.tipo}} presentada el '
            '{{pqrsd.fecha_recepcion}}, le informamos lo siguiente:\n\n'
            '{{cuerpo_respuesta}}\n\n'
            'Atentamente,\n\n{{firmante.nombre}}\n{{firmante.cargo}} — '
            '{{firmante.dependencia}}'
        ),
        'json_schema_campos': {
            'type': 'object',
            'properties': {'cuerpo_respuesta': {'type': 'string'}},
            'required': ['cuerpo_respuesta'],
        },
    },
    {
        'codigo': 'COMUNICACION_EXTERNA_SALIDA',
        'nombre': 'Comunicación externa de salida',
        'tipo_plantilla': 'comunicacion_externa_salida',
        'descripcion': 'Comunicación de salida hacia terceros externos.',
        'contenido_template': (
            '{{org.nombre}}\n{{org.nit}}\n{{org.direccion}}\n\n'
            '{{org.ciudad}}, {{fecha_actual}}\n\n'
            'Señores\n{{destinatario.nombre}}\n{{destinatario.direccion}}\n\n'
            'Asunto: {{asunto}}\n\n{{cuerpo}}\n\nAtentamente,\n\n'
            '{{firmante.nombre}}\n{{firmante.cargo}}'
        ),
        'json_schema_campos': {
            'type': 'object',
            'properties': {
                'asunto': {'type': 'string'},
                'cuerpo': {'type': 'string'},
            },
            'required': ['asunto', 'cuerpo'],
        },
    },
]


# =============================================================================
# Helpers internos
# =============================================================================

_TEMPLATE_VAR_RE = re.compile(r'\{\{\s*([\w.]+)\s*\}\}')


def render_template(template: str, contexto: dict[str, Any]) -> str:
    """Reemplaza marcadores {{path.to.var}} con valores de `contexto`.

    Variables no encontradas se reemplazan por string vacío y se logueean
    en `variables_no_encontradas`.
    """
    def lookup(path: str) -> str:
        keys = path.split('.')
        cur: Any = contexto
        for k in keys:
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                return ''
        return str(cur) if cur is not None else ''

    return _TEMPLATE_VAR_RE.sub(lambda m: lookup(m.group(1)), template)


async def _listar_versiones(
    conn: asyncpg.Connection, *, tenant_id: UUID, plantilla_id: UUID,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select id, plantilla_id, numero_version, contenido_template,
               archivo_digital_id, mime_type, json_schema_campos,
               estado, notas, created_by_user_id, created_at
        from gd.version_plantilla
        where plantilla_id = $1 and tenant_id = $2
        order by numero_version desc
        """,
        plantilla_id, tenant_id,
    )
    out = []
    for r in rows:
        d = dict(r)
        if isinstance(d['json_schema_campos'], str):
            d['json_schema_campos'] = json.loads(d['json_schema_campos'])
        out.append(d)
    return out


# =============================================================================
# CRUD Plantilla (GD-API-0064)
# =============================================================================

async def crear_plantilla(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    codigo: str,
    nombre: str,
    descripcion: str | None,
    tipo_plantilla: str,
    dependencia_propietaria_id: UUID | None,
    es_institucional: bool,
    contenido_template: str | None,
    json_schema_campos: dict[str, Any] | None,
    mime_type: str,
    created_by_user_id: UUID,
) -> dict[str, Any]:
    """Crea plantilla; si trae contenido_template, crea primera versión 'borrador'.

    Raises:
        ValueError('codigo_ya_existe') si el código ya está en uso.
    """
    try:
        pl_row = await conn.fetchrow(
            """
            insert into gd.plantilla_documental (
                tenant_id, codigo, nombre, descripcion, tipo_plantilla,
                dependencia_propietaria_id, es_institucional,
                created_by_user_id
            )
            values ($1, $2, $3, $4, $5, $6, $7, $8)
            returning id, codigo, nombre, descripcion, tipo_plantilla,
                      estado, version_vigente_id, numero_version_vigente,
                      dependencia_propietaria_id, es_institucional,
                      created_by_user_id, created_at, updated_at
            """,
            tenant_id, codigo, nombre, descripcion, tipo_plantilla,
            dependencia_propietaria_id, es_institucional, created_by_user_id,
        )
    except asyncpg.UniqueViolationError as e:
        raise ValueError('codigo_ya_existe') from e

    d = dict(pl_row)
    d['versiones'] = []

    if contenido_template is not None:
        ver_row = await crear_version_plantilla(
            conn, tenant_id=tenant_id, plantilla_id=d['id'],
            contenido_template=contenido_template,
            json_schema_campos=json_schema_campos,
            archivo_digital_id=None, mime_type=mime_type,
            notas='Versión inicial', created_by_user_id=created_by_user_id,
        )
        d['versiones'] = [ver_row]
    return d


async def obtener_plantilla(
    conn: asyncpg.Connection, *, tenant_id: UUID, plantilla_id: UUID,
) -> dict[str, Any] | None:
    pl = await conn.fetchrow(
        """
        select id, codigo, nombre, descripcion, tipo_plantilla,
               estado, version_vigente_id, numero_version_vigente,
               dependencia_propietaria_id, es_institucional,
               created_by_user_id, created_at, updated_at
        from gd.plantilla_documental where id = $1 and tenant_id = $2
        """,
        plantilla_id, tenant_id,
    )
    if pl is None:
        return None
    d = dict(pl)
    d['versiones'] = await _listar_versiones(
        conn, tenant_id=tenant_id, plantilla_id=plantilla_id,
    )
    return d


async def listar_plantillas(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    estado: list[str] | None = None,
    tipo_plantilla: str | None = None,
    dependencia_id: UUID | None = None,
    es_institucional: bool | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if estado:
        params.append(estado)
        where.append(f'estado = any(${len(params)}::text[])')
    if tipo_plantilla:
        params.append(tipo_plantilla)
        where.append(f'tipo_plantilla = ${len(params)}')
    if dependencia_id:
        params.append(dependencia_id)
        where.append(f'dependencia_propietaria_id = ${len(params)}')
    if es_institucional is not None:
        params.append(es_institucional)
        where.append(f'es_institucional = ${len(params)}')
    params.append(limit)
    where_sql = ' and '.join(where)
    rows = await conn.fetch(
        f"""
        select id, codigo, nombre, tipo_plantilla, estado,
               numero_version_vigente, dependencia_propietaria_id,
               es_institucional, created_at
        from gd.plantilla_documental
        where {where_sql}
        order by nombre
        limit ${len(params)}
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def contar_plantillas(
    conn: asyncpg.Connection, *, tenant_id: UUID,
) -> int:
    n = await conn.fetchval(
        'select count(*) from gd.plantilla_documental where tenant_id = $1',
        tenant_id,
    )
    return int(n or 0)


async def patch_plantilla(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    plantilla_id: UUID,
    nombre: str | None,
    descripcion: str | None,
    dependencia_propietaria_id: UUID | None,
) -> dict[str, Any] | None:
    pl = await conn.fetchval(
        'select 1 from gd.plantilla_documental where id = $1 and tenant_id = $2',
        plantilla_id, tenant_id,
    )
    if not pl:
        return None

    sets, params = [], [plantilla_id, tenant_id]
    if nombre is not None:
        params.append(nombre)
        sets.append(f'nombre = ${len(params)}')
    if descripcion is not None:
        params.append(descripcion)
        sets.append(f'descripcion = ${len(params)}')
    if dependencia_propietaria_id is not None:
        params.append(dependencia_propietaria_id)
        sets.append(f'dependencia_propietaria_id = ${len(params)}')
    if not sets:
        return await obtener_plantilla(
            conn, tenant_id=tenant_id, plantilla_id=plantilla_id,
        )
    await conn.execute(
        f"""
        update gd.plantilla_documental
        set {', '.join(sets)}
        where id = $1 and tenant_id = $2
        """,
        *params,
    )
    return await obtener_plantilla(
        conn, tenant_id=tenant_id, plantilla_id=plantilla_id,
    )


# =============================================================================
# Versiones de plantilla
# =============================================================================

async def crear_version_plantilla(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    plantilla_id: UUID,
    contenido_template: str,
    json_schema_campos: dict[str, Any] | None,
    archivo_digital_id: UUID | None,
    mime_type: str,
    notas: str | None,
    created_by_user_id: UUID,
) -> dict[str, Any]:
    """Crea nueva versión en estado 'borrador'.

    Numera incrementalmente sobre el max actual.
    """
    max_num = await conn.fetchval(
        'select coalesce(max(numero_version),0) from gd.version_plantilla '
        'where plantilla_id = $1 and tenant_id = $2',
        plantilla_id, tenant_id,
    )
    nuevo_num = int(max_num) + 1

    row = await conn.fetchrow(
        """
        insert into gd.version_plantilla (
            tenant_id, plantilla_id, numero_version, contenido_template,
            archivo_digital_id, mime_type, json_schema_campos, estado,
            notas, created_by_user_id
        )
        values ($1, $2, $3, $4, $5, $6, $7::jsonb, 'borrador', $8, $9)
        returning id, plantilla_id, numero_version, contenido_template,
                  archivo_digital_id, mime_type, json_schema_campos,
                  estado, notas, created_by_user_id, created_at
        """,
        tenant_id, plantilla_id, nuevo_num, contenido_template,
        archivo_digital_id, mime_type,
        json.dumps(json_schema_campos or {'type': 'object', 'properties': {}}),
        notas, created_by_user_id,
    )
    d = dict(row)
    if isinstance(d['json_schema_campos'], str):
        d['json_schema_campos'] = json.loads(d['json_schema_campos'])
    return d


# =============================================================================
# Activar / inactivar
# =============================================================================

async def activar_plantilla(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    plantilla_id: UUID,
    version_id: UUID | None,
    usuario_actor_id: UUID,
) -> dict[str, Any] | None:
    """Marca una versión como 'activa' y actualiza el header de plantilla.

    Si version_id es None, usa la última versión 'borrador'. La versión
    anteriormente activa pasa a 'reemplazada'.
    """
    pl = await conn.fetchrow(
        'select estado, version_vigente_id from gd.plantilla_documental '
        'where id = $1 and tenant_id = $2',
        plantilla_id, tenant_id,
    )
    if pl is None:
        return None

    # Resolver versión target.
    if version_id is None:
        ver = await conn.fetchrow(
            """
            select id, numero_version from gd.version_plantilla
            where plantilla_id = $1 and tenant_id = $2 and estado = 'borrador'
            order by numero_version desc
            limit 1
            """,
            plantilla_id, tenant_id,
        )
        if ver is None:
            raise ValueError('sin_version_borrador')
    else:
        ver = await conn.fetchrow(
            """
            select id, numero_version, estado from gd.version_plantilla
            where id = $1 and tenant_id = $2 and plantilla_id = $3
            """,
            version_id, tenant_id, plantilla_id,
        )
        if ver is None:
            raise ValueError('version_no_existe')
        if ver['estado'] not in ('borrador',):
            raise ValueError(f"version_estado_invalido:{ver['estado']}")

    # Marcar versión anterior activa como reemplazada.
    if pl['version_vigente_id'] is not None:
        await conn.execute(
            "update gd.version_plantilla set estado = 'reemplazada' "
            "where id = $1 and tenant_id = $2",
            pl['version_vigente_id'], tenant_id,
        )

    # Activar nueva versión.
    await conn.execute(
        "update gd.version_plantilla set estado = 'activa' "
        "where id = $1 and tenant_id = $2",
        ver['id'], tenant_id,
    )

    # Actualizar header.
    await conn.execute(
        """
        update gd.plantilla_documental
        set estado = 'activa',
            version_vigente_id = $3,
            numero_version_vigente = $4
        where id = $1 and tenant_id = $2
        """,
        plantilla_id, tenant_id, ver['id'], ver['numero_version'],
    )

    return await obtener_plantilla(
        conn, tenant_id=tenant_id, plantilla_id=plantilla_id,
    )


async def inactivar_plantilla(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    plantilla_id: UUID,
    usuario_actor_id: UUID,
) -> dict[str, Any] | None:
    pl = await conn.fetchrow(
        'select estado from gd.plantilla_documental where id = $1 and tenant_id = $2',
        plantilla_id, tenant_id,
    )
    if pl is None:
        return None
    if pl['estado'] == 'inactiva':
        raise ValueError('ya_inactiva')
    await conn.execute(
        "update gd.plantilla_documental set estado = 'inactiva' "
        "where id = $1 and tenant_id = $2",
        plantilla_id, tenant_id,
    )
    return await obtener_plantilla(
        conn, tenant_id=tenant_id, plantilla_id=plantilla_id,
    )


# =============================================================================
# Generar documento desde plantilla (GD-API-0065)
# =============================================================================

async def _resolver_contexto_generacion(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    radicado_id: UUID | None,
    pqrsd_id: UUID | None,
    correspondencia_id: UUID | None,
    usuario_id: UUID,
    datos_adicionales: dict[str, Any],
) -> dict[str, Any]:
    """Construye el dict de contexto que se pasa al renderer."""
    ctx: dict[str, Any] = {
        'datos_adicionales': datos_adicionales,
        **datos_adicionales,
    }

    # Datos institucionales (gd.perfil_organizacion).
    org = await conn.fetchrow(
        """
        select razon_social as nombre, nit, direccion, ciudad
        from gd.perfil_organizacion where tenant_id = $1
        """,
        tenant_id,
    )
    if org:
        ctx['org'] = dict(org)

    # Snapshot del usuario (firmante).
    usr = await conn.fetchrow(
        """
        select u.email, p.tipo_vinculacion, p.dependencia_actual_id,
               p.cargo_actual_id, c.nombre as cargo_nombre, d.nombre as dep_nombre
        from app.users u
        join gd.perfil_usuario p on p.user_id = u.id and p.tenant_id = $1
        left join gd.cargo c on c.id = p.cargo_actual_id
        left join gd.dependencia d on d.id = p.dependencia_actual_id
        where u.id = $2
        """,
        tenant_id, usuario_id,
    )
    if usr:
        ctx['firmante'] = {
            'nombre': usr['email'],  # nombre completo no siempre disponible
            'cargo': usr['cargo_nombre'] or '',
            'dependencia': usr['dep_nombre'] or '',
        }
    ctx['remitente'] = ctx.get('firmante', {})

    # Datos del radicado.
    if radicado_id is not None:
        rad = await conn.fetchrow(
            """
            select numero_radicado as numero, asunto, fecha_radicacion,
                   tipo_radicado
            from gd.radicado where id = $1 and tenant_id = $2
            """,
            radicado_id, tenant_id,
        )
        if rad:
            ctx['radicado'] = dict(rad)
            ctx['radicado_referencia'] = rad['numero']

    # Datos PQRSD.
    if pqrsd_id is not None:
        pq = await conn.fetchrow(
            """
            select p.id, p.asunto, p.fecha_recepcion, p.tipo_pqrsd_id,
                   t.nombre as tipo_nombre,
                   te.nombres || ' ' || te.apellidos as solicitante_nombre,
                   te.direccion as solicitante_direccion
            from gd.pqrsd p
            left join gd.tipo_pqrsd t on t.id = p.tipo_pqrsd_id
            left join gd.tercero te on te.id = p.tercero_id
            where p.id = $1 and p.tenant_id = $2
            """,
            pqrsd_id, tenant_id,
        )
        if pq:
            ctx['pqrsd'] = {
                'codigo': str(pq['id']),
                'asunto': pq['asunto'],
                'fecha_recepcion': str(pq['fecha_recepcion']),
                'tipo': pq['tipo_nombre'] or '',
            }
            ctx['solicitante'] = {
                'nombre': pq['solicitante_nombre'] or 'Anónimo',
                'direccion': pq['solicitante_direccion'] or '',
            }

    # Fecha actual (string ISO date).
    from datetime import date
    ctx['fecha_actual'] = date.today().isoformat()

    return ctx


async def generar_documento_desde_plantilla(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    plantilla_id: UUID,
    titulo: str | None,
    clasificacion_informacion: str,
    radicado_id: UUID | None,
    pqrsd_id: UUID | None,
    correspondencia_id: UUID | None,
    datos_adicionales: dict[str, Any],
    usuario_actor_id: UUID,
) -> dict[str, Any] | None:
    """Genera un documento desde la versión vigente de una plantilla.

    Retorna {documento_id, version_documento_id, plantilla_id,
    plantilla_version_id, contenido_renderizado, variables_usadas}.
    """
    from app.gd.services import documentos as svc_docs

    pl = await conn.fetchrow(
        """
        select id, codigo, nombre, estado, version_vigente_id
        from gd.plantilla_documental
        where id = $1 and tenant_id = $2
        """,
        plantilla_id, tenant_id,
    )
    if pl is None:
        return None
    if pl['estado'] != 'activa':
        raise ValueError(f"plantilla_estado_invalido:{pl['estado']}")
    if pl['version_vigente_id'] is None:
        raise ValueError('plantilla_sin_version_vigente')

    ver = await conn.fetchrow(
        """
        select id, contenido_template, mime_type, json_schema_campos
        from gd.version_plantilla
        where id = $1 and tenant_id = $2
        """,
        pl['version_vigente_id'], tenant_id,
    )
    if ver is None:
        raise ValueError('version_vigente_no_encontrada')

    # Construir contexto.
    contexto = await _resolver_contexto_generacion(
        conn, tenant_id=tenant_id,
        radicado_id=radicado_id, pqrsd_id=pqrsd_id,
        correspondencia_id=correspondencia_id,
        usuario_id=usuario_actor_id,
        datos_adicionales=datos_adicionales,
    )

    # Renderizar template.
    contenido_renderizado = render_template(ver['contenido_template'], contexto)

    # Crear documento institucional con contenido como archivo (vía svc_documentos).
    titulo_final = titulo or f"{pl['nombre']} — {pl['codigo']}"

    # archivo_digital_id placeholder: en producción se generaría DOCX/PDF
    # y se subiría vía EP-018. Aquí usamos un UUID derivado del request.
    from uuid import uuid4 as _uuid4
    archivo_id = _uuid4()

    doc = await svc_docs.crear_documento(
        conn, tenant_id=tenant_id,
        titulo=titulo_final, descripcion=None,
        clasificacion_informacion=clasificacion_informacion,
        trd_serie_codigo=None, trd_subserie_codigo=None,
        trd_tipo_documental=pl['codigo'],
        archivo_digital_id=archivo_id,
        mime_type=ver['mime_type'] if ver['mime_type'] in (
            'text/plain', 'text/markdown', 'application/pdf',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        ) else 'text/plain',
        tamano_bytes=len(contenido_renderizado.encode('utf-8')),
        hash_sha256=None,
        observaciones=f"Generado desde plantilla {pl['codigo']}",
        creado_por_user_id=usuario_actor_id,
    )

    return {
        'documento_id': doc['id'],
        'version_documento_id': doc['versiones'][0]['id'],
        'plantilla_id': plantilla_id,
        'plantilla_version_id': ver['id'],
        'contenido_renderizado': contenido_renderizado,
        'variables_usadas': contexto,
    }


# =============================================================================
# Asociaciones (GD-API-0066)
# =============================================================================

async def asociar_dependencia(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    plantilla_id: UUID,
    dependencia_id: UUID,
    creado_por_user_id: UUID,
) -> dict[str, Any] | None:
    pl = await conn.fetchval(
        'select 1 from gd.plantilla_documental where id = $1 and tenant_id = $2',
        plantilla_id, tenant_id,
    )
    if not pl:
        return None
    try:
        row = await conn.fetchrow(
            """
            insert into gd.plantilla_asociacion (
                tenant_id, plantilla_id, asociacion_tipo, asociacion_id,
                creado_por_user_id
            )
            values ($1, $2, 'dependencia', $3, $4)
            returning id, plantilla_id, asociacion_tipo, asociacion_id,
                      asociacion_codigo, creado_por_user_id, created_at
            """,
            tenant_id, plantilla_id, dependencia_id, creado_por_user_id,
        )
    except asyncpg.UniqueViolationError as e:
        raise ValueError('asociacion_ya_existe') from e
    return dict(row)


async def asociar_tipo_tramite(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    plantilla_id: UUID,
    tipo_tramite: str,
    creado_por_user_id: UUID,
) -> dict[str, Any] | None:
    pl = await conn.fetchval(
        'select 1 from gd.plantilla_documental where id = $1 and tenant_id = $2',
        plantilla_id, tenant_id,
    )
    if not pl:
        return None
    try:
        row = await conn.fetchrow(
            """
            insert into gd.plantilla_asociacion (
                tenant_id, plantilla_id, asociacion_tipo, asociacion_codigo,
                creado_por_user_id
            )
            values ($1, $2, 'tipo_tramite', $3, $4)
            returning id, plantilla_id, asociacion_tipo, asociacion_id,
                      asociacion_codigo, creado_por_user_id, created_at
            """,
            tenant_id, plantilla_id, tipo_tramite, creado_por_user_id,
        )
    except asyncpg.UniqueViolationError as e:
        raise ValueError('asociacion_ya_existe') from e
    return dict(row)


async def listar_asociaciones(
    conn: asyncpg.Connection, *, tenant_id: UUID, plantilla_id: UUID,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select id, plantilla_id, asociacion_tipo, asociacion_id,
               asociacion_codigo, creado_por_user_id, created_at
        from gd.plantilla_asociacion
        where plantilla_id = $1 and tenant_id = $2
        """,
        plantilla_id, tenant_id,
    )
    return [dict(r) for r in rows]


# =============================================================================
# Seed institucional (GD-API-0067)
# =============================================================================

async def seed_plantillas_institucionales(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    usuario_actor_id: UUID,
) -> dict[str, Any]:
    """Carga las 7 plantillas institucionales mínimas.

    Idempotente: si una plantilla con el código ya existe, la salta y
    la agrega a `plantillas_existentes`.
    """
    creadas: list[UUID] = []
    existentes: list[str] = []
    for seed in SEED_PLANTILLAS:
        try:
            row = await crear_plantilla(
                conn, tenant_id=tenant_id,
                codigo=seed['codigo'], nombre=seed['nombre'],
                descripcion=seed['descripcion'],
                tipo_plantilla=seed['tipo_plantilla'],
                dependencia_propietaria_id=None,
                es_institucional=True,
                contenido_template=seed['contenido_template'],
                json_schema_campos=seed['json_schema_campos'],
                mime_type='text/plain',
                created_by_user_id=usuario_actor_id,
            )
        except ValueError as e:
            if str(e) == 'codigo_ya_existe':
                existentes.append(seed['codigo'])
                continue
            raise
        creadas.append(row['id'])
    return {
        'plantillas_creadas': creadas,
        'plantillas_existentes': existentes,
        'total': len(creadas),
    }


__all__ = [
    # Constantes
    'SEED_PLANTILLAS',
    # Helpers
    'render_template',
    # CRUD
    'crear_plantilla', 'obtener_plantilla', 'listar_plantillas',
    'contar_plantillas', 'patch_plantilla',
    # Versiones
    'crear_version_plantilla',
    # Activación
    'activar_plantilla', 'inactivar_plantilla',
    # Generación
    'generar_documento_desde_plantilla',
    # Asociaciones
    'asociar_dependencia', 'asociar_tipo_tramite', 'listar_asociaciones',
    # Seed
    'seed_plantillas_institucionales',
]
