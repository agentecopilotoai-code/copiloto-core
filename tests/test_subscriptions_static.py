"""Static tests for TASK-0075 — Suscripciones / membresías con cobro recurrente.

Coverage (≥ 14 tests):
- Schema: ``app.subscription_plans`` and ``app.contact_subscriptions``
  with tenant-scoped composite FKs, status enums, RLS, the unique provider
  reference index, and the WhatsApp template purpose
  ``subscription_payment_failed``.
- Service: ``extract_subscription_event`` translates Stripe and MercadoPago
  invoice webhook payloads to provider-agnostic ``SubscriptionInvoiceEvent``
  records, and ignores unrelated events.
- Pydantic schemas: ``SubscriptionPlanCreate/Update``,
  ``ContactSubscriptionCreate/Patch`` exist with the right enums.
- Routes: tenant_admin_router exposes plan CRUD; tenant_ops_router lists
  subscribers + cancels; the public webhook router accepts
  ``/webhooks/subscriptions/{provider}``; the failed-invoice branch queues a
  reminder_jobs entry with the ``subscription_payment_failed_v1`` template.
- Admin panel: the redesigned ``Subscriptions`` feature module registered,
  modules.js entry, coreApi client exposes the endpoints.
"""

from __future__ import annotations

import inspect
from pathlib import Path

from app.api.v1 import routes as routes_module
from app.api.v1.schemas import (
    ContactSubscriptionCreate,
    ContactSubscriptionPatch,
    SubscriptionPlanCreate,
    SubscriptionPlanUpdate,
)
from app.services import subscriptions as subscriptions_service

SCHEMA = Path('infra/postgres/01-schema.sql')
ROUTES = Path('app/api/v1/routes.py')
SERVICE = Path('app/services/subscriptions.py')
ADMIN_LAYOUT = Path('admin-panel/src/app/moduleRegistry.js')
ADMIN_MODULES = Path('admin-panel/src/app/modules.js')
# UI-007.6: the subscriptions module was redesigned into a feature directory.
SUBS_FEATURE = Path('admin-panel/src/features/owner-admin/subscriptions')
CORE_API = Path('admin-panel/src/services/coreApi.js')


def _subscriptions_feature_source() -> str:
    return '\n'.join(
        path.read_text() for path in sorted(SUBS_FEATURE.rglob('*.js*'))
    )


# ───── Schema ──────────────────────────────────────────────────────────────


def test_schema_creates_subscription_plans_table_with_required_columns():
    schema = SCHEMA.read_text()
    assert 'create table app.subscription_plans (' in schema
    for fragment in (
        'tenant_id uuid not null references app.tenants(id) on delete cascade',
        'name text not null',
        "billing_period text not null check (billing_period in ('monthly','quarterly','yearly'))",
        'price_amount numeric(10,2) not null check (price_amount >= 0)',
        "currency char(3) not null default 'COP'",
        "included_services jsonb not null default '[]'::jsonb",
        "status text not null default 'active' check (status in ('active','archived'))",
    ):
        assert fragment in schema, f'missing subscription_plans column: {fragment}'
    assert (
        'create index ix_subscription_plans_tenant_status\n  on app.subscription_plans(tenant_id, status, name)'
        in schema
    )


def test_schema_creates_contact_subscriptions_table_with_required_columns():
    schema = SCHEMA.read_text()
    assert 'create table app.contact_subscriptions (' in schema
    for fragment in (
        'tenant_id uuid not null references app.tenants(id) on delete cascade',
        'contact_id uuid not null references app.contacts(id) on delete restrict',
        'plan_id uuid not null references app.subscription_plans(id) on delete restrict',
        "status text not null default 'active' check (status in ('active','past_due','cancelled'))",
        "payment_provider text not null check (payment_provider in ('mercadopago','stripe'))",
        'payment_provider_subscription_id text',
        'payment_method_id text',
        'retry_payment_link text',
        'next_billing_at timestamptz',
    ):
        assert fragment in schema, f'missing contact_subscriptions column: {fragment}'
    # Unique index so that the same provider subscription id cannot be
    # registered twice in our system (would break webhook lookup).
    assert (
        'create unique index ux_contact_subscriptions_provider_ref\n'
        '  on app.contact_subscriptions(payment_provider, payment_provider_subscription_id)\n'
        '  where payment_provider_subscription_id is not null'
    ) in schema


