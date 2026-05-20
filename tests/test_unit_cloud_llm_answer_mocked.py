"""Mock-based tests for `app/chatbot/cloud_llm_answer.py`.

Mocks the `anthropic.AsyncAnthropic` and `openai.AsyncOpenAI` clients so we
can drive both providers without API keys. Currently 26% covered; this
suite pushes it to ~85%.
"""
from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from typing import Any

import pytest


class _FakeMatch:
    def __init__(self, *, text='Servicio X cuesta 50000', score=0.9, doc_title='Doc', visibility='public', source_uri='kb://doc', section_path=None, chunk_id='c1'):
        self.chunk_text = text
        self.score = score
        self.document_title = doc_title
        self.visibility = visibility
        self.source_uri = source_uri
        self.section_path = section_path
        self.id = chunk_id


# ────────── Anthropic mock ─────────────────────────────────────────────────


def _install_anthropic_mock(monkeypatch, *, content='Te ayudo', input_tokens=120, raise_exc=None):
    """Insert a fake `anthropic` module with `AsyncAnthropic` returning the
    text we want."""
    class _Usage:
        def __init__(self):
            self.input_tokens = input_tokens
            self.output_tokens = 30
            self.cache_creation_input_tokens = 0
            self.cache_read_input_tokens = 0

    class _Block:
        def __init__(self, text):
            self.text = text

    class _Resp:
        def __init__(self, text):
            self.content = [_Block(text)]
            self.usage = _Usage()

    class _Messages:
        async def create(self, **kwargs):
            if raise_exc:
                raise raise_exc
            return _Resp(content)

    class _AsyncAnthropic:
        def __init__(self, **kw):
            self.messages = _Messages()

    fake_mod = SimpleNamespace(AsyncAnthropic=_AsyncAnthropic)
    monkeypatch.setitem(sys.modules, 'anthropic', fake_mod)


# ────────── OpenAI mock ─────────────────────────────────────────────────────


def _install_openai_mock(monkeypatch, *, content='Te ayudo', raise_exc=None):
    class _Usage:
        prompt_tokens = 80
        completion_tokens = 20

    class _Choice:
        def __init__(self, text):
            self.message = SimpleNamespace(content=text)

    class _Resp:
        def __init__(self, text):
            self.choices = [_Choice(text)]
            self.usage = _Usage()

    class _Completions:
        async def create(self, **kwargs):
            if raise_exc:
                raise raise_exc
            return _Resp(content)

    class _Chat:
        completions = _Completions()

    class _AsyncOpenAI:
        def __init__(self, **kw):
            self.chat = _Chat()

    fake_mod = SimpleNamespace(AsyncOpenAI=_AsyncOpenAI)
    monkeypatch.setitem(sys.modules, 'openai', fake_mod)


# ────────── build_cloud_llm_answer ─────────────────────────────────────────


def test_build_cloud_llm_answer_with_anthropic_returns_answer(monkeypatch):
    from app.services.circuit_breaker import reset_registry
    from app.chatbot.cloud_llm_answer import build_cloud_llm_answer

    reset_registry()
    _install_anthropic_mock(monkeypatch, content='Respuesta cloud Claude')
    matches = [_FakeMatch(score=0.9)]
    result = asyncio.run(build_cloud_llm_answer(
        question='cuanto cuesta?',
        matches=matches,
        provider='claude',
        model='claude-sonnet-4-6',
        api_key='fake-key',
        min_score=0.0,
    ))
    assert result['status'] == 'answered'
    assert 'Respuesta cloud Claude' in result['answer']
    assert result['cloud_llm_used'] is True
    assert result['token_usage']['input_tokens'] == 120
    reset_registry()


def test_build_cloud_llm_answer_with_openai_returns_answer(monkeypatch):
    from app.services.circuit_breaker import reset_registry
    from app.chatbot.cloud_llm_answer import build_cloud_llm_answer

    reset_registry()
    _install_openai_mock(monkeypatch, content='Respuesta de OpenAI')
    matches = [_FakeMatch(score=0.9)]
    result = asyncio.run(build_cloud_llm_answer(
        question='cuanto cuesta?',
        matches=matches,
        provider='openai',
        model='gpt-4',
        api_key='fake-key',
        min_score=0.0,
    ))
    assert result['status'] == 'answered'
    assert 'Respuesta de OpenAI' in result['answer']
    assert result['token_usage']['input_tokens'] == 80
    reset_registry()


def test_build_cloud_llm_answer_returns_handoff_when_no_context():
    from app.services.circuit_breaker import reset_registry
    from app.chatbot.cloud_llm_answer import build_cloud_llm_answer

    reset_registry()
    result = asyncio.run(build_cloud_llm_answer(
        question='x',
        matches=[],
        provider='claude',
        model='claude',
        api_key='k',
        min_score=0.0,
    ))
    assert result['status'] == 'escalate_to_human'
    assert result['handoff']['required'] is True
    reset_registry()


def test_build_cloud_llm_answer_returns_handoff_when_no_information(monkeypatch):
    from app.services.circuit_breaker import reset_registry
    from app.chatbot.cloud_llm_answer import build_cloud_llm_answer

    reset_registry()
    _install_anthropic_mock(
        monkeypatch,
        content='No tengo esa información disponible por el momento.',
    )
    matches = [_FakeMatch(score=0.9)]
    result = asyncio.run(build_cloud_llm_answer(
        question='?',
        matches=matches,
        provider='claude',
        model='claude',
        api_key='k',
        min_score=0.0,
    ))
    assert result['status'] == 'escalate_to_human'
    assert result['handoff']['reason'] == 'llm_no_information'
    reset_registry()


