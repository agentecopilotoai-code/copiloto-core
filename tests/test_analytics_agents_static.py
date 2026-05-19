"""Static checks for TASK-0068 — KPIs de rendimiento por agente.

UI-016.3 refactorizó `AgentPerformance.jsx` al HTML del diseñador (`docs/HTML
DESIGN/Transversales/23b _ Negocio _ Rendimiento del equipo.html`) y movió el
markup de la tabla a la primitiva reutilizable
`features/manager/analytics/components/AgentPerformanceTable.jsx`. Las
aserciones que pinan las columnas ahora apuntan a esa primitiva, no al
contenedor.
"""

from pathlib import Path
from tests._routes_aggregator import routes_aggregated_source

SCHEMA = Path('infra/postgres/01-schema.sql')
CORE_API = Path('admin-panel/src/services/coreApi.js')
ANALYTICS_PANEL = Path('admin-panel/src/features/owner-admin/analytics/AnalyticsPanel.jsx')
AGENT_PERF = Path('admin-panel/src/features/owner-admin/analytics/AgentPerformance.jsx')
AGENT_TABLE = Path('admin-panel/src/features/manager/analytics/components/AgentPerformanceTable.jsx')


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
    source = routes_aggregated_source()
    create_block = source.split('@tenant_ops_router.post(\'/appointments\', status_code=201)')[1]
    create_block = create_block.split('@tenant_ops_router')[0]
    assert "current_user_id_from_request(request, conn)" in create_block
    assert "appointment_metadata['closed_by_user_id']" in create_block
    assert 'insert into app.appointments' in create_block
    assert 'metadata' in create_block.split('insert into app.appointments')[1].split('returning')[0]


def test_update_appointment_sets_closed_by_user_id_on_status_transitions():
    source = routes_aggregated_source()
    update_block = source.split('async def update_appointment(')[1]
    update_block = update_block.split('@tenant_ops_router')[0]
    assert "current_user_id_from_request(request, conn)" in update_block
    assert "next_status in {'confirmed', 'completed'}" in update_block
    assert "metadata_patch['closed_by_user_id']" in update_block
    assert 'metadata=metadata || $10::jsonb' in update_block


def test_analytics_agents_endpoint_is_registered():
    source = routes_aggregated_source()
    # BUG-171 (fix-group-30) movió el decorator a multi-línea para alojar
    # `dependencies=[Depends(require_min_role('manager'))]`. Validamos los
    # dos componentes (decorator path + handler name) en vez del match
    # literal de la línea completa.
    assert "@tenant_analytics_router.get(" in source
    assert "'/analytics/agents'" in source
    assert 'async def analytics_agents(' in source


def test_analytics_agents_computes_required_metrics():
    source = routes_aggregated_source()
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


def test_analytics_agents_never_casts_text_user_id_to_uuid():
    """``messages.sender_actor_id`` and ``metadata->>'closed_by_user_id'`` are
    free-form ``text``. Casting them directly to ``uuid`` blows up the whole
    endpoint as soon as a tenant has a non-UUID agent actor (e.g. the
    ``send_quote`` path uses ``request.state.actor_id`` which is the auth
    subject). The safe direction is to cast the agent's ``users.id`` (always
    a uuid) to text and join on text equality.
    """
    source = routes_aggregated_source()
    block = source.split('async def analytics_agents(')[1]
    block = block.split('SEGMENT_PROJECTION')[0]
    # No "<text col>::uuid = <uuid col>" join in the final select.
    assert 'ms.user_id::uuid' not in block
    assert 'rt.user_id::uuid' not in block
    assert 'ac.user_id::uuid' not in block
    assert 'fp.user_id::uuid' not in block
    # The safe direction (uuid → text) is used instead.
    assert 'ms.user_id = ag.user_id::text' in block
    assert 'rt.user_id = ag.user_id::text' in block
    assert 'ac.user_id = ag.user_id::text' in block
    assert 'fp.user_id = ag.user_id::text' in block


def test_analytics_agents_returns_top_performer_and_totals():
    source = routes_aggregated_source()
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


def test_agent_performance_module_consumes_endpoint_and_table_primitive():
    """The Owner/Admin "Rendimiento del equipo" container reads from
    `getAnalyticsAgents` and reuses the shared `AgentPerformanceTable` primitive
    (UI-016.3 — no duplicated markup with Manager analytics).
    """
    assert AGENT_PERF.exists(), 'AgentPerformance.jsx must exist'
    component = AGENT_PERF.read_text()
    assert 'export function AgentPerformance' in component
    assert 'getAnalyticsAgents' in component
    # Gating + shared primitive.
    assert 'RequirePermission' in component
    assert "capability=\"analytics.tenant.read\"" in component
    assert 'AgentPerformanceTable' in component
    # KPI strip + load distribution chart (the 23b mockup sections).
    assert 'AgentKpis' in component
    assert 'LoadDistribution' in component
    # Range selector + CSV export wiring.
    assert 'buildAgentsCsv' in component
    assert 'Exportar' in component


def test_agent_performance_table_primitive_renders_required_columns():
    """The shared `AgentPerformanceTable` (used by Manager analytics and by the
    Owner/Admin "Rendimiento del equipo") exposes the canonical column set.
    """
    assert AGENT_TABLE.exists(), 'AgentPerformanceTable.jsx must exist'
    table = AGENT_TABLE.read_text()
    for label in (
        'Agente',
        'Mensajes',
        'Handoffs',
        'Citas cerradas',
        'Ingreso',
        '1ª resp.',
        'Rating',
        # Top performer badge (StatusBadge "Top" — UI-008.1 + UI-016.3).
        'Top',
    ):
        assert label in table, f'expected the shared agents table to expose "{label}"'


def test_analytics_panel_registers_agents_subtab():
    panel = ANALYTICS_PANEL.read_text()
    assert "id: 'agents'" in panel
    assert 'AgentPerformance' in panel
    assert "activeTab === 'agents'" in panel


def test_analytics_agents_appts_closed_qualifies_metadata_with_table_alias():
    """BUG-003: the `appts_closed` CTE in `analytics_agents` joins
    `app.appointments a` with `app.service_catalog s` (both expose a
    `metadata` jsonb column). The SELECT used to read an unqualified
    `metadata->>'closed_by_user_id'` → asyncpg raised AmbiguousColumnError
    and every `GET /v1/analytics/agents` returned 500.

    The fix qualifies the SELECT with `a.metadata` (matching the WHERE and
    GROUP BY which already used the alias).
    """
    source = routes_aggregated_source()
    # Locate the `appts_closed as (` CTE and read until the next CTE/SELECT.
    cte_start = source.index('appts_closed as (')
    cte_end = source.index('),', cte_start)
    cte_block = source[cte_start:cte_end]
    # The SELECT must be qualified.
    assert "a.metadata->>'closed_by_user_id'" in cte_block
    # Defensive: ensure no unqualified bare `select metadata->>` slipped back
    # in. The 10-space indent comes from the CTE body's nesting.
    assert "          select metadata->>'closed_by_user_id'" not in source, (
        'analytics_agents `appts_closed` CTE must qualify metadata with `a.` '
        'to avoid AmbiguousColumnError against the joined service_catalog row.'
    )
