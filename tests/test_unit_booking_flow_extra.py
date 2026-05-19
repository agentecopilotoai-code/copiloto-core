"""Extra coverage for ``app/services/booking_flow.py`` — focused on the
larger async flows. Uses a lightweight ``_FakeConn`` to simulate asyncpg
plus targeted monkeypatching of cross-service helpers (``audit``,
``attach_active_promo``, etc.) so the tests stay pure-Python and fast.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime
from uuid import uuid4


# ---- FakeConn ----------------------------------------------------------


class _FakeConn:
    def __init__(
        self,
        *,
        fetch_results=None,
        fetchrow_results=None,
        fetchval_results=None,
    ):
        self._fetch = list(fetch_results or [])
        self._fetchrow = list(fetchrow_results or [])
        self._fetchval = list(fetchval_results or [])
        self.executed: list[tuple[str, tuple]] = []

    async def fetch(self, sql, *args):
        return self._fetch.pop(0) if self._fetch else []

    async def fetchrow(self, sql, *args):
        return self._fetchrow.pop(0) if self._fetchrow else None

    async def fetchval(self, sql, *args):
        return self._fetchval.pop(0) if self._fetchval else None

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    def transaction(self):
        class _Txn:
            async def __aenter__(self_inner):  # noqa: N805
                return self_inner

            async def __aexit__(self_inner, exc_type, exc, tb):  # noqa: N805
                return False

        return _Txn()


# ---- _list_active_services --------------------------------------------


def test_list_active_services_returns_dicts():
    from app.services.booking_flow import _list_active_services

    rows = [{'id': uuid4(), 'name': 'A'}, {'id': uuid4(), 'name': 'B'}]
    conn = _FakeConn(fetch_results=[rows])

    services = asyncio.run(_list_active_services(conn, uuid4()))
    assert len(services) == 2
    assert services[0]['name'] == 'A'


def test_list_active_services_empty():
    from app.services.booking_flow import _list_active_services
    conn = _FakeConn(fetch_results=[[]])
    assert asyncio.run(_list_active_services(conn, uuid4())) == []


# ---- _fetch_service ----------------------------------------------------


def test_fetch_service_returns_dict_when_found():
    from app.services.booking_flow import _fetch_service
    row = {'id': uuid4(), 'name': 'X', 'duration_minutes': 30, 'applies_when': None}
    conn = _FakeConn(fetchrow_results=[row])

    out = asyncio.run(_fetch_service(conn, uuid4(), uuid4()))
    assert out is not None
    assert out['name'] == 'X'


def test_fetch_service_returns_none_when_missing():
    from app.services.booking_flow import _fetch_service
    conn = _FakeConn(fetchrow_results=[None])
    assert asyncio.run(_fetch_service(conn, uuid4(), uuid4())) is None


# ---- _list_active_resources -------------------------------------------


def test_list_active_resources_returns_dicts():
    from app.services.booking_flow import _list_active_resources
    rows = [{'id': uuid4(), 'name': 'R1'}, {'id': uuid4(), 'name': 'R2'}]
    conn = _FakeConn(fetch_results=[rows])
    out = asyncio.run(_list_active_resources(conn, uuid4()))
    assert len(out) == 2


def test_list_active_resources_branch_filter():
    from app.services.booking_flow import _list_active_resources
    conn = _FakeConn(fetch_results=[[]])
    out = asyncio.run(_list_active_resources(conn, uuid4(), branch_id=uuid4()))
    assert out == []


# ---- _list_active_contact_packages ------------------------------------


def test_list_active_contact_packages_returns_rows():
    from app.services.booking_flow import _list_active_contact_packages
    rows = [{'id': uuid4(), 'package_id': uuid4(), 'remaining_sessions': 3,
             'expires_at': None, 'package_name': 'Pack', 'includes_service_ids': []}]
    conn = _FakeConn(fetch_results=[rows])
    out = asyncio.run(_list_active_contact_packages(
        conn, uuid4(), uuid4(), uuid4(),
    ))
    assert out[0]['remaining_sessions'] == 3


def test_list_active_contact_packages_empty():
    from app.services.booking_flow import _list_active_contact_packages
    conn = _FakeConn(fetch_results=[[]])
    out = asyncio.run(_list_active_contact_packages(
        conn, uuid4(), uuid4(), uuid4(),
    ))
    assert out == []


# ---- _list_active_branches --------------------------------------------


def test_list_active_branches_returns_rows():
    from app.services.booking_flow import _list_active_branches
    rows = [{'id': uuid4(), 'name': 'Main'}]
    conn = _FakeConn(fetch_results=[rows])
    out = asyncio.run(_list_active_branches(conn, uuid4()))
    assert out[0]['name'] == 'Main'


def test_list_active_branches_empty():
    from app.services.booking_flow import _list_active_branches
    conn = _FakeConn(fetch_results=[[]])
    assert asyncio.run(_list_active_branches(conn, uuid4())) == []


# ---- _fetch_branch -----------------------------------------------------


def test_fetch_branch_returns_dict_when_found():
    from app.services.booking_flow import _fetch_branch
    row = {'id': uuid4(), 'name': 'B1'}
    conn = _FakeConn(fetchrow_results=[row])
    out = asyncio.run(_fetch_branch(conn, uuid4(), uuid4()))
    assert out is not None
    assert out['name'] == 'B1'


def test_fetch_branch_returns_none():
    from app.services.booking_flow import _fetch_branch
    conn = _FakeConn(fetchrow_results=[None])
    assert asyncio.run(_fetch_branch(conn, uuid4(), uuid4())) is None


# ---- _fetch_resource ---------------------------------------------------


def test_fetch_resource_returns_dict_when_found():
    from app.services.booking_flow import _fetch_resource
    row = {'id': uuid4(), 'name': 'Dr Z', 'capabilities': {'working_hours': {}}}
    conn = _FakeConn(fetchrow_results=[row])
    out = asyncio.run(_fetch_resource(conn, uuid4(), uuid4()))
    assert out['name'] == 'Dr Z'


def test_fetch_resource_with_branch_returns_none():
    from app.services.booking_flow import _fetch_resource
    conn = _FakeConn(fetchrow_results=[None])
    out = asyncio.run(_fetch_resource(
        conn, uuid4(), uuid4(), branch_id=uuid4(),
    ))
    assert out is None


# ---- _queue_text_message + _queue_interactive_message ----------------


def test_queue_text_message_inserts_message_and_event():
    from app.services.booking_flow import _queue_text_message
    msg_id = uuid4()
    conn = _FakeConn(fetchrow_results=[{'id': msg_id}])
    out = asyncio.run(_queue_text_message(
        conn, tenant_id=uuid4(), conversation_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        body_text='Hola', booking_step='awaiting_service',
    ))
    assert out == msg_id
    # We expect the insert into messages + insert into domain_events.
    assert len(conn.executed) == 1


def test_queue_interactive_message_inserts_and_event():
    from app.services.booking_flow import _queue_interactive_message
    msg_id = uuid4()
    conn = _FakeConn(fetchrow_results=[{'id': msg_id}])
    out = asyncio.run(_queue_interactive_message(
        conn, tenant_id=uuid4(), conversation_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        body_text='Pick one', interactive_payload={'type': 'button'},
        booking_step='awaiting_service',
    ))
    assert out == msg_id
    assert len(conn.executed) == 1


# ---- _persist_state ----------------------------------------------------


def test_persist_state_dict_metadata():
    from app.services.booking_flow import _persist_state
    conv = {'id': uuid4(), 'metadata': {'other_key': 1}}
    conn = _FakeConn()
    asyncio.run(_persist_state(conn, uuid4(), conv, {'step': 'awaiting_service'}))
    # one update against conversations
    assert len(conn.executed) == 1


def test_persist_state_string_metadata_replaces():
    from app.services.booking_flow import _persist_state
    conv = {'id': uuid4(), 'metadata': '{"existing": 1}'}
    conn = _FakeConn()
    asyncio.run(_persist_state(conn, uuid4(), conv, {'step': 'awaiting_slot'}))
    assert len(conn.executed) == 1


def test_persist_state_invalid_metadata():
    from app.services.booking_flow import _persist_state
    conv = {'id': uuid4(), 'metadata': 'not json'}
    conn = _FakeConn()
    asyncio.run(_persist_state(conn, uuid4(), conv, {'step': 'awaiting_slot'}))
    assert len(conn.executed) == 1


# ---- _present_packages -------------------------------------------------


def test_present_packages_returns_none_when_no_packages(monkeypatch):
    from app.services import booking_flow

    async def fake_list(conn, tenant_id, contact_id, service_id):
        return []

    monkeypatch.setattr(booking_flow, '_list_active_contact_packages', fake_list)

    conn = _FakeConn()
    out = asyncio.run(booking_flow._present_packages(
        conn, tenant_id=uuid4(),
        conversation={'id': uuid4()}, channel_id=uuid4(),
        channel_account_mode='mock',
        state={}, contact_id=uuid4(),
        service_uuid=uuid4(),
    ))
    assert out is None


def test_present_packages_offers_buttons_when_packages_exist(monkeypatch):
    from app.services import booking_flow

    pkg_id = uuid4()

    async def fake_list(conn, tenant_id, contact_id, service_id):
        return [
            {'id': pkg_id, 'remaining_sessions': 4, 'package_name': 'Premium'},
        ]

    monkeypatch.setattr(booking_flow, '_list_active_contact_packages', fake_list)

    sent: dict = {}

    async def fake_queue(conn, **kwargs):
        sent.update(kwargs)
        return uuid4()

    monkeypatch.setattr(booking_flow, '_queue_interactive_message', fake_queue)

    out = asyncio.run(booking_flow._present_packages(
        _FakeConn(),
        tenant_id=uuid4(),
        conversation={'id': uuid4()},
        channel_id=uuid4(), channel_account_mode='mock',
        state={'selected_service_id': str(uuid4())},
        contact_id=uuid4(), service_uuid=uuid4(),
    ))
    assert out is not None
    assert out['step'] == booking_flow.STEP_AWAITING_PACKAGE
    assert str(pkg_id) in out['available_package_ids']
    assert 'Premium' in sent['body_text']


# ---- _present_services -------------------------------------------------


def test_present_services_returns_none_when_catalog_empty(monkeypatch):
    from app.services import booking_flow

    async def fake_list(conn, tenant_id):
        return []

    monkeypatch.setattr(booking_flow, '_list_active_services', fake_list)
    out = asyncio.run(booking_flow._present_services(
        _FakeConn(), tenant_id=uuid4(),
        conversation={'id': uuid4(), 'metadata': {}}, channel_id=uuid4(),
        channel_account_mode='mock', contact_id=uuid4(),
    ))
    assert out is None


def test_present_services_returns_none_when_qualification_filters_all(monkeypatch):
    from app.services import booking_flow

    async def fake_list(conn, tenant_id):
        return [{'id': uuid4(), 'name': 'A', 'applies_when':
                 {'all_of': [{'key': 'tier', 'op': 'eq', 'value': 'high'}]}}]

    monkeypatch.setattr(booking_flow, '_list_active_services', fake_list)
    conv = {'id': uuid4(),
            'metadata': {'qualification': {'facts': {'tier': 'low'}}}}
    out = asyncio.run(booking_flow._present_services(
        _FakeConn(), tenant_id=uuid4(),
        conversation=conv, channel_id=uuid4(),
        channel_account_mode='mock', contact_id=uuid4(),
    ))
    assert out is None


def test_present_services_lists_when_multiple_eligible(monkeypatch):
    from app.services import booking_flow

    async def fake_list(conn, tenant_id):
        return [
            {'id': uuid4(), 'name': 'A', 'applies_when': None,
             'price_amount': 1000, 'price_currency': 'COP',
             'duration_minutes': 30},
            {'id': uuid4(), 'name': 'B', 'applies_when': None,
             'price_amount': None, 'price_currency': None,
             'duration_minutes': None},
        ]

    monkeypatch.setattr(booking_flow, '_list_active_services', fake_list)

    async def fake_promo(conn, tenant_id, service_id):
        return None

    monkeypatch.setattr(booking_flow, 'attach_active_promo', fake_promo)

    sent = {}

    async def fake_queue(conn, **kwargs):
        sent.update(kwargs)
        return uuid4()

    monkeypatch.setattr(booking_flow, '_queue_interactive_message', fake_queue)

    out = asyncio.run(booking_flow._present_services(
        _FakeConn(),
        tenant_id=uuid4(),
        conversation={'id': uuid4(), 'metadata': {}},
        channel_id=uuid4(), channel_account_mode='mock',
        contact_id=uuid4(),
    ))
    assert out == {'step': booking_flow.STEP_AWAITING_SERVICE}


def test_present_services_auto_selects_single(monkeypatch):
    """With exactly one eligible service, the flow auto-selects it and routes
    via _present_packages → _present_branches → _present_resources."""
    from app.services import booking_flow

    only_id = uuid4()

    async def fake_list(conn, tenant_id):
        return [{'id': only_id, 'name': 'Solo', 'applies_when': None}]

    monkeypatch.setattr(booking_flow, '_list_active_services', fake_list)

    async def fake_packages(conn, **kwargs):
        return None

    monkeypatch.setattr(booking_flow, '_present_packages', fake_packages)

    async def fake_branches(conn, **kwargs):
        return None

    monkeypatch.setattr(booking_flow, '_present_branches', fake_branches)

    async def fake_resources(conn, **kwargs):
        return {'step': booking_flow.STEP_AWAITING_RESOURCE,
                'selected_service_id': str(only_id)}

    monkeypatch.setattr(booking_flow, '_present_resources', fake_resources)

    out = asyncio.run(booking_flow._present_services(
        _FakeConn(), tenant_id=uuid4(),
        conversation={'id': uuid4(), 'metadata': {}},
        channel_id=uuid4(), channel_account_mode='mock',
        contact_id=uuid4(),
    ))
    assert out is not None
    assert out['selected_service_id'] == str(only_id)


# ---- _present_branches -------------------------------------------------


def test_present_branches_returns_none_when_empty(monkeypatch):
    from app.services import booking_flow

    async def fake_list(conn, tenant_id):
        return []

    monkeypatch.setattr(booking_flow, '_list_active_branches', fake_list)
    out = asyncio.run(booking_flow._present_branches(
        _FakeConn(), tenant_id=uuid4(),
        conversation={'id': uuid4()}, channel_id=uuid4(),
        channel_account_mode='mock', state={'selected_service_id': str(uuid4())},
    ))
    assert out is None


def test_present_branches_auto_selects_single(monkeypatch):
    from app.services import booking_flow

    only_id = uuid4()

    async def fake_list(conn, tenant_id):
        return [{'id': only_id, 'name': 'Main', 'city': 'Bogotá'}]

    monkeypatch.setattr(booking_flow, '_list_active_branches', fake_list)

    async def fake_resources(conn, **kwargs):
        return {**kwargs['state'], 'step': booking_flow.STEP_AWAITING_DATE}

    monkeypatch.setattr(booking_flow, '_present_resources', fake_resources)

    out = asyncio.run(booking_flow._present_branches(
        _FakeConn(), tenant_id=uuid4(),
        conversation={'id': uuid4()}, channel_id=uuid4(),
        channel_account_mode='mock', state={'selected_service_id': str(uuid4())},
    ))
    assert out is not None
    assert out['selected_branch_id'] == str(only_id)


def test_present_branches_multi_lists(monkeypatch):
    from app.services import booking_flow

    async def fake_list(conn, tenant_id):
        return [
            {'id': uuid4(), 'name': 'North', 'city': 'Bogotá', 'address': None},
            {'id': uuid4(), 'name': 'South', 'city': None, 'address': 'Cra 11'},
        ]

    monkeypatch.setattr(booking_flow, '_list_active_branches', fake_list)

    async def fake_queue(conn, **kwargs):
        return uuid4()

    monkeypatch.setattr(booking_flow, '_queue_interactive_message', fake_queue)

    out = asyncio.run(booking_flow._present_branches(
        _FakeConn(), tenant_id=uuid4(),
        conversation={'id': uuid4()}, channel_id=uuid4(),
        channel_account_mode='mock', state={'selected_service_id': str(uuid4())},
    ))
    assert out['step'] == booking_flow.STEP_AWAITING_BRANCH


# ---- _present_resources -----------------------------------------------


def test_present_resources_returns_none_when_empty(monkeypatch):
    from app.services import booking_flow

    async def fake_list(conn, tenant_id, branch_id=None):
        return []

    monkeypatch.setattr(booking_flow, '_list_active_resources', fake_list)
    out = asyncio.run(booking_flow._present_resources(
        _FakeConn(), tenant_id=uuid4(),
        conversation={'id': uuid4()}, channel_id=uuid4(),
        channel_account_mode='mock', state={},
    ))
    assert out is None


def test_present_resources_auto_selects_single(monkeypatch):
    from app.services import booking_flow

    only_id = uuid4()

    async def fake_list(conn, tenant_id, branch_id=None):
        return [{'id': only_id, 'name': 'Dr A', 'bio': None,
                 'specialty': None, 'photo_source_uri': None}]

    monkeypatch.setattr(booking_flow, '_list_active_resources', fake_list)

    async def fake_present_date(conn, **kwargs):
        return {**kwargs['state'], 'step': booking_flow.STEP_AWAITING_DATE}

    monkeypatch.setattr(booking_flow, '_present_date', fake_present_date)

    out = asyncio.run(booking_flow._present_resources(
        _FakeConn(), tenant_id=uuid4(),
        conversation={'id': uuid4()}, channel_id=uuid4(),
        channel_account_mode='mock', state={},
    ))
    assert out['selected_resource_id'] == str(only_id)
    assert out['step'] == booking_flow.STEP_AWAITING_DATE


def test_present_resources_multi_lists_options(monkeypatch):
    from app.services import booking_flow

    async def fake_list(conn, tenant_id, branch_id=None):
        return [
            {'id': uuid4(), 'name': 'Dr A', 'bio': None,
             'specialty': None, 'photo_source_uri': None},
            {'id': uuid4(), 'name': 'Dr B', 'bio': 'experienced',
             'specialty': 'cardio', 'photo_source_uri': None},
        ]

    monkeypatch.setattr(booking_flow, '_list_active_resources', fake_list)

    async def fake_queue(conn, **kwargs):
        return uuid4()

    monkeypatch.setattr(booking_flow, '_queue_interactive_message', fake_queue)
    monkeypatch.setattr(booking_flow, '_queue_specialist_photo', fake_queue)

    out = asyncio.run(booking_flow._present_resources(
        _FakeConn(), tenant_id=uuid4(),
        conversation={'id': uuid4()}, channel_id=uuid4(),
        channel_account_mode='mock', state={},
    ))
    assert out['step'] == booking_flow.STEP_AWAITING_RESOURCE


# ---- _present_date -----------------------------------------------------


def test_present_date_returns_state_with_step(monkeypatch):
    from app.services import booking_flow

    async def fake_queue(conn, **kwargs):
        return uuid4()

    monkeypatch.setattr(booking_flow, '_queue_interactive_message', fake_queue)
    out = asyncio.run(booking_flow._present_date(
        _FakeConn(), tenant_id=uuid4(),
        conversation={'id': uuid4()}, channel_id=uuid4(),
        channel_account_mode='mock', state={'selected_resource_id': str(uuid4())},
    ))
    assert out['step'] == booking_flow.STEP_AWAITING_DATE


# ---- _present_slots ----------------------------------------------------


def test_present_slots_resource_missing_restart(monkeypatch):
    from app.services import booking_flow

    async def fake_fetch_service(conn, tenant_id, service_id):
        return {'duration_minutes': 30}

    async def fake_fetch_resource(conn, tenant_id, resource_id, branch_id=None):
        return None

    async def fake_queue_text(conn, **kwargs):
        return uuid4()

    monkeypatch.setattr(booking_flow, '_fetch_service', fake_fetch_service)
    monkeypatch.setattr(booking_flow, '_fetch_resource', fake_fetch_resource)
    monkeypatch.setattr(booking_flow, '_queue_text_message', fake_queue_text)

    out = asyncio.run(booking_flow._present_slots(
        _FakeConn(), tenant_id=uuid4(),
        conversation={'id': uuid4()}, channel_id=uuid4(),
        channel_account_mode='mock',
        state={'selected_resource_id': str(uuid4()),
               'selected_service_id': str(uuid4())},
        target_date=date(2026, 6, 8),
    ))
    assert out['step'] == booking_flow.STEP_AWAITING_SERVICE


def test_present_slots_with_free_slots(monkeypatch):
    from app.services import booking_flow

    async def fake_fetch_service(conn, tenant_id, service_id):
        return {'duration_minutes': 30}

    async def fake_fetch_resource(conn, tenant_id, resource_id, branch_id=None):
        return {'capabilities':
                {'working_hours': {'mon': [{'start': '09:00', 'end': '12:00'}]}}}

    async def fake_busy(conn, tenant_id, resource_id, target_date):
        return []

    async def fake_queue(conn, **kwargs):
        return uuid4()

    monkeypatch.setattr(booking_flow, '_fetch_service', fake_fetch_service)
    monkeypatch.setattr(booking_flow, '_fetch_resource', fake_fetch_resource)
    monkeypatch.setattr(booking_flow, '_busy_intervals', fake_busy)
    monkeypatch.setattr(booking_flow, '_queue_interactive_message', fake_queue)

    out = asyncio.run(booking_flow._present_slots(
        _FakeConn(), tenant_id=uuid4(),
        conversation={'id': uuid4()}, channel_id=uuid4(),
        channel_account_mode='mock',
        state={'selected_resource_id': str(uuid4()),
               'selected_service_id': str(uuid4())},
        target_date=date(2026, 6, 8),  # Monday
    ))
    assert out['step'] == booking_flow.STEP_AWAITING_SLOT
    assert out['proposed_date'] == '2026-06-08'
    assert len(out['proposed_slots']) == 3


def test_present_slots_no_free_suggests_next_date(monkeypatch):
    from app.services import booking_flow

    async def fake_fetch_service(conn, tenant_id, service_id):
        return {'duration_minutes': 30}

    async def fake_fetch_resource(conn, tenant_id, resource_id, branch_id=None):
        return {'capabilities':
                {'working_hours': {'mon': [{'start': '09:00', 'end': '09:30'}]}}}

    async def fake_busy(conn, tenant_id, resource_id, target_date):
        return [(540, 570)]  # blocks the only slot

    async def fake_next(conn, **kwargs):
        return date(2026, 6, 15)

    async def fake_queue(conn, **kwargs):
        return uuid4()

    monkeypatch.setattr(booking_flow, '_fetch_service', fake_fetch_service)
    monkeypatch.setattr(booking_flow, '_fetch_resource', fake_fetch_resource)
    monkeypatch.setattr(booking_flow, '_busy_intervals', fake_busy)
    monkeypatch.setattr(booking_flow, '_suggest_next_available_date', fake_next)
    monkeypatch.setattr(booking_flow, '_queue_text_message', fake_queue)

    out = asyncio.run(booking_flow._present_slots(
        _FakeConn(), tenant_id=uuid4(),
        conversation={'id': uuid4()}, channel_id=uuid4(),
        channel_account_mode='mock',
        state={'selected_resource_id': str(uuid4()),
               'selected_service_id': str(uuid4())},
        target_date=date(2026, 6, 8),
    ))
    assert out['step'] == booking_flow.STEP_AWAITING_DATE
    assert out['proposed_date'] == '2026-06-15'


def test_present_slots_no_free_no_future_handoff(monkeypatch):
    from app.services import booking_flow

    async def fake_fetch_service(conn, tenant_id, service_id):
        return {'duration_minutes': 30}

    async def fake_fetch_resource(conn, tenant_id, resource_id, branch_id=None):
        return {'capabilities': {}}

    async def fake_busy(conn, tenant_id, resource_id, target_date):
        return []

    async def fake_next(conn, **kwargs):
        return None

    async def fake_queue(conn, **kwargs):
        return uuid4()

    monkeypatch.setattr(booking_flow, '_fetch_service', fake_fetch_service)
    monkeypatch.setattr(booking_flow, '_fetch_resource', fake_fetch_resource)
    monkeypatch.setattr(booking_flow, '_busy_intervals', fake_busy)
    monkeypatch.setattr(booking_flow, '_suggest_next_available_date', fake_next)
    monkeypatch.setattr(booking_flow, '_queue_text_message', fake_queue)

    out = asyncio.run(booking_flow._present_slots(
        _FakeConn(), tenant_id=uuid4(),
        conversation={'id': uuid4()}, channel_id=uuid4(),
        channel_account_mode='mock',
        state={'selected_resource_id': str(uuid4()),
               'selected_service_id': str(uuid4())},
        target_date=date(2026, 6, 8),
    ))
    assert out['step'] == booking_flow.STEP_AWAITING_SLOT


# ---- _busy_intervals ---------------------------------------------------


def test_busy_intervals_filters_out_of_range_and_returns_minutes():
    from app.services.booking_flow import _busy_intervals
    target = date(2026, 6, 8)
    rows = [
        {'starts_at': datetime(2026, 6, 8, 10, 0, tzinfo=UTC),
         'ends_at': datetime(2026, 6, 8, 10, 30, tzinfo=UTC)},
        # Cross-day appointment whose start is the day before — filtered
        {'starts_at': datetime(2026, 6, 7, 23, 0, tzinfo=UTC),
         'ends_at': datetime(2026, 6, 8, 0, 30, tzinfo=UTC)},
    ]
    conn = _FakeConn(fetch_results=[rows])
    busy = asyncio.run(_busy_intervals(conn, uuid4(), uuid4(), target))
    assert busy == [(600, 630)]


# ---- _suggest_next_available_date -------------------------------------


def test_suggest_next_available_date_returns_first_available(monkeypatch):
    from app.services import booking_flow

    async def fake_resource(conn, tenant_id, resource_id, branch_id=None):
        return {'capabilities': {
            'working_hours': {wd: [{'start': '09:00', 'end': '12:00'}]
                              for wd in booking_flow.WEEKDAY_KEYS}}}

    async def fake_busy(conn, tenant_id, resource_id, target_date):
        return []

    monkeypatch.setattr(booking_flow, '_fetch_resource', fake_resource)
    monkeypatch.setattr(booking_flow, '_busy_intervals', fake_busy)

    out = asyncio.run(booking_flow._suggest_next_available_date(
        _FakeConn(), tenant_id=uuid4(), resource_id=uuid4(),
        duration=30, after=date(2026, 6, 8),
    ))
    assert out == date(2026, 6, 9)


def test_suggest_next_available_date_returns_none_when_resource_missing(monkeypatch):
    from app.services import booking_flow

    async def fake_resource(conn, tenant_id, resource_id, branch_id=None):
        return None

    monkeypatch.setattr(booking_flow, '_fetch_resource', fake_resource)
    out = asyncio.run(booking_flow._suggest_next_available_date(
        _FakeConn(), tenant_id=uuid4(), resource_id=uuid4(),
        duration=30, after=date(2026, 6, 8),
    ))
    assert out is None


def test_suggest_next_available_date_skips_off_days(monkeypatch):
    """When the working hours dict is empty for every day, no candidate fits."""
    from app.services import booking_flow

    async def fake_resource(conn, tenant_id, resource_id, branch_id=None):
        return {'capabilities': {'working_hours': {}}}

    async def fake_busy(*a, **kw):
        return []

    monkeypatch.setattr(booking_flow, '_fetch_resource', fake_resource)
    monkeypatch.setattr(booking_flow, '_busy_intervals', fake_busy)

    out = asyncio.run(booking_flow._suggest_next_available_date(
        _FakeConn(), tenant_id=uuid4(), resource_id=uuid4(),
        duration=30, after=date(2026, 6, 8),
    ))
    assert out is None


# ---- _queue_specialist_photo ------------------------------------------


def test_queue_specialist_photo_no_photo_falls_back_to_text():
    from app.services.booking_flow import _queue_specialist_photo
    msg_id = uuid4()
    conn = _FakeConn(fetchrow_results=[{'id': msg_id}])
    resource = {'id': uuid4(), 'name': 'Dr X',
                'bio': 'Years of experience', 'specialty': 'cardiology'}
    out = asyncio.run(_queue_specialist_photo(
        conn, tenant_id=uuid4(),
        conversation_id=uuid4(), channel_id=uuid4(),
        channel_account_mode='mock', resource=resource,
        booking_step='awaiting_resource',
    ))
    assert out == msg_id


def test_queue_specialist_photo_with_image():
    from app.services.booking_flow import _queue_specialist_photo
    msg_id = uuid4()
    conn = _FakeConn(fetchrow_results=[{'id': msg_id}])
    resource = {
        'id': uuid4(), 'name': 'Dr Y',
        'bio': 'Experienced', 'specialty': 'derm',
        'photo_source_uri': 'https://x/y.jpg',
        'photo_kind': 'image', 'photo_mime_type': 'image/jpeg',
    }
    out = asyncio.run(_queue_specialist_photo(
        conn, tenant_id=uuid4(),
        conversation_id=uuid4(), channel_id=uuid4(),
        channel_account_mode='mock', resource=resource,
        booking_step='awaiting_resource',
    ))
    assert out == msg_id


# ---- _ask_referrer / _ask_referrer_enabled ---------------------------


def test_ask_referrer_returns_awaiting_step(monkeypatch):
    from app.services import booking_flow

    async def fake_queue(conn, **kwargs):
        return uuid4()

    monkeypatch.setattr(booking_flow, '_queue_text_message', fake_queue)
    out = asyncio.run(booking_flow._ask_referrer(
        _FakeConn(), tenant_id=uuid4(),
        conversation={'id': uuid4()}, channel_id=uuid4(),
        channel_account_mode='mock',
    ))
    assert out == {'step': booking_flow.STEP_AWAITING_REFERRER}


def test_ask_referrer_enabled_default_false():
    from app.services.booking_flow import _ask_referrer_enabled
    conn = _FakeConn(fetchval_results=[None])
    assert asyncio.run(_ask_referrer_enabled(conn, uuid4())) is False


def test_ask_referrer_enabled_returns_true():
    from app.services.booking_flow import _ask_referrer_enabled
    conn = _FakeConn(fetchval_results=['true'])
    assert asyncio.run(_ask_referrer_enabled(conn, uuid4())) is True


def test_ask_referrer_enabled_handles_uppercase():
    from app.services.booking_flow import _ask_referrer_enabled
    conn = _FakeConn(fetchval_results=['TRUE'])
    assert asyncio.run(_ask_referrer_enabled(conn, uuid4())) is True


# ---- _resolve_referrer_answer -----------------------------------------


def test_resolve_referrer_answer_skip_token_returns_skipped():
    from app.services.booking_flow import _resolve_referrer_answer
    out = asyncio.run(_resolve_referrer_answer(
        _FakeConn(), tenant_id=uuid4(), contact_id=uuid4(),
        answer_text='no',
    ))
    assert out == {'resolved': False, 'skipped': True}


def test_resolve_referrer_answer_empty_returns_skipped():
    from app.services.booking_flow import _resolve_referrer_answer
    out = asyncio.run(_resolve_referrer_answer(
        _FakeConn(), tenant_id=uuid4(), contact_id=uuid4(),
        answer_text='   ',
    ))
    assert out['skipped'] is True


def test_resolve_referrer_answer_phone_match_resolves():
    from app.services.booking_flow import _resolve_referrer_answer
    referrer_id = uuid4()
    conn = _FakeConn(fetchrow_results=[
        {'id': referrer_id, 'display_name': 'Maria'},
    ])
    out = asyncio.run(_resolve_referrer_answer(
        conn, tenant_id=uuid4(), contact_id=uuid4(),
        answer_text='+57 300 555 1212',
    ))
    assert out['resolved'] is True
    assert out['referrer_contact_id'] == str(referrer_id)
    assert out['referrer_name'] == 'Maria'


def test_resolve_referrer_answer_name_match_resolves():
    from app.services.booking_flow import _resolve_referrer_answer
    referrer_id = uuid4()
    # No phone digits → phone fetchrow returns None; name fetchrow returns hit.
    conn = _FakeConn(fetchrow_results=[
        {'id': referrer_id, 'display_name': 'Carlos'},
    ])
    out = asyncio.run(_resolve_referrer_answer(
        conn, tenant_id=uuid4(), contact_id=uuid4(),
        answer_text='Carlos',
    ))
    assert out['resolved'] is True
    assert out['referrer_name'] == 'Carlos'


def test_resolve_referrer_answer_unresolved_falls_back_to_free_text():
    """Phone lookup → no row; name lookup → no row; falls back to free-text."""
    from app.services.booking_flow import _resolve_referrer_answer
    conn = _FakeConn(fetchrow_results=[None, None])
    out = asyncio.run(_resolve_referrer_answer(
        conn, tenant_id=uuid4(), contact_id=uuid4(),
        answer_text='Some random name with no match',
    ))
    assert out['resolved'] is False
    assert out['referred_by_name'] == 'Some random name with no match'


# ---- maybe_run_booking_flow -------------------------------------------


def test_maybe_run_booking_flow_no_catalog_returns_none():
    from app.services.booking_flow import maybe_run_booking_flow
    out = asyncio.run(maybe_run_booking_flow(
        _FakeConn(), tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'metadata': {}},
        contact={'id': uuid4()},
        inbound_message={'id': uuid4(), 'payload': {}, 'body_text': ''},
        intent='other', has_catalog=False,
    ))
    assert out is None


def test_maybe_run_booking_flow_no_state_no_book_intent_returns_none():
    from app.services.booking_flow import maybe_run_booking_flow
    out = asyncio.run(maybe_run_booking_flow(
        _FakeConn(), tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'metadata': {}},
        contact={'id': uuid4()},
        inbound_message={'id': uuid4(), 'payload': {}, 'body_text': 'hola'},
        intent='other', has_catalog=True,
    ))
    assert out is None


def test_maybe_run_booking_flow_already_processed_returns_skipped(monkeypatch):
    from app.services import booking_flow

    conn = _FakeConn(fetchval_results=[uuid4()])  # idempotency hit
    out = asyncio.run(booking_flow.maybe_run_booking_flow(
        conn, tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'metadata': {'booking_flow': {'step': 'awaiting_service'}}},
        contact={'id': uuid4()},
        inbound_message={'id': uuid4(),
                         'payload': {'interactive_id': 'book_service:xx'},
                         'body_text': ''},
        intent='other', has_catalog=True,
    ))
    assert out == {'action': 'skipped', 'reason': 'already_processed'}


def test_maybe_run_booking_flow_book_intent_asks_referrer(monkeypatch):
    """When the tenant has ask_referrer=true and the contact lacks one, we
    queue the referrer question instead of going straight to services."""
    from app.services import booking_flow

    async def fake_ask_enabled(conn, tenant_id):
        return True

    monkeypatch.setattr(booking_flow, '_ask_referrer_enabled', fake_ask_enabled)

    async def fake_ask(conn, **kwargs):
        return {'step': booking_flow.STEP_AWAITING_REFERRER}

    monkeypatch.setattr(booking_flow, '_ask_referrer', fake_ask)

    async def fake_persist(conn, tenant_id, conv, state):
        return None

    monkeypatch.setattr(booking_flow, '_persist_state', fake_persist)

    out = asyncio.run(booking_flow.maybe_run_booking_flow(
        _FakeConn(fetchval_results=[None]),
        tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'metadata': {}},
        contact={'id': uuid4()},
        inbound_message={'id': uuid4(), 'payload': {}, 'body_text': 'Quiero agendar'},
        intent='book_appointment', has_catalog=True,
    ))
    assert out is not None
    assert out['action'] == 'booking_step_sent'
    assert out['step'] == booking_flow.STEP_AWAITING_REFERRER


def test_maybe_run_booking_flow_book_intent_falls_through_to_services(monkeypatch):
    from app.services import booking_flow

    async def fake_ask_enabled(conn, tenant_id):
        return False

    monkeypatch.setattr(booking_flow, '_ask_referrer_enabled', fake_ask_enabled)

    async def fake_present(conn, **kwargs):
        return {'step': booking_flow.STEP_AWAITING_SERVICE}

    monkeypatch.setattr(booking_flow, '_present_services', fake_present)

    async def fake_persist(conn, tenant_id, conv, state):
        return None

    monkeypatch.setattr(booking_flow, '_persist_state', fake_persist)

    out = asyncio.run(booking_flow.maybe_run_booking_flow(
        _FakeConn(fetchval_results=[None]),
        tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'metadata': {}},
        contact={'id': uuid4()},
        inbound_message={'id': uuid4(), 'payload': {}, 'body_text': 'Quiero agendar'},
        intent='book_appointment', has_catalog=True,
    ))
    assert out == {'action': 'booking_step_sent',
                   'step': booking_flow.STEP_AWAITING_SERVICE}


def test_maybe_run_booking_flow_prefilled_service_routes_packages(monkeypatch):
    from app.services import booking_flow

    svc = uuid4()

    async def fake_ask_enabled(conn, tenant_id):
        return False

    async def fake_fetch_service(conn, tenant_id, service_id):
        return {'id': svc, 'name': 'Prefilled', 'applies_when': None}

    async def fake_packages(conn, **kwargs):
        return None

    async def fake_branches(conn, **kwargs):
        return None

    async def fake_resources(conn, **kwargs):
        return {'step': booking_flow.STEP_AWAITING_DATE,
                'selected_service_id': str(svc)}

    async def fake_persist(*a, **kw):
        return None

    monkeypatch.setattr(booking_flow, '_ask_referrer_enabled', fake_ask_enabled)
    monkeypatch.setattr(booking_flow, '_fetch_service', fake_fetch_service)
    monkeypatch.setattr(booking_flow, '_present_packages', fake_packages)
    monkeypatch.setattr(booking_flow, '_present_branches', fake_branches)
    monkeypatch.setattr(booking_flow, '_present_resources', fake_resources)
    monkeypatch.setattr(booking_flow, '_persist_state', fake_persist)

    out = asyncio.run(booking_flow.maybe_run_booking_flow(
        _FakeConn(fetchval_results=[None]),
        tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'metadata': {}},
        contact={'id': uuid4()},
        inbound_message={'id': uuid4(), 'payload': {}, 'body_text': 'Quiero agendar'},
        intent='book_appointment', has_catalog=True,
        prefilled_service_id=str(svc),
    ))
    assert out['step'] == booking_flow.STEP_AWAITING_DATE


def test_maybe_run_booking_flow_handles_book_service_interactive(monkeypatch):
    from app.services import booking_flow

    svc = uuid4()

    async def fake_fetch_service(conn, tenant_id, service_id):
        return {'id': svc, 'name': 'Pick', 'applies_when': None}

    async def fake_packages(conn, **kwargs):
        return None

    async def fake_branches(conn, **kwargs):
        return None

    async def fake_resources(conn, **kwargs):
        return {'step': booking_flow.STEP_AWAITING_DATE,
                'selected_service_id': str(svc)}

    async def fake_persist(*a, **kw):
        return None

    monkeypatch.setattr(booking_flow, '_fetch_service', fake_fetch_service)
    monkeypatch.setattr(booking_flow, '_present_packages', fake_packages)
    monkeypatch.setattr(booking_flow, '_present_branches', fake_branches)
    monkeypatch.setattr(booking_flow, '_present_resources', fake_resources)
    monkeypatch.setattr(booking_flow, '_persist_state', fake_persist)

    out = asyncio.run(booking_flow.maybe_run_booking_flow(
        _FakeConn(fetchval_results=[None]),
        tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'metadata': {}},
        contact={'id': uuid4()},
        inbound_message={'id': uuid4(),
                         'payload': {'interactive_id': f'book_service:{svc}'},
                         'body_text': ''},
        intent='other', has_catalog=True,
    ))
    assert out['step'] == booking_flow.STEP_AWAITING_DATE


def test_maybe_run_booking_flow_invalid_uuid_in_book_service(monkeypatch):
    from app.services import booking_flow

    async def fake_persist(*a, **kw):
        return None

    monkeypatch.setattr(booking_flow, '_persist_state', fake_persist)

    out = asyncio.run(booking_flow.maybe_run_booking_flow(
        _FakeConn(fetchval_results=[None]),
        tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'metadata': {}},
        contact={'id': uuid4()},
        inbound_message={'id': uuid4(),
                         'payload': {'interactive_id': 'book_service:not-a-uuid'},
                         'body_text': ''},
        intent='other', has_catalog=True,
    ))
    assert out is None


def test_maybe_run_booking_flow_package_use_new(monkeypatch):
    from app.services import booking_flow

    async def fake_branches(conn, **kwargs):
        return None

    async def fake_resources(conn, **kwargs):
        return {**kwargs.get('state', {}), 'step': booking_flow.STEP_AWAITING_DATE}

    async def fake_persist(*a, **kw):
        return None

    monkeypatch.setattr(booking_flow, '_present_branches', fake_branches)
    monkeypatch.setattr(booking_flow, '_present_resources', fake_resources)
    monkeypatch.setattr(booking_flow, '_persist_state', fake_persist)

    state = {'step': booking_flow.STEP_AWAITING_PACKAGE,
             'selected_service_id': str(uuid4()),
             'available_package_ids': [str(uuid4())]}
    out = asyncio.run(booking_flow.maybe_run_booking_flow(
        _FakeConn(fetchval_results=[None]),
        tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'metadata': {'booking_flow': state}},
        contact={'id': uuid4()},
        inbound_message={'id': uuid4(),
                         'payload': {'interactive_id': 'book_package:new'},
                         'body_text': ''},
        intent='other', has_catalog=True,
    ))
    assert out['step'] == booking_flow.STEP_AWAITING_DATE


def test_maybe_run_booking_flow_package_pick(monkeypatch):
    from app.services import booking_flow

    pkg_id = str(uuid4())

    async def fake_branches(conn, **kwargs):
        return None

    async def fake_resources(conn, **kwargs):
        st = kwargs.get('state', {})
        return {**st, 'step': booking_flow.STEP_AWAITING_DATE}

    async def fake_persist(*a, **kw):
        return None

    monkeypatch.setattr(booking_flow, '_present_branches', fake_branches)
    monkeypatch.setattr(booking_flow, '_present_resources', fake_resources)
    monkeypatch.setattr(booking_flow, '_persist_state', fake_persist)

    state = {'step': booking_flow.STEP_AWAITING_PACKAGE,
             'available_package_ids': [pkg_id]}
    out = asyncio.run(booking_flow.maybe_run_booking_flow(
        _FakeConn(fetchval_results=[None]),
        tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'metadata': {'booking_flow': state}},
        contact={'id': uuid4()},
        inbound_message={'id': uuid4(),
                         'payload': {'interactive_id': f'book_package:{pkg_id}'},
                         'body_text': ''},
        intent='other', has_catalog=True,
    ))
    assert out['step'] == booking_flow.STEP_AWAITING_DATE


def test_maybe_run_booking_flow_branch_interactive(monkeypatch):
    from app.services import booking_flow

    branch_id = uuid4()

    async def fake_fetch_branch(conn, tenant_id, branch_uuid):
        return {'id': branch_id, 'name': 'B', 'city': 'Bog'}

    async def fake_resources(conn, **kwargs):
        return {**kwargs['state'], 'step': booking_flow.STEP_AWAITING_RESOURCE}

    async def fake_persist(*a, **kw):
        return None

    monkeypatch.setattr(booking_flow, '_fetch_branch', fake_fetch_branch)
    monkeypatch.setattr(booking_flow, '_present_resources', fake_resources)
    monkeypatch.setattr(booking_flow, '_persist_state', fake_persist)

    state = {'step': booking_flow.STEP_AWAITING_BRANCH}
    out = asyncio.run(booking_flow.maybe_run_booking_flow(
        _FakeConn(fetchval_results=[None]),
        tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'metadata': {'booking_flow': state}},
        contact={'id': uuid4()},
        inbound_message={'id': uuid4(),
                         'payload': {'interactive_id': f'book_branch:{branch_id}'},
                         'body_text': ''},
        intent='other', has_catalog=True,
    ))
    assert out['step'] == booking_flow.STEP_AWAITING_RESOURCE


def test_maybe_run_booking_flow_resource_interactive(monkeypatch):
    from app.services import booking_flow

    res_id = uuid4()

    async def fake_fetch_resource(conn, tenant_id, resource_id, branch_id=None):
        return {'id': res_id, 'name': 'Dr X', 'capabilities': {}}

    async def fake_date(conn, **kwargs):
        return {**kwargs['state'], 'step': booking_flow.STEP_AWAITING_DATE}

    async def fake_persist(*a, **kw):
        return None

    monkeypatch.setattr(booking_flow, '_fetch_resource', fake_fetch_resource)
    monkeypatch.setattr(booking_flow, '_present_date', fake_date)
    monkeypatch.setattr(booking_flow, '_persist_state', fake_persist)

    state = {'step': booking_flow.STEP_AWAITING_RESOURCE,
             'selected_service_id': str(uuid4())}
    out = asyncio.run(booking_flow.maybe_run_booking_flow(
        _FakeConn(fetchval_results=[None]),
        tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'metadata': {'booking_flow': state}},
        contact={'id': uuid4()},
        inbound_message={'id': uuid4(),
                         'payload': {'interactive_id': f'book_resource:{res_id}'},
                         'body_text': ''},
        intent='other', has_catalog=True,
    ))
    assert out['step'] == booking_flow.STEP_AWAITING_DATE


def test_maybe_run_booking_flow_date_interactive_today(monkeypatch):
    from app.services import booking_flow

    async def fake_slots(conn, **kwargs):
        return {**kwargs['state'], 'step': booking_flow.STEP_AWAITING_SLOT,
                'proposed_date': kwargs['target_date'].isoformat()}

    async def fake_persist(*a, **kw):
        return None

    monkeypatch.setattr(booking_flow, '_present_slots', fake_slots)
    monkeypatch.setattr(booking_flow, '_persist_state', fake_persist)

    state = {'step': booking_flow.STEP_AWAITING_DATE,
             'selected_resource_id': str(uuid4()),
             'selected_service_id': str(uuid4())}
    out = asyncio.run(booking_flow.maybe_run_booking_flow(
        _FakeConn(fetchval_results=[None]),
        tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'metadata': {'booking_flow': state}},
        contact={'id': uuid4()},
        inbound_message={'id': uuid4(),
                         'payload': {'interactive_id': 'book_date:today'},
                         'body_text': ''},
        intent='other', has_catalog=True,
    ))
    assert out['step'] == booking_flow.STEP_AWAITING_SLOT


def test_maybe_run_booking_flow_date_interactive_other_re_asks(monkeypatch):
    from app.services import booking_flow

    async def fake_queue(conn, **kwargs):
        return uuid4()

    async def fake_persist(*a, **kw):
        return None

    monkeypatch.setattr(booking_flow, '_queue_text_message', fake_queue)
    monkeypatch.setattr(booking_flow, '_persist_state', fake_persist)

    state = {'step': booking_flow.STEP_AWAITING_DATE,
             'selected_resource_id': str(uuid4())}
    out = asyncio.run(booking_flow.maybe_run_booking_flow(
        _FakeConn(fetchval_results=[None]),
        tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'metadata': {'booking_flow': state}},
        contact={'id': uuid4()},
        inbound_message={'id': uuid4(),
                         'payload': {'interactive_id': 'book_date:other'},
                         'body_text': ''},
        intent='other', has_catalog=True,
    ))
    assert out['step'] == booking_flow.STEP_AWAITING_DATE


def test_maybe_run_booking_flow_slot_not_in_proposed(monkeypatch):
    from app.services import booking_flow

    async def fake_queue(conn, **kwargs):
        return uuid4()

    async def fake_persist(*a, **kw):
        return None

    monkeypatch.setattr(booking_flow, '_queue_text_message', fake_queue)
    monkeypatch.setattr(booking_flow, '_persist_state', fake_persist)

    state = {'step': booking_flow.STEP_AWAITING_SLOT,
             'proposed_date': '2026-06-08',
             'proposed_slots': ['09:00', '09:30']}
    out = asyncio.run(booking_flow.maybe_run_booking_flow(
        _FakeConn(fetchval_results=[None]),
        tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'metadata': {'booking_flow': state}},
        contact={'id': uuid4()},
        inbound_message={'id': uuid4(),
                         'payload': {'interactive_id': 'book_slot:14:00'},
                         'body_text': ''},
        intent='other', has_catalog=True,
    ))
    assert out['step'] == booking_flow.STEP_AWAITING_DATE


def test_maybe_run_booking_flow_slot_matches_proposed(monkeypatch):
    from app.services import booking_flow

    async def fake_create(conn, **kwargs):
        return {'step': booking_flow.STEP_COMPLETED,
                'appointment_id': str(uuid4())}

    async def fake_persist(*a, **kw):
        return None

    monkeypatch.setattr(booking_flow, '_create_appointment', fake_create)
    monkeypatch.setattr(booking_flow, '_persist_state', fake_persist)

    state = {'step': booking_flow.STEP_AWAITING_SLOT,
             'proposed_date': '2026-06-08',
             'proposed_slots': ['09:00', '09:30']}
    out = asyncio.run(booking_flow.maybe_run_booking_flow(
        _FakeConn(fetchval_results=[None]),
        tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'metadata': {'booking_flow': state}},
        contact={'id': uuid4()},
        inbound_message={'id': uuid4(),
                         'payload': {'interactive_id': 'book_slot:09:00'},
                         'body_text': ''},
        intent='other', has_catalog=True,
    ))
    assert out['step'] == booking_flow.STEP_COMPLETED


def test_maybe_run_booking_flow_referrer_answer_continues_to_services(monkeypatch):
    from app.services import booking_flow

    async def fake_resolve(conn, **kwargs):
        return {'resolved': False, 'skipped': True}

    async def fake_present(conn, **kwargs):
        return {'step': booking_flow.STEP_AWAITING_SERVICE}

    async def fake_persist(*a, **kw):
        return None

    monkeypatch.setattr(booking_flow, '_resolve_referrer_answer', fake_resolve)
    monkeypatch.setattr(booking_flow, '_present_services', fake_present)
    monkeypatch.setattr(booking_flow, '_persist_state', fake_persist)

    state = {'step': booking_flow.STEP_AWAITING_REFERRER}
    out = asyncio.run(booking_flow.maybe_run_booking_flow(
        _FakeConn(fetchval_results=[None]),
        tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'metadata': {'booking_flow': state}},
        contact={'id': uuid4()},
        inbound_message={'id': uuid4(), 'payload': {}, 'body_text': 'no'},
        intent='other', has_catalog=True,
    ))
    assert out['step'] == booking_flow.STEP_AWAITING_SERVICE


# ---- _create_appointment (slot conflict path) -------------------------


def test_create_appointment_slot_conflict_returns_back_to_date(monkeypatch):
    """When the insert raises (asyncpg.ExclusionViolationError), the helper
    queues an explanatory text and rewinds the state to awaiting_date."""
    from app.services import booking_flow

    class _ConflictConn(_FakeConn):
        async def fetchrow(self, sql, *args):
            # First fetchrow is _fetch_service; let it return a service row
            if 'service_catalog' in sql:
                return {'id': uuid4(), 'name': 'X', 'duration_minutes': 30,
                        'applies_when': None}
            # Insert into appointments raises
            if 'insert into app.appointments' in sql:
                raise RuntimeError('exclusion_violation')
            return await super().fetchrow(sql, *args)

    async def fake_queue(conn, **kwargs):
        return uuid4()

    monkeypatch.setattr(booking_flow, '_queue_text_message', fake_queue)

    conn = _ConflictConn(fetchval_results=[None])
    out = asyncio.run(booking_flow._create_appointment(
        conn, tenant_id=uuid4(),
        contact={'id': uuid4()},
        conversation={'id': uuid4()},
        channel_id=uuid4(), channel_account_mode='mock',
        state={'proposed_date': '2026-06-08',
               'duration_minutes': 30,
               'selected_resource_id': str(uuid4()),
               'selected_service_id': str(uuid4()),
               'proposed_slots': ['09:00']},
        slot_start='09:00',
    ))
    assert out['step'] == booking_flow.STEP_AWAITING_DATE
    assert 'proposed_slots' not in out
