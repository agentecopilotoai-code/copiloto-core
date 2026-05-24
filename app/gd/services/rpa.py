"""Services para EP-017 RPA + APIs públicas (bloque 18).

Cubre:
- CRUD identidad técnica (con generación + hash de API key)
- CRUD tareas RPA + reclamar con claim_token + reportar resultado
- CRUD webhook subscripciones (secret generation)
- registrar_webhook_delivery (encolar entrega) + helpers retry
- rate_limit_decision (check + increment atómico)
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID, uuid4

import asyncpg


# =============================================================================
# Helpers de credenciales (hash + generación)
# =============================================================================

API_KEY_PREFIX_LEN = 8


def generar_api_key() -> str:
    """Genera API key segura: 'gdat_' + 40 chars URL-safe."""
    return f"gdat_{secrets.token_urlsafe(30)[:40]}"


def hash_api_key(api_key: str) -> str:
    """SHA-256 hex digest. (En producción usar argon2/bcrypt.)"""
    return hashlib.sha256(api_key.encode('utf-8')).hexdigest()


def generar_webhook_secret() -> str:
    """Secret HMAC: 'whsec_' + 50 chars."""
    return f"whsec_{secrets.token_urlsafe(40)[:50]}"


def hash_webhook_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode('utf-8')).hexdigest()


# =============================================================================
# CRUD identidad técnica (GD-API-0105)
# =============================================================================

async def crear_identidad_tecnica(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    codigo: str,
    nombre: str,
    descripcion: str | None,
    tipo: str,
    scopes: list[str],
    rate_limit_rpm: int | None,
    dependencia_alcance_id: UUID | None,
    created_by_user_id: UUID,
) -> tuple[dict[str, Any], str]:
    """Crea identidad + genera API key. Retorna (identidad_dict, api_key_plain).

    La API key NUNCA vuelve a estar disponible en BD — solo en este return.
    """
    api_key = generar_api_key()
    key_hash = hash_api_key(api_key)
    key_prefix = api_key[:API_KEY_PREFIX_LEN]

    try:
        row = await conn.fetchrow(
            """
            insert into gd.identidad_tecnica (
                tenant_id, codigo, nombre, descripcion, tipo,
                api_key_hash, api_key_prefijo, scopes, estado,
                rate_limit_rpm, dependencia_alcance_id, created_by_user_id
            )
            values ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, 'activa',
                    $9, $10, $11)
            returning id, codigo, nombre, descripcion, tipo,
                      api_key_prefijo, scopes, estado, rate_limit_rpm,
                      ultimo_uso_en, total_requests, dependencia_alcance_id,
                      motivo_revocacion, created_by_user_id,
                      created_at, updated_at
            """,
            tenant_id, codigo, nombre, descripcion, tipo,
            key_hash, key_prefix, json.dumps(scopes),
            rate_limit_rpm, dependencia_alcance_id, created_by_user_id,
        )
    except asyncpg.UniqueViolationError as e:
        raise ValueError('codigo_ya_existe') from e

    d = dict(row)
    if isinstance(d.get('scopes'), str):
        d['scopes'] = json.loads(d['scopes'])
    return d, api_key


async def obtener_identidad(
    conn: asyncpg.Connection, *, tenant_id: UUID, identidad_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, codigo, nombre, descripcion, tipo, api_key_prefijo,
               scopes, estado, rate_limit_rpm, ultimo_uso_en, total_requests,
               dependencia_alcance_id, motivo_revocacion, created_by_user_id,
               created_at, updated_at
        from gd.identidad_tecnica where id = $1 and tenant_id = $2
        """,
        identidad_id, tenant_id,
    )
    if row is None:
        return None
    d = dict(row)
    if isinstance(d.get('scopes'), str):
        d['scopes'] = json.loads(d['scopes'])
    return d


async def listar_identidades(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    tipo: str | None = None,
    estado: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if tipo:
        params.append(tipo)
        where.append(f'tipo = ${len(params)}')
    if estado:
        params.append(estado)
        where.append(f'estado = ${len(params)}')
    params.append(limit)
    rows = await conn.fetch(
        f"""
        select id, codigo, nombre, descripcion, tipo, api_key_prefijo,
               scopes, estado, rate_limit_rpm, ultimo_uso_en, total_requests,
               dependencia_alcance_id, motivo_revocacion, created_by_user_id,
               created_at, updated_at
        from gd.identidad_tecnica
        where {' and '.join(where)}
        order by created_at desc
        limit ${len(params)}
        """,
        *params,
    )
    out = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get('scopes'), str):
            d['scopes'] = json.loads(d['scopes'])
        out.append(d)
    return out


