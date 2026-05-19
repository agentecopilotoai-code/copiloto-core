"""Static tests for TASK-0052 — Recall automático por servicio tras completar.

Coverage:
- Schema: ``service_catalog.recall_interval_days`` and
  ``service_catalog.recall_template_id`` columns, FK to ``whatsapp_templates``,
  ``service_recall`` purpose enum entry, idempotency unique index on
  ``reminder_jobs``.
- Triggers: completion fires a ``service_recall`` reminder_job at
  ``ends_at + interval``, no-op when ``recall_interval_days`` is null, and
  rebooking the same service for the same contact cancels pending recalls.
- Pydantic schemas: ``ServiceCreate``/``ServiceUpdate`` expose
  ``recall_interval_days`` and ``recall_template_id``, and
  ``WHATSAPP_TEMPLATE_PURPOSES`` includes ``service_recall``.
- Routes: ``create_service`` and ``update_service`` persist the new columns,
  ``SERVICE_CATALOG_COLUMNS`` exposes them in selects, and ``update_service``
  uses a "_set" flag so the recall can be cleared back to null.
- Scheduler: ``_mark_conversation_pending_recall`` writes
  ``metadata.pending_recall`` only when payload carries both
  ``service_id`` and ``conversation_id``.
- Orchestrator: ``_pending_recall_service_id`` reads the marker and the main
  flow uses it as ``prefilled_service_id`` before booking_flow.
- Admin Panel: ``ServiceCatalog.jsx`` renders the recall interval input, the
  template picker, the preview helper and loads only approved
  ``service_recall`` templates.
"""
from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from uuid import uuid4

from app.api.v1 import routes as routes_module
from app.api.v1.schemas import (
    WHATSAPP_TEMPLATE_PURPOSES,
    ServiceCreate,
    ServiceUpdate,
)
from app.services import rag_orchestrator
from app.workers import scheduler as scheduler_module
from app.workers.scheduler import (
    _coerce_payload_dict,
    _extract_purpose,
    _mark_conversation_pending_recall,
)
from tests._routes_aggregator import routes_aggregated_source

SCHEMA = Path('infra/postgres/01-schema.sql')
SCHEDULER = Path('app/workers/scheduler.py')
ORCHESTRATOR = Path('app/services/rag_orchestrator.py')
# UI-007.4: the ServiceCatalog monolith was split into a feature directory.
SERVICES_FEATURE = Path('admin-panel/src/features/owner-admin/services')
CORE_API = Path('admin-panel/src/services/coreApi.js')


def _services_feature_source() -> str:
    return '\n'.join(
        path.read_text() for path in sorted(SERVICES_FEATURE.rglob('*.js*'))
    )


# ───── Schema ─────


def test_schema_adds_recall_columns_to_service_catalog():
    schema = SCHEMA.read_text()
    assert 'recall_interval_days int check (recall_interval_days is null or recall_interval_days > 0)' in schema
    assert 'recall_template_id uuid' in schema
    assert 'fk_service_catalog_tenant_recall_template' in schema
    # FK targets whatsapp_templates via the tenant-scoped composite PK.
    assert (
        'foreign key (tenant_id, recall_template_id)\n'
        '    references app.whatsapp_templates(tenant_id, id) on delete set null'
    ) in schema


def test_schema_extends_whatsapp_purpose_check_with_service_recall():
    schema = SCHEMA.read_text()
    # TASK-0062 inserted 'consent_request','consent_reaffirm' between
    # 'service_recall' and 'custom' — keep the assertion focused on the
    # presence of the recall purpose.
    assert "'payment_request','service_recall'" in schema
    assert "'custom'" in schema


def test_schema_creates_idempotency_index_for_service_recall_jobs():
    schema = SCHEMA.read_text()
    # Partial unique index on (tenant_id, target_id) for active jobs only.
    assert 'ux_reminder_jobs_service_recall_appointment' in schema
    assert "(payload->>'purpose') = 'service_recall'" in schema
    assert "status in ('pending','processing')" in schema


