"""Tests to push booking_flow.py to ≥95%.

Targets specific uncovered branches identified from coverage JSON.
"""
from __future__ import annotations

import asyncio
from datetime import date
from uuid import uuid4



class _FakeConn:
    def __init__(self, *, fetch_results=None, fetchrow_results=None, fetchval_results=None, execute_raises=None):
        self._fetch = list(fetch_results or [])
        self._fetchrow = list(fetchrow_results or [])
        self._fetchval = list(fetchval_results or [])
        self._execute_raises = execute_raises
        self.executed = []

    async def fetch(self, sql, *args):
        return self._fetch.pop(0) if self._fetch else []

    async def fetchrow(self, sql, *args):
        v = self._fetchrow.pop(0) if self._fetchrow else None
        if isinstance(v, Exception):
            raise v
        return v

    async def fetchval(self, sql, *args):
        return self._fetchval.pop(0) if self._fetchval else None

    async def execute(self, sql, *args):
        if self._execute_raises:
            raise self._execute_raises
        self.executed.append((sql, args))

    def transaction(self):
        class _T:
            async def __aenter__(self_):
                return self_
            async def __aexit__(self_, *exc):
                return None
        return _T()


# ═══ _booking_state edge cases ════════════════════════════════════════════


def test_booking_state_meta_is_list_returns_empty():
    """parse_json returns a list (or other non-dict). Defensive guard line 83-84."""
    from app.services.booking_flow import _booking_state
    # Force the metadata to be a non-dict after parse_json
    conv = {'metadata': '["not-a-dict"]'}  # JSON list
    assert _booking_state(conv) == {}


def test_interactive_id_payload_is_list_returns_none():
    """Defensive: payload parses to non-dict (list) → returns None tuple (line 92-93)."""
    from app.services.booking_flow import _interactive_id
    msg = {'payload': '["not-dict"]'}
    assert _interactive_id(msg) == (None, None)


# ═══ _qualification_facts_from_conversation guards ═══════════════════════


def test_qualification_facts_meta_non_dict_returns_empty():
    """Defensive: parsed metadata is non-dict (line 149-150)."""
    from app.services.booking_flow import _qualification_facts_from_conversation
    conv = {'metadata': '["not-a-dict"]'}
    assert _qualification_facts_from_conversation(conv) == {}


# ═══ _working_hours_for_date defensive paths ═════════════════════════════


def test_working_hours_for_date_config_non_dict_returns_empty():
    """parse_json returns non-dict → empty franjas (line 472-473)."""
    from app.services.booking_flow import _working_hours_for_date
    # capabilities is a JSON list — parse_json returns a list, not dict
    out = _working_hours_for_date('[1,2,3]', date(2026, 5, 19))
    assert out == []


def test_working_hours_for_date_franjas_non_list_returns_empty():
    """working_hours[day] is not a list (line 479-480)."""
    from app.services.booking_flow import _working_hours_for_date
    caps = {'working_hours': {'mon': 'not-a-list'}}  # Monday → date
    out = _working_hours_for_date(caps, date(2026, 5, 18))  # Monday
    assert out == []


# ═══ _persist_state edge ═══════════════════════════════════════════════


def test_persist_state_with_non_dict_metadata(monkeypatch):
    """When conversation metadata parses to non-dict, defaults to empty."""
    from app.services.booking_flow import _persist_state
    conn = _FakeConn()
    # Metadata is a JSON list → parse_json returns a list → falls to {}
    conv = {'id': uuid4(), 'metadata': '[1,2,3]'}

    async def _go():
        await _persist_state(conn, uuid4(), conv, {'step': 'awaiting_service'})

    asyncio.run(_go())
    assert len(conn.executed) == 1


# ═══ booking_flow happy paths via maybe_run_booking_flow ════════════════


def test_maybe_run_booking_flow_no_catalog_returns_none():
    from app.services.booking_flow import maybe_run_booking_flow

    async def _go():
        return await maybe_run_booking_flow(
            _FakeConn(),
            tenant_id=uuid4(), channel_id=uuid4(),
            channel_account_mode='mock',
            conversation={'id': uuid4(), 'metadata': {}},
            contact={'id': uuid4()},
            inbound_message={'id': uuid4(), 'payload': {}, 'body_text': ''},
            intent='greeting',
            has_catalog=False,
        )

    assert asyncio.run(_go()) is None


def test_maybe_run_booking_flow_no_state_no_interactive_no_intent():
    """has_catalog=True but state empty, no interactive id, intent != book_appointment → None."""
    from app.services.booking_flow import maybe_run_booking_flow

    async def _go():
        return await maybe_run_booking_flow(
            _FakeConn(),
            tenant_id=uuid4(), channel_id=uuid4(),
            channel_account_mode='mock',
            conversation={'id': uuid4(), 'metadata': {}},
            contact={'id': uuid4()},
            inbound_message={'id': uuid4(), 'payload': {}, 'body_text': 'hola'},
            intent='greeting',
            has_catalog=True,
        )

    assert asyncio.run(_go()) is None


