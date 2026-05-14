"""Static tests for TASK-0053 — Budget tier and urgency triage presets.

Covers:
- Schema additions (``qualification_questions.preset`` column).
- Pydantic schema extensions (preset, tier_value, urgency_normalized).
- qualification_flow helpers (_budget_tier_summary, _urgency_summary,
  _vip_budget_threshold, _is_vip).
- Triage handoff signal on completion, VIP tag application, persisted
  state and audit metadata.
- Orchestrator forwards ``triage_handoff`` to ``_do_handoff`` with
  reason ``urgency_triage``.
- Admin panel presets and OperationsDesk urgent badge + sorting.
"""
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from app.services.qualification_flow import (
    DEFAULT_VIP_BUDGET_THRESHOLD,
    KIND_SINGLE_CHOICE,
    PREFIX_QUALIFY,
    PRESET_BUDGET_TIER,
    PRESET_URGENCY_LEVEL,
    URGENCY_TRIAGE_REASON,
    URGENT_LEVELS,
    VIP_TAG_NAME,
    _budget_tier_summary,
    _is_vip,
    _urgency_summary,
    _vip_budget_threshold,
    maybe_run_qualification_flow,
)


SCHEMA = Path('infra/postgres/01-schema.sql')
SCHEMAS = Path('app/api/v1/schemas.py')
ROUTES = Path('app/api/v1/routes.py')
ORCHESTRATOR = Path('app/services/rag_orchestrator.py')
TENANT_SETUP_FEATURE = Path('admin-panel/src/features/owner-admin/tenant-setup')


def _tenant_setup_source() -> str:
    return '\n'.join(p.read_text() for p in sorted(TENANT_SETUP_FEATURE.rglob('*.js*')))
OPERATIONS_DESK = Path('admin-panel/src/features/agente/inbox')


def _operations_desk_source() -> str:
    """Combined source of the Operación · Inbox feature dir (UI-009.1 split).

    OperationsDesk.jsx (2088 LOC) was split into features/agente/inbox/; the
    static assertions below run against the concatenated feature source.
    """
    return '\n'.join(p.read_text() for p in sorted(OPERATIONS_DESK.rglob('*.js*')))


# ───── Schema additions ────────────────────────────────────────────────────


def test_schema_adds_preset_column_with_check_constraint():
    schema = SCHEMA.read_text()
    assert (
        "preset text check (preset is null or preset in "
        "('budget_tier','urgency_level'))"
    ) in schema


def test_pydantic_schemas_expose_presets_and_option_metadata():
    src = SCHEMAS.read_text()
    assert "QUALIFICATION_QUESTION_PRESETS = ('budget_tier', 'urgency_level')" in src
    assert "URGENCY_NORMALIZED_VALUES = ('emergency', 'high', 'normal', 'low')" in src
    assert 'tier_value: float | None' in src
    assert 'urgency_normalized: str | None' in src
    assert 'preset: str | None' in src


def test_routes_projection_and_inserts_include_preset():
    src = ROUTES.read_text()
    # TASK-0054 extended the projection with `key`; check both fragments
    # remain in their canonical order.
    assert ", preset, key, created_at, updated_at" in src
    assert 'applies_to_service_ids, preset' in src
    assert '$8::uuid[], $8' not in src  # sanity: don't reuse param
    assert 'payload.preset' in src


# ───── State helpers ───────────────────────────────────────────────────────


def test_constants_are_consistent():
    assert PRESET_BUDGET_TIER == 'budget_tier'
    assert PRESET_URGENCY_LEVEL == 'urgency_level'
    assert URGENT_LEVELS == {'emergency', 'high'}
    assert URGENCY_TRIAGE_REASON == 'urgency_triage'
    assert VIP_TAG_NAME == 'VIP'
    assert DEFAULT_VIP_BUDGET_THRESHOLD == 0.0


def test_budget_tier_summary_picks_option_value():
    qid = uuid4()
    question = {
        'id': qid,
        'kind': KIND_SINGLE_CHOICE,
        'preset': PRESET_BUDGET_TIER,
        'options': [
            {'value': 'low', 'label': 'Bajo', 'tier_value': 200000},
            {'value': 'high', 'label': 'Alto', 'tier_value': 1500000},
        ],
    }
    summary = _budget_tier_summary([question], {str(qid): 'high'})
    assert summary == {
        'tier_label': 'Alto',
        'tier_value': 1500000.0,
        'option_value': 'high',
    }


