"""Pure tests for `app/services/rate_limit.py`."""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import pytest


# ═════════════════════════════════════════════════════════════════════════
# TokenBucket
# ═════════════════════════════════════════════════════════════════════════


def test_token_bucket_starts_full():
    from app.services.rate_limit import TokenBucket
    bucket = TokenBucket(capacity=10, refill_per_second=1)
    assert bucket.tokens == 10.0


def test_token_bucket_consume_allowed():
    from app.services.rate_limit import TokenBucket
    bucket = TokenBucket(capacity=10, refill_per_second=1)
    allowed, retry_after = bucket.consume(5)
    assert allowed is True
    assert retry_after == 0.0
    assert bucket.tokens == 5.0


def test_token_bucket_consume_blocked():
    from app.services.rate_limit import TokenBucket
    bucket = TokenBucket(capacity=10, refill_per_second=1)
    bucket.tokens = 2.0  # less than amount
    allowed, retry_after = bucket.consume(5)
    assert allowed is False
    assert retry_after > 0  # ~3 seconds at 1 token/sec


def test_token_bucket_refills_over_time():
    from app.services.rate_limit import TokenBucket
    bucket = TokenBucket(capacity=10, refill_per_second=10)
    bucket.tokens = 0.0
    bucket.last_refill = time.monotonic() - 0.5  # simulate 500ms ago
    allowed, _ = bucket.consume(1)
    # 0.5s * 10 tokens/sec = 5 tokens accumulated → can consume 1
    assert allowed is True


def test_token_bucket_caps_refill_at_capacity():
    from app.services.rate_limit import TokenBucket
    bucket = TokenBucket(capacity=10, refill_per_second=100)
    bucket.tokens = 5.0
    bucket.last_refill = time.monotonic() - 100.0  # 100s ago, would refill 10000 tokens
    bucket.consume(0)  # trigger refill calc
    assert bucket.tokens == 10.0  # capped


def test_token_bucket_zero_refill_uses_60_second_retry():
    from app.services.rate_limit import TokenBucket
    bucket = TokenBucket(capacity=10, refill_per_second=0)
    bucket.tokens = 0.0
    allowed, retry_after = bucket.consume(1)
    assert allowed is False
    assert retry_after == 60.0


# ═════════════════════════════════════════════════════════════════════════
# RateLimiter
# ═════════════════════════════════════════════════════════════════════════


def test_rate_limiter_invalid_config_raises():
    from app.services.rate_limit import RateLimiter
    with pytest.raises(ValueError):
        RateLimiter(default_per_minute=0, webhook_per_minute=60)
    with pytest.raises(ValueError):
        RateLimiter(default_per_minute=60, webhook_per_minute=-1)
    with pytest.raises(ValueError):
        RateLimiter(default_per_minute=60, webhook_per_minute=60, max_entries=0)
    with pytest.raises(ValueError):
        RateLimiter(default_per_minute=60, webhook_per_minute=60, ttl_seconds=0)


def test_rate_limiter_check_first_request_allowed():
    from app.services.rate_limit import RateLimiter
    limiter = RateLimiter(default_per_minute=60, webhook_per_minute=120)

    async def _go():
        return await limiter.check('1.2.3.4:-', scope='default')

    allowed, retry = asyncio.run(_go())
    assert allowed is True
    assert retry == 0.0


def test_rate_limiter_check_burst_blocks():
    from app.services.rate_limit import RateLimiter
    limiter = RateLimiter(default_per_minute=5, webhook_per_minute=5)

    async def _go():
        results = []
        for _ in range(10):
            results.append(await limiter.check('ip:-', scope='default'))
        return results

    out = asyncio.run(_go())
    # First 5 allowed, rest blocked
    assert all(r[0] for r in out[:5])
    assert not all(r[0] for r in out[5:])


def test_rate_limiter_webhook_uses_higher_cap():
    from app.services.rate_limit import RateLimiter
    limiter = RateLimiter(default_per_minute=2, webhook_per_minute=10)

    async def _go():
        results = []
        for _ in range(5):
            results.append(await limiter.check('ip:-', scope='webhook'))
        return results

    out = asyncio.run(_go())
    # All 5 allowed via webhook scope's higher cap
    assert all(r[0] for r in out)


def test_rate_limiter_size_property():
    from app.services.rate_limit import RateLimiter
    limiter = RateLimiter(default_per_minute=60, webhook_per_minute=60)
    assert limiter.size == 0

    async def _go():
        await limiter.check('a:-', scope='default')
        await limiter.check('b:-', scope='default')

    asyncio.run(_go())
    assert limiter.size == 2


