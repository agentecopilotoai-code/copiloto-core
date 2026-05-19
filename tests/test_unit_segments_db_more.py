"""Extra tests for app/services/segments.py — DB helpers + remaining branches."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4


class _Row(dict):
    def keys(self):  # type: ignore[override]
        return super().keys()


class _FakeConn:
    def __init__(self, *, fetch_results=None, fetchrow_results=None, fetchval_results=None):
        self._fetch = list(fetch_results or [])
        self._fetchrow = list(fetchrow_results or [])
        self._fetchval = list(fetchval_results or [])
        self.executed = []
        self.executemany_calls = []

    async def fetch(self, sql, *args):
        if not self._fetch:
            return []
        return self._fetch.pop(0)

    async def fetchrow(self, sql, *args):
        if not self._fetchrow:
            return None
        return self._fetchrow.pop(0)

    async def fetchval(self, sql, *args):
        if not self._fetchval:
            return None
        return self._fetchval.pop(0)

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    async def executemany(self, sql, args):
        self.executemany_calls.append((sql, list(args)))


def _run(c):
    return asyncio.run(c)


# ─── _emit_condition with qualification operators ─────────────────────────


def test_emit_qualification_eq():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    out = _emit_condition({'field': 'qualification.foo', 'op': 'eq', 'value': 'bar'}, pb)
    assert out is not None and 'qualification' in out
    assert 'bar' in pb.args


def test_emit_qualification_in_with_list():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    out = _emit_condition({'field': 'qualification.x', 'op': 'in', 'value': ['a', 'b']}, pb)
    assert out is not None
    assert 'any(' in out


def test_emit_qualification_in_with_empty_list():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    out = _emit_condition({'field': 'qualification.x', 'op': 'in', 'value': []}, pb)
    assert out is None


def test_emit_qualification_is_null():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    out = _emit_condition({'field': 'qualification.x', 'op': 'is_null'}, pb)
    assert 'is null' in out


def test_emit_qualification_is_not_null():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    out = _emit_condition({'field': 'qualification.x', 'op': 'is_not_null'}, pb)
    assert 'is not null' in out


def test_emit_qualification_invalid_key():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    # hyphen is not allowed
    out = _emit_condition({'field': 'qualification.bad-key', 'op': 'eq', 'value': 'x'}, pb)
    assert out is None


def test_emit_qualification_unsupported_op():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    out = _emit_condition({'field': 'qualification.x', 'op': 'lt', 'value': 1}, pb)
    assert out is None


def test_emit_invalid_field_or_op():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    assert _emit_condition({'field': 'unknown', 'op': 'eq', 'value': 'x'}, pb) is None
    pb2 = _ParamBuilder()
    assert _emit_condition({'field': 'lead_source.channel', 'op': 'lt', 'value': 'x'}, pb2) is None


def test_emit_lead_source_in_list():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    out = _emit_condition({'field': 'lead_source.channel', 'op': 'in', 'value': ['whatsapp', 'web']}, pb)
    assert 'text[]' in out


def test_emit_numeric_in_filters_invalid_values():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    out = _emit_condition({'field': 'total_appointments_completed', 'op': 'in',
                            'value': ['not-a-number']}, pb)
    assert out is None


def test_emit_numeric_in_with_valid_values():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    out = _emit_condition({'field': 'total_appointments_completed', 'op': 'in',
                            'value': [1, 2, '3']}, pb)
    assert out is not None
    assert 'numeric[]' in out


def test_emit_between_invalid():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    assert _emit_condition({'field': 'total_appointments_completed', 'op': 'between',
                            'value': [1]}, pb) is None
    pb2 = _ParamBuilder()
    assert _emit_condition({'field': 'total_appointments_completed', 'op': 'between',
                            'value': [1, 'bad']}, pb2) is None


def test_emit_between_valid():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    out = _emit_condition({'field': 'total_appointments_completed', 'op': 'between',
                            'value': [1, 10]}, pb)
    assert 'between' in out


def test_emit_lt_days_ago_negative_returns_none():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    out = _emit_condition({'field': 'last_appointment_at', 'op': 'lt_days_ago', 'value': -5}, pb)
    assert out is None


def test_emit_lt_days_ago_valid():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    out = _emit_condition({'field': 'last_appointment_at', 'op': 'lt_days_ago', 'value': 30}, pb)
    assert 'interval' in out


def test_emit_gte_days_ago_valid():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    out = _emit_condition({'field': 'last_appointment_at', 'op': 'gte_days_ago', 'value': 7}, pb)
    assert 'interval' in out


def test_emit_gte_days_ago_invalid():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    assert _emit_condition({'field': 'last_appointment_at', 'op': 'gte_days_ago', 'value': -1}, pb) is None


def test_emit_in_window_days():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    out = _emit_condition({'field': 'total_appointments_no_show', 'op': 'in_window_days', 'value': 30}, pb)
    assert 'no_show' in out
    pb2 = _ParamBuilder()
    assert _emit_condition({'field': 'total_appointments_no_show', 'op': 'in_window_days', 'value': -1}, pb2) is None


def test_emit_is_empty_and_not_empty():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    out = _emit_condition({'field': 'tags', 'op': 'is_empty'}, pb)
    assert 'array_length' in out
    pb2 = _ParamBuilder()
    out2 = _emit_condition({'field': 'tags', 'op': 'is_not_empty'}, pb2)
    assert '> 0' in out2


def test_emit_contains_any_empty_list_none():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    assert _emit_condition({'field': 'tags', 'op': 'contains_any', 'value': []}, pb) is None


def test_emit_contains_any_with_list():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    out = _emit_condition({'field': 'tags', 'op': 'contains_any', 'value': ['x']}, pb)
    assert '&&' in out


def test_emit_contains_all_with_list():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    out = _emit_condition({'field': 'tags', 'op': 'contains_all', 'value': ['x']}, pb)
    assert '@>' in out


def test_emit_contains_all_empty_list_none():
    from app.services.segments import _emit_condition, _ParamBuilder
    pb = _ParamBuilder()
    assert _emit_condition({'field': 'tags', 'op': 'contains_all', 'value': []}, pb) is None


def test_emit_group_empty():
    from app.services.segments import _emit_group, _ParamBuilder
    pb = _ParamBuilder()
    out = _emit_group([], pb, 'and')
    assert out is None


def test_emit_node_non_dict():
    from app.services.segments import _emit_node, _ParamBuilder
    assert _emit_node('not a dict', _ParamBuilder()) is None


def test_emit_node_any_of():
    from app.services.segments import _emit_node, _ParamBuilder
    pb = _ParamBuilder()
    out = _emit_node({'any_of': [
        {'field': 'total_appointments_completed', 'op': 'eq', 'value': 1},
        {'field': 'total_appointments_completed', 'op': 'eq', 'value': 2},
    ]}, pb)
    assert ' or ' in out


# ─── normalize_rules edge cases ───────────────────────────────────────────


def test_normalize_rules_invalid_json_string():
    from app.services.segments import normalize_rules
    assert normalize_rules('not-json') == {}


def test_normalize_rules_non_dict():
    from app.services.segments import normalize_rules
    assert normalize_rules([1, 2]) == {}


def test_normalize_rules_bare_condition_wraps_in_all_of():
    from app.services.segments import normalize_rules
    out = normalize_rules({'field': 'total_appointments_completed', 'op': 'eq', 'value': 1})
    assert 'all_of' in out


def test_normalize_rules_unknown_field_dropped():
    from app.services.segments import normalize_rules
    out = normalize_rules({'field': 'totally_made_up', 'op': 'eq', 'value': 1})
    assert out == {}


def test_normalize_rules_invalid_op_dropped():
    from app.services.segments import normalize_rules
    out = normalize_rules({'field': 'total_appointments_completed', 'op': 'nope', 'value': 1})
    assert out == {}


def test_normalize_rules_nested_groups():
    from app.services.segments import normalize_rules
    out = normalize_rules({
        'all_of': [
            {'any_of': [
                {'field': 'total_appointments_completed', 'op': 'eq', 'value': 1},
            ]},
        ],
    })
    assert 'all_of' in out
    assert 'any_of' in out['all_of'][0]


def test_normalize_rules_qualification_invalid_key_dropped():
    from app.services.segments import normalize_rules
    # hyphen is not allowed in qualification key
    out = normalize_rules({'field': 'qualification.bad-key', 'op': 'eq', 'value': 'x'})
    assert out == {}


def test_normalize_rules_qualification_valid():
    from app.services.segments import normalize_rules
    out = normalize_rules({'field': 'qualification.budget_tier', 'op': 'eq', 'value': 'high'})
    assert out['all_of'][0]['field'] == 'qualification.budget_tier'


# ─── build_segment_query ────────────────────────────────────────────────


def test_build_segment_query_no_rules():
    from app.services.segments import build_segment_query
    sql, args = build_segment_query({})
    assert 'tenant_id =' in sql
    assert len(args) == 1


def test_build_segment_query_with_condition():
    from app.services.segments import build_segment_query
    sql, args = build_segment_query({
        'all_of': [{'field': 'total_appointments_completed', 'op': 'eq', 'value': 5}],
    })
    assert 5 in args


# ─── _bind_tenant ────────────────────────────────────────────────────────


def test_bind_tenant_with_args():
    from app.services.segments import _bind_tenant
    out = _bind_tenant([None, 5, 'x'], uuid4())
    assert isinstance(out[0], type(uuid4()))


def test_bind_tenant_empty_args():
    from app.services.segments import _bind_tenant
    out = _bind_tenant([], uuid4())
    assert out == []


# ─── evaluate_segment_rules + count_segment_contacts ─────────────────────


def test_evaluate_segment_rules_returns_dicts():
    from app.services.segments import evaluate_segment_rules
    rows = [_Row(contact_id=uuid4(), display_name='A', phone_e164='+57', opt_in_status='active')]
    conn = _FakeConn(fetch_results=[rows])
    out = _run(evaluate_segment_rules(conn, uuid4(), {}))
    assert len(out) == 1


def test_evaluate_segment_rules_with_limit():
    from app.services.segments import evaluate_segment_rules
    conn = _FakeConn(fetch_results=[[]])
    out = _run(evaluate_segment_rules(conn, uuid4(), {}, limit=10))
    assert out == []


def test_count_segment_contacts_returns_int():
    from app.services.segments import count_segment_contacts
    conn = _FakeConn(fetchval_results=[7])
    out = _run(count_segment_contacts(conn, uuid4(), {}))
    assert out == 7


def test_count_segment_contacts_none_returns_zero():
    from app.services.segments import count_segment_contacts
    conn = _FakeConn(fetchval_results=[None])
    out = _run(count_segment_contacts(conn, uuid4(), {}))
    assert out == 0


# ─── snapshot_segment_members ────────────────────────────────────────────


def test_snapshot_segment_members_no_rows():
    from app.services.segments import snapshot_segment_members
    snap = datetime(2026, 5, 18, tzinfo=UTC)
    conn = _FakeConn(
        fetch_results=[[]],
        fetchval_results=[snap],
    )
    count, snap_iso = _run(snapshot_segment_members(conn, uuid4(), uuid4(), {}))
    assert count == 0
    # no executemany call when no rows
    assert conn.executemany_calls == []


def test_snapshot_segment_members_with_rows():
    from app.services.segments import snapshot_segment_members
    snap = datetime(2026, 5, 18, tzinfo=UTC)
    rows = [
        _Row(contact_id=uuid4(), display_name='A', phone_e164='+57', opt_in_status='active'),
        _Row(contact_id=uuid4(), display_name='B', phone_e164='+57', opt_in_status='active'),
    ]
    conn = _FakeConn(
        fetch_results=[rows],
        fetchval_results=[snap],
    )
    count, _snap = _run(snapshot_segment_members(conn, uuid4(), uuid4(), {}))
    assert count == 2
    assert len(conn.executemany_calls) == 1


# ─── refresh_due_segments ───────────────────────────────────────────────


def test_refresh_due_segments_no_rows():
    from app.services.segments import refresh_due_segments
    conn = _FakeConn(
        fetch_results=[[]],
        fetchval_results=[datetime(2026, 5, 18, tzinfo=UTC)],
    )
    out = _run(refresh_due_segments(conn))
    assert out == 0


def test_refresh_due_segments_processes_rows(monkeypatch):
    from app.services import segments
    from app.services.segments import refresh_due_segments

    async def _fake_snapshot(conn, tenant_id, seg_id, rules):
        return 1, 'snap'

    monkeypatch.setattr(segments, 'snapshot_segment_members', _fake_snapshot)

    conn = _FakeConn(
        fetch_results=[
            [
                _Row(id=uuid4(), tenant_id=uuid4(), rules={}),
                _Row(id=uuid4(), tenant_id=uuid4(), rules={}),
            ],
        ],
        fetchval_results=[datetime(2026, 5, 18, tzinfo=UTC)],
    )
    out = _run(refresh_due_segments(conn, interval=timedelta(hours=1)))
    assert out == 2


# ─── seed_preconstructed_segments ───────────────────────────────────────


def test_seed_preconstructed_segments_inserts_all():
    from app.services.segments import seed_preconstructed_segments, PRECONSTRUCTED_SEGMENTS
    # Each segment insertion returns a row (newly inserted)
    rows = [_Row(id=uuid4()) for _ in PRECONSTRUCTED_SEGMENTS]
    conn = _FakeConn(fetchrow_results=rows)
    out = _run(seed_preconstructed_segments(conn, uuid4()))
    assert out == len(PRECONSTRUCTED_SEGMENTS)


def test_seed_preconstructed_segments_partial_conflict():
    """Some inserts conflict (None) and aren't counted."""
    from app.services.segments import seed_preconstructed_segments, PRECONSTRUCTED_SEGMENTS
    rows = [None for _ in PRECONSTRUCTED_SEGMENTS]
    conn = _FakeConn(fetchrow_results=rows)
    out = _run(seed_preconstructed_segments(conn, uuid4()))
    assert out == 0