def test_schema_adds_composite_tenant_fks_for_subscriptions():
    schema = SCHEMA.read_text()
    assert (
        'alter table app.subscription_plans add constraint uq_subscription_plans_tenant_id_id unique (tenant_id, id);'
        in schema
    )
    assert (
        'alter table app.contact_subscriptions add constraint uq_contact_subscriptions_tenant_id_id unique (tenant_id, id);'
        in schema
    )
    assert 'fk_contact_subscriptions_tenant_plan foreign key (tenant_id, plan_id)' in schema
    assert 'fk_contact_subscriptions_tenant_contact foreign key (tenant_id, contact_id)' in schema


def test_schema_enables_rls_and_registers_policies_for_subscriptions():
    schema = SCHEMA.read_text()
    assert 'alter table app.subscription_plans enable row level security;' in schema
    assert 'alter table app.contact_subscriptions enable row level security;' in schema
    # Both tables must be in the RLS-policy loop so the generic
    # tenant_select/insert/update/delete policies are attached.
    assert "'subscription_plans','contact_subscriptions'" in schema


def test_schema_extends_whatsapp_template_purpose_with_subscription_payment_failed():
    schema = SCHEMA.read_text()
    assert "'subscription_payment_failed'" in schema, (
        'whatsapp_templates.purpose check constraint must accept subscription_payment_failed'
    )


def test_schema_extends_reminder_jobs_target_type_with_contact_subscription():
    # BUG-134 (fix-group-23): el constraint también incluye ahora `'contact'`
    # para que el consent reaffirm job pueda enqueuear. La aserción ahora
    # valida los miembros uno por uno en vez de hacer match literal de la
    # tupla completa (que cambia cada vez que se extiende el dominio).
    schema = SCHEMA.read_text()
    rj_idx = schema.find('create table app.reminder_jobs (')
    assert rj_idx > 0
    rj_end = schema.find(');', rj_idx)
    rj_block = schema[rj_idx:rj_end]
    assert "target_type text not null check (target_type in" in rj_block
    for member in (
        "'appointment'",
        "'quote'",
        "'service_request'",
        "'conversation'",
        "'contact_subscription'",
        # BUG-134: nuevo miembro.
        "'contact'",
    ):
        assert member in rj_block, (
            f'reminder_jobs.target_type CHECK debe permitir {member}.'
        )


# ───── Service ─────────────────────────────────────────────────────────────


def test_service_constants_match_backlog():
    assert subscriptions_service.BILLING_PERIODS == ('monthly', 'quarterly', 'yearly')
    assert subscriptions_service.SUBSCRIPTION_STATUSES == ('active', 'past_due', 'cancelled')
    assert subscriptions_service.INVOICE_FAILED_TEMPLATE == 'subscription_payment_failed_v1'


def test_extract_subscription_event_stripe_invoice_succeeded_maps_to_active():
    event = subscriptions_service.extract_subscription_event(
        'stripe',
        {
            'type': 'invoice.payment_succeeded',
            'data': {
                'object': {
                    'subscription': 'sub_123',
                    'hosted_invoice_url': 'https://stripe.test/invoice/abc',
                    'next_payment_attempt': 1735689600,
                }
            },
        },
    )
    assert event is not None
    assert event.provider == 'stripe'
    assert event.provider_subscription_id == 'sub_123'
    assert event.new_status == 'active'
    assert event.event_kind == 'invoice.payment_succeeded'


