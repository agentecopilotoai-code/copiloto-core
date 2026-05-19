"""Unit tests for `app/admin/ws_fanout.py` focusing on the pure dispatcher
and the subscriber-management properties (sync, no DB needed)."""
from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest


def test_fanout_initial_state():
    from app.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    assert f.subscriber_count == 0
    assert f.tenant_count == 0


def test_fanout_dispatch_invalid_json_is_dropped():
    from app.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    # Drop happens silently; no exception
    f._dispatch('not json at all')


def test_fanout_dispatch_missing_tenant_id_dropped():
    from app.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    # No tenant_id field → silently dropped
    f._dispatch(json.dumps({'event': 'x'}))


def test_fanout_dispatch_no_subscribers_for_tenant():
    from app.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    # Tenant not registered → silently dropped
    f._dispatch(json.dumps({'tenant_id': str(uuid4()), 'event': 'x'}))


def test_fanout_dispatch_delivers_to_subscribers():
    """Manually wire two queues + dispatch a notification."""
    from app.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    tid = uuid4()
    q1: asyncio.Queue[str] = asyncio.Queue(maxsize=10)
    q2: asyncio.Queue[str] = asyncio.Queue(maxsize=10)
    f._subscribers[str(tid)] = {q1, q2}

    payload = json.dumps({'tenant_id': str(tid), 'event': 'msg.created'})
    f._dispatch(payload)

    # Both queues received the payload
    assert q1.get_nowait() == payload
    assert q2.get_nowait() == payload


def test_fanout_dispatch_drops_oldest_when_queue_full():
    from app.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    tid = uuid4()
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=1)
    # Pre-fill the queue so the dispatch path triggers QueueFull
    q.put_nowait('old')
    f._subscribers[str(tid)] = {q}

    payload = json.dumps({'tenant_id': str(tid), 'event': 'new'})
    f._dispatch(payload)

    # The old payload was discarded, the new one is at the head
    assert q.get_nowait() == payload


def test_fanout_dispatch_filters_by_tenant():
    """A notification for tenant A doesn't reach tenant B's queue."""
    from app.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    tid_a = uuid4()
    tid_b = uuid4()
    qa: asyncio.Queue[str] = asyncio.Queue(maxsize=10)
    qb: asyncio.Queue[str] = asyncio.Queue(maxsize=10)
    f._subscribers[str(tid_a)] = {qa}
    f._subscribers[str(tid_b)] = {qb}

    f._dispatch(json.dumps({'tenant_id': str(tid_a), 'event': 'a'}))

    assert qa.qsize() == 1
    assert qb.qsize() == 0


def test_fanout_subscriber_count_aggregates_across_tenants():
    from app.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    tid_a = uuid4()
    tid_b = uuid4()
    f._subscribers[str(tid_a)] = {asyncio.Queue(), asyncio.Queue()}
    f._subscribers[str(tid_b)] = {asyncio.Queue()}
    assert f.subscriber_count == 3
    assert f.tenant_count == 2


def test_fanout_on_notify_factory_returns_callable():
    """The callback factory returns a 4-arg sync function."""
    from app.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    cb = f._on_notify_factory(None)
    assert callable(cb)
    # Must NOT raise when called with the asyncpg-shaped args
    cb(None, 123, 'tenant_operations_events',
       json.dumps({'tenant_id': str(uuid4()), 'event': 'x'}))


def test_reset_fanout_for_tests_resets_singleton():
    """`reset_fanout_for_tests()` clears the module-level singleton state."""
    from app.admin import ws_fanout
    # Mutate the singleton
    ws_fanout.fanout._subscribers['fake-tenant'] = {asyncio.Queue()}
    assert ws_fanout.fanout.subscriber_count == 1
    ws_fanout.reset_fanout_for_tests()
    # After reset, the singleton is fresh
    assert ws_fanout.fanout.subscriber_count == 0


def test_fanout_unsubscribe_unknown_tenant_no_op():
    """Calling unsubscribe with a tenant_id that isn't registered is a no-op."""
    from app.admin.ws_fanout import _PubSubFanout

    f = _PubSubFanout()
    q: asyncio.Queue[str] = asyncio.Queue()

    async def _go():
        await f.unsubscribe(uuid4(), q)
        return f.subscriber_count

    assert asyncio.run(_go()) == 0


def test_fanout_unsubscribe_removes_subscriber_and_tenant_when_last():
    from app.admin.ws_fanout import _PubSubFanout

    f = _PubSubFanout()
    tid = uuid4()
    q: asyncio.Queue[str] = asyncio.Queue()
    f._subscribers[str(tid)] = {q}

    async def _go():
        await f.unsubscribe(tid, q)
        return f.subscriber_count, f.tenant_count

    sub, ten = asyncio.run(_go())
    assert sub == 0
    assert ten == 0
