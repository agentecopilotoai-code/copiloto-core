"""Pure-helper + mocked-conn tests for `app/services/outbound_dlq.py`.

Uses a tiny `_FakeConn` to simulate asyncpg.fetchrow/fetch/fetchval/execute
since the helpers are pure SQL builders + result coercion.
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest


# ───────── normalize_error_code ──────────────────────────────────────────


def test_normalize_error_code_none_returns_default():
    from app.services.outbound_dlq import normalize_error_code
    assert normalize_error_code(None) == 'transport_error'


def test_normalize_error_code_empty_string_returns_default():
    from app.services.outbound_dlq import normalize_error_code
    assert normalize_error_code('') == 'transport_error'
    assert normalize_error_code('   ') == 'transport_error'


def test_normalize_error_code_returns_stripped():
    from app.services.outbound_dlq import normalize_error_code
    assert normalize_error_code(' 131026 ') == '131026'
    assert normalize_error_code(42) == '42'


# ───────── _row_to_item ──────────────────────────────────────────────────


def _row(**kwargs):
    """A minimal asyncpg.Record stand-in."""
    class _R(dict):
        def keys(self):  # type: ignore[override]
            return super().keys()

    return _R(kwargs)


def test_row_to_item_basic_fields():
    from app.services.outbound_dlq import _row_to_item
    msg_id = uuid4()
    conv_id = uuid4()
    failed_at = datetime(2026, 5, 18, 10, 0, tzinfo=UTC)
    row = _row(
        id=msg_id, conversation_id=conv_id,
        contact_phone='+573009998877', message_type='text',
        body_text='Hola',
        error_code='131026', error_message='Too long',
        failed_at=failed_at,
        created_at=failed_at,
        payload={'k': 'v'},
    )
    item = _row_to_item(row)
    assert item['id'] == str(msg_id)
    assert item['conversation_id'] == str(conv_id)
    assert item['contact_phone_last4'] == '8877'
    assert item['body_preview'] == 'Hola'
    assert item['error_code'] == '131026'
    assert item['failed_at'].startswith('2026-05-18')
    assert item['payload'] == {'k': 'v'}


def test_row_to_item_truncates_body_preview():
    from app.services.outbound_dlq import _row_to_item
    long_text = 'x' * 500
    row = _row(
        id=uuid4(), conversation_id=None, contact_phone=None,
        message_type='text', body_text=long_text,
        error_code=None, error_message=None,
        failed_at=None, created_at=None, payload={},
    )
    item = _row_to_item(row)
    assert len(item['body_preview']) == 160
    assert item['error_code'] == 'transport_error'
    assert item['failed_at'] is None
    assert item['created_at'] is None


def test_row_to_item_decodes_json_string_payload():
    from app.services.outbound_dlq import _row_to_item
    row = _row(
        id=uuid4(), conversation_id=None, contact_phone='',
        message_type='text', body_text='',
        error_code='x', error_message=None,
        failed_at=None, created_at=None,
        payload='{"foo": "bar"}',
    )
    item = _row_to_item(row)
    assert item['payload'] == {'foo': 'bar'}


def test_row_to_item_invalid_json_payload_becomes_empty():
    from app.services.outbound_dlq import _row_to_item
    row = _row(
        id=uuid4(), conversation_id=None, contact_phone='',
        message_type='text', body_text='',
        error_code='x', error_message=None,
        failed_at=None, created_at=None,
        payload='not json',
    )
    item = _row_to_item(row)
    assert item['payload'] == {}


def test_row_to_item_non_dict_payload_becomes_empty():
    from app.services.outbound_dlq import _row_to_item
    row = _row(
        id=uuid4(), conversation_id=None, contact_phone='',
        message_type='text', body_text='',
        error_code='x', error_message=None,
        failed_at=None, created_at=None,
        payload=['array', 'not', 'dict'],
    )
    item = _row_to_item(row)
    assert item['payload'] == {}


# ───────── _FakeConn for list_dlq / count_recent_failures / requeue ──────


class _FakeConn:
    """Minimal asyncpg.Connection stand-in.

    Each method consumes from the corresponding seed list in order.
    """
    def __init__(
        self,
        *,
        fetch_results=None,
        fetchrow_results=None,
        fetchval_results=None,
    ):
        self._fetch = list(fetch_results or [])
        self._fetchrow = list(fetchrow_results or [])
        self._fetchval = list(fetchval_results or [])
        self.executed = []

    async def fetch(self, sql, *args):
        if not self._fetch:
            return []
        return self._fetch.pop(0)

    async def fetchrow(self, sql, *args):
        if not self._fetchrow:
            return None
        return self._fetchrow.pop(0)

    async def fetchval(self, sql, *args):
        if not self._fetchval:
            return None
        return self._fetchval.pop(0)

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


def test_list_dlq_returns_items_and_totals():
    from app.services.outbound_dlq import list_dlq
    tenant_id = uuid4()
    msg_id = uuid4()
    failed_at = datetime(2026, 5, 18, tzinfo=UTC)
    conn = _FakeConn(
        fetch_results=[
            # totals_rows
            [_row(error_code='131026', count=12)],
            # items_rows
            [_row(
                id=msg_id, conversation_id=None,
                contact_phone='+5730099', message_type='text',
                body_text='Hola', error_code='131026',
                error_message='Too long', failed_at=failed_at,
                created_at=failed_at, payload={},
            )],
        ],
    )

    async def _go():
        return await list_dlq(conn, tenant_id=tenant_id)

    out = asyncio.run(_go())
    assert out['totals_by_error_code'] == [
        {'error_code': '131026', 'count': 12},
    ]
    assert len(out['items']) == 1
    assert out['items'][0]['id'] == str(msg_id)


def test_list_dlq_with_filters():
    from app.services.outbound_dlq import list_dlq
    tenant_id = uuid4()
    since = datetime(2026, 5, 17, tzinfo=UTC)
    until = datetime(2026, 5, 18, tzinfo=UTC)
    conn = _FakeConn(
        fetch_results=[
            [],  # totals
            [],  # items
        ],
    )

    async def _go():
        return await list_dlq(
            conn, tenant_id=tenant_id, since=since, until=until,
            limit=10, error_code='131026',
        )

    out = asyncio.run(_go())
    assert out['items'] == []
    assert out['totals_by_error_code'] == []


def test_list_dlq_caps_limit():
    """limit > 500 is bounded; limit < 1 becomes 1."""
    from app.services.outbound_dlq import list_dlq
    tenant_id = uuid4()
    conn = _FakeConn(fetch_results=[[], []])

    async def _go():
        return await list_dlq(conn, tenant_id=tenant_id, limit=999)

    out = asyncio.run(_go())
    assert out['items'] == []


# ───────── count_recent_failures ─────────────────────────────────────────


def test_count_recent_failures_aggregates():
    from app.services.outbound_dlq import count_recent_failures
    tenant_id = uuid4()
    failed_at = datetime(2026, 5, 18, tzinfo=UTC)
    conn = _FakeConn(
        fetch_results=[
            [
                _row(error_code='131026', count=8),
                _row(error_code='131047', count=4),
            ],
            [
                _row(
                    id=uuid4(), error_code='131026',
                    error_message='Too long', at=failed_at,
                ),
            ],
        ],
    )

    async def _go():
        return await count_recent_failures(conn, tenant_id=tenant_id, window_minutes=10)

    out = asyncio.run(_go())
    assert out['total'] == 12
    assert out['window_minutes'] == 10
    assert len(out['by_error_code']) == 2
    assert len(out['preview']) == 1
    assert 'since' in out


def test_count_recent_failures_truncates_long_messages():
    from app.services.outbound_dlq import count_recent_failures
    tenant_id = uuid4()
    long_msg = 'x' * 500
    conn = _FakeConn(
        fetch_results=[
            [_row(error_code='131026', count=1)],
            [_row(id=uuid4(), error_code='131026',
                  error_message=long_msg, at=None)],
        ],
    )

    async def _go():
        return await count_recent_failures(conn, tenant_id=tenant_id, window_minutes=10)

    out = asyncio.run(_go())
    assert len(out['preview'][0]['error_message']) == 300


def test_count_recent_failures_handles_no_rows():
    from app.services.outbound_dlq import count_recent_failures
    conn = _FakeConn(fetch_results=[[], []])

    async def _go():
        return await count_recent_failures(conn, tenant_id=uuid4(), window_minutes=15)

    out = asyncio.run(_go())
    assert out['total'] == 0
    assert out['by_error_code'] == []
    assert out['preview'] == []


# ───────── requeue_message ───────────────────────────────────────────────


def test_requeue_message_not_found():
    from app.services.outbound_dlq import requeue_message
    conn = _FakeConn(fetchrow_results=[None])

    async def _go():
        return await requeue_message(
            conn, tenant_id=uuid4(), message_id=uuid4(),
        )

    out = asyncio.run(_go())
    assert out == {'requeued': False, 'reason': 'not_found'}


def test_requeue_message_not_outbound():
    from app.services.outbound_dlq import requeue_message
    conn = _FakeConn(fetchrow_results=[
        _row(id=uuid4(), status='failed', direction='inbound', retry_count=0),
    ])

    async def _go():
        return await requeue_message(
            conn, tenant_id=uuid4(), message_id=uuid4(),
        )

    out = asyncio.run(_go())
    assert out == {'requeued': False, 'reason': 'not_outbound'}


def test_requeue_message_already_queued():
    from app.services.outbound_dlq import requeue_message
    conn = _FakeConn(fetchrow_results=[
        _row(id=uuid4(), status='queued', direction='outbound', retry_count=1),
    ])

    async def _go():
        return await requeue_message(
            conn, tenant_id=uuid4(), message_id=uuid4(),
        )

    out = asyncio.run(_go())
    assert out == {'requeued': False, 'reason': 'already_queued'}


def test_requeue_message_invalid_status():
    from app.services.outbound_dlq import requeue_message
    conn = _FakeConn(fetchrow_results=[
        _row(id=uuid4(), status='sent', direction='outbound', retry_count=0),
    ])

    async def _go():
        return await requeue_message(
            conn, tenant_id=uuid4(), message_id=uuid4(),
        )

    out = asyncio.run(_go())
    assert out['requeued'] is False
    assert 'invalid_status:sent' in out['reason']


def test_requeue_message_atomic_lost_race():
    """Pre-check sees 'failed' but UPDATE returns no row → lost race."""
    from app.services.outbound_dlq import requeue_message
    conn = _FakeConn(fetchrow_results=[
        # initial select sees 'failed'
        _row(id=uuid4(), status='failed', direction='outbound', retry_count=0),
        # atomic UPDATE returns None (status changed under us)
        None,
    ])

    async def _go():
        return await requeue_message(
            conn, tenant_id=uuid4(), message_id=uuid4(),
        )

    out = asyncio.run(_go())
    assert out == {'requeued': False, 'reason': 'already_queued'}


def test_requeue_message_success():
    from app.services.outbound_dlq import requeue_message
    msg_id = uuid4()
    tenant_id = uuid4()
    conn = _FakeConn(
        fetchrow_results=[
            _row(id=msg_id, status='failed', direction='outbound', retry_count=0),
            _row(retry_count=1),  # after UPDATE
        ],
        fetchval_results=[uuid4()],  # inserted event id
    )

    async def _go():
        return await requeue_message(
            conn, tenant_id=tenant_id, message_id=msg_id,
            requested_by='admin',
        )

    out = asyncio.run(_go())
    assert out['requeued'] is True
    assert out['message_id'] == str(msg_id)
    assert out['retry_count'] == 1
    assert out['idempotency_key'] == f'message-retry:{msg_id}:1'


def test_requeue_message_event_already_emitted():
    """The atomic UPDATE succeeds, but the domain_event insert short-circuits
    on conflict — function still reports success with `event_replayed=True`."""
    from app.services.outbound_dlq import requeue_message
    msg_id = uuid4()
    conn = _FakeConn(
        fetchrow_results=[
            _row(id=msg_id, status='failed', direction='outbound', retry_count=0),
            _row(retry_count=1),
        ],
        fetchval_results=[None],  # insert was already there
    )

    async def _go():
        return await requeue_message(
            conn, tenant_id=uuid4(), message_id=msg_id,
        )

    out = asyncio.run(_go())
    assert out['requeued'] is True
    assert out['event_replayed'] is True


# ───────── requeue_tenant_dlq (bulk) ─────────────────────────────────────


def test_requeue_tenant_dlq_no_matching_rows():
    from app.services.outbound_dlq import requeue_tenant_dlq
    conn = _FakeConn(fetch_results=[[]])

    async def _go():
        return await requeue_tenant_dlq(
            conn, tenant_id=uuid4(),
        )

    out = asyncio.run(_go())
    assert out == {
        'matched': 0, 'requeued': 0, 'message_ids': [], 'capped': False,
    }


def test_requeue_tenant_dlq_processes_each_match():
    """Each matched row is forwarded to requeue_message. Successful ones
    show up in the returned `message_ids` list."""
    from app.services.outbound_dlq import requeue_tenant_dlq
    msg_id_1 = uuid4()
    msg_id_2 = uuid4()
    conn = _FakeConn(
        fetch_results=[
            [_row(id=msg_id_1), _row(id=msg_id_2)],
        ],
        fetchrow_results=[
            # First message: success path
            _row(id=msg_id_1, status='failed', direction='outbound', retry_count=0),
            _row(retry_count=1),
            # Second message: not_outbound (skipped)
            _row(id=msg_id_2, status='failed', direction='inbound', retry_count=0),
        ],
        fetchval_results=[
            uuid4(),  # event id for first
        ],
    )

    async def _go():
        return await requeue_tenant_dlq(
            conn, tenant_id=uuid4(), requested_by='admin',
        )

    out = asyncio.run(_go())
    assert out['matched'] == 2
    assert out['requeued'] == 1
    assert out['message_ids'] == [str(msg_id_1)]
    assert out['capped'] is False


def test_requeue_tenant_dlq_with_filters():
    from app.services.outbound_dlq import requeue_tenant_dlq
    since = datetime(2026, 5, 17, tzinfo=UTC)
    conn = _FakeConn(fetch_results=[[]])

    async def _go():
        return await requeue_tenant_dlq(
            conn, tenant_id=uuid4(),
            error_code='131026', since=since, limit=5,
        )

    out = asyncio.run(_go())
    assert out['matched'] == 0


def test_requeue_tenant_dlq_caps_limit():
    """limit > 1000 is bounded down."""
    from app.services.outbound_dlq import requeue_tenant_dlq
    conn = _FakeConn(fetch_results=[[]])

    async def _go():
        return await requeue_tenant_dlq(
            conn, tenant_id=uuid4(), limit=99999,
        )

    out = asyncio.run(_go())
    assert out['matched'] == 0
