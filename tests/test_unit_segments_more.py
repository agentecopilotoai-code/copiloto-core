"""More tests for `app/services/segments.py` — focused on the SQL builder
and operator coverage (no DB). Complements test_unit_segments_evaluator.py
which exercises the in-memory evaluator path."""
from __future__ import annotations

import pytest


# ───────── _coerce_number ────────────────────────────────────────────────


def test_coerce_number_int():
    from app.services.segments import _coerce_number
    assert _coerce_number(5) == 5


def test_coerce_number_float():
    from app.services.segments import _coerce_number
    assert _coerce_number(3.14) == 3.14


def test_coerce_number_string_int():
    from app.services.segments import _coerce_number
    assert _coerce_number('42') == 42


def test_coerce_number_string_float():
    from app.services.segments import _coerce_number
    assert _coerce_number('3.14') == 3.14


def test_coerce_number_invalid():
    from app.services.segments import _coerce_number
    assert _coerce_number('abc') is None
    assert _coerce_number(None) is None
    assert _coerce_number(True) is None  # bool excluded


# ───────── _valid_qualification_key ──────────────────────────────────────


def test_valid_qualification_key():
    from app.services.segments import _valid_qualification_key
    assert _valid_qualification_key('budget_tier') is True
    assert _valid_qualification_key('abc123') is True
    assert _valid_qualification_key('') is False
    # Special chars rejected
    assert _valid_qualification_key('with-dash') is False
    assert _valid_qualification_key('with space') is False
    # Length cap
    assert _valid_qualification_key('x' * 61) is False


# ───────── normalize_rules ───────────────────────────────────────────────


def test_normalize_rules_empty_inputs():
    from app.services.segments import normalize_rules
    assert normalize_rules(None) == {}
    assert normalize_rules('') == {}
    assert normalize_rules('not json') == {}
    assert normalize_rules({}) == {}


def test_normalize_rules_json_string():
    from app.services.segments import normalize_rules
    out = normalize_rules('{"field":"tags","op":"is_empty"}')
    assert out == {'all_of': [{'field': 'tags', 'op': 'is_empty'}]}


def test_normalize_rules_strips_unknown_fields():
    from app.services.segments import normalize_rules
    out = normalize_rules({'field': 'unknown_field', 'op': 'eq', 'value': 1})
    assert out == {}


def test_normalize_rules_strips_unknown_ops():
    from app.services.segments import normalize_rules
    # 'contains' is not a valid op for 'tags'
    out = normalize_rules({'field': 'tags', 'op': 'contains', 'value': ['vip']})
    assert out == {}


def test_normalize_rules_keeps_valid_all_of():
    from app.services.segments import normalize_rules
    rules = {
        'all_of': [
            {'field': 'tags', 'op': 'is_empty'},
            {'field': 'total_spent', 'op': 'gt', 'value': 100000},
        ],
    }
    out = normalize_rules(rules)
    assert out['all_of'] == rules['all_of']


def test_normalize_rules_keeps_valid_any_of():
    from app.services.segments import normalize_rules
    rules = {
        'any_of': [
            {'field': 'tags', 'op': 'contains_any', 'value': ['vip']},
            {'field': 'lead_source.channel', 'op': 'eq', 'value': 'web'},
        ],
    }
    out = normalize_rules(rules)
    assert out['any_of'] == rules['any_of']


def test_normalize_rules_drops_invalid_nested():
    from app.services.segments import normalize_rules
    rules = {
        'all_of': [
            {'field': 'tags', 'op': 'is_empty'},
            {'field': 'foo', 'op': 'bar'},  # dropped
        ],
    }
    out = normalize_rules(rules)
    assert len(out['all_of']) == 1


def test_normalize_rules_qualification_keys_pass():
    from app.services.segments import normalize_rules
    rules = {
        'all_of': [
            {'field': 'qualification.budget_tier', 'op': 'eq', 'value': 'high'},
        ],
    }
    out = normalize_rules(rules)
    assert out['all_of'][0]['field'] == 'qualification.budget_tier'


