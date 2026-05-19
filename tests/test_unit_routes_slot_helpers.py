"""Test the slot-generator helpers in routes.py.

Targets `compute_free_slots`, `slot_start_minutes`, `minutes_to_hhmm`,
`_derive_health_services`, `fetch_fallback_duration` (mocked conn).
"""
from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException


# ───────── slot_start_minutes / minutes_to_hhmm ─────────────────────────


def test_slot_start_minutes_basic():
    from app.api.v1.routes import slot_start_minutes
    assert slot_start_minutes('09:00') == 540
    assert slot_start_minutes('00:00') == 0
    assert slot_start_minutes('23:59') == 23 * 60 + 59


def test_slot_start_minutes_no_minute_part():
    from app.api.v1.routes import slot_start_minutes
    assert slot_start_minutes('10') == 600


def test_slot_start_minutes_invalid_raises():
    from app.api.v1.routes import slot_start_minutes
    with pytest.raises(HTTPException) as exc_info:
        slot_start_minutes('abc')
    assert exc_info.value.status_code == 400


def test_minutes_to_hhmm():
    from app.api.v1.routes import minutes_to_hhmm
    assert minutes_to_hhmm(540) == '09:00'
    assert minutes_to_hhmm(0) == '00:00'
    assert minutes_to_hhmm(60 * 24 - 1) == '23:59'


# ───────── compute_free_slots ───────────────────────────────────────────


def test_compute_free_slots_zero_duration():
    from app.api.v1.routes import compute_free_slots
    assert compute_free_slots(
        [{'start': '09:00', 'end': '17:00'}], [], 0,
    ) == []


def test_compute_free_slots_no_franjas():
    from app.api.v1.routes import compute_free_slots
    assert compute_free_slots([], [], 30) == []


def test_compute_free_slots_no_busy_fills_franja():
    from app.api.v1.routes import compute_free_slots
    slots = compute_free_slots(
        [{'start': '09:00', 'end': '11:00'}], [], 30,
    )
    assert len(slots) == 4
    assert slots[0] == {'start_time': '09:00', 'end_time': '09:30'}


def test_compute_free_slots_with_step():
    """When step_minutes < duration, slots overlap."""
    from app.api.v1.routes import compute_free_slots
    slots = compute_free_slots(
        [{'start': '09:00', 'end': '10:00'}], [],
        duration_minutes=30, step_minutes=15,
    )
    # 09:00-09:30, 09:15-09:45, 09:30-10:00 → 3 slots
    assert len(slots) == 3


def test_compute_free_slots_busy_interval_blocks():
    from app.api.v1.routes import compute_free_slots
    # Busy 09:30-10:30, so a 30-minute slot at 09:30 or 10:00 overlaps.
    busy = [(570, 630)]
    slots = compute_free_slots(
        [{'start': '09:00', 'end': '11:00'}], busy, 30,
    )
    starts = [s['start_time'] for s in slots]
    assert '09:00' in starts
    assert '10:30' in starts
    assert '09:30' not in starts
    assert '10:00' not in starts


def test_compute_free_slots_skips_inverted_franja():
    from app.api.v1.routes import compute_free_slots
    # 11:00-09:00 is invalid (end <= start), should be skipped.
    slots = compute_free_slots(
        [{'start': '11:00', 'end': '09:00'}], [], 30,
    )
    assert slots == []


def test_compute_free_slots_short_franja_yields_no_slots():
    from app.api.v1.routes import compute_free_slots
    slots = compute_free_slots(
        [{'start': '09:00', 'end': '09:15'}], [], 30,
    )
    assert slots == []


# ───────── _derive_health_services ──────────────────────────────────────


def test_derive_health_services_api_always_ok():
    from app.api.v1.routes import _derive_health_services
    snapshot = {'workers': [], 'circuit_breakers': []}
    out = _derive_health_services(snapshot, db_ok=True, db_latency_ms=12.3)
    api = next(s for s in out if s['key'] == 'api')
    assert api['status'] == 'ok'


def test_derive_health_services_postgres_ok():
    from app.api.v1.routes import _derive_health_services
    snapshot = {'workers': [], 'circuit_breakers': []}
    out = _derive_health_services(snapshot, db_ok=True, db_latency_ms=5.5)
    pg = next(s for s in out if s['key'] == 'postgres')
    assert pg['status'] == 'ok'
    assert '5.5ms' in pg['detail']


