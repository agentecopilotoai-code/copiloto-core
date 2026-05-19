import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest

from app.services.whatsapp import (
    build_template_message_payload,
    build_whatsapp_message_payload,
    template_components_for_meta,
)
from app.workers.scheduler import (
    _extract_purpose,
    _has_approved_template,
    _process_pending_reminder_jobs,
)
from tests._routes_aggregator import routes_aggregated_source

SCHEMA = Path('infra/postgres/01-schema.sql')
SCHEMAS = Path('app/api/v1/schemas.py')
WHATSAPP = Path('app/services/whatsapp.py')
EVENT_WORKER = Path('app/workers/event_worker.py')
SCHEDULER = Path('app/workers/scheduler.py')
CORE_API = Path('admin-panel/src/services/coreApi.js')
# UI-007.8: the WhatsApp module was redesigned into a feature directory.
WHATSAPP_FEATURE = Path('admin-panel/src/features/owner-admin/whatsapp')


def _whatsapp_feature_source() -> str:
    return '\n'.join(
        path.read_text() for path in sorted(WHATSAPP_FEATURE.rglob('*.js*'))
    )


# ───── Pure helpers (template payload + Meta normalization) ─────


def test_build_template_message_payload_with_ordered_variables():
    block = build_template_message_payload(
        'appointment_confirmation',
        'es',
        variables={'1': 'María', '2': '12/06', '3': '10:00'},
    )
    assert block['name'] == 'appointment_confirmation'
    assert block['language'] == {'code': 'es'}
    parameters = block['components'][0]['parameters']
    assert [p['text'] for p in parameters] == ['María', '12/06', '10:00']
    assert all(p['type'] == 'text' for p in parameters)


def test_build_template_message_payload_explicit_components_override():
    custom = [{'type': 'header', 'parameters': [{'type': 'text', 'text': 'Hola'}]}]
    block = build_template_message_payload(
        'reminder', 'es', components=custom, variables={'1': 'ignored'}
    )
    assert block['components'] == custom


def test_build_template_message_payload_requires_name():
    with pytest.raises(ValueError):
        build_template_message_payload('', 'es')


def test_build_whatsapp_message_payload_wraps_template_block():
    block = build_template_message_payload('foo', 'es', variables={'1': 'a'})
    payload = build_whatsapp_message_payload(
        to='+573001112222', message_type='template', template_payload=block,
    )
    assert payload == {
        'messaging_product': 'whatsapp',
        'to': '+573001112222',
        'type': 'template',
        'template': block,
    }


def test_build_whatsapp_message_payload_requires_template_dict():
    with pytest.raises(ValueError):
        build_whatsapp_message_payload(to='+573001112222', message_type='template')


def test_template_components_for_meta_handles_object_form():
    out = template_components_for_meta({
        'header': {'text': 'Recordatorio'},
        'body': {'text': 'Hola {{1}}, tu cita es el {{2}}'},
        'footer': {'text': 'Equipo'},
        'buttons': [
            {'type': 'quick_reply', 'text': 'Confirmar'},
            {'type': 'quick_reply', 'text': 'Reagendar'},
        ],
    })
    types = [item['type'] for item in out]
    assert types == ['HEADER', 'BODY', 'FOOTER', 'BUTTONS']
    assert out[-1]['buttons'][0]['text'] == 'Confirmar'


def test_template_components_for_meta_passes_through_list():
    payload = [{'type': 'BODY', 'text': 'Hola'}]
    assert template_components_for_meta(payload) == payload


# ───── Scheduler gate ─────


class FakeScheduledConn:
    def __init__(self, jobs, approved_purposes=()):
        self.jobs = list(jobs)
        self.approved_purposes = set(approved_purposes)
        self.failed = []
        self.events = []
        self.sent = []

    async def fetch(self, _query):
        rows = self.jobs
        self.jobs = []
        return rows

    async def fetchval(self, query, *args):
        if 'whatsapp_templates' in query:
            _tenant_id, purpose = args
            return 1 if purpose in self.approved_purposes else None
        return None

    async def execute(self, query, *args):
        if 'status=\'failed\'' in query:
            self.failed.append({'id': args[0], 'error': args[1]})
        elif 'insert into app.domain_events' in query:
            self.events.append(args)
        elif 'set status=\'sent\'' in query:
            self.sent.append(args[0])


def _make_job(purpose: str | None, job_id: str | None = None) -> dict:
    payload = {'purpose': purpose} if purpose else {}
    return {
        'id': job_id or str(uuid4()),
        'tenant_id': str(uuid4()),
        'payload': payload,
    }


def test_scheduler_fails_jobs_without_approved_template():
    job = _make_job('appointment_confirmation', job_id='job-1')
    conn = FakeScheduledConn([job], approved_purposes=())
    asyncio.run(_process_pending_reminder_jobs(conn))
    assert conn.failed == [{'id': 'job-1', 'error': 'template_not_approved:appointment_confirmation'}]
    assert conn.sent == []
    assert conn.events == []


def test_scheduler_enqueues_when_template_approved():
    job = _make_job('appointment_reminder_24h', job_id='job-2')
    conn = FakeScheduledConn([job], approved_purposes=('appointment_reminder_24h',))
    asyncio.run(_process_pending_reminder_jobs(conn))
    assert conn.failed == []
    assert conn.sent == ['job-2']
    assert len(conn.events) == 1


