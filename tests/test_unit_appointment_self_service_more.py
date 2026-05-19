"""Extra tests for app/services/appointment_self_service.py pure helpers."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4


class _Row(dict):
    def keys(self):  # type: ignore[override]
        return super().keys()


class _FakeConn:
    def __init__(self, *, fetchrow_results=None, fetchval_results=None, fetch_results=None):
        self._fetchrow = list(fetchrow_results or [])
        self._fetchval = list(fetchval_results or [])
        self._fetch = list(fetch_results or [])
        self.executed = []

    async def fetchrow(self, sql, *args):
        if not self._fetchrow:
            return None
        return self._fetchrow.pop(0)

    async def fetchval(self, sql, *args):
        if not self._fetchval:
            return None
        return self._fetchval.pop(0)

    async def fetch(self, sql, *args):
        if not self._fetch:
            return []
        return self._fetch.pop(0)

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


def _run(c):
    return asyncio.run(c)


# ─── auto_rebook_timeout_minutes ─────────────────────────────────────────


def test_auto_rebook_timeout_minutes_default():
    from app.services.appointment_self_service import (
        auto_rebook_timeout_minutes, DEFAULT_AUTO_REBOOK_TIMEOUT_MINUTES,
    )
    assert auto_rebook_timeout_minutes(None) == DEFAULT_AUTO_REBOOK_TIMEOUT_MINUTES
    assert auto_rebook_timeout_minutes('not-json') == DEFAULT_AUTO_REBOOK_TIMEOUT_MINUTES
    assert auto_rebook_timeout_minutes([1]) == DEFAULT_AUTO_REBOOK_TIMEOUT_MINUTES


def test_auto_rebook_timeout_minutes_invalid_value():
    from app.services.appointment_self_service import (
        auto_rebook_timeout_minutes, DEFAULT_AUTO_REBOOK_TIMEOUT_MINUTES,
    )
    assert auto_rebook_timeout_minutes({'auto_rebook_timeout_minutes': 'abc'}) == DEFAULT_AUTO_REBOOK_TIMEOUT_MINUTES


def test_auto_rebook_timeout_minutes_below_min():
    from app.services.appointment_self_service import (
        auto_rebook_timeout_minutes, MIN_AUTO_REBOOK_TIMEOUT_MINUTES,
    )
    assert auto_rebook_timeout_minutes({'auto_rebook_timeout_minutes': -1}) == MIN_AUTO_REBOOK_TIMEOUT_MINUTES


def test_auto_rebook_timeout_minutes_above_max():
    from app.services.appointment_self_service import (
        auto_rebook_timeout_minutes, MAX_AUTO_REBOOK_TIMEOUT_MINUTES,
    )
    assert auto_rebook_timeout_minutes({'auto_rebook_timeout_minutes': 999999}) == MAX_AUTO_REBOOK_TIMEOUT_MINUTES


def test_auto_rebook_timeout_minutes_valid():
    from app.services.appointment_self_service import auto_rebook_timeout_minutes
    assert auto_rebook_timeout_minutes({'auto_rebook_timeout_minutes': 30}) == 30


def test_auto_rebook_timeout_minutes_from_string():
    from app.services.appointment_self_service import auto_rebook_timeout_minutes
    assert auto_rebook_timeout_minutes('{"auto_rebook_timeout_minutes": 45}') == 45


# ─── _parse_json ──────────────────────────────────────────────────────────


def test_parse_json_string_valid():
    from app.services.appointment_self_service import _parse_json
    assert _parse_json('{"x":1}', {}) == {'x': 1}


def test_parse_json_string_invalid_returns_fallback():
    from app.services.appointment_self_service import _parse_json
    assert _parse_json('not-json', {'fb': True}) == {'fb': True}


def test_parse_json_none_returns_fallback():
    from app.services.appointment_self_service import _parse_json
    assert _parse_json(None, 'default') == 'default'


def test_parse_json_passthrough_value():
    from app.services.appointment_self_service import _parse_json
    assert _parse_json([1, 2], {}) == [1, 2]


# ─── _self_service_state ─────────────────────────────────────────────────


def test_self_service_state_no_metadata():
    from app.services.appointment_self_service import _self_service_state
    assert _self_service_state({'metadata': None}) == {}


def test_self_service_state_metadata_not_dict():
    from app.services.appointment_self_service import _self_service_state
    assert _self_service_state({'metadata': '[1,2,3]'}) == {}


def test_self_service_state_no_self_service_key():
    from app.services.appointment_self_service import _self_service_state
    assert _self_service_state({'metadata': {'other': True}}) == {}


def test_self_service_state_returns_dict():
    from app.services.appointment_self_service import _self_service_state
    assert _self_service_state({'metadata': {'self_service': {'step': 'A'}}}) == {'step': 'A'}


def test_self_service_state_state_not_dict():
    from app.services.appointment_self_service import _self_service_state
    assert _self_service_state({'metadata': {'self_service': 'string'}}) == {}


# ─── _interactive_id ─────────────────────────────────────────────────────


def test_appt_self_service_interactive_id_payload_not_dict():
    from app.services.appointment_self_service import _interactive_id
    assert _interactive_id({'payload': '[1,2]'}) == (None, None)


def test_appt_self_service_interactive_id_no_colon():
    from app.services.appointment_self_service import _interactive_id
    assert _interactive_id({'payload': {'interactive_id': 'nocolon'}}) == (None, None)


def test_appt_self_service_interactive_id_valid():
    from app.services.appointment_self_service import _interactive_id
    out = _interactive_id({'payload': {'interactive_id': 'cancel_confirm:yes'}})
    assert out == ('cancel_confirm', 'yes')


# ─── min_hours_before_start ─────────────────────────────────────────────


def test_min_hours_before_start_default_when_no_policy():
    from app.services.appointment_self_service import min_hours_before_start, DEFAULT_MIN_HOURS_BEFORE_START
    assert min_hours_before_start(None) == float(DEFAULT_MIN_HOURS_BEFORE_START)


def test_min_hours_before_start_policy_not_dict():
    from app.services.appointment_self_service import min_hours_before_start, DEFAULT_MIN_HOURS_BEFORE_START
    assert min_hours_before_start([1, 2]) == float(DEFAULT_MIN_HOURS_BEFORE_START)


def test_min_hours_before_start_no_self_service():
    from app.services.appointment_self_service import min_hours_before_start, DEFAULT_MIN_HOURS_BEFORE_START
    assert min_hours_before_start({}) == float(DEFAULT_MIN_HOURS_BEFORE_START)


def test_min_hours_before_start_self_service_not_dict():
    from app.services.appointment_self_service import min_hours_before_start, DEFAULT_MIN_HOURS_BEFORE_START
    assert min_hours_before_start({'self_service': 'not-dict'}) == float(DEFAULT_MIN_HOURS_BEFORE_START)


def test_min_hours_before_start_invalid_value():
    from app.services.appointment_self_service import min_hours_before_start, DEFAULT_MIN_HOURS_BEFORE_START
    assert min_hours_before_start({'self_service': {'min_hours_before_start': 'abc'}}) == float(DEFAULT_MIN_HOURS_BEFORE_START)


def test_min_hours_before_start_negative_falls_back():
    from app.services.appointment_self_service import min_hours_before_start, DEFAULT_MIN_HOURS_BEFORE_START
    assert min_hours_before_start({'self_service': {'min_hours_before_start': -5}}) == float(DEFAULT_MIN_HOURS_BEFORE_START)


def test_min_hours_before_start_valid():
    from app.services.appointment_self_service import min_hours_before_start
    assert min_hours_before_start({'self_service': {'min_hours_before_start': 4.5}}) == 4.5


# ─── _fetch_upcoming_appointment ─────────────────────────────────────────


def test_fetch_upcoming_appointment_none():
    from app.services.appointment_self_service import _fetch_upcoming_appointment
    conn = _FakeConn(fetchrow_results=[None])
    out = _run(_fetch_upcoming_appointment(conn, uuid4(), uuid4()))
    assert out is None


def test_fetch_upcoming_appointment_with_row():
    from app.services.appointment_self_service import _fetch_upcoming_appointment
    row = _Row(
        id=uuid4(), contact_id=uuid4(), resource_id=uuid4(),
        service_id=uuid4(), service_code='svc',
        starts_at=datetime.now(UTC), ends_at=datetime.now(UTC),
        status='scheduled', payment_status=None,
    )
    conn = _FakeConn(fetchrow_results=[row])
    out = _run(_fetch_upcoming_appointment(conn, uuid4(), uuid4()))
    assert out is not None


# ─── _fetch_appointment ──────────────────────────────────────────────────


def test_fetch_appointment_none():
    from app.services.appointment_self_service import _fetch_appointment
    conn = _FakeConn(fetchrow_results=[None])
    out = _run(_fetch_appointment(conn, uuid4(), uuid4()))
    assert out is None


def test_fetch_appointment_with_row():
    from app.services.appointment_self_service import _fetch_appointment
    row = _Row(
        id=uuid4(), contact_id=uuid4(), resource_id=uuid4(),
        service_id=uuid4(), service_code='svc',
        starts_at=datetime.now(UTC), ends_at=datetime.now(UTC),
        status='confirmed', payment_status=None,
    )
    conn = _FakeConn(fetchrow_results=[row])
    out = _run(_fetch_appointment(conn, uuid4(), uuid4()))
    assert out['status'] == 'confirmed'


# ─── _fetch_tenant_settings ─────────────────────────────────────────────


def test_fetch_tenant_settings_no_row():
    from app.services.appointment_self_service import _fetch_tenant_settings
    conn = _FakeConn(fetchrow_results=[None])
    out = _run(_fetch_tenant_settings(conn, uuid4()))
    assert out == {}


def test_fetch_tenant_settings_with_row():
    from app.services.appointment_self_service import _fetch_tenant_settings
    conn = _FakeConn(fetchrow_results=[_Row(escalation_policy={'self_service': {}})])
    out = _run(_fetch_tenant_settings(conn, uuid4()))
    assert 'escalation_policy' in out


# ─── _too_close_to_start ────────────────────────────────────────────────


def test_too_close_to_start_returns_true_for_imminent():
    from app.services.appointment_self_service import _too_close_to_start
    # appointment is in 1 hour; default threshold > 1
    now = datetime.now(UTC)
    appointment = {'starts_at': now + timedelta(minutes=30)}
    conn = _FakeConn(fetchrow_results=[
        _Row(escalation_policy={'self_service': {'min_hours_before_start': 2}}),
    ])
    out = _run(_too_close_to_start(conn, uuid4(), appointment))
    assert out is True


def test_too_close_to_start_returns_false_for_distant():
    from app.services.appointment_self_service import _too_close_to_start
    now = datetime.now(UTC)
    appointment = {'starts_at': now + timedelta(days=5)}
    conn = _FakeConn(fetchrow_results=[
        _Row(escalation_policy={'self_service': {'min_hours_before_start': 2}}),
    ])
    out = _run(_too_close_to_start(conn, uuid4(), appointment))
    assert out is False


def test_too_close_to_start_handles_naive_starts_at():
    """starts_at without tzinfo gets UTC stamped."""
    from app.services.appointment_self_service import _too_close_to_start
    naive_future = datetime.utcnow() + timedelta(days=5)
    appointment = {'starts_at': naive_future}
    conn = _FakeConn(fetchrow_results=[None])
    out = _run(_too_close_to_start(conn, uuid4(), appointment))
    assert out is False


# ─── _schedule_auto_rebook_timeout ──────────────────────────────────────


def test_schedule_auto_rebook_timeout_inserts():
    from app.services.appointment_self_service import _schedule_auto_rebook_timeout
    job_id = uuid4()
    conn = _FakeConn(fetchrow_results=[_Row(id=job_id)])
    out = _run(_schedule_auto_rebook_timeout(
        conn,
        tenant_id=uuid4(), conversation_id=uuid4(),
        appointment_id=uuid4(), channel_id=uuid4(),
        channel_account_mode='cloud_api', minutes=30,
    ))
    assert out == job_id


def test_schedule_auto_rebook_timeout_already_exists():
    from app.services.appointment_self_service import _schedule_auto_rebook_timeout
    conn = _FakeConn(fetchrow_results=[None])
    out = _run(_schedule_auto_rebook_timeout(
        conn,
        tenant_id=uuid4(), conversation_id=uuid4(),
        appointment_id=uuid4(), channel_id=uuid4(),
        channel_account_mode='cloud_api', minutes=30,
    ))
    assert out is None


# ─── _cancel_auto_rebook_timeout ────────────────────────────────────────


def test_cancel_auto_rebook_timeout_executes():
    from app.services.appointment_self_service import _cancel_auto_rebook_timeout
    conn = _FakeConn(fetch_results=[[_Row(id=uuid4())]])
    out = _run(_cancel_auto_rebook_timeout(conn, tenant_id=uuid4(), conversation_id=uuid4()))
    assert out == 1


def test_cancel_auto_rebook_timeout_no_pending():
    from app.services.appointment_self_service import _cancel_auto_rebook_timeout
    conn = _FakeConn(fetch_results=[[]])
    out = _run(_cancel_auto_rebook_timeout(conn, tenant_id=uuid4(), conversation_id=uuid4()))
    assert out == 0


# ─── _ensure_followup_tag ──────────────────────────────────────────────


def test_ensure_followup_tag_returns_id():
    from app.services.appointment_self_service import _ensure_followup_tag
    tag_id = uuid4()
    conn = _FakeConn(fetchval_results=[tag_id])
    out = _run(_ensure_followup_tag(conn, uuid4()))
    assert out == tag_id


# ─── _persist_state ────────────────────────────────────────────────────


def test_persist_state_removes_state_on_none():
    from app.services.appointment_self_service import _persist_state
    conn = _FakeConn()
    _run(_persist_state(conn, uuid4(), {'id': uuid4(), 'metadata': {'self_service': {'a': 1}, 'other': 1}}, None))
    assert len(conn.executed) == 1


def test_persist_state_sets_state():
    from app.services.appointment_self_service import _persist_state
    conn = _FakeConn()
    _run(_persist_state(conn, uuid4(), {'id': uuid4(), 'metadata': {}}, {'step': 'X'}))
    assert len(conn.executed) == 1
