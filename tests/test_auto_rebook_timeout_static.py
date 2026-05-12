"""Static tests for TASK-0056 — Timeout & escalation for silent auto-rebook.

Verifies:
- ``auto_rebook_timeout_minutes`` parses notification settings and clamps the
  value into the documented [10, 240] window with a default of 90.
- ``start_auto_rebook_flow`` schedules an ``auto_rebook_timeout`` reminder_job
  pointing at the conversation when slots are offered.
- Any inbound during the auto-rebook window cancels the pending timeout job
  before the reply is processed (no race with the scheduler).
- ``execute_auto_rebook_timeout`` is a no-op when the conversation has moved
  past the rebook step (idempotent guard) or the customer already replied.
- ``execute_auto_rebook_timeout`` cancels the appointment, escalates the
  conversation, and tags the contact with ``Necesita seguimiento``.
- The scheduler dispatches ``kind='auto_rebook_timeout'`` jobs without
  requiring a WhatsApp template.
- The schema enforces at most one active timeout per conversation.
- The TenantSetupWizard exposes the timeout input in the Notificaciones tab.
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app.services import appointment_self_service
from app.services.appointment_self_service import (
    AUTO_REBOOK_TIMEOUT_KIND,
    AUTO_REBOOK_TIMEOUT_REASON,
    DEFAULT_AUTO_REBOOK_TIMEOUT_MINUTES,
    FLOW_RESCHEDULE,
    FOLLOWUP_TAG_NAME,
    MAX_AUTO_REBOOK_TIMEOUT_MINUTES,
    MIN_AUTO_REBOOK_TIMEOUT_MINUTES,
    STEP_AWAITING_RESCHEDULE_SLOT,
    STEP_COMPLETED,
    auto_rebook_timeout_minutes,
    execute_auto_rebook_timeout,
    start_auto_rebook_flow,
)


SCHEMA_SQL = Path('infra/postgres/01-schema.sql')
SCHEDULER = Path('app/workers/scheduler.py')
SELF_SERVICE = Path('app/services/appointment_self_service.py')
TENANT_WIZARD = Path('admin-panel/src/components/modules/tenantSetup/TenantSetupWizard.jsx')


# ───── Configuration helpers ────────────────────────────────────────────────


def test_auto_rebook_timeout_default_when_setting_missing():
    assert auto_rebook_timeout_minutes({}) == DEFAULT_AUTO_REBOOK_TIMEOUT_MINUTES
    assert auto_rebook_timeout_minutes(None) == DEFAULT_AUTO_REBOOK_TIMEOUT_MINUTES
    assert auto_rebook_timeout_minutes('not json') == DEFAULT_AUTO_REBOOK_TIMEOUT_MINUTES


def test_auto_rebook_timeout_clamps_to_documented_window():
    # Below floor and above ceiling get clamped.
    assert auto_rebook_timeout_minutes({'auto_rebook_timeout_minutes': 1}) == \
        MIN_AUTO_REBOOK_TIMEOUT_MINUTES
    assert auto_rebook_timeout_minutes({'auto_rebook_timeout_minutes': 9999}) == \
        MAX_AUTO_REBOOK_TIMEOUT_MINUTES
    # In-range values are honoured.
    assert auto_rebook_timeout_minutes({'auto_rebook_timeout_minutes': 45}) == 45
    # JSON-encoded strings are accepted (same as other notification settings).
    raw = json.dumps({'auto_rebook_timeout_minutes': 120})
    assert auto_rebook_timeout_minutes(raw) == 120


# ───── Schema / file-level surfaces ─────────────────────────────────────────


def test_schema_has_unique_index_for_auto_rebook_timeout():
    text = SCHEMA_SQL.read_text()
    assert 'ux_reminder_jobs_auto_rebook_timeout' in text
    assert "(payload->>'kind') = 'auto_rebook_timeout'" in text
    assert "target_type = 'conversation'" in text


def test_scheduler_dispatches_auto_rebook_timeout_kind():
    text = SCHEDULER.read_text()
    # ``kind`` payload key is recognised and routed without the template gate.
    assert '_extract_kind' in text
    assert "kind == 'auto_rebook_timeout'" in text
    assert '_dispatch_auto_rebook_timeout' in text
    assert 'execute_auto_rebook_timeout' in text


def test_self_service_module_exposes_timeout_helpers():
    text = SELF_SERVICE.read_text()
    assert 'def auto_rebook_timeout_minutes(' in text
    assert 'async def _schedule_auto_rebook_timeout(' in text
    assert 'async def _cancel_auto_rebook_timeout(' in text
    assert 'async def execute_auto_rebook_timeout(' in text
    # The mid-flow guard cancels the pending timeout before processing the
    # inbound — keeps the scheduler from racing the reply.
    assert "if state.get('source') == 'auto_rebook':" in text


def test_tenant_wizard_exposes_timeout_input():
    text = TENANT_WIZARD.read_text()
    assert 'auto_rebook_timeout_minutes' in text
    assert 'Tiempo máximo del auto-rebook' in text
    # The min/max attributes match the documented window.
    assert 'min="10"' in text
    assert 'max="240"' in text


# ───── Functional: FakeConn driven scenarios ────────────────────────────────


class FakeConn:
    """Lightweight asyncpg-like double for the auto-rebook timeout flow."""

    def __init__(
        self,
        *,
        appointment=None,
        resource=None,
        notification_settings=None,
        conversation_row=None,
        rebook_started_at=None,
        has_recent_inbound=False,
    ):
        self.appointment = appointment
        self.resource = resource
        self.notification_settings = notification_settings
        self.conversation_row = conversation_row
        self.rebook_started_at = rebook_started_at
        self.has_recent_inbound = has_recent_inbound

        self.inserted_messages: list[dict] = []
        self.inserted_events: list[dict] = []
        self.audit_actions: list[dict] = []
        self.appointment_updates: list[dict] = []
        self.metadata_updates: list[dict] = []
        self.reminder_inserts: list[dict] = []
        self.reminder_cancels: list[dict] = []
        self.handoff_inserts: list[dict] = []
        self.tag_inserts: list[dict] = []
        self.tag_assignments: list[dict] = []
        self._idempotency_seen: set[str] = set()
        self.transactions = 0
        self.should_conflict = False

    def transaction(self):
        outer = self

        class _Ctx:
            async def __aenter__(self_inner):
                outer.transactions += 1
                if outer.should_conflict:
                    raise RuntimeError('conflict')
                return None

            async def __aexit__(self_inner, *exc):
                return False

        return _Ctx()

    async def fetch(self, query, *args):
        if 'update app.reminder_jobs' in query and "status='cancelled'" in query:
            self.reminder_cancels.append({'args': args, 'query': query})
            return [{'id': uuid4()}]
        if 'update app.appointments' in query and 'returning id' in query:
            return []
        if 'update app.reminder_jobs' in query and "set status='processing'" in query:
            return []
        return []

    async def fetchrow(self, query, *args):
        if 'from app.appointments' in query and 'and id=$2' in query:
            return self.appointment
        if 'from app.appointments' in query and 'starts_at >= now()' in query:
            return self.appointment
        if 'from app.appointments' in query and 'contact_id=$2' in query:
            return self.appointment
        if 'from app.resources' in query and 'and id=$2' in query:
            return self.resource
        if 'from app.tenant_settings' in query and 'escalation_policy' in query:
            return {'escalation_policy': {}}
        if 'insert into app.reminder_jobs' in query:
            mid = uuid4()
            self.reminder_inserts.append({
                'id': mid,
                'tenant_id': args[0],
                'target_type': 'conversation',
                'target_id': args[1],
                'channel_id': args[2],
                'template_name': args[3],
                'payload': json.loads(args[4]) if isinstance(args[4], str) else args[4],
                'minutes': args[5],
            })
            return {'id': mid}
        if 'from app.conversations' in query and 'and id=$2' in query:
            return self.conversation_row
        if 'from app.handoffs' in query and "status='open'" in query:
            return None
        if 'insert into app.handoffs' in query:
            handoff_id = uuid4()
            self.handoff_inserts.append({
                'id': handoff_id,
                'tenant_id': args[0],
                'conversation_id': args[1],
                'reason': args[2],
            })
            return {'id': handoff_id}
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
        if 'select id from app.domain_events' in query and 'idempotency_key' in query:
            return 1 if args[1] in self._idempotency_seen else None
        if (
            'from app.domain_events' in query
            and "event_name='self_service.handled'" in query
            and 'select max(created_at)' in query
        ):
            return self.rebook_started_at
        if (
            'from app.messages' in query
            and "direction='inbound'" in query
            and 'select 1' in query
        ):
            return 1 if self.has_recent_inbound else None
        if 'select notification_settings from app.tenant_settings' in query:
            return self.notification_settings
        if 'from app.contact_tags' in query and 'name=$2' in query:
            return getattr(self, '_followup_tag_id', None)
        return None

    async def execute(self, query, *args):
        if 'insert into app.domain_events' in query:
            self._idempotency_seen.add(args[2])
            self.inserted_events.append({
                'idempotency_key': args[2],
                'payload': json.loads(args[3]) if len(args) >= 4 else {},
            })
        elif 'insert into app.audit_logs' in query:
            self.audit_actions.append({'action': args[3] if len(args) > 3 else None})
        elif 'update app.appointments' in query:
            self.appointment_updates.append({'query': query, 'args': args})
            if "set status='cancelled'" in query and self.appointment is not None:
                self.appointment['status'] = 'cancelled'
        elif 'update app.conversations' in query:
            if args and isinstance(args[0], str):
                try:
                    self.metadata_updates.append(json.loads(args[0]))
                except Exception:
                    pass
        elif 'insert into app.contact_tags' in query:
            self._followup_tag_id = uuid4()
            self.tag_inserts.append({'name': args[1]})
        elif 'insert into app.contact_tag_assignments' in query:
            self.tag_assignments.append({
                'tenant_id': args[0],
                'contact_id': args[1],
                'tag_id': args[2],
            })
        elif 'update app.reminder_jobs' in query and "status='cancelled'" in query:
            # cancel_appointment_reminder_jobs uses fetch; this path covers any
            # auxiliary scheduler updates.
            self.reminder_cancels.append({'args': args, 'query': query})
        return None


def _future_appointment(hours_ahead=24):
    starts = datetime.now(UTC) + timedelta(hours=hours_ahead)
    return {
        'id': uuid4(),
        'contact_id': uuid4(),
        'resource_id': uuid4(),
        'service_id': uuid4(),
        'service_code': 'consulta',
        'starts_at': starts,
        'ends_at': starts + timedelta(minutes=60),
        'status': 'scheduled',
        'payment_status': 'not_required',
        'confirmation_status': 'pending',
    }


def _resource_with_open_hours(resource_id):
    weekday = (datetime.now(UTC) + timedelta(days=1)).weekday()
    weekday_key = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')[weekday]
    return {
        'id': resource_id,
        'name': 'Profesional',
        'code': 'p1',
        'capabilities': {'working_hours': {weekday_key: [{'start': '09:00', 'end': '13:00'}]}},
    }


def _conversation(metadata=None):
    return {'id': uuid4(), 'metadata': metadata or {}}


def _inbound(body=None, interactive_id=None):
    return {
        'id': uuid4(),
        'body_text': body,
        'payload': {'interactive_id': interactive_id} if interactive_id else {},
    }


def test_start_auto_rebook_flow_schedules_timeout_job():
    appointment = _future_appointment(hours_ahead=72)
    conn = FakeConn(
        appointment=appointment,
        resource=_resource_with_open_hours(appointment['resource_id']),
        notification_settings={'auto_rebook_timeout_minutes': 60},
    )
    result = asyncio.run(
        start_auto_rebook_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=_conversation(),
            appointment=appointment,
            inbound_message=_inbound(body='no'),
        )
    )
    assert result['action'] == 'self_service_step_sent'
    assert result['timeout_minutes'] == 60
    # Exactly one reminder_job persisted, targetting the conversation with the
    # right payload shape so the scheduler can route it.
    assert len(conn.reminder_inserts) == 1
    job = conn.reminder_inserts[0]
    assert job['template_name'] == AUTO_REBOOK_TIMEOUT_KIND
    assert job['minutes'] == 60
    assert job['payload']['kind'] == AUTO_REBOOK_TIMEOUT_KIND
    assert job['payload']['source'] == 'auto_rebook'
    assert job['payload']['appointment_id'] == str(appointment['id'])
    # The handled event records the timeout metadata so it can be audited.
    handled_event = next(
        e for e in conn.inserted_events
        if e['payload'].get('source') == 'auto_rebook'
    )
    assert handled_event['payload']['timeout_minutes'] == 60


def test_inbound_during_auto_rebook_cancels_pending_timeout():
    """The mid-flow guard cancels the pending timeout before processing the
    reply so the scheduler can't race the customer's response."""
    appointment = _future_appointment(hours_ahead=72)
    state = {
        'flow': FLOW_RESCHEDULE,
        'step': STEP_AWAITING_RESCHEDULE_SLOT,
        'appointment_id': str(appointment['id']),
        'offered_slots': [
            {
                'date': (datetime.now(UTC) + timedelta(days=1)).date().isoformat(),
                'start_time': '09:00',
            }
        ],
        'source': 'auto_rebook',
    }
    conn = FakeConn(
        appointment=appointment,
        resource=_resource_with_open_hours(appointment['resource_id']),
    )
    asyncio.run(
        appointment_self_service.maybe_run_self_service_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=_conversation({'self_service': state}),
            contact={'id': appointment['contact_id']},
            inbound_message=_inbound(body='dame mañana'),
            intent='greeting',
        )
    )
    # _cancel_auto_rebook_timeout uses ``update ... returning id`` so the cancel
    # path hits ``conn.fetch``; verify a cancel was attempted.
    assert conn.reminder_cancels, 'expected the pending timeout to be cancelled'
    cancel = conn.reminder_cancels[0]
    assert AUTO_REBOOK_TIMEOUT_KIND in cancel['args']


def test_execute_auto_rebook_timeout_skips_when_state_completed():
    """If the conversation already moved past the rebook step (e.g. the
    customer rescheduled and the scheduler is just catching up), the timeout
    must be a no-op."""
    appointment = _future_appointment(hours_ahead=72)
    conv_id = uuid4()
    conversation_row = {
        'id': conv_id,
        'tenant_id': uuid4(),
        'contact_id': appointment['contact_id'],
        'channel_id': uuid4(),
        'status': 'bot_active',
        'metadata': json.dumps({
            'self_service': {
                'flow': FLOW_RESCHEDULE,
                'step': STEP_COMPLETED,
                'appointment_id': str(appointment['id']),
                'source': 'auto_rebook',
            }
        }),
    }
    conn = FakeConn(appointment=appointment, conversation_row=conversation_row)
    trace = asyncio.run(
        execute_auto_rebook_timeout(
            conn,
            tenant_id=conversation_row['tenant_id'],
            conversation_id=conv_id,
            appointment_id=appointment['id'],
        )
    )
    assert trace['cancelled'] is False
    assert trace['skipped_reason'] == 'state_changed'
    # No cancellation, no handoff, no tag, no audit.
    assert not conn.appointment_updates
    assert not conn.handoff_inserts
    assert not conn.tag_assignments


def test_execute_auto_rebook_timeout_skips_when_customer_replied():
    """If a fresh inbound exists after the rebook was sent, the customer is
    engaged — the timeout must back off."""
    appointment = _future_appointment(hours_ahead=72)
    conv_id = uuid4()
    conversation_row = {
        'id': conv_id,
        'tenant_id': uuid4(),
        'contact_id': appointment['contact_id'],
        'channel_id': uuid4(),
        'status': 'bot_active',
        'metadata': json.dumps({
            'self_service': {
                'flow': FLOW_RESCHEDULE,
                'step': STEP_AWAITING_RESCHEDULE_SLOT,
                'appointment_id': str(appointment['id']),
                'source': 'auto_rebook',
            }
        }),
    }
    conn = FakeConn(
        appointment=appointment,
        conversation_row=conversation_row,
        rebook_started_at=datetime.now(UTC) - timedelta(minutes=30),
        has_recent_inbound=True,
    )
    trace = asyncio.run(
        execute_auto_rebook_timeout(
            conn,
            tenant_id=conversation_row['tenant_id'],
            conversation_id=conv_id,
            appointment_id=appointment['id'],
        )
    )
    assert trace['skipped_reason'] == 'customer_replied'
    assert not conn.appointment_updates


def test_execute_auto_rebook_timeout_cancels_and_escalates():
    """The happy-path timeout: no inbound for 90 min → cancel appointment,
    open handoff, tag the contact."""
    appointment = _future_appointment(hours_ahead=72)
    conv_id = uuid4()
    tenant_id = uuid4()
    conversation_row = {
        'id': conv_id,
        'tenant_id': tenant_id,
        'contact_id': appointment['contact_id'],
        'channel_id': uuid4(),
        'status': 'bot_active',
        'metadata': json.dumps({
            'self_service': {
                'flow': FLOW_RESCHEDULE,
                'step': STEP_AWAITING_RESCHEDULE_SLOT,
                'appointment_id': str(appointment['id']),
                'source': 'auto_rebook',
            }
        }),
    }
    conn = FakeConn(
        appointment=appointment,
        conversation_row=conversation_row,
        rebook_started_at=datetime.now(UTC) - timedelta(minutes=120),
        has_recent_inbound=False,
    )
    trace = asyncio.run(
        execute_auto_rebook_timeout(
            conn,
            tenant_id=tenant_id,
            conversation_id=conv_id,
            appointment_id=appointment['id'],
        )
    )
    assert trace['cancelled'] is True
    assert trace['handoff_marked'] is True
    assert trace['tag_assigned'] is True
    # Appointment marked cancelled.
    assert any(
        "set status='cancelled'" in u['query']
        for u in conn.appointment_updates
    )
    # Audit logged with the right reason.
    assert any(a.get('action') == 'bot.appointment_cancelled' for a in conn.audit_actions)
    # Handoff opened.
    assert conn.handoff_inserts
    assert conn.handoff_inserts[0]['reason'] == AUTO_REBOOK_TIMEOUT_REASON
    # Follow-up tag created and assigned to the contact.
    assert any(t['name'] == FOLLOWUP_TAG_NAME for t in conn.tag_inserts)
    assert conn.tag_assignments
    assert conn.tag_assignments[0]['contact_id'] == appointment['contact_id']
    # State transitioned to completed with the timeout reason for inspection.
    last_meta = conn.metadata_updates[-1] if conn.metadata_updates else None
    if last_meta is not None:
        assert last_meta['self_service']['closed_reason'] == AUTO_REBOOK_TIMEOUT_REASON


def test_execute_auto_rebook_timeout_handles_missing_conversation():
    """If the conversation was deleted between scheduling and dispatch, the
    timeout must skip cleanly without raising."""
    tenant_id = uuid4()
    conn = FakeConn(conversation_row=None)
    trace = asyncio.run(
        execute_auto_rebook_timeout(
            conn,
            tenant_id=tenant_id,
            conversation_id=uuid4(),
            appointment_id=uuid4(),
        )
    )
    assert trace['skipped_reason'] == 'conversation_missing'
    assert not conn.appointment_updates
    assert not conn.handoff_inserts