def test_scheduler_allows_jobs_without_purpose():
    job = _make_job(None, job_id='job-3')
    conn = FakeScheduledConn([job], approved_purposes=())
    asyncio.run(_process_pending_reminder_jobs(conn))
    assert conn.failed == []
    assert conn.sent == ['job-3']


def test_extract_purpose_accepts_string_and_dict():
    assert _extract_purpose({'purpose': 'x'}) == 'x'
    assert _extract_purpose(json.dumps({'purpose': 'y'})) == 'y'
    assert _extract_purpose({'other': 'nope'}) is None
    assert _extract_purpose(None) is None


# ───── Static surface checks ─────


def test_schema_creates_whatsapp_templates_table():
    schema = SCHEMA.read_text()
    assert 'create table app.whatsapp_templates (' in schema
    assert "category text not null check (category in ('utility','marketing','authentication'))" in schema
    assert "status text not null default 'draft' check (status in ('draft','pending','approved','rejected','paused'))" in schema
    assert "'appointment_confirmation','appointment_reminder_24h','appointment_reminder_1h'" in schema
    assert 'unique (tenant_id, name, locale)' in schema
    assert "'whatsapp_templates'" in schema  # listed in RLS do-block
    assert 'alter table app.whatsapp_templates enable row level security' in schema
    assert 'trg_whatsapp_templates_touch' in schema
    assert 'uq_whatsapp_templates_tenant_id_id' in schema


def test_pydantic_schemas_for_templates_are_exported():
    schemas = SCHEMAS.read_text()
    assert 'class WhatsAppTemplateCreate(BaseModel):' in schemas
    assert 'class WhatsAppTemplateUpdate(BaseModel):' in schemas
    assert 'WHATSAPP_TEMPLATE_PURPOSES = (' in schemas
    assert "'appointment_confirmation'" in schemas
    assert "pattern='^(utility|marketing|authentication)$'" in schemas


def test_template_endpoints_registered_with_audit():
    source = routes_aggregated_source()
    assert "@tenant_admin_router.post('/tenants/{tenant_id}/whatsapp/templates', status_code=201)" in source
    assert "@tenant_admin_router.get('/tenants/{tenant_id}/whatsapp/templates')" in source
    assert "@tenant_admin_router.get('/tenants/{tenant_id}/whatsapp/templates/{template_id}')" in source
    assert "@tenant_admin_router.patch('/tenants/{tenant_id}/whatsapp/templates/{template_id}')" in source
    assert "@tenant_admin_router.post('/tenants/{tenant_id}/whatsapp/templates/sync')" in source
    assert "@tenant_admin_router.delete('/tenants/{tenant_id}/whatsapp/templates/{template_id}', status_code=204)" in source
    assert "action='whatsapp_template.created'" in source
    assert "action='whatsapp_template.synced'" in source
    assert "action='whatsapp_template.deleted'" in source
    assert 'WHATSAPP_TEMPLATE_REQUIRED_PURPOSES' in source


def test_readiness_check_for_minimum_templates():
    source = routes_aggregated_source()
    assert "'whatsapp_templates'" in source
    assert "Plantillas mínimas aprobadas" in source
    assert 'WHATSAPP_TEMPLATE_REQUIRED_PURPOSES' in source


def test_whatsapp_module_exports_template_helpers():
    source = WHATSAPP.read_text()
    assert "SUPPORTED_OUTBOUND_MESSAGE_TYPES = {'text', 'interactive', 'template', *MEDIA_MESSAGE_TYPES}" in source
    assert 'def build_template_message_payload(' in source
    assert 'async def send_whatsapp_template(' in source
    assert 'async def submit_template_to_meta(' in source
    assert 'async def fetch_templates_from_meta(' in source
    assert 'async def delete_template_from_meta(' in source
    assert 'def template_components_for_meta(' in source


def test_event_worker_forwards_template_payload():
    source = EVENT_WORKER.read_text()
    assert "message_payload.get('template')" in source


def test_scheduler_template_gate_is_enforced():
    source = SCHEDULER.read_text()
    assert 'def _extract_purpose' in source
    assert 'def _has_approved_template' in source
    assert "where tenant_id=$1 and purpose=$2 and status='approved'" in source
    assert "template_not_approved" in source
    assert "set status='failed'" in source


def test_admin_client_exposes_template_helpers():
    source = CORE_API.read_text()
    assert 'export function listWhatsappTemplates' in source
    assert 'export function createWhatsappTemplate' in source
    assert 'export function updateWhatsappTemplate' in source
    assert 'export function deleteWhatsappTemplate' in source
    assert 'export function syncWhatsappTemplates' in source


def test_whatsapp_onboarding_renders_templates_section():
    source = _whatsapp_feature_source()
    assert 'TEMPLATE_PURPOSES' in source
    assert 'TEMPLATE_STATUS_LABEL' in source
    assert 'Plantillas de mensajes' in source
    assert 'Sincronizar estado con Meta' in source
    assert 'templates-semaphore' in source
    assert 'handleCreateTemplate' in source
    assert 'handleSyncTemplates' in source
    assert 'handleDeleteTemplate' in source
    assert 'templateComponentsFromForm' in source


# Helper kept to ensure the test exercises the helper without DB.
def test_has_approved_template_helper_uses_status_filter():
    async def runner():
        conn = FakeScheduledConn([], approved_purposes=('appointment_confirmation',))
        assert await _has_approved_template(conn, 'tenant-x', 'appointment_confirmation') is True
        assert await _has_approved_template(conn, 'tenant-x', 'campaign_promo') is False

    asyncio.run(runner())
