"""Static tests for TASK-0043 — Self-service cancel & reschedule by WhatsApp.

These tests verify the module's exposed surface (constants, helpers, state
machine) end-to-end with a ``FakeConn`` stand-in, the orchestrator's wiring,
the new escalation policy field in the admin panel, and the OperationsDesk
badge that flags conversations modified by the bot.
"""
from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from app.services.appointment_self_service import (
    FLOW_CANCEL,
    FLOW_RESCHEDULE,
    INTENT_CANCEL,
    INTENT_RESCHEDULE,
    PREFIX_CANCEL_CONFIRM,
    PREFIX_RESCHED_SLOT,
    STEP_AWAITING_CANCEL_CONFIRM,
    STEP_AWAITING_RESCHEDULE_SLOT,
    STEP_COMPLETED,
    maybe_run_self_service_flow,
    min_hours_before_start,
)


SELF_SERVICE = Path('app/services/appointment_self_service.py')
ORCHESTRATOR = Path('app/services/rag_orchestrator.py')
OPERATIONS_DESK = Path('admin-panel/src/features/agente/inbox')


def _operations_desk_source() -> str:
    """Combined source of the Operación · Inbox feature dir (UI-009.1 split).

    OperationsDesk.jsx (2088 LOC) was split into features/agente/inbox/; the
    static assertions below run against the concatenated feature source.
    """
    return '\n'.join(p.read_text() for p in sorted(OPERATIONS_DESK.rglob('*.js*')))
TENANT_SETUP_FEATURE = Path('admin-panel/src/features/owner-admin/tenant-setup')

def _tenant_setup_source() -> str:
    return '\n'.join(p.read_text() for p in sorted(TENANT_SETUP_FEATURE.rglob('*.js*')))

# ───── Public API & constants ──────────────────────────────────────────────


def test_flow_constants_are_stable():
    assert FLOW_CANCEL == 'cancel'
    assert FLOW_RESCHEDULE == 'reschedule'
    assert PREFIX_CANCEL_CONFIRM == 'cancel_confirm'
    assert PREFIX_RESCHED_SLOT == 'resched_slot'
    assert STEP_AWAITING_CANCEL_CONFIRM == 'awaiting_cancel_confirm'
    assert STEP_AWAITING_RESCHEDULE_SLOT == 'awaiting_reschedule_slot'
    assert STEP_COMPLETED == 'completed'
    assert INTENT_CANCEL == 'cancel_appointment'
    assert INTENT_RESCHEDULE == 'reschedule_appointment'


def test_min_hours_before_start_falls_back_to_default():
    assert min_hours_before_start(None) == 2.0
    assert min_hours_before_start({}) == 2.0
    assert min_hours_before_start({'self_service': {}}) == 2.0
    assert min_hours_before_start({'self_service': {'min_hours_before_start': 'x'}}) == 2.0
    assert min_hours_before_start({'self_service': {'min_hours_before_start': -1}}) == 2.0


def test_min_hours_before_start_parses_explicit_override():
    assert min_hours_before_start({'self_service': {'min_hours_before_start': 4}}) == 4.0
    assert min_hours_before_start({'self_service': {'min_hours_before_start': '0.5'}}) == 0.5
    # JSON-encoded settings (jsonb arrives as str through asyncpg in some paths).
    raw = json.dumps({'self_service': {'min_hours_before_start': 6}})
    assert min_hours_before_start(raw) == 6.0


# ───── Module source surface ───────────────────────────────────────────────


def test_self_service_module_audits_both_flows():
    source = SELF_SERVICE.read_text()
    assert 'bot.appointment_cancelled' in source
    assert 'bot.appointment_rescheduled' in source
    assert 'self_service.handled' in source
    assert 'cancel_appointment_reminder_jobs' in source
    assert 'regenerate_appointment_reminder_jobs' in source


def test_self_service_module_uses_booking_flow_helpers():
    source = SELF_SERVICE.read_text()
    assert 'from app.services.booking_flow import' in source
    assert 'compute_free_slots' in source
    assert '_busy_intervals' in source
    assert '_working_hours_for_date' in source
    assert '_fetch_resource' in source


# ───── Orchestrator integration ─────────────────────────────────────────────