async def revocar_identidad(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    identidad_id: UUID,
    motivo: str,
    revocada_por_user_id: UUID,
) -> dict[str, Any] | None:
    estado = await conn.fetchval(
        'select estado from gd.identidad_tecnica '
        'where id = $1 and tenant_id = $2',
        identidad_id, tenant_id,
    )
    if estado is None:
        return None
    if estado == 'revocada':
        raise ValueError('ya_revocada')

    await conn.execute(
        """
        update gd.identidad_tecnica
        set estado = 'revocada',
            motivo_revocacion = $3,
            revocada_por_user_id = $4,
            fecha_revocacion = now()
        where id = $1 and tenant_id = $2
        """,
        identidad_id, tenant_id, motivo, revocada_por_user_id,
    )
    return await obtener_identidad(
        conn, tenant_id=tenant_id, identidad_id=identidad_id,
    )


async def rotar_api_key(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    identidad_id: UUID,
) -> tuple[dict[str, Any], str] | None:
    """Genera nuevo API key, invalida el anterior. Retorna (identidad, key)."""
    estado = await conn.fetchval(
        'select estado from gd.identidad_tecnica '
        'where id = $1 and tenant_id = $2',
        identidad_id, tenant_id,
    )
    if estado is None:
        return None
    if estado != 'activa':
        raise ValueError(f"estado_invalido:{estado}")

    nueva = generar_api_key()
    nuevo_hash = hash_api_key(nueva)
    nuevo_prefix = nueva[:API_KEY_PREFIX_LEN]

    await conn.execute(
        """
        update gd.identidad_tecnica
        set api_key_hash = $3, api_key_prefijo = $4
        where id = $1 and tenant_id = $2
        """,
        identidad_id, tenant_id, nuevo_hash, nuevo_prefix,
    )
    d = await obtener_identidad(
        conn, tenant_id=tenant_id, identidad_id=identidad_id,
    )
    return d, nueva


async def autenticar_por_api_key(
    conn: asyncpg.Connection, *, api_key: str,
) -> dict[str, Any] | None:
    """Resuelve identidad activa por API key. Retorna identidad o None.

    SOLO usa por handlers de RPA — no es público.
    """
    h = hash_api_key(api_key)
    row = await conn.fetchrow(
        """
        select id, tenant_id, codigo, tipo, scopes, estado, rate_limit_rpm,
               dependencia_alcance_id
        from gd.identidad_tecnica
        where api_key_hash = $1 and estado = 'activa'
        """,
        h,
    )
    if row is None:
        return None
    d = dict(row)
    if isinstance(d.get('scopes'), str):
        d['scopes'] = json.loads(d['scopes'])
    # Incrementar uso (best-effort, no fatal si falla).
    await conn.execute(
        """
        update gd.identidad_tecnica
        set ultimo_uso_en = now(), total_requests = total_requests + 1
        where id = $1
        """,
        d['id'],
    )
    return d


# =============================================================================
# Tareas RPA (GD-API-0106)
# =============================================================================