def test_schema_completion_trigger_inserts_recall_job():
    schema = SCHEMA.read_text()
    assert 'create or replace function app.schedule_service_recall_on_completion()' in schema
    assert "if new.status <> 'completed' then" in schema
    assert "if old.status = 'completed' then" in schema
    assert 'svc.recall_interval_days' in schema
    assert "make_interval(days => svc.recall_interval_days)" in schema
    assert "'service_recall'" in schema
    assert 'trg_appointments_schedule_service_recall' in schema
    assert 'on conflict do nothing' in schema


def test_schema_rebook_trigger_cancels_pending_recalls():
    schema = SCHEMA.read_text()
    assert 'create or replace function app.cancel_pending_recall_on_rebook()' in schema
    assert "rj.status in ('pending','processing')" in schema
    assert "(rj.payload->>'purpose') = 'service_recall'" in schema
    assert "(rj.payload->>'service_id') = new.service_id::text" in schema
    assert "(rj.payload->>'contact_id') = new.contact_id::text" in schema
    assert "rj.target_id <> new.id" in schema
    assert 'trg_appointments_cancel_recall_on_rebook' in schema


# ───── Pydantic schemas ─────


def test_service_create_accepts_recall_fields():
    template_id = uuid4()
    payload = ServiceCreate(
        name='Limpieza dental',
        recall_interval_days=180,
        recall_template_id=template_id,
    )
    assert payload.recall_interval_days == 180
    assert payload.recall_template_id == template_id


def test_service_create_recall_defaults_to_none():
    payload = ServiceCreate(name='Sin recall')
    assert payload.recall_interval_days is None
    assert payload.recall_template_id is None


def test_service_update_recall_supports_partial_changes():
    template_id = uuid4()
    payload = ServiceUpdate(recall_interval_days=90)
    dumped = payload.model_dump(exclude_unset=True)
    assert dumped == {'recall_interval_days': 90}
    payload2 = ServiceUpdate(recall_template_id=template_id)
    dumped2 = payload2.model_dump(exclude_unset=True)
    assert dumped2 == {'recall_template_id': template_id}


def test_template_purpose_enum_includes_service_recall():
    assert 'service_recall' in WHATSAPP_TEMPLATE_PURPOSES


# ───── Routes ─────


def test_service_catalog_projection_exposes_recall_columns():
    assert 'recall_interval_days' in routes_module.SERVICE_CATALOG_COLUMNS
    assert 'recall_template_id' in routes_module.SERVICE_CATALOG_COLUMNS
    assert 'recall_interval_days' in routes_module.SERVICE_CATALOG_PROJECTION
    assert 'recall_template_id' in routes_module.SERVICE_CATALOG_PROJECTION


def test_create_service_route_passes_recall_columns():
    src = routes_aggregated_source()
    # The insert must include both columns and bind the payload values.
    assert 'recall_interval_days, recall_template_id,' in src
    assert 'payload.recall_interval_days,' in src
    assert 'payload.recall_template_id,' in src


def test_update_service_route_uses_set_flags_to_allow_clearing():
    src = routes_aggregated_source()
    assert "recall_days_set = 'recall_interval_days' in update_data" in src
    assert "recall_template_set = 'recall_template_id' in update_data" in src
    assert 'recall_interval_days = case when $14::boolean then $15 else recall_interval_days end' in src
    assert 'recall_template_id   = case when $16::boolean then $17 else recall_template_id end' in src


# ───── Scheduler ─────


class _FakeConn:
    def __init__(self):
        self.executed = []

    async def execute(self, query, *args):
        self.executed.append((query, args))


def test_mark_conversation_pending_recall_writes_metadata():
    tenant_id = uuid4()
    conversation_id = uuid4()
    service_id = uuid4()
    appointment_id = uuid4()
    payload = {
        'purpose': 'service_recall',
        'service_id': str(service_id),
        'conversation_id': str(conversation_id),
        'appointment_id': str(appointment_id),
    }
    conn = _FakeConn()
    asyncio.run(
        _mark_conversation_pending_recall(
            conn,
            tenant_id=tenant_id,
            payload=payload,
        )
    )
    assert len(conn.executed) == 1
    query, args = conn.executed[0]
    assert 'pending_recall' in query
    assert 'jsonb_set' in query
    assert args[0] == tenant_id
    assert args[1] == str(conversation_id)
    assert args[2] == str(service_id)
    assert args[3] == str(appointment_id)


