"""Static tests for TASK-0055 — Tracking de referido entre contactos.

Coverage:
- Schema: ``contacts.referrer_contact_id`` column, tenant-scoped composite FK,
  check constraint preventing self-reference, index for referrer lookups.
- Booking flow: optional ``awaiting_referrer`` step gated on
  ``notification_settings.ask_referrer``; free-text answer resolved either
  by phone substring, name match, or stored as ``lead_source.referred_by_name``.
- Web widget: ``data-ref`` attribute and ``?ref=`` query parameter forwarded
  to ``/v1/web/chat/start`` as ``referrer_contact_id``.
- Endpoint: ``GET /v1/analytics/referrals`` returning top 20 referrers with
  ``count_referrals``, ``appointments_generated`` and ``revenue_generated``.
- Contact profile: ``referrals.referred_by`` + ``referred_contacts``.
- Admin Panel: AnalyticsPanel surfaces the top-referrers card; ContactsModule
  surfaces the referidos panel; TenantSetupWizard exposes the toggle.
"""
from __future__ import annotations

import inspect
from pathlib import Path

from app.api.v1 import routes as routes_module
from app.api.v1.schemas import WebChatStart
from app.services import booking_flow, notifications

SCHEMA = Path('infra/postgres/01-schema.sql')
ROUTES = Path('app/api/v1/routes.py')
BOOKING_FLOW = Path('app/services/booking_flow.py')
WIDGET_JS = Path('admin-panel/public/widget.js')
ANALYTICS_PANEL = Path('admin-panel/src/features/owner-admin/analytics/AnalyticsPanel.jsx')
# UI-007.3: the contacts module was split into a feature directory.
CONTACTS_FEATURE = Path('admin-panel/src/features/owner-admin/conversations-contacts')
TENANT_SETUP_FEATURE = Path('admin-panel/src/features/owner-admin/tenant-setup')

def _tenant_setup_source() -> str:
    return '\n'.join(p.read_text() for p in sorted(TENANT_SETUP_FEATURE.rglob('*.js*')))

CORE_API = Path('admin-panel/src/services/coreApi.js')


def _contacts_feature_source() -> str:
    return '\n'.join(
        path.read_text() for path in sorted(CONTACTS_FEATURE.rglob('*.js*'))
    )


# ───── Schema ──────────────────────────────────────────────────────────────


def test_schema_adds_referrer_contact_id_column_and_check():
    schema = SCHEMA.read_text()
    assert 'referrer_contact_id uuid,' in schema
    # Self-reference is rejected at the row level.
    assert (
        'constraint chk_contacts_referrer_not_self '
        'check (referrer_contact_id is null or referrer_contact_id <> id)'
    ) in schema


def test_schema_indexes_contacts_referrer_for_top_lookups():
    schema = SCHEMA.read_text()
    assert (
        'create index ix_contacts_tenant_referrer on app.contacts'
        '(tenant_id, referrer_contact_id) where referrer_contact_id is not null'
    ) in schema


def test_schema_declares_tenant_scoped_self_fk_for_referrer():
    schema = SCHEMA.read_text()
    assert 'fk_contacts_referrer' in schema
    # Composite FK targets contacts(tenant_id, id) so referrals cannot cross
    # tenants; deleting the referrer falls back to null.
    assert 'foreign key (tenant_id, referrer_contact_id)' in schema
    assert 'references app.contacts(tenant_id, id) on delete set null' in schema


# ───── Notification settings defaults ──────────────────────────────────────


def test_default_notification_settings_include_ask_referrer_false():
    assert 'ask_referrer' in notifications.DEFAULT_NOTIFICATION_SETTINGS
    # Default must stay opt-in so existing tenants are unaffected.
    assert notifications.DEFAULT_NOTIFICATION_SETTINGS['ask_referrer'] is False


# ───── Booking flow ────────────────────────────────────────────────────────


def test_booking_flow_declares_awaiting_referrer_step():
    assert booking_flow.STEP_AWAITING_REFERRER == 'awaiting_referrer'


def test_ask_referrer_enabled_reads_notification_settings_flag():
    source = inspect.getsource(booking_flow._ask_referrer_enabled)
    assert "notification_settings->>'ask_referrer'" in source
    assert 'from app.tenant_settings' in source


def test_resolve_referrer_answer_matches_by_phone_then_name_then_freetext():
    source = inspect.getsource(booking_flow._resolve_referrer_answer)
    # phone substring lookup
    assert "phone_e164 like '%' || $3" in source
    # case-insensitive display_name fallback
    assert 'lower(display_name) like' in source
    # free-text fallback into lead_source.referred_by_name
    assert "jsonb_build_object('referred_by_name', $3::text)" in source
    # never self-link
    assert 'id <> $2' in source


