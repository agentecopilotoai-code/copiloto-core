"""Services para EP-021 periféricos parte 1 (bloque 21a).

Cubre GD-API-0128..0135:
- CRUD puntos atención + periféricos (con gate por módulo organización activo)
- Generación códigos barras/QR
- Impresión etiqueta + reimpresión controlada + impresión constancia
- Digitalización individual + webhook resultado del agente local

Convenciones:
- asyncpg raw SQL + RLS por tenant_id.
- Todo registro de impresión/digitalización es append-only (DELETE bloqueado
  por trigger SQL). Cambios de estado se hacen vía UPDATE.
- El servidor NO habla directamente con el periférico: encola job, el agente
  local reporta resultado vía webhook.
"""
from __future__ import annotations

import json
import secrets
from typing import Any
from uuid import UUID

import asyncpg


# =============================================================================
# Gate por módulo activo
# =============================================================================

class ModuloNoActivoError(LookupError):
    """Raise cuando la organización no tiene el módulo periféricos activo."""


async def assert_modulo_perifericos_activo(
    conn: asyncpg.Connection, *, tenant_id: UUID
) -> None:
    """Verifica que la organización tenga el módulo
    `ventanilla_presencial_con_perifericos` activado.

    Raise `ModuloNoActivoError` si no — los handlers traducen a HTTP 404
    (regla del backlog: "la organización no la verá en menús ni endpoints").
    """
    row = await conn.fetchrow(
        """
        select activado
        from gd.organizacion_modulo_activacion
        where tenant_id = $1
          and modulo_codigo = 'ventanilla_presencial_con_perifericos'
        """,
        tenant_id,
    )
    if row is None or not row['activado']:
        raise ModuloNoActivoError('modulo_perifericos_no_activo')


# =============================================================================
# Puntos de atención (GD-API-0130)
# =============================================================================

async def crear_punto_atencion(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    nombre: str,
    direccion: str | None,
    dependencia_responsable_id: UUID | None,
    metadata: dict[str, Any],
    creado_por_user_id: UUID,
) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        insert into gd.punto_atencion (
            tenant_id, nombre, direccion, dependencia_responsable_id,
            metadata, creado_por_user_id
        ) values ($1, $2, $3, $4, $5::jsonb, $6)
        returning id, nombre, direccion, dependencia_responsable_id,
                  estado, motivo_cierre, metadata, created_at, updated_at
        """,
        tenant_id, nombre, direccion, dependencia_responsable_id,
        json.dumps(metadata or {}), creado_por_user_id,
    )
    return _norm_punto(row)


async def listar_puntos(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, estado: str | None = None,
) -> list[dict[str, Any]]:
    if estado is not None:
        rows = await conn.fetch(
            """
            select id, nombre, direccion, dependencia_responsable_id,
                   estado, motivo_cierre, metadata, created_at, updated_at
            from gd.punto_atencion
            where tenant_id = $1 and estado = $2
            order by nombre
            """,
            tenant_id, estado,
        )
    else:
        rows = await conn.fetch(
            """
            select id, nombre, direccion, dependencia_responsable_id,
                   estado, motivo_cierre, metadata, created_at, updated_at
            from gd.punto_atencion
            where tenant_id = $1
            order by nombre
            """,
            tenant_id,
        )
    return [_norm_punto(r) for r in rows]


async def obtener_punto(
    conn: asyncpg.Connection, *, tenant_id: UUID, punto_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, nombre, direccion, dependencia_responsable_id,
               estado, motivo_cierre, metadata, created_at, updated_at
        from gd.punto_atencion
        where tenant_id = $1 and id = $2
        """,
        tenant_id, punto_id,
    )
    return _norm_punto(row) if row else None


