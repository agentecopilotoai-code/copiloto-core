"""Static tests for TASK-0042 — Conversational qualification flow.

These tests verify:
- Schema additions (`qualification_questions` table, `contacts.qualification` column).
- The Pydantic schemas, FastAPI endpoints and audit actions registered.
- The `qualification_flow.py` state machine handles every kind of question,
  derives the recommended service, snapshots the contact, respects opt-out,
  ignores non-booking intents and is idempotent.
- `rag_orchestrator` calls the qualification flow before the booking flow.
- `booking_flow.maybe_run_booking_flow` accepts ``prefilled_service_id``.
- The admin panel ships the new tab, panel and core API helpers.
"""
import asyncio
import json
from pathlib import Path
from uuid import uuid4

from app.services import qualification_flow
from app.services.qualification_flow import (
    KIND_FREE_TEXT,
    KIND_MULTI_CHOICE,
    KIND_NUMBER,
    KIND_SINGLE_CHOICE,
    KIND_YES_NO,
    PREFIX_QUALIFY,
    _derive_recommended_service,
    _next_pending_question,
    _validate_text_reply,
    maybe_run_qualification_flow,
)


SCHEMA = Path('infra/postgres/01-schema.sql')
ROUTES = Path('app/api/v1/routes.py')
SCHEMAS = Path('app/api/v1/schemas.py')
ORCHESTRATOR = Path('app/services/rag_orchestrator.py')
BOOKING_FLOW = Path('app/services/booking_flow.py')
CORE_API = Path('admin-panel/src/services/coreApi.js')
TENANT_SETUP_FEATURE = Path('admin-panel/src/features/owner-admin/tenant-setup')


def _tenant_setup_source() -> str:
    return '\n'.join(p.read_text() for p in sorted(TENANT_SETUP_FEATURE.rglob('*.js*')))
# UI-007.3: the contacts module was split into a feature directory.
CONTACTS_FEATURE = Path('admin-panel/src/features/owner-admin/conversations-contacts')
OPERATIONS_DESK = Path('admin-panel/src/features/agente/inbox')


def _operations_desk_source() -> str:
    """Combined source of the Operación · Inbox feature dir (UI-009.1 split).

    OperationsDesk.jsx (2088 LOC) was split into features/agente/inbox/; the
    static assertions below run against the concatenated feature source.
    """
    return '\n'.join(p.read_text() for p in sorted(OPERATIONS_DESK.rglob('*.js*')))


def _contacts_feature_source() -> str:
    return '\n'.join(
        path.read_text() for path in sorted(CONTACTS_FEATURE.rglob('*.js*'))
    )


# ───── Schema additions ────────────────────────────────────────────────────


def test_schema_adds_qualification_questions_table():
    schema = SCHEMA.read_text()
    assert 'create table app.qualification_questions' in schema
    assert "check (kind in ('free_text','single_choice','multi_choice','yes_no','number'))" in schema
    assert "applies_to_service_ids uuid[] not null default '{}'" in schema
    assert (
        'alter table app.qualification_questions '
        'add constraint uq_qualification_questions_tenant_id_id unique (tenant_id, id)'
    ) in schema
    assert 'trg_qualification_questions_touch' in schema
    assert 'alter table app.qualification_questions enable row level security' in schema
    assert "'qualification_questions'," in schema


def test_schema_adds_qualification_column_to_contacts():
    schema = SCHEMA.read_text()
    assert "qualification jsonb not null default '{}'::jsonb" in schema


# ───── Pydantic schemas and endpoints ──────────────────────────────────────


def test_qualification_schemas_constrain_kinds():
    source = SCHEMAS.read_text()
    assert 'QUALIFICATION_QUESTION_KINDS' in source
    for kind in ('free_text', 'single_choice', 'multi_choice', 'yes_no', 'number'):
        assert kind in source
    assert 'class QualificationQuestionCreate(BaseModel)' in source
    assert 'class QualificationQuestionUpdate(BaseModel)' in source
    assert 'class QualificationReorderRequest(BaseModel)' in source


