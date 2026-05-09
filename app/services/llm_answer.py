"""Local LLM answer generation via Ollama (answer_engine=local_llm)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import structlog

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
        raise
    except httpx.HTTPStatusError as exc:
        log.warning('llm_answer.http_error', status=exc.response.status_code, model=model)
        raise
    except Exception:
        log.exception('llm_answer.error', model=model)
        raise

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

    best = matches[0]
    source_label = best.source_uri or best.document_title
    full_answer = f'{answer_text}\n\n_(Fuente: {source_label})_'

    return {
        'status': 'answered',
        'sufficient_context': True,
        'answer': full_answer,
        'reason': 'Respuesta generada por LLM local con chunks activos como contexto.',
        'handoff': {'required': False, 'reason': None},
        'llm_used': True,
        'llm_model': model,
    }
