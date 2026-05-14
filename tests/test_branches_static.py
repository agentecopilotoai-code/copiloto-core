"""Static tests for TASK-0050 — Multi-sede (branches) with explicit selection during booking.

Coverage:
- Schema: ``app.branches`` table, indexes, RLS, ``branch_id`` on ``app.resources``
  and ``app.appointments`` with tenant-scoped composite foreign keys.
- Seed: auto-creation of a "Principal" branch per tenant and association of the
  default resource with that branch.
- Booking flow: new ``awaiting_branch`` step, branch picker before resources,
  branch=1 skip path, branch propagated to the appointment row.
- Notifications: reads address/maps from ``app.branches`` instead of
  ``tenant_settings.notification_settings.location_*``.
- Admin API: CRUD routes for branches, analytics + list filters by branch,
  audit actions ``branch.created/updated/deleted``.
- Admin Panel: BranchesModule registered, wizard tab "Sedes", coreApi client.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from app.api.v1 import routes as routes_module
from app.api.v1.schemas import BranchCreate, BranchUpdate, ResourceCreate, ResourceUpdate
from app.services import booking_flow, notifications

SCHEMA = Path('infra/postgres/01-schema.sql')
SEED = Path('infra/postgres/02-seed.sql')
ROUTES = Path('app/api/v1/routes.py')
BOOKING_FLOW = Path('app/services/booking_flow.py')
NOTIFICATIONS = Path('app/services/notifications.py')
ADMIN_LAYOUT = Path('admin-panel/src/app/moduleRegistry.js')
ADMIN_MODULES = Path('admin-panel/src/data/modules.js')
BRANCHES_MODULE = Path('admin-panel/src/components/modules/branches/BranchesModule.jsx')
WIZARD = Path('admin-panel/src/components/modules/tenantSetup/TenantSetupWizard.jsx')
CORE_API = Path('admin-panel/src/services/coreApi.js')


# ───── Schema ──────────────────────────────────────────────────────────────


def test_schema_creates_branches_table_with_required_columns():
    schema = SCHEMA.read_text()
    assert 'create table app.branches (' in schema
    for column in (
        'tenant_id uuid not null references app.tenants(id)',
        'name text not null',
        'code text not null',
        'address text',
        'city text',
        'state text',
        "country char(2) not null default 'CO'",
        'lat numeric(10,7)',
        'lng numeric(10,7)',
        'maps_url text',
        'phone_e164 text',
        "timezone text not null default 'America/Bogota'",
        "opening_hours jsonb not null default '{}'::jsonb",
        'is_active boolean not null default true',
        'sort_order int not null default 0',
        'unique (tenant_id, code)',
    ):
        assert column in schema, f'missing in branches schema: {column}'


def test_schema_indexes_branches_for_active_lookup():
    schema = SCHEMA.read_text()
    assert (
        'create index ix_branches_tenant_active on app.branches(tenant_id, is_active, sort_order)'
        in schema
    )


def test_schema_adds_branch_id_to_resources_and_appointments():
    schema = SCHEMA.read_text()
    # column on resources (declared in the create-table block)
    assert 'branch_id uuid,\n  is_active boolean not null default true' in schema
    # column on appointments (before metadata + created_at)
    assert "branch_id uuid,\n  metadata jsonb not null default '{}'::jsonb" in schema
    # composite tenant-scoped FKs
    assert 'fk_resources_tenant_branch' in schema
    assert (
        'foreign key (tenant_id, branch_id) references app.branches(tenant_id, id) on delete set null'
        in schema
    )
    assert 'fk_appointments_tenant_branch' in schema
    assert (
        'foreign key (tenant_id, branch_id) references app.branches(tenant_id, id) on delete restrict'
        in schema
    )


def test_schema_enables_rls_for_branches():
    schema = SCHEMA.read_text()
    assert 'alter table app.branches enable row level security' in schema
    # branches is included in the policy generation loop
    assert "'branches'" in schema
    # composite uniqueness for tenant-scoped FK targets
    assert 'uq_branches_tenant_id_id unique (tenant_id, id)' in schema


def test_schema_registers_touch_trigger_for_branches():
    schema = SCHEMA.read_text()
    assert (
        'create trigger trg_branches_touch before update on app.branches'
        in schema
    )


# ───── Seed ────────────────────────────────────────────────────────────────


def test_seed_creates_principal_branch_per_tenant():
    seed = SEED.read_text()
    assert 'insert into app.branches' in seed
    assert "'Principal'" in seed
    assert "'principal'" in seed
    # default resource is wired to the principal branch
    assert 'left join app.branches b on b.tenant_id = t.id' in seed
    assert 'branch_id' in seed


# ───── Pydantic schemas ────────────────────────────────────────────────────


def test_branch_create_exposes_required_fields():
    fields = BranchCreate.model_fields
    for key in ('name', 'code', 'address', 'city', 'state', 'country',
                'lat', 'lng', 'maps_url', 'phone_e164', 'timezone',
                'opening_hours', 'is_active', 'sort_order'):
        assert key in fields, key
    assert fields['country'].default == 'CO'
    assert fields['timezone'].default == 'America/Bogota'
    assert fields['is_active'].default is True


def test_branch_update_is_fully_partial():
    fields = BranchUpdate.model_fields
    for key in ('name', 'code', 'address', 'city', 'state', 'country',
                'lat', 'lng', 'maps_url', 'phone_e164', 'timezone',
                'opening_hours', 'is_active', 'sort_order'):
        assert key in fields, key
        assert fields[key].default is None


def test_resource_schemas_accept_branch_id():
    assert 'branch_id' in ResourceCreate.model_fields
    assert 'branch_id' in ResourceUpdate.model_fields


# ───── Booking flow ────────────────────────────────────────────────────────


def test_booking_flow_declares_awaiting_branch_step_and_prefix():
    assert booking_flow.STEP_AWAITING_BRANCH == 'awaiting_branch'
    assert booking_flow.PREFIX_BRANCH == 'book_branch'


def test_present_branches_skips_picker_when_single_branch():
    source = inspect.getsource(booking_flow._present_branches)
    # Single-branch path auto-routes to resources with the only branch attached.
    assert 'if len(branches) == 1' in source
    assert '_present_resources' in source
    assert "'selected_branch_id'" in source


def test_present_branches_emits_interactive_list_when_multiple():
    source = inspect.getsource(booking_flow._present_branches)
    assert 'PREFIX_BRANCH' in source
    assert 'STEP_AWAITING_BRANCH' in source
    assert 'build_interactive_list_payload' in source


def test_present_resources_filters_by_selected_branch():
    source = inspect.getsource(booking_flow._present_resources)
    assert "state.get('selected_branch_id')" in source
    assert 'branch_uuid' in source


def test_list_active_resources_accepts_branch_filter():
    source = inspect.getsource(booking_flow._list_active_resources)
    assert 'branch_id' in source
    assert 'r.branch_id = $2' in source


def test_maybe_run_booking_flow_routes_through_branch_picker():
    source = inspect.getsource(booking_flow.maybe_run_booking_flow)
    # After a service is picked the flow asks for branch first, falling back
    # to resources when no branch exists.
    assert '_present_branches' in source
    assert "elif prefix == PREFIX_BRANCH" in source


def test_create_appointment_persists_branch_id():
    source = inspect.getsource(booking_flow._create_appointment)
    assert 'branch_id' in source
    assert "state.get('selected_branch_id')" in source
    # Falls back to the resource's branch when state did not capture one.
    assert 'select branch_id from app.resources' in source


# ───── Notifications ───────────────────────────────────────────────────────


def test_appointment_context_joins_branch():
    source = inspect.getsource(notifications._appointment_context)
    assert 'left join app.branches b' in source
    assert 'b.address as branch_address' in source
    assert 'b.maps_url as branch_maps_url' in source


def test_create_reminder_jobs_prefers_branch_address():
    source = inspect.getsource(notifications.create_appointment_reminder_jobs)
    assert "context.get('branch_id')" in source
    assert "context.get('branch_address')" in source
    assert "context.get('branch_maps_url')" in source
    # Legacy tenant-wide defaults are only used when no branch is attached.
    assert "settings.get('location_address')" in source
    assert "settings.get('location_maps_url')" in source


# ───── Routes (API) ────────────────────────────────────────────────────────


def test_branches_routes_registered_on_admin_and_ops_routers():
    admin_paths = {
        (getattr(r, 'path', ''), tuple(sorted(getattr(r, 'methods', []) or [])))
        for r in routes_module.tenant_admin_router.routes
        if hasattr(r, 'path')
    }
    ops_paths = {
        (getattr(r, 'path', ''), tuple(sorted(getattr(r, 'methods', []) or [])))
        for r in routes_module.tenant_ops_router.routes
        if hasattr(r, 'path')
    }
    assert ('/branches', ('GET',)) in ops_paths
    assert ('/branches', ('POST',)) in admin_paths
    assert ('/branches/{branch_id}', ('PATCH',)) in admin_paths
    assert ('/branches/{branch_id}', ('DELETE',)) in admin_paths


def test_branch_routes_emit_audit_events():
    source = ROUTES.read_text()
    assert "action='branch.created'" in source
    assert "action='branch.updated'" in source
    assert "action='branch.deleted'" in source


def test_list_resources_and_appointments_accept_branch_filter():
    source = ROUTES.read_text()
    # resources listing exposes branch filter
    assert 'branch_id: UUID | None = Query(default=None)' in source
    assert 'and ($4::uuid is null or branch_id=$4)' in source
    # ops appointments use the same filter
    assert 'and ($4::uuid is null or a.branch_id=$4)' in source


def test_analytics_appointments_accepts_branch_filter():
    source = inspect.getsource(routes_module.analytics_appointments)
    assert 'branch_id' in source
    assert '($4::uuid is null or a.branch_id = $4)' in source
    assert '($4::uuid is null or branch_id = $4)' in source


def test_create_resource_persists_branch_id():
    source = ROUTES.read_text()
    assert 'public_profile, branch_id, is_active' in source
    assert 'payload.branch_id,' in source


# ───── Admin panel ─────────────────────────────────────────────────────────


def test_admin_panel_registers_branches_module():
    layout = ADMIN_LAYOUT.read_text()
    assert "import { BranchesModule } from '../components/modules/branches/BranchesModule.jsx'" in layout
    assert 'branches: {' in layout
    catalog = ADMIN_MODULES.read_text()
    assert "id: 'branches'" in catalog
    # UI-005: el gate ad-hoc minRole se reemplazó por la capability de la
    # matriz de permisos (admin/owner tienen branches.write=RW).
    assert "capability: 'branches.write'" in catalog


def test_branches_module_has_form_and_listing():
    source = BRANCHES_MODULE.read_text()
    assert 'createBranch' in source
    assert 'updateBranch' in source
    assert 'deactivateBranch' in source
    assert 'opening_hours' in source
    assert 'data-testid="branches-hours"' in source


def test_wizard_adds_branches_tab():
    source = WIZARD.read_text()
    assert "{ id: 'branches', label: 'Sedes' }" in source
    assert 'data-wizard-tab="branches"' in source
    assert "import { BranchesModule } from '../branches/BranchesModule.jsx'" in source


def test_core_api_exposes_branch_endpoints():
    source = CORE_API.read_text()
    assert 'export function listBranches' in source
    assert 'export function createBranch' in source
    assert 'export function updateBranch' in source
    assert 'export function deactivateBranch' in source
