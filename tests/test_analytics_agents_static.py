"""Static checks for TASK-0068 — KPIs de rendimiento por agente."""

from pathlib import Path

API_ROUTES = Path('app/api/v1/routes.py')
SCHEMA = Path('infra/postgres/01-schema.sql')
CORE_API = Path('admin-panel/src/services/coreApi.js')
ANALYTICS_PANEL = Path('admin-panel/src/components/modules/analytics/AnalyticsPanel.jsx')
AGENT_PERF = Path('admin-panel/src/components/modules/analytics/AgentPerformance.jsx')


def test_appointments_table_has_metadata_jsonb_column():
    schema = SCHEMA.read_text()
    appointments = schema.split('create table app.appointments')[1].split(');')[0]
    assert "metadata jsonb not null default '{}'::jsonb" in appointments, (
        'appointments.metadata jsonb column is required to persist closed_by_user_id'
    )
    assert "ix_appointments_closed_by" in schema, (
        'an index on (tenant_id, metadata->>closed_by_user_id) keeps the agent '
        'analytics query cheap'
    )


def test_create_appointment_persists_closed_by_user_id():
    source = API_ROUTES.read_text()
    create_block = source.split('@tenant_ops_router.post(\'/appointments\', status_code=201)')[1]
    create_block = create_block.split('@tenant_ops_router')[0]
    assert "current_user_id_from_request(request, conn)" in create_block
    assert "appointment_metadata['closed_by_user_id']" in create_block
    assert 'insert into app.appointments' in create_block
    assert 'metadata' in create_block.split('insert into app.appointments')[1].split('returning')[0]


def test_update_appointment_sets_closed_by_user_id_on_status_transitions():
    source = API_ROUTES.read_text()
    update_block = source.split('async def update_appointment(')[1]
    update_block = update_block.split('@tenant_ops_router')[0]
    assert "current_user_id_from_request(request, conn)" in update_block
    assert "next_status in {'confirmed', 'completed'}" in update_block
    assert "metadata_patch['closed_by_user_id']" in update_block
    assert 'metadata=metadata || $10::jsonb' in update_block


def test_analytics_agents_endpoint_is_registered():
    source = API_ROUTES.read_text()
    assert "@tenant_analytics_router.get('/analytics/agents')" in source
    assert 'async def analytics_agents(' in source


def test_analytics_agents_computes_required_metrics():
    source = API_ROUTES.read_text()
    block = source.split('async def analytics_agents(')[1]
    block = block.split('SEGMENT_PROJECTION')[0]
    # Only agents in this tenant.
    assert "app.user_tenant_roles r on r.user_id = u.id" in block
    assert "r.role = 'agent'" in block
    # Messages sent by the agent on the desk.
    assert "sender_actor_type = 'agent'" in block
    assert "direction = 'outbound'" in block
    # Handoffs accepted / resolved.
    assert "status in ('accepted','resolved')" in block
    assert "status = 'resolved'" in block
    # Average response time vs last customer inbound.
    assert "join lateral" in block
    assert "direction = 'inbound'" in block
    # Appointments closed by the agent + revenue attribution.
    assert "metadata->>'closed_by_user_id'" in block
    assert 'sum(s.price_amount)' in block
    # Feedback rating on those appointments.
    assert 'from app.appointment_feedback' in block
    assert 'avg(f.rating)' in block


def test_analytics_agents_returns_top_performer_and_totals():
    source = API_ROUTES.read_text()
    block = source.split('async def analytics_agents(')[1]
    block = block.split('SEGMENT_PROJECTION')[0]
    assert "'top_performer_user_id'" in block
    assert "'totals'" in block
    # Output items expose every documented field.
    for field in (
        'messages_sent',
        'handoffs_accepted',
        'handoffs_resolved',
        'avg_response_time_seconds',
        'appointments_confirmed',
        'revenue_attributed',
        'feedback_avg_rating',
    ):
        assert f"'{field}'" in block, f'field {field} missing from agent payload'


def test_core_api_exposes_get_analytics_agents():
    api = CORE_API.read_text()
    assert 'export function getAnalyticsAgents' in api
    assert '/analytics/agents' in api


def test_agent_performance_module_renders_required_columns():
    assert AGENT_PERF.exists(), 'AgentPerformance.jsx must exist'
    component = AGENT_PERF.read_text()
    assert 'export function AgentPerformance' in component
    assert 'getAnalyticsAgents' in component
    # Table columns + top performer badge.
    for label in (
        'Mensajes',
        'Handoffs aceptados',
        'Handoffs resueltos',
        'Tiempo medio respuesta',
        'Citas confirmadas',
        'Ingreso atribuido',
        'Rating',
        'top performer',
    ):
        assert label in component, f'expected the agents table to expose "{label}"'


def test_analytics_panel_registers_agents_subtab():
    panel = ANALYTICS_PANEL.read_text()
    assert "id: 'agents'" in panel
    assert 'AgentPerformance' in panel
    assert "activeTab === 'agents'" in panel
