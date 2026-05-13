"""Static tests for TASK-0059 — Rate limiting + circuit breaker.

Coverage (≥12 tests):
1.  Token bucket allows up to `capacity` requests, then blocks.
2.  Bucket refill restores capacity over time.
3.  `extract_client_ip` honors X-Forwarded-For first hop.
4.  `extract_client_ip` falls back to `request.client.host`.
5.  `classify_scope` routes /webhooks/whatsapp to webhook scope.
6.  `build_rate_limit_key` includes tenant_id when in path.
7.  `RateLimiter.build_bucket(scope='webhook')` uses webhook capacity.
8.  Rate-limit middleware returns 429 with Retry-After when bucket empty.
9.  `app.main.create_app` registers the rate-limit middleware.
10. Circuit breaker transitions closed → open after N consecutive failures.
11. Circuit breaker after cooldown enters half_open and a successful call
    resets it to closed.
12. Circuit breaker probe failure in half_open re-opens the circuit.
13. `cloud_llm_answer._call_provider` wraps providers in a named breaker.
14. `payment_provider.generate_payment_link` routes through a payment breaker.
15. `get_breaker` returns the same instance for the same name.
"""

from __future__ import annotations

import asyncio
import inspect
import time
from pathlib import Path

import pytest

from app.services import circuit_breaker as cb_module
from app.services import cloud_llm_answer as cloud_llm_module
from app.services import payment_provider as payment_module
from app.services import rate_limit as rl_module
from app.services.circuit_breaker import (
    CLOSED,
    HALF_OPEN,
    OPEN,
    CircuitBreaker,
    CircuitOpenError,
    get_breaker,
    reset_registry,
)
from app.services.rate_limit import (
    RateLimiter,
    TokenBucket,
    build_rate_limit_key,
    build_rate_limit_middleware,
    classify_scope,
    extract_client_ip,
)


# ───── Token bucket ────────────────────────────────────────────────────────


def test_token_bucket_allows_up_to_capacity_then_blocks():
    bucket = TokenBucket(capacity=3.0, refill_per_second=0.0)
    bucket.last_refill = time.monotonic()
    bucket.tokens = 3.0
    assert bucket.consume()[0] is True
    assert bucket.consume()[0] is True
    assert bucket.consume()[0] is True
    allowed, retry = bucket.consume()
    assert allowed is False
    assert retry > 0


def test_token_bucket_refills_over_time():
    bucket = TokenBucket(capacity=2.0, refill_per_second=10.0)
    bucket.tokens = 0.0
    # Force a refill by rewinding last_refill 1s into the past.
    bucket.last_refill = time.monotonic() - 1.0
    allowed, _ = bucket.consume()
    assert allowed is True  # refilled ~10 tokens, capped at 2 → consumed 1


# ───── Helpers ────────────────────────────────────────────────────────────


class _FakeRequest:
    def __init__(self, *, headers=None, client_host='1.2.3.4'):
        self.headers = headers or {}
        client = type('C', (), {'host': client_host})()
        self.client = client


def test_extract_client_ip_uses_x_forwarded_for_first_hop():
    req = _FakeRequest(headers={'x-forwarded-for': '8.8.8.8, 10.0.0.1'})
    assert extract_client_ip(req) == '8.8.8.8'


def test_extract_client_ip_falls_back_to_request_client():
    req = _FakeRequest(headers={}, client_host='9.9.9.9')
    assert extract_client_ip(req) == '9.9.9.9'


def test_classify_scope_routes_meta_webhook_separately():
    assert classify_scope('/webhooks/whatsapp/abc-123') == 'webhook'
    assert classify_scope('/v1/contacts') == 'default'


def test_build_rate_limit_key_includes_tenant_id():
    tenant = '11111111-2222-3333-4444-555555555555'
    key = build_rate_limit_key(client_ip='1.1.1.1', path=f'/v1/tenants/{tenant}/contacts')
    assert tenant in key
    assert '1.1.1.1' in key


def test_rate_limiter_webhook_scope_uses_webhook_capacity():
    limiter = RateLimiter(default_per_minute=60, webhook_per_minute=600)
    bucket = limiter.build_bucket(scope='webhook')
    assert bucket.capacity == 600
    default_bucket = limiter.build_bucket(scope='default')
    assert default_bucket.capacity == 60


# ───── Middleware ─────────────────────────────────────────────────────────