# ─── normalize_applies_when / _coerce_for_compare / _equal ───────────────


def test_normalize_applies_when_invalid_json():
    from app.services.segments import normalize_applies_when
    assert normalize_applies_when('not-json') == {}


def test_normalize_applies_when_non_dict():
    from app.services.segments import normalize_applies_when
    assert normalize_applies_when([1]) == {}


def test_normalize_applies_when_empty_dict():
    from app.services.segments import normalize_applies_when
    assert normalize_applies_when({}) == {}


def test_normalize_applies_when_bare_predicate():
    from app.services.segments import normalize_applies_when
    out = normalize_applies_when({'key': 'budget_tier', 'op': 'eq', 'value': 'high'})
    assert 'all_of' in out


def test_normalize_applies_when_invalid_key():
    from app.services.segments import normalize_applies_when
    out = normalize_applies_when({'key': '1bad', 'op': 'eq'})
    assert out == {}


def test_normalize_applies_when_nested():
    from app.services.segments import normalize_applies_when
    out = normalize_applies_when({
        'any_of': [
            {'all_of': [{'key': 'budget', 'op': 'eq', 'value': 1}]},
        ],
    })
    assert 'any_of' in out


def test_coerce_for_compare_string_to_int():
    from app.services.segments import _coerce_for_compare
    assert _coerce_for_compare('5') == 5


