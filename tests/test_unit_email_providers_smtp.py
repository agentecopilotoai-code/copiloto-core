"""Tests unitarios para `copiloto_core.email.providers.smtp`.

Mock aiosmtplib para validar el dispatch sin abrir conexiones reales.
"""
from __future__ import annotations

import asyncio
from unittest.mock import patch, AsyncMock

import pytest

from copiloto_core.email.providers.base import (
    EmailMessage,
    ProviderInvalidConfig,
    ProviderRejected,
    ProviderUnavailable,
)
from copiloto_core.email.providers.smtp import SMTPProvider


def _run(coro):
    return asyncio.run(coro)


def _msg():
    return EmailMessage(
        to_address='a@b.com',
        subject='hola',
        html='<p>hola</p>',
        text='hola',
        tags={'kind': 'test'},
    )


def _config(**override):
    return {
        'host': override.get('host', 'smtp.example.com'),
        'port': override.get('port', 587),
        'username': override.get('username', 'me'),
        'use_tls': override.get('use_tls', True),
    }


# ─── Constructor validation ───────────────────────────────────────────────


def test_smtp_constructor_rejects_remote_without_tls():
    with pytest.raises(ProviderInvalidConfig, match='use_tls=false'):
        SMTPProvider(
            provider_code='c', api_key='pw',
            config=_config(use_tls=False, host='smtp.example.com'),
            from_address='a@b.com', from_name='x',
        )


def test_smtp_constructor_allows_localhost_without_tls():
    SMTPProvider(
        provider_code='c', api_key='',
        config=_config(use_tls=False, host='localhost', port=2525),
        from_address='a@b.com', from_name='x',
    )


def test_smtp_constructor_rejects_remote_without_password():
    with pytest.raises(ProviderInvalidConfig, match='api_key'):
        SMTPProvider(
            provider_code='c', api_key='',
            config=_config(host='smtp.example.com'),
            from_address='a@b.com', from_name='x',
        )


def test_smtp_constructor_rejects_invalid_port():
    with pytest.raises(ProviderInvalidConfig):
        SMTPProvider(
            provider_code='c', api_key='pw',
            config={'host': 'h', 'port': 99999, 'username': 'u', 'use_tls': True},
            from_address='a@b.com', from_name='x',
        )


# ─── send() ───────────────────────────────────────────────────────────────


def test_smtp_send_success_calls_aiosmtplib():
    """Path feliz: aiosmtplib.send() devuelve sin levantar → ProviderResult.ok."""
    fake_send = AsyncMock(return_value=None)
    fake_aiosmtplib = type(
        'F', (),
        {
            'send': fake_send,
            'SMTPAuthenticationError': type('E1', (Exception,), {}),
            'SMTPRecipientsRefused': type('E2', (Exception,), {}),
            'SMTPSenderRefused': type('E3', (Exception,), {}),
            'SMTPException': type('E4', (Exception,), {}),
        },
    )
    with patch.dict('sys.modules', {'aiosmtplib': fake_aiosmtplib}):
        prov = SMTPProvider(
            provider_code='smtp-1', api_key='pw',
            config=_config(),
            from_address='from@x.com', from_name='X',
        )
        res = _run(prov.send(_msg()))
    assert res.success is True
    assert res.provider_code == 'smtp-1'
    # aiosmtplib.send fue llamado con kwargs esperados
    call_kwargs = fake_send.call_args.kwargs
    assert call_kwargs['hostname'] == 'smtp.example.com'
    assert call_kwargs['port'] == 587
    assert call_kwargs['username'] == 'me'
    assert call_kwargs['password'] == 'pw'
    assert call_kwargs['start_tls'] is True


def test_smtp_send_auth_error_raises_unavailable():
    auth_err = type('AuthErr', (Exception,), {})
    async def _fake_send(*a, **kw):
        raise auth_err('bad creds')
    fake_aiosmtplib = type(
        'F', (),
        {
            'send': _fake_send,
            'SMTPAuthenticationError': auth_err,
            'SMTPRecipientsRefused': type('E2', (Exception,), {}),
            'SMTPSenderRefused': type('E3', (Exception,), {}),
            'SMTPException': type('E4', (Exception,), {}),
        },
    )
    with patch.dict('sys.modules', {'aiosmtplib': fake_aiosmtplib}):
        prov = SMTPProvider(
            provider_code='c', api_key='pw', config=_config(),
            from_address='from@x.com', from_name='X',
        )
        with pytest.raises(ProviderUnavailable, match='auth failed'):
            _run(prov.send(_msg()))


def test_smtp_send_recipient_refused_raises_rejected():
    rec_err = type('RecErr', (Exception,), {})
    async def _fake_send(*a, **kw):
        raise rec_err('bad to addr')
    fake_aiosmtplib = type(
        'F', (),
        {
            'send': _fake_send,
            'SMTPAuthenticationError': type('E1', (Exception,), {}),
            'SMTPRecipientsRefused': rec_err,
            'SMTPSenderRefused': type('E3', (Exception,), {}),
            'SMTPException': type('E4', (Exception,), {}),
        },
    )
    with patch.dict('sys.modules', {'aiosmtplib': fake_aiosmtplib}):
        prov = SMTPProvider(
            provider_code='c', api_key='pw', config=_config(),
            from_address='from@x.com', from_name='X',
        )
        with pytest.raises(ProviderRejected, match='recipient'):
            _run(prov.send(_msg()))
