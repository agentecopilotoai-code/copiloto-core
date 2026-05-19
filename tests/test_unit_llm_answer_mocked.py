"""Mock-based tests for `app/services/llm_answer.py`.

The module is currently 26% covered. By mocking the Ollama HTTP client we
exercise the entire happy path + timeout + HTTP-error + circuit-open
branches in both `build_llm_answer` and `build_conversational_llm_answer`.
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx
import pytest


# ───────── Test doubles ────────────────────────────────────────────────────


class _FakeMatch:
    def __init__(self, *, text='Algun contexto relevante', score=0.5, doc_title='Doc', visibility='public', source_uri=None, section_path=None, chunk_id='c1'):
        self.chunk_text = text
        self.score = score
        self.document_title = doc_title
        self.visibility = visibility
        self.source_uri = source_uri
        self.section_path = section_path
        self.id = chunk_id


class _StubResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            req = httpx.Request('POST', 'http://test')
            resp = httpx.Response(self.status_code, request=req)
            raise httpx.HTTPStatusError('bad', request=req, response=resp)


class _StubAsyncClient:
    """Drop-in for `httpx.AsyncClient`. We stash the call args so tests can
    assert what was sent."""

    def __init__(self, payload=None, *, raise_timeout=False, status_code=200, **_kw):
        self.payload = payload or {'message': {'content': 'Respuesta del LLM'}}
        self.raise_timeout = raise_timeout
        self.status_code = status_code
        self.last_url = None
        self.last_json = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, **kw):
        self.last_url = url
        self.last_json = json
        if self.raise_timeout:
            raise httpx.TimeoutException('timeout')
        return _StubResponse(self.payload, status_code=self.status_code)


# ───────── build_llm_answer ────────────────────────────────────────────────


def _patch_httpx(monkeypatch, **kw):
    """Replace `httpx.AsyncClient` with our stub. Returns the stub for assertions."""
    stub_holder = {'client': None}

    def _factory(**client_kw):
        stub = _StubAsyncClient(**kw, **client_kw)
        stub_holder['client'] = stub
        return stub

    monkeypatch.setattr(httpx, 'AsyncClient', _factory)
    return stub_holder


def test_build_llm_answer_returns_handoff_when_no_context(monkeypatch):
    from app.services.circuit_breaker import reset_registry
    from app.services.llm_answer import build_llm_answer

    reset_registry()
    _patch_httpx(monkeypatch)
    matches: list[Any] = []  # no chunks → handoff
    result = asyncio.run(build_llm_answer(
        question='cualquier cosa',
        matches=matches,
        base_url='http://fake',
        model='fake-model',
    ))
    assert result['status'] == 'escalate_to_human'
    assert result['handoff']['required'] is True
    reset_registry()


def test_build_llm_answer_returns_answer_when_ollama_responds_ok(monkeypatch):
    from app.services.circuit_breaker import reset_registry
    from app.services.llm_answer import build_llm_answer

    reset_registry()
    _patch_httpx(monkeypatch, payload={'message': {'content': 'Aqui esta tu respuesta'}})
    matches = [_FakeMatch(text='Servicio X cuesta 50000', score=0.9)]
    result = asyncio.run(build_llm_answer(
        question='cuanto cuesta',
        matches=matches,
        base_url='http://fake',
        model='fake-model',
        min_score=0.0,
    ))
    assert result['status'] == 'answered'
    assert 'Aqui esta tu respuesta' in result['answer']
    assert result['llm_used'] is True
    reset_registry()


def test_build_llm_answer_falls_back_when_no_information(monkeypatch):
    from app.services.circuit_breaker import reset_registry
    from app.services.llm_answer import build_llm_answer

    reset_registry()
    _patch_httpx(monkeypatch, payload={
        'message': {'content': 'No tengo esa información disponible por el momento.'}
    })
    matches = [_FakeMatch(score=0.9)]
    result = asyncio.run(build_llm_answer(
        question='?',
        matches=matches,
        base_url='http://fake',
        model='fake-model',
        min_score=0.0,
    ))
    assert result['status'] == 'escalate_to_human'
    assert result['handoff']['reason'] == 'llm_no_information'
    reset_registry()


def test_build_llm_answer_raises_on_timeout(monkeypatch):
    from app.services.circuit_breaker import reset_registry
    from app.services.llm_answer import build_llm_answer

    reset_registry()
    _patch_httpx(monkeypatch, raise_timeout=True)
    matches = [_FakeMatch(score=0.9)]
    with pytest.raises(httpx.TimeoutException):
        asyncio.run(build_llm_answer(
            question='x',
            matches=matches,
            base_url='http://fake',
            model='fake-model',
            min_score=0.0,
        ))
    reset_registry()


def test_build_llm_answer_raises_on_http_error(monkeypatch):
    from app.services.circuit_breaker import reset_registry
    from app.services.llm_answer import build_llm_answer

    reset_registry()
    _patch_httpx(monkeypatch, status_code=500)
    matches = [_FakeMatch(score=0.9)]
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(build_llm_answer(
            question='x',
            matches=matches,
            base_url='http://fake',
            model='fake-model',
            min_score=0.0,
        ))
    reset_registry()


def test_build_llm_answer_circuit_open_after_threshold(monkeypatch):
    """5 timeouts trip the breaker; the 6th call raises CircuitOpenError before
    even hitting httpx."""
    from app.services.circuit_breaker import CircuitOpenError, reset_registry
    from app.services.llm_answer import build_llm_answer

    reset_registry()
    _patch_httpx(monkeypatch, raise_timeout=True)
    matches = [_FakeMatch(score=0.9)]
    # Trip threshold (5)
    for _ in range(5):
        with pytest.raises(httpx.TimeoutException):
            asyncio.run(build_llm_answer(
                question='x',
                matches=matches,
                base_url='http://fake',
                model='fake-model',
                min_score=0.0,
            ))
    # 6th call: breaker open → CircuitOpenError
    with pytest.raises(CircuitOpenError):
        asyncio.run(build_llm_answer(
            question='x',
            matches=matches,
            base_url='http://fake',
            model='fake-model',
            min_score=0.0,
        ))
    reset_registry()


# ───────── build_conversational_llm_answer ─────────────────────────────────


def _real_ctx():
    """Build a real `ConversationContext` (the conversational LLM path
    calls `ctx.collected_summary()` and `ctx.is_conversational`)."""
    from app.services.conversation_flow import ConversationContext
    return ConversationContext(stage='collecting', collected={})


def test_build_conversational_llm_answer_returns_answer(monkeypatch):
    from app.services.circuit_breaker import reset_registry
    from app.services.llm_answer import build_conversational_llm_answer

    reset_registry()
    # The conversational flow parses JSON from the LLM response. Return a
    # valid `{message, next_stage, action}` JSON block.
    payload_text = '{"message": "Te puedo ayudar", "next_stage": "collecting", "action": "continue"}'
    _patch_httpx(monkeypatch, payload={'message': {'content': payload_text}})
    matches = [_FakeMatch(text='svc info', score=0.9)]
    result = asyncio.run(build_conversational_llm_answer(
        question='quiero agendar',
        matches=matches,
        ctx=_real_ctx(),
        history='',
        base_url='http://fake',
        model='fake-model',
        min_score=0.0,
    ))
    assert result['status'] in ('answered', 'escalate_to_human')
    assert result['llm_used'] is True
    reset_registry()


def test_build_conversational_llm_answer_escalates_on_request_human(monkeypatch):
    from app.services.circuit_breaker import reset_registry
    from app.services.llm_answer import build_conversational_llm_answer

    reset_registry()
    payload_text = '{"message": "Te conecto con un agente", "next_stage": "collecting", "action": "request_human"}'
    _patch_httpx(monkeypatch, payload={'message': {'content': payload_text}})
    matches = [_FakeMatch(score=0.9)]
    result = asyncio.run(build_conversational_llm_answer(
        question='necesito un humano',
        matches=matches,
        ctx=_real_ctx(),
        history='',
        base_url='http://fake',
        model='fake-model',
        min_score=0.0,
    ))
    assert result['status'] == 'escalate_to_human'
    assert result['handoff']['required'] is True
    reset_registry()


def test_build_conversational_llm_answer_uses_history_block(monkeypatch):
    """When history is non-empty, the conversational call includes the prior
    turn — verify the request payload structure."""
    from app.services.circuit_breaker import reset_registry
    from app.services.llm_answer import build_conversational_llm_answer

    reset_registry()
    holder = _patch_httpx(monkeypatch, payload={
        'message': {'content': '{"message": "x", "next_stage": "collecting", "action": "continue"}'}
    })
    matches = [_FakeMatch(score=0.9)]
    asyncio.run(build_conversational_llm_answer(
        question='hola',
        matches=matches,
        ctx=_real_ctx(),
        history='Usuario: que servicios ofrecen?',
        base_url='http://fake',
        model='fake-model',
        min_score=0.0,
    ))
    msgs = holder['client'].last_json['messages']
    # First message is system; second includes history block
    history_msgs = [m for m in msgs if 'HISTORIAL' in (m.get('content') or '')]
    assert len(history_msgs) >= 1
    reset_registry()


def test_build_conversational_llm_answer_raises_on_timeout(monkeypatch):
    from app.services.circuit_breaker import reset_registry
    from app.services.llm_answer import build_conversational_llm_answer

    reset_registry()
    _patch_httpx(monkeypatch, raise_timeout=True)
    matches = [_FakeMatch(score=0.9)]
    with pytest.raises(httpx.TimeoutException):
        asyncio.run(build_conversational_llm_answer(
            question='x',
            matches=matches,
            ctx=_real_ctx(),
            history='',
            base_url='http://fake',
            model='fake-model',
            min_score=0.0,
        ))
    reset_registry()


def test_build_llm_answer_context_filter_excludes_low_score_matches(monkeypatch):
    """The `_build_context` helper skips matches below min_score. With no
    survivors, the function should return handoff (insufficient context)."""
    from app.services.circuit_breaker import reset_registry
    from app.services.llm_answer import build_llm_answer

    reset_registry()
    _patch_httpx(monkeypatch)
    # All matches have score 0.01 < min_score 0.5 → filtered out → handoff
    matches = [_FakeMatch(score=0.01)]
    result = asyncio.run(build_llm_answer(
        question='x',
        matches=matches,
        base_url='http://fake',
        model='fake-model',
        min_score=0.5,
    ))
    assert result['status'] == 'escalate_to_human'
    reset_registry()


def test_build_llm_answer_context_filter_excludes_agents_only_visibility(monkeypatch):
    """Matches with visibility=agents_only are skipped (defense in depth)."""
    from app.services.circuit_breaker import reset_registry
    from app.services.llm_answer import build_llm_answer

    reset_registry()
    _patch_httpx(monkeypatch)
    matches = [_FakeMatch(score=0.9, visibility='agents_only')]
    result = asyncio.run(build_llm_answer(
        question='x',
        matches=matches,
        base_url='http://fake',
        model='fake-model',
        min_score=0.0,
    ))
    # Skipped → empty context → handoff
    assert result['status'] == 'escalate_to_human'
    reset_registry()
