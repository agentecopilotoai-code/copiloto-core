"""Static surface checks + functional tests for the campaigns module.

TASK-0038 ships:
  * ``app.campaigns`` table with RLS and tenant-scoped FKs.
  * Endpoints under ``/v1/tenants/{tenant_id}/campaigns``.
  * Scheduler worker that picks up scheduled campaigns and enqueues
    template messages, respecting opt-out and rate limits.
  * Admin Panel module under ``components/modules/campaigns``.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

from app.services.campaigns import (
    DEFAULT_RATE_LIMIT_PER_SECOND,
    SUPPRESSED_OPT_IN_STATUSES,
    build_recipients_query,
    build_template_message_payload,
    coerce_dict,
    dispatch_campaign,
    enqueue_campaign_message,
    normalize_segment_filter,
    refresh_campaign_counters,
)

SCHEMA = Path('infra/postgres/01-schema.sql')
API_ROUTES = Path('app/api/v1/routes.py')
SCHEMAS = Path('app/api/v1/schemas.py')
CAMPAIGNS_SERVICE = Path('app/services/campaigns.py')
SCHEDULER = Path('app/workers/scheduler.py')
CORE_API = Path('admin-panel/src/services/coreApi.js')
CAMPAIGNS_FEATURE = Path('admin-panel/src/features/manager/campaigns')
MODULES = Path('admin-panel/src/app/modules.js')
ADMIN_LAYOUT = Path('admin-panel/src/app/moduleRegistry.js')


def _campaigns_feature_source() -> str:
    """Combined source of the Manager · Campañas feature directory.

    UI-008.2 split the legacy ``CampaignsModule.jsx`` into a feature dir;
    the static literals below are spread across the orchestrator, the hook
    and the components, so we read them as one blob.
    """
    return '\n'.join(p.read_text() for p in sorted(CAMPAIGNS_FEATURE.rglob('*.js*')))


# ───── Schema ─────


def test_schema_creates_campaigns_table_with_rls():
    schema = SCHEMA.read_text()
    assert 'create table app.campaigns (' in schema
    assert 'tenant_id uuid not null references app.tenants(id) on delete cascade' in schema
    assert (
        "status text not null default 'draft' check (status in ('draft','scheduled','running','completed','cancelled'))"
        in schema
    )
    assert 'template_id uuid references app.whatsapp_templates(id) on delete restrict' in schema
    assert "template_variables jsonb not null default '{}'::jsonb" in schema
    assert "segment_filter jsonb not null default '{}'::jsonb" in schema
    assert 'recipient_count int not null default 0' in schema
    assert 'sent_count int not null default 0' in schema
    assert 'delivered_count int not null default 0' in schema
    assert 'read_count int not null default 0' in schema
    assert 'failed_count int not null default 0' in schema
    assert 'alter table app.campaigns enable row level security' in schema
    assert 'uq_campaigns_tenant_id_id' in schema
    assert 'fk_campaigns_tenant_template' in schema
    assert "'campaigns'" in schema
    assert 'trg_campaigns_touch' in schema


def test_messages_table_links_to_campaign():
    schema = SCHEMA.read_text()
    assert 'campaign_id uuid' in schema
    assert 'fk_messages_tenant_campaign' in schema
    assert 'ix_messages_tenant_campaign' in schema


# ───── Pydantic / segment normalization ─────


def test_normalize_segment_filter_drops_unknown_keys():
    raw = {
        'tags': [str(uuid4()), 'not-a-uuid'],
        'min_appointments': '3',
        'last_visit_before_days': 30,
        'last_visit_after_days': -1,  # invalid → dropped
        'has_upcoming_appointment': True,
        'evil_field': 'x',
    }
    result = normalize_segment_filter(raw)
    assert 'evil_field' not in result
    assert 'last_visit_after_days' not in result
    assert result['min_appointments'] == 3
    assert result['has_upcoming_appointment'] is True
    assert len(result['tags']) == 1


def test_normalize_segment_filter_handles_string_json():
    raw = json.dumps({'min_appointments': 5})
    result = normalize_segment_filter(raw)
    assert result == {'min_appointments': 5}


def test_normalize_segment_filter_returns_empty_for_garbage():
    assert normalize_segment_filter(None) == {}
    assert normalize_segment_filter(42) == {}
    assert normalize_segment_filter('not-json') == {}


def test_coerce_dict_passthrough_json_string():
    assert coerce_dict('{"a": 1}') == {'a': 1}
    assert coerce_dict({'a': 1}) == {'a': 1}
    assert coerce_dict(None) == {}


def test_suppressed_statuses_match_contact_check_values():
    schema = SCHEMA.read_text()
    for status in SUPPRESSED_OPT_IN_STATUSES:
        assert f"'{status}'" in schema


# ───── Recipients query ─────


def test_build_recipients_query_excludes_suppressed_and_revoked():
    sql, args = build_recipients_query({})
    assert "opt_in_status not in ('revoked','suppressed')" in sql
    assert 'c.tenant_id = $1' in sql
    # The args list pre-allocates one slot for tenant_id (filled later).
    assert args == [None]


def test_build_recipients_query_filters_by_tags():
    tag_id = str(uuid4())
    sql, args = build_recipients_query({'tags': [tag_id]})
    assert 'contact_tag_assignments' in sql
    assert 'cta.tag_id = any($2::uuid[])' in sql
    assert args[1] == [tag_id]


def test_build_recipients_query_filters_by_min_appointments():
    sql, args = build_recipients_query({'min_appointments': 3})
    assert 'count(*) from app.appointments' in sql
    assert ') >= $2' in sql
    assert args[1] == 3


def test_build_recipients_query_filters_by_last_visit_window():
    sql_before, args_before = build_recipients_query({'last_visit_before_days': 90})
    assert "interval '1 day'" in sql_before
    assert '<= now()' in sql_before
    assert args_before[1] == 90

    sql_after, args_after = build_recipients_query({'last_visit_after_days': 7})
    assert '>= now()' in sql_after
    assert args_after[1] == 7


def test_build_recipients_query_filters_upcoming_appointment_both_directions():
    sql_has, _ = build_recipients_query({'has_upcoming_appointment': True})
    assert 'exists' in sql_has
    assert "status in ('scheduled','confirmed')" in sql_has

    sql_none, _ = build_recipients_query({'has_upcoming_appointment': False})
    assert 'not exists' in sql_none


# ───── Template payload ─────


def test_build_template_message_payload_orders_numeric_variables():
    payload = build_template_message_payload(
        'campaign_promo_es',
        'es_CO',
        {'2': 'Promo', '1': 'María', '10': 'Junio'},
    )
    assert payload['name'] == 'campaign_promo_es'
    assert payload['language']['code'] == 'es_CO'
    body = payload['components'][0]
    assert body['type'] == 'body'
    # ordering: 1, 2, 10
    assert [p['text'] for p in body['parameters']] == ['María', 'Promo', 'Junio']


def test_build_template_message_payload_without_variables_omits_components():
    payload = build_template_message_payload('promo_es', 'es', None)
    assert 'components' not in payload


# ───── FakeConn for worker dispatch ─────


class FakeConn:
    """Minimal async stand-in for an asyncpg connection.

    Captures the inserted messages, conversations and domain events so the
    tests can verify the worker's behaviour without a real database.
    """

    def __init__(self, *, recipients, template):
        self.recipients = recipients
        self.template = template
        self.inserted_messages = []
        self.inserted_events = []
        self.created_conversations = []
        self.executed = []

    async def fetch(self, query, *args):
        if 'from app.contacts c' in query and 'order by c.created_at' in query:
            return self.recipients
        if 'update app.campaigns' in query and "status='running'" in query:
            return []
        return []

    async def fetchrow(self, query, *args):
        if 'select id, name, locale, status, channel_id' in query:
            return self.template
        if 'select t.channel_id as template_channel_id' in query:
            return {
                'template_channel_id': self.template['channel_id'],
                'status': self.template['status'],
                'channel_id': self.template['channel_id'],
                'account_mode': 'mock',
            }
        if 'from app.conversations' in query and 'order by updated_at desc' in query:
            # Force the worker to create a new conversation each time.
            return None
        if 'insert into app.conversations' in query:
            conversation_id = uuid4()
            self.created_conversations.append({
                'id': conversation_id,
                'tenant_id': args[0],
                'contact_id': args[1],
                'channel_id': args[2],
            })
            return {'id': conversation_id}
        if 'insert into app.messages' in query:
            message_id = uuid4()
            tenant_id, conversation_id, payload_json, campaign_id = args
            self.inserted_messages.append({
                'id': message_id,
                'tenant_id': tenant_id,
                'conversation_id': conversation_id,
                'payload': json.loads(payload_json),
                'campaign_id': campaign_id,
            })
            return {'id': message_id}
        return None

    async def fetchval(self, query, *args):
        return None

    async def execute(self, query, *args):
        if 'insert into app.domain_events' in query:
            self.inserted_events.append({
                'tenant_id': args[0],
                'aggregate_id': args[1],
                'idempotency_key': args[2],
                'payload': json.loads(args[3]),
            })
        else:
            self.executed.append((query, args))
        return None


def _recipient(opt_in='granted'):
    return {
        'id': uuid4(),
        'wa_id': '57300' + str(uuid4().int)[:7],
        'phone_e164': '+573001112233',
        'display_name': 'Cliente',
        'opt_in_status': opt_in,
    }


def test_enqueue_campaign_message_inserts_template_and_event():
    recipient = _recipient()
    template = {
        'id': uuid4(),
        'name': 'campaign_promo_es',
        'locale': 'es',
        'status': 'approved',
        'channel_id': uuid4(),
    }
    conn = FakeConn(recipients=[recipient], template=template)

    tenant_id = uuid4()
    campaign_id = uuid4()
    asyncio.run(
        enqueue_campaign_message(
            conn,
            tenant_id=tenant_id,
            campaign_id=campaign_id,
            contact_id=recipient['id'],
            channel_id=template['channel_id'],
            template_name=template['name'],
            template_locale=template['locale'],
            template_variables={'1': 'María'},
        )
    )

    assert len(conn.inserted_messages) == 1
    msg = conn.inserted_messages[0]
    assert msg['campaign_id'] == campaign_id
    assert msg['payload']['campaign_id'] == str(campaign_id)
    assert msg['payload']['template']['name'] == 'campaign_promo_es'

    assert len(conn.inserted_events) == 1
    event = conn.inserted_events[0]
    assert event['idempotency_key'].startswith(f'campaign:{campaign_id}:')
    assert event['payload']['campaign_id'] == str(campaign_id)


def test_dispatch_campaign_skips_when_template_not_approved():
    template = {
        'id': uuid4(),
        'name': 'campaign_promo_es',
        'locale': 'es',
        'status': 'pending',
        'channel_id': uuid4(),
    }
    conn = FakeConn(recipients=[_recipient(), _recipient()], template=template)
    campaign = {
        'id': uuid4(),
        'template_id': template['id'],
        'segment_filter': {},
        'template_variables': {},
    }
    result = asyncio.run(dispatch_campaign(conn, uuid4(), campaign))
    assert result['enqueued'] == 0
    assert 'template_not_approved' in result['error']
    assert conn.inserted_messages == []


def test_dispatch_campaign_enqueues_one_message_per_recipient():
    template = {
        'id': uuid4(),
        'name': 'campaign_promo_es',
        'locale': 'es',
        'status': 'approved',
        'channel_id': uuid4(),
    }
    recipients = [_recipient(), _recipient(), _recipient()]
    conn = FakeConn(recipients=recipients, template=template)
    campaign = {
        'id': uuid4(),
        'template_id': template['id'],
        'segment_filter': {},
        'template_variables': {'1': 'María'},
    }
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    result = asyncio.run(
        dispatch_campaign(
            conn,
            uuid4(),
            campaign,
            rate_limit_per_second=2,
            sleep_func=fake_sleep,
        )
    )
    assert result['enqueued'] == 3
    assert len(conn.inserted_messages) == 3
    # Rate limiter pauses after every 2 messages, so 3 messages → 1 pause.
    assert sleeps == [1.0]


def test_dispatch_campaign_returns_zero_when_no_channel():
    template = {
        'id': uuid4(),
        'name': 'campaign_promo_es',
        'locale': 'es',
        'status': 'approved',
        'channel_id': None,
    }

    class NoChannelConn(FakeConn):
        async def fetchrow(self, query, *args):
            if 'select t.channel_id as template_channel_id' in query:
                return {
                    'template_channel_id': None,
                    'status': 'approved',
                    'channel_id': None,
                    'account_mode': None,
                }
            return await super().fetchrow(query, *args)

    conn = NoChannelConn(recipients=[_recipient()], template=template)
    campaign = {
        'id': uuid4(),
        'template_id': template['id'],
        'segment_filter': {},
        'template_variables': {},
    }
    result = asyncio.run(dispatch_campaign(conn, uuid4(), campaign))
    assert result == {'enqueued': 0, 'error': 'channel_not_found'}


def test_refresh_campaign_counters_aggregates_messages():
    captured = {}

    class CountersConn:
        async def fetchrow(self, query, *args):
            assert 'count(*) filter (where status' in query
            return {
                'sent_count': 5,
                'delivered_count': 4,
                'read_count': 3,
                'failed_count': 1,
                'total': 5,
            }

        async def execute(self, query, *args):
            captured['args'] = args
            captured['query'] = query
            return None

    counters = asyncio.run(
        refresh_campaign_counters(CountersConn(), uuid4(), uuid4())
    )
    assert counters == {
        'sent_count': 5,
        'delivered_count': 4,
        'read_count': 3,
        'failed_count': 1,
        'total': 5,
    }
    assert 'update app.campaigns' in captured['query']
    assert captured['args'][2:6] == (5, 4, 3, 1)


# ───── Rate limit constant ─────


def test_default_rate_limit_matches_meta_recommendation():
    assert DEFAULT_RATE_LIMIT_PER_SECOND == 20


# ───── API surface ─────


def test_campaigns_endpoints_registered():
    source = API_ROUTES.read_text()
    assert "@tenant_admin_router.post('/tenants/{tenant_id}/campaigns', status_code=201)" in source
    assert "@tenant_admin_router.get('/tenants/{tenant_id}/campaigns')" in source
    assert "@tenant_admin_router.get('/tenants/{tenant_id}/campaigns/{campaign_id}')" in source
    assert "@tenant_admin_router.patch('/tenants/{tenant_id}/campaigns/{campaign_id}')" in source
    assert "@tenant_admin_router.post('/tenants/{tenant_id}/campaigns/{campaign_id}/preview')" in source
    assert "@tenant_admin_router.post('/tenants/{tenant_id}/campaigns/{campaign_id}/launch')" in source
    assert "@tenant_admin_router.post('/tenants/{tenant_id}/campaigns/{campaign_id}/cancel')" in source


def test_campaigns_routes_audit_actions():
    source = API_ROUTES.read_text()
    assert "action='campaign.created'" in source
    assert "action='campaign.launched'" in source
    assert "action='campaign.cancelled'" in source
    assert "action='campaign.updated'" in source


def test_campaigns_schema_module_exposes_pydantic_models():
    source = SCHEMAS.read_text()
    assert 'class CampaignCreate(BaseModel):' in source
    assert 'class CampaignUpdate(BaseModel):' in source
    assert 'class CampaignLaunch(BaseModel):' in source
    assert 'class CampaignSegmentFilter(BaseModel):' in source
    assert 'template_id: UUID' in source


def test_campaigns_service_public_api():
    source = CAMPAIGNS_SERVICE.read_text()
    assert 'async def evaluate_segment(' in source
    assert 'async def count_recipients(' in source
    assert 'async def dispatch_campaign(' in source
    assert 'async def process_due_campaigns(' in source
    assert 'async def refresh_campaign_counters(' in source
    assert 'DEFAULT_RATE_LIMIT_PER_SECOND' in source
    assert 'SUPPRESSED_OPT_IN_STATUSES' in source


def test_scheduler_processes_campaigns():
    source = SCHEDULER.read_text()
    assert 'from app.services.campaigns import process_due_campaigns' in source
    assert 'await process_due_campaigns(conn)' in source


# ───── Admin Panel ─────


def test_admin_client_exposes_campaign_helpers():
    source = CORE_API.read_text()
    assert 'export function listCampaigns' in source
    assert 'export function createCampaign' in source
    assert 'export function previewCampaign' in source
    assert 'export function launchCampaign' in source
    assert 'export function cancelCampaign' in source


def test_modules_register_campaigns_entry():
    source = MODULES.read_text()
    assert "id: 'campaigns'" in source
    assert "label: 'Campañas'" in source
    # UI-005: minRole → capability de la matriz de permisos.
    assert "capability: 'campaigns.write'" in source


def test_admin_layout_renders_campaigns_module():
    source = ADMIN_LAYOUT.read_text()
    assert 'CampaignsModule' in source
    assert 'campaigns: {' in source


def test_campaigns_module_exists():
    source = _campaigns_feature_source()
    assert 'export function CampaignsModule' in source
    assert 'listCampaigns' in source
    assert 'createCampaign' in source
    assert 'previewCampaign' in source
    assert 'launchCampaign' in source