def test_budget_tier_summary_returns_none_when_no_preset_question():
    question = {
        'id': uuid4(),
        'kind': KIND_SINGLE_CHOICE,
        'preset': None,
        'options': [{'value': 'low', 'label': 'Bajo', 'tier_value': 100}],
    }
    assert _budget_tier_summary([question], {}) is None


def test_urgency_summary_normalizes_to_known_levels():
    qid = uuid4()
    question = {
        'id': qid,
        'kind': KIND_SINGLE_CHOICE,
        'preset': PRESET_URGENCY_LEVEL,
        'options': [
            {'value': 'now', 'label': 'Ahora', 'urgency_normalized': 'emergency'},
            {'value': 'later', 'label': 'Después', 'urgency_normalized': 'low'},
            {'value': 'mid', 'label': 'Medio'},
        ],
    }
    assert _urgency_summary([question], {str(qid): 'now'})['level'] == 'emergency'
    assert _urgency_summary([question], {str(qid): 'later'})['level'] == 'low'
    # Unknown urgency_normalized falls back to 'normal'.
    assert _urgency_summary([question], {str(qid): 'mid'})['level'] == 'normal'


def test_vip_threshold_parses_dict_and_json_string():
    assert _vip_budget_threshold({'vip_budget_threshold': 800000}) == 800000.0
    assert (
        _vip_budget_threshold(json.dumps({'vip_budget_threshold': '1200000'}))
        == 1200000.0
    )
    assert _vip_budget_threshold(None) == 0.0
    assert _vip_budget_threshold({}) == 0.0
    assert _vip_budget_threshold('not json') == 0.0


def test_is_vip_compares_tier_value_against_threshold():
    summary = {'tier_label': 'Alto', 'tier_value': 1000000.0, 'option_value': 'h'}
    assert _is_vip(summary, 800000) is True
    assert _is_vip(summary, 1500000) is False
    assert _is_vip(None, 800000) is False
    # Threshold ≤ 0 disables VIP routing.
    assert _is_vip(summary, 0) is False


# ───── Completion path — FakeConn integration ──────────────────────────────


class FakeConn:
    def __init__(self, questions, *, notification_settings=None, existing_tag_id=None):
        self.questions = questions
        self.notification_settings = notification_settings or {}
        self.inserted_messages = []
        self.inserted_events = []
        self.contact_qualification = {}
        self.audit_actions = []
        self.tag_assignments = []
        self.existing_tag_id = existing_tag_id or uuid4()
        self._idempotency_seen: set[str] = set()

    async def fetch(self, query, *args):
        if 'from app.qualification_questions' in query:
            return self.questions
        return []

    async def fetchrow(self, query, *args):
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
        return None

    async def fetchval(self, query, *args):
        if 'select id from app.domain_events' in query and 'idempotency_key' in query:
            return 1 if args[1] in self._idempotency_seen else None
        if 'notification_settings from app.tenant_settings' in query:
            return self.notification_settings
        if 'select id from app.contact_tags' in query:
            return self.existing_tag_id
        return None

    async def execute(self, query, *args):
        if 'insert into app.domain_events' in query:
            payload = json.loads(args[3]) if len(args) >= 4 else {}
            self.inserted_events.append({
                'idempotency_key': args[2],
                'payload': payload,
            })
            self._idempotency_seen.add(args[2])
        elif 'insert into app.audit_logs' in query:
            self.audit_actions.append(args)
        elif 'insert into app.contact_tag_assignments' in query:
            self.tag_assignments.append({'tenant_id': args[0], 'contact_id': args[1], 'tag_id': args[2]})
        return None


def _conversation():
    return {'id': uuid4(), 'metadata': {}}


def _contact():
    return {'id': uuid4()}


def _inbound(body=None, interactive_id=None):
    payload = {'interactive_id': interactive_id} if interactive_id else {}
    return {'id': uuid4(), 'body_text': body, 'payload': payload}


def _budget_question():
    return {
        'id': uuid4(),
        'position': 0,
        'label': '¿Tu presupuesto?',
        'kind': KIND_SINGLE_CHOICE,
        'required': True,
        'preset': PRESET_BUDGET_TIER,
        'options': [
            {'value': 'low', 'label': '< $200k', 'tier_value': 200000},
            {'value': 'mid', 'label': '$200k–$800k', 'tier_value': 800000},
            {'value': 'high', 'label': '> $800k', 'tier_value': 1000000},
        ],
        'applies_to_service_ids': [],
    }