async def patch_punto(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, punto_id: UUID,
    nombre: str | None, direccion: str | None,
    dependencia_responsable_id: UUID | None,
    metadata: dict[str, Any] | None,
) -> dict[str, Any] | None:
    sets: list[str] = []
    params: list[Any] = [tenant_id, punto_id]
    if nombre is not None:
        params.append(nombre)
        sets.append(f'nombre = ${len(params)}')
    if direccion is not None:
        params.append(direccion)
        sets.append(f'direccion = ${len(params)}')
    if dependencia_responsable_id is not None:
        params.append(dependencia_responsable_id)
        sets.append(f'dependencia_responsable_id = ${len(params)}')
    if metadata is not None:
        params.append(json.dumps(metadata))
        sets.append(f'metadata = ${len(params)}::jsonb')
    if not sets:
        return await obtener_punto(
            conn, tenant_id=tenant_id, punto_id=punto_id,
        )
    sets.append('updated_at = now()')
    row = await conn.fetchrow(
        f"""
        update gd.punto_atencion set {', '.join(sets)}
        where tenant_id = $1 and id = $2
        returning id, nombre, direccion, dependencia_responsable_id,
                  estado, motivo_cierre, metadata, created_at, updated_at
        """,
        *params,
    )
    return _norm_punto(row) if row else None


async def cambiar_estado_punto(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, punto_id: UUID,
    nuevo_estado: str, motivo: str,
) -> dict[str, Any]:
    """Cambia estado del punto. Si pasa a inactivo/cerrado, verifica que no
    queden periféricos activos huérfanos (regla GD-API-0130)."""
    # Validar existencia.
    existente = await obtener_punto(
        conn, tenant_id=tenant_id, punto_id=punto_id,
    )
    if existente is None:
        raise LookupError('punto_atencion_no_existe')

    if nuevo_estado in ('inactivo', 'cerrado'):
        huerfanos = await conn.fetchval(
            """
            select count(*) from gd.periferico
            where tenant_id = $1 and punto_atencion_id = $2
              and estado = 'activo'
            """,
            tenant_id, punto_id,
        )
        if huerfanos and huerfanos > 0:
            raise ValueError('perifericos_huerfanos')

    row = await conn.fetchrow(
        """
        update gd.punto_atencion
        set estado = $3, motivo_cierre = $4, updated_at = now()
        where tenant_id = $1 and id = $2
        returning id, nombre, direccion, dependencia_responsable_id,
                  estado, motivo_cierre, metadata, created_at, updated_at
        """,
        tenant_id, punto_id, nuevo_estado, motivo,
    )
    return _norm_punto(row)


