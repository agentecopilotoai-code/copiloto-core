"""Pure-helper + mocked-conn tests for `app/services/booking_flow.py`.

Targets the uncovered helpers identified from coverage JSON. These tests
avoid the DB roundtrip — the few DB-flavoured ones use a tiny in-memory
async stub instead of asyncpg.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4



# ───────── _parse_json ────────────────────────────────────────────────────


def test_parse_json_dict_passthrough():
    from app.services.booking_flow import _parse_json
    d = {'foo': 'bar'}
    assert _parse_json(d, {}) is d


def test_parse_json_string_decodes():
    from app.services.booking_flow import _parse_json
    assert _parse_json('{"x": 1}', {}) == {'x': 1}


def test_parse_json_invalid_returns_fallback():
    from app.services.booking_flow import _parse_json
    assert _parse_json('not json', {'fallback': True}) == {'fallback': True}


def test_parse_json_none_returns_fallback():
    from app.services.booking_flow import _parse_json
    assert _parse_json(None, ['fb']) == ['fb']


# ───────── _booking_state ─────────────────────────────────────────────────


def test_booking_state_empty_metadata():
    from app.services.booking_flow import _booking_state
    assert _booking_state({'metadata': {}}) == {}


def test_booking_state_returns_persisted_state():
    from app.services.booking_flow import _booking_state
    conv = {'metadata': {'booking_flow': {'step': 'awaiting_service'}}}
    assert _booking_state(conv) == {'step': 'awaiting_service'}


def test_booking_state_with_json_string_metadata():
    from app.services.booking_flow import _booking_state
    conv = {'metadata': '{"booking_flow": {"step": "awaiting_slot"}}'}
    assert _booking_state(conv) == {'step': 'awaiting_slot'}


def test_booking_state_invalid_metadata_returns_empty():
    from app.services.booking_flow import _booking_state
    conv = {'metadata': 'broken json'}
    assert _booking_state(conv) == {}


def test_booking_state_non_dict_returns_empty():
    from app.services.booking_flow import _booking_state
    conv = {'metadata': {'booking_flow': 'not-a-dict'}}
    assert _booking_state(conv) == {}


# ───────── _interactive_id ────────────────────────────────────────────────


def test_interactive_id_extracts_prefix_and_value():
    from app.services.booking_flow import _interactive_id
    msg = {'payload': {'interactive_id': 'book_service:uuid-1234'}}
    assert _interactive_id(msg) == ('book_service', 'uuid-1234')


def test_interactive_id_returns_none_when_missing():
    from app.services.booking_flow import _interactive_id
    assert _interactive_id({'payload': {}}) == (None, None)


def test_interactive_id_returns_none_when_no_colon():
    from app.services.booking_flow import _interactive_id
    msg = {'payload': {'interactive_id': 'no-colon'}}
    assert _interactive_id(msg) == (None, None)


def test_interactive_id_with_json_string_payload():
    from app.services.booking_flow import _interactive_id
    msg = {'payload': '{"interactive_id": "book_slot:09:00"}'}
    prefix, value = _interactive_id(msg)
    assert prefix == 'book_slot'
    # value is everything after first colon
    assert value == '09:00'


# ───────── _qualification_facts_from_conversation ────────────────────────


def test_qualification_facts_empty_when_no_metadata():
    from app.services.booking_flow import _qualification_facts_from_conversation
    assert _qualification_facts_from_conversation({'metadata': {}}) == {}


def test_qualification_facts_returns_keyed_facts():
    from app.services.booking_flow import _qualification_facts_from_conversation
    conv = {
        'metadata': {
            'qualification': {
                'facts': {'budget_tier': 'mid', 'urgency_level': 'high'},
            },
        },
    }
    facts = _qualification_facts_from_conversation(conv)
    assert facts['budget_tier'] == 'mid'
    assert facts['urgency_level'] == 'high'


def test_qualification_facts_falls_back_to_presets():
    """When `facts` is missing, the helper synthesizes from budget_tier/urgency_level dicts."""
    from app.services.booking_flow import _qualification_facts_from_conversation
    conv = {
        'metadata': {
            'qualification': {
                'budget_tier': {'tier_value': 'low', 'tier_label': 'Bajo'},
                'urgency_level': 'medium',
            },
        },
    }
    facts = _qualification_facts_from_conversation(conv)
    assert facts.get('budget_tier') == 'low'
    assert facts.get('budget_label') == 'Bajo'
    assert facts.get('urgency_level') == 'medium'


def test_qualification_facts_with_non_dict_qualification():
    from app.services.booking_flow import _qualification_facts_from_conversation
    conv = {'metadata': {'qualification': 'not-a-dict'}}
    assert _qualification_facts_from_conversation(conv) == {}


# ───────── _filter_services_by_qualification ─────────────────────────────


def test_filter_services_by_qualification_empty_facts_passthrough():
    from app.services.booking_flow import _filter_services_by_qualification
    services = [{'id': 's1', 'applies_when': None}]
    assert _filter_services_by_qualification(services, {}) == services


def test_filter_services_by_qualification_keeps_no_rules():
    from app.services.booking_flow import _filter_services_by_qualification
    services = [
        {'id': 's1', 'applies_when': None},
        {'id': 's2', 'applies_when': {}},
    ]
    out = _filter_services_by_qualification(services, {'budget_tier': 'mid'})
    assert len(out) == 2


# ───────── _working_hours_for_date ────────────────────────────────────────


def test_working_hours_for_date_returns_franjas():
    from app.services.booking_flow import _working_hours_for_date
    caps = {'working_hours': {'mon': [{'start': '09:00', 'end': '17:00'}]}}
    franjas = _working_hours_for_date(caps, date(2026, 5, 18))  # Monday
    assert franjas == [{'start': '09:00', 'end': '17:00'}]


def test_working_hours_for_date_empty_when_off_day():
    from app.services.booking_flow import _working_hours_for_date
    caps = {'working_hours': {'mon': [{'start': '09:00', 'end': '17:00'}]}}
    franjas = _working_hours_for_date(caps, date(2026, 5, 17))  # Sunday
    assert franjas == []


def test_working_hours_for_date_handles_malformed():
    from app.services.booking_flow import _working_hours_for_date
    assert _working_hours_for_date(None, date(2026, 5, 18)) == []
    assert _working_hours_for_date('not json', date(2026, 5, 18)) == []
    assert _working_hours_for_date({}, date(2026, 5, 18)) == []
    assert _working_hours_for_date({'working_hours': 'bad'}, date(2026, 5, 18)) == []


def test_working_hours_for_date_skips_invalid_entries():
    from app.services.booking_flow import _working_hours_for_date
    caps = {
        'working_hours': {
            'mon': [
                'not-a-dict',  # skipped
                {'start': '09:00'},  # missing end
                {'start': '09:00', 'end': '12:00'},  # ok
            ],
        },
    }
    franjas = _working_hours_for_date(caps, date(2026, 5, 18))
    assert franjas == [{'start': '09:00', 'end': '12:00'}]


# ───────── _hhmm_to_minutes / _minutes_to_hhmm ───────────────────────────


def test_hhmm_to_minutes_basic():
    from app.services.booking_flow import _hhmm_to_minutes
    assert _hhmm_to_minutes('09:30') == 570
    assert _hhmm_to_minutes('00:00') == 0
    assert _hhmm_to_minutes('23:59') == 23 * 60 + 59


def test_hhmm_to_minutes_no_minute_part():
    from app.services.booking_flow import _hhmm_to_minutes
    assert _hhmm_to_minutes('10') == 600


def test_minutes_to_hhmm_basic():
    from app.services.booking_flow import _minutes_to_hhmm
    assert _minutes_to_hhmm(0) == '00:00'
    assert _minutes_to_hhmm(570) == '09:30'
    assert _minutes_to_hhmm(60 * 24 - 1) == '23:59'


# ───────── compute_free_slots ────────────────────────────────────────────


def test_compute_free_slots_zero_duration_returns_empty():
    from app.services.booking_flow import compute_free_slots
    assert compute_free_slots([{'start': '09:00', 'end': '17:00'}], [], 0) == []


def test_compute_free_slots_no_franjas_returns_empty():
    from app.services.booking_flow import compute_free_slots
    assert compute_free_slots([], [], 30) == []


def test_compute_free_slots_no_busy_fills_franja():
    from app.services.booking_flow import compute_free_slots
    slots = compute_free_slots(
        [{'start': '09:00', 'end': '11:00'}], [], 30,
    )
    assert len(slots) == 4
    assert slots[0] == {'start_time': '09:00', 'end_time': '09:30'}
    assert slots[-1] == {'start_time': '10:30', 'end_time': '11:00'}


def test_compute_free_slots_skips_busy_overlap():
    from app.services.booking_flow import compute_free_slots
    # Busy 09:30-10:30 → 09:00-09:30 ok, 09:30-10:00 BUSY, 10:00-10:30 BUSY,
    # 10:30-11:00 ok
    busy = [(570, 630)]
    slots = compute_free_slots(
        [{'start': '09:00', 'end': '11:00'}], busy, 30,
    )
    assert {'start_time': '09:00', 'end_time': '09:30'} in slots
    assert {'start_time': '10:30', 'end_time': '11:00'} in slots
    assert all('09:30' not in s['start_time'] for s in slots)


def test_compute_free_slots_too_short_franja_skipped():
    from app.services.booking_flow import compute_free_slots
    slots = compute_free_slots(
        [{'start': '09:00', 'end': '09:15'}], [], 30,
    )
    assert slots == []


# ───────── _format_price ──────────────────────────────────────────────────


def test_format_price_none_returns_empty():
    from app.services.booking_flow import _format_price
    assert _format_price(None, 'COP') == ''


def test_format_price_invalid_returns_empty():
    from app.services.booking_flow import _format_price
    assert _format_price('not a number', 'COP') == ''


def test_format_price_numeric_returns_formatted():
    from app.services.booking_flow import _format_price
    out = _format_price(50000, 'COP')
    assert isinstance(out, str)
    assert out  # non-empty


def test_format_price_default_currency():
    from app.services.booking_flow import _format_price
    out = _format_price(100, None)
    assert isinstance(out, str)


# ───────── _resolve_date_choice ──────────────────────────────────────────


def test_resolve_date_choice_today():
    from app.services.booking_flow import _resolve_date_choice
    today = datetime.now(UTC).date()
    assert _resolve_date_choice('today') == today


def test_resolve_date_choice_tomorrow():
    from app.services.booking_flow import _resolve_date_choice
    expected = datetime.now(UTC).date() + timedelta(days=1)
    assert _resolve_date_choice('tomorrow') == expected


def test_resolve_date_choice_unknown_returns_none():
    from app.services.booking_flow import _resolve_date_choice
    assert _resolve_date_choice('other') is None
    assert _resolve_date_choice('') is None


# ───────── _normalize_phone_query ─────────────────────────────────────────


def test_normalize_phone_query_extracts_digits():
    from app.services.booking_flow import _normalize_phone_query
    assert _normalize_phone_query('300 555 1212') == '3005551212'
    assert _normalize_phone_query('+57 300-555-1212') == '573005551212'


def test_normalize_phone_query_returns_none_for_short():
    from app.services.booking_flow import _normalize_phone_query
    assert _normalize_phone_query('123') is None
    assert _normalize_phone_query('no digits here') is None


# ───────── _contact_has_referrer ──────────────────────────────────────────


def test_contact_has_referrer_none():
    from app.services.booking_flow import _contact_has_referrer
    assert _contact_has_referrer(None) is False


def test_contact_has_referrer_with_referrer_contact_id():
    from app.services.booking_flow import _contact_has_referrer
    contact = {'referrer_contact_id': str(uuid4())}
    assert _contact_has_referrer(contact) is True


def test_contact_has_referrer_with_lead_source_text():
    from app.services.booking_flow import _contact_has_referrer
    contact = {
        'referrer_contact_id': None,
        'lead_source': {'referred_by_name': 'Maria'},
    }
    assert _contact_has_referrer(contact) is True


def test_contact_has_referrer_with_json_string_lead_source():
    from app.services.booking_flow import _contact_has_referrer
    contact = {
        'referrer_contact_id': None,
        'lead_source': '{"referred_by_name": "Carlos"}',
    }
    assert _contact_has_referrer(contact) is True


def test_contact_has_referrer_empty():
    from app.services.booking_flow import _contact_has_referrer
    assert _contact_has_referrer({}) is False
    assert _contact_has_referrer({'referrer_contact_id': None, 'lead_source': {}}) is False


# ───────── _specialist_caption ────────────────────────────────────────────


def test_specialist_caption_includes_name():
    from app.services.booking_flow import _specialist_caption
    resource = {'name': 'Dr. House'}
    caption = _specialist_caption(resource)
    assert isinstance(caption, str)
    assert 'Dr. House' in caption
