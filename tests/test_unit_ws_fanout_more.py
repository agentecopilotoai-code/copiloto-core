"""Unit tests for app/admin/ws_fanout.py — pub/sub fanout."""
from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import pytest


def _run(c):
    return asyncio.run(c)


# ─── _dispatch ──────────────────────────────────────────────────────────


def test_dispatch_invalid_json_logged():
    from copiloto_core.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    # Empty subscribers + invalid JSON → no raise
    f._dispatch('not-json')


def test_dispatch_no_tenant_id_in_payload():
    from copiloto_core.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    f._dispatch(json.dumps({'event': 'something'}))


def test_dispatch_no_matching_subscribers():
    from copiloto_core.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    f._dispatch(json.dumps({'tenant_id': str(uuid4()), 'event': 'x'}))


def test_dispatch_to_matching_subscriber():
    from copiloto_core.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    tid = uuid4()
    queue = asyncio.Queue(maxsize=100)
    f._subscribers[str(tid)] = {queue}
    payload = json.dumps({'tenant_id': str(tid), 'event': 'x'})
    f._dispatch(payload)
    # Queue gets the payload
    assert queue.qsize() == 1


def test_dispatch_queue_full_drops_oldest():
    from copiloto_core.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    tid = uuid4()
    queue = asyncio.Queue(maxsize=2)
    queue.put_nowait('old1')
    queue.put_nowait('old2')
    f._subscribers[str(tid)] = {queue}
    payload = json.dumps({'tenant_id': str(tid), 'event': 'x'})
    f._dispatch(payload)
    # old1 dropped, old2 still there + new payload added
    assert queue.qsize() == 2
    # First out is now old2 (oldest of remaining)
    assert queue.get_nowait() == 'old2'
    assert queue.get_nowait() == payload


# ─── subscribe / unsubscribe ──────────────────────────────────────────


class _FakeConn:
    def __init__(self):
        self.listened = []
        self.added_listeners = []

    async def add_listener(self, channel, callback):
        self.added_listeners.append((channel, callback))

    async def remove_listener(self, channel, callback):
        pass

    async def execute(self, sql, *args):
        self.listened.append(sql)


class _FakePoolCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *a):
        return False


class _FakePool:
    def __init__(self):
        self.conn = _FakeConn()

    def acquire(self):
        return _FakePoolCtx(self.conn)


def test_subscribe_starts_supervisor_and_dispatches():
    from copiloto_core.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    pool = _FakePool()
    tid = uuid4()

    async def _go():
        queue = await f.subscribe(pool, tid)
        assert queue is not None
        # The dispatcher should now be hooked up
        assert len(pool.conn.added_listeners) == 1
        # Send a notification
        callback = pool.conn.added_listeners[0][1]
        payload = json.dumps({'tenant_id': str(tid), 'event': 'x'})
        callback(None, 0, 'channel', payload)
        # Subscriber should receive it
        assert queue.get_nowait() == payload
        await f.unsubscribe(tid, queue)
        # Supervisor torn down
        assert f._task is None

    _run(_go())


def test_subscribe_multiple_subscribers_share_supervisor():
    from copiloto_core.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    pool = _FakePool()
    tid_a = uuid4()
    tid_b = uuid4()

    async def _go():
        q1 = await f.subscribe(pool, tid_a)
        q2 = await f.subscribe(pool, tid_b)
        # Only one listener registered
        assert len(pool.conn.added_listeners) == 1
        # Two tenants tracked
        assert f.tenant_count == 2
        await f.unsubscribe(tid_a, q1)
        # Still one subscriber → supervisor still running
        assert f._task is not None
        await f.unsubscribe(tid_b, q2)
        # All gone → supervisor torn down
        assert f._task is None

    _run(_go())


def test_subscribe_same_tenant_two_subscribers():
    from copiloto_core.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    pool = _FakePool()
    tid = uuid4()

    async def _go():
        q1 = await f.subscribe(pool, tid)
        q2 = await f.subscribe(pool, tid)
        assert f.subscriber_count == 2
        # Dispatch goes to both
        callback = pool.conn.added_listeners[0][1]
        payload = json.dumps({'tenant_id': str(tid), 'event': 'x'})
        callback(None, 0, 'channel', payload)
        assert q1.qsize() == 1
        assert q2.qsize() == 1
        await f.unsubscribe(tid, q1)
        # Still has q2
        assert f.tenant_count == 1
        await f.unsubscribe(tid, q2)

    _run(_go())


def test_subscribe_supervisor_crashes(monkeypatch):
    """Supervisor crashes on setup → subscribe retries then bails out."""
    from copiloto_core.admin.ws_fanout import _PubSubFanout

    class _BrokenConn:
        async def add_listener(self, *a, **kw):
            raise RuntimeError('connection refused')

        async def remove_listener(self, *a, **kw):
            pass

        async def execute(self, *a, **kw):
            pass

    class _BrokenPool:
        def acquire(self):
            class _Ctx:
                async def __aenter__(self_):
                    return _BrokenConn()

                async def __aexit__(self_, *a):
                    return False

            return _Ctx()

    f = _PubSubFanout()
    tid = uuid4()

    async def _go():
        with pytest.raises(RuntimeError, match='supervisor crashed'):
            await f.subscribe(_BrokenPool(), tid)

    _run(_go())


def test_reset_fanout_for_tests():
    from copiloto_core.admin.ws_fanout import reset_fanout_for_tests
    import copiloto_core.admin.ws_fanout as wf
    original = wf.fanout
    reset_fanout_for_tests()
    new = wf.fanout
    # Should be a new instance
    assert new is not original


def test_subscriber_count_and_tenant_count_empty():
    from copiloto_core.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    assert f.subscriber_count == 0
    assert f.tenant_count == 0


def test_unsubscribe_unknown_queue_noop():
    from copiloto_core.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    tid = uuid4()
    queue = asyncio.Queue()
    # tenant not in subscribers → unsubscribe is no-op

    _run(f.unsubscribe(tid, queue))
    # No crash


def test_dispatch_queue_full_after_drop_still_logs():
    """Edge: drop oldest, but put fails again — should log + give up."""
    from copiloto_core.admin.ws_fanout import _PubSubFanout
    f = _PubSubFanout()
    tid = uuid4()
    queue = asyncio.Queue(maxsize=1)
    queue.put_nowait('old')
    f._subscribers[str(tid)] = {queue}

    # Monkey-patch put_nowait to always fail
    call_count = [0]

    def _fail(_item):
        call_count[0] += 1
        raise asyncio.QueueFull('full')

    queue.put_nowait = _fail  # type: ignore[assignment]

    payload = json.dumps({'tenant_id': str(tid), 'event': 'x'})
    f._dispatch(payload)
    # First attempt + retry after dropping oldest = 2 calls
    assert call_count[0] == 2