async def listar_perifericos_de_punto(
    conn: asyncpg.Connection, *, tenant_id: UUID, punto_id: UUID,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select id, tipo_periferico, nombre, marca, modelo, serial,
               dependencia_id, punto_atencion_id, estado,
               motivo_cambio_estado, configuracion, ultimo_handshake_en,
               fecha_registro, created_at, updated_at
        from gd.periferico
        where tenant_id = $1 and punto_atencion_id = $2
        order by nombre
        """,
        tenant_id, punto_id,
    )
    return [_norm_perif(r) for r in rows]


def _norm_punto(row: Any) -> dict[str, Any]:
    if row is None:
        return None  # type: ignore[return-value]
    d = dict(row)
    md = d.get('metadata')
    if isinstance(md, str):
        d['metadata'] = json.loads(md) if md else {}
    elif md is None:
        d['metadata'] = {}
    return d


# =============================================================================
# Periféricos (GD-API-0129)
# =============================================================================

async def crear_periferico(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    tipo_periferico: str,
    nombre: str,
    marca: str | None,
    modelo: str | None,
    serial: str,
    dependencia_id: UUID | None,
    punto_atencion_id: UUID | None,
    configuracion: dict[str, Any],
    registrado_por_user_id: UUID,
) -> dict[str, Any]:
    try:
        row = await conn.fetchrow(
            """
            insert into gd.periferico (
                tenant_id, tipo_periferico, nombre, marca, modelo, serial,
                dependencia_id, punto_atencion_id, configuracion,
                registrado_por_user_id
            ) values ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10)
            returning id, tipo_periferico, nombre, marca, modelo, serial,
                      dependencia_id, punto_atencion_id, estado,
                      motivo_cambio_estado, configuracion, ultimo_handshake_en,
                      fecha_registro, created_at, updated_at
            """,
            tenant_id, tipo_periferico, nombre, marca, modelo, serial,
            dependencia_id, punto_atencion_id,
            json.dumps(configuracion or {}), registrado_por_user_id,
        )
    except asyncpg.UniqueViolationError as e:
        raise ValueError('serial_duplicado') from e
    return _norm_perif(row)


async def listar_perifericos(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    dependencia_id: UUID | None = None,
    punto_atencion_id: UUID | None = None,
    estado: str | None = None,
    tipo_periferico: str | None = None,
) -> list[dict[str, Any]]:
    where: list[str] = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if dependencia_id is not None:
        params.append(dependencia_id)
        where.append(f'dependencia_id = ${len(params)}')
    if punto_atencion_id is not None:
        params.append(punto_atencion_id)
        where.append(f'punto_atencion_id = ${len(params)}')
    if estado is not None:
        params.append(estado)
        where.append(f'estado = ${len(params)}')
    if tipo_periferico is not None:
        params.append(tipo_periferico)
        where.append(f'tipo_periferico = ${len(params)}')
    sql = f"""
        select id, tipo_periferico, nombre, marca, modelo, serial,
               dependencia_id, punto_atencion_id, estado,
               motivo_cambio_estado, configuracion, ultimo_handshake_en,
               fecha_registro, created_at, updated_at
        from gd.periferico
        where {' and '.join(where)}
        order by nombre
    """
    rows = await conn.fetch(sql, *params)
    return [_norm_perif(r) for r in rows]


async def obtener_periferico(
    conn: asyncpg.Connection, *, tenant_id: UUID, periferico_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, tipo_periferico, nombre, marca, modelo, serial,
               dependencia_id, punto_atencion_id, estado,
               motivo_cambio_estado, configuracion, ultimo_handshake_en,
               fecha_registro, created_at, updated_at
        from gd.periferico
        where tenant_id = $1 and id = $2
        """,
        tenant_id, periferico_id,
    )
    return _norm_perif(row) if row else None


async def detalle_periferico(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, periferico_id: UUID,
) -> dict[str, Any] | None:
    base = await obtener_periferico(
        conn, tenant_id=tenant_id, periferico_id=periferico_id,
    )
    if base is None:
        return None
    # Últimas 10 operaciones unificadas (impresiones + digitalizaciones).
    impresiones = await conn.fetch(
        """
        select id, 'impresion' as tipo_operacion, tipo_impresion as subtipo,
               estado, fecha_impresion as fecha, mensaje_error
        from gd.impresion_radicado
        where tenant_id = $1 and periferico_id = $2
        order by fecha_impresion desc
        limit 10
        """,
        tenant_id, periferico_id,
    )
    digit = await conn.fetch(
        """
        select id, 'digitalizacion' as tipo_operacion,
               tipo_digitalizacion as subtipo,
               estado, fecha_digitalizacion as fecha, mensaje_error
        from gd.digitalizacion_documento
        where tenant_id = $1 and periferico_id = $2
        order by fecha_digitalizacion desc
        limit 10
        """,
        tenant_id, periferico_id,
    )
    todas = [dict(r) for r in impresiones] + [dict(r) for r in digit]
    todas.sort(key=lambda x: x['fecha'], reverse=True)
    base['ultimas_operaciones'] = todas[:10]
    return base