async def crear_tarea_rpa(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    tipo: str,
    payload: dict[str, Any],
    prioridad: str,
    identidad_tecnica_id: UUID | None,
    created_by_user_id: UUID | None,
) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        insert into gd.tarea_rpa (
            tenant_id, identidad_tecnica_id, tipo, payload, prioridad,
            estado, created_by_user_id
        )
        values ($1, $2, $3, $4::jsonb, $5, 'pending', $6)
        returning id, identidad_tecnica_id, tipo, payload, prioridad,
                  estado, resultado, error_texto, error_codigo,
                  claim_token, claim_expira_en, created_by_user_id,
                  started_at, completed_at, created_at
        """,
        tenant_id, identidad_tecnica_id, tipo, json.dumps(payload),
        prioridad, created_by_user_id,
    )
    d = dict(row)
    for k in ('payload', 'resultado'):
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k]) if d[k] else None
    return d


async def reclamar_tarea(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    identidad_tecnica_id: UUID,
    tipo: str | None,
    ttl_segundos: int,
) -> dict[str, Any] | None:
    """Reclama atómicamente la próxima tarea pendiente.

    Filtros:
    - tenant_id, estado='pending'
    - tipo (opcional)
    - identidad_tecnica_id null o == identidad_tecnica_id

    Setea claim_token + claim_expira_en + estado='in_progress'.
    Retorna la tarea reclamada o None si no hay disponibles.
    """
    where = ["tenant_id = $1", "estado = 'pending'",
             "(identidad_tecnica_id is null or identidad_tecnica_id = $2)"]
    params: list[Any] = [tenant_id, identidad_tecnica_id]
    if tipo is not None:
        params.append(tipo)
        where.append(f"tipo = ${len(params)}")
    where_sql = ' and '.join(where)

    token = uuid4()
    expira = datetime.now(timezone.utc) + timedelta(seconds=ttl_segundos)

    row = await conn.fetchrow(
        f"""
        update gd.tarea_rpa
        set estado = 'in_progress',
            claim_token = ${len(params) + 1},
            claim_expira_en = ${len(params) + 2},
            identidad_tecnica_id = coalesce(identidad_tecnica_id, $2),
            started_at = now()
        where id = (
            select id from gd.tarea_rpa
            where {where_sql}
            order by case prioridad
                       when 'urgente' then 0
                       when 'alta' then 1
                       when 'normal' then 2
                       else 3 end,
                     created_at
            limit 1
            for update skip locked
        )
        returning id, identidad_tecnica_id, tipo, payload, prioridad,
                  estado, resultado, error_texto, error_codigo,
                  claim_token, claim_expira_en, created_by_user_id,
                  started_at, completed_at, created_at
        """,
        *params, token, expira,
    )
    if row is None:
        return None
    d = dict(row)
    for k in ('payload', 'resultado'):
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k]) if d[k] else None
    return d


async def reportar_resultado(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    tarea_id: UUID,
    claim_token: UUID,
    estado: str,
    resultado: dict[str, Any] | None,
    error_texto: str | None,
    error_codigo: str | None,
) -> dict[str, Any] | None:
    """Reporta el resultado de una tarea reclamada.

    Valida que claim_token coincida (evita reportes cruzados de tareas
    re-asignadas tras expirar el claim).
    """
    t = await conn.fetchrow(
        """
        select claim_token, claim_expira_en, estado
        from gd.tarea_rpa where id = $1 and tenant_id = $2
        """,
        tarea_id, tenant_id,
    )
    if t is None:
        return None
    if t['estado'] != 'in_progress':
        raise ValueError(f"estado_invalido:{t['estado']}")
    if t['claim_token'] != claim_token:
        raise ValueError('claim_token_invalido')

    row = await conn.fetchrow(
        """
        update gd.tarea_rpa
        set estado = $3,
            resultado = $4::jsonb,
            error_texto = $5,
            error_codigo = $6,
            completed_at = now(),
            claim_token = null,
            claim_expira_en = null
        where id = $1 and tenant_id = $2
        returning id, identidad_tecnica_id, tipo, payload, prioridad,
                  estado, resultado, error_texto, error_codigo,
                  claim_token, claim_expira_en, created_by_user_id,
                  started_at, completed_at, created_at
        """,
        tarea_id, tenant_id, estado,
        json.dumps(resultado) if resultado is not None else None,
        error_texto, error_codigo,
    )
    d = dict(row)
    for k in ('payload', 'resultado'):
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k]) if d[k] else None
    return d


async def listar_tareas_rpa(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    estado: str | None = None,
    tipo: str | None = None,
    identidad_tecnica_id: UUID | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if estado:
        params.append(estado)
        where.append(f'estado = ${len(params)}')
    if tipo:
        params.append(tipo)
        where.append(f'tipo = ${len(params)}')
    if identidad_tecnica_id:
        params.append(identidad_tecnica_id)
        where.append(f'identidad_tecnica_id = ${len(params)}')
    params.append(limit)
    rows = await conn.fetch(
        f"""
        select id, identidad_tecnica_id, tipo, payload, prioridad,
               estado, resultado, error_texto, error_codigo,
               claim_token, claim_expira_en, created_by_user_id,
               started_at, completed_at, created_at
        from gd.tarea_rpa
        where {' and '.join(where)}
        order by created_at desc
        limit ${len(params)}
        """,
        *params,
    )
    out = []
    for r in rows:
        d = dict(r)
        for k in ('payload', 'resultado'):
            if isinstance(d.get(k), str):
                d[k] = json.loads(d[k]) if d[k] else None
        out.append(d)
    return out


# =============================================================================
# Webhooks (GD-API-0108)
# =============================================================================

async def crear_webhook_sub(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    identidad_tecnica_id: UUID,
    url: str,
    eventos_suscritos: list[str],
    descripcion: str | None,
    max_intentos: int,
    backoff_inicial_segundos: int,
    backoff_max_segundos: int,
) -> tuple[dict[str, Any], str]:
    """Crea suscripción + genera secret. Retorna (sub_dict, secret_plain)."""
    # Validar identidad existe + activa.
    estado = await conn.fetchval(
        'select estado from gd.identidad_tecnica '
        'where id = $1 and tenant_id = $2',
        identidad_tecnica_id, tenant_id,
    )
    if estado is None:
        raise LookupError('identidad_no_existe')
    if estado != 'activa':
        raise ValueError(f"identidad_estado:{estado}")

    secret = generar_webhook_secret()
    secret_hash = hash_webhook_secret(secret)

    row = await conn.fetchrow(
        """
        insert into gd.webhook_subscripcion (
            tenant_id, identidad_tecnica_id, url, secret_hash,
            eventos_suscritos, descripcion, estado,
            max_intentos, backoff_inicial_segundos, backoff_max_segundos
        )
        values ($1, $2, $3, $4, $5, $6, 'activa', $7, $8, $9)
        returning id, identidad_tecnica_id, url, eventos_suscritos,
                  descripcion, estado, max_intentos,
                  backoff_inicial_segundos, backoff_max_segundos,
                  total_eventos_entregados, total_eventos_fallidos,
                  ultimo_evento_en, created_at, updated_at
        """,
        tenant_id, identidad_tecnica_id, url, secret_hash,
        eventos_suscritos, descripcion, max_intentos,
        backoff_inicial_segundos, backoff_max_segundos,
    )
    return dict(row), secret


async def listar_webhook_subs(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    identidad_tecnica_id: UUID | None = None,
    estado: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if identidad_tecnica_id:
        params.append(identidad_tecnica_id)
        where.append(f'identidad_tecnica_id = ${len(params)}')
    if estado:
        params.append(estado)
        where.append(f'estado = ${len(params)}')
    params.append(limit)
    rows = await conn.fetch(
        f"""
        select id, identidad_tecnica_id, url, eventos_suscritos,
               descripcion, estado, max_intentos,
               backoff_inicial_segundos, backoff_max_segundos,
               total_eventos_entregados, total_eventos_fallidos,
               ultimo_evento_en, created_at, updated_at
        from gd.webhook_subscripcion
        where {' and '.join(where)}
        order by created_at desc
        limit ${len(params)}
        """,
        *params,
    )
    return [dict(r) for r in rows]


async def patch_webhook_sub(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    sub_id: UUID,
    cambios: dict[str, Any],
) -> dict[str, Any] | None:
    exists = await conn.fetchval(
        'select 1 from gd.webhook_subscripcion '
        'where id = $1 and tenant_id = $2',
        sub_id, tenant_id,
    )
    if not exists:
        return None
    if not cambios:
        return await obtener_webhook_sub(
            conn, tenant_id=tenant_id, sub_id=sub_id,
        )

    sets, params = [], [sub_id, tenant_id]
    for k, v in cambios.items():
        params.append(v)
        sets.append(f'{k} = ${len(params)}')
    await conn.execute(
        f"""
        update gd.webhook_subscripcion set {', '.join(sets)}
        where id = $1 and tenant_id = $2
        """,
        *params,
    )
    return await obtener_webhook_sub(
        conn, tenant_id=tenant_id, sub_id=sub_id,
    )


async def obtener_webhook_sub(
    conn: asyncpg.Connection, *, tenant_id: UUID, sub_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, identidad_tecnica_id, url, eventos_suscritos,
               descripcion, estado, max_intentos,
               backoff_inicial_segundos, backoff_max_segundos,
               total_eventos_entregados, total_eventos_fallidos,
               ultimo_evento_en, created_at, updated_at
        from gd.webhook_subscripcion where id = $1 and tenant_id = $2
        """,
        sub_id, tenant_id,
    )
    return dict(row) if row else None


