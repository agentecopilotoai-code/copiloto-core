"""Tests unitarios para `copiloto_core.email.providers.sendgrid`.

Mock httpx (no SDK) — el adapter del core usa httpx directo.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from copiloto_core.email.providers.base import (
    EmailMessage,
    ProviderInvalidConfig,
    ProviderRateLimited,
    ProviderRejected,
    ProviderUnavailable,
)
from copiloto_core.email.providers.sendgrid import SendGridProvider


def _run(coro):
    return asyncio.run(coro)


def _msg(**kw):
    return EmailMessage(
        to_address=kw.get('to_address', 'a@b.com'),
        subject=kw.get('subject', 'hola'),
        html=kw.get('html', '<p>hola</p>'),
        text=kw.get('text', 'hola'),
        tags=kw.get('tags', {}),
    )


def _provider():
    return SendGridProvider(
        provider_code='sendgrid-main',
        api_key='SG.key',
        config={},
        from_address='from@x.com',
        from_name='X',
    )


class _FakeAsyncClient:
    """Stub que mimica `httpx.AsyncClient` como async-context-manager."""
    def __init__(self, *, base_url='', timeout=10.0, **_):
        self.base_url = base_url
        self.posts: list[dict] = []
        self._response = SimpleNamespace(
            status_code=200, content=b'', json=lambda: {},
            headers={}, text='',
        )

    def configure_response(self, *, status_code, body=b'', headers=None):
        self._response = SimpleNamespace(
            status_code=status_code,
            content=body,
            json=lambda: ({'id': 'i'} if body == b'' else {}),
            headers=headers or {},
            text=body.decode('utf-8', errors='ignore') if body else '',
        )

    def configure_error(self, exc):
        self._error = exc

    async def post(self, url, headers=None, json=None):
        self.posts.append({'url': url, 'headers': headers, 'json': json})
        if hasattr(self, '_error'):
            raise self._error
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


def _patch_with_fake(fake):
    return patch('httpx.AsyncClient', return_value=fake)


def test_sendgrid_constructor_rejects_empty_api_key():
    with pytest.raises(ProviderInvalidConfig):
        SendGridProvider(
            provider_code='c', api_key='', config={},
            from_address='a@b.com', from_name='x',
        )


def test_sendgrid_success_returns_message_id_from_header():
    fake = _FakeAsyncClient()
    fake.configure_response(status_code=202, headers={'x-message-id': 'sg-msg-99'})
    with _patch_with_fake(fake):
        res = _run(_provider().send(_msg()))
    assert res.success is True
    assert res.message_id == 'sg-msg-99'
    assert res.provider_code == 'sendgrid-main'


def test_sendgrid_429_rate_limited():
    fake = _FakeAsyncClient()
    fake.configure_response(status_code=429, body=b'too many', headers={'retry-after': '5'})
    with _patch_with_fake(fake):
        with pytest.raises(ProviderRateLimited) as exc:
            _run(_provider().send(_msg()))
    assert exc.value.retry_after == 5


def test_sendgrid_400_rejected():
    fake = _FakeAsyncClient()
    fake.configure_response(status_code=400, body=b'invalid email')
    with _patch_with_fake(fake):
        with pytest.raises(ProviderRejected):
            _run(_provider().send(_msg()))


def test_sendgrid_401_unavailable():
    fake = _FakeAsyncClient()
    fake.configure_response(status_code=401)
    with _patch_with_fake(fake):
        with pytest.raises(ProviderUnavailable):
            _run(_provider().send(_msg()))


def test_sendgrid_500_unavailable():
    fake = _FakeAsyncClient()
    fake.configure_response(status_code=503, body=b'down')
    with _patch_with_fake(fake):
        with pytest.raises(ProviderUnavailable):
            _run(_provider().send(_msg()))


def test_sendgrid_tags_become_categories():
    """SendGrid usa `categories` (no `tags`), serializadas como 'k:v'."""
    fake = _FakeAsyncClient()
    fake.configure_response(status_code=202, headers={'x-message-id': 'm'})
    with _patch_with_fake(fake):
        _run(_provider().send(_msg(tags={'kind': 'welcome', 'tenant': 'acme'})))

    captured = fake.posts[0]
    assert captured['url'] == '/v3/mail/send'
    assert 'categories' in captured['json']
    assert sorted(captured['json']['categories']) == ['kind:welcome', 'tenant:acme']
    # `from` con name
    assert captured['json']['from'] == {'email': 'from@x.com', 'name': 'X'}
    assert captured['json']['personalizations'][0]['to'] == [{'email': 'a@b.com'}]


def test_sendgrid_transport_error_unavailable():
    fake = _FakeAsyncClient()
    fake.configure_error(httpx.ConnectError('net down'))
    with _patch_with_fake(fake):
        with pytest.raises(ProviderUnavailable):
            _run(_provider().send(_msg()))
