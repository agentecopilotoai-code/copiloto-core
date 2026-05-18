"""Fix-group 14: BUG-088..BUG-092.

- BUG-088: VIGENTE. ErrorBoundary rendereaba `error.message` raw en `<pre>`,
  leakeando stacks/paths/SQL params al usuario. Fix: mostrar
  `ERR-XXXXXXXX` (FNV-1a hash 8 hex chars) — el operador correlaciona
  con logs/audit.
- BUG-089: NOT-APPLICABLE. `Landing` ya usa `adminPath('/admin/login')`.
- BUG-090: VIGENTE. `AgentPerformance` tiene botón "Exportar" CSV;
  `ViewerAnalytics` reusaba `AnalyticsPanel` que rendereaba
  `AgentPerformance` sin gate → viewer veía CSV export. Fix: prop
  `readOnly` propagada por la cadena
  `ViewerAnalytics → AnalyticsPanel → AgentPerformance`.
- BUG-091: NOT-APPLICABLE. `StorageSummary` ya concatena bucket + prefix.
- BUG-092: NOT-APPLICABLE. `useKnowledgeStudioData` ya pasa
  `statusesForFilterTab(filterTab)` al backend (server-side filter).
"""
from __future__ import annotations

from pathlib import Path


ERROR_BOUNDARY = Path('admin-panel/src/components/ui/ErrorBoundary.jsx')
LANDING = Path('admin-panel/src/features/public/landing/Landing.jsx')
AGENT_PERFORMANCE = Path('admin-panel/src/features/owner-admin/analytics/AgentPerformance.jsx')
ANALYTICS_PANEL = Path('admin-panel/src/features/owner-admin/analytics/AnalyticsPanel.jsx')
VIEWER_ANALYTICS = Path('admin-panel/src/features/viewer/analytics/ViewerAnalytics.jsx')
STORAGE_SUMMARY = Path('admin-panel/src/features/owner-admin/knowledge-studio/components/StorageSummary.jsx')
KNOWLEDGE_HOOK = Path('admin-panel/src/features/owner-admin/knowledge-studio/hooks/useKnowledgeStudioData.js')


# ───── BUG-088 — ErrorBoundary no leak error.message ────────────────────


def test_bug_088_error_boundary_does_not_render_raw_error_message():
    src = ERROR_BOUNDARY.read_text()
    # No queremos `{error.message}` raw en JSX (con `<pre>`).
    assert '{error.message}' not in src, (
        'BUG-088: regresión — `{error.message}` reaparece en el render. '
        'Esto leakea stacks/paths/SQL params al usuario.'
    )
    # Debe usar el hash helper.
    assert 'hashErrorMessage' in src, (
        'BUG-088: el helper `hashErrorMessage` debe existir para generar '
        'un código de incidente determinístico.'
    )
    assert "`ERR-${" in src, (
        'BUG-088: el código que se muestra debe ser tipo `ERR-XXXXXXXX`.'
    )


# ───── BUG-089 — NOT-APPLICABLE (Landing usa adminPath) ─────────────────


def test_bug_089_landing_uses_admin_path_for_login():
    src = LANDING.read_text()
    assert "adminPath('/admin/login')" in src, (
        'BUG-089: regresión — Landing ya no usa `adminPath(\'/admin/login\')` '
        'para el login CTA. Si apunta al frontend, el flow Auth0 BFF se rompe.'
    )


# ───── BUG-090 — Viewer CSV oculto ──────────────────────────────────────


def test_bug_090_agent_performance_accepts_read_only_prop():
    src = AGENT_PERFORMANCE.read_text()
    assert 'readOnly = false' in src, (
        'BUG-090: `AgentPerformance` debe aceptar prop `readOnly` (default '
        'false para no cambiar el comportamiento de owner/admin/manager).'
    )
    # El botón Exportar debe estar dentro de un `readOnly ? null : ...`.
    assert 'readOnly ? null : (' in src, (
        'BUG-090: el botón "Exportar" CSV debe ocultarse cuando readOnly=true.'
    )


def test_bug_090_analytics_panel_propagates_read_only():
    src = ANALYTICS_PANEL.read_text()
    assert 'readOnly = false' in src, (
        'BUG-090: `AnalyticsPanel` debe aceptar prop `readOnly` para '
        'propagarla a AgentPerformance.'
    )
    assert 'readOnly={readOnly}' in src, (
        'BUG-090: `AnalyticsPanel` debe pasar `readOnly` al `<AgentPerformance>`.'
    )


def test_bug_090_viewer_analytics_passes_read_only_true():
    src = VIEWER_ANALYTICS.read_text()
    assert '<AnalyticsPanel' in src and 'readOnly' in src, (
        'BUG-090: `ViewerAnalytics` debe pasar `readOnly` al `<AnalyticsPanel>` '
        'para que el CTA de export quede oculto en el shell read-only.'
    )


# ───── BUG-091 — NOT-APPLICABLE (StorageSummary concatena prefix) ──────


def test_bug_091_storage_summary_concatenates_bucket_and_prefix():
    src = STORAGE_SUMMARY.read_text()
    assert 'bucketBase' in src and 'prefix' in src, (
        'BUG-091: regresión — `StorageSummary` ya no combina bucket + prefix.'
    )


# ───── BUG-092 — NOT-APPLICABLE (server-side status filter) ─────────────


def test_bug_092_knowledge_studio_uses_server_side_status_filter():
    src = KNOWLEDGE_HOOK.read_text()
    assert 'statusesForFilterTab(filterTab)' in src, (
        'BUG-092: regresión — `useKnowledgeStudioData` ya no usa '
        '`statusesForFilterTab(filterTab)` server-side; vuelve el client-filter '
        'que oculta docs con >250 results.'
    )