def test_derive_health_services_postgres_down():
    from app.api.v1.routes import _derive_health_services
    snapshot = {'workers': [], 'circuit_breakers': []}
    out = _derive_health_services(snapshot, db_ok=False, db_latency_ms=None)
    pg = next(s for s in out if s['key'] == 'postgres')
    assert pg['status'] == 'down'
    assert 'sin conexión' in pg['detail']


def test_derive_health_services_workers():
    """Worker statuses are 'ok' | 'warn' | 'down' based on queue_depth."""
    from app.api.v1.routes import _derive_health_services
    snapshot = {
        'workers': [
            {'worker': 'event', 'queue_depth': 0},     # ok
            {'worker': 'extraction', 'queue_depth': 50},  # ok
            {'worker': 'scheduler', 'queue_depth': 500},  # warn
            {'worker': 'digest', 'queue_depth': 2000},    # down
        ],
        'circuit_breakers': [],
    }
    out = _derive_health_services(snapshot, db_ok=True, db_latency_ms=1.0)
    by_key = {s['key']: s for s in out}
    assert by_key['worker:event']['status'] == 'ok'
    assert by_key['worker:extraction']['status'] == 'ok'
    assert by_key['worker:scheduler']['status'] == 'warn'
    assert by_key['worker:digest']['status'] == 'down'


def test_derive_health_services_circuit_breakers():
    """Breaker statuses: 'closed' → ok, 'half_open' → warn, 'open' → down."""
    from app.api.v1.routes import _derive_health_services
    snapshot = {
        'workers': [],
        'circuit_breakers': [
            {'provider': 'ollama', 'state': 'closed'},
            {'provider': 'auth0', 'state': 'half_open'},
            {'provider': 'meta', 'state': 'open'},
        ],
    }
    out = _derive_health_services(snapshot, db_ok=True, db_latency_ms=1.0)
    by_key = {s['key']: s for s in out}
    assert by_key['provider:ollama']['status'] == 'ok'
    assert by_key['provider:auth0']['status'] == 'warn'
    assert by_key['provider:meta']['status'] == 'down'


# ───────── fetch_fallback_duration (mocked conn) ────────────────────────


class _FakeConn:
    """Minimal asyncpg-like conn that returns canned fetchval values."""
    def __init__(self, *values):
        self._vals = list(values)

    async def fetchval(self, sql, *args):
        if self._vals:
            return self._vals.pop(0)
        return None


def test_fetch_fallback_duration_returns_60_when_unset():
    from app.api.v1.routes import fetch_fallback_duration
    from uuid import uuid4
    conn = _FakeConn(None, None)

    async def _go():
        return await fetch_fallback_duration(conn, uuid4())

    assert asyncio.run(_go()) == 60


def test_fetch_fallback_duration_reads_from_first_fetchval():
    """When the first fetchval returns a JSON string with default,
    that value wins."""
    from app.api.v1.routes import fetch_fallback_duration
    from uuid import uuid4
    conn = _FakeConn('{"default": 45}')

    async def _go():
        return await fetch_fallback_duration(conn, uuid4())

    assert asyncio.run(_go()) == 45


def test_fetch_fallback_duration_invalid_json_falls_back():
    """Invalid JSON in the first fetchval falls back to the second fetchval."""
    from app.api.v1.routes import fetch_fallback_duration
    from uuid import uuid4
    # First returns invalid JSON; second returns a parsed dict
    conn = _FakeConn('not json', {'service_durations': {'default': 90}})

    async def _go():
        return await fetch_fallback_duration(conn, uuid4())

    assert asyncio.run(_go()) == 90


def test_fetch_fallback_duration_reads_from_second_fetchval():
    from app.api.v1.routes import fetch_fallback_duration
    from uuid import uuid4
    conn = _FakeConn(None, {'service_durations': {'default': 30}})

    async def _go():
        return await fetch_fallback_duration(conn, uuid4())

    assert asyncio.run(_go()) == 30


def test_fetch_fallback_duration_returns_60_when_default_invalid():
    from app.api.v1.routes import fetch_fallback_duration
    from uuid import uuid4
    conn = _FakeConn(
        '{"default": "abc"}',  # default is not int → ignored
        {'service_durations': {'default': -5}},  # negative → ignored
    )

    async def _go():
        return await fetch_fallback_duration(conn, uuid4())

    assert asyncio.run(_go()) == 60
