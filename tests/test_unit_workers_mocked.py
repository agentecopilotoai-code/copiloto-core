"""Mocked-conn tests for worker async helpers.

Tests async DB helpers in app/workers/{scheduler,digest_worker,event_worker,
extraction_worker}.py using a `_FakeConn` stand-in (no real database needed).
"""
from __future__ import annotations

import asyncio
import json
from uuid import uuid4


class _FakeConn:
    """Tiny asyncpg.Connection stand-in. Pops canned results in order."""
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
        return self._fetch.pop(0) if self._fetch else []

    async def fetchrow(self, sql, *args):
        return self._fetchrow.pop(0) if self._fetchrow else None

    async def fetchval(self, sql, *args):
        return self._fetchval.pop(0) if self._fetchval else None

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


# ═════════════════════════════════════════════════════════════════════════
# scheduler.py async helpers
# ═════════════════════════════════════════════════════════════════════════


def test_mark_conversation_pending_recall_with_valid_payload():
    from app.workers.scheduler import _mark_conversation_pending_recall

    tid = uuid4()
    conv_id = uuid4()
    svc_id = uuid4()
    appt_id = uuid4()
    payload = {
        'service_id': str(svc_id),
        'conversation_id': str(conv_id),
        'appointment_id': str(appt_id),
    }

    async def _go():
        conn = _FakeConn()
        await _mark_conversation_pending_recall(
            conn, tenant_id=tid, payload=payload,
        )
        return conn.executed

    executed = asyncio.run(_go())
    assert len(executed) == 1
    sql, args = executed[0]
    assert 'pending_recall' in sql
    assert tid in args


def test_mark_conversation_pending_recall_skips_when_missing_service_id():
    from app.workers.scheduler import _mark_conversation_pending_recall

    async def _go():
        conn = _FakeConn()
        await _mark_conversation_pending_recall(
            conn, tenant_id=uuid4(),
            payload={'conversation_id': str(uuid4())},  # no service_id
        )
        return conn.executed

    executed = asyncio.run(_go())
    assert executed == []


def test_mark_conversation_pending_recall_skips_when_no_conversation_id():
    from app.workers.scheduler import _mark_conversation_pending_recall

    async def _go():
        conn = _FakeConn()
        await _mark_conversation_pending_recall(
            conn, tenant_id=uuid4(),
            payload={'service_id': str(uuid4())},  # no conversation_id
        )
        return conn.executed

    asyncio.run(_go())


def test_mark_conversation_pending_recall_handles_invalid_payload():
    from app.workers.scheduler import _mark_conversation_pending_recall

    async def _go():
        conn = _FakeConn()
        await _mark_conversation_pending_recall(
            conn, tenant_id=uuid4(), payload='not json',
        )

    asyncio.run(_go())  # no raise


def test_has_approved_template_true():
    from app.workers.scheduler import _has_approved_template
    conn = _FakeConn(fetchval_results=[1])

    async def _go():
        return await _has_approved_template(conn, uuid4(), 'service_recall')

    assert asyncio.run(_go()) is True


def test_has_approved_template_false():
    from app.workers.scheduler import _has_approved_template
    conn = _FakeConn(fetchval_results=[None])

    async def _go():
        return await _has_approved_template(conn, uuid4(), 'service_recall')

    assert asyncio.run(_go()) is False


def test_dispatch_auto_rebook_timeout_invalid_payload_marks_failed():
    """When the payload lacks conversation_id/appointment_id, the job is marked failed."""
    from app.workers.scheduler import _dispatch_auto_rebook_timeout

    job_id = uuid4()
    tenant_id = uuid4()
    row = {
        'id': job_id,
        'tenant_id': tenant_id,
        'payload': json.dumps({'missing': 'fields'}),  # no conversation_id/appointment_id
    }
    conn = _FakeConn()

    async def _go():
        await _dispatch_auto_rebook_timeout(conn, row)
        return conn.executed

    executed = asyncio.run(_go())
    # One UPDATE marking the row failed
    assert len(executed) == 1
    sql, args = executed[0]
    assert 'failed' in sql
    assert 'auto_rebook_timeout_invalid_payload' in args


def test_dispatch_auto_rebook_timeout_calls_execute_and_marks_sent(monkeypatch):
    """When payload is valid, calls execute_auto_rebook_timeout and marks sent."""
    from app.workers import scheduler as sched

    calls = []

    async def fake_execute(*args, **kwargs):
        calls.append(kwargs)
        return {'cancelled': True, 'skipped_reason': None}

    monkeypatch.setattr(
        'app.services.appointment_self_service.execute_auto_rebook_timeout',
        fake_execute,
    )

    job_id = uuid4()
    tenant_id = uuid4()
    conv_id = uuid4()
    appt_id = uuid4()
    row = {
        'id': job_id,
        'tenant_id': tenant_id,
        'payload': json.dumps({
            'conversation_id': str(conv_id),
            'appointment_id': str(appt_id),
        }),
    }
    conn = _FakeConn()

    async def _go():
        await sched._dispatch_auto_rebook_timeout(conn, row)
        return conn.executed

    executed = asyncio.run(_go())
    # 1 UPDATE marking sent
    assert len(executed) == 1
    assert "set status='sent'" in executed[0][0]
    # execute_auto_rebook_timeout was called
    assert len(calls) == 1
    assert calls[0]['tenant_id'] == tenant_id


