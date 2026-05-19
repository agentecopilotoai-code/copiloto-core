"""Fix-group 17: BUG-103..BUG-107.

- BUG-103: VIGENTE. `OperationsDesk` montaba `useInboxData` (+ WebSocket)
  antes de `<RequirePermission>`. Fix: split outer/Body.
- BUG-104: VIGENTE. El summary header de `DigestReports` (counts) usaba
  el list que `useDigestReportsData` fetch al mount, pero el panel hijo
  hacía CRUD sin notificar al outer → summary stale. Fix: `onMutation`
  callback propagado, panel lo llama post-create/toggle/delete.
- BUG-105: VIGENTE. `useManagerAnalyticsData` no limpiaba state al
  cambiar de tenant → KPIs del tenant anterior visibles durante la
  carga (loading no se dispara porque `state.overview` es truthy).
  Fix: limpiar `setOverview/setPreviousOverview/setFunnel/setAgents/
  setCampaigns` al inicio del effect.
- BUG-106: NOT-APPLICABLE. BUG-037 (fix-group-03) ya bajó
  `tenant_analytics_router` a `require_min_role('viewer')`, así que
  agent puede leer endpoints sin recibir 403.
- BUG-107: VIGENTE. `TeamModule` montaba `useTeamData` antes de
  `<RequirePermission>`. Fix: split outer/Body.
"""
from __future__ import annotations

from pathlib import Path
from tests._routes_aggregator import routes_aggregated_source


OPERATIONS_DESK = Path('admin-panel/src/features/agente/inbox/OperationsDesk.jsx')
TEAM_MODULE = Path('admin-panel/src/features/owner-admin/team/TeamModule.jsx')
DIGEST_REPORTS = Path('admin-panel/src/features/manager/digest-reports/DigestReports.jsx')
DIGEST_PANEL = Path('admin-panel/src/features/manager/digest-reports/components/DigestSubscriptionsPanel.jsx')
MANAGER_ANALYTICS_HOOK = Path('admin-panel/src/features/manager/analytics/hooks/useManagerAnalyticsData.js')


# ───── BUG-103 — OperationsDesk split ───────────────────────────────────


def test_bug_103_operations_desk_gates_before_data_hook():
    src = OPERATIONS_DESK.read_text()
    assert 'OperationsDeskBody' in src, (
        'BUG-103: el split debe introducir `OperationsDeskBody`.'
    )
    outer_idx = src.find('export function OperationsDesk(props)')
    body_idx = src.find('function OperationsDeskBody(')
    assert outer_idx >= 0 and body_idx > outer_idx
    outer_block = src[outer_idx:body_idx]
    assert 'useInboxData' not in outer_block, (
        'BUG-103: el outer NO debe invocar `useInboxData` antes del gate.'
    )
    assert '<RequirePermission' in outer_block


# ───── BUG-104 — DigestReports refresh via callback ─────────────────────


def test_bug_104_digest_reports_propagates_on_mutation_callback():
    src = DIGEST_REPORTS.read_text()
    assert 'onMutation={actions.refresh}' in src, (
        'BUG-104: el orchestrator debe pasar `onMutation={actions.refresh}` al '
        'panel para que el summary header se refresque post-CRUD.'
    )


def test_bug_104_digest_panel_invokes_on_mutation_after_crud():
    src = DIGEST_PANEL.read_text()
    assert 'onMutation' in src, (
        'BUG-104: el panel debe aceptar la prop `onMutation`.'
    )
    assert "if (typeof onMutation === 'function') onMutation();" in src, (
        'BUG-104: el panel debe invocar `onMutation()` después de cada CRUD '
        '(create/toggle/delete) — sin esto el summary del outer queda stale.'
    )


# ───── BUG-105 — analytics clear on tenant switch ───────────────────────


def test_bug_105_manager_analytics_clears_state_on_tenant_change():
    src = MANAGER_ANALYTICS_HOOK.read_text()
    # Las 5 limpiezas explícitas del state antes del fetch.
    for setter in ('setOverview(null)', 'setPreviousOverview(null)', 'setFunnel(null)', 'setAgents(null)', 'setCampaigns(null)'):
        assert setter in src, (
            f'BUG-105: el effect debe llamar `{setter}` ANTES del fetch para '
            'evitar mostrar data del tenant anterior durante la carga.'
        )


# ───── BUG-106 — NOT-APPLICABLE (fix-group-03 BUG-037 ya bajó router) ──


def test_bug_106_tenant_analytics_router_allows_viewer_or_lower():
    """BUG-037 (fix-group-03) bajó `tenant_analytics_router` a
    `require_min_role('viewer')`. Como agent > viewer en la jerarquía,
    agent también pasa el gate — no más 403 en analytics.
    """
    src = routes_aggregated_source()
    block_idx = src.find('tenant_analytics_router = APIRouter(')
    assert block_idx > 0
    block_end = src.find('tenant_manager_router', block_idx)
    block = src[block_idx:block_end]
    assert "require_min_role('viewer')" in block, (
        'BUG-106/037: regresión — `tenant_analytics_router` volvió a un gate '
        'más alto que `viewer`, dejando a agent/viewer sin acceso.'
    )


# ───── BUG-107 — TeamModule split ───────────────────────────────────────


def test_bug_107_team_module_gates_before_data_hook():
    src = TEAM_MODULE.read_text()
    assert 'TeamModuleBody' in src, (
        'BUG-107: el split debe introducir `TeamModuleBody`.'
    )
    outer_idx = src.find('export function TeamModule(props)')
    body_idx = src.find('function TeamModuleBody(')
    assert outer_idx >= 0 and body_idx > outer_idx
    outer_block = src[outer_idx:body_idx]
    assert 'useTeamData' not in outer_block, (
        'BUG-107: el outer NO debe invocar `useTeamData` antes del gate.'
    )
    assert '<RequirePermission' in outer_block
