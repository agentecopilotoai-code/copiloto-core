"""Tests unitarios para `copiloto_core.email.providers.resend` (v2.0.0).

Mock httpx para validar el request format (URL, headers, body) y la
clasificación de errores (rate-limit, auth, server) en las excepciones
tipadas que el dispatcher inspecciona.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from copiloto_core.email.providers.base import (
    EmailMessage,
    ProviderInvalidConfig,
    ProviderRateLimited,
    ProviderRejected,
    ProviderResult,
    ProviderUnavailable,
)
from copiloto_core.email.providers.resend import ResendProvider


def _run(coro):
    return asyncio.run(coro)


def _msg(**overrides):
    return EmailMessage(
        to_address=overrides.get('to_address', 'a@b.com'),
        subject=overrides.get('subject', 'hola'),
        html=overrides.get('html', '<p>hola</p>'),
        text=overrides.get('text', 'hola'),
        tags=overrides.get('tags', {'kind': 'test'}),
    )


def _provider(api_key='re_xxx', from_addr='from@x.com', from_name='X'):
    return ResendProvider(
        provider_code='resend-main',
        api_key=api_key,
        config={},
        from_address=from_addr,
        from_name=from_name,
    )


# ─── Constructor validation ───────────────────────────────────────────────


def test_resend_constructor_rejects_empty_api_key():
    with pytest.raises(ProviderInvalidConfig, match='api_key'):
        ResendProvider(
            provider_code='c', api_key='', config={},
            from_address='a@b.com', from_name='x',
        )


def test_resend_constructor_rejects_empty_from_address():
    with pytest.raises(ProviderInvalidConfig, match='from_address'):
        ResendProvider(
            provider_code='c', api_key='re_x', config={},
            from_address='', from_name='x',
        )


def test_resend_constructor_rejects_unknown_config_keys():
    with pytest.raises(ProviderInvalidConfig):
        ResendProvider(
            provider_code='c', api_key='re_x', config={'unknown': 1},
            from_address='a@b.com', from_name='x',
        )


# ─── send() happy path ────────────────────────────────────────────────────


def test_resend_send_success_returns_message_id(monkeypatch):
    """Path feliz: 200 con body {id} → ProviderResult(success=True, message_id=...)."""
    captured: dict = {}

    async def _fake_post(url, headers=None, json=None):
        captured['url'] = url
        captured['headers'] = headers
        captured['json'] = json
        return SimpleNamespace(
            status_code=200,
            content=b'{"id":"msg-123"}',
            json=lambda: {'id': 'msg-123'},
            headers={},
            text='{"id":"msg-123"}',
        )

    client = SimpleNamespace(post=_fake_post)

    async def _get_client():
        return client

    monkeypatch.setattr(
        'copiloto_core.services.http_clients.get_resend_client',
        _get_client,
    )

    result = _run(_provider().send(_msg()))
    assert isinstance(result, ProviderResult)
    assert result.success is True
    assert result.message_id == 'msg-123'
    assert result.provider_code == 'resend-main'
    assert result.latency_ms >= 0
    # request validation
    assert captured['url'] == '/emails'
    assert captured['headers']['authorization'] == 'Bearer re_xxx'
    assert captured['headers']['content-type'] == 'application/json'
    body = captured['json']
    assert body['from'] == 'X <from@x.com>'
    assert body['to'] == ['a@b.com']
    assert body['subject'] == 'hola'
    assert body['html'] == '<p>hola</p>'
    assert body['text'] == 'hola'
    # tags → list of {name,value}
    assert body['tags'] == [{'name': 'kind', 'value': 'test'}]


def test_resend_send_without_from_name_uses_bare_address(monkeypatch):
    async def _fake_post(url, headers=None, json=None):
        return SimpleNamespace(
            status_code=200, content=b'{"id":"m"}',
            json=lambda: {'id': 'm'}, headers={}, text='',
        )
    monkeypatch.setattr(
        'copiloto_core.services.http_clients.get_resend_client',
        AsyncMock(return_value=SimpleNamespace(post=_fake_post)),
    )

    prov = _provider(from_name='')
    res = _run(prov.send(_msg()))
    assert res.success is True


# ─── send() error classification ──────────────────────────────────────────


def test_resend_429_raises_rate_limited_with_retry_after(monkeypatch):
    async def _fake_post(url, headers=None, json=None):
        return SimpleNamespace(
            status_code=429, content=b'too many',
            json=lambda: {}, headers={'retry-after': '30'}, text='too many',
        )
    monkeypatch.setattr(
        'copiloto_core.services.http_clients.get_resend_client',
        AsyncMock(return_value=SimpleNamespace(post=_fake_post)),
    )

    with pytest.raises(ProviderRateLimited) as exc:
        _run(_provider().send(_msg()))
    assert exc.value.retry_after == 30


def test_resend_400_raises_rejected(monkeypatch):
    async def _fake_post(url, headers=None, json=None):
        return SimpleNamespace(
            status_code=400, content=b'bad',
            json=lambda: {}, headers={}, text='Invalid to address',
        )
    monkeypatch.setattr(
        'copiloto_core.services.http_clients.get_resend_client',
        AsyncMock(return_value=SimpleNamespace(post=_fake_post)),
    )
    with pytest.raises(ProviderRejected):
        _run(_provider().send(_msg()))


def test_resend_401_raises_unavailable(monkeypatch):
    async def _fake_post(url, headers=None, json=None):
        return SimpleNamespace(
            status_code=401, content=b'', json=lambda: {}, headers={}, text='',
        )
    monkeypatch.setattr(
        'copiloto_core.services.http_clients.get_resend_client',
        AsyncMock(return_value=SimpleNamespace(post=_fake_post)),
    )
    with pytest.raises(ProviderUnavailable):
        _run(_provider().send(_msg()))


def test_resend_503_raises_unavailable(monkeypatch):
    async def _fake_post(url, headers=None, json=None):
        return SimpleNamespace(
            status_code=503, content=b'', json=lambda: {}, headers={}, text='down',
        )
    monkeypatch.setattr(
        'copiloto_core.services.http_clients.get_resend_client',
        AsyncMock(return_value=SimpleNamespace(post=_fake_post)),
    )
    with pytest.raises(ProviderUnavailable):
        _run(_provider().send(_msg()))


def test_resend_transport_error_raises_unavailable(monkeypatch):
    async def _fake_post(url, headers=None, json=None):
        raise httpx.ConnectError('boom')
    monkeypatch.setattr(
        'copiloto_core.services.http_clients.get_resend_client',
        AsyncMock(return_value=SimpleNamespace(post=_fake_post)),
    )
    with pytest.raises(ProviderUnavailable, match='transport'):
        _run(_provider().send(_msg()))