def test_coerce_for_compare_string_to_float():
    from app.services.segments import _coerce_for_compare
    assert _coerce_for_compare('3.14') == 3.14


def test_coerce_for_compare_string_yes():
    from app.services.segments import _coerce_for_compare
    assert _coerce_for_compare('yes') is True


def test_coerce_for_compare_string_no():
    from app.services.segments import _coerce_for_compare
    assert _coerce_for_compare('no') is False


def test_coerce_for_compare_string_unparseable():
    from app.services.segments import _coerce_for_compare
    assert _coerce_for_compare('hello') == 'hello'


def test_coerce_for_compare_passthrough():
    from app.services.segments import _coerce_for_compare
    assert _coerce_for_compare([1]) == [1]


def test_equal_both_none():
    from app.services.segments import _equal
    assert _equal(None, None) is True


def test_equal_one_none():
    from app.services.segments import _equal
    assert _equal(None, 1) is False


def test_equal_bools():
    from app.services.segments import _equal
    assert _equal(True, 'yes') is True
    assert _equal(False, 'no') is True


def test_equal_bool_vs_string_unrelated():
    from app.services.segments import _equal
    assert _equal(True, 'consultation') is False


def test_equal_numeric():
    from app.services.segments import _equal
    assert _equal(1, 1.0) is True
    assert _equal('5', 5) is True