async def patch_periferico(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, periferico_id: UUID,
    nombre: str | None, marca: str | None, modelo: str | None,
    dependencia_id: UUID | None, punto_atencion_id: UUID | None,
    configuracion: dict[str, Any] | None,
) -> dict[str, Any] | None:
    sets: list[str] = []
    params: list[Any] = [tenant_id, periferico_id]
    if nombre is not None:
        params.append(nombre)
        sets.append(f'nombre = ${len(params)}')
    if marca is not None:
        params.append(marca)
        sets.append(f'marca = ${len(params)}')
    if modelo is not None:
        params.append(modelo)
        sets.append(f'modelo = ${len(params)}')
    if dependencia_id is not None:
        params.append(dependencia_id)
        sets.append(f'dependencia_id = ${len(params)}')
    if punto_atencion_id is not None:
        params.append(punto_atencion_id)
        sets.append(f'punto_atencion_id = ${len(params)}')
    if configuracion is not None:
        params.append(json.dumps(configuracion))
        sets.append(f'configuracion = ${len(params)}::jsonb')
    if not sets:
        return await obtener_periferico(
            conn, tenant_id=tenant_id, periferico_id=periferico_id,
        )
    sets.append('updated_at = now()')
    row = await conn.fetchrow(
        f"""
        update gd.periferico set {', '.join(sets)}
        where tenant_id = $1 and id = $2
        returning id, tipo_periferico, nombre, marca, modelo, serial,
                  dependencia_id, punto_atencion_id, estado,
                  motivo_cambio_estado, configuracion, ultimo_handshake_en,
                  fecha_registro, created_at, updated_at
        """,
        *params,
    )
    return _norm_perif(row) if row else None


async def cambiar_estado_periferico(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, periferico_id: UUID,
    nuevo_estado: str, motivo: str, forzar: bool = False,
) -> dict[str, Any]:
    """Cambia estado del periférico.

    Si pasa a `inactivo`/`mantenimiento`/`retirado` y hay operaciones
    `encolada` en curso, devuelve 409 a menos que `forzar=True`.
    """
    existente = await obtener_periferico(
        conn, tenant_id=tenant_id, periferico_id=periferico_id,
    )
    if existente is None:
        raise LookupError('periferico_no_existe')

    if nuevo_estado in ('inactivo', 'mantenimiento', 'retirado') and not forzar:
        encoladas = await conn.fetchval(
            """
            select (
              (select count(*) from gd.impresion_radicado
               where tenant_id = $1 and periferico_id = $2
                 and estado = 'encolada')
              +
              (select count(*) from gd.digitalizacion_documento
               where tenant_id = $1 and periferico_id = $2
                 and estado = 'encolada')
            )
            """,
            tenant_id, periferico_id,
        )
        if encoladas and encoladas > 0:
            raise ValueError('periferico_en_uso')

    row = await conn.fetchrow(
        """
        update gd.periferico
        set estado = $3, motivo_cambio_estado = $4, updated_at = now()
        where tenant_id = $1 and id = $2
        returning id, tipo_periferico, nombre, marca, modelo, serial,
                  dependencia_id, punto_atencion_id, estado,
                  motivo_cambio_estado, configuracion, ultimo_handshake_en,
                  fecha_registro, created_at, updated_at
        """,
        tenant_id, periferico_id, nuevo_estado, motivo,
    )
    return _norm_perif(row)


def _norm_perif(row: Any) -> dict[str, Any]:
    if row is None:
        return None  # type: ignore[return-value]
    d = dict(row)
    cfg = d.get('configuracion')
    if isinstance(cfg, str):
        d['configuracion'] = json.loads(cfg) if cfg else {}
    elif cfg is None:
        d['configuracion'] = {}
    return d


# =============================================================================
# Códigos de barras / QR (GD-API-0131)
# =============================================================================

def _token_opaco() -> str:
    """Token urlsafe ~12 chars. Sin datos sensibles — Doc 6 § 14."""
    return secrets.token_urlsafe(9)  # 9 bytes → ~12 chars base64