def test_orchestrator_calls_self_service_before_qualification():
    source = ORCHESTRATOR.read_text()
    assert 'from app.services.appointment_self_service import maybe_run_self_service_flow' in source
    idx_ss = source.find('maybe_run_self_service_flow(')
    idx_qual = source.find('maybe_run_qualification_flow(')
    idx_book = source.find('maybe_run_booking_flow(')
    assert idx_ss != -1 and idx_qual != -1 and idx_book != -1
    assert idx_ss < idx_qual < idx_book


def test_orchestrator_escalates_self_service_result():
    source = ORCHESTRATOR.read_text()
    assert "action == 'self_service_escalated'" in source
    assert "reason='self_service_escalated'" in source


# ───── Admin panel wiring ──────────────────────────────────────────────────


def test_escalation_form_exposes_self_service_min_hours():
    source = _tenant_setup_source()
    assert 'selfServiceMinHoursBeforeStart' in source
    assert 'min_hours_before_start' in source
    assert 'Self-service: horas mínimas antes de la cita' in source


def test_operations_desk_renders_self_service_badge():
    source = _operations_desk_source()
    assert 'self-service' in source
    assert 'self_service' in source


# ───── State machine — driven with FakeConn ────────────────────────────────


class FakeConn:
    """Minimal asyncpg stand-in. Each query is matched by substring."""

    def __init__(
        self,
        *,
        upcoming_appointment=None,
        appointments_by_id=None,
        resource=None,
        busy=None,
        escalation_policy=None,
    ):
        self.upcoming_appointment = upcoming_appointment
        self.appointments_by_id = appointments_by_id or {}
        self.resource = resource
        self.busy_rows = busy or []
        self.escalation_policy = escalation_policy or {}
        self.inserted_messages = []
        self.inserted_events = []
        self.audit_actions = []
        self.appointment_updates = []
        self.executed = []
        self.transactions = 0
        self.reschedule_should_conflict = False

    # asyncpg transaction CM ------------------------------------------------
    def transaction(self):
        outer = self

        class _Ctx:
            async def __aenter__(self_inner):
                outer.transactions += 1
                if outer.reschedule_should_conflict:
                    raise RuntimeError('exclude using gist conflict')
                return None

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _Ctx()

    async def fetch(self, query, *args):
        if 'from app.reminder_jobs' in query:
            return []
        return []

    async def fetchrow(self, query, *args):
        if 'from app.appointments' in query and "status in ('scheduled','confirmed')" in query and 'starts_at >= now()' in query:
            return self.upcoming_appointment
        if 'from app.appointments' in query and 'and id=$2' in query:
            return self.appointments_by_id.get(args[1])
        if 'from app.resources' in query and 'and id=$2' in query:
            return self.resource
        if 'from app.tenant_settings' in query and 'escalation_policy' in query:
            return {'escalation_policy': self.escalation_policy}
        if 'from app.appointments' in query and 'resource_id=$2' in query and 'starts_at < $4' in query:
            return self.busy_rows
        if 'insert into app.messages' in query:
            mid = uuid4()
            payload = json.loads(args[3]) if len(args) >= 4 else {}
            self.inserted_messages.append({
                'id': mid,
                'tenant_id': args[0],
                'conversation_id': args[1],
                'body_text': args[2],
                'payload': payload,
            })
            return {'id': mid}
        if 'insert into app.audit_logs' in query:
            return {'id': 1}
        return None

    async def fetchval(self, query, *args):
        if 'select id from app.domain_events' in query and 'idempotency_key' in query:
            return None
        return None

    async def execute(self, query, *args):
        if 'insert into app.domain_events' in query:
            self.inserted_events.append({
                'idempotency_key': args[2],
                'payload': json.loads(args[3]) if len(args) >= 4 else {},
            })
        elif 'insert into app.audit_logs' in query:
            self.audit_actions.append({'action': args[3] if len(args) > 3 else None, 'args': args})
        elif 'update app.appointments' in query:
            self.appointment_updates.append({'query': query, 'args': args})
            # Reflect the mutation on the cached row so subsequent reads see it.
            if "set status='cancelled'" in query:
                appt = self.appointments_by_id.get(args[1])
                if appt is not None:
                    appt['status'] = 'cancelled'
            elif 'set starts_at=$3, ends_at=$4' in query:
                appt = self.appointments_by_id.get(args[1])
                if appt is not None:
                    appt['starts_at'] = args[2]
                    appt['ends_at'] = args[3]
        elif 'update app.reminder_jobs' in query:
            self.executed.append((query, args))
        elif 'update app.conversations' in query:
            self.executed.append((query, args))
        else:
            self.executed.append((query, args))
        return None