def test_rate_limiter_evicts_when_cap_exceeded():
    """When more keys than max_entries, oldest are evicted (LRU)."""
    from app.services.rate_limit import RateLimiter
    limiter = RateLimiter(
        default_per_minute=60, webhook_per_minute=60, max_entries=3,
    )

    async def _go():
        for i in range(6):
            await limiter.check(f'ip{i}:-', scope='default')

    asyncio.run(_go())
    # Cap enforced
    assert limiter.size <= 3


def test_rate_limiter_ttl_expires_on_same_key():
    """TTL eviction triggers when the SAME key is rechecked after expiring."""
    from app.services.rate_limit import RateLimiter
    limiter = RateLimiter(
        default_per_minute=60, webhook_per_minute=60, ttl_seconds=1,
    )

    async def _go_initial():
        await limiter.check('cold:-', scope='default')

    asyncio.run(_go_initial())
    assert limiter.size == 1
    first_bucket = limiter._buckets['cold:-']

    # Age it past TTL
    first_bucket.last_refill = time.monotonic() - 2  # > ttl_seconds

    async def _go_again():
        await limiter.check('cold:-', scope='default')

    asyncio.run(_go_again())
    # Bucket was discarded and recreated (new instance)
    new_bucket = limiter._buckets['cold:-']
    assert new_bucket is not first_bucket


# ═════════════════════════════════════════════════════════════════════════
# classify_scope + build_rate_limit_key + extract_client_ip
# ═════════════════════════════════════════════════════════════════════════


def test_classify_scope_webhook_prefix():
    from app.services.rate_limit import classify_scope
    assert classify_scope('/webhooks/inbound/123') == 'webhook'
    assert classify_scope('/v1/tenants') == 'default'


def test_build_rate_limit_key_with_tenant():
    from app.services.rate_limit import build_rate_limit_key
    tid = '11111111-1111-1111-1111-111111111111'
    key = build_rate_limit_key(
        client_ip='1.2.3.4',
        path=f'/v1/tenants/{tid}/settings',
    )
    assert key == f'1.2.3.4:{tid}'


def test_build_rate_limit_key_without_tenant():
    from app.services.rate_limit import build_rate_limit_key
    key = build_rate_limit_key(client_ip='1.2.3.4', path='/v1/health')
    assert key == '1.2.3.4:-'


def test_extract_client_ip_uses_peer_when_trust_xff_false(monkeypatch):
    from app.services import rate_limit
    monkeypatch.setattr(rate_limit, 'get_settings', lambda: SimpleNamespace(
        trust_proxy_forwarded_for=False,
    ))
    request = SimpleNamespace(
        headers={'x-forwarded-for': '99.99.99.99'},
        client=SimpleNamespace(host='1.2.3.4'),
    )
    assert rate_limit.extract_client_ip(request) == '1.2.3.4'


def test_extract_client_ip_uses_xff_when_trust_enabled(monkeypatch):
    from app.services import rate_limit
    monkeypatch.setattr(rate_limit, 'get_settings', lambda: SimpleNamespace(
        trust_proxy_forwarded_for=True,
    ))
    request = SimpleNamespace(
        headers={'x-forwarded-for': '99.99.99.99, 10.0.0.1'},
        client=SimpleNamespace(host='1.2.3.4'),
    )
    assert rate_limit.extract_client_ip(request) == '99.99.99.99'


def test_extract_client_ip_fallback_unknown(monkeypatch):
    from app.services import rate_limit
    monkeypatch.setattr(rate_limit, 'get_settings', lambda: SimpleNamespace(
        trust_proxy_forwarded_for=False,
    ))
    request = SimpleNamespace(headers={}, client=None)
    assert rate_limit.extract_client_ip(request) == 'unknown'


def test_extract_client_ip_fails_safe_when_settings_raises(monkeypatch):
    """If get_settings() throws, we default to trust_xff=False."""
    from app.services import rate_limit

    def _fail():
        raise RuntimeError('config broken')

    monkeypatch.setattr(rate_limit, 'get_settings', _fail)
    request = SimpleNamespace(
        headers={'x-forwarded-for': '1.1.1.1'},
        client=SimpleNamespace(host='2.2.2.2'),
    )
    # Falls back to peer IP (not the spoofable XFF)
    assert rate_limit.extract_client_ip(request) == '2.2.2.2'
