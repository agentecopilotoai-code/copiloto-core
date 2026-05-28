"""Tests for PERF-022 (audit#4) — backoff/jitter + retry-after honor.

El dispatcher antes saltaba al siguiente provider inmediatamente al
fallar, causando thundering-herd al fallback cuando rate-limit
afectaba al primary. Ahora:

 1. Espera con backoff exponencial + jitter entre intentos.
 2. Si el `ProviderRateLimited` trae `retry_after`, lo honra (cap a
    BACKOFF_MAX_SECONDS).
 3. Si el chain se agotó, NO duerme (no tiene sentido).
"""
from __future__ import annotations

import asyncio
import random
from unittest.mock import AsyncMock, patch

import pytest

from app.ai.dispatcher import (
    BACKOFF_MAX_SECONDS,
    _backoff_for_attempt,
)
from app.ai.providers.base import ProviderRateLimited


# ─── _backoff_for_attempt unit tests ──────────────────────────────────────


def test_backoff_with_explicit_retry_after_honored():
    delay = _backoff_for_attempt(attempt=0, retry_after=3.0)
    assert delay == 3.0


def test_backoff_retry_after_capped_to_max():
    # provider hostil sugiere 600s — cap a BACKOFF_MAX_SECONDS.
    delay = _backoff_for_attempt(attempt=0, retry_after=600.0)
    assert delay == BACKOFF_MAX_SECONDS


def test_backoff_retry_after_zero_falls_through_to_exponential(monkeypatch):
    # retry_after=0 → cae al exponential (porque condición es `> 0`).
    monkeypatch.setattr(random, 'random', lambda: 0.5)  # jitter neutro
    delay = _backoff_for_attempt(attempt=0, retry_after=0.0)
    assert delay > 0  # exponential base, no cero.


def test_backoff_exponential_grows(monkeypatch):
    # Sin jitter para test determinístico.
    monkeypatch.setattr(random, 'random', lambda: 0.5)
    d0 = _backoff_for_attempt(0)
    d1 = _backoff_for_attempt(1)
    d2 = _backoff_for_attempt(2)
    assert d0 < d1 < d2
    # Cap eventual.
    big = _backoff_for_attempt(20)
    assert big <= BACKOFF_MAX_SECONDS * 1.31  # con jitter +30% en el peor caso


def test_backoff_capped_at_max(monkeypatch):
    monkeypatch.setattr(random, 'random', lambda: 0.5)  # jitter = 0
    delay = _backoff_for_attempt(attempt=100)
    assert delay == BACKOFF_MAX_SECONDS


def test_backoff_jitter_in_range():
    # Distribución con jitter ±30%. Sampleamos N veces y verificamos rango.
    samples = [_backoff_for_attempt(attempt=2) for _ in range(50)]
    base = 0.25 * 4  # BACKOFF_BASE_SECONDS * 2^2
    lo = base * 0.7
    hi = base * 1.3
    assert all(lo - 0.01 <= s <= hi + 0.01 for s in samples)


# ─── ProviderRateLimited carries retry_after ──────────────────────────────


def test_provider_rate_limited_with_retry_after():
    exc = ProviderRateLimited('test', retry_after=5.5)
    assert exc.retry_after == 5.5


def test_provider_rate_limited_without_retry_after():
    exc = ProviderRateLimited('test')
    assert exc.retry_after is None


# ─── Integration: dispatcher honra retry_after antes de fallback ──────────


@pytest.mark.asyncio
async def test_dispatcher_honors_retry_after_before_fallback(monkeypatch):
    """Cuando primary lanza ProviderRateLimited con retry_after=2.0,
    el dispatcher debe esperar ~2.0s antes del siguiente intento.
    """
    from app.ai.dispatcher import dispatch
    from app.ai.registry import ResolvedProvider

    primary = ResolvedProvider(
        modality='llm', provider='primary_x',
        secret_ref='ref/primary', model=None, params={}, source='db',
    )
    chain = ['primary_x', 'fallback_y']

    monkeypatch.setattr(
        'app.ai.dispatcher.resolve_provider',
        AsyncMock(return_value=primary),
    )
    monkeypatch.setattr(
        'app.ai.dispatcher._get_fallback_chain',
        lambda p: ['fallback_y'],
    )
    # Reset breakers para evitar carry-over entre tests.
    monkeypatch.setattr('app.ai.dispatcher._BREAKERS',
                        __import__('collections').defaultdict(
                            __import__('app.ai.dispatcher', fromlist=['_CircuitState'])._CircuitState))

    call_count = {'n': 0}

    async def fake_call(resolved):
        call_count['n'] += 1
        if resolved.provider == 'primary_x':
            raise ProviderRateLimited('primary 429', retry_after=0.1)
        return 'ok-from-fallback'

    sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def captured_sleep(d):
        sleeps.append(d)
        # No durmas de verdad en test.
        await real_sleep(0)

    with patch('app.ai.dispatcher.asyncio.sleep', side_effect=captured_sleep):
        result = await dispatch(
            conn=AsyncMock(),
            modality='llm',
            call_fn=fake_call,
            audit_conn=None,
        )

    assert result == 'ok-from-fallback'
    assert call_count['n'] == 2
    # Honra retry_after — el primer sleep es exactamente 0.1.
    assert len(sleeps) == 1
    assert abs(sleeps[0] - 0.1) < 0.01


