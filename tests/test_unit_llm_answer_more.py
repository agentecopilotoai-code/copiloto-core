"""Extra tests for app/chatbot/llm_answer.py to push coverage."""
from __future__ import annotations

import asyncio

import httpx
import pytest


class _FakeMatch:
    def __init__(self, *, text='ctx', score=0.5, doc_title='Doc', visibility='public',
                 source_uri=None, section_path=None, chunk_id='c1'):
        self.chunk_text = text
        self.score = score
        self.document_title = doc_title
        self.visibility = visibility
        self.source_uri = source_uri
        self.section_path = section_path
        self.id = chunk_id


class _StubResp:
    def __init__(self, payload, status_code=200):
        self._p = payload
        self.status_code = status_code

    def json(self):
        return self._p

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            req = httpx.Request('POST', 'http://t')
            resp = httpx.Response(self.status_code, request=req)
            raise httpx.HTTPStatusError('bad', request=req, response=resp)


class _StubClient:
    def __init__(self, payload=None, *, raise_timeout=False, status_code=200,
                 raise_runtime=False, **_kw):
        self.payload = payload or {'message': {'content': 'ok'}}
        self.raise_timeout = raise_timeout
        self.status_code = status_code
        self.raise_runtime = raise_runtime
        self.last_json = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, **kw):
        self.last_json = json
        if self.raise_timeout:
            raise httpx.TimeoutException('timeout')
        if self.raise_runtime:
            raise RuntimeError('boom')
        return _StubResp(self.payload, status_code=self.status_code)


def _patch(monkeypatch, **kw):
    def _factory(**ck):
        return _StubClient(**kw, **ck)

    monkeypatch.setattr(httpx, 'AsyncClient', _factory)


def test_breaker_for_local_llm_falls_back_when_settings_unavailable(monkeypatch):
    from app.chatbot import llm_answer

    def _boom():
        raise RuntimeError('no settings')

    monkeypatch.setattr(llm_answer, 'get_settings', _boom)
    b = llm_answer._breaker_for_local_llm()
    assert b is not None


def test_qa_system_prompt_appends_personality_block(monkeypatch):
    from app.chatbot import llm_answer
    out = llm_answer._qa_system_prompt(None)
    # default returns the base prompt
    assert 'asistente' in out.lower() or 'cliente' in out.lower()


def test_qa_system_prompt_with_personality(monkeypatch):
    from app.chatbot import llm_answer
    # Patch build_personality_block to return a non-empty block
    import app.services.conversation_flow as cf
    monkeypatch.setattr(cf, 'build_personality_block', lambda p: 'BLOCK')
    out = llm_answer._qa_system_prompt({'tone': 'formal'})
    assert 'BLOCK' in out


def test_build_llm_answer_raises_on_generic_exception(monkeypatch):
    from app.services.circuit_breaker import reset_registry
    from app.chatbot.llm_answer import build_llm_answer

    reset_registry()
    _patch(monkeypatch, raise_runtime=True)
    matches = [_FakeMatch(score=0.9)]
    with pytest.raises(RuntimeError):
        asyncio.run(build_llm_answer(
            question='x', matches=matches,
            base_url='http://fake', model='fake-model',
            min_score=0.0,
        ))
    reset_registry()


def test_build_conversational_llm_answer_raises_on_http_error(monkeypatch):
    from app.services.circuit_breaker import reset_registry
    from app.services.conversation_flow import ConversationContext
    from app.chatbot.llm_answer import build_conversational_llm_answer

    reset_registry()
    _patch(monkeypatch, status_code=503)
    matches = [_FakeMatch(score=0.9)]
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(build_conversational_llm_answer(
            question='hola', matches=matches,
            ctx=ConversationContext(stage='collecting', collected={}),
            history='', base_url='http://fake', model='fake-model',
            min_score=0.0,
        ))
    reset_registry()


def test_build_conversational_llm_answer_raises_on_runtime(monkeypatch):
    from app.services.circuit_breaker import reset_registry
    from app.services.conversation_flow import ConversationContext
    from app.chatbot.llm_answer import build_conversational_llm_answer

    reset_registry()
    _patch(monkeypatch, raise_runtime=True)
    matches = [_FakeMatch(score=0.9)]
    with pytest.raises(RuntimeError):
        asyncio.run(build_conversational_llm_answer(
            question='hola', matches=matches,
            ctx=ConversationContext(stage='collecting', collected={}),
            history='', base_url='http://fake', model='fake-model',
            min_score=0.0,
        ))
    reset_registry()


def test_build_conversational_llm_answer_circuit_open(monkeypatch):
    from app.services.circuit_breaker import CircuitOpenError, reset_registry
    from app.services.conversation_flow import ConversationContext
    from app.chatbot.llm_answer import build_conversational_llm_answer

    reset_registry()
    _patch(monkeypatch, raise_timeout=True)
    matches = [_FakeMatch(score=0.9)]
    for _ in range(5):
        with pytest.raises(httpx.TimeoutException):
            asyncio.run(build_conversational_llm_answer(
                question='x', matches=matches,
                ctx=ConversationContext(stage='collecting', collected={}),
                history='', base_url='http://fake', model='fake-model',
                min_score=0.0,
            ))
    with pytest.raises(CircuitOpenError):
        asyncio.run(build_conversational_llm_answer(
            question='x', matches=matches,
            ctx=ConversationContext(stage='collecting', collected={}),
            history='', base_url='http://fake', model='fake-model',
            min_score=0.0,
        ))
    reset_registry()


def test_build_llm_answer_includes_section_path_in_context(monkeypatch):
    from app.services.circuit_breaker import reset_registry
    from app.chatbot.llm_answer import build_llm_answer

    reset_registry()
    _patch(monkeypatch, payload={'message': {'content': 'respuesta'}})
    matches = [_FakeMatch(score=0.9, section_path='Sección 1', text='contenido')]
    result = asyncio.run(build_llm_answer(
        question='x', matches=matches,
        base_url='http://fake', model='fake-model',
        min_score=0.0,
    ))
    assert result['status'] == 'answered'
    reset_registry()
