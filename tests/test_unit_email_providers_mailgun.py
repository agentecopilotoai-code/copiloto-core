"""Tests unitarios para `copiloto_core.email.providers.mailgun`."""
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
from copiloto_core.email.providers.mailgun import MailgunProvider


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


def _provider(config=None):
    return MailgunProvider(
        provider_code='mailgun-main',
        api_key='mg-key',
        config=config or {'domain': 'mg.example.com', 'region': 'us'},
        from_address='from@x.com',
        from_name='X',
    )


class _FakeAsyncClient:
    def __init__(self, *, base_url='', timeout=10.0, **_):
        self.base_url = base_url
        self.posts: list[dict] = []
        self._response = SimpleNamespace(
            status_code=200, content=b'{"id":"mg-msg-1"}',
            json=lambda: {'id': 'mg-msg-1', 'message': 'Queued.'},
            headers={}, text='{"id":"mg-msg-1"}',
        )

    def configure_response(self, *, status_code, body=b'', headers=None):
        self._response = SimpleNamespace(
            status_code=status_code,
            content=body,
            json=lambda: ({} if not body else {'id': 'mg-x'}),
            headers=headers or {},
            text=body.decode('utf-8', errors='ignore') if body else '',
        )

    def configure_error(self, exc):
        self._error = exc

    async def post(self, url, auth=None, data=None):
        self.posts.append({'url': url, 'auth': auth, 'data': data})
        if hasattr(self, '_error'):
            raise self._error
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


def _patch_with_fake(fake):
    return patch('httpx.AsyncClient', return_value=fake)


def test_mailgun_constructor_requires_domain():
    with pytest.raises(ProviderInvalidConfig):
        MailgunProvider(
            provider_code='c', api_key='k', config={},
            from_address='a@b.com', from_name='x',
        )


def test_mailgun_eu_region_uses_eu_base_url():
    p = _provider({'domain': 'mg.eu.example.com', 'region': 'eu'})
    assert 'eu.mailgun.net' in p._base_url


def test_mailgun_us_region_default():
    p = _provider()
    assert 'api.mailgun.net' in p._base_url


def test_mailgun_success_returns_message_id():
    fake = _FakeAsyncClient()
    fake.configure_response(status_code=200, body=b'{"id":"mg-msg-1","message":"Queued."}')
    # restablecemos json() para devolver el id correcto en este caso
    fake._response = SimpleNamespace(
        status_code=200, content=b'{"id":"mg-msg-1"}',
        json=lambda: {'id': 'mg-msg-1', 'message': 'Queued.'},
        headers={}, text='{"id":"mg-msg-1"}',
    )
    with _patch_with_fake(fake):
        res = _run(_provider().send(_msg()))
    assert res.success is True
    assert res.message_id == 'mg-msg-1'


def test_mailgun_429_rate_limited():
    fake = _FakeAsyncClient()
    fake.configure_response(status_code=429, body=b'too many', headers={'retry-after': '2'})
    with _patch_with_fake(fake):
        with pytest.raises(ProviderRateLimited):
            _run(_provider().send(_msg()))


def test_mailgun_404_rejected_domain_not_found():
    fake = _FakeAsyncClient()
    fake.configure_response(status_code=404)
    with _patch_with_fake(fake):
        with pytest.raises(ProviderRejected, match='domain not found'):
            _run(_provider().send(_msg()))


def test_mailgun_401_unavailable():
    fake = _FakeAsyncClient()
    fake.configure_response(status_code=401)
    with _patch_with_fake(fake):
        with pytest.raises(ProviderUnavailable):
            _run(_provider().send(_msg()))


def test_mailgun_500_unavailable():
    fake = _FakeAsyncClient()
    fake.configure_response(status_code=503, body=b'down')
    with _patch_with_fake(fake):
        with pytest.raises(ProviderUnavailable):
            _run(_provider().send(_msg()))


def test_mailgun_form_data_includes_tags():
    fake = _FakeAsyncClient()
    with _patch_with_fake(fake):
        _run(_provider().send(_msg(tags={'kind': 'welcome'})))

    captured = fake.posts[0]
    # url incluye el domain
    assert '/v3/mg.example.com/messages' in captured['url']
    # auth básico api:<key>
    assert captured['auth'] == ('api', 'mg-key')
    # form data como list de tuples
    data = captured['data']
    keys = [k for k, _ in data]
    assert 'from' in keys
    assert 'to' in keys
    assert 'subject' in keys
    assert 'html' in keys
    assert 'text' in keys
    # o:tag entry para los tags
    assert any(k == 'o:tag' and v == 'kind:welcome' for k, v in data)
