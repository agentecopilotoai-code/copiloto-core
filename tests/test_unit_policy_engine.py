"""Tests for `app/services/policy_engine.py`."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta



def test_evaluate_policy_intent_complaint_or_risk_forces_handoff():
    from app.services.policy_engine import evaluate_policy
    result = evaluate_policy(
        tenant_settings={}, conversation={}, message_text='hola',
        intent='complaint_or_risk',
    )
    assert result.action == 'require_handoff'
    assert result.reason == 'intent_complaint_or_risk'
    assert result.risk_level == 'high'


def test_evaluate_policy_trigger_keyword_matches():
    from app.services.policy_engine import evaluate_policy
    result = evaluate_policy(
        tenant_settings={
            'escalation_policy': {'triggers': {'keywords': ['estafa', 'fraude']}},
        },
        conversation={},
        message_text='Esto es una estafa total',
        intent='faq',
    )
    assert result.action == 'require_handoff'
    assert 'estafa' in result.reason
    assert result.risk_level == 'high'


def test_evaluate_policy_trigger_keyword_case_insensitive():
    from app.services.policy_engine import evaluate_policy
    result = evaluate_policy(
        tenant_settings={
            'escalation_policy': {'triggers': {'keywords': ['Estafa']}},
        },
        conversation={},
        message_text='es una ESTAFA',
        intent='faq',
    )
    assert result.action == 'require_handoff'


def test_evaluate_policy_service_window_expired():
    from app.services.policy_engine import evaluate_policy
    expired = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    result = evaluate_policy(
        tenant_settings={'escalation_policy': {}},
        conversation={'service_window_expires_at': expired},
        message_text='hola',
        intent='faq',
    )
    assert result.action == 'require_handoff'
    assert result.reason == 'service_window_expired'
    assert result.risk_level == 'medium'


def test_evaluate_policy_service_window_enforcement_disabled():
    """When enforce_service_window=False, expired window doesn't trigger handoff."""
    from app.services.policy_engine import evaluate_policy
    expired = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    result = evaluate_policy(
        tenant_settings={'escalation_policy': {'enforce_service_window': False}},
        conversation={'service_window_expires_at': expired},
        message_text='hola',
        intent='faq',
    )
    assert result.action == 'continue_bot'


def test_evaluate_policy_max_bot_turns():
    from app.services.policy_engine import evaluate_policy
    result = evaluate_policy(
        tenant_settings={
            'escalation_policy': {'triggers': {'after_bot_turns': 5}},
        },
        conversation={'bot_turn_count': 10},
        message_text='hola',
        intent='faq',
    )
    assert result.action == 'require_handoff'
    assert '10/5' in result.reason


def test_evaluate_policy_consecutive_no_context():
    from app.services.policy_engine import evaluate_policy
    result = evaluate_policy(
        tenant_settings={
            'escalation_policy': {'consecutive_no_context_limit': 2},
        },
        conversation={'consecutive_no_context': 3},
        message_text='hola',
        intent='faq',
    )
    assert result.action == 'require_handoff'
    assert 'consecutive_no_context' in result.reason


def test_evaluate_policy_default_max_bot_turns_8():
    from app.services.policy_engine import evaluate_policy
    # without after_bot_turns set, default is 8
    result = evaluate_policy(
        tenant_settings={'escalation_policy': {}},
        conversation={'bot_turn_count': 10},
        message_text='hola',
        intent='faq',
    )
    assert result.action == 'require_handoff'


def test_evaluate_policy_all_pass_returns_continue_bot():
    from app.services.policy_engine import evaluate_policy
    result = evaluate_policy(
        tenant_settings={'escalation_policy': {'triggers': {'after_bot_turns': 8}}},
        conversation={'bot_turn_count': 3, 'consecutive_no_context': 0},
        message_text='hola',
        intent='faq',
    )
    assert result.action == 'continue_bot'
    assert result.reason == 'all_policies_passed'
    assert result.risk_level == 'low'


def test_evaluate_policy_escalation_policy_as_json_string():
    from app.services.policy_engine import evaluate_policy
    result = evaluate_policy(
        tenant_settings={
            'escalation_policy': '{"triggers": {"keywords": ["fuck"]}}',
        },
        conversation={},
        message_text='fuck this',
        intent='faq',
    )
    assert result.action == 'require_handoff'


def test_evaluate_policy_skips_blank_keywords():
    from app.services.policy_engine import evaluate_policy
    result = evaluate_policy(
        tenant_settings={
            'escalation_policy': {'triggers': {'keywords': ['', '   ', 'real']}},
        },
        conversation={},
        message_text='real keyword here',
        intent='faq',
    )
    assert result.action == 'require_handoff'
    assert 'real' in result.reason


def test_evaluate_policy_no_window_no_handoff():
    from app.services.policy_engine import evaluate_policy
    result = evaluate_policy(
        tenant_settings={'escalation_policy': {}},
        conversation={'service_window_expires_at': None},
        message_text='hola', intent='faq',
    )
    assert result.action == 'continue_bot'


def test_parse_json_helpers():
    from app.services.policy_engine import _parse_json, _to_positive_int, _parse_datetime
    assert _parse_json({'k': 'v'}) == {'k': 'v'}
    assert _parse_json('{"k": 1}') == {'k': 1}
    assert _parse_json('not json') == {}
    assert _parse_json(None) == {}

    assert _to_positive_int(5, default=10) == 5
    assert _to_positive_int(0, default=10) == 10
    assert _to_positive_int(-3, default=10) == 10
    assert _to_positive_int('abc', default=10) == 10
    assert _to_positive_int(None, default=10) == 10

    now = datetime.now(UTC)
    assert _parse_datetime(now) is now
    parsed = _parse_datetime(now.isoformat())
    assert parsed is not None
    assert _parse_datetime('not iso') is None
    assert _parse_datetime(None) is None
    assert _parse_datetime(42) is None
