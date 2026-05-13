"""Static tests for TASK-0086 / BUG09: cloud LLM classifier no longer
blocks the event loop and respects ``cloud_llm_timeout_seconds``.

The bug instanced sync ``anthropic.Anthropic`` / ``openai.OpenAI`` clients
and called ``create()`` without ``await`` and without ``timeout``. Each
WhatsApp message that bypassed the regex rules layer froze the event loop
until the provider responded or hung — a trivial webhook DoS vector.

The fix:
  1. Use ``AsyncAnthropic`` / ``AsyncOpenAI`` with ``await``.
  2. Pass ``timeout=settings.cloud_llm_timeout_seconds`` to the SDK.
  3. Wrap each provider call in ``asyncio.wait_for(..., timeout=hard_deadline)``
     so a buggy SDK that ignores its native timeout still releases the loop.
  4. ``asyncio.TimeoutError`` degrades to ``None`` (cascade fallback);
     other exceptions log and fall through.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest  # noqa: F401

from app.services.intent_classifier import _llm_classify, classify_intent

CLASSIFIER = Path('app/services/intent_classifier.py')


# ── Source-level invariants ──────────────────────────────────────────────────


def _llm_classify_block() -> str:
    source = CLASSIFIER.read_text()
    start = source.index('async def _llm_classify(')
    end = source.index('\n# ── Clasificador principal', start)
    return source[start:end]


def test_llm_classify_uses_async_anthropic_not_sync_client():
    block = _llm_classify_block()
    assert 'anthropic.AsyncAnthropic(' in block
    # Old sync client must not be present in the LLM block.
    assert 'anthropic.Anthropic(' not in block.replace('AsyncAnthropic', '')


def test_llm_classify_uses_async_openai_not_sync_client():
    block = _llm_classify_block()
    assert 'openai.AsyncOpenAI(' in block
    assert 'openai.OpenAI(' not in block.replace('AsyncOpenAI', '')


def test_llm_classify_passes_timeout_to_both_sdks():
    block = _llm_classify_block()
    # Both clients receive ``timeout=float(timeout_seconds)``.
    pattern = re.compile(r'(AsyncAnthropic|AsyncOpenAI)\(api_key=api_key, timeout=float\(timeout_seconds\)')
    matches = pattern.findall(block)
    assert set(matches) == {'AsyncAnthropic', 'AsyncOpenAI'}


def test_llm_classify_awaits_provider_calls():
    block = _llm_classify_block()
    # The .create() calls must be awaited (directly or via wait_for).
    assert 'await asyncio.wait_for(' in block
    # Defensive: there should be no .create( call that is NOT inside wait_for.
    # We approximate by ensuring there is no `intent_raw = ... = .create(` with
    # no surrounding `await`.
    assert 'client.messages.create(' in block  # call still present
    assert 'client.chat.completions.create(' in block
    # Old blocking patterns gone:
    assert 'msg = client.messages.create(' not in block
    assert 'resp = client.chat.completions.create(' not in block


def test_llm_classify_uses_hard_deadline_above_sdk_timeout():
    block = _llm_classify_block()
    # The outer wait_for runs with hard_deadline = max(timeout_seconds + 2, 5).
    assert 'hard_deadline = max(timeout_seconds + 2, 5)' in block
    # Both provider branches pass it.
    assert 'timeout=hard_deadline' in block


def test_llm_classify_distinguishes_timeout_from_other_errors():
    block = _llm_classify_block()
    # Each provider branch has a dedicated TimeoutError handler.
    timeout_handlers = block.count('except asyncio.TimeoutError:')
    assert timeout_handlers >= 2  # cloud branch + ollama branch
    assert 'intent_classifier.llm_timeout' in block
    assert 'intent_classifier.ollama_timeout' in block


def test_llm_classify_reads_timeout_from_settings_with_default():
    block = _llm_classify_block()
    assert "getattr(settings, 'cloud_llm_timeout_seconds', 30)" in block


# ── Runtime behaviour: stub clients to assert async dispatch + timeout ───────


class _StubAnthropicResponse:
    def __init__(self, intent: str):
        self.content = [SimpleNamespace(text=intent)]


class _StubAsyncAnthropic:
    """Coroutine factory that mimics ``anthropic.AsyncAnthropic``."""

    def __init__(self, *, hang: bool = False, intent: str = 'faq', api_key: str | None = None, timeout: float | None = None):
        self._hang = hang
        self._intent = intent
        self.received_timeout = timeout
        self.received_api_key = api_key
        self.messages = self  # so .messages.create works

    async def create(self, **kwargs):  # noqa: ARG002 - signature mirrors SDK
        if self._hang:
            await asyncio.sleep(60)
        return _StubAnthropicResponse(self._intent)


def _settings(timeout: int = 30, provider: str = 'claude') -> Any:
    return SimpleNamespace(
        cloud_llm_provider=provider,
        cloud_llm_api_key='test-key',
        cloud_llm_model='claude-sonnet-4-6',
        cloud_llm_timeout_seconds=timeout,
        local_llm_base_url=None,
        local_llm_model=None,
        local_llm_timeout_seconds=8,
    )


def test_llm_classify_returns_intent_when_provider_responds_promptly(monkeypatch):
    import sys

    stub_module = SimpleNamespace(AsyncAnthropic=lambda **kw: _StubAsyncAnthropic(intent='book_appointment', **kw))
    monkeypatch.setitem(sys.modules, 'anthropic', stub_module)

    result = asyncio.run(
        _llm_classify(
            'agendame mañana',
            {'book_appointment', 'faq', 'greeting'},
            _settings(timeout=5),
        )
    )

    assert result is not None
    assert result.intent == 'book_appointment'
    assert result.resolved_by == 'llm'


def test_llm_classify_returns_none_on_provider_timeout_without_hanging(monkeypatch):
    """Hard guarantee: a hanging provider must NOT block the event loop past
    hard_deadline. We use timeout=1 → hard_deadline=3."""
    import sys

    stub_module = SimpleNamespace(AsyncAnthropic=lambda **kw: _StubAsyncAnthropic(hang=True, **kw))
    monkeypatch.setitem(sys.modules, 'anthropic', stub_module)

    async def run_with_concurrent_workload():
        # Concurrent task that measures whether the event loop stayed
        # responsive while the LLM call hung.
        latencies: list[float] = []

        async def ticker():
            loop = asyncio.get_event_loop()
            for _ in range(5):
                t0 = loop.time()
                await asyncio.sleep(0.05)
                latencies.append(loop.time() - t0)

        ticker_task = asyncio.create_task(ticker())
        result = await _llm_classify(
            'algo ambiguo',
            {'faq', 'book_appointment'},
            _settings(timeout=1),
        )
        await ticker_task
        return result, latencies

    result, latencies = asyncio.run(run_with_concurrent_workload())

    assert result is None
    # Ticker latencies stayed close to the requested 50ms — none blew past
    # 200ms even though the LLM hung for the whole hard_deadline.
    assert max(latencies) < 0.2, f'event loop was blocked: {latencies}'


def test_llm_classify_propagates_timeout_to_anthropic_sdk(monkeypatch):
    """The SDK timeout (not just our outer wait_for) is wired."""
    import sys

    captured: dict[str, Any] = {}

    def factory(**kw):
        captured.update(kw)
        return _StubAsyncAnthropic(intent='faq', **kw)

    stub_module = SimpleNamespace(AsyncAnthropic=factory)
    monkeypatch.setitem(sys.modules, 'anthropic', stub_module)

    asyncio.run(
        _llm_classify(
            'cuánto cuesta',
            {'faq'},
            _settings(timeout=7),
        )
    )

    assert captured['timeout'] == 7.0
    assert captured['api_key'] == 'test-key'


def test_classify_intent_falls_back_to_faq_when_llm_times_out(monkeypatch):
    """End-to-end cascade: rule layer doesn't match → LLM hangs → fallback."""
    import sys

    stub_module = SimpleNamespace(AsyncAnthropic=lambda **kw: _StubAsyncAnthropic(hang=True, **kw))
    monkeypatch.setitem(sys.modules, 'anthropic', stub_module)

    result = asyncio.run(
        classify_intent(
            'xyz palabras inventadas que no matchean nada',
            settings=_settings(timeout=1),
        )
    )

    # Cascade fell back to faq (the safe neutral) without hanging.
    assert result.resolved_by == 'fallback'
    assert result.intent == 'faq'


# ── Ollama branch also wraps with wait_for ───────────────────────────────────


def test_ollama_branch_also_uses_wait_for_for_event_loop_safety():
    block = _llm_classify_block()
    # The ollama branch must wrap httpx.AsyncClient.post in wait_for too.
    ollama_idx = block.index('ollama_url =')
    end_idx = block.index('if intent_raw and intent_raw in ALL_INTENTS')
    ollama_block = block[ollama_idx:end_idx]
    assert 'await asyncio.wait_for(' in ollama_block
    assert "intent_classifier.ollama_timeout" in ollama_block
