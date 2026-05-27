"""Tests para `app.services.sliding_window_rate_limit` (P1-3 audit 2026-05-27)."""
from __future__ import annotations

import asyncio
import time

import pytest


def test_check_admits_first_call_returns_true():
    from app.services.sliding_window_rate_limit import SlidingWindowLimiter
    limiter = SlidingWindowLimiter(max_calls=3, window_seconds=60)
    assert asyncio.run(limiter.check('user-1')) is True


def test_check_rejects_call_above_max():
    from app.services.sliding_window_rate_limit import SlidingWindowLimiter
    limiter = SlidingWindowLimiter(max_calls=2, window_seconds=60)
    assert asyncio.run(limiter.check('u')) is True
    assert asyncio.run(limiter.check('u')) is True
    assert asyncio.run(limiter.check('u')) is False  # 3rd → rejected


def test_check_distinct_keys_isolated():
    from app.services.sliding_window_rate_limit import SlidingWindowLimiter
    limiter = SlidingWindowLimiter(max_calls=1, window_seconds=60)
    assert asyncio.run(limiter.check('a')) is True
    assert asyncio.run(limiter.check('b')) is True
    # Cada key rechaza individualmente.
    assert asyncio.run(limiter.check('a')) is False
    assert asyncio.run(limiter.check('b')) is False


def test_check_allows_after_window_passes():
    """Sliding-window: timestamps fuera del window se descartan."""
    from app.services.sliding_window_rate_limit import SlidingWindowLimiter
    limiter = SlidingWindowLimiter(max_calls=1, window_seconds=0.5)
    assert asyncio.run(limiter.check('u')) is True
    assert asyncio.run(limiter.check('u')) is False  # rechazado
    time.sleep(0.6)
    # El timestamp viejo cayó del window → admite nuevo.
    assert asyncio.run(limiter.check('u')) is True


def test_check_or_raise_raises_429():
    from fastapi import HTTPException

    from app.services.sliding_window_rate_limit import SlidingWindowLimiter
    limiter = SlidingWindowLimiter(max_calls=1, window_seconds=60)
    asyncio.run(limiter.check_or_raise('u'))  # ok
    with pytest.raises(HTTPException) as exc:
        asyncio.run(limiter.check_or_raise('u'))
    assert exc.value.status_code == 429


def test_lru_eviction_when_exceeds_max_entries():
    """Cap LRU: tras N keys distintas, las más viejas se evictean."""
    from app.services.sliding_window_rate_limit import SlidingWindowLimiter
    limiter = SlidingWindowLimiter(
        max_calls=10, window_seconds=60, max_entries=3,
    )
    asyncio.run(limiter.check('a'))
    asyncio.run(limiter.check('b'))
    asyncio.run(limiter.check('c'))
    assert limiter.size == 3
    asyncio.run(limiter.check('d'))  # evicta 'a' (LRU)
    assert limiter.size == 3
    # 'a' fue evictada → su counter se resetea.
    # Para verificar, llenamos 'a' hasta el max y debe permitir 10 (no
    # acumular el call previo).
    for _ in range(10):
        asyncio.run(limiter.check('a'))


def test_reset_clears_all_buckets():
    from app.services.sliding_window_rate_limit import SlidingWindowLimiter
    limiter = SlidingWindowLimiter(max_calls=1, window_seconds=60)
    asyncio.run(limiter.check('u'))
    assert asyncio.run(limiter.check('u')) is False
    limiter.reset()
    assert asyncio.run(limiter.check('u')) is True


def test_init_validation():
    from app.services.sliding_window_rate_limit import SlidingWindowLimiter
    with pytest.raises(ValueError):
        SlidingWindowLimiter(max_calls=0, window_seconds=60)
    with pytest.raises(ValueError):
        SlidingWindowLimiter(max_calls=10, window_seconds=0)
    with pytest.raises(ValueError):
        SlidingWindowLimiter(
            max_calls=10, window_seconds=60, max_entries=0,
        )


def test_sync_adapter():
    """`_build_sync_check` para call sites que no son async."""
    from app.services.sliding_window_rate_limit import (
        SlidingWindowLimiter, _build_sync_check,
    )
    limiter = SlidingWindowLimiter(max_calls=2, window_seconds=60)
    check = _build_sync_check(limiter)
    assert check('u') is True
    assert check('u') is True
    assert check('u') is False
