"""Stateful conversation flow for WhatsApp booking assistant.

Stage progression stored in conversations.metadata['conv_stage'].
Collected booking data stored in conversations.metadata['collected'].
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# ── Stages ────────────────────────────────────────────────────────────────────

STAGE_START = 'start'
STAGE_SERVICE_SELECTION = 'service_selection'
STAGE_AVAILABILITY = 'availability_check'
STAGE_PRICE_NEGOTIATION = 'price_negotiation'
STAGE_DATA_COLLECTION = 'data_collection'
STAGE_CONFIRMATION = 'confirmation'
STAGE_BOOKED = 'booked'

# Stages that need full conversational LLM (not just RAG Q&A)
CONVERSATIONAL_STAGES = {
    STAGE_SERVICE_SELECTION,
    STAGE_AVAILABILITY,
    STAGE_PRICE_NEGOTIATION,
    STAGE_DATA_COLLECTION,
    STAGE_CONFIRMATION,
}

_STAGE_LABELS = {
    STAGE_START: 'Inicio / detección de intención',
    STAGE_SERVICE_SELECTION: 'Selección de servicio',
    STAGE_AVAILABILITY: 'Consulta de disponibilidad y horario',
    STAGE_PRICE_NEGOTIATION: 'Negociación de precio u objeción',
    STAGE_DATA_COLLECTION: 'Recolección de datos del cliente',
    STAGE_CONFIRMATION: 'Confirmación final de la cita',
    STAGE_BOOKED: 'Cita agendada',
}

# Follow-up question per stage when Ollama is unavailable and template answers
_STAGE_FOLLOWUP = {
    STAGE_START: '¿Te gustaría agendar una cita o tienes alguna otra pregunta? 😊',
    STAGE_SERVICE_SELECTION: '¿Cuál de nuestros servicios te interesa?',
    STAGE_AVAILABILITY: '¿Qué día y hora te viene mejor?',
    STAGE_PRICE_NEGOTIATION: '¿Te gustaría que te agendemos con ese precio? 😊',
    STAGE_DATA_COLLECTION: '¿Me puedes dar tu nombre completo y teléfono de contacto?',
    STAGE_CONFIRMATION: '¿Confirmas que deseas agendar la cita?',
    STAGE_BOOKED: '¿Hay algo más en que te pueda ayudar?',
}

_BOOKING_KEYWORDS = {
    'agendar', 'cita', 'reservar', 'turno', 'disponibilidad', 'horario',
    'cuando', 'cuándo', 'quiero', 'necesito', 'solicitar', 'pedir',
    'para cuando', 'me pueden', 'tienen espacio',
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_price_int(value: Any) -> int | None:
    """Parse price that may arrive as int, float, or string like '$35.000 COP'."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r'[^\d]', '', str(value))
    return int(digits) if digits else None


# ── Dataclass ─────────────────────────────────────────────────────────────────

@dataclass
class ConversationContext:
    stage: str = STAGE_START
    collected: dict[str, Any] = field(default_factory=dict)

    @property
    def is_conversational(self) -> bool:
        return self.stage in CONVERSATIONAL_STAGES

    @property
    def booking_complete(self) -> bool:
        c = self.collected
        return bool(c.get('name') and c.get('phone') and c.get('service_name'))

    def collected_summary(self) -> str:
        c = self.collected
        lines = []
        if c.get('service_name'):
            price_val = _safe_price_int(c.get('service_price'))
            price = f" — ${price_val:,} COP" if price_val is not None else ''
            lines.append(f"  Servicio: {c['service_name']}{price}")
        if c.get('preferred_day') or c.get('preferred_time'):
            lines.append(f"  Horario: {c.get('preferred_day', '?')} {c.get('preferred_time', '')}".strip())
        if c.get('name'):
            lines.append(f"  Nombre: {c['name']}")
        if c.get('phone'):
            lines.append(f"  Teléfono: {c['phone']}")
        if c.get('notes'):
            lines.append(f"  Notas: {c['notes']}")
        return '\n'.join(lines) if lines else '  (sin datos aún)'


