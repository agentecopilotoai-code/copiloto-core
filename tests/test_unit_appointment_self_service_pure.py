"""Pure-helper tests for `app/services/appointment_self_service.py`."""
from __future__ import annotations



# ───────── _parse_json ────────────────────────────────────────────────────


def test_parse_json_dict_passthrough():
    from app.services.appointment_self_service import _parse_json
    d = {'k': 'v'}
    assert _parse_json(d, {}) is d


def test_parse_json_json_string():
    from app.services.appointment_self_service import _parse_json
    assert _parse_json('{"k": 1}', {}) == {'k': 1}


def test_parse_json_invalid_falls_back():
    from app.services.appointment_self_service import _parse_json
    assert _parse_json('garbage', ['fb']) == ['fb']


def test_parse_json_none_falls_back():
    from app.services.appointment_self_service import _parse_json
    assert _parse_json(None, []) == []


# ───────── _self_service_state ──────────────────────────────────────────


def test_self_service_state_empty():
    from app.services.appointment_self_service import _self_service_state
    assert _self_service_state({'metadata': {}}) == {}


def test_self_service_state_returns_persisted():
    from app.services.appointment_self_service import _self_service_state
    conv = {'metadata': {'self_service': {'flow': 'cancel'}}}
    assert _self_service_state(conv) == {'flow': 'cancel'}


def test_self_service_state_json_string_metadata():
    from app.services.appointment_self_service import _self_service_state
    conv = {'metadata': '{"self_service": {"step": "awaiting_cancel_confirm"}}'}
    assert _self_service_state(conv) == {'step': 'awaiting_cancel_confirm'}


def test_self_service_state_non_dict_returns_empty():
    from app.services.appointment_self_service import _self_service_state
    conv = {'metadata': {'self_service': 'not-a-dict'}}
    assert _self_service_state(conv) == {}


# ───────── _interactive_id ───────────────────────────────────────────────


def test_interactive_id_extracts():
    from app.services.appointment_self_service import _interactive_id
    msg = {'payload': {'interactive_id': 'cancel:appt-1'}}
    assert _interactive_id(msg) == ('cancel', 'appt-1')


def test_interactive_id_no_match():
    from app.services.appointment_self_service import _interactive_id
    assert _interactive_id({'payload': {}}) == (None, None)
    assert _interactive_id({'payload': {'interactive_id': 'no-colon'}}) == (None, None)


# ───────── min_hours_before_start ────────────────────────────────────────


def test_min_hours_before_start_default_for_invalid():
    from app.services.appointment_self_service import (
        DEFAULT_MIN_HOURS_BEFORE_START,
        min_hours_before_start,
    )
    expected = float(DEFAULT_MIN_HOURS_BEFORE_START)
    assert min_hours_before_start(None) == expected
    assert min_hours_before_start('not json') == expected
    assert min_hours_before_start({}) == expected
    assert min_hours_before_start({'self_service': 'not-a-dict'}) == expected


def test_min_hours_before_start_reads_from_policy():
    from app.services.appointment_self_service import min_hours_before_start
    policy = {'self_service': {'min_hours_before_start': 24}}
    assert min_hours_before_start(policy) == 24.0


def test_min_hours_before_start_json_string():
    from app.services.appointment_self_service import min_hours_before_start
    assert min_hours_before_start(
        '{"self_service": {"min_hours_before_start": 6}}',
    ) == 6.0


def test_min_hours_before_start_negative_falls_back():
    from app.services.appointment_self_service import (
        DEFAULT_MIN_HOURS_BEFORE_START,
        min_hours_before_start,
    )
    policy = {'self_service': {'min_hours_before_start': -5}}
    assert min_hours_before_start(policy) == float(DEFAULT_MIN_HOURS_BEFORE_START)


def test_min_hours_before_start_invalid_value_falls_back():
    from app.services.appointment_self_service import (
        DEFAULT_MIN_HOURS_BEFORE_START,
        min_hours_before_start,
    )
    policy = {'self_service': {'min_hours_before_start': 'abc'}}
    assert min_hours_before_start(policy) == float(DEFAULT_MIN_HOURS_BEFORE_START)