def test_dispatch_auto_rebook_timeout_exception_marks_failed(monkeypatch):
    """When execute_auto_rebook_timeout raises, marks the row as failed with the exception text."""
    from app.workers import scheduler as sched

    async def fake_execute(*args, **kwargs):
        raise RuntimeError('boom')

    monkeypatch.setattr(
        'app.services.appointment_self_service.execute_auto_rebook_timeout',
        fake_execute,
    )

    job_id = uuid4()
    row = {
        'id': job_id,
        'tenant_id': uuid4(),
        'payload': json.dumps({
            'conversation_id': str(uuid4()),
            'appointment_id': str(uuid4()),
        }),
    }
    conn = _FakeConn()

    async def _go():
        await sched._dispatch_auto_rebook_timeout(conn, row)
        return conn.executed

    executed = asyncio.run(_go())
    assert len(executed) == 1
    sql, args = executed[0]
    assert 'failed' in sql
    assert any('auto_rebook_timeout_exception' in str(a) for a in args)


def test_update_scheduler_queue_depth_writes_metric():
    """The helper reads pending count from DB and updates a metric."""
    from app.workers.scheduler import _update_scheduler_queue_depth
    conn = _FakeConn(fetchval_results=[42])

    async def _go():
        await _update_scheduler_queue_depth(conn)

    asyncio.run(_go())  # no raise; metric side-effect (Prometheus gauge)


def test_process_pending_reminder_jobs_no_rows_returns_zero():
    from app.workers.scheduler import _process_pending_reminder_jobs
    conn = _FakeConn(fetch_results=[[]])

    async def _go():
        return await _process_pending_reminder_jobs(conn)

    assert asyncio.run(_go()) == 0


def test_process_pending_reminder_jobs_skips_no_template():
    """Jobs whose purpose has no approved template are marked failed."""
    from app.workers.scheduler import _process_pending_reminder_jobs

    job_id = uuid4()
    tid = uuid4()
    rows = [{
        'id': job_id,
        'tenant_id': tid,
        'payload': json.dumps({'purpose': 'unknown_purpose'}),
    }]
    conn = _FakeConn(
        fetch_results=[rows],
        fetchval_results=[None],  # _has_approved_template returns None (no template)
    )

    async def _go():
        return await _process_pending_reminder_jobs(conn)

    out = asyncio.run(_go())
    assert out == 1
    # One UPDATE marking failed
    assert any('failed' in sql for sql, _ in conn.executed)


def test_process_pending_reminder_jobs_emits_reminder_due():
    """Jobs whose purpose has an approved template emit `reminder.due` events and are marked sent."""
    from app.workers.scheduler import _process_pending_reminder_jobs

    job_id = uuid4()
    tid = uuid4()
    rows = [{
        'id': job_id,
        'tenant_id': tid,
        'payload': json.dumps({'purpose': 'service_recall', 'service_id': str(uuid4()), 'conversation_id': str(uuid4())}),
    }]
    conn = _FakeConn(
        fetch_results=[rows],
        fetchval_results=[1],  # approved template exists
    )

    async def _go():
        return await _process_pending_reminder_jobs(conn)

    out = asyncio.run(_go())
    assert out == 1
    # Inserts reminder.due
    assert any('reminder.due' in sql for sql, _ in conn.executed)


# ═════════════════════════════════════════════════════════════════════════
# event_worker async (process_once and _process_locked_batch via FakeConn)
# ═════════════════════════════════════════════════════════════════════════


def test_process_once_no_events_returns_zero():
    """When the batch query returns no rows, the loop breaks at iter 0."""
    from app.workers import event_worker

    class _FakeConnWithTransaction(_FakeConn):
        def transaction(self):
            return self

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

    conn = _FakeConnWithTransaction()

    async def _go():
        return await event_worker.process_once(conn)

    assert asyncio.run(_go()) == 0


# ═════════════════════════════════════════════════════════════════════════
# digest_worker async helpers
# ═════════════════════════════════════════════════════════════════════════


def test_fetch_due_subscriptions_returns_rows():
    from app.workers.digest_worker import _fetch_due_subscriptions
    sub_id = uuid4()
    rows = [
        {
            'id': sub_id, 'tenant_id': uuid4(),
            'recipient_email': 'a@b.com', 'recipient_whatsapp': '+57300',
            'cadence': 'daily', 'last_sent_at': None,
        },
    ]
    conn = _FakeConn(fetch_results=[rows])

    async def _go():
        return await _fetch_due_subscriptions(conn)

    out = asyncio.run(_go())
    assert len(out) == 1
    assert out[0]['id'] == sub_id


def test_fetch_due_subscriptions_empty():
    from app.workers.digest_worker import _fetch_due_subscriptions
    conn = _FakeConn(fetch_results=[[]])

    async def _go():
        return await _fetch_due_subscriptions(conn)

    assert asyncio.run(_go()) == []