def _urgency_question():
    return {
        'id': uuid4(),
        'position': 0,
        'label': '¿Qué tan urgente?',
        'kind': KIND_SINGLE_CHOICE,
        'required': True,
        'preset': PRESET_URGENCY_LEVEL,
        'options': [
            {'value': 'now', 'label': 'Emergencia', 'urgency_normalized': 'emergency'},
            {'value': 'soon', 'label': 'Alta', 'urgency_normalized': 'high'},
            {'value': 'whenever', 'label': 'Normal', 'urgency_normalized': 'normal'},
        ],
        'applies_to_service_ids': [],
    }


def test_urgency_emergency_triggers_triage_handoff_signal():
    q = _urgency_question()
    qid = str(q['id'])
    conn = FakeConn(questions=[q])
    conv = _conversation()
    conv['metadata'] = {'qualification': {'answered': {}}}
    result = asyncio.run(
        maybe_run_qualification_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=conv,
            contact=_contact(),
            inbound_message=_inbound(interactive_id=f'{PREFIX_QUALIFY}:{qid}:now'),
            intent='book_appointment',
        )
    )
    assert result['action'] == 'qualification_completed'
    assert result['triage_handoff'] is True
    assert result['triage_reason'] == 'urgency_triage'
    assert result['urgency_level'] == 'emergency'
    # qualification_flow MUST NOT queue a wait message itself — the
    # orchestrator delivers it via _do_handoff so we never duplicate the
    # bot reply. Any bot reply queued here is a regression.
    waits = [m for m in conn.inserted_messages if m['payload'].get('qualification_step') == 'urgency_triage']
    assert waits == []


def test_urgency_emergency_short_circuits_remaining_required_questions():
    """P1: urgency=emergency answered first must escalate immediately,
    even if other required questions are still pending."""
    urgency_q = _urgency_question()
    follow_up = {
        'id': uuid4(),
        'position': 1,
        'label': '¿Cuál es tu motivo?',
        'kind': 'free_text',
        'required': True,
        'preset': None,
        'options': [],
        'applies_to_service_ids': [],
    }
    qid = str(urgency_q['id'])
    conn = FakeConn(questions=[urgency_q, follow_up])
    conv = _conversation()
    conv['metadata'] = {'qualification': {'answered': {}}}
    result = asyncio.run(
        maybe_run_qualification_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=conv,
            contact=_contact(),
            inbound_message=_inbound(interactive_id=f'{PREFIX_QUALIFY}:{qid}:now'),
            intent='book_appointment',
        )
    )
    # Must complete (with triage) without asking the follow-up question.
    assert result['action'] == 'qualification_completed'
    assert result['triage_handoff'] is True
    assert result['urgency_level'] == 'emergency'
    # No outbound message must be queued — the follow-up should NOT be presented.
    assert conn.inserted_messages == []


def test_urgency_normal_does_not_short_circuit_remaining_questions():
    """Regression guard for P1: non-urgent answers must still ask the
    remaining required questions instead of short-circuiting."""
    urgency_q = _urgency_question()
    follow_up = {
        'id': uuid4(),
        'position': 1,
        'label': '¿Cuál es tu motivo?',
        'kind': 'free_text',
        'required': True,
        'preset': None,
        'options': [],
        'applies_to_service_ids': [],
    }
    qid = str(urgency_q['id'])
    conn = FakeConn(questions=[urgency_q, follow_up])
    conv = _conversation()
    conv['metadata'] = {'qualification': {'answered': {}}}
    result = asyncio.run(
        maybe_run_qualification_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=conv,
            contact=_contact(),
            inbound_message=_inbound(interactive_id=f'{PREFIX_QUALIFY}:{qid}:whenever'),
            intent='book_appointment',
        )
    )
    # Flow asked the next question instead of completing.
    assert result['action'] == 'qualification_step_sent'
    assert len(conn.inserted_messages) == 1
    assert conn.inserted_messages[0]['body_text'] == '¿Cuál es tu motivo?'


def test_urgency_normal_does_not_trigger_triage():
    q = _urgency_question()
    qid = str(q['id'])
    conn = FakeConn(questions=[q])
    conv = _conversation()
    conv['metadata'] = {'qualification': {'answered': {}}}
    result = asyncio.run(
        maybe_run_qualification_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=conv,
            contact=_contact(),
            inbound_message=_inbound(interactive_id=f'{PREFIX_QUALIFY}:{qid}:whenever'),
            intent='book_appointment',
        )
    )
    assert result['action'] == 'qualification_completed'
    assert 'triage_handoff' not in result
    assert result['urgency_level'] == 'normal'


