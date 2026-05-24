"""Services SQL para EP-013 agentes IA asistidos (bloque 14).

MANDATO RNF-029/RNF-030:
- La IA SOLO sugiere. Toda materialización requiere endpoint humano separado.
- Toda solicitud + resultado + decisión es trazable (append-only).
- Datos sensibles se minimizan antes de enviar al proveedor.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

import asyncpg


# =============================================================================
# Redactor PII (GD-API-0086, RNF-029, RNF-017)
# =============================================================================

# Cédulas colombianas: 7-10 dígitos (con o sin puntos/espacios).
# Para máxima cobertura: precedida por keyword (cédula/CC/NIT/TI/CE/NUIP/RC)
# y hasta 30 chars no-dígito entre keyword y los dígitos
# (ej. "Mi cédula es 79.123.456").
_RE_CEDULA = re.compile(
    r'\b(?:c(?:[ée]dula)?|cc|ti|ce|nit|nuip|rc)\b'
    r'(?:[^\d\n]{0,30})(\d[\d\.]{5,14}\d)',
    re.IGNORECASE,
)
# Tarjeta de crédito (Luhn no requerido — minimizer agresivo).
_RE_TARJETA = re.compile(r'\b\d{13,19}\b')
# Teléfonos colombianos: 7 dígitos fijos, 10 móviles (con o sin prefijo +57).
_RE_TELEFONO = re.compile(
    r'(?:\+?57[\s\.-]?)?(?:\(?\d{1,3}\)?[\s\.-]?)?\d{3}[\s\.-]?\d{4}\b',
)
# Email — patrón estándar.
_RE_EMAIL = re.compile(
    r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
)


def redactar_datos_sensibles(
    texto: str | None,
) -> tuple[str | None, list[dict[str, Any]]]:
    """Reemplaza PII por placeholders y retorna metadatos de redacciones.

    Orden de aplicación (importa para precedencia):
    1. Cédula (con keyword) → [CEDULA_REDACTADA]
    2. Email → [EMAIL_REDACTADO]
    3. Teléfono → [TELEFONO_REDACTADO]
    4. Tarjeta crédito → [TARJETA_REDACTADA]

    Retorna (texto_redactado, redacciones_aplicadas) donde
    redacciones_aplicadas es lista de {tipo, cantidad, placeholder}.
    """
    if not texto:
        return texto, []

    redacciones = []
    out = texto

    # 1. Cédula (precedencia: antes que teléfono porque 10 dígitos podría ser ambos).
    cedulas = _RE_CEDULA.findall(out)
    if cedulas:
        out = _RE_CEDULA.sub('[CEDULA_REDACTADA]', out)
        redacciones.append({
            'tipo': 'cedula', 'cantidad': len(cedulas),
            'placeholder': '[CEDULA_REDACTADA]',
        })

    # 2. Email.
    emails = _RE_EMAIL.findall(out)
    if emails:
        out = _RE_EMAIL.sub('[EMAIL_REDACTADO]', out)
        redacciones.append({
            'tipo': 'email', 'cantidad': len(emails),
            'placeholder': '[EMAIL_REDACTADO]',
        })

    # 3. Teléfono (después de cédula).
    telefonos = _RE_TELEFONO.findall(out)
    if telefonos:
        out = _RE_TELEFONO.sub('[TELEFONO_REDACTADO]', out)
        redacciones.append({
            'tipo': 'telefono', 'cantidad': len(telefonos),
            'placeholder': '[TELEFONO_REDACTADO]',
        })

    # 4. Tarjeta crédito (después de teléfono).
    tarjetas = _RE_TARJETA.findall(out)
    if tarjetas:
        out = _RE_TARJETA.sub('[TARJETA_REDACTADA]', out)
        redacciones.append({
            'tipo': 'tarjeta', 'cantidad': len(tarjetas),
            'placeholder': '[TARJETA_REDACTADA]',
        })

    return out, redacciones


def redactar_payload(
    payload: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Aplica redacción recursiva a strings en el payload (jsonb).

    Retorna (payload_redactado, redacciones_consolidadas).
    """
    redacciones_total: dict[str, int] = {}

    def _walk(obj):
        if isinstance(obj, str):
            redacted, redacciones = redactar_datos_sensibles(obj)
            for r in redacciones:
                redacciones_total[r['tipo']] = (
                    redacciones_total.get(r['tipo'], 0) + r['cantidad']
                )
            return redacted
        if isinstance(obj, dict):
            return {k: _walk(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_walk(x) for x in obj]
        return obj

    redacted_payload = _walk(payload)
    consolidated = [
        {'tipo': k, 'cantidad': v, 'placeholder': f'[{k.upper()}_REDACTADO]'}
        for k, v in redacciones_total.items()
    ]
    return redacted_payload, consolidated


# =============================================================================
# Provider stub (GD-API-0077)
# =============================================================================

class IIAProvider(ABC):
    """Interface para proveedores IA (Claude, GPT-4, stub local).

    Cada método retorna {contenido: dict, confianza: float, explicacion: str,
    modelo: str, tokens_input: int, tokens_output: int, timing_ms: int}.
    """

    @abstractmethod
    async def clasificar(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    async def extraer_datos(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    async def resumir(
        self, *, payload: dict[str, Any], max_caracteres: int = 500,
    ) -> dict[str, Any]:
        ...

    @abstractmethod
    async def sugerir_dependencia(
        self, *, payload: dict[str, Any],
    ) -> dict[str, Any]:
        ...

    @abstractmethod
    async def detectar_duplicados(
        self, *, payload: dict[str, Any], top_k: int = 5,
    ) -> dict[str, Any]:
        ...

    @abstractmethod
    async def borrador_respuesta(
        self, *, payload: dict[str, Any],
    ) -> dict[str, Any]:
        ...

    @abstractmethod
    async def sugerir_termino(
        self, *, payload: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class StubIAProvider(IIAProvider):
    """Stub determinista. Reglas heurísticas simples sobre el texto."""

    NOMBRE = 'stub-v1'

    async def clasificar(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        t = (payload.get('texto') or payload.get('asunto') or '').lower()
        if any(k in t for k in ('queja', 'reclamo', 'petición', 'peticion',
                                  'pqrsd', 'derecho de petición')):
            tipo = 'pqrsd'
            conf = 0.85
        elif any(k in t for k in ('oficio', 'memorando', 'comunicación',
                                    'correspondencia')):
            tipo = 'correspondencia_externa'
            conf = 0.75
        else:
            tipo = 'tramite'
            conf = 0.55
        return {
            'contenido': {'tipo_clasificacion_sugerido': tipo,
                           'razones': [f"keyword detectada en '{t[:50]}'"]},
            'confianza': conf,
            'explicacion': "Heurística stub: keywords del texto.",
            'modelo': self.NOMBRE,
            'tokens_input': len(t.split()), 'tokens_output': 8,
            'timing_ms': 5,
        }

    async def extraer_datos(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        t = payload.get('texto', '')
        emails = _RE_EMAIL.findall(t) or []
        cedulas = _RE_CEDULA.findall(t) or []
        return {
            'contenido': {
                'emails_detectados': emails[:3],
                'cedulas_detectadas': cedulas[:3],
                'fechas_detectadas': [],
            },
            'confianza': 0.7,
            'explicacion': 'Stub extrae via regex simple.',
            'modelo': self.NOMBRE,
            'tokens_input': len(t.split()), 'tokens_output': 12,
            'timing_ms': 4,
        }

    async def resumir(self, *, payload, max_caracteres=500) -> dict[str, Any]:
        t = payload.get('texto', '')
        resumen = (t[:max_caracteres] + '...') if len(t) > max_caracteres else t
        return {
            'contenido': {'resumen': resumen},
            'confianza': 0.6,
            'explicacion': 'Stub: trunca primer N caracteres.',
            'modelo': self.NOMBRE,
            'tokens_input': len(t.split()), 'tokens_output': len(resumen.split()),
            'timing_ms': 3,
        }

    async def sugerir_dependencia(self, *, payload) -> dict[str, Any]:
        dep_id = payload.get('dependencia_hint')
        return {
            'contenido': {
                'dependencia_sugerida_id': dep_id,
                'alternativas': [],
            },
            'confianza': 0.5 if dep_id else 0.3,
            'explicacion': 'Stub: usa hint si fue provisto, baja confianza.',
            'modelo': self.NOMBRE,
            'tokens_input': 0, 'tokens_output': 4, 'timing_ms': 2,
        }

    async def detectar_duplicados(self, *, payload, top_k=5) -> dict[str, Any]:
        candidatos = payload.get('candidatos_recientes', [])[:top_k]
        return {
            'contenido': {
                'duplicados': [
                    {'entidad_id': c.get('id'), 'similitud': 0.0}
                    for c in candidatos
                ],
            },
            'confianza': 0.4,
            'explicacion': 'Stub: similitud 0 (sin embeddings reales).',
            'modelo': self.NOMBRE,
            'tokens_input': len(candidatos), 'tokens_output': len(candidatos) * 2,
            'timing_ms': 6,
        }

    async def borrador_respuesta(self, *, payload) -> dict[str, Any]:
        asunto = payload.get('asunto', 'su solicitud')
        return {
            'contenido': {
                'borrador_texto': (
                    f"Estimado(a) solicitante,\n\n"
                    f"En atención a {asunto}, le informamos que su "
                    f"requerimiento está en proceso de revisión.\n\n"
                    f"Atentamente,\n[Nombre del funcionario]"
                ),
            },
            'confianza': 0.55,
            'explicacion': 'Stub: plantilla genérica.',
            'modelo': self.NOMBRE,
            'tokens_input': 10, 'tokens_output': 35, 'timing_ms': 8,
        }

    async def sugerir_termino(self, *, payload) -> dict[str, Any]:
        tipo = payload.get('tipo_pqrsd_codigo', '').lower()
        # Sugerencia simple: peticiones = 15 dias, quejas = 15 dias, etc.
        dias = 15
        if 'consulta' in tipo:
            dias = 30
        elif 'reclamo' in tipo:
            dias = 15
        return {
            'contenido': {'dias_sugeridos': dias},
            'confianza': 0.5,
            'explicacion': f'Stub: heurística por keyword tipo={tipo}.',
            'modelo': self.NOMBRE,
            'tokens_input': 5, 'tokens_output': 1, 'timing_ms': 1,
        }


_default_provider: IIAProvider = StubIAProvider()


def get_default_provider() -> IIAProvider:
    return _default_provider


# =============================================================================
# CRUD solicitud + ejecución
# =============================================================================

# Map tipo_asistencia → método del provider
_METHOD_MAP = {
    'clasificacion': 'clasificar',
    'extraccion': 'extraer_datos',
    'resumen': 'resumir',
    'sugerencia_dependencia': 'sugerir_dependencia',
    'deteccion_duplicados': 'detectar_duplicados',
    'borrador_respuesta': 'borrador_respuesta',
    'sugerencia_termino': 'sugerir_termino',
}


async def encolar_solicitud(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    tipo_asistencia: str,
    entidad_origen_tipo: str,
    entidad_origen_id: UUID,
    payload_original: dict[str, Any],
    solicitante_user_id: UUID,
) -> dict[str, Any]:
    """Crea solicitud_ia con datos_redactados aplicando minimizador."""
    payload_red, redacciones = redactar_payload(payload_original)

    row = await conn.fetchrow(
        """
        insert into gd.solicitud_ia (
            tenant_id, tipo_asistencia, entidad_origen_tipo, entidad_origen_id,
            estado, payload_original, datos_redactados, redacciones_aplicadas,
            proveedor, solicitante_user_id
        )
        values ($1, $2, $3, $4, 'pending', $5::jsonb, $6::jsonb, $7::jsonb,
                $8, $9)
        returning id, tipo_asistencia, entidad_origen_tipo, entidad_origen_id,
                  estado, payload_original, datos_redactados,
                  redacciones_aplicadas, proveedor, error_texto, error_codigo,
                  solicitante_user_id, inicio_procesamiento_en,
                  fin_procesamiento_en, created_at
        """,
        tenant_id, tipo_asistencia, entidad_origen_tipo, entidad_origen_id,
        json.dumps(payload_original), json.dumps(payload_red),
        json.dumps(redacciones),
        get_default_provider().__class__.__name__,
        solicitante_user_id,
    )
    d = dict(row)
    for k in ('payload_original', 'datos_redactados', 'redacciones_aplicadas'):
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])
    return d


async def ejecutar_solicitud(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    solicitud_id: UUID,
    extra_kwargs: dict[str, Any] | None = None,
    provider: IIAProvider | None = None,
) -> dict[str, Any] | None:
    """Ejecuta la solicitud llamando al provider y guarda resultado.

    Worker síncrono in-process: en producción esto va a Celery/RQ.
    Retorna {solicitud, resultado}.
    """
    sol = await conn.fetchrow(
        """
        select tipo_asistencia, estado, datos_redactados
        from gd.solicitud_ia where id = $1 and tenant_id = $2
        """,
        solicitud_id, tenant_id,
    )
    if sol is None:
        return None
    if sol['estado'] not in ('pending', 'failed'):
        raise ValueError(f"estado_invalido:{sol['estado']}")

    # Marcar processing.
    await conn.execute(
        """
        update gd.solicitud_ia
        set estado = 'processing', inicio_procesamiento_en = now()
        where id = $1 and tenant_id = $2
        """,
        solicitud_id, tenant_id,
    )

    pv = provider or get_default_provider()
    method_name = _METHOD_MAP[sol['tipo_asistencia']]
    method = getattr(pv, method_name)

    datos = sol['datos_redactados']
    if isinstance(datos, str):
        datos = json.loads(datos)

    extra = extra_kwargs or {}
    # Nota: el provider devuelve `timing_ms` directamente; no necesitamos medirlo
    # con `time.monotonic()` aquí.
    try:
        result = await method(payload=datos, **extra)
        # Persistir resultado.
        res_row = await conn.fetchrow(
            """
            insert into gd.resultado_ia (
                tenant_id, solicitud_id, contenido, confianza, explicacion,
                modelo, tokens_input, tokens_output, timing_ms
            )
            values ($1, $2, $3::jsonb, $4, $5, $6, $7, $8, $9)
            returning id, solicitud_id, contenido, confianza, explicacion,
                      modelo, tokens_input, tokens_output, timing_ms, created_at
            """,
            tenant_id, solicitud_id, json.dumps(result['contenido']),
            result.get('confianza'), result.get('explicacion'),
            result.get('modelo'),
            result.get('tokens_input'), result.get('tokens_output'),
            result.get('timing_ms'),
        )

        await conn.execute(
            """
            update gd.solicitud_ia
            set estado = 'completed',
                fin_procesamiento_en = now()
            where id = $1 and tenant_id = $2
            """,
            solicitud_id, tenant_id,
        )

        d_res = dict(res_row)
        if isinstance(d_res['contenido'], str):
            d_res['contenido'] = json.loads(d_res['contenido'])
        return {'resultado': d_res}
    except Exception as e:
        # Marcar failed.
        await conn.execute(
            """
            update gd.solicitud_ia
            set estado = 'failed',
                error_texto = $3,
                error_codigo = $4,
                fin_procesamiento_en = now()
            where id = $1 and tenant_id = $2
            """,
            solicitud_id, tenant_id, str(e)[:1000],
            type(e).__name__,
        )
        return {'resultado': None, 'error': str(e)}


async def obtener_solicitud(
    conn: asyncpg.Connection, *, tenant_id: UUID, solicitud_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, tipo_asistencia, entidad_origen_tipo, entidad_origen_id,
               estado, payload_original, datos_redactados,
               redacciones_aplicadas, proveedor, error_texto, error_codigo,
               solicitante_user_id, inicio_procesamiento_en,
               fin_procesamiento_en, created_at
        from gd.solicitud_ia where id = $1 and tenant_id = $2
        """,
        solicitud_id, tenant_id,
    )
    if row is None:
        return None
    d = dict(row)
    for k in ('payload_original', 'datos_redactados', 'redacciones_aplicadas'):
        if isinstance(d.get(k), str):
            d[k] = json.loads(d[k])
    return d


async def obtener_resultado(
    conn: asyncpg.Connection, *, tenant_id: UUID, resultado_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, solicitud_id, contenido, confianza, explicacion,
               modelo, tokens_input, tokens_output, timing_ms, created_at
        from gd.resultado_ia where id = $1 and tenant_id = $2
        """,
        resultado_id, tenant_id,
    )
    if row is None:
        return None
    d = dict(row)
    if isinstance(d['contenido'], str):
        d['contenido'] = json.loads(d['contenido'])
    return d


# =============================================================================
# Decisión humana (GD-API-0084)
# =============================================================================

async def decidir_sugerencia(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    resultado_id: UUID,
    decision: str,
    contenido_modificado: dict[str, Any] | None,
    observaciones: str | None,
    decided_by_user_id: UUID,
) -> dict[str, Any] | None:
    """Registra decisión humana. Una sola decisión por resultado (unique)."""
    # Verificar que resultado existe.
    res = await conn.fetchval(
        'select 1 from gd.resultado_ia where id = $1 and tenant_id = $2',
        resultado_id, tenant_id,
    )
    if not res:
        return None

    try:
        row = await conn.fetchrow(
            """
            insert into gd.decision_ia (
                tenant_id, resultado_id, decision, contenido_modificado,
                observaciones, decided_by_user_id
            )
            values ($1, $2, $3, $4::jsonb, $5, $6)
            returning id, resultado_id, decision, contenido_modificado,
                      observaciones, decided_by_user_id, decided_at,
                      materializado_endpoint, materializado_entidad_id
            """,
            tenant_id, resultado_id, decision,
            json.dumps(contenido_modificado) if contenido_modificado else None,
            observaciones, decided_by_user_id,
        )
    except asyncpg.UniqueViolationError as e:
        raise ValueError('decision_ya_registrada') from e

    d = dict(row)
    if isinstance(d.get('contenido_modificado'), str):
        d['contenido_modificado'] = json.loads(d['contenido_modificado'])
    return d


# =============================================================================
# Trazabilidad (GD-API-0085, RNF-030)
# =============================================================================

async def obtener_trazabilidad(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    entidad_origen_tipo: str,
    entidad_origen_id: UUID,
) -> list[dict[str, Any]]:
    """Retorna lista de {solicitud, resultado?, decision?} para una entidad."""
    sols = await conn.fetch(
        """
        select id, tipo_asistencia, entidad_origen_tipo, entidad_origen_id,
               estado, payload_original, datos_redactados,
               redacciones_aplicadas, proveedor, error_texto, error_codigo,
               solicitante_user_id, inicio_procesamiento_en,
               fin_procesamiento_en, created_at
        from gd.solicitud_ia
        where tenant_id = $1
          and entidad_origen_tipo = $2
          and entidad_origen_id = $3
        order by created_at desc
        """,
        tenant_id, entidad_origen_tipo, entidad_origen_id,
    )

    out = []
    for s_row in sols:
        s = dict(s_row)
        for k in ('payload_original', 'datos_redactados', 'redacciones_aplicadas'):
            if isinstance(s.get(k), str):
                s[k] = json.loads(s[k])

        # Buscar último resultado (puede haber 0 o 1).
        res_row = await conn.fetchrow(
            """
            select id, solicitud_id, contenido, confianza, explicacion,
                   modelo, tokens_input, tokens_output, timing_ms, created_at
            from gd.resultado_ia
            where solicitud_id = $1 and tenant_id = $2
            order by created_at desc
            limit 1
            """,
            s['id'], tenant_id,
        )
        resultado = None
        decision = None
        if res_row:
            resultado = dict(res_row)
            if isinstance(resultado['contenido'], str):
                resultado['contenido'] = json.loads(resultado['contenido'])
            # Decisión asociada (puede no existir).
            dec_row = await conn.fetchrow(
                """
                select id, resultado_id, decision, contenido_modificado,
                       observaciones, decided_by_user_id, decided_at,
                       materializado_endpoint, materializado_entidad_id
                from gd.decision_ia
                where resultado_id = $1 and tenant_id = $2
                """,
                resultado['id'], tenant_id,
            )
            if dec_row:
                decision = dict(dec_row)
                if isinstance(decision.get('contenido_modificado'), str):
                    decision['contenido_modificado'] = json.loads(
                        decision['contenido_modificado'],
                    )

        out.append({'solicitud': s, 'resultado': resultado, 'decision': decision})
    return out


__all__ = [
    # Redactor
    'redactar_datos_sensibles', 'redactar_payload',
    # Provider
    'IIAProvider', 'StubIAProvider', 'get_default_provider',
    # Workflow
    'encolar_solicitud', 'ejecutar_solicitud',
    'obtener_solicitud', 'obtener_resultado',
    # Decisión + trazabilidad
    'decidir_sugerencia', 'obtener_trazabilidad',
]
