"""Tests para `copiloto_core.email.EmailDispatcher`.

Mock de la conn asyncpg + factory para validar:
- fallback chain on Unavailable/RateLimited.
- short-circuit on InvalidConfig/Rejected.
- no_providers_configured → ProviderResult(success=False).
- audit insert por cada attempt.
"""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from copiloto_core.email import EmailDispatcher, EmailMessage
from copiloto_core.email.providers.base import (
    ProviderInvalidConfig,
    ProviderRejected,
    ProviderResult,
    ProviderUnavailable,
)


def _run(coro):
    return asyncio.run(coro)


class _FakeConn:
    """asyncpg.Connection stub que registra los fetchs y executes."""
    def __init__(self, rows):
        self._rows = rows
        self.executed: list[tuple] = []

    @asynccontextmanager
    async def transaction(self):
        yield

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return ''

    async def fetch(self, sql, *args):
        return list(self._rows)


def _msg():
    return EmailMessage(
        to_address='a@b.com',
        subject='hola',
        html='<p>x</p>',
        text='x',
    )


def _ok_provider(code='resend-main'):
    p = AsyncMock()
    p.send = AsyncMock(return_value=ProviderResult(
        success=True,
        message_id='m-1',
        provider_code=code,
        latency_ms=42.0,
    ))
    return p


def _fail_provider(exc):
    p = AsyncMock()
    p.send = AsyncMock(side_effect=exc)
    return p


def _row(idx, code='p1', is_active=True, priority=10):
    return {
        'id': f'00000000-0000-0000-0000-00000000000{idx}',
        'code': code,
        'provider_type': 'resend',
        'name': 'N',
        'config_jsonb': {},
        'api_key_ciphertext': 'cipher',
        'from_address_override': None,
        'from_name_override': None,
        'is_active': is_active,
        'priority': priority,
    }


def test_no_providers_configured_returns_failure():
    conn = _FakeConn(rows=[])
    dispatcher = EmailDispatcher()
    result = _run(dispatcher.send(conn, _msg(), support_mode=False))
    assert result.success is False
    assert result.error == 'no_providers_configured'


def test_first_provider_success_returns_immediately(monkeypatch):
    conn = _FakeConn(rows=[_row(1, code='resend-main')])

    factory = lambda row, **kw: _ok_provider(row['code'])
    monkeypatch.setattr(
        'copiloto_core.email.dispatcher.make_email_provider', factory,
    )
    dispatcher = EmailDispatcher(
        fallback_from_address='g@x.com', fallback_from_name='G',
    )
    result = _run(dispatcher.send(conn, _msg(), support_mode=False))
    assert result.success is True
    assert result.provider_code == 'resend-main'
    # audit: 1 insert (status sent)
    insert_count = sum(
        1 for sql, _ in conn.executed if 'insert into app.email_dispatch_log' in sql
    )
    assert insert_count == 1


def test_unavailable_falls_back_to_next(monkeypatch):
    conn = _FakeConn(rows=[
        _row(1, code='resend-main', priority=10),
        _row(2, code='sendgrid-backup', priority=20),
    ])

    def _factory(row, **kw):
        if row['code'] == 'resend-main':
            return _fail_provider(ProviderUnavailable('down'))
        return _ok_provider('sendgrid-backup')

    monkeypatch.setattr(
        'copiloto_core.email.dispatcher.make_email_provider', _factory,
    )
    dispatcher = EmailDispatcher(
        fallback_from_address='g@x.com', fallback_from_name='G',
    )
    result = _run(dispatcher.send(conn, _msg(), support_mode=False))
    assert result.success is True
    assert result.provider_code == 'sendgrid-backup'
    # audit: 2 inserts (retried + sent)
    insert_count = sum(
        1 for sql, _ in conn.executed if 'insert into app.email_dispatch_log' in sql
    )
    assert insert_count == 2


def test_rejected_does_not_fall_back(monkeypatch):
    conn = _FakeConn(rows=[
        _row(1, code='primary', priority=10),
        _row(2, code='backup', priority=20),
    ])

    def _factory(row, **kw):
        if row['code'] == 'primary':
            return _fail_provider(ProviderRejected('bad to'))
        # Backup nunca debería ser llamado.
        raise AssertionError('backup should not be called')

    monkeypatch.setattr(
        'copiloto_core.email.dispatcher.make_email_provider', _factory,
    )
    dispatcher = EmailDispatcher(
        fallback_from_address='g@x.com', fallback_from_name='G',
    )
    result = _run(dispatcher.send(conn, _msg(), support_mode=False))
    assert result.success is False
    assert 'ProviderRejected' in (result.error or '')
    assert result.provider_code == 'primary'


def test_invalid_config_does_not_fall_back(monkeypatch):
    conn = _FakeConn(rows=[
        _row(1, code='primary', priority=10),
        _row(2, code='backup', priority=20),
    ])

    def _factory(row, **kw):
        if row['code'] == 'primary':
            raise ProviderInvalidConfig('bad cfg')
        raise AssertionError('backup should not be called')

    monkeypatch.setattr(
        'copiloto_core.email.dispatcher.make_email_provider', _factory,
    )
    dispatcher = EmailDispatcher(
        fallback_from_address='g@x.com', fallback_from_name='G',
    )
    result = _run(dispatcher.send(conn, _msg(), support_mode=False))
    assert result.success is False
    assert 'ProviderInvalidConfig' in (result.error or '')


def test_all_providers_unavailable_returns_failure(monkeypatch):
    conn = _FakeConn(rows=[
        _row(1, code='a'), _row(2, code='b'),
    ])

    def _factory(row, **kw):
        return _fail_provider(ProviderUnavailable(f'{row["code"]} down'))

    monkeypatch.setattr(
        'copiloto_core.email.dispatcher.make_email_provider', _factory,
    )
    dispatcher = EmailDispatcher(
        fallback_from_address='g@x.com', fallback_from_name='G',
    )
    result = _run(dispatcher.send(conn, _msg(), support_mode=False))
    assert result.success is False
    assert 'b down' in (result.error or '') or 'a down' in (result.error or '')
    # 2 audit rows (both retried)
    insert_count = sum(
        1 for sql, _ in conn.executed if 'insert into app.email_dispatch_log' in sql
    )
    assert insert_count == 2
