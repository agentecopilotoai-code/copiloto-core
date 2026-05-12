"""Static tests for TASK-0048 — funnel and campaign attribution."""

from pathlib import Path

API_ROUTES = Path('app/api/v1/routes.py')
CORE_API = Path('admin-panel/src/services/coreApi.js')
ANALYTICS_PANEL = Path('admin-panel/src/components/modules/analytics/AnalyticsPanel.jsx')
SCHEMA = Path('infra/postgres/01-schema.sql')
ATTRIBUTION_SERVICE = Path('app/services/campaign_attribution.py')
BOOKING_FLOW = Path('app/services/booking_flow.py')
SCHEMAS_PY = Path('app/api/v1/schemas.py')


def test_schema_creates_campaign_attributions_table():
    schema = SCHEMA.read_text()
    assert 'create table app.campaign_attributions (' in schema
    # Tenant-scoped FK composite keys.
    assert 'fk_campaign_attributions_tenant_campaign foreign key (tenant_id, campaign_id) references app.campaigns(tenant_id, id) on delete cascade' in schema
    assert 'fk_campaign_attributions_tenant_contact foreign key (tenant_id, contact_id) references app.contacts(tenant_id, id) on delete cascade' in schema
    assert 'fk_campaign_attributions_tenant_appointment foreign key (tenant_id, appointment_id) references app.appointments(tenant_id, id) on delete cascade' in schema
    # Single row per appointment.
    assert 'unique (tenant_id, appointment_id)' in schema
    # RLS enabled and policy seeded.
    assert 'alter table app.campaign_attributions enable row level security' in schema
    assert "'campaigns','campaign_attributions'" in schema


def test_schema_extends_campaigns_with_cost_and_window():
    schema = SCHEMA.read_text()
    assert 'cost_amount numeric(12,2)' in schema
    assert "cost_currency char(3) not null default 'COP'" in schema
    assert 'attribution_window_days int not null default 14' in schema
    assert 'check (attribution_window_days between 1 and 90)' in schema


def test_funnel_endpoint_registered_under_manager_role():
    source = API_ROUTES.read_text()
    assert "tenant_analytics_router = APIRouter(" in source
    assert "require_min_role('manager')" in source
    assert "@tenant_analytics_router.get('/analytics/funnel')" in source
    assert "@tenant_analytics_router.get('/analytics/campaigns')" in source


def test_funnel_query_covers_five_steps():
    source = API_ROUTES.read_text()
    # Five steps: leads, engaged, scheduled, completed, repeat_customers.
    assert 'with leads as (' in source
    assert 'engaged as (' in source
    assert 'scheduled as (' in source
    assert 'completed as (' in source
    assert 'repeat_customers as (' in source
    assert "having count(*) >= 2" in source
    # Channel breakdown.
    assert "coalesce(nullif(lead_source->>'channel', ''), 'unknown')" in source
    # Conversion percentages.
    assert 'conversion_from_previous_pct' in source
    assert 'conversion_from_top_pct' in source
    # 90-day repeat window.
    assert 'repeat_window_start = range_end - timedelta(days=90)' in source


def test_campaigns_endpoint_joins_attribution_and_revenue():
    source = API_ROUTES.read_text()
    # Attribution join.
    assert 'from app.campaign_attributions ca' in source
    assert 'join app.appointments a on a.tenant_id = ca.tenant_id' in source
    # Revenue from completed appointments only.
    assert "filter (where a.status = 'completed')" in source
    assert 'sum(s.price_amount)' in source
    assert 'app.service_catalog s' in source
    # Returns cost + ROI + attribution_window_days.
    assert 'cost_amount' in source
    assert 'roi_estimated' in source
    assert 'attribution_window_days' in source


def test_attribution_service_last_touch_within_window():
    svc = ATTRIBUTION_SERVICE.read_text()
    assert 'async def attribute_appointment(' in svc
    # Only delivered campaign messages within the campaign's window count.
    assert "m.direction='outbound'" in svc
    assert 'm.campaign_id is not null' in svc
    assert '(m.delivered_at is not null or m.sent_at is not null)' in svc
    assert "c.attribution_window_days * interval '1 day'" in svc
    # Last-touch: order by touch_at desc limit 1.
    assert 'order by touch_at desc' in svc
    assert 'limit 1' in svc
    # Idempotent insert (one attribution per appointment).
    assert 'on conflict (tenant_id, appointment_id) do update' in svc


def test_attribution_wired_into_appointment_creation_paths():
    # Both the ops endpoint and the bot booking flow attribute appointments.
    routes = API_ROUTES.read_text()
    assert 'from app.services.campaign_attribution import attribute_appointment' in routes
    assert 'await attribute_appointment(' in routes

    flow = BOOKING_FLOW.read_text()
    assert 'from app.services.campaign_attribution import attribute_appointment' in flow
    assert 'await attribute_appointment(' in flow


def test_campaign_schema_accepts_cost_and_window_overrides():
    schemas = SCHEMAS_PY.read_text()
    assert 'cost_amount: float | None' in schemas
    assert 'cost_currency: str | None' in schemas
    assert 'attribution_window_days: int | None' in schemas
    # Validators: window between 1 and 90.
    assert 'ge=1, le=90' in schemas


def test_core_api_exposes_funnel_and_campaigns_helpers():
    api = CORE_API.read_text()
    assert 'export function getAnalyticsFunnel' in api
    assert 'export function getAnalyticsCampaigns' in api
    assert "/analytics/funnel" in api
    assert "/analytics/campaigns" in api


def test_analytics_panel_registers_funnel_and_campaigns_subtabs():
    panel = ANALYTICS_PANEL.read_text()
    assert 'getAnalyticsFunnel' in panel
    assert 'getAnalyticsCampaigns' in panel
    # Sub-tabs and labels.
    assert "id: 'funnel'" in panel
    assert "id: 'campaigns'" in panel
    assert 'Funnel' in panel
    assert 'Campañas' in panel
    # Sub-views.
    assert 'function FunnelView(' in panel
    assert 'function CampaignsView(' in panel
    # Step labels shown on the funnel.
    assert 'Citas agendadas' in panel
    assert 'Citas completadas' in panel
    assert 'Clientes recurrentes' in panel
    # Campaign table shows ROI and revenue.
    assert 'ROI' in panel
    assert 'Ingreso atribuido' in panel


def test_create_campaign_persists_cost_and_window():
    source = API_ROUTES.read_text()
    # The insert must reference the new columns.
    assert 'cost_amount, cost_currency, attribution_window_days' in source
    # PATCH supports updating cost_amount nullable, cost_currency, window.
    assert "cost_amount=case when $11 then $12 else cost_amount end" in source
    assert "cost_currency=coalesce($13, cost_currency)" in source
    assert "attribution_window_days=coalesce($14, attribution_window_days)" in source


def test_campaign_projection_includes_new_columns():
    source = API_ROUTES.read_text()
    assert 'cost_amount, cost_currency, ' in source
    assert 'attribution_window_days' in source