def test_extract_subscription_event_stripe_invoice_failed_maps_to_past_due():
    event = subscriptions_service.extract_subscription_event(
        'stripe',
        {
            'type': 'invoice.payment_failed',
            'data': {
                'object': {
                    'subscription': 'sub_456',
                    'hosted_invoice_url': 'https://stripe.test/retry',
                }
            },
        },
    )
    assert event is not None
    assert event.new_status == 'past_due'
    assert event.retry_url == 'https://stripe.test/retry'


def test_extract_subscription_event_mercadopago_subscription_event():
    event = subscriptions_service.extract_subscription_event(
        'mercadopago',
        {
            'type': 'subscription_authorized_payment',
            'action': 'updated',
            'data': {
                'preapproval_id': 'MP-123',
                'status': 'rejected',
                'init_point': 'https://mp.test/retry',
            },
        },
    )
    assert event is not None
    assert event.provider == 'mercadopago'
    assert event.provider_subscription_id == 'MP-123'
    assert event.new_status == 'past_due'
    assert event.retry_url == 'https://mp.test/retry'


def test_extract_subscription_event_ignores_unrelated_payloads():
    # One-shot payment (not a subscription) must not be misread as one.
    assert subscriptions_service.extract_subscription_event(
        'stripe',
        {'type': 'checkout.session.completed', 'data': {'object': {}}},
    ) is None
    assert subscriptions_service.extract_subscription_event(
        'mercadopago',
        {'type': 'payment', 'data': {'id': 'pay-1', 'status': 'approved'}},
    ) is None


# ───── Pydantic schemas ────────────────────────────────────────────────────


def test_subscription_plan_create_enforces_billing_period_enum():
    plan = SubscriptionPlanCreate(
        name='Mensual',
        billing_period='monthly',
        price_amount=99.0,
        currency='COP',
    )
    assert plan.billing_period == 'monthly'
    assert plan.status == 'active'

    import pytest

    with pytest.raises(Exception):
        SubscriptionPlanCreate(name='x', billing_period='weekly', price_amount=10, currency='COP')


def test_contact_subscription_create_requires_provider():
    import pytest

    from uuid import uuid4

    sub = ContactSubscriptionCreate(
        contact_id=uuid4(),
        plan_id=uuid4(),
        payment_provider='stripe',
    )
    assert sub.payment_provider == 'stripe'

    with pytest.raises(Exception):
        ContactSubscriptionCreate(
            contact_id=uuid4(),
            plan_id=uuid4(),
            payment_provider='paypal',
        )


def test_contact_subscription_patch_status_enum():
    patch = ContactSubscriptionPatch(status='past_due')
    assert patch.status == 'past_due'

    import pytest

    with pytest.raises(Exception):
        ContactSubscriptionPatch(status='unknown')


def test_subscription_plan_update_is_partial():
    update = SubscriptionPlanUpdate(price_amount=120)
    assert update.model_dump(exclude_unset=True) == {'price_amount': 120}


# ───── Routes ──────────────────────────────────────────────────────────────


def test_routes_register_plan_crud_under_admin_router():
    src = ROUTES.read_text()
    assert "@tenant_admin_router.post('/subscription-plans', status_code=201)" in src
    assert "@tenant_admin_router.patch('/subscription-plans/{plan_id}')" in src
    assert "@tenant_admin_router.delete('/subscription-plans/{plan_id}', status_code=204)" in src
    assert "@tenant_ops_router.get('/subscription-plans')" in src


