"""Static tests for app/services/policy_engine.py — 20+ cases covering all 5 rules."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.policy_engine import PolicyResult, evaluate_policy, _parse_json, _to_positive_int, _parse_datetime


# ── Fixtures ──────────────────────────────────────────────────────────────────

def base_settings(**overrides):
    s = {
        'max_bot_turns': 8,
        'escalation_policy': {
            'risk_keywords': [],
            'enforce_service_window': True,
            'consecutive_no_context_limit': 2,
        },
    }
    s.update(overrides)
    return s


def base_conversation(**overrides):
    c = {
        'bot_turn_count': 0,
        'consecutive_no_context': 0,
        'service_window_expires_at': None,
    }
    c.update(overrides)
    return c


def _future(hours: int = 1) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def _past(hours: int = 1) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


# ── Rule 1: complaint_or_risk intent ─────────────────────────────────────────

def test_rule1_complaint_or_risk_forces_handoff():
    result = evaluate_policy(base_settings(), base_conversation(), 'necesito ayuda', 'complaint_or_risk')
    assert result.action == 'require_handoff'
    assert result.reason == 'intent_complaint_or_risk'
    assert result.risk_level == 'high'


def test_rule1_complaint_or_risk_takes_priority_over_keywords():
    settings = base_settings(escalation_policy={'risk_keywords': ['urgente'], 'enforce_service_window': False})
    result = evaluate_policy(settings, base_conversation(), 'esto es urgente', 'complaint_or_risk')
    assert result.action == 'require_handoff'
    assert result.reason == 'intent_complaint_or_risk'
    assert result.risk_level == 'high'


def test_rule1_complaint_or_risk_ignores_max_turns():
    result = evaluate_policy(base_settings(), base_conversation(bot_turn_count=999), 'msg', 'complaint_or_risk')
    assert result.action == 'require_handoff'
    assert result.reason == 'intent_complaint_or_risk'


def test_rule1_non_complaint_intent_does_not_trigger():
    result = evaluate_policy(base_settings(), base_conversation(), 'hola', 'greeting')
    assert result.action == 'continue_bot'


# ── Rule 2: risk keywords ─────────────────────────────────────────────────────

def test_rule2_risk_keyword_triggers_handoff():
    settings = base_settings(escalation_policy={'risk_keywords': ['demanda', 'fraude']})
    result = evaluate_policy(settings, base_conversation(), 'quiero interponer una demanda', 'faq')
    assert result.action == 'require_handoff'
    assert 'demanda' in result.reason
    assert result.risk_level == 'high'


def test_rule2_risk_keyword_case_insensitive():
    settings = base_settings(escalation_policy={'risk_keywords': ['URGENTE']})
    result = evaluate_policy(settings, base_conversation(), 'esto es urgente', 'faq')
    assert result.action == 'require_handoff'


def test_rule2_partial_word_match():
    settings = base_settings(escalation_policy={'risk_keywords': ['legal']})
    result = evaluate_policy(settings, base_conversation(), 'quiero asesoría legal ahora', 'faq')
    assert result.action == 'require_handoff'


def test_rule2_no_keyword_match_continues():
    settings = base_settings(escalation_policy={'risk_keywords': ['demanda']})
    result = evaluate_policy(settings, base_conversation(), 'tengo una pregunta', 'faq')
    assert result.action == 'continue_bot'


def test_rule2_empty_risk_keywords_continues():
    settings = base_settings(escalation_policy={'risk_keywords': []})
    result = evaluate_policy(settings, base_conversation(), 'hola', 'greeting')
    assert result.action == 'continue_bot'


def test_rule2_risk_keywords_json_string():
    import json
    settings = base_settings(
        escalation_policy=json.dumps({'risk_keywords': ['amenaza'], 'enforce_service_window': False})
    )
    result = evaluate_policy(settings, base_conversation(), 'voy a poner una amenaza', 'faq')
    assert result.action == 'require_handoff'


# ── Rule 3: service window expired ───────────────────────────────────────────

def test_rule3_expired_window_triggers_handoff():
    conv = base_conversation(service_window_expires_at=_past(hours=2))
    result = evaluate_policy(base_settings(), conv, 'hola', 'greeting')
    assert result.action == 'require_handoff'
    assert result.reason == 'service_window_expired'
    assert result.risk_level == 'medium'


def test_rule3_future_window_continues():
    conv = base_conversation(service_window_expires_at=_future(hours=2))
    result = evaluate_policy(base_settings(), conv, 'hola', 'greeting')
    assert result.action == 'continue_bot'


def test_rule3_no_window_continues():
    conv = base_conversation(service_window_expires_at=None)
    result = evaluate_policy(base_settings(), conv, 'hola', 'greeting')
    assert result.action == 'continue_bot'


def test_rule3_enforce_false_ignores_expired_window():
    settings = base_settings(escalation_policy={'enforce_service_window': False})
    conv = base_conversation(service_window_expires_at=_past(hours=5))
    result = evaluate_policy(settings, conv, 'hola', 'greeting')
    assert result.action == 'continue_bot'


def test_rule3_iso_string_datetime():
    expired = (_past(hours=1)).isoformat()
    conv = base_conversation(service_window_expires_at=expired)
    result = evaluate_policy(base_settings(), conv, 'hola', 'greeting')
    assert result.action == 'require_handoff'


# ── Rule 4: max bot turns ─────────────────────────────────────────────────────

def test_rule4_max_bot_turns_exact_limit():
    settings = base_settings(max_bot_turns=5)
    conv = base_conversation(bot_turn_count=5)
    result = evaluate_policy(settings, conv, 'msg', 'faq')
    assert result.action == 'require_handoff'
    assert 'max_bot_turns_exceeded' in result.reason
    assert result.risk_level == 'medium'


def test_rule4_below_limit_continues():
    settings = base_settings(max_bot_turns=5)
    conv = base_conversation(bot_turn_count=4)
    result = evaluate_policy(settings, conv, 'msg', 'faq')
    assert result.action == 'continue_bot'


def test_rule4_default_limit_applied():
    settings = {'max_bot_turns': None, 'escalation_policy': {}}
    conv = base_conversation(bot_turn_count=8)
    result = evaluate_policy(settings, conv, 'msg', 'faq')
    assert result.action == 'require_handoff'


# ── Rule 5: consecutive no-context ───────────────────────────────────────────

def test_rule5_consecutive_no_context_at_limit():
    settings = base_settings(escalation_policy={'consecutive_no_context_limit': 2})
    conv = base_conversation(consecutive_no_context=2)
    result = evaluate_policy(settings, conv, 'msg', 'faq')
    assert result.action == 'require_handoff'
    assert 'consecutive_no_context' in result.reason
    assert result.risk_level == 'medium'


def test_rule5_below_consecutive_limit_continues():
    settings = base_settings(escalation_policy={'consecutive_no_context_limit': 3})
    conv = base_conversation(consecutive_no_context=2)
    result = evaluate_policy(settings, conv, 'msg', 'faq')
    assert result.action == 'continue_bot'


def test_rule5_default_limit_of_two():
    settings = base_settings(escalation_policy={})
    conv = base_conversation(consecutive_no_context=2)
    result = evaluate_policy(settings, conv, 'msg', 'faq')
    assert result.action == 'require_handoff'


# ── All-pass case ─────────────────────────────────────────────────────────────

def test_all_rules_pass_returns_continue_bot():
    result = evaluate_policy(
        base_settings(),
        base_conversation(bot_turn_count=3, consecutive_no_context=0, service_window_expires_at=_future()),
        'quisiera agendar una cita',
        'book_appointment',
    )
    assert result.action == 'continue_bot'
    assert result.reason == 'all_policies_passed'
    assert result.risk_level == 'low'


# ── Priority: Rule 1 beats Rule 2 ────────────────────────────────────────────

def test_priority_rule1_beats_rule2():
    settings = base_settings(escalation_policy={'risk_keywords': ['algo'], 'enforce_service_window': False})
    result = evaluate_policy(settings, base_conversation(), 'algo', 'complaint_or_risk')
    assert result.reason == 'intent_complaint_or_risk'


# ── Priority: Rule 2 beats Rule 3 ────────────────────────────────────────────

def test_priority_rule2_beats_rule3():
    settings = base_settings(escalation_policy={'risk_keywords': ['demanda'], 'enforce_service_window': True})
    conv = base_conversation(service_window_expires_at=_past())
    result = evaluate_policy(settings, conv, 'voy a demandar', 'faq')
    assert 'demanda' in result.reason  # Rule 2 fires before Rule 3


# ── Helper function unit tests ────────────────────────────────────────────────

def test_parse_json_valid_dict():
    assert _parse_json({'a': 1}) == {'a': 1}


def test_parse_json_valid_string():
    assert _parse_json('{"x": 2}') == {'x': 2}


def test_parse_json_invalid_string():
    assert _parse_json('not-json') == {}


def test_parse_json_none():
    assert _parse_json(None) == {}


def test_to_positive_int_valid():
    assert _to_positive_int(5, default=8) == 5


def test_to_positive_int_zero_uses_default():
    assert _to_positive_int(0, default=8) == 8


def test_to_positive_int_negative_uses_default():
    assert _to_positive_int(-1, default=8) == 8


def test_to_positive_int_none_uses_default():
    assert _to_positive_int(None, default=8) == 8


def test_parse_datetime_none():
    assert _parse_datetime(None) is None


def test_parse_datetime_datetime_object():
    dt = datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert _parse_datetime(dt) is dt


def test_parse_datetime_valid_iso_string():
    result = _parse_datetime('2025-01-01T12:00:00+00:00')
    assert result is not None
    assert result.year == 2025


def test_parse_datetime_invalid_string():
    assert _parse_datetime('not-a-date') is None


# ── PolicyResult dataclass ────────────────────────────────────────────────────

def test_policy_result_fields():
    r = PolicyResult(action='continue_bot', reason='all_policies_passed', risk_level='low')
    assert r.action == 'continue_bot'
    assert r.reason == 'all_policies_passed'
    assert r.risk_level == 'low'