def test_normalize_rules_qualification_invalid_key():
    from app.services.segments import normalize_rules
    out = normalize_rules({
        'field': 'qualification.bad-key',
        'op': 'eq', 'value': 'x',
    })
    assert out == {}


def test_normalize_rules_nested_groups():
    """Groups within groups (one level)."""
    from app.services.segments import normalize_rules
    rules = {
        'all_of': [
            {
                'any_of': [
                    {'field': 'tags', 'op': 'is_empty'},
                    {'field': 'total_spent', 'op': 'gt', 'value': 1},
                ],
            },
        ],
    }
    out = normalize_rules(rules)
    assert 'all_of' in out
    nested = out['all_of'][0]
    assert 'any_of' in nested
    assert len(nested['any_of']) == 2


# ───────── build_segment_query — operator coverage ───────────────────────


def test_build_segment_query_uses_tenant_placeholder():
    """args[0] should be the tenant placeholder (initially None)."""
    from app.services.segments import build_segment_query
    sql, args = build_segment_query({})
    assert args[0] is None
    assert '$1' in sql
    assert 'opt_in_status' in sql
    assert 'phone_e164' in sql


def test_build_segment_query_eq_text():
    from app.services.segments import build_segment_query
    sql, args = build_segment_query({
        'field': 'lead_source.channel', 'op': 'eq', 'value': 'web',
    })
    assert "= $2" in sql
    assert 'web' in args


def test_build_segment_query_in_text():
    from app.services.segments import build_segment_query
    sql, args = build_segment_query({
        'field': 'lead_source.channel', 'op': 'in', 'value': ['web', 'wa'],
    })
    assert '= any($2::text[])' in sql
    assert ['web', 'wa'] in args


def test_build_segment_query_in_numeric():
    from app.services.segments import build_segment_query
    sql, args = build_segment_query({
        'field': 'total_appointments_completed', 'op': 'in', 'value': [1, 2],
    })
    assert '= any($2::numeric[])' in sql


def test_build_segment_query_in_filters_invalid():
    """Non-numeric values are dropped → if list becomes empty, condition omitted."""
    from app.services.segments import build_segment_query
    sql, args = build_segment_query({
        'field': 'total_appointments_completed', 'op': 'in', 'value': ['abc'],
    })
    # No condition appended
    assert '= any' not in sql


def test_build_segment_query_gt_numeric():
    from app.services.segments import build_segment_query
    sql, args = build_segment_query({
        'field': 'total_spent', 'op': 'gt', 'value': 100000,
    })
    assert ' > $2' in sql


def test_build_segment_query_between():
    from app.services.segments import build_segment_query
    sql, args = build_segment_query({
        'field': 'total_spent', 'op': 'between', 'value': [1000, 5000],
    })
    assert ' between $2 and $3' in sql


def test_build_segment_query_between_invalid_length():
    from app.services.segments import build_segment_query
    sql, args = build_segment_query({
        'field': 'total_spent', 'op': 'between', 'value': [1000],
    })
    # Condition dropped → only tenant + opt-in + phone filters
    assert 'between' not in sql


def test_build_segment_query_lt_days_ago():
    from app.services.segments import build_segment_query
    sql, args = build_segment_query({
        'field': 'last_appointment_at', 'op': 'lt_days_ago', 'value': 60,
    })
    assert "now() - ($2 * interval '1 day')" in sql


def test_build_segment_query_gte_days_ago():
    from app.services.segments import build_segment_query
    sql, args = build_segment_query({
        'field': 'last_appointment_at', 'op': 'gte_days_ago', 'value': 7,
    })
    assert "now() - ($2 * interval '1 day')" in sql


def test_build_segment_query_lt_days_ago_negative_rejected():
    from app.services.segments import build_segment_query
    sql, _ = build_segment_query({
        'field': 'last_appointment_at', 'op': 'lt_days_ago', 'value': -1,
    })
    assert 'interval' not in sql


def test_build_segment_query_is_null():
    from app.services.segments import build_segment_query
    sql, _ = build_segment_query({
        'field': 'last_appointment_at', 'op': 'is_null',
    })
    assert ' is null' in sql


