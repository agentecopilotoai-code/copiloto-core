"""Unit tests for `app/services/segments.py` (segment evaluator + rules parser).

Currently 67% covered. This suite exercises the pure rules evaluator
(`evaluate_rules`, `_evaluate_predicate`, `_evaluate_node`,
`normalize_rules`, `normalize_applies_when`, `build_segment_query`) which
runs entirely in-memory — no DB needed.
"""
from __future__ import annotations



# ───────── _coerce_number ─────────────────────────────────────────────────


def test_coerce_number_handles_int_float_str_none():
    from app.services.segments import _coerce_number
    assert _coerce_number(42) == 42
    assert _coerce_number(3.14) == 3.14
    assert _coerce_number('5') == 5
    assert _coerce_number('3.14') == 3.14
    assert _coerce_number(None) is None
    assert _coerce_number('not-a-number') is None
    assert _coerce_number({}) is None
    assert _coerce_number([1, 2]) is None


# ───────── _valid_qualification_key + _qualification_expression ───────────


def test_qualification_key_accepts_valid_alnum_underscore():
    from app.services.segments import _valid_qualification_key
    assert _valid_qualification_key('pain_level') is True
    assert _valid_qualification_key('budget') is True
    assert _valid_qualification_key('age_group_1') is True


def test_qualification_key_rejects_sql_injection_chars():
    from app.services.segments import _valid_qualification_key
    assert _valid_qualification_key('drop table') is False
    assert _valid_qualification_key("'; DROP") is False
    assert _valid_qualification_key('hyphen-not-allowed') is False
    assert _valid_qualification_key('') is False


# ───────── _coerce_for_compare ────────────────────────────────────────────


def test_coerce_for_compare_normalizes_truthy_strings():
    """Real behavior: parses bool-y strings and numbers; leaves others as-is."""
    from app.services.segments import _coerce_for_compare
    assert _coerce_for_compare('true') is True
    assert _coerce_for_compare('YES') is True
    assert _coerce_for_compare('false') is False
    assert _coerce_for_compare('No') is False
    assert _coerce_for_compare('42') == 42
    assert _coerce_for_compare('3.14') == 3.14
    # Non-parseable strings pass through unchanged
    assert _coerce_for_compare('Hello') == 'Hello'


def test_coerce_for_compare_passes_through_non_strings():
    from app.services.segments import _coerce_for_compare
    assert _coerce_for_compare(42) == 42
    assert _coerce_for_compare(None) is None
    assert _coerce_for_compare([1, 2]) == [1, 2]


# ───────── _equal ─────────────────────────────────────────────────────────


def test_equal_case_insensitive_strings():
    from app.services.segments import _equal
    assert _equal('A', 'a') is True
    assert _equal('Hello', 'HELLO') is True


def test_equal_falls_back_to_value_equality_for_non_strings():
    from app.services.segments import _equal
    assert _equal(42, 42) is True
    assert _equal(42, 43) is False
    assert _equal(None, None) is True


# ───────── _evaluate_predicate ────────────────────────────────────────────


def test_evaluate_predicate_eq():
    """Real signature: `{'key': str, 'op': str, 'value': any}`."""
    from app.services.segments import _evaluate_predicate
    pred = {'key': 'name', 'op': 'eq', 'value': 'juan'}
    assert _evaluate_predicate(pred, {'name': 'JUAN'}) is True
    assert _evaluate_predicate(pred, {'name': 'pedro'}) is False
    assert _evaluate_predicate(pred, {}) is False


def test_evaluate_predicate_in():
    from app.services.segments import _evaluate_predicate
    pred = {'key': 'status', 'op': 'in', 'value': ['active', 'trial']}
    assert _evaluate_predicate(pred, {'status': 'active'}) is True
    assert _evaluate_predicate(pred, {'status': 'inactive'}) is False


def test_evaluate_predicate_not_in():
    from app.services.segments import _evaluate_predicate
    pred = {'key': 'status', 'op': 'not_in', 'value': ['suppressed']}
    assert _evaluate_predicate(pred, {'status': 'active'}) is True
    assert _evaluate_predicate(pred, {'status': 'suppressed'}) is False


def test_evaluate_predicate_gt_gte_lt_lte():
    from app.services.segments import _evaluate_predicate
    assert _evaluate_predicate({'key': 'budget', 'op': 'gt', 'value': 100}, {'budget': 200}) is True
    assert _evaluate_predicate({'key': 'budget', 'op': 'gte', 'value': 100}, {'budget': 100}) is True
    assert _evaluate_predicate({'key': 'budget', 'op': 'lt', 'value': 100}, {'budget': 50}) is True
    assert _evaluate_predicate({'key': 'budget', 'op': 'lte', 'value': 100}, {'budget': 100}) is True