def test_resolve_referrer_answer_skips_on_no_or_empty_response():
    # Skip tokens cover the most common ways a customer says "no one".
    for token in ('no', 'nadie', 'ninguno', 'n/a', 'skip', ''):
        assert token in booking_flow.REFERRER_SKIP_TOKENS or token == ''


def test_maybe_run_booking_flow_asks_referrer_before_services():
    source = inspect.getsource(booking_flow.maybe_run_booking_flow)
    # The booking entry point gates the ask on the tenant flag and skips when
    # the contact already has a referrer recorded.
    assert '_ask_referrer_enabled' in source
    assert '_contact_has_referrer' in source
    # The free-text reply handler runs before the standard service step.
    assert "state.get('step') == STEP_AWAITING_REFERRER" in source
    assert '_resolve_referrer_answer' in source


def test_contact_has_referrer_covers_id_and_freetext_fallback():
    # Has explicit referrer_contact_id → True.
    assert booking_flow._contact_has_referrer({'referrer_contact_id': 'x'}) is True
    # Has lead_source.referred_by_name → True.
    assert booking_flow._contact_has_referrer(
        {'referrer_contact_id': None, 'lead_source': {'referred_by_name': 'María'}}
    ) is True
    # Empty contact → False so the booking flow asks.
    assert booking_flow._contact_has_referrer(
        {'referrer_contact_id': None, 'lead_source': {}}
    ) is False
    assert booking_flow._contact_has_referrer(None) is False


# ───── Web widget ──────────────────────────────────────────────────────────


def test_widget_js_reads_data_ref_and_query_ref():
    source = WIDGET_JS.read_text()
    assert "scriptEl.getAttribute('data-ref')" in source
    assert "params.get('ref')" in source
    # The lead-start payload forwards the referrer.
    assert 'referrer_contact_id: readReferrerContactId()' in source


def test_webchat_start_schema_accepts_referrer_contact_id():
    fields = WebChatStart.model_fields
    assert 'referrer_contact_id' in fields
    # Optional — the snippet does not always provide one.
    assert fields['referrer_contact_id'].default is None


def test_web_chat_start_persists_referrer_when_valid_same_tenant():
    source = inspect.getsource(routes_module.web_chat_start)
    # Validate the referrer belongs to the same tenant before linking.
    assert 'payload.referrer_contact_id' in source
    assert "select 1 from app.contacts where tenant_id=$1 and id=$2" in source
    # Insert column is wired through.
    assert 'referrer_contact_id' in source


# ───── Analytics endpoint ──────────────────────────────────────────────────


def test_referrals_endpoint_registered_on_analytics_router():
    paths = {
        getattr(r, 'path', '')
        for r in routes_module.tenant_analytics_router.routes
        if hasattr(r, 'path')
    }
    assert '/analytics/referrals' in paths


def test_analytics_referrals_query_shape_and_limits():
    source = inspect.getsource(routes_module.analytics_referrals)
    # Range plumbing matches the rest of the analytics endpoints.
    assert '_resolve_analytics_range' in source
    assert '_range_bounds' in source
    # Aggregates the three required metrics.
    assert 'count_referrals' in source
    assert 'appointments_generated' in source
    assert 'revenue_generated' in source
    # Top 20 referrers cap matches the spec.
    assert 'limit 20' in source
    # Revenue computation joins the service catalog price.
    assert 'app.service_catalog s' in source
    # Only completed appointments count.
    assert "a.status = 'completed'" in source


def test_contact_profile_exposes_referrals_block():
    source = inspect.getsource(routes_module.get_contact_profile)
    assert "'referrals'" in source
    assert 'referred_by' in source
    assert 'referred_contacts' in source
    assert 'where tenant_id=$1 and referrer_contact_id=$2' in source


# ───── Admin panel ─────────────────────────────────────────────────────────


def test_core_api_exposes_analytics_referrals():
    source = CORE_API.read_text()
    assert 'export function getAnalyticsReferrals' in source
    assert "/analytics/referrals" in source


def test_analytics_panel_renders_top_referrers_card():
    source = ANALYTICS_PANEL.read_text()
    assert 'getAnalyticsReferrals' in source
    assert 'data-testid="analytics-top-referrers"' in source
    assert 'Top referidores' in source


def test_contacts_module_renders_referrals_panel():
    source = _contacts_feature_source()
    assert 'data-testid="contact-referrals-panel"' in source
    # UI-007.3 split: ContactTimeline destructures `profile.referrals` before
    # reading `referred_by` / `referred_contacts`.
    assert 'referred_by' in source
    assert 'referred_contacts' in source


def test_wizard_exposes_ask_referrer_toggle():
    source = _tenant_setup_source()
    assert 'ask_referrer: false' in source
    assert 'data-wizard-field="ask_referrer"' in source
    assert 'notificationSettings.ask_referrer === true' in source