# ── Factory ───────────────────────────────────────────────────────────────────

def get_context(conv_metadata: Any) -> ConversationContext:
    """Extract ConversationContext from the conversations.metadata jsonb field."""
    if isinstance(conv_metadata, str):
        try:
            conv_metadata = json.loads(conv_metadata)
        except (json.JSONDecodeError, TypeError):
            conv_metadata = {}
    meta = conv_metadata if isinstance(conv_metadata, dict) else {}
    return ConversationContext(
        stage=meta.get('conv_stage', STAGE_START),
        collected=meta.get('collected') or {},
    )


def has_booking_intent(text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in _BOOKING_KEYWORDS)


def stage_followup_prompt(stage: str) -> str:
    """Return a short follow-up question to keep the conversation flowing after a template answer."""
    return _STAGE_FOLLOWUP.get(stage, '')


# ── System prompt ─────────────────────────────────────────────────────────────

_SYSTEM_TEMPLATE = """Eres el asistente virtual de WhatsApp de {business_name}.
Tu misión: guiar al cliente de forma natural y amable desde su primera consulta hasta agendar su cita. Actúas como un asesor cercano, no como un formulario.

== CONTEXTO TEMPORAL ==
Fecha y hora actual en la zona horaria del negocio: {current_datetime_label}
Zona horaria: {timezone}
Usa esta fecha para resolver expresiones como "hoy", "mañana", "el viernes" o "esta semana" sin inventar otra. Si el cliente pide una fecha pasada, indícalo.

== SERVICIOS Y PRECIOS DISPONIBLES ==
{services_context}

== PROFESIONALES / RECURSOS DISPONIBLES ==
{resources_context}

== ESTADO ACTUAL ==
Etapa: {stage_label}
Datos recopilados:
{collected_summary}

== INSTRUCCIONES POR ETAPA ==
• start / service_selection
  Saluda si es el primer mensaje. Detecta qué servicio quiere.
  Presenta 2-3 opciones relevantes con precio y duración. Si ya eligió, mueve a availability_check.

• availability_check
  Pregunta qué día y hora le sirve. Puedes sugerir franjas: "Tenemos martes o jueves en la tarde".
  IMPORTANTE: cuando el cliente diga "hoy", "mañana" o un día de la semana, resuelve la fecha REAL usando el contexto temporal de arriba. No inventes calendarios.
  Si hay más de un profesional disponible para ese servicio, presenta las opciones con su nombre ("¿Prefieres con María o con Carlos?"). Si solo hay uno, agenda directamente con él/ella.
  Cuando el cliente acepta un horario, mueve a data_collection.

• price_negotiation
  Empatiza con la objeción ("Entiendo, el precio puede ser un factor").
  Ofrece alternativas del menú (versión más económica, descuento por agenda inmediata, paquete).
  Si acepta, vuelve a availability_check o data_collection.

• data_collection
  Pide nombre completo y teléfono de contacto si no los tienes aún.
  Si ya los tienes, mueve a confirmation.

• confirmation
  Resume: servicio, día/hora, precio, nombre y teléfono.
  Pide confirmación explícita ("¿Confirmas que deseas agendar?").
  Si confirma → action: create_appointment, next_stage: booked.

• booked
  Confirma que quedó agendada. Recuerda política de cancelación (avisar con 4h de anticipación).
  Ofrece recordatorio para el día anterior.

== MANEJO DE SITUACIONES ESPECIALES ==
- Si el cliente dice "humano", "asesor", "persona" o "reclamo" → action: request_human.
- Si pregunta algo que no está en los servicios disponibles, sé honesto: "No tengo esa información".
- Si el cliente se desanima o deja de responder → ofrece alternativas o cierra sin presionar.
- Si ya conoces nombre y teléfono, NO los vuelvas a pedir.

== REGLAS DE FORMATO ==
1. Máximo 4 líneas por mensaje — WhatsApp es mobile.
2. Usa 1-2 emojis por mensaje, no más.
3. NUNCA inventes precios, horarios ni servicios fuera del contexto.
4. Responde SIEMPRE en JSON válido, sin texto antes ni después.

== FORMATO DE RESPUESTA (JSON estricto) ==
{{
  "message": "texto del mensaje para el cliente (máx 4 líneas)",
  "next_stage": "{valid_stages}",
  "action": null | "create_appointment" | "request_human",
  "collected": {{
    "service_type": null,
    "service_name": null,
    "service_price": null,
    "preferred_day": null,
    "preferred_time": null,
    "name": null,
    "phone": null,
    "notes": null
  }}
}}"""