def test_qualification_endpoints_are_registered():
    source = ROUTES.read_text()
    assert "@tenant_catalog_router.get('/tenants/{tenant_id}/qualification-questions')" in source
    assert (
        "@tenant_admin_router.post(\n"
        "    '/tenants/{tenant_id}/qualification-questions', status_code=201\n"
        ')'
    ) in source
    assert (
        "@tenant_admin_router.patch(\n"
        "    '/tenants/{tenant_id}/qualification-questions/{question_id}'\n"
        ')'
    ) in source
    assert (
        "@tenant_admin_router.delete(\n"
        "    '/tenants/{tenant_id}/qualification-questions/{question_id}',"
    ) in source
    assert (
        "@tenant_admin_router.post('/tenants/{tenant_id}/qualification-questions/reorder')"
    ) in source


def test_qualification_endpoints_emit_audit_actions():
    source = ROUTES.read_text()
    for action in (
        'qualification.created',
        'qualification.updated',
        'qualification.deleted',
        'qualification.reordered',
    ):
        assert action in source


def test_contact_profile_returns_qualification_answers():
    source = ROUTES.read_text()
    assert "'qualification_questions': [" in source
    assert "'qualification_answers': raw_qualification" in source


# ───── Orchestrator + booking integration ──────────────────────────────────


def test_orchestrator_calls_qualification_before_booking():
    source = ORCHESTRATOR.read_text()
    idx_q = source.find('maybe_run_qualification_flow(')
    idx_b = source.find('maybe_run_booking_flow(')
    assert idx_q != -1 and idx_b != -1
    assert idx_q < idx_b, 'qualification flow must run before booking flow'
    assert "qualification_result.get('action') == 'qualification_completed'" in source
    assert 'prefilled_service_id=prefilled_service_id' in source


def test_booking_flow_accepts_prefilled_service_id():
    source = BOOKING_FLOW.read_text()
    assert 'prefilled_service_id: str | None = None' in source
    # Prefilled service still drives the package/branch/resource chain. The
    # surrounding gating (``new_state is None and ...``) lets the referrer
    # question (TASK-0055) run first when the tenant opted in.
    assert 'prefilled_service_id:' in source
    assert "selected_service_id" in source


# ───── State machine — helpers ──────────────────────────────────────────────


def test_validate_text_reply_accepts_number_for_number_kind():
    q = {'kind': KIND_NUMBER}
    assert _validate_text_reply(q, '3') == 3.0
    assert _validate_text_reply(q, '3,5') == 3.5
    assert _validate_text_reply(q, 'no es un número') is None


def test_validate_text_reply_returns_text_for_free_text():
    q = {'kind': KIND_FREE_TEXT}
    assert _validate_text_reply(q, '  Hola  ') == 'Hola'
    assert _validate_text_reply(q, '   ') is None


def test_next_pending_question_skips_already_answered():
    questions = [
        {'id': 'q1', 'kind': KIND_YES_NO, 'required': True},
        {'id': 'q2', 'kind': KIND_FREE_TEXT, 'required': True},
    ]
    assert _next_pending_question(questions, {})['id'] == 'q1'
    assert _next_pending_question(questions, {'q1': True})['id'] == 'q2'
    assert _next_pending_question(questions, {'q1': True, 'q2': 'algo'}) is None


def test_derive_recommended_service_uses_single_choice_with_service_id():
    qid = str(uuid4())
    service_id = str(uuid4())
    questions = [
        {
            'id': qid,
            'kind': KIND_SINGLE_CHOICE,
            'options': [
                {'value': 'first', 'label': 'Primera vez', 'service_id': service_id},
                {'value': 'returning', 'label': 'Recurrente'},
            ],
        }
    ]
    assert _derive_recommended_service(questions, {qid: 'first'}) == service_id
    assert _derive_recommended_service(questions, {qid: 'returning'}) is None


