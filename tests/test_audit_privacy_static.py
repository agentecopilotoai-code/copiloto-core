from pathlib import Path

API_ROUTES = Path('app/api/v1/routes.py')
LOGGING = Path('app/core/logging.py')
SCHEMA_SQL = Path('infra/postgres/01-schema.sql')
BOOTSTRAP = Path('scripts/bootstrap.sh')
CORE_API = Path('admin-panel/src/services/coreApi.js')
AUDIT_PANEL = Path('admin-panel/src/components/modules/audit/AuditPanel.jsx')
ADMIN_LAYOUT = Path('admin-panel/src/components/layout/AdminLayout.jsx')
GLOBAL_CSS = Path('admin-panel/src/styles/global.css')
DPA = Path('docs/DPA.md')


# --- DB schema ---

def test_contacts_opt_in_status_includes_suppressed():
    source = SCHEMA_SQL.read_text()
    assert "'suppressed'" in source
    assert "opt_in_status in ('unknown','granted','revoked','suppressed')" in source


def test_schema_defines_suppressed_opt_in_status():
    """The canonical schema includes 'suppressed' from the start — bootstrap no
    longer carries an incremental constraint migration."""
    source = SCHEMA_SQL.read_text()
    assert "opt_in_status in ('unknown','granted','revoked','suppressed')" in source
    assert 'contacts_opt_in_status_check' not in BOOTSTRAP.read_text()


# --- Logging PII redaction ---

def test_logging_has_pii_redaction_processor():
    source = LOGGING.read_text()
    assert '_redact_pii' in source
    assert '_PHONE_RE' in source
    assert '_EMAIL_RE' in source
    assert '[PHONE]' in source
    assert '[EMAIL]' in source
    assert '_PII_KEYS' in source


def test_logging_processor_is_in_pipeline():
    source = LOGGING.read_text()
    assert '_redact_pii,' in source or '_redact_pii\n' in source


# --- Backend routes ---

def test_list_audit_logs_has_filters():
    source = API_ROUTES.read_text()
    assert 'async def list_audit_logs' in source
    assert 'action: str | None' in source
    assert 'actor_type: str | None' in source
    assert 'entity_type: str | None' in source
    assert 'from_date' in source
    assert 'to_date' in source


def test_export_audit_logs_endpoint_exists():
    source = API_ROUTES.read_text()
    assert "'/audit-logs/export'" in source
    assert 'async def export_audit_logs' in source
    assert 'text/csv' in source
    assert 'Content-Disposition' in source
    assert "action='audit_logs.exported'" in source


def test_suppress_contact_endpoint_exists():
    source = API_ROUTES.read_text()
    assert "'/contacts/{contact_id}/suppress'" in source
    assert 'async def suppress_contact' in source
    assert "opt_in_status = 'suppressed'" in source
    assert "action='contact.suppressed'" in source


def test_suppress_contact_requires_admin_role():
    source = API_ROUTES.read_text()
    assert "require_min_role('admin')(request)" in source


def test_suppress_contact_pseudonymizes_fields():
    source = API_ROUTES.read_text()
    assert 'pseudo' in source
    assert 'suppressed+' in source
    assert 'phone_hash' in source


def test_tenant_data_export_endpoint_exists():
    source = API_ROUTES.read_text()
    assert "'/tenants/{tenant_id}/data-export'" in source
    assert 'async def export_tenant_data' in source
    assert 'application/json' in source
    assert "action='tenant.data_exported'" in source
    assert 'no_train' in source
    assert 'pii_policy' in source


def test_tenant_data_export_requires_owner():
    """TASK-0077/BUG17: data-export is gated by ``ensure_tenant_role('owner')``,
    a double-check (JWT + DB) that replaces the single-side
    ``require_min_role('owner')`` previously used at the handler level."""
    source = API_ROUTES.read_text()
    assert "ensure_tenant_role(request, conn, tenant_id, 'owner')" in source


# --- coreApi.js ---

def test_core_api_has_audit_functions():
    source = CORE_API.read_text()
    assert 'export function listAuditLogsFiltered' in source
    assert 'export function exportAuditLogs' in source
    assert 'export function suppressContact' in source
    assert 'export function exportTenantData' in source


def test_core_api_suppress_uses_post():
    source = CORE_API.read_text()
    assert "suppress', {" in source or '/suppress' in source


# --- AuditPanel.jsx ---

def test_audit_panel_component_exists():
    assert AUDIT_PANEL.exists()
    source = AUDIT_PANEL.read_text()
    assert 'export function AuditPanel' in source


def test_audit_panel_has_log_table():
    source = AUDIT_PANEL.read_text()
    assert 'audit-table' in source
    assert 'listAuditLogsFiltered' in source
    assert 'exportAuditLogs' in source


def test_audit_panel_has_suppression_form():
    source = AUDIT_PANEL.read_text()
    assert 'suppressContact' in source
    assert 'handleSuppressContact' in source
    assert 'danger-action' in source
    assert 'confirm' in source


def test_audit_panel_has_tenant_export():
    source = AUDIT_PANEL.read_text()
    assert 'exportTenantData' in source
    assert 'handleExportTenantData' in source


def test_audit_panel_shows_dpa_summary():
    source = AUDIT_PANEL.read_text()
    assert 'no_train' in source or 'no entrenamiento' in source.lower()
    assert 'DPA' in source or 'dpa' in source.lower()


# --- AdminLayout.jsx ---

def test_admin_layout_imports_audit_panel():
    source = ADMIN_LAYOUT.read_text()
    assert "import { AuditPanel }" in source


def test_admin_layout_mounts_audit_panel():
    source = ADMIN_LAYOUT.read_text()
    assert "activeModuleId === 'audit'" in source
    assert '<AuditPanel' in source


# --- CSS ---

def test_global_css_has_audit_styles():
    source = GLOBAL_CSS.read_text()
    assert '.audit-panel' in source or '.audit-section' in source
    assert '.audit-table' in source
    assert '.danger-action' in source
    assert '.dpa-list' in source


# --- DPA doc ---

def test_dpa_document_exists():
    assert DPA.exists()
    source = DPA.read_text()
    assert 'no_train' in source
    assert 'suppressed' in source
    assert '365' in source
    assert '730' in source
    assert 'contact.suppressed' in source


# --- Feedback fixes ---

def test_logging_uses_recursive_redact_value():
    source = LOGGING.read_text()
    assert '_redact_value' in source
    assert 'isinstance(value, dict)' in source
    assert 'isinstance(value, (list, tuple))' in source


def test_logging_redact_pii_applies_redact_value_to_all_fields():
    source = LOGGING.read_text()
    # Should NOT just loop over _PII_KEYS - must apply _redact_value recursively
    assert '_redact_value(v)' in source


def test_core_api_export_uses_authenticated_fetch_not_anchor():
    source = CORE_API.read_text()
    assert 'downloadAuthenticated' in source
    assert 'blob()' in source
    assert 'URL.createObjectURL' in source
    # Must NOT use tenant_id_hint workaround
    assert 'tenant_id_hint' not in source


def test_core_api_export_sends_x_tenant_id_header():
    source = CORE_API.read_text()
    # buildHeaders is called inside downloadAuthenticated
    assert 'buildHeaders(session, tenantId)' in source


def test_core_api_tenant_data_export_also_uses_authenticated_fetch():
    source = CORE_API.read_text()
    # exportTenantData must delegate to downloadAuthenticated, not build its own URL
    assert 'exportTenantData' in source
    count = source.count('downloadAuthenticated')
    assert count >= 2  # used by both exportAuditLogs and exportTenantData