def _construir_valor_codigo(numero_radicado: str, token: str) -> str:
    """URL pública de verificación + token. NUNCA datos personales."""
    return f'/gd/verificar/{token}'


async def generar_codigo_barras_radicado(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, radicado_id: UUID, tipo_codigo: str,
    generado_por_user_id: UUID,
) -> dict[str, Any]:
    # Validar existencia del radicado.
    rad = await conn.fetchrow(
        """
        select numero_radicado from gd.radicado
        where tenant_id = $1 and id = $2
        """,
        tenant_id, radicado_id,
    )
    if rad is None:
        raise LookupError('radicado_no_existe')

    numero = rad['numero_radicado']
    token = _token_opaco()
    valor = _construir_valor_codigo(numero, token)

    row = await conn.fetchrow(
        """
        insert into gd.codigo_barras_radicado (
            tenant_id, tipo_codigo, radicado_id, valor_codigo, token_opaco,
            generado_por_user_id
        ) values ($1, $2, $3, $4, $5, $6)
        returning id, tipo_codigo, radicado_id, documento_id, expediente_id,
                  valor_codigo, token_opaco, estado, reemplazado_por_id,
                  motivo_anulacion, fecha_generacion, created_at
        """,
        tenant_id, tipo_codigo, radicado_id, valor, token,
        generado_por_user_id,
    )
    return dict(row)


