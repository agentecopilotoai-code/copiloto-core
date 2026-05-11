"""Clasificador de intenciones genérico orientado al journey de agendamiento.

Tres capas en cascada:
  1. rule-router — keywords/regex configurables por tenant, O(1), confianza alta.
  2. intent-llm  — LLM ligero cuando confianza < CONF_LLM_THRESHOLD (0.78).
  3. fallback    — si confianza sigue < CONF_FALLBACK_THRESHOLD (0.70) devuelve
                   faq como neutral seguro. Solo fuerza complaint_or_risk si el LLM
                   detectó queja explícita o la capa-1 detectó riesgo con conf >= 0.85.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import structlog

log = structlog.get_logger()

# ── Catálogo de intenciones ───────────────────────────────────────────────────

INTENT_GREETING = 'greeting'
INTENT_FAQ = 'faq'
INTENT_BOOK_APPOINTMENT = 'book_appointment'
INTENT_CONFIRM_APPOINTMENT = 'confirm_appointment'
INTENT_RESCHEDULE_APPOINTMENT = 'reschedule_appointment'
INTENT_CANCEL_APPOINTMENT = 'cancel_appointment'
INTENT_CHECK_AVAILABILITY = 'check_availability'
INTENT_COMPLAINT_OR_RISK = 'complaint_or_risk'
INTENT_OUT_OF_SCOPE = 'out_of_scope'
INTENT_OPT_OUT = 'opt_out'

ALL_INTENTS = [
    INTENT_GREETING,
    INTENT_FAQ,
    INTENT_BOOK_APPOINTMENT,
    INTENT_CONFIRM_APPOINTMENT,
    INTENT_RESCHEDULE_APPOINTMENT,
    INTENT_CANCEL_APPOINTMENT,
    INTENT_CHECK_AVAILABILITY,
    INTENT_COMPLAINT_OR_RISK,
    INTENT_OUT_OF_SCOPE,
    INTENT_OPT_OUT,
]

CONF_LLM_THRESHOLD = 0.78
CONF_FALLBACK_THRESHOLD = 0.70

# ── Keywords globales por defecto ─────────────────────────────────────────────
# Cada entrada: (patrón regex, intención, confianza)

_BASE_RULES: list[tuple[str, str, float]] = [
    # opt_out — máxima prioridad
    (r'\b(stop|baja|cancelar\s+suscripci[oó]n|no\s+me\s+env[íi]es|no\s+quiero\s+recibir|d[ae]s?suscrib)\b', INTENT_OPT_OUT, 0.95),

    # complaint_or_risk
    (r'\b(estafa|fraude|robo|amenaza|v[io]olaci[oó]n|abuso|acoso|mentira|enga[ñn]o|ridículo|p[ée]simo|horrible|muy\s+mal|muy\s+enojad[oa]|harto|hart[oa]|indignado|qué\s+porquería|qu[eé]\s+asco)\b', INTENT_COMPLAINT_OR_RISK, 0.95),
    (r'\b(queja|reclamo|reclamaci[oó]n|insatisf|protestar|exigir|demanda|denuncia)\b', INTENT_COMPLAINT_OR_RISK, 0.90),

    # greeting
    (r'^(hola|buenas|buenos\s+d[íi]as|buenas\s+tardes|buenas\s+noches|hi|hey|good\s+morning|hello|saludos|qu[eé]\s+tal|c[oó]mo\s+est[aá]s|buen\s+d[íi]a)[,!.?\s]*$', INTENT_GREETING, 0.92),

    # opt_out alternativo (cola)
    (r'\b(no\s+contactar|remover\s+lista|eliminar\s+cuenta)\b', INTENT_OPT_OUT, 0.88),

    # cancel_appointment
    (r'\b(cancelar\s+cita|anular\s+cita|cancel[ao]?\s+mi\s+reserva|quiero\s+cancelar|necesito\s+cancelar)\b', INTENT_CANCEL_APPOINTMENT, 0.93),
    (r'\b(cancelar|anular|dar\s+de\s+baja)\b.*\b(cita|reserva|turno|appointment)\b', INTENT_CANCEL_APPOINTMENT, 0.88),

    # reschedule_appointment
    (r'\b(cambiar\s+cita|mover\s+cita|reagendar|reprogramar|reschedule|cambiar\s+mi\s+turno|cambiar\s+horario)\b', INTENT_RESCHEDULE_APPOINTMENT, 0.93),
    (r'\b(cambiar|mover|posterg|adelantar)\b.*\b(cita|turno|reserva|appointment)\b', INTENT_RESCHEDULE_APPOINTMENT, 0.87),

    # confirm_appointment
    (r'\b(confirmar?\s+(?:mi\s+)?cita|confirmo\s+mi\s+cita|mi\s+cita\s+es|tengo\s+cita|consultar?\s+mi\s+cita|ver\s+mi\s+reserva|cu[aá]ndo\s+es\s+mi\s+cita)\b', INTENT_CONFIRM_APPOINTMENT, 0.90),

    # check_availability
    (r'\b(disponibilidad|horarios?\s+disponibles?|qu[eé]\s+d[íi]as?\s+tienen|est[aá]n\s+disponibles?|tienen\s+espacio|hay\s+lugar|hay\s+cupo|cu[aá]ndo\s+tienen)\b', INTENT_CHECK_AVAILABILITY, 0.88),

    # book_appointment
    (r'\b(agendar|reservar|pedir\s+cita|solicitar\s+cita|quiero\s+una\s+cita|quiero\s+un\s+turno|necesito\s+una\s+cita|hacer\s+una\s+cita|programar\s+cita|hacer\s+un\s+turno)\b', INTENT_BOOK_APPOINTMENT, 0.93),
    (r'\b(quiero|necesito|me\s+gustar[íi]a)\b.{0,30}\b(cita|turno|reserva|appointment)\b', INTENT_BOOK_APPOINTMENT, 0.83),

    # faq — amplio, baja prioridad en la lista (reglas anteriores más específicas ganan)
    (r'\b(cu[aá]nto\s+cuesta|precio|tarifas?|qu[eé]\s+incluye|horario[s]?\s+de\s+atenci[oó]n|d[oó]nde\s+est[aá]n|direcci[oó]n|c[oó]mo\s+funciona|qu[eé]\s+servicios?|tienen\s+[a-záéíóú]+)\b', INTENT_FAQ, 0.82),
]

_COMPILED: list[tuple[re.Pattern[str], str, float]] = [
    (re.compile(pat, re.IGNORECASE | re.UNICODE), intent, conf)
    for pat, intent, conf in _BASE_RULES
]


def _compile_tenant_rules(extra_keywords: dict[str, list[str]]) -> list[tuple[re.Pattern[str], str, float]]:
    """Compila las keywords personalizadas del tenant en reglas regex simples."""
    rules: list[tuple[re.Pattern[str], str, float]] = []
    for intent, keywords in extra_keywords.items():
        if intent not in ALL_INTENTS or not keywords:
            continue
        for kw in keywords:
            kw = kw.strip()
            if not kw:
                continue
            pattern = re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE | re.UNICODE)
            rules.append((pattern, intent, 0.85))
    return rules


@dataclass
class IntentResult:
    intent: str
    confidence: float
    resolved_by: str  # 'rule' | 'llm' | 'fallback'
    layer_detail: str = ''


# ── Capa 1: rule-router ───────────────────────────────────────────────────────

def _rule_classify(
    text: str,
    enabled_intents: set[str],
    tenant_rules: list[tuple[re.Pattern[str], str, float]],
) -> IntentResult | None:
    """Devuelve la primera coincidencia con confianza >= CONF_LLM_THRESHOLD, o None."""
    best: tuple[float, str, str] | None = None  # (conf, intent, pattern_str)

    for pat, intent, conf in (tenant_rules + _COMPILED):
        if intent not in enabled_intents:
            continue
        if pat.search(text):
            if best is None or conf > best[0]:
                best = (conf, intent, pat.pattern[:60])

    if best is None:
        return None

    conf, intent, detail = best
    return IntentResult(intent=intent, confidence=conf, resolved_by='rule', layer_detail=detail)


# ── Capa 2: LLM ──────────────────────────────────────────────────────────────

_LLM_SYSTEM = """\
Eres un clasificador de intenciones para un asistente de atención al cliente.
Dado el mensaje del usuario, devuelve ÚNICAMENTE el nombre de la intención más probable.
No incluyas explicación ni texto adicional. Solo responde con UNO de estos valores exactos:

greeting
faq
book_appointment
confirm_appointment
reschedule_appointment
cancel_appointment
check_availability
complaint_or_risk
out_of_scope
opt_out"""


async def _llm_classify(text: str, enabled_intents: set[str], settings: Any) -> IntentResult | None:
    """Llama al LLM de la cascada y devuelve una IntentResult o None si falla."""
    provider = getattr(settings, 'cloud_llm_provider', None)
    api_key = getattr(settings, 'cloud_llm_api_key', None)
    model = getattr(settings, 'cloud_llm_model', 'claude-sonnet-4-6')

    intent_raw: str | None = None

    if provider and api_key:
        try:
            if provider == 'claude':
                import anthropic  # type: ignore[import]
                client = anthropic.Anthropic(api_key=api_key)
                msg = client.messages.create(
                    model=model,
                    max_tokens=20,
                    system=_LLM_SYSTEM,
                    messages=[{'role': 'user', 'content': text}],
                )
                intent_raw = msg.content[0].text.strip().lower()
            elif provider == 'openai':
                import openai  # type: ignore[import]
                client = openai.OpenAI(api_key=api_key)
                resp = client.chat.completions.create(
                    model=model,
                    max_tokens=20,
                    messages=[
                        {'role': 'system', 'content': _LLM_SYSTEM},
                        {'role': 'user', 'content': text},
                    ],
                )
                intent_raw = resp.choices[0].message.content.strip().lower()
        except Exception as exc:
            log.warning('intent_classifier.llm_error', provider=provider, error=str(exc))
            return None
    else:
        # Intentar con Ollama local
        ollama_url = getattr(settings, 'local_llm_base_url', None) or 'http://host.docker.internal:11434'
        ollama_model = getattr(settings, 'local_llm_model', None) or 'llama3.2:3b'
        try:
            import httpx
            payload = {
                'model': ollama_model,
                'messages': [
                    {'role': 'system', 'content': _LLM_SYSTEM},
                    {'role': 'user', 'content': text},
                ],
                'stream': False,
            }
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.post(f'{ollama_url}/api/chat', json=payload)
                data = resp.json()
                intent_raw = (data.get('message') or {}).get('content', '').strip().lower()
        except Exception as exc:
            log.warning('intent_classifier.ollama_error', error=str(exc))
            return None

    if intent_raw and intent_raw in ALL_INTENTS and intent_raw in enabled_intents:
        return IntentResult(
            intent=intent_raw,
            confidence=0.75,
            resolved_by='llm',
            layer_detail=f'provider={provider or "ollama"}',
        )
    return None


# ── Clasificador principal ────────────────────────────────────────────────────

async def classify_intent(
    text: str,
    *,
    settings: Any,
    tenant_config: dict[str, Any] | None = None,
) -> IntentResult:
    """Clasifica la intención del mensaje en 3 capas.

    tenant_config puede incluir:
      - enabled_intents: list[str]  — intenciones activas (default: todas)
      - custom_keywords: dict[str, list[str]]  — keywords adicionales por intención
      - min_confidence: float  — umbral mínimo de confianza para fallback (default 0.70)
    """
    cfg = tenant_config or {}
    enabled_set = set(cfg.get('enabled_intents') or ALL_INTENTS) & set(ALL_INTENTS)
    if not enabled_set:
        enabled_set = set(ALL_INTENTS)

    min_conf: float = float(cfg.get('min_confidence') or CONF_FALLBACK_THRESHOLD)
    tenant_rules = _compile_tenant_rules(cfg.get('custom_keywords') or {})

    # Capa 1 — reglas
    result = _rule_classify(text, enabled_set, tenant_rules)

    if result and result.confidence >= CONF_LLM_THRESHOLD:
        log.info('intent_classifier.resolved_rule', intent=result.intent, confidence=result.confidence)
        return result

    # Detectar frustración/queja explícita incluso si la confianza es baja
    complaint_result = _rule_classify(text, {INTENT_COMPLAINT_OR_RISK}, tenant_rules)
    if complaint_result and complaint_result.confidence >= 0.85:
        log.info('intent_classifier.forced_complaint', confidence=complaint_result.confidence)
        return IntentResult(
            intent=INTENT_COMPLAINT_OR_RISK,
            confidence=complaint_result.confidence,
            resolved_by='rule',
            layer_detail='high_confidence_complaint',
        )

    # Capa 2 — LLM
    llm_result = await _llm_classify(text, enabled_set, settings)
    if llm_result and llm_result.confidence >= min_conf:
        log.info('intent_classifier.resolved_llm', intent=llm_result.intent, confidence=llm_result.confidence)
        # Si la capa 1 tenía algo con menor confianza, combinar
        if result:
            return llm_result
        return llm_result

    # Capa 3 — fallback
    # Si la capa 1 ya tenía un resultado que supera el umbral mínimo, usarlo
    if result and result.confidence >= min_conf:
        log.info('intent_classifier.resolved_rule_min', intent=result.intent, confidence=result.confidence)
        return IntentResult(
            intent=result.intent,
            confidence=result.confidence,
            resolved_by='rule',
            layer_detail=result.layer_detail,
        )

    # Solo forzar handoff si el LLM explícitamente detectó queja/riesgo
    if llm_result and llm_result.intent == INTENT_COMPLAINT_OR_RISK:
        log.info('intent_classifier.fallback', forced_intent=INTENT_COMPLAINT_OR_RISK, reason='llm_complaint_low_conf')
        return IntentResult(
            intent=INTENT_COMPLAINT_OR_RISK,
            confidence=llm_result.confidence,
            resolved_by='fallback',
            layer_detail='llm_complaint_below_threshold',
        )

    # Sin evidencia de queja: devolver faq como neutral seguro (no dispara handoff)
    log.info('intent_classifier.fallback', forced_intent=INTENT_FAQ, reason='no_rule_no_llm')
    return IntentResult(
        intent=INTENT_FAQ,
        confidence=0.50,
        resolved_by='fallback',
        layer_detail='no_rule_match_llm_unavailable',
    )
