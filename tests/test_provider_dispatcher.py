"""Tests para ``provider_dispatcher.dispatch`` — TASK-INFLU-007.

Cubren:
- primary fail → fallback usado
- chain completo fail → ``ProviderUnavailable``
- ``ProviderContentRejected`` no se reintenta
- circuit breaker abre tras 5 fallos consecutivos
- audit fila se inserta (mock conn que captura el INSERT)
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.ai.dispatcher import (
    CB_FAILURE_THRESHOLD,
    _breakers_reset,
    dispatch,
)
from app.ai.registry import (
    ResolvedProvider,
    _cache_invalidate,
)
from app.ai.providers.base import (
    ProviderContentRejected,
    ProviderTimeoutError,
    ProviderUnavailable,
    TextResult,
)


@pytest.fixture(autouse=True)
def _reset_state():
    _breakers_reset()
    _cache_invalidate()
    yield
    _breakers_reset()
    _cache_invalidate()


def _make_conn(provider: str = 'grok', fallback: list[str] | None = None):
    """Mock conn que devuelve un ResolvedProvider con un fallback chain."""
    fallback = fallback or ['anthropic', 'ollama']
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(
        return_value={
            'provider': provider,
            'secret_ref': 'secrets/grok-api-key',
            'model': 'grok-4.3',
            'params': {'fallback_chain': fallback},
        },
    )
    conn.execute = AsyncMock(return_value='INSERT 0 1')
    return conn


def test_primary_success_returns_result_without_fallback():
    calls: list[str] = []

    async def call(resolved: ResolvedProvider) -> TextResult:
        calls.append(resolved.provider)
        return TextResult(text='hola', finish_reason='stop')

    conn = _make_conn()
    result = asyncio.run(dispatch(conn=conn, modality='llm', call_fn=call))
    assert isinstance(result, TextResult)
    assert result.text == 'hola'
    assert calls == ['grok']  # primary, no fallback


def test_primary_fails_fallback_succeeds():
    calls: list[str] = []

    async def call(resolved: ResolvedProvider) -> TextResult:
        calls.append(resolved.provider)
        if resolved.provider == 'grok':
            raise ProviderTimeoutError('grok timed out')
        return TextResult(text='fallback works')

    conn = _make_conn()
    result = asyncio.run(dispatch(conn=conn, modality='llm', call_fn=call))
    assert result.text == 'fallback works'
    assert calls == ['grok', 'anthropic']


def test_entire_chain_fails_raises_unavailable():
    async def call(resolved: ResolvedProvider) -> Any:
        raise ProviderUnavailable(f'{resolved.provider} down')

    conn = _make_conn()
    with pytest.raises(ProviderUnavailable):
        asyncio.run(dispatch(conn=conn, modality='llm', call_fn=call))


def test_content_rejected_does_not_fallback():
    calls: list[str] = []

    async def call(resolved: ResolvedProvider) -> Any:
        calls.append(resolved.provider)
        raise ProviderContentRejected('safety filter')

    conn = _make_conn()
    with pytest.raises(ProviderContentRejected):
        asyncio.run(dispatch(conn=conn, modality='llm', call_fn=call))
    assert calls == ['grok'], 'content rejection NO debe disparar fallback'


def test_circuit_breaker_opens_after_threshold_failures():
    # Forzar fallos consecutivos del primario en una misma ventana.
    async def always_fail_primary(resolved: ResolvedProvider) -> Any:
        if resolved.provider == 'grok':
            raise ProviderTimeoutError('timeout')
        return TextResult(text='ok')  # fallback siempre OK

    conn = _make_conn()
    # Las primeras 5 corridas usan fallback porque primary falla.
    for _ in range(CB_FAILURE_THRESHOLD):
        result = asyncio.run(
            dispatch(conn=conn, modality='llm', call_fn=always_fail_primary),
        )
        assert result.text == 'ok'

    # Después de 5 fallos, el breaker debe estar abierto. La 6ta call
    # debe saltar el primary y usar fallback directo.
    calls: list[str] = []

    async def trace(resolved: ResolvedProvider) -> Any:
        calls.append(resolved.provider)
        return TextResult(text='from fallback')

    asyncio.run(dispatch(conn=conn, modality='llm', call_fn=trace))
    assert 'grok' not in calls, 'breaker abierto debe saltar a grok'
    assert calls[0] == 'anthropic'


def test_audit_row_inserted_on_success():
    conn = _make_conn()

    async def call(resolved: ResolvedProvider) -> TextResult:
        return TextResult(text='ok')

    asyncio.run(
        dispatch(conn=conn, modality='llm', call_fn=call, audit_conn=conn),
    )
    # Verificar que el INSERT al audit table se llamó.
    assert conn.execute.called
    sql = conn.execute.call_args[0][0]
    assert 'influencer.provider_dispatch' in sql


def test_audit_records_failure_when_all_fail():
    conn = _make_conn()

    async def call(_):
        raise ProviderUnavailable('down')

    with pytest.raises(ProviderUnavailable):
        asyncio.run(
            dispatch(conn=conn, modality='llm', call_fn=call, audit_conn=conn),
        )
    assert conn.execute.called
    args = conn.execute.call_args[0]
    # args[0] = SQL; args[1..] = parámetros
    assert args[6] is False, 'success debería ser False cuando todo falla'


def test_empty_fallback_chain_raises_when_primary_fails():
    conn = _make_conn(fallback=[])

    async def call(_):
        raise ProviderTimeoutError('timeout')

    with pytest.raises(ProviderUnavailable):
        asyncio.run(dispatch(conn=conn, modality='llm', call_fn=call))