async def obtener_codigo_vigente_radicado(
    conn: asyncpg.Connection, *, tenant_id: UUID, radicado_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, tipo_codigo, radicado_id, documento_id, expediente_id,
               valor_codigo, token_opaco, estado, reemplazado_por_id,
               motivo_anulacion, fecha_generacion, created_at
        from gd.codigo_barras_radicado
        where tenant_id = $1 and radicado_id = $2 and estado = 'activo'
        order by fecha_generacion desc
        limit 1
        """,
        tenant_id, radicado_id,
    )
    return dict(row) if row else None


async def anular_codigo_barras(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, radicado_id: UUID, codigo_id: UUID,
    motivo: str, generar_reemplazo: bool,
    tipo_codigo_reemplazo: str | None,
    user_id: UUID,
) -> dict[str, Any]:
    existente = await conn.fetchrow(
        """
        select id, estado from gd.codigo_barras_radicado
        where tenant_id = $1 and id = $2 and radicado_id = $3
        """,
        tenant_id, codigo_id, radicado_id,
    )
    if existente is None:
        raise LookupError('codigo_no_existe')
    if existente['estado'] != 'activo':
        raise ValueError('codigo_ya_no_activo')

    reemplazo_id: UUID | None = None
    if generar_reemplazo:
        nuevo = await generar_codigo_barras_radicado(
            conn, tenant_id=tenant_id, radicado_id=radicado_id,
            tipo_codigo=tipo_codigo_reemplazo or 'qr',
            generado_por_user_id=user_id,
        )
        reemplazo_id = nuevo['id']

    row = await conn.fetchrow(
        """
        update gd.codigo_barras_radicado
        set estado = case when $3::uuid is not null
                          then 'reemplazado' else 'anulado' end,
            motivo_anulacion = $4,
            reemplazado_por_id = $3
        where tenant_id = $1 and id = $2
        returning id, tipo_codigo, radicado_id, documento_id, expediente_id,
                  valor_codigo, token_opaco, estado, reemplazado_por_id,
                  motivo_anulacion, fecha_generacion, created_at
        """,
        tenant_id, codigo_id, reemplazo_id, motivo,
    )
    return dict(row)


# =============================================================================
# Impresión (GD-API-0132/0133/0134)
# =============================================================================

async def _validar_periferico_activo(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, periferico_id: UUID,
) -> dict[str, Any]:
    perif = await obtener_periferico(
        conn, tenant_id=tenant_id, periferico_id=periferico_id,
    )
    if perif is None:
        raise LookupError('periferico_no_existe')
    if perif['estado'] != 'activo':
        raise ValueError('periferico_no_disponible')
    return perif


async def encolar_impresion(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, periferico_id: UUID, radicado_id: UUID,
    tipo_impresion: str, formato: str | None,
    contenido_impreso: dict[str, Any],
    motivo_reimpresion: str | None,
    impresion_original_id: UUID | None,
    intentos_reimpresion: int,
    usuario_id: UUID,
) -> dict[str, Any]:
    """Inserta impresion_radicado en estado encolada."""
    row = await conn.fetchrow(
        """
        insert into gd.impresion_radicado (
            tenant_id, radicado_id, periferico_id, usuario_id,
            tipo_impresion, formato, contenido_impreso,
            motivo_reimpresion, impresion_original_id,
            intentos_reimpresion, estado
        ) values ($1, $2, $3, $4, $5, $6, $7::jsonb, $8, $9, $10, 'encolada')
        returning id, radicado_id, documento_id, periferico_id, usuario_id,
                  tipo_impresion, formato, estado, mensaje_error, latencia_ms,
                  motivo_reimpresion, intentos_reimpresion,
                  impresion_original_id, archivo_digital_id,
                  contenido_impreso, fecha_impresion, created_at
        """,
        tenant_id, radicado_id, periferico_id, usuario_id,
        tipo_impresion, formato, json.dumps(contenido_impreso or {}),
        motivo_reimpresion, impresion_original_id, intentos_reimpresion,
    )
    return _norm_impresion(row)


async def imprimir_etiqueta(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, periferico_id: UUID, radicado_id: UUID,
    formato: str, incluir_qr: bool, incluir_codigo_barras: bool,
    usuario_id: UUID,
) -> dict[str, Any]:
    await _validar_periferico_activo(
        conn, tenant_id=tenant_id, periferico_id=periferico_id,
    )
    rad = await conn.fetchrow(
        """
        select numero_radicado, estado from gd.radicado
        where tenant_id = $1 and id = $2
        """,
        tenant_id, radicado_id,
    )
    if rad is None:
        raise LookupError('radicado_no_existe')

    tipo = 'etiqueta_qr' if incluir_qr else 'etiqueta_codigo_barras'
    contenido = {
        'numero_radicado': rad['numero_radicado'],
        'incluir_qr': incluir_qr,
        'incluir_codigo_barras': incluir_codigo_barras,
        'anulado': rad['estado'] == 'anulado',  # marca "RADICADO ANULADO"
    }
    return await encolar_impresion(
        conn, tenant_id=tenant_id, periferico_id=periferico_id,
        radicado_id=radicado_id, tipo_impresion=tipo, formato=formato,
        contenido_impreso=contenido,
        motivo_reimpresion=None, impresion_original_id=None,
        intentos_reimpresion=0, usuario_id=usuario_id,
    )


async def reimprimir_etiqueta(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, periferico_id: UUID, radicado_id: UUID,
    motivo: str, impresion_original_id: UUID | None,
    usuario_id: UUID,
) -> dict[str, Any]:
    """RFP-003: requiere motivo (mínimo 10 chars validado en schema) y
    cuenta intentos. Si intentos > 3 retorna error que el handler traduce a
    'requiere aprobación coordinador'.
    """
    await _validar_periferico_activo(
        conn, tenant_id=tenant_id, periferico_id=periferico_id,
    )
    rad = await conn.fetchrow(
        """
        select numero_radicado, estado from gd.radicado
        where tenant_id = $1 and id = $2
        """,
        tenant_id, radicado_id,
    )
    if rad is None:
        raise LookupError('radicado_no_existe')

    # Calcular intentos previos.
    prev = await conn.fetchval(
        """
        select coalesce(max(intentos_reimpresion), 0)
        from gd.impresion_radicado
        where tenant_id = $1 and radicado_id = $2
          and tipo_impresion in ('etiqueta_qr', 'etiqueta_codigo_barras')
        """,
        tenant_id, radicado_id,
    )
    nuevo_intentos = int(prev or 0) + 1
    if nuevo_intentos > 3:
        raise ValueError('requiere_aprobacion_coordinador')

    contenido = {
        'numero_radicado': rad['numero_radicado'],
        'reimpresion': True,
        'motivo': motivo,
    }
    return await encolar_impresion(
        conn, tenant_id=tenant_id, periferico_id=periferico_id,
        radicado_id=radicado_id, tipo_impresion='etiqueta_qr',
        formato='estandar', contenido_impreso=contenido,
        motivo_reimpresion=motivo,
        impresion_original_id=impresion_original_id,
        intentos_reimpresion=nuevo_intentos, usuario_id=usuario_id,
    )


async def imprimir_constancia(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, periferico_id: UUID, radicado_id: UUID,
    formato: str, incluir_qr: bool,
    usuario_id: UUID,
) -> dict[str, Any]:
    """RFP-004: documento institucional formal entregable al ciudadano."""
    await _validar_periferico_activo(
        conn, tenant_id=tenant_id, periferico_id=periferico_id,
    )
    rad = await conn.fetchrow(
        """
        select numero_radicado from gd.radicado
        where tenant_id = $1 and id = $2
        """,
        tenant_id, radicado_id,
    )
    if rad is None:
        raise LookupError('radicado_no_existe')

    contenido = {
        'numero_radicado': rad['numero_radicado'],
        'incluir_qr': incluir_qr,
        'formato': formato,
    }
    return await encolar_impresion(
        conn, tenant_id=tenant_id, periferico_id=periferico_id,
        radicado_id=radicado_id, tipo_impresion='constancia_radicacion',
        formato=formato, contenido_impreso=contenido,
        motivo_reimpresion=None, impresion_original_id=None,
        intentos_reimpresion=0, usuario_id=usuario_id,
    )


async def reportar_resultado_impresion(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, periferico_id: UUID, impresion_id: UUID,
    estado: str, mensaje_error: str | None, latencia_ms: int | None,
) -> dict[str, Any]:
    """Webhook desde agente local. Actualiza estado y latencia."""
    existente = await conn.fetchrow(
        """
        select id, estado from gd.impresion_radicado
        where tenant_id = $1 and id = $2 and periferico_id = $3
        """,
        tenant_id, impresion_id, periferico_id,
    )
    if existente is None:
        raise LookupError('impresion_no_existe')

    if existente['estado'] not in ('encolada',):
        raise ValueError('impresion_no_actualizable')

    row = await conn.fetchrow(
        """
        update gd.impresion_radicado
        set estado = $3, mensaje_error = $4, latencia_ms = $5,
            reportado_en = now(), updated_at = now()
        where tenant_id = $1 and id = $2
        returning id, radicado_id, documento_id, periferico_id, usuario_id,
                  tipo_impresion, formato, estado, mensaje_error, latencia_ms,
                  motivo_reimpresion, intentos_reimpresion,
                  impresion_original_id, archivo_digital_id,
                  contenido_impreso, fecha_impresion, created_at
        """,
        tenant_id, impresion_id, estado, mensaje_error, latencia_ms,
    )
    return _norm_impresion(row)


def _norm_impresion(row: Any) -> dict[str, Any]:
    if row is None:
        return None  # type: ignore[return-value]
    d = dict(row)
    ci = d.get('contenido_impreso')
    if isinstance(ci, str):
        d['contenido_impreso'] = json.loads(ci) if ci else {}
    elif ci is None:
        d['contenido_impreso'] = {}
    return d


# =============================================================================
# Digitalización (GD-API-0135)
# =============================================================================

async def encolar_digitalizacion(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, periferico_id: UUID, radicado_id: UUID,
    tipo_digitalizacion: str, calidad_dpi: int,
    observacion: str | None, usuario_id: UUID,
    lote_id: UUID | None = None,
) -> dict[str, Any]:
    """Encola comando de digitalización individual."""
    await _validar_periferico_activo(
        conn, tenant_id=tenant_id, periferico_id=periferico_id,
    )
    rad = await conn.fetchrow(
        """
        select id, estado from gd.radicado
        where tenant_id = $1 and id = $2
        """,
        tenant_id, radicado_id,
    )
    if rad is None:
        raise LookupError('radicado_no_existe')

    row = await conn.fetchrow(
        """
        insert into gd.digitalizacion_documento (
            tenant_id, radicado_id, periferico_id, usuario_id,
            tipo_digitalizacion, calidad_dpi, observacion, lote_id, estado
        ) values ($1, $2, $3, $4, $5, $6, $7, $8, 'encolada')
        returning id, radicado_id, documento_id, archivo_digital_id,
                  periferico_id, usuario_id, tipo_digitalizacion,
                  numero_paginas, calidad_dpi, estado, mensaje_error,
                  observacion, lote_id, fecha_digitalizacion, created_at
        """,
        tenant_id, radicado_id, periferico_id, usuario_id,
        tipo_digitalizacion, calidad_dpi, observacion, lote_id,
    )
    return dict(row)


async def reportar_resultado_digitalizacion(
    conn: asyncpg.Connection, *,
    tenant_id: UUID, periferico_id: UUID, digitalizacion_id: UUID,
    estado: str, archivo_digital_id: UUID | None,
    numero_paginas: int | None, mensaje_error: str | None,
    observacion: str | None,
) -> dict[str, Any]:
    """Webhook desde agente local. Actualiza con archivo_digital_id si OK."""
    existente = await conn.fetchrow(
        """
        select id, estado from gd.digitalizacion_documento
        where tenant_id = $1 and id = $2 and periferico_id = $3
        """,
        tenant_id, digitalizacion_id, periferico_id,
    )
    if existente is None:
        raise LookupError('digitalizacion_no_existe')
    if existente['estado'] != 'encolada':
        raise ValueError('digitalizacion_no_actualizable')

    row = await conn.fetchrow(
        """
        update gd.digitalizacion_documento
        set estado = $3,
            archivo_digital_id = coalesce($4, archivo_digital_id),
            numero_paginas = coalesce($5, numero_paginas),
            mensaje_error = $6,
            observacion = coalesce($7, observacion),
            updated_at = now()
        where tenant_id = $1 and id = $2
        returning id, radicado_id, documento_id, archivo_digital_id,
                  periferico_id, usuario_id, tipo_digitalizacion,
                  numero_paginas, calidad_dpi, estado, mensaje_error,
                  observacion, lote_id, fecha_digitalizacion, created_at
        """,
        tenant_id, digitalizacion_id, estado, archivo_digital_id,
        numero_paginas, mensaje_error, observacion,
    )
    return dict(row)


__all__ = [
    'ModuloNoActivoError', 'assert_modulo_perifericos_activo',
    # Puntos
    'crear_punto_atencion', 'listar_puntos', 'obtener_punto', 'patch_punto',
    'cambiar_estado_punto', 'listar_perifericos_de_punto',
    # Periféricos
    'crear_periferico', 'listar_perifericos', 'obtener_periferico',
    'detalle_periferico', 'patch_periferico', 'cambiar_estado_periferico',
    # Códigos
    'generar_codigo_barras_radicado', 'obtener_codigo_vigente_radicado',
    'anular_codigo_barras',
    # Impresión
    'imprimir_etiqueta', 'reimprimir_etiqueta', 'imprimir_constancia',
    'encolar_impresion', 'reportar_resultado_impresion',
    # Digitalización
    'encolar_digitalizacion', 'reportar_resultado_digitalizacion',
]