def test_maybe_run_booking_flow_idempotency_returns_skipped():
    """idempotency_key already exists in domain_events → skipped."""
    from app.services.booking_flow import maybe_run_booking_flow

    # First fetchval is the idempotency check — return non-None to indicate "already processed"
    conn = _FakeConn(fetchval_results=[uuid4()])

    async def _go():
        return await maybe_run_booking_flow(
            conn,
            tenant_id=uuid4(), channel_id=uuid4(),
            channel_account_mode='mock',
            conversation={'id': uuid4(), 'metadata': {'booking_flow': {'step': 'awaiting_service'}}},
            contact={'id': uuid4()},
            inbound_message={'id': uuid4(), 'payload': {}, 'body_text': ''},
            intent='other',
            has_catalog=True,
        )

    out = asyncio.run(_go())
    assert out == {'action': 'skipped', 'reason': 'already_processed'}


# ═══ _resolve_referrer_answer skip / free-text fallback ══════════════════


def test_resolve_referrer_answer_skip_tokens():
    """Skip tokens (no, nadie, etc.) → outcome.skipped=True."""
    from app.services.booking_flow import _resolve_referrer_answer

    async def _go():
        return await _resolve_referrer_answer(
            _FakeConn(),
            tenant_id=uuid4(),
            contact_id=uuid4(),
            answer_text='nadie',
        )

    out = asyncio.run(_go())
    assert out['skipped'] is True


def test_resolve_referrer_answer_empty_skip():
    """Empty answer → skipped."""
    from app.services.booking_flow import _resolve_referrer_answer

    async def _go():
        return await _resolve_referrer_answer(
            _FakeConn(),
            tenant_id=uuid4(), contact_id=uuid4(),
            answer_text='   ',
        )

    out = asyncio.run(_go())
    assert out['skipped'] is True


def test_resolve_referrer_answer_phone_match():
    """Digit-rich answer + DB returns referrer → resolved=True."""
    from app.services.booking_flow import _resolve_referrer_answer

    referrer_id = uuid4()
    conn = _FakeConn(fetchrow_results=[
        {'id': referrer_id, 'display_name': 'María'},  # phone lookup matches
    ])

    async def _go():
        return await _resolve_referrer_answer(
            conn, tenant_id=uuid4(), contact_id=uuid4(),
            answer_text='+57 300-555-1234',
        )

    out = asyncio.run(_go())
    assert out['resolved'] is True
    assert out['referrer_name'] == 'María'


def test_resolve_referrer_answer_name_match_only():
    """No digits in answer → name lookup only. If it matches, resolved=True."""
    from app.services.booking_flow import _resolve_referrer_answer

    referrer_id = uuid4()
    # Only 1 fetchrow because no digits → no phone lookup, only name lookup
    conn = _FakeConn(fetchrow_results=[
        {'id': referrer_id, 'display_name': 'Pedro'},  # name lookup matches
    ])

    async def _go():
        return await _resolve_referrer_answer(
            conn, tenant_id=uuid4(), contact_id=uuid4(),
            answer_text='Pedro',
        )

    out = asyncio.run(_go())
    assert out['resolved'] is True


def test_resolve_referrer_answer_free_text_fallback():
    """No match → records `referred_by_name` and returns dict with that field."""
    from app.services.booking_flow import _resolve_referrer_answer
    conn = _FakeConn(fetchrow_results=[None, None])  # neither lookup matches

    async def _go():
        return await _resolve_referrer_answer(
            conn, tenant_id=uuid4(), contact_id=uuid4(),
            answer_text='un amigo del trabajo',
        )

    out = asyncio.run(_go())
    assert out['resolved'] is False
    assert out['referred_by_name'] == 'un amigo del trabajo'


# ═══ _ask_referrer_enabled ════════════════════════════════════════════════


def test_ask_referrer_enabled_true():
    from app.services.booking_flow import _ask_referrer_enabled
    conn = _FakeConn(fetchval_results=['true'])

    async def _go():
        return await _ask_referrer_enabled(conn, uuid4())

    assert asyncio.run(_go()) is True


def test_ask_referrer_enabled_false_or_missing():
    from app.services.booking_flow import _ask_referrer_enabled
    conn = _FakeConn(fetchval_results=[None])  # no setting

    async def _go():
        return await _ask_referrer_enabled(conn, uuid4())

    assert asyncio.run(_go()) is False