def test_derive_recommended_service_ignores_non_single_choice():
    qid = str(uuid4())
    questions = [
        {
            'id': qid,
            'kind': KIND_YES_NO,
            'options': [{'value': 'yes', 'label': 'Sí', 'service_id': str(uuid4())}],
        }
    ]
    assert _derive_recommended_service(questions, {qid: True}) is None


# ───── State machine — FakeConn driven scenarios ────────────────────────────


class FakeConn:
    def __init__(self, questions, *, contact_qualification=None):
        self.questions = questions
        self.inserted_messages = []
        self.inserted_events = []
        self.contact_qualification = contact_qualification or {}
        self.audit_actions = []
        self.executed = []
        self._idempotency_seen: set[str] = set()

    async def fetch(self, query, *args):
        if 'from app.qualification_questions' in query and 'order by position' in query:
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
        if 'insert into app.audit_logs' in query:
            return {'id': 1}
        return None

    async def fetchval(self, query, *args):
        if 'select id from app.domain_events' in query and 'idempotency_key' in query:
            return 1 if args[1] in self._idempotency_seen else None
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
        else:
            self.executed.append((query, args))
        return None


def _question(kind, label='?', options=None, required=True, position=0):
    return {
        'id': uuid4(),
        'position': position,
        'label': label,
        'kind': kind,
        'options': options or [],
        'required': required,
        'applies_to_service_ids': [],
    }


def _conversation():
    return {'id': uuid4(), 'metadata': {}}


def _contact():
    return {'id': uuid4()}


def _inbound(body=None, interactive_id=None):
    payload = {'interactive_id': interactive_id} if interactive_id else {}
    return {
        'id': uuid4(),
        'body_text': body,
        'payload': payload,
    }


def test_qualification_skips_when_no_questions_configured():
    conn = FakeConn(questions=[])
    result = asyncio.run(
        maybe_run_qualification_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=_conversation(),
            contact=_contact(),
            inbound_message=_inbound(body='hola'),
            intent='book_appointment',
        )
    )
    assert result is None
    assert conn.inserted_messages == []


def test_qualification_does_not_start_outside_booking_intents():
    questions = [_question(KIND_YES_NO, label='¿Primera vez?')]
    conn = FakeConn(questions=questions)
    result = asyncio.run(
        maybe_run_qualification_flow(
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


def test_qualification_starts_on_book_appointment_and_sends_first_question():
    q = _question(KIND_YES_NO, label='¿Primera vez?')
    conn = FakeConn(questions=[q])
    result = asyncio.run(
        maybe_run_qualification_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=_conversation(),
            contact=_contact(),
            inbound_message=_inbound(body='quiero una cita'),
            intent='book_appointment',
        )
    )
    assert result is not None
    assert result['action'] == 'qualification_step_sent'
    assert len(conn.inserted_messages) == 1
    sent = conn.inserted_messages[0]
    assert sent['body_text'] == '¿Primera vez?'
    assert sent['payload']['qualification_step'].startswith('q:')


def test_qualification_completes_and_returns_recommended_service():
    service_id = str(uuid4())
    q = _question(
        KIND_SINGLE_CHOICE,
        label='¿Qué necesitas?',
        options=[
            {'value': 'valoracion', 'label': 'Valoración', 'service_id': service_id},
            {'value': 'control', 'label': 'Control'},
        ],
    )
    qid = str(q['id'])

    # Drive the flow: first, intent='book_appointment' presents the question.
    conn = FakeConn(questions=[q])
    conv = _conversation()
    contact = _contact()
    first = asyncio.run(
        maybe_run_qualification_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=conv,
            contact=contact,
            inbound_message=_inbound(body='quiero una cita'),
            intent='book_appointment',
        )
    )
    assert first['action'] == 'qualification_step_sent'

    # Mid-flow: user clicks the "Valoración" option.
    conv['metadata'] = {'qualification': {'answered': {}}}
    second = asyncio.run(
        maybe_run_qualification_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=conv,
            contact=contact,
            inbound_message=_inbound(
                interactive_id=f'{PREFIX_QUALIFY}:{qid}:valoracion'
            ),
            intent='book_appointment',
        )
    )
    assert second['action'] == 'qualification_completed'
    assert second['recommended_service_id'] == service_id
    assert second['answered'][qid] == 'valoracion'
    # An audit log was queued for the completion.
    assert conn.audit_actions, 'qualification.answered must be audited'


