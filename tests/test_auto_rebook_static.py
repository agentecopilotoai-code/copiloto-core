"""Static tests for TASK-0044 — Auto-rebooking on active confirmation decline.

Verifies:
- The toggle ``auto_rebook_on_decline`` defaults to ``True`` and is correctly
  parsed from notification settings shapes (dict, JSON-string, missing, false).
- ``maybe_record_confirmation`` ignores inbound when there's an active
  self-service flow (so a "no" mid-rebook doesn't re-trigger a new rebooking
  loop).
- ``start_auto_rebook_flow`` sends the empathic intro + offers slots, persists
  state tagged with ``source='auto_rebook'``, and is idempotent.
- A "no" reply mid-rebook cancels the appointment and escalates.
- The orchestrator forwards conversation/channel info to
  ``maybe_record_confirmation`` and short-circuits when auto-rebook returns.
- The TenantSetupWizard exposes the toggle in the Notificaciones tab.
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from app.services import appointment_self_service
from app.services.appointment_self_service import (
    FLOW_RESCHEDULE,
    PREFIX_RESCHED_SLOT,
    STEP_AWAITING_RESCHEDULE_SLOT,
    start_auto_rebook_flow,
)
from app.services.feedback_flow import (
    auto_rebook_enabled,
    maybe_record_confirmation,
)


FEEDBACK_FLOW = Path('app/services/feedback_flow.py')
SELF_SERVICE = Path('app/services/appointment_self_service.py')
ORCHESTRATOR = Path('app/services/rag_orchestrator.py')
TENANT_WIZARD = Path('admin-panel/src/components/modules/tenantSetup/TenantSetupWizard.jsx')


# ───── Toggle parsing ──────────────────────────────────────────────────────


def test_auto_rebook_enabled_defaults_to_true_when_missing():
    assert auto_rebook_enabled({}) is True
    assert auto_rebook_enabled(None) is True


def test_auto_rebook_enabled_respects_explicit_false():
    assert auto_rebook_enabled({'auto_rebook_on_decline': False}) is False


def test_auto_rebook_enabled_handles_json_string_settings():
    raw = json.dumps({'auto_rebook_on_decline': False})
    assert auto_rebook_enabled(raw) is False
    raw_true = json.dumps({'auto_rebook_on_decline': True})
    assert auto_rebook_enabled(raw_true) is True


def test_auto_rebook_enabled_handles_invalid_payload_as_default():
    assert auto_rebook_enabled('not a json') is True
    assert auto_rebook_enabled(42) is True


# ───── Module surfaces ─────────────────────────────────────────────────────


def test_start_auto_rebook_flow_is_exported():
    source = SELF_SERVICE.read_text()
    assert 'async def start_auto_rebook_flow(' in source
    assert "'source': 'auto_rebook'" in source
    assert "'auto_rebook_intro'" in source


def test_self_service_handles_decline_during_auto_rebook():
    source = SELF_SERVICE.read_text()
    assert "state.get('source') == 'auto_rebook'" in source
    assert "auto_rebook_declined" in source


def test_feedback_flow_passes_conversation_and_channel_to_auto_rebook():
    source = FEEDBACK_FLOW.read_text()
    assert 'auto_rebook_enabled' in source
    assert 'start_auto_rebook_flow' in source
    # Skip-on-active-self-service guard prevents loops.
    assert 'self_service' in source
    assert "self_service_state.get('step') not in (None, 'completed')" in source


def test_orchestrator_short_circuits_on_auto_rebook_step():
    source = ORCHESTRATOR.read_text()
    assert 'conversation=conversation' in source
    assert "auto_rebook.get('action') == 'self_service_step_sent'" in source
    assert "auto_rebook.get('action') == 'self_service_escalated'" in source
    assert "reason='auto_rebook_escalated'" in source


def test_tenant_wizard_exposes_auto_rebook_toggle():
    source = TENANT_WIZARD.read_text()
    assert 'auto_rebook_on_decline' in source
    assert 'Ofrecer reprogramar al declinar la confirmación' in source


# ───── Functional: FakeConn driven scenarios ───────────────────────────────


class FakeConn:
    def __init__(self, *, appointment=None, resource=None, notification_settings=None):
        self.appointment = appointment
        self.resource = resource
        self.notification_settings = notification_settings
        self.inserted_messages = []
        self.inserted_events = []
        self.audit_actions = []
        self.appointment_updates = []
        self.metadata_updates = []
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
        if 'select notification_settings from app.tenant_settings' in query:
            return self.notification_settings
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
            try:
                self.metadata_updates.append(json.loads(args[0]))
            except Exception:
                pass
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


def test_start_auto_rebook_sends_intro_and_offers_slots():
    appointment = _future_appointment(hours_ahead=72)
    conn = FakeConn(
        appointment=appointment,
        resource=_resource_with_open_hours(appointment['resource_id']),
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
    assert result['flow'] == FLOW_RESCHEDULE
    assert result['source'] == 'auto_rebook'
    # First outbound is the empathic intro.
    intro = conn.inserted_messages[0]
    assert 'Sin problema' in intro['body_text']
    # Persisted state must mark this as auto_rebook for the "no" cancel path.
    assert conn.metadata_updates
    last_meta = conn.metadata_updates[-1]
    assert last_meta['self_service']['source'] == 'auto_rebook'
    assert last_meta['self_service']['step'] == STEP_AWAITING_RESCHEDULE_SLOT


def test_start_auto_rebook_is_idempotent():
    appointment = _future_appointment(hours_ahead=72)
    conn = FakeConn(
        appointment=appointment,
        resource=_resource_with_open_hours(appointment['resource_id']),
    )
    inbound = _inbound(body='no')
    conn._idempotency_seen.add(f'self_service_auto_rebook:{inbound["id"]}')
    result = asyncio.run(
        start_auto_rebook_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=_conversation(),
            appointment=appointment,
            inbound_message=inbound,
        )
    )
    assert result == {'action': 'skipped', 'reason': 'already_processed'}


def test_start_auto_rebook_escalates_when_no_slots():
    appointment = _future_appointment(hours_ahead=72)
    conn = FakeConn(
        appointment=appointment,
        resource={
            'id': appointment['resource_id'],
            'name': 'Profesional',
            'code': 'p1',
            'capabilities': {'working_hours': {}},  # nothing open ever
        },
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
    assert result['action'] == 'self_service_escalated'
    assert result['reason'] == 'no_alternative_slots'


def test_decline_during_auto_rebook_cancels_and_escalates():
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
    result = asyncio.run(
        appointment_self_service.maybe_run_self_service_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=_conversation({'self_service': state}),
            contact={'id': appointment['contact_id']},
            inbound_message=_inbound(body='no'),
            intent='greeting',
        )
    )
    assert result['action'] == 'self_service_escalated'
    assert result['reason'] == 'auto_rebook_declined'
    actions = [a['action'] for a in conn.audit_actions]
    assert 'bot.appointment_cancelled' in actions


def test_maybe_record_confirmation_skips_when_self_service_active():
    appointment = _future_appointment(hours_ahead=72)
    conv = _conversation({
        'self_service': {
            'flow': FLOW_RESCHEDULE,
            'step': STEP_AWAITING_RESCHEDULE_SLOT,
            'appointment_id': str(appointment['id']),
            'source': 'auto_rebook',
        }
    })
    conn = FakeConn(appointment=appointment)
    result = asyncio.run(
        maybe_record_confirmation(
            conn,
            tenant_id=uuid4(),
            contact_id=appointment['contact_id'],
            inbound_message=_inbound(body='no'),
            conversation=conv,
            channel_id=uuid4(),
            channel_account_mode='mock',
        )
    )
    # Guard returned None → no UPDATE on the appointment, no nested rebook.
    assert result is None
    assert not conn.appointment_updates


def test_maybe_record_confirmation_skips_when_toggle_disabled():
    """Even though the customer declined, with the toggle off no rebook
    flow is started."""
    appointment = _future_appointment(hours_ahead=72)
    conn = FakeConn(
        appointment=appointment,
        notification_settings={'auto_rebook_on_decline': False},
    )
    result = asyncio.run(
        maybe_record_confirmation(
            conn,
            tenant_id=uuid4(),
            contact_id=appointment['contact_id'],
            inbound_message=_inbound(body='no'),
            conversation=_conversation(),
            channel_id=uuid4(),
            channel_account_mode='mock',
        )
    )
    assert result is not None
    assert result['confirmation_status'] == 'declined'
    assert 'auto_rebook' not in result
    # No outbound rebook message queued.
    intro = [m for m in conn.inserted_messages if 'Sin problema' in (m['body_text'] or '')]
    assert not intro


def test_maybe_record_confirmation_triggers_auto_rebook_when_enabled():
    appointment = _future_appointment(hours_ahead=72)
    conn = FakeConn(
        appointment=appointment,
        resource=_resource_with_open_hours(appointment['resource_id']),
        notification_settings={'auto_rebook_on_decline': True},
    )
    result = asyncio.run(
        maybe_record_confirmation(
            conn,
            tenant_id=uuid4(),
            contact_id=appointment['contact_id'],
            inbound_message=_inbound(body='no'),
            conversation=_conversation(),
            channel_id=uuid4(),
            channel_account_mode='mock',
        )
    )
    assert result['confirmation_status'] == 'declined'
    auto_rebook = result.get('auto_rebook')
    assert auto_rebook is not None
    assert auto_rebook['action'] == 'self_service_step_sent'
    intro = [m for m in conn.inserted_messages if 'Sin problema' in (m['body_text'] or '')]
    assert intro