def test_evaluate_predicate_contains_any():
    from app.services.segments import _evaluate_predicate
    pred = {'key': 'tags', 'op': 'contains_any', 'value': ['vip']}
    assert _evaluate_predicate(pred, {'tags': ['vip', 'regular']}) is True
    assert _evaluate_predicate(pred, {'tags': ['regular']}) is False


def test_evaluate_predicate_is_null():
    from app.services.segments import _evaluate_predicate
    pred = {'key': 'optional', 'op': 'is_null'}
    assert _evaluate_predicate(pred, {'optional': None}) is True
    assert _evaluate_predicate(pred, {'optional': 'x'}) is False


def test_evaluate_predicate_unknown_op_returns_false():
    from app.services.segments import _evaluate_predicate
    pred = {'key': 'x', 'op': 'magic_unknown', 'value': 'y'}
    assert _evaluate_predicate(pred, {'x': 'y'}) is False


# ───────── _evaluate_node + evaluate_rules ───────────────────────────────


def test_evaluate_node_all_of_combines_predicates():
    """Real key: `all_of` (not `all`)."""
    from app.services.segments import _evaluate_node
    node = {
        'all_of': [
            {'key': 'status', 'op': 'eq', 'value': 'active'},
            {'key': 'budget', 'op': 'gte', 'value': 100},
        ],
    }
    assert _evaluate_node(node, {'status': 'active', 'budget': 200}) is True
    assert _evaluate_node(node, {'status': 'active', 'budget': 50}) is False


def test_evaluate_node_any_of_combines_predicates():
    from app.services.segments import _evaluate_node
    node = {
        'any_of': [
            {'key': 'tier', 'op': 'eq', 'value': 'vip'},
            {'key': 'tier', 'op': 'eq', 'value': 'gold'},
        ],
    }
    assert _evaluate_node(node, {'tier': 'vip'}) is True
    assert _evaluate_node(node, {'tier': 'gold'}) is True
    assert _evaluate_node(node, {'tier': 'silver'}) is False


def test_evaluate_node_nested_all_of_and_any_of():
    from app.services.segments import _evaluate_node
    node = {
        'all_of': [
            {'key': 'status', 'op': 'eq', 'value': 'active'},
            {'any_of': [
                {'key': 'tier', 'op': 'eq', 'value': 'vip'},
                {'key': 'budget', 'op': 'gte', 'value': 200},
            ]},
        ],
    }
    facts1 = {'status': 'active', 'tier': 'regular', 'budget': 250}
    assert _evaluate_node(node, facts1) is True
    facts2 = {'status': 'active', 'tier': 'regular', 'budget': 50}
    assert _evaluate_node(node, facts2) is False


def test_evaluate_rules_with_empty_rules_returns_true():
    """Empty / no-op rules → match everyone."""
    from app.services.segments import evaluate_rules
    assert evaluate_rules({}, {'x': 1}) is True
    assert evaluate_rules({'all_of': []}, {'x': 1}) is True


def test_evaluate_rules_with_string_json_rules():
    from app.services.segments import evaluate_rules
    rules_json = '{"all_of": [{"key": "x", "op": "eq", "value": 1}]}'
    assert evaluate_rules(rules_json, {'x': 1}) is True
    assert evaluate_rules(rules_json, {'x': 2}) is False


# ───────── normalize_rules / normalize_applies_when ──────────────────────


def test_normalize_rules_passes_through_dict():
    from app.services.segments import normalize_rules
    rules = {'all': [{'field': 'x', 'op': 'eq', 'value': 1}]}
    out = normalize_rules(rules)
    assert isinstance(out, dict)


def test_normalize_rules_parses_string_json():
    from app.services.segments import normalize_rules
    out = normalize_rules('{"all": []}')
    assert isinstance(out, dict)


def test_normalize_rules_returns_empty_for_invalid():
    from app.services.segments import normalize_rules
    assert normalize_rules(None) == {}
    assert normalize_rules('not-json') == {}
    assert normalize_rules(42) == {}


def test_normalize_applies_when_with_qualification_facts():
    from app.services.segments import normalize_applies_when
    rules = {'all': [{'field': 'pain_level', 'op': 'gte', 'value': 7}]}
    out = normalize_applies_when(rules)
    assert isinstance(out, dict)


# ───────── build_segment_query ────────────────────────────────────────────


def test_build_segment_query_returns_sql_and_args():
    from app.services.segments import build_segment_query
    rules = {'all': [{'field': 'opt_in_status', 'op': 'in', 'values': ['granted']}]}
    sql, args = build_segment_query(rules)
    assert isinstance(sql, str)
    assert isinstance(args, list)


def test_build_segment_query_handles_empty_rules():
    """Empty rules → match all contacts (no WHERE filter beyond tenant)."""
    from app.services.segments import build_segment_query
    sql, args = build_segment_query({})
    assert isinstance(sql, str)
    assert isinstance(args, list)