def _conversation(metadata=None):
    return {'id': uuid4(), 'metadata': metadata or {}}


def _contact():
    return {'id': uuid4()}


def _inbound(body=None, interactive_id=None):
    return {
        'id': uuid4(),
        'body_text': body,
        'payload': {'interactive_id': interactive_id} if interactive_id else {},
    }


def _future_appointment(hours_ahead=24):
    starts = datetime.now(UTC) + timedelta(hours=hours_ahead)
    ends = starts + timedelta(minutes=60)
    return {
        'id': uuid4(),
        'contact_id': uuid4(),
        'resource_id': uuid4(),
        'service_id': uuid4(),
        'service_code': 'consulta',
        'starts_at': starts,
        'ends_at': ends,
        'status': 'scheduled',
        'payment_status': 'not_required',
    }


# ── 1. No upcoming appointment ──


def test_self_service_responds_when_contact_has_no_upcoming():
    conn = FakeConn(upcoming_appointment=None)
    result = asyncio.run(
        maybe_run_self_service_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=_conversation(),
            contact=_contact(),
            inbound_message=_inbound(body='quiero cancelar mi cita'),
            intent=INTENT_CANCEL,
        )
    )
    assert result == {'action': 'self_service_no_appointment'}
    assert len(conn.inserted_messages) == 1
    assert 'cita próxima' in conn.inserted_messages[0]['body_text']


# ── 2. Skipping when intent unrelated ──


def test_self_service_returns_none_for_unrelated_intent():
    conn = FakeConn(upcoming_appointment=_future_appointment())
    result = asyncio.run(
        maybe_run_self_service_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=_conversation(),
            contact=_contact(),
            inbound_message=_inbound(body='hola'),
            intent='greeting',
        )
    )
    assert result is None
    assert conn.inserted_messages == []


# ── 3. Cancel: presents confirmation ──


def test_cancel_flow_presents_confirmation_buttons():
    appointment = _future_appointment(hours_ahead=72)
    conn = FakeConn(upcoming_appointment=appointment)
    result = asyncio.run(
        maybe_run_self_service_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=_conversation(),
            contact=_contact(),
            inbound_message=_inbound(body='quiero cancelar mi cita'),
            intent=INTENT_CANCEL,
        )
    )
    assert result == {
        'action': 'self_service_step_sent',
        'flow': FLOW_CANCEL,
        'step': STEP_AWAITING_CANCEL_CONFIRM,
    }
    assert len(conn.inserted_messages) == 1
    payload = conn.inserted_messages[0]['payload']
    assert payload['self_service_step'] == STEP_AWAITING_CANCEL_CONFIRM
    btn_ids = [
        b['reply']['id']
        for b in payload['interactive']['action']['buttons']
    ]
    assert f'{PREFIX_CANCEL_CONFIRM}:yes' in btn_ids
    assert f'{PREFIX_CANCEL_CONFIRM}:no' in btn_ids


# ── 4. Cancel: button reply executes the cancel ──


def test_cancel_flow_yes_button_cancels_and_audits():
    appointment = _future_appointment(hours_ahead=72)
    conn = FakeConn(
        upcoming_appointment=appointment,
        appointments_by_id={appointment['id']: appointment},
    )
    state = {
        'flow': FLOW_CANCEL,
        'step': STEP_AWAITING_CANCEL_CONFIRM,
        'appointment_id': str(appointment['id']),
    }
    result = asyncio.run(
        maybe_run_self_service_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=_conversation({'self_service': state}),
            contact=_contact(),
            inbound_message=_inbound(interactive_id=f'{PREFIX_CANCEL_CONFIRM}:yes'),
            intent='greeting',  # mid-flow doesn't need a matching intent
        )
    )
    assert result['action'] == 'self_service_cancelled'
    assert result['appointment_id'] == str(appointment['id'])
    # One UPDATE on appointments to cancelled.
    cancel_updates = [u for u in conn.appointment_updates if "status='cancelled'" in u['query']]
    assert cancel_updates
    # Audit for bot.appointment_cancelled emitted.
    actions = [a['action'] for a in conn.audit_actions]
    assert 'bot.appointment_cancelled' in actions


# ── 5. Cancel: "no" keeps appointment ──


