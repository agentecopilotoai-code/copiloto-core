"""Static tests for UI-016.1-FU — Backend endpoint para "Marcar live".

These tests inspect source files (no FastAPI app spin-up, no DB) so they
run in CI without Docker. They cover:

- the schema declares the ``go_live_at`` column on ``app.tenant_settings``
  + migration hint for existing databases;
- the new endpoint ``POST /v1/tenants/{tenant_id}/go-live`` is registered
  on ``tenant_admin_router`` and explicitly escalates to
  ``require_min_role('owner')`` above the router default;
- the handler uses the four mandatory security primitives
  (``ensure_tenant_access`` + ``set_config('app.tenant_id')`` +
  ``audit('tenant.go_live_marked')`` + role escalation);
- the handler rejects with 409 when the readiness report is not ready;
- the write is idempotent (preserves the original ``go_live_at`` if
  already set);
- the admin panel exposes the ``markTenantLive`` helper and wires it
  inside ``GoLiveReadiness.jsx``.
"""
from pathlib import Path

ROUTES = Path('app/api/v1/routes.py')
SCHEMA = Path('infra/postgres/01-schema.sql')
CORE_API = Path('admin-panel/src/services/coreApi.js')
READINESS_JSX = Path(
    'admin-panel/src/features/owner-admin/readiness/GoLiveReadiness.jsx'
)


def _go_live_function_source() -> str:
    source = ROUTES.read_text()
    start = source.index('async def mark_tenant_go_live')
    # Walk forward to the next top-level decorator (start of next route).
    end = source.index('\n@tenant_admin_router', start + 1)
    return source[start:end]


def test_schema_declares_go_live_at_column():
    schema = SCHEMA.read_text()
    # Column on app.tenant_settings.
    assert 'go_live_at timestamptz null' in schema
    # Migration hint block must reference the task ID so future operators
    # see why the column was added.
    assert 'TASK-UI-016.1-FU' in schema
    # The migration hint for existing databases must be runnable as a
    # single alter table statement.
    assert 'alter table app.tenant_settings add column if not exists go_live_at' in schema


def test_go_live_endpoint_is_registered_under_admin_router():
    source = ROUTES.read_text()
    assert "@tenant_admin_router.post('/tenants/{tenant_id}/go-live')" in source
    assert 'async def mark_tenant_go_live' in source


def test_go_live_endpoint_escalates_to_owner_role():
    fn_source = _go_live_function_source()
    # The router default is `require_min_role('admin')` — owners-only ops
    # must escalate explicitly inside the handler.
    assert "await require_min_role('owner')(request)" in fn_source


def test_go_live_endpoint_uses_security_primitives():
    fn_source = _go_live_function_source()
    assert 'await ensure_tenant_access(' in fn_source
    assert "set_config('app.tenant_id'" in fn_source
    assert 'await audit(' in fn_source
    # action name must match the spec (queriable from audit log filters).
    assert "action='tenant.go_live_marked'" in fn_source


def test_go_live_endpoint_validates_readiness():
    fn_source = _go_live_function_source()
    assert 'build_tenant_readiness_report' in fn_source
    assert 'status_code=409' in fn_source
    # The handler must compare the report's `status` field against
    # `'ready'` — anything else (or missing) returns 409.
    assert "'status') != 'ready'" in fn_source or "'status' != 'ready'" in fn_source


def test_go_live_endpoint_audit_carries_readiness_snapshot():
    fn_source = _go_live_function_source()
    # The audit metadata must include both the optional reason and a
    # snapshot of the readiness checks at the moment of marking, so we
    # have a forensic trail of *why* the owner believed the tenant was
    # ready when they flipped the switch.
    assert 'metadata=' in fn_source
    assert 'readiness_snapshot' in fn_source
    assert "'reason'" in fn_source or '"reason"' in fn_source


def test_go_live_endpoint_is_idempotent():
    fn_source = _go_live_function_source()
    # The write must be guarded by `if current['go_live_at'] is None`
    # so re-clicks preserve the original timestamp + skip a duplicate
    # audit event.
    assert "current['go_live_at'] is None" in fn_source
    assert 'update app.tenant_settings set go_live_at = now()' in fn_source


def test_go_live_endpoint_validates_reason_shape():
    fn_source = _go_live_function_source()
    # If the client passes a `reason`, it must be a string (or null).
    # Other shapes are rejected with 422 BEFORE the write.
    assert 'reason must be a string' in fn_source
    assert 'status_code=422' in fn_source


def test_readiness_response_exposes_go_live_at():
    source = ROUTES.read_text()
    # `build_tenant_readiness_report` must surface `tenant_status.go_live_at`
    # so the frontend can render the "Tenant en producción desde X" banner
    # without a second round-trip.
    assert "response['tenant_status']" in source
    assert "'go_live_at'" in source


def test_admin_panel_exposes_mark_tenant_live_helper():
    source = CORE_API.read_text()
    assert 'export function markTenantLive' in source
    assert '/tenants/${tenantId}/go-live' in source
    helper_start = source.index('export function markTenantLive')
    helper_end = source.index('\nexport ', helper_start + 1)
    helper_src = source[helper_start:helper_end]
    assert "method: 'POST'" in helper_src
    assert 'tenantId' in helper_src


def test_go_live_readiness_wires_real_endpoint():
    source = READINESS_JSX.read_text()
    # The frontend must call the real helper (no longer the placeholder).
    assert 'markTenantLive' in source
    # The mutation must be gated by a confirmation prompt.
    assert 'useConfirm' in source
    assert 'await confirm(' in source
    # 409 path renders the reasons in an AlertBanner.
    assert 'markLiveReasons' in source
    # The "already live" banner reads tenant_status.go_live_at from the report.
    assert 'tenant_status' in source
    assert 'go_live_at' in source
    # The placeholder text from UI-016.1 must be gone.
    assert 'UI-016.1-FU. Mientras tanto' not in source