def test_equal_strings():
    from app.services.segments import _equal
    assert _equal('HELLO', 'hello') is True


# ─── _evaluate_predicate edge cases ──────────────────────────────────────


def test_evaluate_predicate_invalid_op():
    from app.services.segments import _evaluate_predicate
    assert _evaluate_predicate({'key': 'x', 'op': 'bad'}, {}) is False


def test_evaluate_predicate_is_null():
    from app.services.segments import _evaluate_predicate
    assert _evaluate_predicate({'key': 'x', 'op': 'is_null'}, {}) is True


def test_evaluate_predicate_is_not_null():
    from app.services.segments import _evaluate_predicate
    assert _evaluate_predicate({'key': 'x', 'op': 'is_not_null'}, {'x': 1}) is True


def test_evaluate_predicate_actual_none_other_ops():
    from app.services.segments import _evaluate_predicate
    assert _evaluate_predicate({'key': 'x', 'op': 'eq', 'value': 1}, {}) is False


def test_evaluate_predicate_in_non_list_value():
    from app.services.segments import _evaluate_predicate
    assert _evaluate_predicate({'key': 'x', 'op': 'in', 'value': 'not-list'}, {'x': 1}) is False


def test_evaluate_predicate_in_matches():
    from app.services.segments import _evaluate_predicate
    assert _evaluate_predicate({'key': 'x', 'op': 'in', 'value': [1, 2]}, {'x': 1}) is True


