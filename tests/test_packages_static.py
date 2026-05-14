"""Static tests for TASK-0051 — Treatment packages / multi-session plans.

Coverage:
- Schema: ``app.treatment_packages``, ``app.contact_packages``,
  ``app.appointment_package_links`` with tenant-scoped composite FKs, RLS, and
  the consumption trigger on appointment status transitions.
- Trigger: idempotent decrement on ``status='completed'`` only, exhaustion
  flag, and renewal domain event on penultimate consumption.
- Pydantic schemas: ``TreatmentPackageCreate/Update``,
  ``ContactPackageAssign/Patch``.
- Routes: CRUD for packages under tenant_admin_router; assignment, update and
  refund under tenant_ops_router; audit events for each verb.
- Booking flow: ``awaiting_package`` step + ``book_package`` prefix, list-only
  packages whose ``includes_service_ids`` cover the chosen service, link the
  appointment to the chosen contact_package, fallback to branch picker on
  decline.
- Admin Panel: PackagesModule registered, contacts profile shows packages
  block, coreApi client exposes the package endpoints.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from app.api.v1 import routes as routes_module
from app.api.v1.schemas import (
    ContactPackageAssign,
    ContactPackagePatch,
    TreatmentPackageCreate,
    TreatmentPackageUpdate,
)
from app.services import booking_flow

SCHEMA = Path('infra/postgres/01-schema.sql')
ROUTES = Path('app/api/v1/routes.py')
BOOKING_FLOW = Path('app/services/booking_flow.py')
ADMIN_LAYOUT = Path('admin-panel/src/app/moduleRegistry.js')
ADMIN_MODULES = Path('admin-panel/src/data/modules.js')
# UI-007.5: the packages module was redesigned into a feature directory.
PACKAGES_FEATURE = Path('admin-panel/src/features/owner-admin/packages')
# UI-007.3: the contacts module was split into a feature directory.
CONTACTS_FEATURE = Path('admin-panel/src/features/owner-admin/conversations-contacts')
CORE_API = Path('admin-panel/src/services/coreApi.js')


def _contacts_feature_source() -> str:
    return '\n'.join(
        path.read_text() for path in sorted(CONTACTS_FEATURE.rglob('*.js*'))
    )


def _packages_feature_source() -> str:
    return '\n'.join(
        path.read_text() for path in sorted(PACKAGES_FEATURE.rglob('*.js*'))
    )


# ───── Schema ──────────────────────────────────────────────────────────────


def test_schema_creates_treatment_packages_table_with_required_columns():
    schema = SCHEMA.read_text()
    assert 'create table app.treatment_packages (' in schema
    for column in (
        'tenant_id uuid not null references app.tenants(id) on delete cascade',
        'name text not null',
        'total_sessions int not null check (total_sessions > 0)',
        'validity_days int check (validity_days is null or validity_days > 0)',
        'price_amount numeric(10,2) not null check (price_amount >= 0)',
        "price_currency char(3) not null default 'COP'",
        "includes_service_ids uuid[] not null default '{}'",
        'renewal_template_id uuid',
        'is_active boolean not null default true',
        'sort_order int not null default 0',
        "metadata jsonb not null default '{}'::jsonb",
    ):
        assert column in schema, f'missing in treatment_packages schema: {column}'
    # GIN index for the services-array filter used by the booking flow.
    assert (
        'create index gin_treatment_packages_services\n  on app.treatment_packages using gin(includes_service_ids)'
        in schema
    )


def test_schema_creates_contact_packages_table_with_status_and_payment_columns():
    schema = SCHEMA.read_text()
    assert 'create table app.contact_packages (' in schema
    for column in (
        'tenant_id uuid not null references app.tenants(id) on delete cascade',
        'contact_id uuid not null references app.contacts(id) on delete restrict',
        'package_id uuid not null references app.treatment_packages(id) on delete restrict',
        'remaining_sessions int not null check (remaining_sessions >= 0)',
        "status text not null default 'active' check (status in ('active','exhausted','expired','refunded'))",
        "payment_status text not null default 'pending'",
        'expires_at timestamptz',
    ):
        assert column in schema, f'missing in contact_packages schema: {column}'
    assert (
        'create index ix_contact_packages_contact_active\n  on app.contact_packages(tenant_id, contact_id, status)'
        in schema
    )


def test_schema_creates_appointment_package_links_table():
    schema = SCHEMA.read_text()
    assert 'create table app.appointment_package_links (' in schema
    assert 'primary key (appointment_id)' in schema
    assert (
        'contact_package_id uuid not null references app.contact_packages(id) on delete restrict'
        in schema
    )
    # tenant-scoped composite FKs
    assert 'fk_appointment_package_links_tenant_appointment' in schema
    assert (
        'foreign key (tenant_id, appointment_id)\n    references app.appointments(tenant_id, id) on delete cascade'
        in schema
    )
    assert 'fk_appointment_package_links_tenant_contact_package' in schema


def test_schema_enables_rls_for_package_tables():
    schema = SCHEMA.read_text()
    for table in ('treatment_packages', 'contact_packages', 'appointment_package_links'):
        assert f'alter table app.{table} enable row level security' in schema, table
        assert f"'{table}'" in schema, f'missing policy loop entry for {table}'
    # composite tenant-scoped uniqueness used by FK targets.
    assert 'uq_treatment_packages_tenant_id_id unique (tenant_id, id)' in schema
    assert 'uq_contact_packages_tenant_id_id unique (tenant_id, id)' in schema


def test_schema_registers_touch_trigger_for_packages():
    schema = SCHEMA.read_text()
    assert (
        'create trigger trg_treatment_packages_touch before update on app.treatment_packages'
        in schema
    )
    assert (
        'create trigger trg_contact_packages_touch before update on app.contact_packages'
        in schema
    )


def test_schema_consumption_trigger_runs_only_when_status_transitions_to_completed():
    schema = SCHEMA.read_text()
    assert 'create or replace function app.consume_package_on_appointment()' in schema
    # idempotency guards: skip when already completed and when link already consumed.
    assert "if new.status <> 'completed' then\n    return new" in schema
    assert "if old.status = 'completed' then\n    return new" in schema
    assert 'if link_row.consumed_at is not null then' in schema
    # the decrement clamps at 0 and flips to 'exhausted' at zero.
    assert 'greatest(pkg.remaining_sessions - 1, 0)' in schema
    assert "case when new_remaining = 0 then 'exhausted' else pkg.status end" in schema
    # Renewal-offer domain event is emitted when 1 session is left.
    assert 'package.renewal_offer_due' in schema
    assert "'pkg_renewal:' || pkg.id::text" in schema
    # the trigger is attached after-update of status on appointments.
    assert (
        'create trigger trg_appointments_consume_package\n  after update of status on app.appointments'
        in schema
    )


def test_schema_indexes_expiring_packages_for_scheduler():
    schema = SCHEMA.read_text()
    assert (
        "create index ix_contact_packages_expiry\n  on app.contact_packages(expires_at) where status='active' and expires_at is not null"
        in schema
    )


# ───── Pydantic schemas ────────────────────────────────────────────────────


def test_treatment_package_create_required_fields():
    fields = TreatmentPackageCreate.model_fields
    for key in (
        'name', 'description', 'total_sessions', 'validity_days',
        'price_amount', 'price_currency', 'includes_service_ids',
        'renewal_template_id', 'is_active', 'sort_order', 'metadata',
    ):
        assert key in fields, key
    assert fields['price_currency'].default == 'COP'
    assert fields['is_active'].default is True


def test_treatment_package_update_is_fully_partial():
    fields = TreatmentPackageUpdate.model_fields
    for key in (
        'name', 'description', 'total_sessions', 'validity_days',
        'price_amount', 'price_currency', 'includes_service_ids',
        'renewal_template_id', 'is_active', 'sort_order', 'metadata',
    ):
        assert key in fields, key
        assert fields[key].default is None


def test_contact_package_assign_required_fields():
    fields = ContactPackageAssign.model_fields
    assert 'package_id' in fields
    assert 'payment_status' in fields
    assert fields['payment_status'].default == 'pending'


def test_contact_package_patch_is_partial():
    fields = ContactPackagePatch.model_fields
    for key in (
        'payment_status', 'payment_amount', 'payment_currency',
        'expires_at', 'status', 'notes',
    ):
        assert key in fields, key
        assert fields[key].default is None


# ───── Routes ──────────────────────────────────────────────────────────────


def test_package_routes_registered():
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
    # Admin-only CRUD for the catalogue of packages.
    assert ('/packages', ('GET',)) in ops_paths
    assert ('/packages', ('POST',)) in admin_paths
    assert ('/packages/{package_id}', ('PATCH',)) in admin_paths
    assert ('/packages/{package_id}', ('DELETE',)) in admin_paths
    # TASK-0084 / BUG02: assignment/patch/refund of a contact_package are
    # financial side-effects and now live on tenant_admin_router (admin+).
    # Read access (list) stays on tenant_ops_router so agents can plan.
    assert ('/contacts/{contact_id}/packages', ('GET',)) in ops_paths
    assert ('/contacts/{contact_id}/packages', ('POST',)) in admin_paths
    assert ('/contacts/{contact_id}/packages/{contact_package_id}', ('PATCH',)) in admin_paths
    assert ('/contacts/{contact_id}/packages/{contact_package_id}', ('DELETE',)) in admin_paths


def test_package_routes_emit_audit_events():
    source = ROUTES.read_text()
    assert "action='package.created'" in source
    assert "action='package.updated'" in source
    assert "action='package.deleted'" in source
    assert "action='contact_package.assigned'" in source
    assert "action='contact_package.updated'" in source
    assert "action='contact_package.refunded'" in source


def test_create_treatment_package_validates_renewal_template_ownership():
    source = inspect.getsource(routes_module.create_treatment_package)
    assert 'renewal_template_id' in source
    assert 'select 1 from app.whatsapp_templates where tenant_id=$1 and id=$2' in source


def test_assign_contact_package_seeds_remaining_sessions_from_total():
    source = inspect.getsource(routes_module.assign_contact_package)
    # remaining_sessions and total_sessions are seeded from the package's
    # total_sessions ($5 in the insert) so a refund/exhaust check can compare
    # the original count later.
    assert 'remaining_sessions, total_sessions' in source
    assert 'values ($1,$2,$3,$4,$5,$5' in source
    # auto-derive expires_at from validity_days when the caller didn't set it.
    assert "pkg['validity_days']" in source
    assert 'timedelta(days=int(pkg' in source


def test_refund_contact_package_zeroes_remaining_sessions():
    source = inspect.getsource(routes_module.refund_contact_package)
    assert "status='refunded'" in source
    assert "payment_status='refunded'" in source
    assert 'remaining_sessions=0' in source


# ───── Booking flow ────────────────────────────────────────────────────────


def test_booking_flow_declares_awaiting_package_step_and_prefix():
    assert booking_flow.STEP_AWAITING_PACKAGE == 'awaiting_package'
    assert booking_flow.PREFIX_PACKAGE == 'book_package'
    assert booking_flow.PACKAGE_USE_NEW == 'new'


def test_list_active_contact_packages_filters_paid_and_unexpired():
    source = inspect.getsource(booking_flow._list_active_contact_packages)
    assert "cp.status='active'" in source
    assert "cp.payment_status='paid'" in source
    assert 'cp.remaining_sessions > 0' in source
    assert 'cp.expires_at is null or cp.expires_at > now()' in source
    # only packages whose includes_service_ids cover the picked service.
    assert 'tp.includes_service_ids' in source
    assert '= any(tp.includes_service_ids)' in source


def test_present_packages_returns_none_when_no_active_pkg():
    source = inspect.getsource(booking_flow._present_packages)
    assert 'if not packages:\n        return None' in source
    # The prompt exposes a third button for "pay normally".
    assert 'PACKAGE_USE_NEW' in source
    assert 'available_package_ids' in source


def test_maybe_run_booking_flow_routes_through_package_picker():
    source = inspect.getsource(booking_flow.maybe_run_booking_flow)
    assert '_present_packages' in source
    assert 'elif prefix == PREFIX_PACKAGE' in source
    # The decline branch falls back to branches/resources as before.
    assert 'PACKAGE_USE_NEW' in source


def test_create_appointment_links_contact_package_when_chosen():
    source = inspect.getsource(booking_flow._create_appointment)
    assert "state.get('selected_contact_package_id')" in source
    assert 'insert into app.appointment_package_links' in source
    # re-validates the package right before the insert to avoid race/replay.
    assert 'select id, remaining_sessions' in source
    assert "cp.status='active'" not in source  # this lives in _list helper
    assert "status='active'" in source


# ───── Admin panel ─────────────────────────────────────────────────────────


def test_admin_panel_registers_packages_module():
    # UI-007.5: the registry now points at the redesigned feature module.
    layout = ADMIN_LAYOUT.read_text()
    assert "import { Packages } from '../features/owner-admin/packages/index.js'" in layout
    assert 'packages: {' in layout
    # The legacy module path must be fully gone (no parallel implementation).
    assert 'components/modules/packages/PackagesModule' not in layout
    catalog = ADMIN_MODULES.read_text()
    assert "id: 'packages'" in catalog
    assert "label: 'Paquetes'" in catalog
    assert 'TASK-0051' in catalog


def test_packages_module_has_form_and_service_picker():
    source = _packages_feature_source()
    assert 'createTreatmentPackage' in source
    assert 'updateTreatmentPackage' in source
    assert 'deactivateTreatmentPackage' in source
    assert 'includes_service_ids' in source
    assert 'total_sessions' in source


def test_contacts_module_exposes_packages_block_and_actions():
    source = _contacts_feature_source()
    assert "listContactPackages" in source
    assert 'assignContactPackage' in source
    assert 'refundContactPackage' in source
    assert 'data-testid="contact-packages-panel"' in source


def test_core_api_exposes_package_endpoints():
    source = CORE_API.read_text()
    for fn in (
        'listTreatmentPackages',
        'createTreatmentPackage',
        'updateTreatmentPackage',
        'deactivateTreatmentPackage',
        'listContactPackages',
        'assignContactPackage',
        'updateContactPackage',
        'refundContactPackage',
    ):
        assert f'export function {fn}' in source, fn