# ───────── auto_rebook_timeout_minutes ───────────────────────────────────


def test_auto_rebook_timeout_minutes_default():
    from app.services.appointment_self_service import (
        DEFAULT_AUTO_REBOOK_TIMEOUT_MINUTES,
        auto_rebook_timeout_minutes,
    )
    assert auto_rebook_timeout_minutes(None) == DEFAULT_AUTO_REBOOK_TIMEOUT_MINUTES
    assert auto_rebook_timeout_minutes({}) == DEFAULT_AUTO_REBOOK_TIMEOUT_MINUTES
    assert auto_rebook_timeout_minutes('not json') == DEFAULT_AUTO_REBOOK_TIMEOUT_MINUTES


def test_auto_rebook_timeout_minutes_reads_value():
    from app.services.appointment_self_service import auto_rebook_timeout_minutes
    assert auto_rebook_timeout_minutes({'auto_rebook_timeout_minutes': 60}) == 60


def test_auto_rebook_timeout_minutes_json_string():
    from app.services.appointment_self_service import auto_rebook_timeout_minutes
    assert auto_rebook_timeout_minutes(
        '{"auto_rebook_timeout_minutes": 45}',
    ) == 45


def test_auto_rebook_timeout_minutes_invalid_value_falls_back():
    from app.services.appointment_self_service import (
        DEFAULT_AUTO_REBOOK_TIMEOUT_MINUTES,
        auto_rebook_timeout_minutes,
    )
    assert auto_rebook_timeout_minutes(
        {'auto_rebook_timeout_minutes': 'abc'},
    ) == DEFAULT_AUTO_REBOOK_TIMEOUT_MINUTES


def test_auto_rebook_timeout_minutes_clamps_low():
    from app.services.appointment_self_service import (
        MIN_AUTO_REBOOK_TIMEOUT_MINUTES,
        auto_rebook_timeout_minutes,
    )
    assert auto_rebook_timeout_minutes(
        {'auto_rebook_timeout_minutes': 1},
    ) == MIN_AUTO_REBOOK_TIMEOUT_MINUTES


def test_auto_rebook_timeout_minutes_clamps_high():
    from app.services.appointment_self_service import (
        MAX_AUTO_REBOOK_TIMEOUT_MINUTES,
        auto_rebook_timeout_minutes,
    )
    assert auto_rebook_timeout_minutes(
        {'auto_rebook_timeout_minutes': 99999},
    ) == MAX_AUTO_REBOOK_TIMEOUT_MINUTES


def test_auto_rebook_timeout_minutes_in_range_returns_unchanged():
    from app.services.appointment_self_service import auto_rebook_timeout_minutes
    assert auto_rebook_timeout_minutes(
        {'auto_rebook_timeout_minutes': 30},
    ) == 30


# ───────── flow + step constants exposed ─────────────────────────────────


def test_flow_constants():
    from app.services.appointment_self_service import (
        FLOW_CANCEL,
        FLOW_RESCHEDULE,
    )
    assert FLOW_CANCEL == 'cancel'
    assert FLOW_RESCHEDULE == 'reschedule'


def test_step_constants():
    from app.services.appointment_self_service import (
        STEP_AWAITING_CANCEL_CONFIRM,
        STEP_AWAITING_RESCHEDULE_SLOT,
        STEP_COMPLETED,
    )
    assert STEP_COMPLETED == 'completed'
    assert STEP_AWAITING_CANCEL_CONFIRM == 'awaiting_cancel_confirm'
    assert STEP_AWAITING_RESCHEDULE_SLOT == 'awaiting_reschedule_slot'


def test_auto_rebook_timeout_kind_constant():
    from app.services.appointment_self_service import AUTO_REBOOK_TIMEOUT_KIND
    assert AUTO_REBOOK_TIMEOUT_KIND == 'auto_rebook_timeout'