def test_cancel_flow_no_button_keeps_appointment():
    appointment = _future_appointment(hours_ahead=72)
    conn = FakeConn(
        upcoming_appointment=appointment,
        appointments_by_id={appointment['id']: appointment},
    )
    state = {
        'flow': FLOW_CANCEL,
        'step': STEP_AWAITING_CANCEL_CONFIRM,
        'appointment_id': str(appointment['id']),
    }
    result = asyncio.run(
        maybe_run_self_service_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=_conversation({'self_service': state}),
            contact=_contact(),
            inbound_message=_inbound(interactive_id=f'{PREFIX_CANCEL_CONFIRM}:no'),
            intent='greeting',
        )
    )
    assert result['action'] == 'self_service_kept'
    cancel_updates = [u for u in conn.appointment_updates if "status='cancelled'" in u['query']]
    assert not cancel_updates


# ── 6. Reschedule: too close to start escalates ──


def test_self_service_escalates_when_too_close_to_start():
    appointment = _future_appointment(hours_ahead=1)  # within 2h default
    conn = FakeConn(upcoming_appointment=appointment)
    result = asyncio.run(
        maybe_run_self_service_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=_conversation(),
            contact=_contact(),
            inbound_message=_inbound(body='cambiar mi cita'),
            intent=INTENT_RESCHEDULE,
        )
    )
    assert result['action'] == 'self_service_escalated'
    assert result['reason'] == 'too_close_to_start'


# ── 7. Paid appointment escalates ──


def test_self_service_escalates_when_appointment_is_paid():
    appointment = _future_appointment(hours_ahead=48)
    appointment['payment_status'] = 'paid'
    conn = FakeConn(upcoming_appointment=appointment)
    result = asyncio.run(
        maybe_run_self_service_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=_conversation(),
            contact=_contact(),
            inbound_message=_inbound(body='cambiar mi cita'),
            intent=INTENT_RESCHEDULE,
        )
    )
    assert result['action'] == 'self_service_escalated'
    assert result['reason'] == 'paid_appointment'


# ── 8. Reschedule: offers slots ──


def test_reschedule_flow_offers_three_slots():
    appointment = _future_appointment(hours_ahead=72)
    weekday = (datetime.now(UTC) + timedelta(days=1)).weekday()
    weekday_key = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')[weekday]
    capabilities = {
        'working_hours': {
            weekday_key: [{'start': '09:00', 'end': '13:00'}],
        }
    }
    resource = {
        'id': appointment['resource_id'],
        'name': 'Profesional 1',
        'code': 'p1',
        'capabilities': capabilities,
    }
    conn = FakeConn(upcoming_appointment=appointment, resource=resource, busy=[])
    result = asyncio.run(
        maybe_run_self_service_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=_conversation(),
            contact=_contact(),
            inbound_message=_inbound(body='cambiar mi cita'),
            intent=INTENT_RESCHEDULE,
        )
    )
    assert result['action'] == 'self_service_step_sent'
    assert result['flow'] == FLOW_RESCHEDULE
    # The persisted state must hold the offered slots so a subsequent reply maps
    # the button to the correct slot.
    metadata_updates = [
        e for e in conn.executed if isinstance(e, tuple) and 'update app.conversations' in e[0]
    ]
    assert metadata_updates
    last_meta = json.loads(metadata_updates[-1][1][0])
    assert last_meta['self_service']['flow'] == FLOW_RESCHEDULE
    assert len(last_meta['self_service']['offered_slots']) == 3


# ── 9. Reschedule: slot pick conflicts and re-offers ──


def test_reschedule_flow_handles_slot_conflict():
    appointment = _future_appointment(hours_ahead=72)
    weekday = (datetime.now(UTC) + timedelta(days=1)).weekday()
    weekday_key = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')[weekday]
    capabilities = {
        'working_hours': {
            weekday_key: [{'start': '09:00', 'end': '13:00'}],
        }
    }
    resource = {
        'id': appointment['resource_id'],
        'name': 'Profesional 1',
        'code': 'p1',
        'capabilities': capabilities,
    }
    conn = FakeConn(
        upcoming_appointment=appointment,
        appointments_by_id={appointment['id']: appointment},
        resource=resource,
        busy=[],
    )
    conn.reschedule_should_conflict = True
    offered_slot = {
        'date': (datetime.now(UTC) + timedelta(days=1)).date().isoformat(),
        'start_time': '09:00',
    }
    state = {
        'flow': FLOW_RESCHEDULE,
        'step': STEP_AWAITING_RESCHEDULE_SLOT,
        'appointment_id': str(appointment['id']),
        'offered_slots': [offered_slot],
    }
    result = asyncio.run(
        maybe_run_self_service_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=_conversation({'self_service': state}),
            contact=_contact(),
            inbound_message=_inbound(interactive_id=f'{PREFIX_RESCHED_SLOT}:0'),
            intent='greeting',
        )
    )
    assert result['action'] == 'self_service_step_sent'
    assert result['step'] == STEP_AWAITING_RESCHEDULE_SLOT
    # No bot.appointment_rescheduled audit on failure.
    actions = [a['action'] for a in conn.audit_actions]
    assert 'bot.appointment_rescheduled' not in actions