def test_routes_register_subscriber_endpoints_with_correct_auth_boundary():
    """SEC-008: GET stays on tenant_ops_router (agents read for the contact
    they're chatting with); POST/PATCH/DELETE move to tenant_admin_router
    (admin role required + MFA enforced) so an `agent` cannot fake/mutate
    paid subscriptions or cancel a customer's billing.
    """
    src = ROUTES.read_text()
    # GET stays on ops (read-only) — agents legitimately need this.
    assert "@tenant_ops_router.get('/subscriptions')" in src
    # POST/PATCH/DELETE require admin (router-level dependency).
    assert "@tenant_admin_router.post('/subscriptions', status_code=201)" in src
    assert "@tenant_admin_router.patch('/subscriptions/{subscription_id}')" in src
    assert "@tenant_admin_router.delete('/subscriptions/{subscription_id}', status_code=204)" in src
    # Negative: the mutating endpoints MUST NOT be on tenant_ops_router (agent).
    assert "@tenant_ops_router.post('/subscriptions'" not in src
    assert "@tenant_ops_router.patch('/subscriptions/" not in src
    assert "@tenant_ops_router.delete('/subscriptions/" not in src


def test_routes_register_subscriptions_webhook():
    src = ROUTES.read_text()
    assert "@webhook_router.post('/subscriptions/{provider}', status_code=202)" in src
    # The handler must hit our service translator and queue a reminder_jobs
    # entry when the invoice fails.
    assert 'extract_subscription_event(' in src
    assert "target_type, target_id, template_name" in src
    assert "INVOICE_FAILED_TEMPLATE" in src


def test_routes_audit_subscription_actions():
    src = ROUTES.read_text()
    for action in (
        "action='subscription_plan.created'",
        "action='subscription_plan.updated'",
        "action='subscription_plan.archived'",
        "action='contact_subscription.created'",
        "action='contact_subscription.updated'",
        "action='contact_subscription.cancelled'",
        "action='contact_subscription.invoice_webhook'",
    ):
        assert action in src, f'missing audit entry: {action}'


def test_routes_import_service_helpers():
    # The handler must import the service helpers we depend on.
    src_module = inspect.getsource(routes_module)
    assert 'from app.services.subscriptions import' in src_module
    assert 'extract_subscription_event' in src_module
    assert 'INVOICE_FAILED_TEMPLATE' in src_module


# ───── Admin panel ─────────────────────────────────────────────────────────


def test_admin_modules_registers_subscriptions_entry():
    # El marcador "TASK-0075" se removió del copy visible (sólo queda en
    # comentarios JSDoc). Verificamos el contrato del registro.
    src = ADMIN_MODULES.read_text()
    assert "id: 'subscriptions'" in src
    assert "capability: 'subscriptions.write'" in src
    assert 'Membresías con cobro recurrente' in src


def test_admin_layout_wires_subscriptions_module_with_admin_gate():
    src = ADMIN_LAYOUT.read_text()
    # UI-007.6: the registry now points at the redesigned feature module.
    assert (
        "import { Subscriptions } from '../features/owner-admin/subscriptions/index.js'"
        in src
    )
    assert 'subscriptions: {' in src
    # The legacy module path must be fully gone (no parallel implementation).
    assert 'components/modules/subscriptions/SubscriptionsModule' not in src
    # UI-003: el switch de ModuleContent se reemplazó por MODULE_REGISTRY; el
    # gate de capability vive en la entrada del registro (mode RW = admin/owner).
    assert "capability: 'subscriptions.write'" in src
    assert "mode: 'RW'" in src


def test_subscriptions_module_renders_plan_form_and_subscriber_lists():
    src = _subscriptions_feature_source()
    assert 'listSubscriptionPlans' in src
    assert 'listContactSubscriptions' in src
    assert 'createSubscriptionPlan' in src
    assert 'archiveSubscriptionPlan' in src
    assert 'cancelContactSubscription' in src
    # The retry link must surface in the past-due table for ops to inspect.
    assert 'retry_payment_link' in src


def test_core_api_exposes_subscription_endpoints():
    src = CORE_API.read_text()
    for fn in (
        'listSubscriptionPlans',
        'createSubscriptionPlan',
        'updateSubscriptionPlan',
        'archiveSubscriptionPlan',
        'listContactSubscriptions',
        'cancelContactSubscription',
    ):
        assert f'export function {fn}(' in src, f'missing coreApi export: {fn}'
