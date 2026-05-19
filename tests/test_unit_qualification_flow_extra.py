"""More tests for `app/services/qualification_flow.py` covering uncovered branches."""
from __future__ import annotations

import asyncio
import json
from uuid import uuid4


class _FakeConn:
    def __init__(self, *, fetch_results=None, fetchrow_results=None, fetchval_results=None):
        self._fetch = list(fetch_results or [])
        self._fetchrow = list(fetchrow_results or [])
        self._fetchval = list(fetchval_results or [])
        self.executed = []

    async def fetch(self, sql, *args):
        return self._fetch.pop(0) if self._fetch else []

    async def fetchrow(self, sql, *args):
        return self._fetchrow.pop(0) if self._fetchrow else None

    async def fetchval(self, sql, *args):
        return self._fetchval.pop(0) if self._fetchval else None

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


# ═══ _apply_vip_tag tag_id None branch ═══════════════════════════════════


def test_apply_vip_tag_returns_none_when_no_tag(monkeypatch):
    """When _ensure_vip_tag returns None, no insert happens."""
    from app.services import qualification_flow

    async def _fake_ensure(*args, **kw):
        return None

    monkeypatch.setattr(qualification_flow, '_ensure_vip_tag', _fake_ensure)
    conn = _FakeConn()

    async def _go():
        return await qualification_flow._apply_vip_tag(conn, uuid4(), uuid4())

    out = asyncio.run(_go())
    assert out is None
    assert conn.executed == []


def test_apply_vip_tag_inserts_when_tag_exists(monkeypatch):
    from app.services import qualification_flow

    tag_id = uuid4()
    async def _fake_ensure(*args, **kw):
        return tag_id

    monkeypatch.setattr(qualification_flow, '_ensure_vip_tag', _fake_ensure)
    conn = _FakeConn()

    async def _go():
        return await qualification_flow._apply_vip_tag(conn, uuid4(), uuid4())

    out = asyncio.run(_go())
    assert out == tag_id
    assert any('contact_tag_assignments' in sql for sql, _ in conn.executed)


# ═══ _options_for_render — invalid options ═════════════════════════════


def test_options_for_render_skips_non_dict_and_blank():
    from app.services.qualification_flow import _options_for_render
    q = {
        'options': [
            'not-a-dict',
            {'value': '   ', 'label': 'blank'},  # value blank after strip
            {'value': 'ok', 'label': ''},  # blank label falls to value
            {'id': 'fallback-id', 'label': 'X'},  # uses id when no value
        ],
    }
    out = _options_for_render(q)
    # 2 valid: 'ok' and 'fallback-id'
    values = [o['value'] for o in out]
    assert 'ok' in values
    assert 'fallback-id' in values


# ═══ _next_pending_question skip optional with False marker ════════════


def test_next_pending_question_skips_explicit_false_optional():
    from app.services.qualification_flow import _next_pending_question
    questions = [
        {'id': 'q1', 'required': False},
        {'id': 'q2', 'required': True},
    ]
    answered = {'q1': False}  # user explicitly skipped optional
    out = _next_pending_question(questions, answered)
    assert out['id'] == 'q2'


# ═══ _persist_state ═══════════════════════════════════════════════════════


def test_persist_state_with_state_dict():
    from app.services.qualification_flow import _persist_state

    conv = {
        'id': uuid4(),
        'metadata': {'other_key': 'preserved'},
    }
    conn = _FakeConn()
    state = {'answered': {'q1': 'a'}, 'started_at': '2026-05-19'}

    async def _go():
        await _persist_state(conn, uuid4(), conv, state)

    asyncio.run(_go())
    sql, args = conn.executed[0]
    # The metadata contains both `qualification` (the new state) AND `other_key`
    saved_meta = json.loads(args[0])
    assert saved_meta['qualification'] == state
    assert saved_meta['other_key'] == 'preserved'


def test_persist_state_with_none_pops_qualification():
    """When state is None, removes qualification key from metadata."""
    from app.services.qualification_flow import _persist_state

    conv = {
        'id': uuid4(),
        'metadata': {'qualification': {'foo': 'bar'}, 'other_key': 'x'},
    }
    conn = _FakeConn()

    async def _go():
        await _persist_state(conn, uuid4(), conv, None)

    asyncio.run(_go())
    sql, args = conn.executed[0]
    saved_meta = json.loads(args[0])
    assert 'qualification' not in saved_meta
    assert saved_meta['other_key'] == 'x'


def test_persist_state_json_string_metadata():
    from app.services.qualification_flow import _persist_state

    conv = {
        'id': uuid4(),
        'metadata': '{"existing": "data"}',
    }
    conn = _FakeConn()

    async def _go():
        await _persist_state(conn, uuid4(), conv, {'step': 1})

    asyncio.run(_go())
    sql, args = conn.executed[0]
    saved_meta = json.loads(args[0])
    assert saved_meta['existing'] == 'data'
    assert saved_meta['qualification'] == {'step': 1}


def test_persist_state_invalid_metadata_falls_back_to_empty():
    from app.services.qualification_flow import _persist_state

    conv = {
        'id': uuid4(),
        'metadata': 'broken json',
    }
    conn = _FakeConn()

    async def _go():
        await _persist_state(conn, uuid4(), conv, {'step': 1})

    asyncio.run(_go())
    # Doesn't raise
    sql, args = conn.executed[0]
    saved_meta = json.loads(args[0])
    assert saved_meta == {'qualification': {'step': 1}}