# ── 10. Reschedule: successful slot pick ──


def test_reschedule_flow_success_emits_audit_and_updates_appointment():
    appointment = _future_appointment(hours_ahead=72)
    weekday = (datetime.now(UTC) + timedelta(days=1)).weekday()
    weekday_key = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')[weekday]
    capabilities = {
        'working_hours': {
            weekday_key: [{'start': '09:00', 'end': '13:00'}],
        }
    }
    resource = {
        'id': appointment['resource_id'],
        'name': 'Profesional 1',
        'code': 'p1',
        'capabilities': capabilities,
    }
    conn = FakeConn(
        upcoming_appointment=appointment,
        appointments_by_id={appointment['id']: appointment},
        resource=resource,
        busy=[],
    )
    offered_slot = {
        'date': (datetime.now(UTC) + timedelta(days=1)).date().isoformat(),
        'start_time': '09:00',
    }
    state = {
        'flow': FLOW_RESCHEDULE,
        'step': STEP_AWAITING_RESCHEDULE_SLOT,
        'appointment_id': str(appointment['id']),
        'offered_slots': [offered_slot],
    }
    result = asyncio.run(
        maybe_run_self_service_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=_conversation({'self_service': state}),
            contact=_contact(),
            inbound_message=_inbound(interactive_id=f'{PREFIX_RESCHED_SLOT}:0'),
            intent='greeting',
        )
    )
    assert result['action'] == 'self_service_rescheduled'
    actions = [a['action'] for a in conn.audit_actions]
    assert 'bot.appointment_rescheduled' in actions
    moved = [u for u in conn.appointment_updates if 'set starts_at=$3' in u['query']]
    assert moved


# ── 11. Idempotency replay ──


def test_self_service_idempotency_skips_replays():
    appointment = _future_appointment()
    conn = FakeConn(upcoming_appointment=appointment)
    inbound = _inbound(body='quiero cancelar')
    # Pre-mark this inbound as already processed.
    original_fetchval = conn.fetchval

    async def fake_fetchval(query, *args):
        if 'idempotency_key' in query and args[1] == f'self_service:{inbound["id"]}':
            return 1
        return await original_fetchval(query, *args)

    conn.fetchval = fake_fetchval
    result = asyncio.run(
        maybe_run_self_service_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=_conversation(),
            contact=_contact(),
            inbound_message=inbound,
            intent=INTENT_CANCEL,
        )
    )
    assert result == {'action': 'skipped', 'reason': 'already_processed'}


# ── 12. No alternative slots ──


def test_reschedule_flow_escalates_when_no_slots_available():
    appointment = _future_appointment(hours_ahead=72)
    # Empty working_hours → no candidate slot ever.
    resource = {
        'id': appointment['resource_id'],
        'name': 'Profesional 1',
        'code': 'p1',
        'capabilities': {'working_hours': {}},
    }
    conn = FakeConn(upcoming_appointment=appointment, resource=resource, busy=[])
    result = asyncio.run(
        maybe_run_self_service_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=_conversation(),
            contact=_contact(),
            inbound_message=_inbound(body='cambiar mi cita'),
            intent=INTENT_RESCHEDULE,
        )
    )
    assert result['action'] == 'self_service_escalated'
    assert result['reason'] == 'no_alternative_slots'


# ── 13. State-machine prefix sanity ──


def test_prefixes_match_those_in_module_source():
    source = SELF_SERVICE.read_text()
    assert f"PREFIX_CANCEL_CONFIRM = '{PREFIX_CANCEL_CONFIRM}'" in source
    assert f"PREFIX_RESCHED_SLOT = '{PREFIX_RESCHED_SLOT}'" in source
