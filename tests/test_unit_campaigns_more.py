"""Mock-based tests for app/services/campaigns.py."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
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


def _run(c):
    return asyncio.run(c)


# ─── coerce_dict ──────────────────────────────────────────────────────────


def test_coerce_dict_handles_json_string():
    from app.services.campaigns import coerce_dict
    assert coerce_dict('{"a":1}') == {'a': 1}


def test_coerce_dict_invalid_json_returns_empty():
    from app.services.campaigns import coerce_dict
    assert coerce_dict('not-json') == {}


def test_coerce_dict_non_dict_returns_empty():
    from app.services.campaigns import coerce_dict
    assert coerce_dict([1, 2]) == {}


def test_coerce_dict_passes_through_dict():
    from app.services.campaigns import coerce_dict
    assert coerce_dict({'k': 'v'}) == {'k': 'v'}


# ─── normalize_segment_filter ─────────────────────────────────────────────


def test_normalize_segment_filter_valid_tags():
    from app.services.campaigns import normalize_segment_filter
    tag_id = uuid4()
    out = normalize_segment_filter({'tags': [str(tag_id), 'bad-uuid']})
    assert 'tags' in out
    assert len(out['tags']) == 1


def test_normalize_segment_filter_invalid_tags_dropped():
    from app.services.campaigns import normalize_segment_filter
    out = normalize_segment_filter({'tags': ['xx', 'yy']})
    assert 'tags' not in out


def test_normalize_segment_filter_non_list_tags_dropped():
    from app.services.campaigns import normalize_segment_filter
    out = normalize_segment_filter({'tags': 'string-not-list'})
    assert 'tags' not in out


def test_normalize_segment_filter_min_appointments():
    from app.services.campaigns import normalize_segment_filter
    out = normalize_segment_filter({'min_appointments': 5})
    assert out['min_appointments'] == 5


def test_normalize_segment_filter_min_appointments_invalid_dropped():
    from app.services.campaigns import normalize_segment_filter
    out = normalize_segment_filter({'min_appointments': 'abc'})
    assert 'min_appointments' not in out


def test_normalize_segment_filter_min_appointments_negative_dropped():
    from app.services.campaigns import normalize_segment_filter
    out = normalize_segment_filter({'min_appointments': -3})
    assert 'min_appointments' not in out


def test_normalize_segment_filter_has_upcoming_appointment_bool():
    from app.services.campaigns import normalize_segment_filter
    out = normalize_segment_filter({'has_upcoming_appointment': True})
    assert out['has_upcoming_appointment'] is True


def test_normalize_segment_filter_unknown_keys_dropped():
    from app.services.campaigns import normalize_segment_filter
    out = normalize_segment_filter({'foo': 'bar'})
    assert 'foo' not in out


def test_normalize_segment_filter_handles_days_keys():
    from app.services.campaigns import normalize_segment_filter
    out = normalize_segment_filter({
        'last_visit_before_days': 30,
        'last_visit_after_days': 5,
    })
    assert out['last_visit_before_days'] == 30
    assert out['last_visit_after_days'] == 5


# ─── build_recipients_query ───────────────────────────────────────────────


def test_build_recipients_query_no_filter():
    from app.services.campaigns import build_recipients_query
    sql, args = build_recipients_query({})
    assert 'c.tenant_id = $1' in sql
    assert 'opt_in_status not in' in sql
    assert len(args) == 1


def test_build_recipients_query_with_tags():
    from app.services.campaigns import build_recipients_query
    sql, args = build_recipients_query({'tags': [str(uuid4())]})
    assert 'contact_tag_assignments' in sql
    assert len(args) == 2


def test_build_recipients_query_with_min_appointments():
    from app.services.campaigns import build_recipients_query
    sql, args = build_recipients_query({'min_appointments': 3})
    assert 'count(*)' in sql
    assert 3 in args


def test_build_recipients_query_with_last_visit_before_days():
    from app.services.campaigns import build_recipients_query
    sql, args = build_recipients_query({'last_visit_before_days': 30})
    assert "interval '1 day'" in sql
    assert 30 in args


def test_build_recipients_query_with_last_visit_after_days():
    from app.services.campaigns import build_recipients_query
    sql, args = build_recipients_query({'last_visit_after_days': 7})
    assert "interval '1 day'" in sql
    assert 7 in args


def test_build_recipients_query_with_has_upcoming_true():
    from app.services.campaigns import build_recipients_query
    sql, args = build_recipients_query({'has_upcoming_appointment': True})
    assert 'exists' in sql
    assert 'not exists' not in sql


def test_build_recipients_query_with_has_upcoming_false():
    from app.services.campaigns import build_recipients_query
    sql, args = build_recipients_query({'has_upcoming_appointment': False})
    assert 'not exists' in sql


# ─── evaluate_segment / count_recipients ──────────────────────────────────


def test_evaluate_segment_returns_dicts():
    from app.services.campaigns import evaluate_segment
    rows = [_Row(id=uuid4(), wa_id='+5730', phone_e164='+5730', display_name='X', opt_in_status='active')]
    conn = _FakeConn(fetch_results=[rows])
    out = _run(evaluate_segment(conn, uuid4(), {}))
    assert len(out) == 1


def test_evaluate_segment_with_limit():
    from app.services.campaigns import evaluate_segment
    conn = _FakeConn(fetch_results=[[]])
    out = _run(evaluate_segment(conn, uuid4(), {}, limit=5))
    assert out == []


def test_count_recipients_returns_int():
    from app.services.campaigns import count_recipients
    conn = _FakeConn(fetchval_results=[42])
    out = _run(count_recipients(conn, uuid4(), {}))
    assert out == 42


def test_count_recipients_none_returns_zero():
    from app.services.campaigns import count_recipients
    conn = _FakeConn(fetchval_results=[None])
    out = _run(count_recipients(conn, uuid4(), {}))
    assert out == 0


# ─── build_template_message_payload ───────────────────────────────────────


def test_build_template_message_payload_no_vars():
    from app.services.campaigns import build_template_message_payload
    out = build_template_message_payload('hello', 'es', None)
    assert out['name'] == 'hello'
    assert out['language']['code'] == 'es'
    assert 'components' not in out


def test_build_template_message_payload_default_locale():
    from app.services.campaigns import build_template_message_payload
    out = build_template_message_payload('hello', '', None)
    assert out['language']['code'] == 'es'


def test_build_template_message_payload_with_vars():
    from app.services.campaigns import build_template_message_payload
    out = build_template_message_payload('hi', 'es', {'1': 'foo', '2': 'bar'})
    assert out['components'][0]['type'] == 'body'
    assert len(out['components'][0]['parameters']) == 2
    assert out['components'][0]['parameters'][0]['text'] == 'foo'


def test_build_template_message_payload_with_non_digit_keys():
    from app.services.campaigns import build_template_message_payload
    out = build_template_message_payload('hi', 'es', {'name': 'Carla'})
    assert out['components'][0]['parameters'][0]['text'] == 'Carla'


# ─── _resolve_channel_for_template ────────────────────────────────────────


def test_resolve_channel_no_row_returns_none():
    from app.services.campaigns import _resolve_channel_for_template
    conn = _FakeConn(fetchrow_results=[None])
    out = _run(_resolve_channel_for_template(conn, uuid4(), uuid4()))
    assert out == (None, None)


def test_resolve_channel_returns_id_and_mode():
    from app.services.campaigns import _resolve_channel_for_template
    cid = uuid4()
    conn = _FakeConn(fetchrow_results=[_Row(
        template_channel_id=cid, status='approved',
        channel_id=cid, account_mode='cloud_api',
    )])
    out = _run(_resolve_channel_for_template(conn, uuid4(), uuid4()))
    assert out == (cid, 'cloud_api')


# ─── _conversation_for_campaign ───────────────────────────────────────────


def test_conversation_for_campaign_returns_existing():
    from app.services.campaigns import _conversation_for_campaign
    cid = uuid4()
    conn = _FakeConn(fetchrow_results=[_Row(id=cid)])
    out = _run(_conversation_for_campaign(conn, uuid4(), uuid4(), uuid4()))
    assert out == cid


def test_conversation_for_campaign_creates_new():
    from app.services.campaigns import _conversation_for_campaign
    cid = uuid4()
    conn = _FakeConn(fetchrow_results=[None, _Row(id=cid)])
    out = _run(_conversation_for_campaign(conn, uuid4(), uuid4(), uuid4()))
    assert out == cid


# ─── enqueue_campaign_message ─────────────────────────────────────────────


def test_enqueue_campaign_message_inserts_outbound_and_event():
    from app.services.campaigns import enqueue_campaign_message
    conv_id = uuid4()
    outbound_id = uuid4()
    conn = _FakeConn(fetchrow_results=[
        _Row(id=conv_id),  # find existing conversation
        _Row(id=outbound_id),  # insert message
    ])
    out = _run(enqueue_campaign_message(
        conn,
        tenant_id=uuid4(),
        campaign_id=uuid4(),
        contact_id=uuid4(),
        channel_id=uuid4(),
        template_name='welcome',
        template_locale='es',
        template_variables={'1': 'Hola'},
    ))
    assert out == outbound_id
    # The execute call should have happened for the domain_event insert
    assert len(conn.executed) == 1


# ─── refresh_campaign_counters ────────────────────────────────────────────


def test_refresh_campaign_counters_aggregates():
    from app.services.campaigns import refresh_campaign_counters
    conn = _FakeConn(fetchrow_results=[_Row(
        sent_count=10, delivered_count=5, read_count=3, failed_count=1, total=10,
    )])
    out = _run(refresh_campaign_counters(conn, uuid4(), uuid4()))
    assert out['sent_count'] == 10
    assert out['failed_count'] == 1


def test_refresh_campaign_counters_no_row():
    from app.services.campaigns import refresh_campaign_counters
    conn = _FakeConn(fetchrow_results=[None])
    out = _run(refresh_campaign_counters(conn, uuid4(), uuid4()))
    assert out['sent_count'] == 0


# ─── dispatch_campaign ────────────────────────────────────────────────────


def test_dispatch_campaign_template_not_found():
    from app.services.campaigns import dispatch_campaign
    conn = _FakeConn(fetchrow_results=[None])
    out = _run(dispatch_campaign(conn, uuid4(), {'template_id': uuid4(), 'id': uuid4()}))
    assert out['error'] == 'template_not_found'


def test_dispatch_campaign_template_not_approved():
    from app.services.campaigns import dispatch_campaign
    conn = _FakeConn(fetchrow_results=[_Row(
        id=uuid4(), name='t', locale='es', status='pending', channel_id=uuid4(),
    )])
    out = _run(dispatch_campaign(conn, uuid4(), {'template_id': uuid4(), 'id': uuid4()}))
    assert out['error'].startswith('template_not_approved:')


def test_dispatch_campaign_no_channel():
    from app.services.campaigns import dispatch_campaign
    conn = _FakeConn(fetchrow_results=[
        _Row(id=uuid4(), name='t', locale='es', status='approved', channel_id=uuid4()),
        None,  # _resolve_channel_for_template
    ])
    out = _run(dispatch_campaign(conn, uuid4(), {'template_id': uuid4(), 'id': uuid4()}))
    assert out['error'] == 'channel_not_found'


def test_dispatch_campaign_enqueues_recipients_with_sleep():
    """rate=2, 5 recipients → expect sleep_func called at indices 1 and 3 (after 2 and 4 enqueues)."""
    from app.services.campaigns import dispatch_campaign

    sleep_calls = []

    async def _fake_sleep(seconds):
        sleep_calls.append(seconds)

    tpl_id = uuid4()
    channel_id = uuid4()
    fetchrows = [
        _Row(id=tpl_id, name='t', locale='es', status='approved', channel_id=channel_id),
        # _resolve_channel_for_template
        _Row(template_channel_id=channel_id, status='approved', channel_id=channel_id, account_mode='cloud'),
    ]
    # For each recipient, enqueue_campaign_message does 2 fetchrow calls (conv + insert)
    for _ in range(5):
        fetchrows.append(_Row(id=uuid4()))  # conversation
        fetchrows.append(_Row(id=uuid4()))  # message insert

    conn = _FakeConn(
        fetchrow_results=fetchrows,
        fetch_results=[
            # _resolve_campaign_recipients via evaluate_segment
            [_Row(id=uuid4(), wa_id='', phone_e164='+57', display_name='', opt_in_status='active') for _ in range(5)],
        ],
    )

    out = _run(dispatch_campaign(
        conn, uuid4(),
        {'template_id': tpl_id, 'id': uuid4(), 'segment_filter': None, 'template_variables': None},
        rate_limit_per_second=2,
        sleep_func=_fake_sleep,
    ))
    assert out['enqueued'] == 5
    assert out['recipient_count'] == 5
    assert len(sleep_calls) == 2  # after index 1 and 3 (1-indexed: 2 and 4)


def test_dispatch_campaign_uses_snapshot_when_present():
    from app.services.campaigns import dispatch_campaign
    tpl_id = uuid4()
    channel_id = uuid4()
    seg_id = uuid4()
    snap_at = datetime(2026, 5, 18, tzinfo=UTC)
    fetchrows = [
        _Row(id=tpl_id, name='t', locale='es', status='approved', channel_id=channel_id),
        _Row(template_channel_id=channel_id, status='approved', channel_id=channel_id, account_mode='cloud'),
    ]
    conn = _FakeConn(
        fetchrow_results=fetchrows,
        fetch_results=[
            # _resolve_campaign_recipients uses snapshot path → fetch contact_segment_members
            [],
        ],
    )
    out = _run(dispatch_campaign(
        conn, uuid4(),
        {'template_id': tpl_id, 'id': uuid4(), 'segment_id': seg_id, 'launched_snapshot_at': snap_at,
         'template_variables': None},
    ))
    assert out['enqueued'] == 0


# ─── process_due_campaigns ────────────────────────────────────────────────


def test_process_due_campaigns_no_rows():
    from app.services.campaigns import process_due_campaigns
    conn = _FakeConn(fetch_results=[[]])
    out = _run(process_due_campaigns(conn))
    assert out == 0


def test_process_due_campaigns_processes_one(monkeypatch):
    from app.services import campaigns
    from app.services.campaigns import process_due_campaigns

    async def _fake_dispatch(conn, tenant_id, campaign, **kw):
        return {'enqueued': 3, 'recipient_count': 3}

    monkeypatch.setattr(campaigns, 'dispatch_campaign', _fake_dispatch)

    row = _Row(
        tenant_id=uuid4(), id=uuid4(),
        segment_filter='{}', template_variables='{}',
        segment_id=None, launched_snapshot_at=None,
        template_id=uuid4(),
    )
    conn = _FakeConn(fetch_results=[[row]])
    out = _run(process_due_campaigns(conn))
    assert out == 1
    # execute happens for: set_config + update campaigns
    assert len(conn.executed) >= 2
