"""Cover remaining small gaps in app/services/segments.py."""
from __future__ import annotations


def test_emit_condition_in_with_non_list_returns_none():
    from app.services.segments import _ParamBuilder, _emit_condition
    pb = _ParamBuilder()
    # `in` op with non-list value → returns None
    out = _emit_condition(
        {'field': 'tags', 'op': 'in', 'value': 'not-a-list'}, pb,
    )
    assert out is None


def test_emit_condition_numeric_in_with_no_valid_returns_none():
    """If `in` value has no convertible numbers, returns None (covers 173)."""
    from app.services.segments import _ParamBuilder, _emit_condition
    pb = _ParamBuilder()
    out = _emit_condition(
        {'field': 'total_spent', 'op': 'in', 'value': ['abc', 'def']}, pb,
    )
    assert out is None


def test_emit_condition_lt_non_numeric_returns_none():
    """lt with non-numeric value → None (covers 173)."""
    from app.services.segments import _ParamBuilder, _emit_condition
    pb = _ParamBuilder()
    out = _emit_condition(
        {'field': 'total_spent', 'op': 'lt', 'value': 'abc'}, pb,
    )
    assert out is None


def test_emit_condition_in_window_days_invalid_returns_none():
    """in_window_days with non-numeric value → None (covers 228)."""
    from app.services.segments import _ParamBuilder, _emit_condition
    pb = _ParamBuilder()
    out = _emit_condition(
        {'field': 'total_appointments_no_show', 'op': 'in_window_days', 'value': 'abc'}, pb,
    )
    assert out is None


def test_emit_condition_unknown_op_returns_none():
    """Field with valid op but unknown specific op returns None."""
    from app.services.segments import _ParamBuilder, _emit_condition
    pb = _ParamBuilder()
    out = _emit_condition(
        {'field': 'tags', 'op': 'invalid_op', 'value': []}, pb,
    )
    assert out is None


# ═══ normalize_applies_when ════════════════════════════════════════════


def test_normalize_applies_when_non_string_returns_dict():
    from app.services.segments import normalize_applies_when
    out = normalize_applies_when({'all_of': [{'key': 'budget_tier', 'op': 'eq', 'value': 'mid'}]})
    assert isinstance(out, dict)


def test_normalize_applies_when_invalid_returns_empty():
    from app.services.segments import normalize_applies_when
    assert normalize_applies_when(None) == {}
    assert normalize_applies_when('not json') == {}
    assert normalize_applies_when({}) == {}


def test_normalize_applies_when_nested_groups():
    from app.services.segments import normalize_applies_when
    out = normalize_applies_when({
        'all_of': [
            {'any_of': [
                {'key': 'budget_tier', 'op': 'eq', 'value': 'high'},
                {'key': 'urgency_level', 'op': 'eq', 'value': 'emergency'},
            ]},
        ],
    })
    assert 'all_of' in out


# ═══ evaluate_rules contains_all / contains_any ═════════════════════════


def test_evaluate_rules_contains_all_all_match():
    from app.services.segments import evaluate_rules
    rules = {'key': 'tags', 'op': 'contains_all', 'value': ['vip', 'gold']}
    assert evaluate_rules(rules, {'tags': ['vip', 'gold', 'silver']}) is True


def test_evaluate_rules_contains_all_some_missing():
    from app.services.segments import evaluate_rules
    rules = {'key': 'tags', 'op': 'contains_all', 'value': ['vip', 'gold']}
    assert evaluate_rules(rules, {'tags': ['vip']}) is False


def test_evaluate_rules_contains_all_not_list_actual():
    """If actual is not a list, returns False (covers 668)."""
    from app.services.segments import evaluate_rules
    rules = {'key': 'tags', 'op': 'contains_all', 'value': ['vip']}
    assert evaluate_rules(rules, {'tags': 'vip'}) is False


def test_evaluate_rules_contains_any_match():
    from app.services.segments import evaluate_rules
    rules = {'key': 'tags', 'op': 'contains_any', 'value': ['vip', 'gold']}
    assert evaluate_rules(rules, {'tags': ['gold', 'other']}) is True


def test_evaluate_rules_contains_any_no_overlap():
    from app.services.segments import evaluate_rules
    rules = {'key': 'tags', 'op': 'contains_any', 'value': ['vip', 'gold']}
    assert evaluate_rules(rules, {'tags': ['bronze']}) is False
