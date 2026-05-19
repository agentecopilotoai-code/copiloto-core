"""Extra coverage for ``app/services/rag_orchestrator.py``.

These tests use a lightweight ``_FakeConn`` stand-in for asyncpg plus
selective monkeypatching of helper services (audit, llm_answer, etc.) so
the orchestrator's branching can be exercised without hitting the DB or
the LLM stack.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4


# ───────── FakeConn ─────────────────────────────────────────────────────


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


# ───────── _load_active_resources_context ──────────────────────────────


def test_load_active_resources_context_default_when_no_rows():
    from app.services.rag_orchestrator import _load_active_resources_context

    conn = _FakeConn(fetch_results=[[]])
    out = asyncio.run(_load_active_resources_context(conn, uuid4()))
    assert 'profesionales' in out.lower()


def test_load_active_resources_context_formats_with_type():
    from app.services.rag_orchestrator import _load_active_resources_context
    rows = [
        {'name': 'Dr A', 'resource_type': 'staff'},
        {'name': 'Mariana', 'resource_type': ''},
    ]
    conn = _FakeConn(fetch_results=[rows])
    out = asyncio.run(_load_active_resources_context(conn, uuid4()))
    assert 'Dr A (staff)' in out
    assert '- Mariana' in out


# ───────── _clear_pending_recall ────────────────────────────────────────


def test_clear_pending_recall_runs_update():
    from app.services.rag_orchestrator import _clear_pending_recall

    conn = _FakeConn()
    asyncio.run(_clear_pending_recall(conn, uuid4(), uuid4()))
    assert len(conn.executed) == 1
    assert 'pending_recall' in conn.executed[0][0]


# ───────── _resolve_answer (no-LLM paths) ──────────────────────────────


def _settings(**overrides):
    defaults = {
        'answer_engine': 'template',
        'cascade_template_min_score': 0.55,
        'cascade_llm_min_score': 0.12,
        'local_llm_base_url': 'http://fake',
        'local_llm_model': 'fake',
        'local_llm_timeout_seconds': 1,
        'cloud_llm_provider': None,
        'cloud_llm_api_key': None,
        'cloud_llm_model': '',
        'cloud_llm_timeout_seconds': 1,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_resolve_answer_template_engine_empty_matches():
    from app.services.rag_orchestrator import _resolve_answer
    out = asyncio.run(_resolve_answer(
        question='hola', matches=[],
        settings=_settings(answer_engine='template'),
        tenant_no_train=True,
    ))
    assert isinstance(out, dict)
    assert out['sufficient_context'] is False


def test_resolve_answer_local_llm_engine_no_matches_falls_back():
    from app.services.rag_orchestrator import _resolve_answer
    out = asyncio.run(_resolve_answer(
        question='hola', matches=[],
        settings=_settings(answer_engine='local_llm'),
        tenant_no_train=True,
    ))
    assert out['sufficient_context'] is False


def test_resolve_answer_local_llm_with_matches(monkeypatch):
    """When matches are present, it invokes build_llm_answer."""
    from app.services import rag_orchestrator

    async def fake_build(question, matches, **kwargs):
        return {'sufficient_context': True, 'answer': 'ok',
                'status': 'answered', 'llm_used': True}

    monkeypatch.setattr(rag_orchestrator, 'build_llm_answer', fake_build)

    fake_match = SimpleNamespace(score=0.9)
    out = asyncio.run(rag_orchestrator._resolve_answer(
        question='hola', matches=[fake_match],
        settings=_settings(answer_engine='local_llm'),
        tenant_no_train=True,
    ))
    assert out['llm_used'] is True


def test_resolve_answer_cloud_llm_no_matches_falls_back():
    from app.services.rag_orchestrator import _resolve_answer
    out = asyncio.run(_resolve_answer(
        question='hola', matches=[],
        settings=_settings(answer_engine='cloud_llm'),
        tenant_no_train=False,
    ))
    assert out['sufficient_context'] is False


def test_resolve_answer_cloud_llm_not_configured_falls_back(monkeypatch):
    from app.services import rag_orchestrator

    def fake_grounded(question, matches, min_score=None):
        return {'sufficient_context': False, 'answer': None}

    monkeypatch.setattr(rag_orchestrator, 'build_grounded_answer', fake_grounded)

    out = asyncio.run(rag_orchestrator._resolve_answer(
        question='hola',
        matches=[SimpleNamespace(score=0.9)],
        settings=_settings(answer_engine='cloud_llm'),
        tenant_no_train=False,
    ))
    # Cloud not configured (provider/key None) → fall back to grounded answer.
    assert isinstance(out, dict)
    assert out['sufficient_context'] is False


def test_resolve_answer_cloud_llm_blocked_by_no_train(monkeypatch):
    from app.services import rag_orchestrator

    def fake_grounded(question, matches, min_score=None):
        return {'sufficient_context': False, 'answer': None}

    monkeypatch.setattr(rag_orchestrator, 'build_grounded_answer', fake_grounded)

    out = asyncio.run(rag_orchestrator._resolve_answer(
        question='hola',
        matches=[SimpleNamespace(score=0.9)],
        settings=_settings(
            answer_engine='cloud_llm',
            cloud_llm_provider='anthropic',
            cloud_llm_api_key='sk-test',
            cloud_llm_model='claude',
        ),
        tenant_no_train=True,  # blocks cloud
    ))
    assert isinstance(out, dict)


def test_resolve_answer_cloud_llm_invoked_when_allowed(monkeypatch):
    from app.services import rag_orchestrator

    async def fake_cloud(question, matches, **kwargs):
        return {'sufficient_context': True, 'answer': 'cloud-said',
                'cloud_llm_used': True, 'status': 'answered'}

    monkeypatch.setattr(rag_orchestrator, 'build_cloud_llm_answer', fake_cloud)

    out = asyncio.run(rag_orchestrator._resolve_answer(
        question='hola',
        matches=[SimpleNamespace(score=0.9)],
        settings=_settings(
            answer_engine='cloud_llm',
            cloud_llm_provider='anthropic',
            cloud_llm_api_key='sk-x',
            cloud_llm_model='claude',
        ),
        tenant_no_train=False,
    ))
    assert out.get('cloud_llm_used') is True


def test_resolve_answer_cascade_template_high_score_returns_template(monkeypatch):
    """When the template top match clears the high threshold, the cascade
    short-circuits to template — no LLM call made."""
    from app.services import rag_orchestrator

    def fake_grounded(question, matches, min_score=None):
        return {'sufficient_context': True, 'answer': 'template-answer',
                'status': 'answered'}

    monkeypatch.setattr(rag_orchestrator, 'build_grounded_answer', fake_grounded)

    out = asyncio.run(rag_orchestrator._resolve_answer(
        question='hola',
        matches=[SimpleNamespace(score=0.9)],
        settings=_settings(answer_engine='cascade'),
        tenant_no_train=True,
    ))
    assert out['answer'] == 'template-answer'


def test_resolve_answer_cascade_falls_through_to_llm(monkeypatch):
    """Template misses → LLM tries → LLM answers."""
    from app.services import rag_orchestrator

    def fake_grounded(question, matches, min_score=None):
        return {'sufficient_context': False, 'answer': None, 'status': 'no_context'}

    async def fake_llm(question, matches, **kwargs):
        return {'sufficient_context': True, 'answer': 'llm-said',
                'llm_used': True, 'status': 'answered'}

    monkeypatch.setattr(rag_orchestrator, 'build_grounded_answer', fake_grounded)
    monkeypatch.setattr(rag_orchestrator, 'build_llm_answer', fake_llm)

    out = asyncio.run(rag_orchestrator._resolve_answer(
        question='hola',
        matches=[SimpleNamespace(score=0.5)],
        settings=_settings(answer_engine='cascade'),
        tenant_no_train=True,
    ))
    assert out['llm_used'] is True
    assert out['answer'] == 'llm-said'


def test_resolve_answer_cascade_local_llm_unavailable_no_train_falls_to_handoff(monkeypatch):
    from app.services import rag_orchestrator

    def fake_grounded(question, matches, min_score=None):
        return {'sufficient_context': False, 'answer': None, 'status': 'no_context'}

    async def fake_llm(question, matches, **kwargs):
        raise RuntimeError('ollama down')

    monkeypatch.setattr(rag_orchestrator, 'build_grounded_answer', fake_grounded)
    monkeypatch.setattr(rag_orchestrator, 'build_llm_answer', fake_llm)

    out = asyncio.run(rag_orchestrator._resolve_answer(
        question='hola',
        matches=[SimpleNamespace(score=0.5)],
        settings=_settings(answer_engine='cascade',
                           cloud_llm_provider='anthropic',
                           cloud_llm_api_key='sk-x',
                           cloud_llm_model='claude'),
        tenant_no_train=True,  # blocks cloud → handoff
    ))
    assert out['status'] == 'escalate_to_human'


def test_resolve_answer_cascade_cloud_succeeds_after_llm_fails(monkeypatch):
    from app.services import rag_orchestrator

    def fake_grounded(question, matches, min_score=None):
        return {'sufficient_context': False, 'answer': None, 'status': 'no_context'}

    async def fake_llm(question, matches, **kwargs):
        raise RuntimeError('ollama down')

    async def fake_cloud(question, matches, **kwargs):
        return {'sufficient_context': True, 'answer': 'cloud',
                'cloud_llm_used': True, 'status': 'answered',
                'token_usage': {'cache_read_tokens': 0}}

    monkeypatch.setattr(rag_orchestrator, 'build_grounded_answer', fake_grounded)
    monkeypatch.setattr(rag_orchestrator, 'build_llm_answer', fake_llm)
    monkeypatch.setattr(rag_orchestrator, 'build_cloud_llm_answer', fake_cloud)

    out = asyncio.run(rag_orchestrator._resolve_answer(
        question='hola',
        matches=[SimpleNamespace(score=0.5)],
        settings=_settings(answer_engine='cascade',
                           cloud_llm_provider='anthropic',
                           cloud_llm_api_key='sk-x',
                           cloud_llm_model='claude'),
        tenant_no_train=False,
    ))
    assert out['answer'] == 'cloud'


def test_resolve_answer_cascade_no_llm_candidates_to_handoff(monkeypatch):
    """When no chunks clear the LLM threshold, cascade short-circuits to handoff
    without even attempting the LLM."""
    from app.services import rag_orchestrator

    def fake_grounded(question, matches, min_score=None):
        return {'sufficient_context': False, 'answer': None, 'status': 'no_context'}

    monkeypatch.setattr(rag_orchestrator, 'build_grounded_answer', fake_grounded)

    out = asyncio.run(rag_orchestrator._resolve_answer(
        question='hola',
        matches=[SimpleNamespace(score=0.05)],  # below cascade_llm_min_score=0.12
        settings=_settings(answer_engine='cascade'),
        tenant_no_train=True,
    ))
    assert out['status'] == 'escalate_to_human'


def test_resolve_answer_cascade_llm_returns_insufficient_then_handoff(monkeypatch):
    """LLM returns sufficient_context=False → cascade falls through to handoff
    (no cloud configured)."""
    from app.services import rag_orchestrator

    def fake_grounded(question, matches, min_score=None):
        return {'sufficient_context': False, 'answer': None, 'status': 'no_context'}

    async def fake_llm(question, matches, **kwargs):
        return {'sufficient_context': False, 'answer': None, 'status': 'no_context'}

    monkeypatch.setattr(rag_orchestrator, 'build_grounded_answer', fake_grounded)
    monkeypatch.setattr(rag_orchestrator, 'build_llm_answer', fake_llm)

    out = asyncio.run(rag_orchestrator._resolve_answer(
        question='hola',
        matches=[SimpleNamespace(score=0.5)],
        settings=_settings(answer_engine='cascade'),
        tenant_no_train=True,
    ))
    assert out['status'] == 'escalate_to_human'


# ───────── _resolve_conversational ─────────────────────────────────────


def test_resolve_conversational_llm_success(monkeypatch):
    from app.services import rag_orchestrator
    from app.services.conversation_flow import ConversationContext, STAGE_START

    async def fake_conv(question, matches, **kwargs):
        return {'sufficient_context': True, 'answer': 'conv-answer',
                'llm_used': True, 'status': 'answered'}

    monkeypatch.setattr(rag_orchestrator, 'build_conversational_llm_answer', fake_conv)

    ctx = ConversationContext(stage=STAGE_START, collected={})
    out = asyncio.run(rag_orchestrator._resolve_conversational(
        question='hola', matches=[],
        ctx=ctx, history='',
        settings=_settings(),
        business_name='Negocio',
        tenant_no_train=True,
    ))
    assert out['answer'] == 'conv-answer'


def test_resolve_conversational_llm_fails_cloud_blocked_falls_to_qa(monkeypatch):
    from app.services import rag_orchestrator
    from app.services.conversation_flow import ConversationContext, STAGE_START

    async def fake_conv(question, matches, **kwargs):
        raise RuntimeError('ollama down')

    async def fake_resolve(question, matches, settings, **kwargs):
        return {'sufficient_context': True, 'answer': 'qa-fallback',
                'status': 'answered'}

    monkeypatch.setattr(rag_orchestrator, 'build_conversational_llm_answer', fake_conv)
    monkeypatch.setattr(rag_orchestrator, '_resolve_answer', fake_resolve)

    ctx = ConversationContext(stage=STAGE_START, collected={})
    out = asyncio.run(rag_orchestrator._resolve_conversational(
        question='hola', matches=[],
        ctx=ctx, history='',
        settings=_settings(),  # no cloud key
        business_name='Negocio',
        tenant_no_train=True,
    ))
    assert out['answer'].startswith('qa-fallback')


def test_resolve_conversational_llm_fails_cloud_succeeds(monkeypatch):
    from app.services import rag_orchestrator
    from app.services.conversation_flow import ConversationContext, STAGE_START

    async def fake_conv(question, matches, **kwargs):
        raise RuntimeError('ollama down')

    async def fake_cloud_conv(question, matches, **kwargs):
        return {'sufficient_context': True, 'answer': 'cloud-conv',
                'cloud_llm_used': True, 'status': 'answered'}

    monkeypatch.setattr(rag_orchestrator, 'build_conversational_llm_answer', fake_conv)
    monkeypatch.setattr(rag_orchestrator, 'build_conversational_cloud_llm_answer', fake_cloud_conv)

    ctx = ConversationContext(stage=STAGE_START, collected={})
    out = asyncio.run(rag_orchestrator._resolve_conversational(
        question='hola', matches=[],
        ctx=ctx, history='',
        settings=_settings(
            cloud_llm_provider='anthropic',
            cloud_llm_api_key='sk-x',
            cloud_llm_model='claude'),
        business_name='Negocio',
        tenant_no_train=False,  # allows cloud
    ))
    assert out['answer'] == 'cloud-conv'


def test_resolve_conversational_llm_fails_cloud_fails_falls_to_qa(monkeypatch):
    from app.services import rag_orchestrator
    from app.services.conversation_flow import ConversationContext, STAGE_START

    async def fake_conv(question, matches, **kwargs):
        raise RuntimeError('ollama down')

    async def fake_cloud_conv(question, matches, **kwargs):
        raise RuntimeError('cloud down')

    async def fake_resolve(question, matches, settings, **kwargs):
        return {'sufficient_context': True, 'answer': 'qa',
                'status': 'answered'}

    monkeypatch.setattr(rag_orchestrator, 'build_conversational_llm_answer', fake_conv)
    monkeypatch.setattr(rag_orchestrator, 'build_conversational_cloud_llm_answer', fake_cloud_conv)
    monkeypatch.setattr(rag_orchestrator, '_resolve_answer', fake_resolve)

    ctx = ConversationContext(stage=STAGE_START, collected={})
    out = asyncio.run(rag_orchestrator._resolve_conversational(
        question='hola', matches=[],
        ctx=ctx, history='',
        settings=_settings(
            cloud_llm_provider='anthropic',
            cloud_llm_api_key='sk-x',
            cloud_llm_model='claude'),
        business_name='Negocio',
        tenant_no_train=False,
    ))
    assert 'qa' in out['answer']


# ───────── _update_conversation_metadata ───────────────────────────────


def test_update_conversation_metadata_dict_meta():
    from app.services.rag_orchestrator import _update_conversation_metadata
    conv = {'id': uuid4(), 'metadata': {'existing': 'x'}}
    conn = _FakeConn()
    asyncio.run(_update_conversation_metadata(
        conn, uuid4(), conv, 'new_stage', {'foo': 'bar'},
    ))
    assert len(conn.executed) == 1


def test_update_conversation_metadata_string_meta():
    from app.services.rag_orchestrator import _update_conversation_metadata
    conv = {'id': uuid4(), 'metadata': '{"prev": 1}'}
    conn = _FakeConn()
    asyncio.run(_update_conversation_metadata(
        conn, uuid4(), conv, 'stage', {},
    ))
    assert len(conn.executed) == 1


def test_update_conversation_metadata_invalid_string_falls_back():
    from app.services.rag_orchestrator import _update_conversation_metadata
    conv = {'id': uuid4(), 'metadata': 'not json'}
    conn = _FakeConn()
    asyncio.run(_update_conversation_metadata(
        conn, uuid4(), conv, 'stage', {},
    ))
    assert len(conn.executed) == 1


# ───────── _handle_appointment_created ─────────────────────────────────


def test_handle_appointment_created_inserts_service_request(monkeypatch):
    from app.services import rag_orchestrator

    sr_id = uuid4()
    inbound_id = uuid4()
    conn = _FakeConn(
        fetchval_results=[None],  # idempotency = not yet created
        fetchrow_results=[{'id': sr_id}],
    )

    async def fake_audit(conn, **kwargs):
        return None

    monkeypatch.setattr(rag_orchestrator, 'audit', fake_audit)

    asyncio.run(rag_orchestrator._handle_appointment_created(
        conn, tenant_id=uuid4(),
        contact_id=uuid4(),
        conversation={'id': uuid4()},
        inbound_message={'id': inbound_id, 'body_text': 'hola'},
        collected={'service_type': 'massage', 'preferred_day': 'lunes',
                   'preferred_time': '10:00', 'service_name': 'Massage'},
        vertical_code='wellness',
    ))
    # insert into service_requests + insert into domain_events
    assert len(conn.executed) >= 1


def test_handle_appointment_created_skips_when_idempotent(monkeypatch):
    from app.services import rag_orchestrator

    conn = _FakeConn(fetchval_results=[uuid4()])  # already_created

    async def fake_audit(*a, **kw):
        return None

    monkeypatch.setattr(rag_orchestrator, 'audit', fake_audit)
    asyncio.run(rag_orchestrator._handle_appointment_created(
        conn, tenant_id=uuid4(),
        contact_id=uuid4(),
        conversation={'id': uuid4()},
        inbound_message={'id': uuid4(), 'body_text': 'hola'},
        collected={'service_type': 'massage'},
        vertical_code='wellness',
    ))
    # No inserts performed, since already created.
    assert len(conn.executed) == 0


def test_handle_appointment_created_uses_fallback_service_type(monkeypatch):
    from app.services import rag_orchestrator

    conn = _FakeConn(
        fetchval_results=[None],
        fetchrow_results=[{'id': uuid4()}],
    )

    async def fake_audit(*a, **kw):
        return None

    monkeypatch.setattr(rag_orchestrator, 'audit', fake_audit)

    # Collected has only "notes", no service_type or service_name.
    asyncio.run(rag_orchestrator._handle_appointment_created(
        conn, tenant_id=uuid4(),
        contact_id=uuid4(),
        conversation={'id': uuid4()},
        inbound_message={'id': uuid4(), 'body_text': 'hola'},
        collected={'notes': 'wants something'},
        vertical_code='salon',
    ))
    # At least the insert + event ran.
    assert len(conn.executed) >= 1


# ───────── _send_bot_reply ──────────────────────────────────────────────


def test_send_bot_reply_inserts_message_event_and_updates_conv(monkeypatch):
    from app.services import rag_orchestrator

    out_id = uuid4()
    conn = _FakeConn(fetchrow_results=[{'id': out_id}])

    async def fake_audit(*a, **kw):
        return None

    monkeypatch.setattr(rag_orchestrator, 'audit', fake_audit)
    monkeypatch.setattr(rag_orchestrator, 'retrieval_match_to_dict',
                        lambda m: {'doc': 'mock'})

    res = asyncio.run(rag_orchestrator._send_bot_reply(
        conn, tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4()},
        inbound_message={'id': uuid4(), 'body_text': 'q'},
        answer_text='hola',
        matches=[],
        idempotency_key='bot_reply:test',
        top_score=0.9, top_document='doc-1',
        llm_used=False, llm_model=None,
    ))
    assert res['action'] == 'bot_replied'
    assert res['outbound_message_id'] == str(out_id)


def test_send_bot_reply_with_llm_used_marks_local(monkeypatch):
    from app.services import rag_orchestrator

    out_id = uuid4()
    conn = _FakeConn(fetchrow_results=[{'id': out_id}])

    async def fake_audit(*a, **kw):
        return None

    monkeypatch.setattr(rag_orchestrator, 'audit', fake_audit)
    monkeypatch.setattr(rag_orchestrator, 'retrieval_match_to_dict',
                        lambda m: {})

    res = asyncio.run(rag_orchestrator._send_bot_reply(
        conn, tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4()},
        inbound_message={'id': uuid4(), 'body_text': 'q'},
        answer_text='hola',
        matches=[],
        idempotency_key='k',
        top_score=None, top_document=None,
        llm_used=True, llm_model='llama3',
    ))
    assert res['outbound_message_id'] == str(out_id)


def test_send_bot_reply_with_cloud_llm(monkeypatch):
    from app.services import rag_orchestrator

    out_id = uuid4()
    conn = _FakeConn(fetchrow_results=[{'id': out_id}])

    async def fake_audit(*a, **kw):
        return None

    monkeypatch.setattr(rag_orchestrator, 'audit', fake_audit)
    monkeypatch.setattr(rag_orchestrator, 'retrieval_match_to_dict',
                        lambda m: {})

    res = asyncio.run(rag_orchestrator._send_bot_reply(
        conn, tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4()},
        inbound_message={'id': uuid4(), 'body_text': 'q'},
        answer_text='hola',
        matches=[],
        idempotency_key='k',
        top_score=None, top_document=None,
        cloud_llm_used=True, llm_model='claude',
        token_usage={'cache_read_tokens': 100},
    ))
    assert res['action'] == 'bot_replied'


# ───────── _do_handoff ──────────────────────────────────────────────────


def test_do_handoff_creates_new_when_no_existing(monkeypatch):
    from app.services import rag_orchestrator

    handoff_id = uuid4()
    conn = _FakeConn(
        fetchrow_results=[
            None,  # existing_handoff lookup → none
            {'id': handoff_id},  # insert into handoffs returns
            {'id': uuid4()},  # insert into outbound message returns
        ],
        fetchval_results=[None],  # idempotency for handoff_msg
    )

    async def fake_audit(*a, **kw):
        return None

    monkeypatch.setattr(rag_orchestrator, 'audit', fake_audit)
    monkeypatch.setattr(rag_orchestrator, 'record_handoff',
                        lambda **kwargs: None)

    out = asyncio.run(rag_orchestrator._do_handoff(
        conn, tenant_id=uuid4(),
        channel_id=uuid4(),
        conversation={'id': uuid4()},
        inbound_message={'id': uuid4(), 'body_text': 'q'},
        policy={'handoff_message': ''},  # use default
        reason='cascade_exhausted',
        reason_detail='no answer',
    ))
    assert out['action'] == 'handoff'
    assert out['handoff_id'] == str(handoff_id)
    assert out['handoff_message_sent'] is True


def test_do_handoff_reuses_existing_handoff(monkeypatch):
    from app.services import rag_orchestrator

    existing_id = uuid4()
    conn = _FakeConn(
        fetchrow_results=[
            {'id': existing_id},  # existing_handoff found
            {'id': uuid4()},  # outbound message insert
        ],
        fetchval_results=[None],  # handoff_msg idempotency
    )

    async def fake_audit(*a, **kw):
        return None

    monkeypatch.setattr(rag_orchestrator, 'audit', fake_audit)
    monkeypatch.setattr(rag_orchestrator, 'record_handoff',
                        lambda **kwargs: None)

    out = asyncio.run(rag_orchestrator._do_handoff(
        conn, tenant_id=uuid4(),
        channel_id=uuid4(),
        conversation={'id': uuid4()},
        inbound_message={'id': uuid4(), 'body_text': 'q'},
        policy={'handoff_message': 'Custom handoff'},
        reason='policy',
        reason_detail='detail',
    ))
    assert out['handoff_id'] == str(existing_id)
    assert out['handoff_message_sent'] is True


def test_do_handoff_skips_message_when_already_emitted(monkeypatch):
    """When the handoff_msg idempotency key already exists, the helper does
    NOT re-insert the message."""
    from app.services import rag_orchestrator

    handoff_id = uuid4()
    conn = _FakeConn(
        fetchrow_results=[
            None,  # no existing handoff
            {'id': handoff_id},  # insert handoffs
        ],
        fetchval_results=[uuid4()],  # idempotency hit
    )

    async def fake_audit(*a, **kw):
        return None

    monkeypatch.setattr(rag_orchestrator, 'audit', fake_audit)
    monkeypatch.setattr(rag_orchestrator, 'record_handoff',
                        lambda **kwargs: None)

    out = asyncio.run(rag_orchestrator._do_handoff(
        conn, tenant_id=uuid4(),
        channel_id=uuid4(),
        conversation={'id': uuid4()},
        inbound_message={'id': uuid4(), 'body_text': 'q'},
        policy={'handoff_message': 'Custom'},
        reason='policy', reason_detail='detail',
    ))
    assert out['handoff_message_sent'] is False


# ───────── orchestrate_inbound_message — high-level skip flows ─────────


def test_orchestrate_inbound_skips_non_text_messages(monkeypatch):
    from app.services import rag_orchestrator

    conn = _FakeConn()
    out = asyncio.run(rag_orchestrator.orchestrate_inbound_message(
        conn, tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'status': 'open'},
        contact={'id': uuid4()},
        inbound_message={
            'id': uuid4(), 'body_text': '', 'message_type': 'image',
        },
    ))
    assert out == {'action': 'skipped', 'reason': 'non_text_message'}


def test_orchestrate_inbound_skips_when_status_human_active(monkeypatch):
    from app.services import rag_orchestrator

    conn = _FakeConn()
    out = asyncio.run(rag_orchestrator.orchestrate_inbound_message(
        conn, tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'status': 'human_active'},
        contact={'id': uuid4()},
        inbound_message={
            'id': uuid4(), 'body_text': 'hola', 'message_type': 'text',
        },
    ))
    assert out == {'action': 'skipped', 'reason': 'human_active'}


def test_orchestrate_inbound_skips_when_active_human_handoff(monkeypatch):
    from app.services import rag_orchestrator

    # Conversation is in 'open' status (so it passes that check), but the
    # active_human_handoff query returns a uuid → orchestrator skips.
    conn = _FakeConn(fetchval_results=[uuid4()])

    out = asyncio.run(rag_orchestrator.orchestrate_inbound_message(
        conn, tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'status': 'open'},
        contact={'id': uuid4()},
        inbound_message={
            'id': uuid4(), 'body_text': 'hola', 'message_type': 'text',
        },
    ))
    assert out == {'action': 'skipped', 'reason': 'active_human_handoff'}


def test_orchestrate_inbound_skips_whitespace_body(monkeypatch):
    from app.services import rag_orchestrator

    conn = _FakeConn()
    out = asyncio.run(rag_orchestrator.orchestrate_inbound_message(
        conn, tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'status': 'open'},
        contact={'id': uuid4()},
        inbound_message={
            'id': uuid4(), 'body_text': '    ',
            'message_type': 'text',
        },
    ))
    assert out == {'action': 'skipped', 'reason': 'non_text_message'}


def test_orchestrate_inbound_waiting_agent_no_real_handoff_resets_and_processes(monkeypatch):
    """When status='waiting_agent' but no open handoff row exists, the
    orchestrator resets the conversation to 'open' instead of skipping."""
    from app.services import rag_orchestrator

    async def fake_enforce(conn, **kwargs):
        return SimpleNamespace(handled=True, reason='opt_in_pending')

    monkeypatch.setattr(rag_orchestrator, 'enforce_inbound_consent', fake_enforce)

    conn = _FakeConn(
        fetchval_results=[
            None,  # active_human_handoff lookup
            None,  # handoff_age (no row → triggers reset branch)
        ],
        fetchrow_results=[
            None,  # tenant_settings row
        ],
    )

    out = asyncio.run(rag_orchestrator.orchestrate_inbound_message(
        conn, tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={
            'id': uuid4(),
            'status': 'waiting_agent',
            'handoff_required': True,
            'metadata': {},
        },
        contact={'id': uuid4()},
        inbound_message={
            'id': uuid4(), 'body_text': 'hola',
            'message_type': 'text',
        },
    ))
    assert out['reason'] == 'opt_in_pending'


def test_orchestrate_inbound_waiting_agent_skips_when_handoff_recent(monkeypatch):
    """When status='waiting_agent' AND there's an open handoff that's still
    fresh (< reopen_hours old), the orchestrator skips."""
    from app.services import rag_orchestrator

    # We need get_settings().bot_reopen_after_hours > 0 → typical default.
    # The query returns a small age (0.5 hours) → triggers should_skip=True.
    conn = _FakeConn(
        fetchval_results=[
            None,  # active_human_handoff (none)
            0.5,   # handoff_age_hours
        ],
    )

    out = asyncio.run(rag_orchestrator.orchestrate_inbound_message(
        conn, tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={
            'id': uuid4(),
            'status': 'waiting_agent',
            'handoff_required': True,
            'metadata': {},
        },
        contact={'id': uuid4()},
        inbound_message={
            'id': uuid4(), 'body_text': 'hola',
            'message_type': 'text',
        },
    ))
    assert out['reason'] == 'waiting_agent_handoff_pending'


def test_orchestrate_inbound_waiting_agent_reopen_after_timeout(monkeypatch):
    """When the handoff is older than reopen_after_hours, the orchestrator
    resets the conversation back to 'waiting_user' and processes."""
    from app.services import rag_orchestrator

    async def fake_enforce(conn, **kwargs):
        return SimpleNamespace(handled=True, reason='opt_in_pending')

    monkeypatch.setattr(rag_orchestrator, 'enforce_inbound_consent', fake_enforce)

    # Patch get_settings to return a low reopen_after_hours so 1000 > value
    real_get = rag_orchestrator.get_settings

    class _GS:
        def __init__(self):
            inner = real_get()
            # Copy attrs we use
            for attr in ('bot_reopen_after_hours', 'answer_engine'):
                if hasattr(inner, attr):
                    setattr(self, attr, getattr(inner, attr))
            self.bot_reopen_after_hours = 24  # finite

    monkeypatch.setattr(rag_orchestrator, 'get_settings', _GS)

    conn = _FakeConn(
        fetchval_results=[
            None,    # active_human_handoff
            1000.0,  # handoff_age_hours >> 24 → reset
        ],
        fetchrow_results=[None],  # tenant_settings → None
    )

    out = asyncio.run(rag_orchestrator.orchestrate_inbound_message(
        conn, tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={
            'id': uuid4(),
            'status': 'waiting_agent',
            'handoff_required': True,
            'metadata': {},
        },
        contact={'id': uuid4()},
        inbound_message={
            'id': uuid4(), 'body_text': 'hola',
            'message_type': 'text',
        },
    ))
    # Reset path → consent gate gets to run → opt_in_pending
    assert out['reason'] == 'opt_in_pending'


def test_orchestrate_inbound_opt_out_intent_skips(monkeypatch):
    """When the intent classifier returns INTENT_OPT_OUT, we update the
    contact and skip with reason='opt_out_registered'."""
    from app.services import rag_orchestrator
    from app.services.intent_classifier import INTENT_OPT_OUT

    async def fake_enforce(conn, **kwargs):
        return None  # consent decision not handled

    async def fake_classify(body, **kwargs):
        return SimpleNamespace(intent=INTENT_OPT_OUT, confidence=0.9,
                               resolved_by='keyword')

    async def fake_record_opt(conn, **kwargs):
        return None

    monkeypatch.setattr(rag_orchestrator, 'enforce_inbound_consent', fake_enforce)
    monkeypatch.setattr(rag_orchestrator, 'classify_intent', fake_classify)
    monkeypatch.setattr(rag_orchestrator, 'record_opt_out_by_keyword', fake_record_opt)

    conn = _FakeConn(
        fetchval_results=[None],  # active_human_handoff
        fetchrow_results=[
            # tenant_settings row
            {
                'escalation_policy': {},
                'bot_personality': {},
                'no_train': True,
                'pii_policy': None,
                'business_name': 'Biz',
                'vertical_code': 'general',
                'timezone': 'America/Bogota',
            },
            # No further fetchrow needed before opt-out short-circuit.
        ],
    )

    out = asyncio.run(rag_orchestrator.orchestrate_inbound_message(
        conn, tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'status': 'open', 'metadata': {}},
        contact={'id': uuid4()},
        inbound_message={
            'id': uuid4(), 'body_text': 'STOP',
            'message_type': 'text',
        },
    ))
    assert out['reason'] == 'opt_out_registered'


def test_orchestrate_inbound_already_processed_after_policy_skips(monkeypatch):
    """When the inbound message has already been processed (idempotency key
    exists), we skip with 'already_processed'."""
    from app.services import rag_orchestrator
    from app.services.intent_classifier import INTENT_GREETING

    async def fake_enforce(conn, **kwargs):
        return None

    async def fake_classify(body, **kwargs):
        return SimpleNamespace(intent=INTENT_GREETING, confidence=0.9,
                               resolved_by='keyword')

    def fake_eval(**kwargs):
        return SimpleNamespace(action='allow', reason='ok', risk_level='low')

    monkeypatch.setattr(rag_orchestrator, 'enforce_inbound_consent', fake_enforce)
    monkeypatch.setattr(rag_orchestrator, 'classify_intent', fake_classify)
    monkeypatch.setattr(rag_orchestrator, 'evaluate_policy', fake_eval)

    conn = _FakeConn(
        fetchval_results=[
            None,  # active_human_handoff
            None,  # last_release_at
            0,     # bot_turn_count
            uuid4(),  # idempotency_key → already processed
        ],
        fetch_results=[
            [],  # recent_sc_rows
        ],
        fetchrow_results=[
            {
                'escalation_policy': {},
                'bot_personality': {},
                'no_train': True,
                'pii_policy': None,
                'business_name': 'Biz',
                'vertical_code': 'general',
                'timezone': 'America/Bogota',
            },
        ],
    )

    out = asyncio.run(rag_orchestrator.orchestrate_inbound_message(
        conn, tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'status': 'open', 'metadata': {}},
        contact={'id': uuid4()},
        inbound_message={
            'id': uuid4(), 'body_text': 'hola',
            'message_type': 'text',
        },
    ))
    assert out['reason'] == 'already_processed'


def test_orchestrate_inbound_require_handoff_routes_via_policy(monkeypatch):
    """When policy_result.action == 'require_handoff', we trigger _do_handoff."""
    from app.services import rag_orchestrator
    from app.services.intent_classifier import INTENT_GREETING

    async def fake_enforce(conn, **kwargs):
        return None

    async def fake_classify(body, **kwargs):
        return SimpleNamespace(intent=INTENT_GREETING, confidence=0.9,
                               resolved_by='keyword')

    def fake_eval(**kwargs):
        return SimpleNamespace(action='require_handoff', reason='policy_rule',
                               risk_level='medium')

    async def fake_handoff(conn, **kwargs):
        return {'action': 'handoff', 'handoff_id': str(uuid4()),
                'reason': 'policy_rule'}

    monkeypatch.setattr(rag_orchestrator, 'enforce_inbound_consent', fake_enforce)
    monkeypatch.setattr(rag_orchestrator, 'classify_intent', fake_classify)
    monkeypatch.setattr(rag_orchestrator, 'evaluate_policy', fake_eval)
    monkeypatch.setattr(rag_orchestrator, '_do_handoff', fake_handoff)

    conn = _FakeConn(
        fetchval_results=[
            None,  # active_human_handoff
            None,  # last_release_at
            0,     # bot_turn_count
        ],
        fetch_results=[[]],  # recent_sc_rows
        fetchrow_results=[
            {
                'escalation_policy': {},
                'bot_personality': {},
                'no_train': True,
                'pii_policy': None,
                'business_name': 'Biz',
                'vertical_code': 'general',
                'timezone': 'America/Bogota',
            },
        ],
    )

    out = asyncio.run(rag_orchestrator.orchestrate_inbound_message(
        conn, tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'status': 'open', 'metadata': {}},
        contact={'id': uuid4()},
        inbound_message={
            'id': uuid4(), 'body_text': 'mala atención',
            'message_type': 'text',
        },
    ))
    assert out['action'] == 'handoff'


def test_orchestrate_inbound_complaint_alert_enqueued(monkeypatch):
    """When the policy fires `intent_complaint_or_risk`, we also enqueue an
    operator alert (best-effort) alongside the handoff."""
    from app.services import rag_orchestrator
    from app.services.intent_classifier import INTENT_GREETING

    async def fake_enforce(conn, **kwargs):
        return None

    async def fake_classify(body, **kwargs):
        return SimpleNamespace(intent=INTENT_GREETING, confidence=0.9,
                               resolved_by='keyword')

    def fake_eval(**kwargs):
        return SimpleNamespace(action='require_handoff',
                               reason='intent_complaint_or_risk',
                               risk_level='high')

    enqueue_calls = []

    async def fake_enqueue(conn, **kwargs):
        enqueue_calls.append(kwargs)

    async def fake_handoff(conn, **kwargs):
        return {'action': 'handoff', 'handoff_id': str(uuid4())}

    monkeypatch.setattr(rag_orchestrator, 'enforce_inbound_consent', fake_enforce)
    monkeypatch.setattr(rag_orchestrator, 'classify_intent', fake_classify)
    monkeypatch.setattr(rag_orchestrator, 'evaluate_policy', fake_eval)
    monkeypatch.setattr(rag_orchestrator, 'enqueue_operator_alert', fake_enqueue)
    monkeypatch.setattr(rag_orchestrator, '_do_handoff', fake_handoff)

    conn = _FakeConn(
        fetchval_results=[None, None, 0],
        fetch_results=[[]],
        fetchrow_results=[
            {
                'escalation_policy': {},
                'bot_personality': {},
                'no_train': True,
                'pii_policy': None,
                'business_name': 'Biz',
                'vertical_code': 'general',
                'timezone': 'America/Bogota',
            },
        ],
    )

    out = asyncio.run(rag_orchestrator.orchestrate_inbound_message(
        conn, tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'status': 'open', 'metadata': {}},
        contact={'id': uuid4()},
        inbound_message={
            'id': uuid4(), 'body_text': 'esto es pésimo',
            'message_type': 'text',
        },
    ))
    assert out['action'] == 'handoff'
    assert len(enqueue_calls) == 1


def test_orchestrate_inbound_skips_when_active_human_handoff_with_assigned(monkeypatch):
    """The active_human_handoff branch — when a handoff row with
    status='accepted' AND assigned_to is not null exists."""
    from app.services import rag_orchestrator

    conn = _FakeConn(fetchval_results=[uuid4()])  # active handoff hit

    out = asyncio.run(rag_orchestrator.orchestrate_inbound_message(
        conn, tenant_id=uuid4(),
        channel_id=uuid4(), channel_account_mode='mock',
        conversation={'id': uuid4(), 'status': 'open', 'metadata': {}},
        contact={'id': uuid4()},
        inbound_message={
            'id': uuid4(), 'body_text': 'hola',
            'message_type': 'text',
        },
    ))
    assert out['reason'] == 'active_human_handoff'
