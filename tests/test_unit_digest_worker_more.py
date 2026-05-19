"""Mocked-conn tests for digest_worker async helpers and dispatch flow."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4


class _FakeConn:
    """Tiny asyncpg.Connection stand-in."""
    def __init__(self, *, fetch_results=None, fetchrow_results=None, fetchval_results=None):
        self._fetch = list(fetch_results or [])
        self._fetchrow = list(fetchrow_results or [])
        self._fetchval = list(fetchval_results or [])
        self.executed = []

    async def fetch(self, sql, *args):
        return self._fetch.pop(0) if self._fetch else []

    async def fetchrow(self, sql, *args):
        return self._fetchrow.pop(0) if self._fetchrow else None

    async def fetchval(self, sql, *args):
        return self._fetchval.pop(0) if self._fetchval else None

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


# ───── _ensure_internal_digest_conversation ──────────────────────────────


def test_ensure_internal_digest_conversation_reuses_existing():
    from app.workers.digest_worker import _ensure_internal_digest_conversation
    existing_conv = uuid4()
    contact_id = uuid4()
    conn = _FakeConn(fetchval_results=[contact_id, existing_conv])

    async def _go():
        return await _ensure_internal_digest_conversation(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            recipient_phone='+5730099887766',
        )

    out = asyncio.run(_go())
    assert out == existing_conv


def test_ensure_internal_digest_conversation_creates_new():
    """When no conversation exists, inserts and returns the new id."""
    from app.workers.digest_worker import _ensure_internal_digest_conversation
    contact_id = uuid4()
    new_conv = uuid4()
    conn = _FakeConn(fetchval_results=[contact_id, None, new_conv])

    async def _go():
        return await _ensure_internal_digest_conversation(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            recipient_phone='+5730099887766',
        )

    out = asyncio.run(_go())
    assert out == new_conv


# ───── _queue_whatsapp_template ──────────────────────────────────────────


def test_queue_whatsapp_template_no_channel_returns_false():
    from app.workers.digest_worker import _queue_whatsapp_template
    conn = _FakeConn(fetchval_results=[None])  # no channel found

    async def _go():
        return await _queue_whatsapp_template(
            conn,
            tenant_id=uuid4(),
            recipient='+5730099',
            cadence='daily',
            components=[],
        )

    assert asyncio.run(_go()) is False


def test_queue_whatsapp_template_with_channel_inserts_message():
    from app.workers.digest_worker import _queue_whatsapp_template
    channel_id = uuid4()
    contact_id = uuid4()
    conv_id = uuid4()
    message_id = uuid4()
    conn = _FakeConn(
        fetchval_results=[channel_id, contact_id, conv_id],
        fetchrow_results=[{'id': message_id}],
    )

    async def _go():
        return await _queue_whatsapp_template(
            conn,
            tenant_id=uuid4(),
            recipient='+5730099',
            cadence='daily',
            components=[],
        )

    out = asyncio.run(_go())
    assert out is True
    # 1 execute: insert into domain_events
    assert any('domain_events' in sql for sql, _ in conn.executed)


# ───── _dispatch_one ─────────────────────────────────────────────────────


def test_dispatch_one_not_due_returns_false(monkeypatch):
    """When `is_due` returns False, dispatch returns False without action."""
    from app.workers import digest_worker

    monkeypatch.setattr(digest_worker, 'is_due', lambda **kw: False)

    row = {
        'id': uuid4(), 'tenant_id': uuid4(), 'cadence': 'daily',
        'tz_name': 'America/Bogota', 'last_sent_at': None,
        'currency': 'COP', 'recipient_email': None, 'recipient_whatsapp': None,
    }
    cfg = SimpleNamespace(alerts_smtp_host=None, alerts_smtp_from=None)
    conn = _FakeConn()

    async def _go():
        return await digest_worker._dispatch_one(
            conn, row=row, config=cfg, now_utc=datetime.now(UTC),
        )

    assert asyncio.run(_go()) is False


def test_dispatch_one_email_only_smtp_unconfigured(monkeypatch):
    """Email recipient but no SMTP → email branch fails, returns False."""
    from app.workers import digest_worker

    monkeypatch.setattr(digest_worker, 'is_due', lambda **kw: True)
    async def fake_daily(*a, **kw):
        return {'subject': 'S', 'text': 'T', 'whatsapp_components': []}
    monkeypatch.setattr(digest_worker, 'build_daily_digest', fake_daily)

    row = {
        'id': uuid4(), 'tenant_id': uuid4(), 'cadence': 'daily',
        'tz_name': 'America/Bogota', 'last_sent_at': None,
        'currency': 'COP',
        'recipient_email': 'a@b.com',
        'recipient_whatsapp': None,
    }
    cfg = SimpleNamespace(alerts_smtp_host=None, alerts_smtp_from=None)
    conn = _FakeConn()

    async def _go():
        return await digest_worker._dispatch_one(
            conn, row=row, config=cfg, now_utc=datetime.now(UTC),
        )

    assert asyncio.run(_go()) is False


def test_dispatch_one_email_success(monkeypatch):
    """Email send succeeds → returns True and updates last_sent_at."""
    from app.workers import digest_worker

    monkeypatch.setattr(digest_worker, 'is_due', lambda **kw: True)
    async def fake_daily(*a, **kw):
        return {'subject': 'S', 'text': 'T', 'whatsapp_components': []}
    monkeypatch.setattr(digest_worker, 'build_daily_digest', fake_daily)

    sent_msgs = []
    async def fake_email_sender(cfg, msg):
        sent_msgs.append(msg)

    row = {
        'id': uuid4(), 'tenant_id': uuid4(), 'cadence': 'daily',
        'tz_name': 'America/Bogota', 'last_sent_at': None,
        'currency': 'COP',
        'recipient_email': 'a@b.com',
        'recipient_whatsapp': None,
    }
    cfg = SimpleNamespace(alerts_smtp_host='smtp.example.com', alerts_smtp_from='digest@example.com')
    conn = _FakeConn()

    async def _go():
        return await digest_worker._dispatch_one(
            conn, row=row, config=cfg, now_utc=datetime.now(UTC),
            email_sender=fake_email_sender,
        )

    assert asyncio.run(_go()) is True
    assert len(sent_msgs) == 1
    # UPDATE last_sent_at
    assert any('last_sent_at' in sql for sql, _ in conn.executed)


def test_dispatch_one_weekly_calls_weekly_builder(monkeypatch):
    """When cadence=weekly, builds the weekly digest payload."""
    from app.workers import digest_worker

    monkeypatch.setattr(digest_worker, 'is_due', lambda **kw: True)
    calls = []
    async def fake_weekly(conn, *, tenant_id, tz_name, currency):
        calls.append({'tenant_id': tenant_id, 'currency': currency})
        return {'subject': 'W', 'text': 'wT', 'whatsapp_components': []}
    monkeypatch.setattr(digest_worker, 'build_weekly_digest', fake_weekly)

    row = {
        'id': uuid4(), 'tenant_id': uuid4(), 'cadence': 'weekly',
        'tz_name': 'America/Bogota', 'last_sent_at': None,
        'currency': 'COP',
        'recipient_email': None, 'recipient_whatsapp': None,
    }
    cfg = SimpleNamespace(alerts_smtp_host=None, alerts_smtp_from=None)
    conn = _FakeConn()

    async def _go():
        return await digest_worker._dispatch_one(
            conn, row=row, config=cfg, now_utc=datetime.now(UTC),
        )

    asyncio.run(_go())
    assert len(calls) == 1
    assert calls[0]['currency'] == 'COP'


def test_dispatch_one_email_send_exception_captured(monkeypatch):
    """If email_sender throws, error captured but not raised."""
    from app.workers import digest_worker

    monkeypatch.setattr(digest_worker, 'is_due', lambda **kw: True)
    async def fake_daily(*a, **kw):
        return {'subject': 'S', 'text': 'T', 'whatsapp_components': []}
    monkeypatch.setattr(digest_worker, 'build_daily_digest', fake_daily)

    async def fake_sender(cfg, msg):
        raise RuntimeError('smtp gone')

    row = {
        'id': uuid4(), 'tenant_id': uuid4(), 'cadence': 'daily',
        'tz_name': 'America/Bogota', 'last_sent_at': None,
        'currency': 'COP', 'recipient_email': 'a@b.com', 'recipient_whatsapp': None,
    }
    cfg = SimpleNamespace(alerts_smtp_host='x', alerts_smtp_from='y@z')
    conn = _FakeConn()

    async def _go():
        return await digest_worker._dispatch_one(
            conn, row=row, config=cfg, now_utc=datetime.now(UTC),
            email_sender=fake_sender,
        )

    # Doesn't raise; returns False because not delivered
    assert asyncio.run(_go()) is False


# ───── run_digest_cycle ──────────────────────────────────────────────────


def test_run_digest_cycle_no_subscriptions_returns_zero():
    from app.workers.digest_worker import run_digest_cycle
    conn = _FakeConn(fetch_results=[[]])

    async def _go():
        return await run_digest_cycle(conn)

    assert asyncio.run(_go()) == 0


def test_run_digest_cycle_processes_each_subscription(monkeypatch):
    """Dispatches each row; counts only the ones that returned True."""
    from app.workers import digest_worker

    # Patch _dispatch_one to control return values
    calls = []
    async def fake_dispatch(conn, *, row, config, now_utc, email_sender=None, whatsapp_sender=None):
        calls.append(row['id'])
        return row['cadence'] == 'daily'  # daily succeeds, weekly fails

    monkeypatch.setattr(digest_worker, '_dispatch_one', fake_dispatch)

    rows = [
        {'id': uuid4(), 'tenant_id': uuid4(), 'cadence': 'daily'},
        {'id': uuid4(), 'tenant_id': uuid4(), 'cadence': 'weekly'},
        {'id': uuid4(), 'tenant_id': uuid4(), 'cadence': 'daily'},
    ]
    conn = _FakeConn(fetch_results=[rows])

    async def _go():
        return await digest_worker.run_digest_cycle(conn)

    out = asyncio.run(_go())
    assert out == 2  # 2 daily succeeded
    assert len(calls) == 3


def test_run_digest_cycle_unhandled_exception_captured(monkeypatch):
    """If _dispatch_one raises, the error is logged but loop continues."""
    from app.workers import digest_worker

    async def fake_dispatch(*args, **kwargs):
        raise RuntimeError('boom')

    monkeypatch.setattr(digest_worker, '_dispatch_one', fake_dispatch)

    rows = [
        {'id': uuid4(), 'tenant_id': uuid4(), 'cadence': 'daily'},
        {'id': uuid4(), 'tenant_id': uuid4(), 'cadence': 'daily'},
    ]
    conn = _FakeConn(fetch_results=[rows])

    async def _go():
        return await digest_worker.run_digest_cycle(conn)

    # No raise; returns 0 (none delivered)
    assert asyncio.run(_go()) == 0