def test_qualification_opt_out_aborts_flow_when_mid_flow():
    q = _question(KIND_FREE_TEXT, label='Cuéntame el motivo')
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
            inbound_message=_inbound(body='stop'),
            intent='book_appointment',
        )
    )
    assert result == {'action': 'qualification_aborted', 'reason': 'opt_out'}


def test_qualification_idempotency_skips_replays_of_same_message():
    q = _question(KIND_YES_NO, label='¿Primera vez?')
    conn = FakeConn(questions=[q])
    # Pre-populate idempotency: the orchestrator already processed this inbound.
    inbound = _inbound(body='quiero una cita')
    conn._idempotency_seen.add(f'qualification_flow:{inbound["id"]}')
    result = asyncio.run(
        maybe_run_qualification_flow(
            conn,
            tenant_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            conversation=_conversation(),
            contact=_contact(),
            inbound_message=inbound,
            intent='book_appointment',
        )
    )
    assert result == {'action': 'skipped', 'reason': 'already_processed'}


def test_qualification_invalid_number_re_presents_same_question():
    q = _question(KIND_NUMBER, label='¿Cuántas veces?')
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
            inbound_message=_inbound(body='no sé'),
            intent='book_appointment',
        )
    )
    assert result['action'] == 'qualification_step_sent'
    assert result.get('retry') is True


# ───── Admin panel wiring ───────────────────────────────────────────────────


def test_core_api_exposes_qualification_helpers():
    source = CORE_API.read_text()
    for fn in (
        'listQualificationQuestions',
        'createQualificationQuestion',
        'updateQualificationQuestion',
        'deleteQualificationQuestion',
        'reorderQualificationQuestions',
    ):
        assert f'export function {fn}' in source


def test_tenant_setup_wizard_registers_calificacion_tab():
    source = _tenant_setup_source()
    assert "{ id: 'calificacion', label: 'Calificación' }," in source
    assert "activeTab === 'calificacion'" in source
    assert 'QualificationQuestionsPanel' in source


def test_qualification_panel_component_exists_and_uses_drag_handles():
    source = _tenant_setup_source()
    assert 'export default function QualificationQuestionsPanel' in source
    for fn in (
        'createQualificationQuestion',
        'updateQualificationQuestion',
        'deleteQualificationQuestion',
        'reorderQualificationQuestions',
        'listQualificationQuestions',
    ):
        assert fn in source
    # Drag-handle controls (up/down arrows) per the backlog requirement.
    assert 'drag-handle' in source


def test_contacts_module_renders_qualification_answers():
    source = _contacts_feature_source()
    assert 'qualification_questions' in source
    assert 'qualification_answers' in source


def test_operations_desk_shows_qualification_metadata():
    source = _operations_desk_source()
    assert 'Calificación previa' in source
    assert 'qualification' in source


# ───── Sanity: every kind constant aligns with schema ───────────────────────


def test_kind_constants_match_schema_check():
    schema = SCHEMA.read_text()
    expected = {KIND_FREE_TEXT, KIND_SINGLE_CHOICE, KIND_MULTI_CHOICE, KIND_YES_NO, KIND_NUMBER}
    # The schema's check constraint lists each kind exactly once.
    for kind in expected:
        assert f"'{kind}'" in schema
    assert qualification_flow.DONE_TOKEN == 'done'
    assert qualification_flow.PREFIX_QUALIFY == 'qualify'
