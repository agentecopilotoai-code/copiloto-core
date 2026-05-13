"""Cloud LLM answer generation via Anthropic (Claude) or OpenAI APIs.

Two modes:
  build_cloud_llm_answer()              — Q&A simple (answer_engine=cloud_llm / cascade tier-3)
  build_conversational_cloud_llm_answer() — Flujo de booking multi-turno con estado

Reutiliza el mismo contrato de retorno que llm_answer.py para drop-in compatibility.
En modo Anthropic, el bloque de contexto RAG se marca con cache_control ephemeral para
reducir costos en preguntas frecuentes contra el mismo conjunto de chunks.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from app.core.config import get_settings
from app.services.circuit_breaker import CircuitOpenError, get_breaker
from app.services.metrics import record_llm_call
from app.services.conversation_flow import (
    ConversationContext,
    build_system_prompt,
    parse_llm_response,
)

if TYPE_CHECKING:
    from app.services.rag_retrieval import RetrievalMatch

log = structlog.get_logger()

_SYSTEM_PROMPT = """Eres un asistente de atención al cliente amable, claro y conciso.
Responde la pregunta del cliente basándote ÚNICAMENTE en el contexto proporcionado.
No inventes información. Si el contexto no contiene la respuesta, responde exactamente:
"No tengo esa información disponible por el momento."
Responde siempre en español, de forma natural y conversacional."""


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


def _extract_token_usage(usage: Any, provider: str) -> dict[str, int]:
    """Normaliza el uso de tokens de Anthropic u OpenAI a un dict uniforme."""
    if provider == 'claude':
        return {
            'input_tokens': getattr(usage, 'input_tokens', 0),
            'output_tokens': getattr(usage, 'output_tokens', 0),
            'cache_creation_tokens': getattr(usage, 'cache_creation_input_tokens', 0),
            'cache_read_tokens': getattr(usage, 'cache_read_input_tokens', 0),
        }
    return {
        'input_tokens': getattr(usage, 'prompt_tokens', 0),
        'output_tokens': getattr(usage, 'completion_tokens', 0),
        'cache_creation_tokens': 0,
        'cache_read_tokens': 0,
    }


async def _call_anthropic(
    *,
    system_text: str,
    context_text: str,
    messages: list[dict[str, str]],
    model: str,
    api_key: str,
    timeout_seconds: int,
    max_tokens: int,
    temperature: float,
) -> tuple[str, dict[str, int]]:
    """Llama a la API de Anthropic con prompt caching en el bloque de contexto RAG."""
    import anthropic  # noqa: PLC0415

    client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout_seconds)

    system_blocks: list[dict[str, Any]] = [{'type': 'text', 'text': system_text}]
    if context_text:
        # El contexto RAG se cachea para ahorrar tokens en preguntas repetidas.
        system_blocks.append({
            'type': 'text',
            'text': context_text,
            'cache_control': {'type': 'ephemeral'},
        })

    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_blocks,
        messages=messages,
    )
    text = response.content[0].text.strip() if response.content else ''
    return text, _extract_token_usage(response.usage, 'claude')


async def _call_openai(
    *,
    system_text: str,
    context_text: str,
    messages: list[dict[str, str]],
    model: str,
    api_key: str,
    timeout_seconds: int,
    max_tokens: int,
    temperature: float,
) -> tuple[str, dict[str, int]]:
    """Llama a la API de OpenAI."""
    from openai import AsyncOpenAI  # noqa: PLC0415

    client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)
    full_system = system_text
    if context_text:
        full_system = f'{system_text}\n\n{context_text}'

    full_messages: list[dict[str, str]] = [
        {'role': 'system', 'content': full_system},
        *messages,
    ]
    response = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=full_messages,
    )
    text = (response.choices[0].message.content or '').strip()
    return text, _extract_token_usage(response.usage, 'openai')


def _breaker_for(provider: str):
    try:
        settings = get_settings()
        threshold = settings.circuit_breaker_failure_threshold
        cooldown = settings.circuit_breaker_cooldown_seconds
    except Exception:  # noqa: BLE001
        threshold, cooldown = 5, 30.0
    return get_breaker(
        f'cloud_llm:{provider}',
        failure_threshold=threshold,
        cooldown_seconds=cooldown,
    )


async def _call_provider(
    *,
    system_text: str,
    context_text: str,
    messages: list[dict[str, str]],
    provider: str,
    model: str,
    api_key: str,
    timeout_seconds: int,
    max_tokens: int,
    temperature: float,
) -> tuple[str, dict[str, int]]:
    if provider == 'claude':
        impl, breaker = _call_anthropic, _breaker_for('claude')
    elif provider == 'openai':
        impl, breaker = _call_openai, _breaker_for('openai')
    else:
        raise ValueError(f'Proveedor cloud LLM desconocido: {provider!r}. Usa "claude" o "openai".')
    try:
        result = await breaker.call(
            impl,
            system_text=system_text,
            context_text=context_text,
            messages=messages,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    except CircuitOpenError:
        record_llm_call(provider=provider, status='rejected')
        raise
    except Exception:
        record_llm_call(provider=provider, status='error')
        raise
    record_llm_call(provider=provider, status='success')
    return result


async def build_cloud_llm_answer(
    question: str,
    matches: list[RetrievalMatch],
    *,
    provider: str,
    model: str,
    api_key: str,
    timeout_seconds: int = 30,
    min_score: float = 0.12,
) -> dict[str, Any]:
    """Llama a un LLM cloud (Claude o OpenAI) para generar respuesta conversacional desde chunks RAG."""
    context = _build_context(matches, min_score=min_score)
    if not context:
        return {
            'status': 'escalate_to_human',
            'sufficient_context': False,
            'answer': None,
            'reason': 'No hay evidencia activa suficiente en la base de conocimiento.',
            'handoff': {'required': True, 'reason': 'knowledge_context_insufficient'},
            'llm_used': True,
            'cloud_llm_used': True,
            'llm_model': model,
            'token_usage': None,
        }

    try:
        answer_text, token_usage = await _call_provider(
            system_text=_SYSTEM_PROMPT,
            context_text=context,
            messages=[{'role': 'user', 'content': f'Pregunta del cliente: {question}'}],
            provider=provider,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_tokens=400,
            temperature=0.2,
        )
    except Exception:
        log.exception('cloud_llm_answer.error', provider=provider, model=model)
        raise

    log.info(
        'cloud_llm_answer.token_usage',
        provider=provider,
        model=model,
        input_tokens=token_usage['input_tokens'],
        output_tokens=token_usage['output_tokens'],
        cache_creation_tokens=token_usage['cache_creation_tokens'],
        cache_read_tokens=token_usage['cache_read_tokens'],
    )

    no_info_signal = 'no tengo esa información' in answer_text.lower()
    if not answer_text or no_info_signal:
        return {
            'status': 'escalate_to_human',
            'sufficient_context': False,
            'answer': None,
            'reason': 'El LLM cloud indicó que no tiene información suficiente.',
            'handoff': {'required': True, 'reason': 'llm_no_information'},
            'llm_used': True,
            'cloud_llm_used': True,
            'llm_model': model,
            'token_usage': token_usage,
        }

    return {
        'status': 'answered',
        'sufficient_context': True,
        'answer': answer_text,
        '_source_document': matches[0].source_uri or matches[0].document_title,
        'reason': f'Respuesta generada por cloud LLM ({provider}/{model}) con chunks activos.',
        'handoff': {'required': False, 'reason': None},
        'llm_used': True,
        'cloud_llm_used': True,
        'llm_model': model,
        'token_usage': token_usage,
    }


async def build_conversational_cloud_llm_answer(
    question: str,
    matches: list[RetrievalMatch],
    *,
    ctx: ConversationContext,
    history: str,
    provider: str,
    model: str,
    api_key: str,
    timeout_seconds: int = 30,
    min_score: float = 0.12,
    business_name: str = 'nuestro negocio',
    current_datetime_label: str = 'no disponible',
    timezone: str = 'America/Bogota',
    resources_context: str = 'No hay profesionales activos configurados todavía.',
    bot_personality: Any = None,
) -> dict[str, Any]:
    """Flujo de booking multi-turno vía LLM cloud (Claude o OpenAI)."""
    services_context = _build_context(matches, min_score=min_score)
    # build_system_prompt embeds context internally; se pasa como system_text completo
    # para que Anthropic lo cachee como bloque único (estable por stage).
    system = build_system_prompt(
        ctx,
        services_context,
        business_name=business_name,
        current_datetime_label=current_datetime_label,
        timezone=timezone,
        resources_context=resources_context,
        bot_personality=bot_personality,
    )

    messages: list[dict[str, str]] = []
    if history:
        messages.append({'role': 'user', 'content': f'== HISTORIAL ==\n{history}'})
        messages.append({'role': 'assistant', 'content': 'Entendido, continúo.'})
    messages.append({'role': 'user', 'content': question})

    try:
        raw_text, token_usage = await _call_provider(
            system_text=system,
            context_text='',  # ya incluido en system via build_system_prompt
            messages=messages,
            provider=provider,
            model=model,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            max_tokens=500,
            temperature=0.3,
        )
    except Exception:
        log.exception('cloud_llm_conv.error', provider=provider, model=model)
        raise

    log.info(
        'cloud_llm_conv.token_usage',
        provider=provider,
        model=model,
        input_tokens=token_usage['input_tokens'],
        output_tokens=token_usage['output_tokens'],
        cache_creation_tokens=token_usage['cache_creation_tokens'],
        cache_read_tokens=token_usage['cache_read_tokens'],
    )

    parsed = parse_llm_response(raw_text, ctx)
    action = parsed.get('action')
    message_text = parsed.get('message', '')

    if action == 'request_human' or not message_text:
        return {
            'status': 'escalate_to_human',
            'sufficient_context': False,
            'answer': message_text or None,
            'reason': 'LLM cloud solicitó transferencia a agente humano.',
            'handoff': {'required': True, 'reason': 'user_requested_human'},
            'next_stage': parsed.get('next_stage', ctx.stage),
            'action': action,
            'collected': parsed.get('collected', ctx.collected),
            'llm_used': True,
            'cloud_llm_used': True,
            'llm_model': model,
            'token_usage': token_usage,
        }

    return {
        'status': 'answered',
        'sufficient_context': True,
        'answer': message_text,
        'reason': f'Respuesta conversacional generada por cloud LLM ({provider}/{model}).',
        'handoff': {'required': False, 'reason': None},
        'next_stage': parsed.get('next_stage', ctx.stage),
        'action': action,
        'collected': parsed.get('collected', ctx.collected),
        'llm_used': True,
        'cloud_llm_used': True,
        'llm_model': model,
        'token_usage': token_usage,
    }