def test_rate_limit_middleware_returns_429_when_bucket_empty():
    limiter = RateLimiter(default_per_minute=1, webhook_per_minute=1)
    middleware = build_rate_limit_middleware(limiter)

    async def call_next(_request):
        return type('R', (), {'status_code': 200, 'headers': {}})()

    req = _FakeRequest()
    req.url = type('U', (), {'path': '/v1/anything'})()

    async def run():
        first = await middleware(req, call_next)
        second = await middleware(req, call_next)
        return first, second

    first, second = asyncio.new_event_loop().run_until_complete(run())
    assert first.status_code == 200
    assert second.status_code == 429
    assert 'retry-after' in {k.lower() for k in second.headers.keys()}


def test_main_create_app_registers_rate_limit_middleware():
    main_source = Path('app/main.py').read_text(encoding='utf-8')
    assert 'build_rate_limit_middleware' in main_source
    assert 'RateLimiter' in main_source


# ───── Circuit breaker ────────────────────────────────────────────────────


def test_circuit_breaker_opens_after_threshold():
    breaker = CircuitBreaker(name='t', failure_threshold=3, cooldown_seconds=30.0)

    async def boom():
        raise RuntimeError('fail')

    async def run():
        for _ in range(3):
            with pytest.raises(RuntimeError):
                await breaker.call(boom)

    asyncio.new_event_loop().run_until_complete(run())
    assert breaker._state == OPEN
    # Next call rejected without invoking the function.
    with pytest.raises(CircuitOpenError) as exc_info:
        asyncio.new_event_loop().run_until_complete(breaker.call(boom))
    assert exc_info.value.name == 't'


def test_circuit_breaker_half_open_then_closed_on_success():
    breaker = CircuitBreaker(name='t2', failure_threshold=2, cooldown_seconds=0.05)

    async def boom():
        raise RuntimeError('x')

    async def ok():
        return 'ok'

    async def run():
        with pytest.raises(RuntimeError):
            await breaker.call(boom)
        with pytest.raises(RuntimeError):
            await breaker.call(boom)
        # Sleep past cooldown so state becomes half_open.
        await asyncio.sleep(0.08)
        assert breaker.state == HALF_OPEN
        result = await breaker.call(ok)
        return result

    res = asyncio.new_event_loop().run_until_complete(run())
    assert res == 'ok'
    assert breaker._state == CLOSED


def test_circuit_breaker_half_open_probe_failure_reopens():
    breaker = CircuitBreaker(name='t3', failure_threshold=2, cooldown_seconds=0.05)

    async def boom():
        raise RuntimeError('x')

    async def run():
        with pytest.raises(RuntimeError):
            await breaker.call(boom)
        with pytest.raises(RuntimeError):
            await breaker.call(boom)
        await asyncio.sleep(0.08)
        # Probe still fails → must reopen.
        with pytest.raises(RuntimeError):
            await breaker.call(boom)

    asyncio.new_event_loop().run_until_complete(run())
    assert breaker._state == OPEN


def test_get_breaker_is_idempotent_per_name():
    reset_registry()
    a = get_breaker('cloud_llm:claude')
    b = get_breaker('cloud_llm:claude')
    assert a is b


# ───── Integration ────────────────────────────────────────────────────────


def test_cloud_llm_call_provider_uses_named_breakers():
    source = inspect.getsource(cloud_llm_module)
    assert 'get_breaker' in source
    assert "f'cloud_llm:{provider}'" in source
    call_provider_src = inspect.getsource(cloud_llm_module._call_provider)
    assert "_breaker_for('claude')" in call_provider_src
    assert "_breaker_for('openai')" in call_provider_src


def test_payment_provider_wraps_calls_in_breaker():
    source = inspect.getsource(payment_module.generate_payment_link)
    assert '_payment_breaker' in source
    helpers = inspect.getsource(payment_module._payment_breaker)
    assert "f'payment:{provider}'" in helpers


def test_settings_expose_rate_and_breaker_knobs():
    from app.core.config import Settings  # noqa: PLC0415

    field_names = set(Settings.model_fields.keys())
    for name in (
        'rate_limit_per_min',
        'rate_limit_webhook_per_min',
        'circuit_breaker_failure_threshold',
        'circuit_breaker_cooldown_seconds',
    ):
        assert name in field_names, f'missing setting: {name}'


def test_circuit_breaker_module_has_three_states():
    # Sanity guard so renames don't silently break the integration layer.
    assert {CLOSED, OPEN, HALF_OPEN} == {'closed', 'open', 'half_open'}


def test_rate_limit_module_lives_in_services_package():
    path = Path(rl_module.__file__)
    assert path.parts[-2] == 'services'
    cb_path = Path(cb_module.__file__)
    assert cb_path.parts[-2] == 'services'