_VALID_STAGES = ' | '.join([
    STAGE_START, STAGE_SERVICE_SELECTION, STAGE_AVAILABILITY,
    STAGE_PRICE_NEGOTIATION, STAGE_DATA_COLLECTION, STAGE_CONFIRMATION, STAGE_BOOKED,
])


def build_system_prompt(
    ctx: ConversationContext,
    services_context: str,
    business_name: str = 'nuestro negocio',
    *,
    current_datetime_label: str = 'no disponible',
    timezone: str = 'America/Bogota',
    resources_context: str = 'No hay profesionales activos configurados todavía.',
) -> str:
    return _SYSTEM_TEMPLATE.format(
        business_name=business_name,
        services_context=services_context or 'No hay servicios indexados aún.',
        resources_context=resources_context or 'No hay profesionales activos configurados todavía.',
        current_datetime_label=current_datetime_label,
        timezone=timezone,
        stage_label=_STAGE_LABELS.get(ctx.stage, ctx.stage),
        collected_summary=ctx.collected_summary(),
        valid_stages=_VALID_STAGES,
    )


def format_history(messages: list[dict[str, Any]], *, max_turns: int = 8) -> str:
    """Format recent message history as readable thread for LLM context."""
    lines: list[str] = []
    for msg in messages[-max_turns * 2:]:
        direction = msg.get('direction', '')
        body = (msg.get('body_text') or '').strip()
        if not body:
            continue
        actor = 'Cliente' if direction == 'inbound' else 'Bot'
        lines.append(f'{actor}: {body}')
    return '\n'.join(lines)


# ── Response parsing ──────────────────────────────────────────────────────────

_JSON_BLOCK_RE = re.compile(r'```(?:json)?\s*(\{.*?\})\s*```', re.DOTALL)
_JSON_OBJ_RE = re.compile(r'\{[\s\S]*?"message"[\s\S]*?\}')


def parse_llm_response(text: str, current_ctx: ConversationContext) -> dict[str, Any]:
    """Parse LLM JSON response with multiple fallback strategies."""
    raw = text.strip()

    parsed: dict[str, Any] | None = None
    for attempt in (raw, _extract_json_block(raw), _extract_json_object(raw)):
        if not attempt:
            continue
        try:
            parsed = json.loads(attempt)
            break
        except (json.JSONDecodeError, TypeError):
            continue

    if not parsed or not isinstance(parsed, dict):
        # Treat entire response as plain message, keep current stage
        return {
            'message': raw[:600],
            'next_stage': current_ctx.stage,
            'action': None,
            'collected': current_ctx.collected,
        }

    # Merge collected: keep existing values if LLM returns null
    merged_collected = dict(current_ctx.collected)
    llm_collected = parsed.get('collected') or {}
    for key, val in llm_collected.items():
        if val is not None:
            merged_collected[key] = val

    return {
        'message': str(parsed.get('message') or '').strip(),
        'next_stage': parsed.get('next_stage') or current_ctx.stage,
        'action': parsed.get('action'),
        'collected': merged_collected,
    }


def _extract_json_block(text: str) -> str | None:
    m = _JSON_BLOCK_RE.search(text)
    return m.group(1) if m else None


def _extract_json_object(text: str) -> str | None:
    m = _JSON_OBJ_RE.search(text)
    return m.group(0) if m else None