def test_high_budget_above_threshold_applies_vip_tag():
    q = _budget_question()
    qid = str(q['id'])
    conn = FakeConn(
        questions=[q],
        notification_settings={'vip_budget_threshold': 800000},
    )
    conv = _conversation()
    conv['metadata'] = {'qualification': {'answered': {}}}
    contact = _contact()
    result = asyncio.run(
        maybe_run_qualification_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=conv,
            contact=contact,
            inbound_message=_inbound(interactive_id=f'{PREFIX_QUALIFY}:{qid}:high'),
            intent='book_appointment',
        )
    )
    assert result['action'] == 'qualification_completed'
    assert result['vip'] is True
    assert result['budget_tier']['tier_value'] == 1000000.0
    assert len(conn.tag_assignments) == 1
    assert conn.tag_assignments[0]['contact_id'] == contact['id']


def test_low_budget_does_not_apply_vip_tag():
    q = _budget_question()
    qid = str(q['id'])
    conn = FakeConn(
        questions=[q],
        notification_settings={'vip_budget_threshold': 800000},
    )
    conv = _conversation()
    conv['metadata'] = {'qualification': {'answered': {}}}
    result = asyncio.run(
        maybe_run_qualification_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=conv,
            contact=_contact(),
            inbound_message=_inbound(interactive_id=f'{PREFIX_QUALIFY}:{qid}:low'),
            intent='book_appointment',
        )
    )
    assert result['action'] == 'qualification_completed'
    assert 'vip' not in result
    assert conn.tag_assignments == []


def test_zero_threshold_disables_vip_routing_even_for_high_budget():
    q = _budget_question()
    qid = str(q['id'])
    conn = FakeConn(
        questions=[q],
        notification_settings={'vip_budget_threshold': 0},
    )
    conv = _conversation()
    conv['metadata'] = {'qualification': {'answered': {}}}
    result = asyncio.run(
        maybe_run_qualification_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=conv,
            contact=_contact(),
            inbound_message=_inbound(interactive_id=f'{PREFIX_QUALIFY}:{qid}:high'),
            intent='book_appointment',
        )
    )
    assert result['action'] == 'qualification_completed'
    assert 'vip' not in result
    assert conn.tag_assignments == []


# ───── Orchestrator + admin panel wiring ───────────────────────────────────


def test_orchestrator_forwards_triage_handoff_to_do_handoff():
    src = ORCHESTRATOR.read_text()
    assert "qualification_result.get('triage_handoff')" in src
    assert "qualification_result.get('triage_reason')" in src
    assert 'urgency_triage' in src


def test_orchestrator_overrides_handoff_message_for_triage():
    """P2: avoid double bot reply on triage — qualification_flow no longer
    queues the wait message itself, so the orchestrator must override
    policy.handoff_message with URGENCY_WAIT_MESSAGE before calling
    _do_handoff."""
    src = ORCHESTRATOR.read_text()
    assert 'URGENCY_WAIT_MESSAGE' in src
    assert "'handoff_message': URGENCY_WAIT_MESSAGE" in src
    assert 'triage_policy = {**policy' in src


def test_qualification_flow_does_not_queue_urgency_wait_message():
    """P2 regression guard: ensure qualification_flow itself never queues a
    bot message on the triage path (the orchestrator owns that reply)."""
    src = Path('app/services/qualification_flow.py').read_text()
    assert "step='urgency_triage'" not in src
    assert "body_text=URGENCY_WAIT_MESSAGE" not in src


def test_qualification_panel_exposes_preset_buttons_and_normalized_fields():
    src = _tenant_setup_source()
    assert 'Insertar pregunta de presupuesto' in src
    assert 'Insertar pregunta de urgencia' in src
    assert "PRESET_BUDGET_TIER = 'budget_tier'" in src
    assert "PRESET_URGENCY_LEVEL = 'urgency_level'" in src
    assert 'tier_value' in src
    assert 'urgency_normalized' in src


def test_tenant_wizard_adds_vip_budget_threshold_input():
    src = _tenant_setup_source()
    assert 'vip_budget_threshold' in src
    assert 'Umbral VIP' in src


def test_operations_desk_shows_urgent_badge_and_sorts_to_top():
    src = _operations_desk_source()
    assert '🚨 Urgente' in src
    assert 'urgency_level' in src
    assert 'data-urgent' in src
    # Sorting logic: urgent items first.
    assert "['emergency', 'high'].includes" in src
