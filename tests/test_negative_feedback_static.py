"""Static tests for TASK-0045 — Auto-escalate negative feedback.

Verifies:
- Helper booleans / settings parsing.
- Negative ratings (≤2) trigger: tag upsert + assignment, conversation handoff,
  handoff row creation with ``reason='negative_feedback'``, empathic reply
  queued, domain event ``feedback.negative_received`` emitted.
- Positive ratings (≥3) do NOT escalate.
- The orchestrator forwards conversation/channel info to ``maybe_record_feedback``.
- The new endpoint ``/conversations/complaints`` is registered with
  ``handoff_reason='negative_feedback'`` and lists the right rows.
- Operations Desk surfaces a complaint filter tab with rating + comment, and
  the core API exports the matching helper.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.services import feedback_flow
from app.services.feedback_flow import (
    DEFAULT_NEGATIVE_FEEDBACK_REPLY,
    NEGATIVE_FEEDBACK_HANDOFF_REASON,
    NEGATIVE_FEEDBACK_TAG_NAME,
    NEGATIVE_FEEDBACK_THRESHOLD,
    is_negative_rating,
    maybe_record_feedback,
    negative_feedback_reply,
    parse_rating,
)


FEEDBACK_FLOW = Path('app/services/feedback_flow.py')
ROUTES = Path('app/api/v1/routes.py')
ORCHESTRATOR = Path('app/services/rag_orchestrator.py')
CORE_API = Path('admin-panel/src/services/coreApi.js')
OPERATIONS_DESK = Path('admin-panel/src/components/modules/operations/OperationsDesk.jsx')


# ───── Constants and helpers ───────────────────────────────────────────────


def test_constants_match_spec():
    assert NEGATIVE_FEEDBACK_THRESHOLD == 2
    assert NEGATIVE_FEEDBACK_TAG_NAME == 'Atención prioritaria'
    assert NEGATIVE_FEEDBACK_HANDOFF_REASON == 'negative_feedback'
    assert 'Un agente' in DEFAULT_NEGATIVE_FEEDBACK_REPLY


def test_is_negative_rating_threshold():
    assert is_negative_rating(1) is True
    assert is_negative_rating(2) is True
    assert is_negative_rating(3) is False
    assert is_negative_rating(5) is False
    assert is_negative_rating(None) is False


def test_negative_feedback_reply_uses_setting_when_present():
    custom = '¡Gracias por avisarnos! Nuestro gerente se comunicará contigo.'
    assert negative_feedback_reply({'negative_feedback_reply': custom}) == custom


def test_negative_feedback_reply_falls_back_to_default():
    assert negative_feedback_reply(None) == DEFAULT_NEGATIVE_FEEDBACK_REPLY
    assert negative_feedback_reply({}) == DEFAULT_NEGATIVE_FEEDBACK_REPLY
    assert negative_feedback_reply({'negative_feedback_reply': ''}) == DEFAULT_NEGATIVE_FEEDBACK_REPLY
    # JSON-encoded jsonb settings.
    raw = json.dumps({'negative_feedback_reply': 'Hola'})
    assert negative_feedback_reply(raw) == 'Hola'
    # Invalid payload
    assert negative_feedback_reply('not json') == DEFAULT_NEGATIVE_FEEDBACK_REPLY


def test_parse_rating_handles_extra_decorations():
    assert parse_rating('5') == 5
    assert parse_rating('2 estrellas') == 2
    assert parse_rating('1 ⭐') == 1
    assert parse_rating('no me gustó') is None


# ───── Module source: shape ────────────────────────────────────────────────


def test_feedback_flow_source_handles_escalation_path():
    source = FEEDBACK_FLOW.read_text()
    assert '_escalate_negative_feedback' in source
    assert "reason='open'" in source or "'open'" in source
    assert "'feedback.negative_received'" in source
    assert "'feedback_negative_escalated'" in source
    assert 'contact_tag_assignments' in source
    # The empathic reply path must be conditional on conversation+channel.
    assert 'channel_id is not None' in source


def test_orchestrator_threads_conversation_and_channel_into_feedback():
    source = ORCHESTRATOR.read_text()
    assert 'conversation=conversation' in source
    assert 'channel_account_mode=channel_account_mode' in source
    # Both feedback and confirmation handlers now receive conversation context.
    assert source.count("conversation=conversation,") >= 2


# ───── API + UI surface ────────────────────────────────────────────────────


def test_complaints_endpoint_is_registered():
    source = ROUTES.read_text()
    assert "@tenant_ops_router.get('/conversations/complaints')" in source
    assert "h.reason = 'negative_feedback'" in source
    assert 'appointment_feedback' in source
    assert "h.status in ('open', 'accepted')" in source


def test_core_api_exposes_complaints_helper():
    source = CORE_API.read_text()
    assert 'export function listComplaintConversations' in source
    assert '/conversations/complaints' in source


def test_operations_desk_renders_complaints_filter_tab():
    source = OPERATIONS_DESK.read_text()
    assert "inboxFilter === 'complaints'" in source
    assert 'Quejas' in source
    assert 'data-complaint="negative_feedback"' in source
    assert 'feedback_rating' in source
    assert 'feedback_comment' in source
    assert 'listComplaintConversations' in source


# ───── Functional: FakeConn driven scenarios ───────────────────────────────


class FakeConn:
    def __init__(
        self,
        *,
        appointment=None,
        notification_settings=None,
        existing_tag_id=None,
    ):
        self.appointment = appointment
        self.notification_settings = notification_settings
        self.existing_tag_id = existing_tag_id
        self.inserted_messages = []
        self.inserted_events = []
        self.executed = []
        self.tag_upserts = 0
        self.tag_assignments = []
        self.handoff_inserts = []
        self.conversation_updates = []
        self.feedback_rows = []
        self.appointment_feedback_id = None

    async def fetch(self, query, *args):
        return []

    async def fetchrow(self, query, *args):
        if 'from app.appointments' in query and 'contact_id=$2' in query:
            return self.appointment
        if 'insert into app.appointment_feedback' in query:
            fid = uuid4()
            self.appointment_feedback_id = fid
            self.feedback_rows.append({
                'id': fid,
                'tenant_id': args[0],
                'appointment_id': args[1],
                'contact_id': args[2],
                'rating': args[3],
                'comment': args[4],
            })
            return {'id': fid}
        if 'from app.handoffs' in query and "status='open'" in query:
            return None
        if 'insert into app.messages' in query:
            mid = uuid4()
            payload = json.loads(args[3]) if len(args) >= 4 else {}
            self.inserted_messages.append({
                'id': mid,
                'body_text': args[2],
                'payload': payload,
            })
            return {'id': mid}
        if 'insert into app.audit_logs' in query:
            return {'id': 1}
        return None

    async def fetchval(self, query, *args):
        if 'select id from app.contact_tags' in query and 'name=$2' in query:
            return self.existing_tag_id
        if 'select notification_settings from app.tenant_settings' in query:
            return self.notification_settings
        if 'select id from app.domain_events' in query and 'idempotency_key' in query:
            return None
        return None

    async def execute(self, query, *args):
        if 'insert into app.contact_tags' in query and 'on conflict' in query:
            self.tag_upserts += 1
            if self.existing_tag_id is None:
                self.existing_tag_id = uuid4()
        elif 'insert into app.contact_tag_assignments' in query:
            self.tag_assignments.append({
                'tenant_id': args[0],
                'contact_id': args[1],
                'tag_id': args[2],
            })
        elif 'update app.conversations' in query and 'handoff_required=true' in query:
            self.conversation_updates.append({'query': query, 'args': args})
        elif 'insert into app.handoffs' in query:
            self.handoff_inserts.append({
                'tenant_id': args[0],
                'conversation_id': args[1],
                'reason': args[2],
            })
        elif 'insert into app.domain_events' in query:
            self.inserted_events.append({
                'idempotency_key': args[2],
                'payload': json.loads(args[3]) if len(args) >= 4 else {},
                'event_name': 'feedback.negative_received' if 'feedback.negative_received' in args[2] else 'other',
            })
        else:
            self.executed.append((query, args))
        return None


def _appointment():
    return {
        'id': uuid4(),
        'starts_at': None,
        'ends_at': None,
        'status': 'completed',
        'confirmation_status': 'confirmed',
    }


def _conversation():
    return {'id': uuid4(), 'metadata': {}}


def _inbound(body):
    return {
        'id': uuid4(),
        'body_text': body,
        'payload': {},
    }


def test_rating_two_triggers_full_escalation():
    appointment = _appointment()
    conv = _conversation()
    conn = FakeConn(appointment=appointment)
    result = asyncio.run(
        maybe_record_feedback(
            conn,
            tenant_id=uuid4(),
            contact_id=uuid4(),
            inbound_message=_inbound('2'),
            conversation=conv,
            channel_id=uuid4(),
            channel_account_mode='mock',
        )
    )
    assert result['action'] == 'feedback_negative_escalated'
    assert result['rating'] == 2
    trace = result['negative_escalation']
    assert trace['tag_assigned'] is True
    assert trace['handoff_marked'] is True
    assert trace['reply_sent'] is True
    assert trace['event_emitted'] is True

    # Side-effects on the fake DB:
    assert conn.tag_upserts == 1
    assert conn.tag_assignments
    assert conn.conversation_updates
    assert conn.handoff_inserts and conn.handoff_inserts[0]['reason'] == 'negative_feedback'
    assert any('feedback.negative_received' in event['idempotency_key'] for event in conn.inserted_events)
    # The empathic message went out:
    assert conn.inserted_messages
    assert DEFAULT_NEGATIVE_FEEDBACK_REPLY in conn.inserted_messages[0]['body_text']


def test_rating_one_uses_custom_reply_when_configured():
    appointment = _appointment()
    custom_reply = '¡Lo sentimos! Nuestro gerente te llamará en 1 hora.'
    conn = FakeConn(
        appointment=appointment,
        notification_settings={'negative_feedback_reply': custom_reply},
    )
    result = asyncio.run(
        maybe_record_feedback(
            conn,
            tenant_id=uuid4(),
            contact_id=uuid4(),
            inbound_message=_inbound('1'),
            conversation=_conversation(),
            channel_id=uuid4(),
            channel_account_mode='mock',
        )
    )
    assert result['action'] == 'feedback_negative_escalated'
    assert conn.inserted_messages[0]['body_text'] == custom_reply


def test_rating_four_does_not_escalate():
    appointment = _appointment()
    conn = FakeConn(appointment=appointment)
    result = asyncio.run(
        maybe_record_feedback(
            conn,
            tenant_id=uuid4(),
            contact_id=uuid4(),
            inbound_message=_inbound('4'),
            conversation=_conversation(),
            channel_id=uuid4(),
            channel_account_mode='mock',
        )
    )
    assert result['action'] == 'feedback_recorded'
    assert 'negative_escalation' not in result
    assert conn.tag_upserts == 0
    assert not conn.handoff_inserts
    assert not conn.inserted_messages


def test_rating_five_does_not_escalate_even_with_conversation():
    appointment = _appointment()
    conn = FakeConn(appointment=appointment)
    result = asyncio.run(
        maybe_record_feedback(
            conn,
            tenant_id=uuid4(),
            contact_id=uuid4(),
            inbound_message=_inbound('5'),
            conversation=_conversation(),
            channel_id=uuid4(),
            channel_account_mode='mock',
        )
    )
    assert result['action'] == 'feedback_recorded'
    assert not conn.inserted_events
    assert not conn.conversation_updates


def test_negative_rating_without_conversation_still_emits_event():
    """When the caller doesn't pass conversation/channel (e.g. backfill), the
    tag is still applied and the domain event still fires; only the empathic
    reply is skipped."""
    appointment = _appointment()
    conn = FakeConn(appointment=appointment)
    result = asyncio.run(
        maybe_record_feedback(
            conn,
            tenant_id=uuid4(),
            contact_id=uuid4(),
            inbound_message=_inbound('2'),
        )
    )
    assert result['action'] == 'feedback_negative_escalated'
    trace = result['negative_escalation']
    assert trace['reply_sent'] is False
    assert trace['handoff_marked'] is False
    assert trace['tag_assigned'] is True
    assert trace['event_emitted'] is True
    assert conn.inserted_messages == []
    assert any('feedback.negative_received' in e['idempotency_key'] for e in conn.inserted_events)


def test_no_appointment_returns_none():
    conn = FakeConn(appointment=None)
    result = asyncio.run(
        maybe_record_feedback(
            conn,
            tenant_id=uuid4(),
            contact_id=uuid4(),
            inbound_message=_inbound('1'),
            conversation=_conversation(),
            channel_id=uuid4(),
            channel_account_mode='mock',
        )
    )
    assert result is None


def test_non_rating_message_returns_none():
    conn = FakeConn(appointment=_appointment())
    result = asyncio.run(
        maybe_record_feedback(
            conn,
            tenant_id=uuid4(),
            contact_id=uuid4(),
            inbound_message=_inbound('hola'),
            conversation=_conversation(),
            channel_id=uuid4(),
            channel_account_mode='mock',
        )
    )
    assert result is None
    assert not conn.feedback_rows


def test_tag_creation_is_idempotent_when_already_present():
    """If the tag already exists for the tenant, the upsert is a no-op and we
    use the existing id."""
    appointment = _appointment()
    existing_id = uuid4()
    conn = FakeConn(appointment=appointment, existing_tag_id=existing_id)
    result = asyncio.run(
        maybe_record_feedback(
            conn,
            tenant_id=uuid4(),
            contact_id=uuid4(),
            inbound_message=_inbound('2'),
            conversation=_conversation(),
            channel_id=uuid4(),
            channel_account_mode='mock',
        )
    )
    assert result['action'] == 'feedback_negative_escalated'
    # The upsert SQL was emitted exactly once (the on-conflict path).
    assert conn.tag_upserts == 1
    assert conn.tag_assignments[0]['tag_id'] == existing_id