def test_build_segment_query_is_not_null():
    from app.services.segments import build_segment_query
    sql, _ = build_segment_query({
        'field': 'last_appointment_at', 'op': 'is_not_null',
    })
    assert ' is not null' in sql


def test_build_segment_query_contains_any():
    from app.services.segments import build_segment_query
    sql, args = build_segment_query({
        'field': 'tags', 'op': 'contains_any', 'value': ['vip'],
    })
    assert '&&' in sql
    assert ['vip'] in args


def test_build_segment_query_contains_all():
    from app.services.segments import build_segment_query
    sql, args = build_segment_query({
        'field': 'tags', 'op': 'contains_all', 'value': ['vip', 'gold'],
    })
    assert '@>' in sql


def test_build_segment_query_is_empty():
    from app.services.segments import build_segment_query
    sql, _ = build_segment_query({
        'field': 'tags', 'op': 'is_empty',
    })
    assert 'array_length' in sql
    assert '= 0' in sql


def test_build_segment_query_is_not_empty():
    from app.services.segments import build_segment_query
    sql, _ = build_segment_query({
        'field': 'tags', 'op': 'is_not_empty',
    })
    assert 'array_length' in sql
    assert '> 0' in sql


def test_build_segment_query_in_window_days_no_show():
    from app.services.segments import build_segment_query
    sql, args = build_segment_query({
        'field': 'total_appointments_no_show',
        'op': 'in_window_days', 'value': 30,
    })
    assert 'no_show' in sql
    assert "interval '1 day'" in sql


def test_build_segment_query_qualification_eq():
    from app.services.segments import build_segment_query
    sql, args = build_segment_query({
        'field': 'qualification.budget_tier', 'op': 'eq', 'value': 'high',
    })
    assert "c.qualification->>'budget_tier' = $2" in sql
    assert 'high' in args


def test_build_segment_query_qualification_in():
    from app.services.segments import build_segment_query
    sql, args = build_segment_query({
        'field': 'qualification.budget_tier', 'op': 'in',
        'value': ['high', 'mid'],
    })
    assert 'any($2::text[])' in sql


def test_build_segment_query_qualification_is_null():
    from app.services.segments import build_segment_query
    sql, _ = build_segment_query({
        'field': 'qualification.budget_tier', 'op': 'is_null',
    })
    assert "c.qualification->>'budget_tier' is null" in sql


def test_build_segment_query_combined_all_of():
    from app.services.segments import build_segment_query
    sql, args = build_segment_query({
        'all_of': [
            {'field': 'tags', 'op': 'is_empty'},
            {'field': 'total_spent', 'op': 'gt', 'value': 100},
        ],
    })
    assert ' and ' in sql
    assert 'array_length' in sql


def test_build_segment_query_combined_any_of():
    from app.services.segments import build_segment_query
    sql, args = build_segment_query({
        'any_of': [
            {'field': 'tags', 'op': 'is_empty'},
            {'field': 'total_spent', 'op': 'gt', 'value': 100},
        ],
    })
    # Top of the SQL has the tenant/opt-in/phone joined by AND, then the
    # rule fragment is joined with OR internally
    assert ' or ' in sql


# ───────── _emit helpers via direct calls ────────────────────────────────


def test_emit_condition_invalid_input():
    from app.services.segments import _ParamBuilder, _emit_condition
    pb = _ParamBuilder()
    assert _emit_condition('not a dict', pb) is None
    assert _emit_condition({'field': 'x', 'op': 5}, pb) is None
    assert _emit_condition({'field': 'unknown', 'op': 'eq'}, pb) is None
    assert _emit_condition(
        {'field': 'tags', 'op': 'eq', 'value': 'x'}, pb,
    ) is None  # tags doesn't support 'eq'


def test_emit_node_returns_none_for_non_dict():
    from app.services.segments import _ParamBuilder, _emit_node
    pb = _ParamBuilder()
    assert _emit_node(None, pb) is None
    assert _emit_node([], pb) is None
    assert _emit_node('x', pb) is None