@pytest.mark.asyncio
async def test_dispatcher_uses_backoff_when_no_retry_after(monkeypatch):
    """Sin retry_after, debe usar backoff exponencial con jitter."""
    from app.ai.dispatcher import dispatch
    from app.ai.registry import ResolvedProvider

    primary = ResolvedProvider(
        modality='llm', provider='primary_x',
        secret_ref='ref/primary', model=None, params={}, source='db',
    )

    monkeypatch.setattr(
        'app.ai.dispatcher.resolve_provider',
        AsyncMock(return_value=primary),
    )
    monkeypatch.setattr(
        'app.ai.dispatcher._get_fallback_chain',
        lambda p: ['fallback_y'],
    )
    monkeypatch.setattr('app.ai.dispatcher._BREAKERS',
                        __import__('collections').defaultdict(
                            __import__('app.ai.dispatcher', fromlist=['_CircuitState'])._CircuitState))

    async def fake_call(resolved):
        if resolved.provider == 'primary_x':
            raise ProviderRateLimited('primary 429')  # no retry_after
        return 'ok'

    sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def captured_sleep(d):
        sleeps.append(d)
        await real_sleep(0)

    with patch('app.ai.dispatcher.asyncio.sleep', side_effect=captured_sleep):
        result = await dispatch(
            conn=AsyncMock(), modality='llm',
            call_fn=fake_call, audit_conn=None,
        )

    assert result == 'ok'
    # Backoff exponencial — para attempt=0, base=0.25 ± 30%.
    assert len(sleeps) == 1
    assert 0.15 <= sleeps[0] <= 0.35


@pytest.mark.asyncio
async def test_dispatcher_no_sleep_when_chain_exhausted(monkeypatch):
    """Si el último provider falla, no debe haber sleep (sería overhead
    inútil — la dispatch fall completa)."""
    from app.ai.dispatcher import dispatch
    from app.ai.registry import ResolvedProvider

    primary = ResolvedProvider(
        modality='llm', provider='primary_x',
        secret_ref='ref/primary', model=None, params={}, source='db',
    )

    monkeypatch.setattr(
        'app.ai.dispatcher.resolve_provider',
        AsyncMock(return_value=primary),
    )
    monkeypatch.setattr(
        'app.ai.dispatcher._get_fallback_chain',
        lambda p: [],  # cadena sin fallback
    )
    monkeypatch.setattr('app.ai.dispatcher._BREAKERS',
                        __import__('collections').defaultdict(
                            __import__('app.ai.dispatcher', fromlist=['_CircuitState'])._CircuitState))

    async def fake_call(resolved):
        raise ProviderRateLimited('429', retry_after=10.0)

    sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def captured_sleep(d):
        sleeps.append(d)
        await real_sleep(0)

    from app.ai.providers.base import ProviderUnavailable

    with patch('app.ai.dispatcher.asyncio.sleep', side_effect=captured_sleep):
        with pytest.raises(ProviderUnavailable):
            await dispatch(
                conn=AsyncMock(), modality='llm',
                call_fn=fake_call, audit_conn=None,
            )

    # No sleeps cuando chain agotada.
    assert sleeps == []


# ─── _parse_retry_after unit tests ────────────────────────────────────────


def test_parse_retry_after_seconds():
    from app.ai.providers.grok import _parse_retry_after

    assert _parse_retry_after('5') == 5.0
    assert _parse_retry_after('2.5') == 2.5


def test_parse_retry_after_none():
    from app.ai.providers.grok import _parse_retry_after

    assert _parse_retry_after(None) is None
    assert _parse_retry_after('') is None


def test_parse_retry_after_negative_or_too_big():
    from app.ai.providers.grok import _parse_retry_after

    assert _parse_retry_after('-1') is None
    assert _parse_retry_after('99999') is None


def test_parse_retry_after_garbage():
    from app.ai.providers.grok import _parse_retry_after

    assert _parse_retry_after('not-a-number') is None


def test_parse_retry_after_http_date():
    """HTTP-date format (RFC 9110) — convertir a delta desde ahora."""
    from app.ai.providers.grok import _parse_retry_after
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime

    future = datetime.now(tz=timezone.utc) + timedelta(seconds=10)
    s = format_datetime(future, usegmt=True)
    delta = _parse_retry_after(s)
    assert delta is not None
    assert 5 < delta <= 15  # margen por timing


def test_parse_retry_after_past_http_date():
    """HTTP-date en el pasado → None (no espera)."""
    from app.ai.providers.grok import _parse_retry_after
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime

    past = datetime.now(tz=timezone.utc) - timedelta(seconds=10)
    s = format_datetime(past, usegmt=True)
    assert _parse_retry_after(s) is None