def test_build_cloud_llm_answer_unknown_provider_raises():
    from app.services.circuit_breaker import reset_registry
    from app.chatbot.cloud_llm_answer import build_cloud_llm_answer

    reset_registry()
    matches = [_FakeMatch(score=0.9)]
    with pytest.raises(ValueError, match='Proveedor cloud LLM desconocido'):
        asyncio.run(build_cloud_llm_answer(
            question='x',
            matches=matches,
            provider='cohere',  # unknown
            model='c',
            api_key='k',
            min_score=0.0,
        ))
    reset_registry()


def test_build_cloud_llm_answer_circuit_open_after_threshold(monkeypatch):
    from app.services.circuit_breaker import CircuitOpenError, reset_registry
    from app.chatbot.cloud_llm_answer import build_cloud_llm_answer

    reset_registry()
    _install_anthropic_mock(monkeypatch, raise_exc=RuntimeError('upstream blew up'))
    matches = [_FakeMatch(score=0.9)]
    for _ in range(5):
        with pytest.raises(RuntimeError):
            asyncio.run(build_cloud_llm_answer(
                question='x',
                matches=matches,
                provider='claude',
                model='c',
                api_key='k',
                min_score=0.0,
            ))
    with pytest.raises(CircuitOpenError):
        asyncio.run(build_cloud_llm_answer(
            question='x',
            matches=matches,
            provider='claude',
            model='c',
            api_key='k',
            min_score=0.0,
        ))
    reset_registry()


# ────────── build_conversational_cloud_llm_answer ──────────────────────────


def _real_ctx():
    from app.services.conversation_flow import ConversationContext
    return ConversationContext(stage='collecting', collected={})


def test_build_conversational_cloud_llm_answer_with_anthropic(monkeypatch):
    from app.services.circuit_breaker import reset_registry
    from app.chatbot.cloud_llm_answer import build_conversational_cloud_llm_answer

    reset_registry()
    payload_text = (
        '{"message": "te ayudo con la cita", "next_stage": "collecting", "action": "continue"}'
    )
    _install_anthropic_mock(monkeypatch, content=payload_text)
    matches = [_FakeMatch(score=0.9)]
    result = asyncio.run(build_conversational_cloud_llm_answer(
        question='quiero agendar',
        matches=matches,
        ctx=_real_ctx(),
        history='',
        provider='claude',
        model='claude',
        api_key='k',
        min_score=0.0,
    ))
    assert result['cloud_llm_used'] is True
    assert result['status'] in ('answered', 'escalate_to_human')
    reset_registry()


def test_build_conversational_cloud_llm_answer_escalates_on_request_human(monkeypatch):
    from app.services.circuit_breaker import reset_registry
    from app.chatbot.cloud_llm_answer import build_conversational_cloud_llm_answer

    reset_registry()
    payload_text = (
        '{"message": "te conecto con un agente", "next_stage": "collecting", "action": "request_human"}'
    )
    _install_anthropic_mock(monkeypatch, content=payload_text)
    matches = [_FakeMatch(score=0.9)]
    result = asyncio.run(build_conversational_cloud_llm_answer(
        question='necesito humano',
        matches=matches,
        ctx=_real_ctx(),
        history='',
        provider='claude',
        model='claude',
        api_key='k',
        min_score=0.0,
    ))
    assert result['status'] == 'escalate_to_human'
    assert result['handoff']['required'] is True
    reset_registry()


def test_build_conversational_cloud_llm_answer_uses_history(monkeypatch):
    from app.services.circuit_breaker import reset_registry
    from app.chatbot.cloud_llm_answer import build_conversational_cloud_llm_answer

    reset_registry()
    captured: dict[str, Any] = {}

    class _Block:
        def __init__(self, text):
            self.text = text

    class _Resp:
        def __init__(self, text):
            self.content = [_Block(text)]
            self.usage = SimpleNamespace(
                input_tokens=10, output_tokens=5,
                cache_creation_input_tokens=0, cache_read_input_tokens=0,
            )

    class _Messages:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return _Resp('{"message": "x", "next_stage": "collecting", "action": "continue"}')

    class _AsyncAnthropic:
        def __init__(self, **kw): self.messages = _Messages()

    monkeypatch.setitem(sys.modules, 'anthropic', SimpleNamespace(AsyncAnthropic=_AsyncAnthropic))

    matches = [_FakeMatch(score=0.9)]
    asyncio.run(build_conversational_cloud_llm_answer(
        question='hola',
        matches=matches,
        ctx=_real_ctx(),
        history='Usuario: pregunta previa',
        provider='claude',
        model='claude',
        api_key='k',
        min_score=0.0,
    ))
    msgs = captured.get('messages') or []
    history_present = any('HISTORIAL' in (m.get('content') or '') for m in msgs)
    assert history_present
    reset_registry()


def test_build_conversational_cloud_llm_answer_with_openai(monkeypatch):
    from app.services.circuit_breaker import reset_registry
    from app.chatbot.cloud_llm_answer import build_conversational_cloud_llm_answer

    reset_registry()
    payload_text = (
        '{"message": "respuesta openai", "next_stage": "collecting", "action": "continue"}'
    )
    _install_openai_mock(monkeypatch, content=payload_text)
    matches = [_FakeMatch(score=0.9)]
    result = asyncio.run(build_conversational_cloud_llm_answer(
        question='x',
        matches=matches,
        ctx=_real_ctx(),
        history='',
        provider='openai',
        model='gpt-4',
        api_key='k',
        min_score=0.0,
    ))
    assert result['cloud_llm_used'] is True
    reset_registry()
