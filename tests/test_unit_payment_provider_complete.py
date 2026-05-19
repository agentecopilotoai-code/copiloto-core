"""Completeness tests for payment_provider — covers _payment_breaker
fallback (config exception), MP success_url/notification_url branches,
MP/Stripe API error responses + missing-fields branches, and the BUG-201
freshness check rejecting non-integer ts.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from app.services.payment_provider import (
    PaymentProviderError,
    _payment_breaker,
    generate_payment_link,
    verify_mercadopago_signature,
    verify_stripe_signature,
)


def _mock_transport(handler):
    return httpx.MockTransport(handler)


# ── Lines 42-43: _payment_breaker config exception fallback ────────────────


def test_payment_breaker_falls_back_when_settings_unavailable(monkeypatch):
    import app.services.payment_provider as mod

    def boom():
        raise RuntimeError('no settings')

    monkeypatch.setattr(mod, 'get_settings', boom)
    breaker = _payment_breaker('mercadopago')
    assert breaker is not None  # falls back to default threshold/cooldown


# ── Lines 132: defensive raise for missing provider implementation ─────────


def test_generate_payment_link_unknown_after_validation(monkeypatch):
    """Force the `Provider not implemented` branch by mocking normalize to
    return a provider not handled in the if-tree."""
    import app.services.payment_provider as mod

    monkeypatch.setattr(mod, 'normalize_provider', lambda v: 'paypal')

    async def runner():
        with pytest.raises(PaymentProviderError, match='not implemented'):
            await generate_payment_link('paypal', 'k', 100, 'COP', 'd', 'r')

    asyncio.run(runner())


# ── Lines 158, 160-161: MP optional notification_url + success_url branches


def test_mercadopago_includes_optional_urls():
    captured = {}

    def handler(request):
        captured['body'] = __import__('json').loads(request.content.decode())
        return httpx.Response(200, json={'id': 'p', 'init_point': 'https://mp.example/p'})

    async def runner():
        await generate_payment_link(
            'mercadopago', 'k', 100, 'COP', 'd', 'r',
            notification_url='https://t.example/notify',
            success_url='https://t.example/ok',
            transport=_mock_transport(handler),
        )

    asyncio.run(runner())
    body = captured['body']
    assert body['notification_url'] == 'https://t.example/notify'
    assert body['back_urls']['success'] == 'https://t.example/ok'
    assert body['auto_return'] == 'approved'


# ── Lines 172, 178: MP error response + missing init_point ─────────────────


def test_mercadopago_propagates_4xx_error():
    def handler(_req):
        return httpx.Response(401, text='unauthorized')

    async def runner():
        with pytest.raises(PaymentProviderError, match='MercadoPago error'):
            await generate_payment_link(
                'mercadopago', 'bad', 100, 'COP', 'd', 'r',
                transport=_mock_transport(handler),
            )

    asyncio.run(runner())


def test_mercadopago_missing_init_point():
    def handler(_req):
        return httpx.Response(201, json={'id': 'p'})  # no init_point/sandbox_init_point

    async def runner():
        with pytest.raises(PaymentProviderError, match='missing init_point'):
            await generate_payment_link(
                'mercadopago', 'k', 100, 'COP', 'd', 'r',
                transport=_mock_transport(handler),
            )

    asyncio.run(runner())


# ── Line 213: Stripe price response missing id ─────────────────────────────


def test_stripe_price_missing_id():
    def handler(req):
        if req.url.path.endswith('/prices'):
            return httpx.Response(200, json={})  # no id
        return httpx.Response(200, json={'id': 'pl', 'url': 'https://x'})

    async def runner():
        with pytest.raises(PaymentProviderError, match='price response missing id'):
            await generate_payment_link(
                'stripe', 'k', 100, 'USD', 'd', 'r',
                transport=_mock_transport(handler),
            )

    asyncio.run(runner())


# ── Line 227: Stripe payment_link 4xx response ─────────────────────────────


def test_stripe_payment_link_error():
    def handler(req):
        if req.url.path.endswith('/prices'):
            return httpx.Response(200, json={'id': 'price_abc'})
        return httpx.Response(403, text='blocked')

    async def runner():
        with pytest.raises(PaymentProviderError, match='payment_link error'):
            await generate_payment_link(
                'stripe', 'k', 100, 'USD', 'd', 'r',
                transport=_mock_transport(handler),
            )

    asyncio.run(runner())


# ── Line 234: Stripe payment_link response missing url/id ─────────────────


def test_stripe_payment_link_missing_url_or_id():
    def handler(req):
        if req.url.path.endswith('/prices'):
            return httpx.Response(200, json={'id': 'price_abc'})
        return httpx.Response(200, json={'id': 'pl'})  # missing url

    async def runner():
        with pytest.raises(PaymentProviderError, match='missing url/id'):
            await generate_payment_link(
                'stripe', 'k', 100, 'USD', 'd', 'r',
                transport=_mock_transport(handler),
            )

    asyncio.run(runner())


# ── Lines 284-285: MP verify rejects non-int ts when freshness required ────


def test_mercadopago_signature_rejects_nonint_ts_when_freshness_required():
    # ts is present but malformed — when caller supplies now_ts, fail-closed
    assert verify_mercadopago_signature(
        b'{}', 'ts=notanumber,v1=deadbeef', 'secret', now_ts=1700000000,
    ) is False


# ── Lines 327-328: Stripe verify rejects non-int ts ────────────────────────


def test_stripe_signature_rejects_nonint_ts():
    assert verify_stripe_signature(
        b'{}', 't=notanumber,v1=deadbeef', 'secret', now_ts=1700000000,
    ) is False


# ── Line 297: MP verify falls through when no manifest matches ─────────────


def test_mercadopago_signature_no_match_returns_false():
    # All fields populated so first manifest candidate is built, but
    # the v1 hex is wrong → both manifests fail → return False at line 297.
    assert verify_mercadopago_signature(
        b'{"x":1}', 'ts=1700000000,v1=deadbeefdeadbeef', 'secret',
        request_id='req-1', data_id='data-1', now_ts=1700000000,
    ) is False
