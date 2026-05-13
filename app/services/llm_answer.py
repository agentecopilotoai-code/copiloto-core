"""Local LLM answer generation via Ollama.

Two modes:
  build_llm_answer()              — Q&A simple (answer_engine=local_llm / cascade tier-2)
  build_conversational_llm_answer() — Flujo de booking multi-turno con estado
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import structlog

from app.services.conversation_flow import (
    ConversationContext,
    build_system_prompt,
    parse_llm_response,
)
from app.services.metrics import record_llm_call

if TYPE_CHECKING:
    from app.services.rag_retrieval import RetrievalMatch

log = structlog.get_logger()

_SYSTEM_PROMPT = """Eres un asistente de atención al cliente amable, claro y conciso.
Responde la pregunta del cliente basándote ÚNICAMENTE en el contexto proporcionado.
No inventes información. Si el contexto no contiene la respuesta, responde exactamente:
"No tengo esa información disponible por el momento."
Responde siempre en español, de forma natural y conversacional."""

_USER_TEMPLATE = """Contexto de conocimiento:
{context}

Pregunta del cliente: {question}

Respuesta:"""


def _build_context(matches: list[RetrievalMatch], *, min_score: float) -> str:
    parts = []
    for m in matches:
        if m.score < min_score:
            continue
        header = f'[{m.document_title}]'
        if m.section_path:
            header += f' › {m.section_path}'
        parts.append(f'{header}\n{m.chunk_text}')
    return '\n\n'.join(parts)


async def build_llm_answer(
    question: str,
    matches: list[RetrievalMatch],
    *,
    base_url: str,
    model: str,
    timeout_seconds: int = 30,
    min_score: float = 0.12,
) -> dict[str, Any]:
    """Call a local Ollama instance to generate a conversational answer from retrieved chunks."""
    context = _build_context(matches, min_score=min_score)
    if not context:
        return {
            'status': 'escalate_to_human',
            'sufficient_context': False,
            'answer': None,
            'reason': 'No hay evidencia activa suficiente en la base de conocimiento.',
            'handoff': {'required': True, 'reason': 'knowledge_context_insufficient'},
            'llm_used': True,
            'llm_model': model,
        }

    user_message = _USER_TEMPLATE.format(context=context, question=question)

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                f'{base_url.rstrip("/")}/api/chat',
                json={
                    'model': model,
                    'stream': False,
                    'options': {'temperature': 0.2, 'num_predict': 400},
                    'messages': [
                        {'role': 'system', 'content': _SYSTEM_PROMPT},
                        {'role': 'user', 'content': user_message},
                    ],
                },
            )
            response.raise_for_status()
            data = response.json()
            answer_text: str = data.get('message', {}).get('content', '').strip()
    except httpx.TimeoutException:
        log.warning('llm_answer.timeout', model=model, base_url=base_url)
        record_llm_call(provider='local_llm', status='timeout')
        raise
    except httpx.HTTPStatusError as exc:
        log.warning('llm_answer.http_error', status=exc.response.status_code, model=model)
        record_llm_call(provider='local_llm', status='error')
        raise
    except Exception:
        log.exception('llm_answer.error', model=model)
        record_llm_call(provider='local_llm', status='error')
        raise

    record_llm_call(provider='local_llm', status='success')
    no_info_signal = 'no tengo esa información' in answer_text.lower()
    if not answer_text or no_info_signal:
        return {
            'status': 'escalate_to_human',
            'sufficient_context': False,
            'answer': None,
            'reason': 'El LLM indicó que no tiene información suficiente.',
            'handoff': {'required': True, 'reason': 'llm_no_information'},
            'llm_used': True,
            'llm_model': model,
        }

    return {
        'status': 'answered',
        'sufficient_context': True,
        'answer': answer_text,
        '_source_document': matches[0].source_uri or matches[0].document_title,
        'reason': 'Respuesta generada por LLM local con chunks activos como contexto.',
        'handoff': {'required': False, 'reason': None},
        'llm_used': True,
        'llm_model': model,
    }


async def build_conversational_llm_answer(
    question: str,
    matches: list[RetrievalMatch],
    *,
    ctx: ConversationContext,
    history: str,
    base_url: str,
    model: str,
    timeout_seconds: int = 30,
    min_score: float = 0.12,
    business_name: str = 'nuestro negocio',
    current_datetime_label: str = 'no disponible',
    timezone: str = 'America/Bogota',
    resources_context: str = 'No hay profesionales activos configurados todavía.',
) -> dict[str, Any]:
    """Multi-turn booking flow response via Ollama.

    Returns the standard orchestrator decision dict, extended with:
      next_stage, action, collected — for the orchestrator to persist in DB.
    """
    services_context = _build_context(matches, min_score=min_score)
    system = build_system_prompt(
        ctx,
        services_context,
        business_name=business_name,
        current_datetime_label=current_datetime_label,
        timezone=timezone,
        resources_context=resources_context,
    )

    messages_payload: list[dict[str, str]] = [
        {'role': 'system', 'content': system},
    ]
    if history:
        messages_payload.append({'role': 'user', 'content': f'== HISTORIAL ==\n{history}'})
        messages_payload.append({'role': 'assistant', 'content': 'Entendido, continúo.'})
    messages_payload.append({'role': 'user', 'content': question})

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                f'{base_url.rstrip("/")}/api/chat',
                json={
                    'model': model,
                    'stream': False,
                    'options': {'temperature': 0.3, 'num_predict': 500},
                    'messages': messages_payload,
                },
            )
            response.raise_for_status()
            data = response.json()
            raw_text: str = data.get('message', {}).get('content', '').strip()
    except httpx.TimeoutException:
        log.warning('llm_conv.timeout', model=model, base_url=base_url)
        record_llm_call(provider='local_llm', status='timeout')
        raise
    except httpx.HTTPStatusError as exc:
        log.warning('llm_conv.http_error', status=exc.response.status_code, model=model)
        record_llm_call(provider='local_llm', status='error')
        raise
    except Exception:
        log.exception('llm_conv.error', model=model)
        record_llm_call(provider='local_llm', status='error')
        raise

    record_llm_call(provider='local_llm', status='success')
    parsed = parse_llm_response(raw_text, ctx)
    action = parsed.get('action')
    message_text = parsed.get('message', '')

    if action == 'request_human' or not message_text:
        return {
            'status': 'escalate_to_human',
            'sufficient_context': False,
            'answer': message_text or None,
            'reason': 'LLM solicitó transferencia a agente humano.',
            'handoff': {'required': True, 'reason': 'user_requested_human'},
            'next_stage': parsed.get('next_stage', ctx.stage),
            'action': action,
            'collected': parsed.get('collected', ctx.collected),
            'llm_used': True,
            'llm_model': model,
        }

    return {
        'status': 'answered',
        'sufficient_context': True,
        'answer': message_text,
        'reason': 'Respuesta conversacional generada por LLM local.',
        'handoff': {'required': False, 'reason': None},
        'next_stage': parsed.get('next_stage', ctx.stage),
        'action': action,
        'collected': parsed.get('collected', ctx.collected),
        'llm_used': True,
        'llm_model': model,
    }