async def encolar_delivery(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    suscripcion_id: UUID,
    evento_id: UUID,
    tipo_evento: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Crea registro pendiente de entrega. El worker lo procesará."""
    row = await conn.fetchrow(
        """
        insert into gd.webhook_delivery (
            tenant_id, suscripcion_id, evento_id, tipo_evento, payload,
            estado, intentos, next_retry_at
        )
        values ($1, $2, $3, $4, $5::jsonb, 'pending', 0, now())
        returning id, suscripcion_id, evento_id, tipo_evento, estado,
                  intentos, http_status, ultimo_intento_en, next_retry_at,
                  delivered_at, error_texto, created_at
        """,
        tenant_id, suscripcion_id, evento_id, tipo_evento,
        json.dumps(payload),
    )
    return dict(row)


async def listar_deliveries(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    suscripcion_id: UUID | None = None,
    estado: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    where = ['tenant_id = $1']
    params: list[Any] = [tenant_id]
    if suscripcion_id:
        params.append(suscripcion_id)
        where.append(f'suscripcion_id = ${len(params)}')
    if estado:
        params.append(estado)
        where.append(f'estado = ${len(params)}')
    params.append(limit)
    rows = await conn.fetch(
        f"""
        select id, suscripcion_id, evento_id, tipo_evento, estado,
               intentos, http_status, ultimo_intento_en, next_retry_at,
               delivered_at, error_texto, created_at
        from gd.webhook_delivery
        where {' and '.join(where)}
        order by created_at desc
        limit ${len(params)}
        """,
        *params,
    )
    return [dict(r) for r in rows]


def calcular_next_retry(
    *, intento: int, backoff_inicial_segundos: int,
    backoff_max_segundos: int,
) -> datetime:
    """Backoff exponencial con cap."""
    delay = min(
        backoff_inicial_segundos * (2 ** max(0, intento - 1)),
        backoff_max_segundos,
    )
    return datetime.now(timezone.utc) + timedelta(seconds=delay)


# =============================================================================
# Rate limiting (GD-API-0109)
# =============================================================================

def _ventana_minuto_actual() -> datetime:
    """Trunca al minuto la hora actual UTC."""
    now = datetime.now(timezone.utc)
    return now.replace(second=0, microsecond=0)


async def rate_limit_decision(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    identidad_tecnica_id: UUID,
    rate_limit_rpm: int | None,
) -> dict[str, Any]:
    """Verifica + incrementa el contador atómicamente.

    Retorna {permitido, contador_actual, ventana_actual, retry_after_segundos}.
    Si rate_limit_rpm es None → siempre permitido (sin contador).
    """
    if rate_limit_rpm is None:
        return {
            'identidad_tecnica_id': identidad_tecnica_id,
            'rate_limit_rpm': None,
            'ventana_actual': _ventana_minuto_actual(),
            'contador_actual': 0,
            'permitido': True,
            'retry_after_segundos': None,
        }

    ventana = _ventana_minuto_actual()

    # Atomic upsert + increment.
    row = await conn.fetchrow(
        """
        insert into gd.rate_limit_uso (
            tenant_id, identidad_tecnica_id, ventana_minuto, contador
        )
        values ($1, $2, $3, 1)
        on conflict (identidad_tecnica_id, ventana_minuto)
        do update set contador = gd.rate_limit_uso.contador + 1
        returning contador
        """,
        tenant_id, identidad_tecnica_id, ventana,
    )
    contador = int(row['contador'])
    permitido = contador <= rate_limit_rpm

    retry_after = None
    if not permitido:
        # Segundos hasta la siguiente ventana.
        siguiente = ventana + timedelta(minutes=1)
        retry_after = max(1, int((siguiente - datetime.now(timezone.utc)).total_seconds()))

    return {
        'identidad_tecnica_id': identidad_tecnica_id,
        'rate_limit_rpm': rate_limit_rpm,
        'ventana_actual': ventana,
        'contador_actual': contador,
        'permitido': permitido,
        'retry_after_segundos': retry_after,
    }


__all__ = [
    # Helpers
    'generar_api_key', 'hash_api_key',
    'generar_webhook_secret', 'hash_webhook_secret',
    'calcular_next_retry',
    # Identidad técnica
    'crear_identidad_tecnica', 'obtener_identidad', 'listar_identidades',
    'revocar_identidad', 'rotar_api_key', 'autenticar_por_api_key',
    # Tareas RPA
    'crear_tarea_rpa', 'reclamar_tarea', 'reportar_resultado',
    'listar_tareas_rpa',
    # Webhooks
    'crear_webhook_sub', 'listar_webhook_subs', 'obtener_webhook_sub',
    'patch_webhook_sub', 'encolar_delivery', 'listar_deliveries',
    # Rate limit
    'rate_limit_decision',
]
