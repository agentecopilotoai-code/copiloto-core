from pathlib import Path

API_ROUTES = Path('app/api/v1/routes.py')
CORE_API = Path('admin-panel/src/services/coreApi.js')
ANALYTICS_PANEL = Path('admin-panel/src/components/modules/analytics/AnalyticsPanel.jsx')
MODULES = Path('admin-panel/src/data/modules.js')
ADMIN_LAYOUT = Path('admin-panel/src/app/ModuleContent.jsx')


def test_analytics_router_requires_manager_role():
    source = API_ROUTES.read_text()
    assert 'tenant_analytics_router = APIRouter(' in source
    assert "require_min_role('manager')" in source
    assert 'router.include_router(tenant_analytics_router)' in source


def test_analytics_endpoints_registered():
    source = API_ROUTES.read_text()
    assert "@tenant_analytics_router.get('/analytics/overview')" in source
    assert "@tenant_analytics_router.get('/analytics/conversations')" in source
    assert "@tenant_analytics_router.get('/analytics/appointments')" in source
    assert "@tenant_analytics_router.get('/analytics/contacts')" in source


def test_analytics_overview_computes_required_kpis():
    source = API_ROUTES.read_text()
    # Conversations: total + handoff rate.
    assert "count(*) filter (where status in ('open','waiting_user','waiting_agent'))" in source
    assert "handoff_rate_pct" in source
    # Appointments: created/confirmed/completed/cancelled/no_show + rate.
    assert "count(*) filter (where status = 'completed') as completed" in source
    assert "count(*) filter (where status = 'no_show') as no_shows" in source
    assert "no_show_rate_pct" in source
    # Revenue based on service_catalog.price_amount of completed appointments.
    assert "sum(s.price_amount)" in source
    assert "and a.status = 'completed'" in source
    # Feedback ratings.
    assert "from app.appointment_feedback" in source
    assert "avg(rating)" in source
    # Messages inbound/outbound.
    assert "count(*) filter (where direction = 'inbound') as inbound" in source
    assert "count(*) filter (where direction = 'outbound') as outbound" in source
    # Retention 90-day window.
    assert "timedelta(days=90)" in source
    assert "retention_rate_pct" in source


def test_analytics_conversations_returns_intents_and_evolution():
    source = API_ROUTES.read_text()
    assert "coalesce(current_intent, 'unknown') as intent" in source
    assert "avg_first_bot_response_seconds" in source
    assert "daily_evolution" in source
    assert "from app.messages" in source


def test_analytics_appointments_returns_services_and_weekday():
    source = API_ROUTES.read_text()
    assert "top_services" in source
    assert "no_shows_by_weekday" in source
    assert "extract(dow from starts_at)" in source


def test_analytics_contacts_returns_tags_and_optout():
    source = API_ROUTES.read_text()
    assert "from app.contact_tags t" in source
    assert "opt_out_rate_pct" in source
    assert "source_distribution" in source


def test_analytics_range_helper_defaults_to_30_days():
    source = API_ROUTES.read_text()
    assert 'def _resolve_analytics_range' in source
    # Default range is 30 days, expressed as today - 29 days inclusive.
    assert 'timedelta(days=29)' in source
    assert "from_date must be on or before to_date" in source


def test_core_api_exposes_analytics_helpers():
    api = CORE_API.read_text()
    assert 'export function getAnalyticsOverview' in api
    assert 'export function getAnalyticsConversations' in api
    assert 'export function getAnalyticsAppointments' in api
    assert 'export function getAnalyticsContacts' in api
    assert "/analytics/overview" in api
    assert "/analytics/conversations" in api
    assert "/analytics/appointments" in api
    assert "/analytics/contacts" in api


def test_analytics_panel_component_exists_and_registered():
    assert ANALYTICS_PANEL.exists(), 'AnalyticsPanel.jsx must exist'
    component = ANALYTICS_PANEL.read_text()
    assert 'export function AnalyticsPanel' in component
    assert 'getAnalyticsOverview' in component
    assert 'getAnalyticsConversations' in component
    assert 'getAnalyticsAppointments' in component
    assert 'getAnalyticsContacts' in component
    # Range presets 7/30/90/custom.
    assert "'7d'" in component
    assert "'30d'" in component
    assert "'90d'" in component
    assert "'custom'" in component
    # KPI cards.
    assert 'Tasa de no-show' in component
    assert 'Ingreso estimado' in component
    assert 'Calificación promedio' in component
    # Top intents and services tables.
    assert 'Top intenciones' in component
    assert 'Servicios más solicitados' in component


def test_analytics_module_registered_in_sidebar():
    modules = MODULES.read_text()
    assert "id: 'analytics'" in modules
    assert 'Analítica' in modules

    layout = ADMIN_LAYOUT.read_text()
    assert 'AnalyticsPanel' in layout
    assert "case 'analytics'" in layout
