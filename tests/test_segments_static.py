"""Static and unit checks for TASK-0047 — contact segments.

Covers:
  * DB schema: ``app.contact_segments``, ``app.contact_segment_members``,
    new ``campaigns.segment_id`` / ``campaigns.launched_snapshot_at`` columns,
    RLS and tenant guards.
  * Seed file pre-populates the 5 preconstructed segments per tenant.
  * ``app.services.segments`` rule builder: whitelist of fields/ops,
    parameter binding, ``all_of`` / ``any_of`` combinators, qualification
    keys, snapshot helper.
  * Tenant creation seeds the preconstructed segments through the service.
  * API endpoints registered with the correct router.
  * Scheduler invokes the hourly refresh.
  * Campaigns dispatch resolves recipients from the snapshot when
    ``segment_id`` and ``launched_snapshot_at`` are present.
  * Admin Panel module + coreApi helpers exist and Layout/Modules wire
    the new "Segmentos" entry.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from app.services import segments as segments_service
from app.services.campaigns import _resolve_campaign_recipients
from app.services.segments import (
    PRECONSTRUCTED_SEGMENTS,
    build_segment_query,
    normalize_rules,
    seed_preconstructed_segments,
)

SCHEMA = Path('infra/postgres/01-schema.sql')
SEED = Path('infra/postgres/02-seed.sql')
API_ROUTES = Path('app/api/v1/routes.py')
API_SCHEMAS = Path('app/api/v1/schemas.py')
SEGMENTS_SERVICE = Path('app/services/segments.py')
CAMPAIGNS_SERVICE = Path('app/services/campaigns.py')
SCHEDULER = Path('app/workers/scheduler.py')
CORE_API = Path('admin-panel/src/services/coreApi.js')
MODULES = Path('admin-panel/src/app/modules.js')
ADMIN_LAYOUT = Path('admin-panel/src/app/moduleRegistry.js')
SEGMENTS_FEATURE = Path('admin-panel/src/features/manager/segments')
CAMPAIGNS_FEATURE = Path('admin-panel/src/features/manager/campaigns')


def _campaigns_feature_source() -> str:
    """Combined source of the Manager · Campañas feature directory.

    UI-008.2 split the legacy ``CampaignsModule.jsx`` into a feature dir;
    the segment-picker literals are spread across the hook + the form
    drawer component, so we read them as one blob.
    """
    return '\n'.join(p.read_text() for p in sorted(CAMPAIGNS_FEATURE.rglob('*.js*')))


def _segments_feature_source() -> str:
    """Combined source of the Manager · Segmentos feature directory.

    UI-008.3 split the legacy ``SegmentsModule.jsx`` into a feature dir;
    the ``listContactSegments`` / ``previewContactSegment`` /
    ``refreshContactSegment`` literals live in the hook while
    ``export function SegmentsModule`` lives in the orchestrator, so we
    read them as one blob.
    """
    return '\n'.join(p.read_text() for p in sorted(SEGMENTS_FEATURE.rglob('*.js*')))


# ───── Schema ─────


def test_schema_creates_contact_segments_table_with_rls():
    schema = SCHEMA.read_text()
    assert 'create table app.contact_segments (' in schema
    assert (
        "kind text not null default 'dynamic' check (kind in ('dynamic','static'))"
        in schema
    )
    assert "rules jsonb not null default '{}'::jsonb" in schema
    assert 'contact_count int not null default 0' in schema
    assert 'last_refreshed_at timestamptz' in schema
    assert 'is_system boolean not null default false' in schema
    assert 'unique (tenant_id, name)' in schema
    assert 'alter table app.contact_segments enable row level security' in schema
    assert 'uq_contact_segments_tenant_id_id' in schema
    assert 'trg_contact_segments_touch' in schema
    assert "'contact_segments'" in schema


def test_schema_creates_contact_segment_members_with_composite_pk():
    schema = SCHEMA.read_text()
    assert 'create table app.contact_segment_members (' in schema
    assert 'primary key (segment_id, contact_id, snapshot_at)' in schema
    assert (
        'alter table app.contact_segment_members enable row level security' in schema
    )
    assert 'fk_contact_segment_members_tenant_segment' in schema
    assert 'fk_contact_segment_members_tenant_contact' in schema
    assert "'contact_segment_members'" in schema


def test_campaigns_table_gains_segment_columns():
    schema = SCHEMA.read_text()
    # segment_id y launched_snapshot_at viven inline en el CREATE TABLE de
    # app.campaigns; no se agregan como ALTER TABLE incremental porque el MVP
    # no está en producción y el esquema se aplica una sola vez.
    assert 'alter table app.campaigns add column segment_id' not in schema
    assert 'alter table app.campaigns add column launched_snapshot_at' not in schema
    create_block_start = schema.index('create table app.campaigns')
    create_block_end = schema.index(');', create_block_start)
    create_block = schema[create_block_start:create_block_end]
    assert 'segment_id uuid' in create_block
    assert 'launched_snapshot_at timestamptz' in create_block
    assert 'fk_campaigns_tenant_segment' in schema


def test_seed_inserts_preconstructed_segments_for_demo_tenants():
    seed = SEED.read_text()
    assert 'insert into app.contact_segments' in seed
    for segment in PRECONSTRUCTED_SEGMENTS:
        assert segment['name'] in seed


# ───── Service: rule builder ─────


def test_normalize_rules_drops_unknown_field():
    result = normalize_rules({'all_of': [{'field': 'evil', 'op': 'eq', 'value': 1}]})
    assert result == {'all_of': []}


def test_normalize_rules_keeps_only_whitelisted_operators():
    result = normalize_rules(
        {
            'all_of': [
                {'field': 'total_spent', 'op': 'gt', 'value': 1000},
                {'field': 'total_spent', 'op': 'like', 'value': 'x'},
            ]
        }
    )
    assert len(result['all_of']) == 1
    assert result['all_of'][0]['op'] == 'gt'


def test_normalize_rules_supports_qualification_namespace():
    result = normalize_rules(
        {'any_of': [{'field': 'qualification.motivo', 'op': 'eq', 'value': 'corte'}]}
    )
    assert result == {
        'any_of': [{'field': 'qualification.motivo', 'op': 'eq', 'value': 'corte'}]
    }


def test_normalize_rules_rejects_bad_qualification_key():
    result = normalize_rules(
        {'all_of': [{'field': 'qualification.bad key!', 'op': 'eq', 'value': 'x'}]}
    )
    assert result == {'all_of': []}


def test_normalize_rules_handles_string_json():
    text = json.dumps({'all_of': [{'field': 'tags', 'op': 'contains_any', 'value': ['vip']}]})
    result = normalize_rules(text)
    assert result['all_of'][0]['field'] == 'tags'


def test_build_segment_query_returns_tenant_filter_and_opt_in_guard():
    sql, args = build_segment_query({})
    assert 'c.tenant_id = $1' in sql
    assert "c.opt_in_status not in ('revoked','suppressed')" in sql
    assert 'c.phone_e164 is not null' in sql
    assert args == [None]


def test_build_segment_query_emits_lt_days_ago_for_dates():
    sql, args = build_segment_query(
        {'all_of': [{'field': 'last_appointment_at', 'op': 'lt_days_ago', 'value': 60}]}
    )
    assert "interval '1 day'" in sql
    assert '< now()' in sql
    assert args == [None, 60]


def test_build_segment_query_combines_any_of_with_or():
    sql, _args = build_segment_query(
        {
            'any_of': [
                {'field': 'total_appointments_completed', 'op': 'gte', 'value': 3},
                {'field': 'total_spent', 'op': 'gt', 'value': 500000},
            ]
        }
    )
    assert ') or (' in sql


def test_build_segment_query_supports_contains_any_on_tags():
    sql, args = build_segment_query(
        {'all_of': [{'field': 'tags', 'op': 'contains_any', 'value': ['vip', 'frecuente']}]}
    )
    assert 'c.tags && $2::text[]' in sql
    assert args[1] == ['vip', 'frecuente']


def test_build_segment_query_supports_qualification_key():
    sql, args = build_segment_query(
        {'all_of': [{'field': 'qualification.motivo', 'op': 'eq', 'value': 'corte'}]}
    )
    assert "c.qualification->>'motivo'" in sql
    assert args[1] == 'corte'


def test_build_segment_query_ignores_unsafe_qualification_key():
    sql, args = build_segment_query(
        {'all_of': [{'field': "qualification.evil'; drop", 'op': 'eq', 'value': 'x'}]}
    )
    # Bad key → no condition emitted → only tenant placeholder remains.
    assert "qualification->>'evil'" not in sql
    assert args == [None]


def test_build_segment_query_emits_is_null_for_dates():
    sql, _args = build_segment_query(
        {'all_of': [{'field': 'last_appointment_at', 'op': 'is_null'}]}
    )
    assert 'is null' in sql


# ───── Preconstructed seeds ─────


def test_preconstructed_segments_have_five_definitions():
    assert len(PRECONSTRUCTED_SEGMENTS) == 5
    names = {s['name'] for s in PRECONSTRUCTED_SEGMENTS}
    assert 'Sin visita en 60+ días' in names
    assert 'Clientes recurrentes (3+ citas)' in names
    assert 'VIP (gasto > $500.000)' in names
    assert 'Primer contacto sin agendar' in names
    assert 'No-show reciente (30 días)' in names


class FakeSeedConn:
    def __init__(self) -> None:
        self.inserted: list[dict] = []

    async def fetchrow(self, _query: str, *args):
        tenant_id, name, description, rules_json, created_by = args
        self.inserted.append(
            {
                'tenant_id': tenant_id,
                'name': name,
                'description': description,
                'rules': json.loads(rules_json),
                'created_by': created_by,
            }
        )
        return {'id': uuid4()}


def test_seed_preconstructed_segments_inserts_five_rows():
    conn = FakeSeedConn()
    tenant_id = uuid4()
    inserted = asyncio.run(seed_preconstructed_segments(conn, tenant_id))
    assert inserted == 5
    assert all(item['tenant_id'] == tenant_id for item in conn.inserted)
    # Every seed contains a normalized rules object.
    for item in conn.inserted:
        assert 'all_of' in item['rules']


# ───── Campaign dispatch resolves snapshot ─────


def test_resolve_campaign_recipients_prefers_snapshot_when_segment_id_present():
    expected_rows = [
        {
            'id': uuid4(),
            'wa_id': 'wa1',
            'phone_e164': '+57300',
            'display_name': 'Cliente A',
            'opt_in_status': 'granted',
        }
    ]
    snapshot_at = 'snapshot-1'
    segment_id = uuid4()

    class Conn:
        def __init__(self) -> None:
            self.captured = None

        async def fetch(self, query: str, *args):
            self.captured = (query, args)
            assert 'app.contact_segment_members' in query
            return expected_rows

    conn = Conn()
    tenant_id = uuid4()
    campaign = {
        'segment_id': segment_id,
        'launched_snapshot_at': snapshot_at,
        'segment_filter': {},
    }
    rows = asyncio.run(_resolve_campaign_recipients(conn, tenant_id, campaign))
    assert rows == expected_rows
    assert conn.captured[1] == (tenant_id, segment_id, snapshot_at)


def test_resolve_campaign_recipients_falls_back_to_segment_filter():
    """Without segment_id/snapshot_at the legacy live query runs."""
    legacy_called = {}

    async def fake_evaluate(conn, tenant_id, segment_filter):
        legacy_called['segment_filter'] = segment_filter
        return [{'id': uuid4()}]

    from app.services import campaigns as campaigns_module

    real = campaigns_module.evaluate_segment
    campaigns_module.evaluate_segment = fake_evaluate  # type: ignore
    try:
        result = asyncio.run(
            _resolve_campaign_recipients(
                object(),
                uuid4(),
                {'segment_filter': {'min_appointments': 1}},
            )
        )
    finally:
        campaigns_module.evaluate_segment = real  # type: ignore
    assert legacy_called == {'segment_filter': {'min_appointments': 1}}
    assert len(result) == 1


# ───── API surface ─────


def test_segments_endpoints_registered():
    source = API_ROUTES.read_text()
    assert "@tenant_admin_router.get('/tenants/{tenant_id}/segments')" in source
    assert "@tenant_admin_router.post('/tenants/{tenant_id}/segments', status_code=201)" in source
    assert "@tenant_admin_router.get('/tenants/{tenant_id}/segments/{segment_id}')" in source
    assert "@tenant_admin_router.patch('/tenants/{tenant_id}/segments/{segment_id}')" in source
    assert "@tenant_admin_router.delete(" in source and 'segments/{segment_id}' in source
    assert "@tenant_admin_router.get('/tenants/{tenant_id}/segments/{segment_id}/preview')" in source
    assert "@tenant_admin_router.post('/tenants/{tenant_id}/segments/{segment_id}/refresh')" in source


def test_segments_routes_audit_actions():
    source = API_ROUTES.read_text()
    assert "action='segment.created'" in source
    assert "action='segment.updated'" in source
    assert "action='segment.deleted'" in source
    assert "action='segment.refreshed'" in source


def test_tenant_creation_seeds_preconstructed_segments():
    source = API_ROUTES.read_text()
    assert 'seed_preconstructed_segments(conn, tenant_id)' in source
    # Both the admin-side create_tenant and self-service create paths seed.
    assert source.count('seed_preconstructed_segments(') >= 2


def test_segment_schemas_in_pydantic_module():
    source = API_SCHEMAS.read_text()
    assert 'class ContactSegmentCreate(BaseModel):' in source
    assert 'class ContactSegmentUpdate(BaseModel):' in source
    assert 'class ContactSegmentMembersAssign(BaseModel):' in source
    assert 'SEGMENT_KIND_PATTERN' in source


def test_campaign_pydantic_models_accept_segment_id():
    source = API_SCHEMAS.read_text()
    assert 'segment_id: UUID | None = None' in source


# ───── Scheduler ─────


def test_scheduler_refreshes_segments_in_loop():
    source = SCHEDULER.read_text()
    assert 'from app.services.segments import refresh_due_segments' in source
    assert 'await refresh_due_segments(conn)' in source


def test_segments_service_public_api():
    source = SEGMENTS_SERVICE.read_text()
    assert 'def build_segment_query(' in source
    assert 'async def evaluate_segment_rules(' in source
    assert 'async def count_segment_contacts(' in source
    assert 'async def snapshot_segment_members(' in source
    assert 'async def refresh_due_segments(' in source
    assert 'async def seed_preconstructed_segments(' in source
    assert 'PRECONSTRUCTED_SEGMENTS' in source


def test_segments_module_exposes_refresh_default_interval():
    # Default refresh window is 1h per TASK-0047 acceptance criteria.
    defaults = segments_service.refresh_due_segments.__kwdefaults__ or {}
    interval = defaults.get('interval')
    assert interval is not None
    assert interval.total_seconds() == 3600


# ───── Campaigns service integration ─────


def test_campaigns_service_resolves_recipients_via_snapshot_helper():
    source = CAMPAIGNS_SERVICE.read_text()
    assert 'async def _resolve_campaign_recipients(' in source
    assert 'await _resolve_campaign_recipients(' in source
    assert 'launched_snapshot_at' in source


# ───── Admin Panel ─────


def test_admin_client_exposes_segment_helpers():
    source = CORE_API.read_text()
    assert 'export function listContactSegments' in source
    assert 'export function createContactSegment' in source
    assert 'export function updateContactSegment' in source
    assert 'export function deleteContactSegment' in source
    assert 'export function previewContactSegment' in source
    assert 'export function refreshContactSegment' in source


def test_modules_register_segments_entry():
    source = MODULES.read_text()
    assert "id: 'segments'" in source
    assert "label: 'Segmentos'" in source
    # UI-005: minRole → capability de la matriz de permisos (manager/admin/owner
    # tienen segments.write=RW).
    assert "capability: 'segments.write'" in source


def test_admin_layout_renders_segments_module():
    source = ADMIN_LAYOUT.read_text()
    assert 'SegmentsModule' in source
    assert 'segments: {' in source


def test_segments_module_exists():
    source = _segments_feature_source()
    assert 'export function SegmentsModule' in source
    assert 'listContactSegments' in source
    assert 'previewContactSegment' in source
    assert 'refreshContactSegment' in source


def test_campaigns_module_uses_segment_picker():
    source = _campaigns_feature_source()
    assert 'listContactSegments' in source
    assert 'segment_id' in source
    assert 'Segmento guardado' in source