def test_evaluate_predicate_not_in_non_list():
    from app.services.segments import _evaluate_predicate
    assert _evaluate_predicate({'key': 'x', 'op': 'not_in', 'value': 'bad'}, {'x': 1}) is False


def test_evaluate_predicate_not_in_works():
    from app.services.segments import _evaluate_predicate
    assert _evaluate_predicate({'key': 'x', 'op': 'not_in', 'value': [2, 3]}, {'x': 1}) is True


def test_evaluate_predicate_numeric_ops():
    from app.services.segments import _evaluate_predicate
    assert _evaluate_predicate({'key': 'x', 'op': 'lt', 'value': 10}, {'x': 5}) is True
    assert _evaluate_predicate({'key': 'x', 'op': 'lte', 'value': 5}, {'x': 5}) is True
    assert _evaluate_predicate({'key': 'x', 'op': 'gt', 'value': 5}, {'x': 10}) is True
    assert _evaluate_predicate({'key': 'x', 'op': 'gte', 'value': 5}, {'x': 5}) is True


def test_evaluate_predicate_numeric_non_numeric():
    from app.services.segments import _evaluate_predicate
    assert _evaluate_predicate({'key': 'x', 'op': 'lt', 'value': 10}, {'x': 'hello'}) is False


def test_evaluate_predicate_contains_any():
    from app.services.segments import _evaluate_predicate
    assert _evaluate_predicate({'key': 'tags', 'op': 'contains_any', 'value': ['a']},
                               {'tags': ['a', 'b']}) is True


def test_evaluate_predicate_contains_any_wrong_types():
    from app.services.segments import _evaluate_predicate
    assert _evaluate_predicate({'key': 'tags', 'op': 'contains_any', 'value': 'not-list'},
                               {'tags': ['a']}) is False
    assert _evaluate_predicate({'key': 'tags', 'op': 'contains_any', 'value': ['a']},
                               {'tags': 'not-list'}) is False


def test_evaluate_predicate_contains_all_matches():
    from app.services.segments import _evaluate_predicate
    assert _evaluate_predicate({'key': 'tags', 'op': 'contains_all', 'value': ['a', 'b']},
                               {'tags': ['a', 'b', 'c']}) is True


def test_evaluate_predicate_contains_all_missing():
    from app.services.segments import _evaluate_predicate
    assert _evaluate_predicate({'key': 'tags', 'op': 'contains_all', 'value': ['a', 'z']},
                               {'tags': ['a', 'b']}) is False


# ─── evaluate_rules ──────────────────────────────────────────────────────


def test_evaluate_rules_empty_returns_true():
    from app.services.segments import evaluate_rules
    assert evaluate_rules({}, {}) is True


def test_evaluate_rules_facts_not_dict_coerced():
    from app.services.segments import evaluate_rules
    # facts None → coerced to {}
    assert evaluate_rules({'key': 'x', 'op': 'is_null'}, None) is True


def test_evaluate_rules_all_of():
    from app.services.segments import evaluate_rules
    assert evaluate_rules({
        'all_of': [
            {'key': 'budget', 'op': 'gte', 'value': 100},
            {'key': 'budget', 'op': 'lt', 'value': 1000},
        ],
    }, {'budget': 500}) is True


def test_evaluate_rules_any_of():
    from app.services.segments import evaluate_rules
    assert evaluate_rules({
        'any_of': [
            {'key': 'budget', 'op': 'eq', 'value': 100},
            {'key': 'budget', 'op': 'eq', 'value': 500},
        ],
    }, {'budget': 500}) is True


def test_evaluate_node_empty_lists_return_true():
    from app.services.segments import _evaluate_node
    assert _evaluate_node({'all_of': []}, {}) is True
    assert _evaluate_node({'any_of': []}, {}) is True
