"""AUDIT-46 — Static regression tests for the audit quick wins (2026-05-18).

Covers (1) DB pool config exposure, (2) rate-limiter LRU eviction,
(3) Ollama circuit breaker wrap, (4) Auth0 Management API circuit breaker
+ 401 token cache invalidation.

All tests are static (no DB, no network) — they assert on source patterns
and exercise the in-process units with monkeypatched primitives.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# ─────────────────── Speed #1 — DB pool config exposure ────────────────────


def test_pool_uses_settings_not_hardcoded():
    src = (REPO_ROOT / 'app' / 'db' / 'pool.py').read_text()
    # Settings hook present
    assert 'db_pool_min_size' in src
    assert 'db_pool_max_size' in src
    assert 'db_pool_command_timeout_seconds' in src
    # And no longer the hardcoded literal trio
    assert 'min_size=1, max_size=10, command_timeout=30' not in src


def test_config_exposes_pool_fields():
    src = (REPO_ROOT / 'app' / 'core' / 'config.py').read_text()
    assert 'db_pool_min_size: int = Field(default=1, ge=1)' in src
    assert 'db_pool_max_size: int = Field(default=10, ge=2, le=200)' in src
    assert 'db_pool_command_timeout_seconds: float = Field(default=30.0' in src


# ─────────────────── Speed #2 — Rate limiter LRU eviction ──────────────────


def test_rate_limiter_evicts_oldest_when_max_entries_exceeded():
    from app.services.rate_limit import RateLimiter

    limiter = RateLimiter(
        default_per_minute=60,
        webhook_per_minute=600,
        max_entries=3,
        ttl_seconds=900,
    )

    async def run():
        # Insert 4 distinct keys → oldest must be evicted to keep cap=3
        for i in range(4):
            await limiter.check(f'ip{i}', scope='default')
        return list(limiter._buckets.keys())

    keys = asyncio.new_event_loop().run_until_complete(run())
    assert len(keys) == 3
    # First inserted ('ip0') must have been evicted (LRU = least recently used)
    assert 'ip0' not in keys
    assert {'ip1', 'ip2', 'ip3'} == set(keys)


def test_rate_limiter_touches_lru_on_reuse():
    from app.services.rate_limit import RateLimiter

    limiter = RateLimiter(
        default_per_minute=60,
        webhook_per_minute=600,
        max_entries=3,
        ttl_seconds=900,
    )

    async def run():
        for i in range(3):
            await limiter.check(f'ip{i}', scope='default')
        # Touch the oldest ('ip0') so it moves to most-recently-used.
        await limiter.check('ip0', scope='default')
        # Insert one more; LRU eviction should drop ip1, NOT ip0.
        await limiter.check('ip3', scope='default')
        return list(limiter._buckets.keys())

    keys = asyncio.new_event_loop().run_until_complete(run())
    assert 'ip0' in keys, 'ip0 was touched and should NOT be evicted'
    assert 'ip1' not in keys, 'ip1 was oldest after touch; should be evicted'


def test_rate_limiter_expires_idle_keys_by_ttl(monkeypatch):
    from app.services import rate_limit as rl
    from app.services.rate_limit import RateLimiter

    limiter = RateLimiter(
        default_per_minute=1,  # tiny capacity so we exhaust in 1 call
        webhook_per_minute=600,
        max_entries=1000,
        ttl_seconds=10,
    )

    fake_now = {'t': 1000.0}
    monkeypatch.setattr(rl.time, 'monotonic', lambda: fake_now['t'])

    async def run():
        # First call: consume the bucket (now empty)
        allowed1, _ = await limiter.check('ip-cold', scope='default')
        # Second call: would be rate-limited (bucket empty, no refill yet)
        allowed2, _ = await limiter.check('ip-cold', scope='default')
        # Advance past TTL → bucket should be purged on next access
        fake_now['t'] += 100.0
        # Third call: bucket recreated fresh; allowed again with full capacity
        allowed3, _ = await limiter.check('ip-cold', scope='default')
        return allowed1, allowed2, allowed3

    a1, a2, a3 = asyncio.new_event_loop().run_until_complete(run())
    assert a1 is True, 'first call must consume the bucket'
    assert a2 is False, 'second call must be rate-limited (no refill within ms)'
    assert a3 is True, (
        'third call after TTL must hit a fresh bucket — proves the expired one '
        'was purged, NOT just refilled by elapsed-time math'
    )


def test_rate_limiter_rejects_bad_construction():
    from app.services.rate_limit import RateLimiter

    with pytest.raises(ValueError):
        RateLimiter(default_per_minute=60, webhook_per_minute=600, max_entries=0)
    with pytest.raises(ValueError):
        RateLimiter(default_per_minute=60, webhook_per_minute=600, ttl_seconds=0)


def test_main_passes_rate_limiter_cap_and_ttl_settings():
    src = (REPO_ROOT / 'app' / 'main.py').read_text()
    assert 'max_entries=settings.rate_limit_bucket_max_entries' in src
    assert 'ttl_seconds=settings.rate_limit_bucket_ttl_seconds' in src


# ───────────────── Speed #5 — Ollama circuit breaker wrap ──────────────────


def test_llm_answer_imports_and_uses_circuit_breaker():
    src = (REPO_ROOT / 'app' / 'chatbot' / 'llm_answer.py').read_text()
    assert 'from app.services.circuit_breaker import CircuitOpenError, get_breaker' in src
    # Both entry points wrap the call in a breaker
    assert src.count('breaker = _breaker_for_local_llm()') >= 2
    assert src.count("await breaker.call(") >= 2
    # The breaker name is "local_llm" (consistent with metrics naming)
    assert "'local_llm'" in src
    # No more raw httpx.AsyncClient calls inside build_llm_answer /
    # build_conversational_llm_answer (those moved into _ollama_chat).
    assert src.count('async with httpx.AsyncClient(') == 1  # only _ollama_chat


def test_llm_answer_records_rejected_on_circuit_open():
    src = (REPO_ROOT / 'app' / 'chatbot' / 'llm_answer.py').read_text()
    # Both flows record 'rejected' status when the breaker is open so the
    # metric distinguishes Ollama-down (rejected) from Ollama-slow (timeout).
    assert src.count("status='rejected'") >= 2


# ───── Security #5 — Auth0 Management API circuit breaker + 401 cache ──────


def test_auth0_admin_uses_circuit_breaker():
    src = (REPO_ROOT / 'app' / 'services' / 'auth0_admin.py').read_text()
    assert 'from app.services.circuit_breaker import CircuitOpenError, get_breaker' in src
    assert "_auth0_mgmt_breaker()" in src
    # Used for both oauth/token and api/v2 routes
    assert "get_breaker(\n        'auth0_management'" in src or "'auth0_management'" in src


def test_auth0_admin_invalidates_token_cache_on_401():
    src = (REPO_ROOT / 'app' / 'services' / 'auth0_admin.py').read_text()
    assert 'response.status_code == 401' in src
    # The clear is called inside _mgmt_request, not only in the public helper
    assert 'clear_management_token_cache()' in src
    # And we log the event so operators can see token rotation in audit
    assert 'auth0_admin.token_invalidated_by_401' in src


def test_auth0_admin_no_longer_uses_raw_httpx_directly():
    """Both Auth0 HTTP call sites now route through the breaker primitives
    `_auth0_http_post` / `_auth0_http_request`."""
    src = (REPO_ROOT / 'app' / 'services' / 'auth0_admin.py').read_text()
    # The two primitives exist
    assert 'async def _auth0_http_post' in src
    assert 'async def _auth0_http_request' in src
    # And only those primitives instantiate the client (single httpx.AsyncClient construct)
    assert src.count('httpx.AsyncClient(timeout=') == 2  # post + request


def test_circuit_breaker_local_llm_opens_after_threshold():
    """Smoke: verify the Ollama breaker actually trips after N failures."""
    from app.services.circuit_breaker import CircuitOpenError, get_breaker, reset_registry

    reset_registry()
    breaker = get_breaker('local_llm', failure_threshold=2, cooldown_seconds=60)

    async def fail():
        raise RuntimeError('ollama down')

    async def run():
        with pytest.raises(RuntimeError):
            await breaker.call(fail)
        with pytest.raises(RuntimeError):
            await breaker.call(fail)
        # Third call must be rejected with CircuitOpenError, not RuntimeError
        with pytest.raises(CircuitOpenError):
            await breaker.call(fail)

    asyncio.new_event_loop().run_until_complete(run())
    reset_registry()