def test_mark_conversation_pending_recall_noop_without_conversation():
    payload = {'purpose': 'service_recall', 'service_id': str(uuid4())}
    conn = _FakeConn()
    asyncio.run(
        _mark_conversation_pending_recall(conn, tenant_id=uuid4(), payload=payload)
    )
    assert conn.executed == []


def test_scheduler_recognizes_service_recall_purpose():
    """``_extract_purpose`` works for service_recall jobs (string + dict)."""
    assert _extract_purpose({'purpose': 'service_recall'}) == 'service_recall'
    assert _extract_purpose(json.dumps({'purpose': 'service_recall'})) == 'service_recall'
    assert _coerce_payload_dict('not-json') is None
    assert _coerce_payload_dict({'a': 1}) == {'a': 1}


def test_scheduler_calls_mark_pending_recall_for_service_recall_jobs():
    src = SCHEDULER.read_text()
    assert "if purpose == 'service_recall':" in src
    assert '_mark_conversation_pending_recall(' in src
    # The existing template gate must still apply: no opt-out for service_recall.
    assert "if purpose and not await _has_approved_template" in src


# ───── Orchestrator ─────


def test_orchestrator_reads_pending_recall_marker_from_conversation():
    service_id = str(uuid4())
    conversation = {
        'metadata': {
            'pending_recall': {
                'service_id': service_id,
                'appointment_id': str(uuid4()),
            }
        }
    }
    assert rag_orchestrator._pending_recall_service_id(conversation) == service_id
    # JSON-string metadata is also accepted because the rest of the codebase
    # serializes ``metadata`` as text in some paths.
    serialized = {'metadata': json.dumps(conversation['metadata'])}
    assert rag_orchestrator._pending_recall_service_id(serialized) == service_id
    # Without a marker we return None so the orchestrator falls back to its
    # normal flow.
    assert rag_orchestrator._pending_recall_service_id({'metadata': {}}) is None
    assert rag_orchestrator._pending_recall_service_id({}) is None


def test_orchestrator_uses_pending_recall_as_prefilled_service_id():
    src = ORCHESTRATOR.read_text()
    assert 'pending_recall_service_id = _pending_recall_service_id(conversation)' in src
    assert 'prefilled_service_id = pending_recall_service_id' in src
    assert '_clear_pending_recall(conn, tenant_id, conversation[\'id\'])' in src


def test_orchestrator_clear_pending_recall_drops_jsonb_key():
    src = ORCHESTRATOR.read_text()
    assert "(coalesce(metadata, '{}'::jsonb)) - 'pending_recall'" in src


# ───── Admin Panel ─────


def test_admin_panel_service_catalog_imports_template_listing():
    src = _services_feature_source()
    assert 'listWhatsappTemplates' in src
    assert "purpose: 'service_recall'" in src
    assert "status: 'approved'" in src


def test_admin_panel_service_catalog_renders_recall_inputs():
    src = _services_feature_source()
    assert 'Recordatorio de control cada N días' in src
    assert 'Plantilla del recordatorio' in src
    assert 'formatRecallPreview' in src
    # Preview should mention the projected send date.
    assert 'dispararía el recordatorio el' in src


def test_admin_panel_service_catalog_payload_handles_empty_recall():
    src = _services_feature_source()
    # Empty string or non-positive numbers must clear the recall.
    assert 'recall_interval_days: recallDays' in src
    assert 'recall_template_id: form.recall_template_id || null' in src


def test_admin_panel_service_catalog_disables_template_picker_without_interval():
    src = _services_feature_source()
    assert 'disabled={!form.recall_interval_days}' in src


# ───── Wiring sanity ─────


def test_extract_purpose_module_is_reused_for_scheduling():
    # The helper that the scheduler uses to read the payload purpose must come
    # from the same module that owns the recall-specific branch — otherwise
    # the gate and the marker could disagree if either is refactored later.
    assert inspect.getmodule(_extract_purpose) is scheduler_module
    assert inspect.getmodule(_mark_conversation_pending_recall) is scheduler_module
