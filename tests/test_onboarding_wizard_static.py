"""TASK-0069: static tests for the self-service onboarding wizard.

Covers:
- backend constants & verifier table
- normalize_onboarding_progress helper
- DB schema column
- readiness endpoint emits onboarding_progress
- per-step verifier behavior (positive + negative)
- no-skip rule
- audit + domain_events emission on completion
- admin panel module registration + coreApi helpers
- React wizard renders 7 steps
"""

import asyncio
from pathlib import Path
from uuid import uuid4


ROUTES = Path('app/api/v1/routes.py')
SCHEMA = Path('infra/postgres/01-schema.sql')
CORE_API = Path('admin-panel/src/services/coreApi.js')
MODULES = Path('admin-panel/src/data/modules.js')
ADMIN_LAYOUT = Path('admin-panel/src/app/moduleRegistry.js')
# UI-007.2: the wizard was redesigned and moved to features/owner-admin/onboarding/.
ONBOARDING_DIR = Path('admin-panel/src/features/owner-admin/onboarding')
WIZARD = ONBOARDING_DIR / 'Onboarding.jsx'
WIZARD_STEPS = ONBOARDING_DIR / 'onboardingSteps.js'
WIZARD_STEP_COMPONENT = ONBOARDING_DIR / 'components' / 'OnboardingStep.jsx'


# ─────────────────────────────────────────────────────────────────────────────
# 1. Constants & schema
# ─────────────────────────────────────────────────────────────────────────────


def test_onboarding_constants_have_seven_steps():
    import app.api.v1.routes as routes
    assert routes.ONBOARDING_TOTAL_STEPS == 7
    assert tuple(routes.ONBOARDING_STEPS) == (1, 2, 3, 4, 5, 6, 7)
    keys = [routes.ONBOARDING_STEP_METADATA[n]['key'] for n in routes.ONBOARDING_STEPS]
    assert keys == [
        'business_details',
        'locale_currency',
        'whatsapp_channel',
        'consent_template',
        'service_catalog',
        'business_hours',
        'end_to_end_test',
    ]
    for n in routes.ONBOARDING_STEPS:
        assert n in routes.ONBOARDING_VERIFIERS
    assert routes.ONBOARDING_CONSENT_TEMPLATE_NAME == 'consent_request_v1'


def test_schema_declares_onboarding_progress_column():
    schema = SCHEMA.read_text()
    assert 'onboarding_progress jsonb not null default' in schema
    # Must live on tenant_settings, not on a brand-new table.
    settings_block = schema.split('create table app.tenant_settings')[1].split('create table')[0]
    assert 'onboarding_progress' in settings_block


def test_normalize_onboarding_progress_handles_garbage():
    from app.api.v1.routes import normalize_onboarding_progress, ONBOARDING_TOTAL_STEPS
    out = normalize_onboarding_progress(None)
    assert out['step'] == 1
    assert out['total'] == ONBOARDING_TOTAL_STEPS
    assert out['last_completed_step'] == 0
    assert out['complete'] is False
    assert out['steps'] == {}

    out2 = normalize_onboarding_progress({'last_completed_step': 99, 'steps': 'not-a-dict'})
    assert out2['last_completed_step'] == ONBOARDING_TOTAL_STEPS
    assert out2['complete'] is True
    assert out2['step'] == ONBOARDING_TOTAL_STEPS

    out3 = normalize_onboarding_progress({'last_completed_step': 3, 'steps': {'2': {'completed_at': 'x'}}})
    assert out3['last_completed_step'] == 3
    assert out3['step'] == 4
    assert out3['steps'] == {'2': {'completed_at': 'x'}}


def test_endpoints_registered_on_tenant_admin_router():
    source = ROUTES.read_text()
    assert "@tenant_admin_router.get('/tenants/{tenant_id}/onboarding')" in source
    assert "@tenant_admin_router.post('/tenants/{tenant_id}/onboarding/steps/{step}/verify')" in source
    assert "@tenant_admin_router.post('/tenants/{tenant_id}/onboarding/steps/{step}/complete')" in source
    assert "@tenant_admin_router.post('/tenants/{tenant_id}/onboarding/steps/7/send-test')" in source
    assert "action='tenant_onboarding.step_completed'" in source
    assert "'tenant_onboarding.step_completed'" in source  # domain_events emission


# ─────────────────────────────────────────────────────────────────────────────
# 2. Verifier behavior
# ─────────────────────────────────────────────────────────────────────────────


class FakeConn:
    """A minimal asyncpg-style stub keyed by `(method, query-fragment)`."""

    def __init__(self, fetchrow=None, fetch=None, fetchval=None, execute=None):
        self._fetchrow = fetchrow or {}
        self._fetch = fetch or {}
        self._fetchval = fetchval or {}
        self.executed = []

    async def fetchrow(self, query, *args):
        for fragment, value in self._fetchrow.items():
            if fragment in query:
                return value(args) if callable(value) else value
        raise AssertionError(f'unexpected fetchrow: {query}')

    async def fetch(self, query, *args):
        for fragment, value in self._fetch.items():
            if fragment in query:
                return value(args) if callable(value) else value
        raise AssertionError(f'unexpected fetch: {query}')

    async def fetchval(self, query, *args):
        for fragment, value in self._fetchval.items():
            if fragment in query:
                return value(args) if callable(value) else value
        raise AssertionError(f'unexpected fetchval: {query}')

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return None


def test_verifier_step1_business_details_missing_fields():
    from app.api.v1.routes import _verify_onboarding_business_details
    conn = FakeConn(fetchrow={
        'from app.tenants where id=$1': {
            'slug': 'demo', 'legal_name': '', 'display_name': 'Demo',
            'vertical_code': 'beauty', 'country_code': 'CO', 'timezone': 'America/Bogota',
            'status': 'active', 'deleted_at': None,
        },
    })
    ready, reason, details = asyncio.run(_verify_onboarding_business_details(conn, uuid4()))
    assert ready is False
    assert 'legal_name' in reason
    assert details['missing'] == ['legal_name']


def test_verifier_step1_business_details_ready():
    from app.api.v1.routes import _verify_onboarding_business_details
    conn = FakeConn(fetchrow={
        'from app.tenants where id=$1': {
            'slug': 'demo', 'legal_name': 'Demo SAS', 'display_name': 'Demo',
            'vertical_code': 'beauty', 'country_code': 'CO', 'timezone': 'America/Bogota',
            'status': 'active', 'deleted_at': None,
        },
    })
    ready, reason, _ = asyncio.run(_verify_onboarding_business_details(conn, uuid4()))
    assert ready is True
    assert 'completos' in reason


def test_verifier_step2_locale_currency_requires_all_three():
    from app.api.v1.routes import _verify_onboarding_locale_currency
    conn = FakeConn(fetchrow={
        'from app.tenants where id=$1': {'timezone': 'America/Bogota'},
        'from app.tenant_settings where tenant_id=$1': {
            'locale': 'es-CO', 'payment_settings': {},
        },
    })
    ready, reason, _ = asyncio.run(_verify_onboarding_locale_currency(conn, uuid4()))
    assert ready is False
    assert 'currency' in reason


def test_verifier_step3_whatsapp_requires_active_and_secrets(monkeypatch):
    import app.api.v1.routes as routes
    monkeypatch.setattr(routes, 'token_ref_is_configured', lambda r: True)
    monkeypatch.setattr(routes, 'secret_ref_is_configured', lambda r: True)
    conn = FakeConn(fetchrow={
        'from app.tenant_channels': {
            'business_id': 'biz', 'waba_id': 'waba', 'phone_number_id': 'phone',
            'token_ref': 'secrets/token', 'app_secret_ref': 'secrets/app',
            'verify_token_hash_configured': True, 'status': 'provisioning',
        },
    })
    ready, reason, _ = asyncio.run(routes._verify_onboarding_whatsapp_channel(conn, uuid4()))
    assert ready is False
    assert 'provisioning' in reason


def test_verifier_step3_whatsapp_token_invalid_blocks(monkeypatch):
    import app.api.v1.routes as routes
    monkeypatch.setattr(routes, 'token_ref_is_configured', lambda r: False)
    monkeypatch.setattr(routes, 'secret_ref_is_configured', lambda r: True)
    conn = FakeConn(fetchrow={
        'from app.tenant_channels': {
            'business_id': 'biz', 'waba_id': 'waba', 'phone_number_id': 'phone',
            'token_ref': 'secrets/token', 'app_secret_ref': 'secrets/app',
            'verify_token_hash_configured': True, 'status': 'active',
        },
    })
    ready, reason, _ = asyncio.run(routes._verify_onboarding_whatsapp_channel(conn, uuid4()))
    assert ready is False
    assert 'Token Meta' in reason


def test_verifier_step4_consent_template_requires_approval():
    from app.api.v1.routes import _verify_onboarding_consent_template
    conn = FakeConn(fetchrow={
        'from app.whatsapp_templates': {'status': 'pending'},
    })
    ready, reason, details = asyncio.run(_verify_onboarding_consent_template(conn, uuid4()))
    assert ready is False
    assert 'pending' in reason
    assert details['status'] == 'pending'


def test_verifier_step5_service_catalog_requires_at_least_one_active():
    from app.api.v1.routes import _verify_onboarding_service_catalog
    conn = FakeConn(fetchval={
        'from app.service_catalog': lambda args: 0,
    })
    ready, reason, _ = asyncio.run(_verify_onboarding_service_catalog(conn, uuid4()))
    assert ready is False
    assert 'al menos un servicio' in reason

    conn2 = FakeConn(fetchval={'from app.service_catalog': lambda args: 3})
    ready2, _, details = asyncio.run(_verify_onboarding_service_catalog(conn2, uuid4()))
    assert ready2 is True
    assert details['active_services'] == 3


def test_verifier_step6_business_hours_rejects_empty_payload():
    from app.api.v1.routes import _verify_onboarding_business_hours
    conn = FakeConn(fetchrow={
        'from app.tenant_settings': {'business_hours': {}},
    })
    ready, reason, _ = asyncio.run(_verify_onboarding_business_hours(conn, uuid4()))
    assert ready is False
    assert 'vacíos' in reason

    conn2 = FakeConn(fetchrow={
        'from app.tenant_settings': {'business_hours': {'monday': ['09:00-17:00']}},
    })
    ready2, _, details = asyncio.run(_verify_onboarding_business_hours(conn2, uuid4()))
    assert ready2 is True
    assert 'monday' in details['days_configured']


def test_verifier_step6_business_hours_inspects_weekly_schedule():
    """The TenantSetupWizard emits {timezone_strategy, weekly_schedule: {mon: [...]}}.

    The verifier MUST look inside weekly_schedule rather than treating the
    top-level keys as days, otherwise a fully empty schedule produced by the
    wizard would still pass because `timezone_strategy` is a truthy string.
    """
    from app.api.v1.routes import _verify_onboarding_business_hours
    empty_weekly = {
        'timezone_strategy': 'tenant_timezone',
        'weekly_schedule': {'mon': [], 'tue': [], 'wed': [], 'thu': [], 'fri': [], 'sat': [], 'sun': []},
    }
    conn = FakeConn(fetchrow={'from app.tenant_settings': {'business_hours': empty_weekly}})
    ready, reason, _ = asyncio.run(_verify_onboarding_business_hours(conn, uuid4()))
    assert ready is False
    assert 'Ningún día' in reason

    populated_weekly = {
        'timezone_strategy': 'tenant_timezone',
        'weekly_schedule': {'mon': [{'start': '09:00', 'end': '17:00'}], 'tue': []},
    }
    conn2 = FakeConn(fetchrow={'from app.tenant_settings': {'business_hours': populated_weekly}})
    ready2, _, details = asyncio.run(_verify_onboarding_business_hours(conn2, uuid4()))
    assert ready2 is True
    assert details['days_configured'] == ['mon']


def test_verifier_step7_end_to_end_requires_sent_and_inbound():
    from app.api.v1.routes import _verify_onboarding_end_to_end_test
    # No sent timestamp recorded yet.
    conn = FakeConn(fetchrow={
        'from app.tenant_settings': {
            'onboarding_progress': {'last_completed_step': 6, 'steps': {}},
        },
    })
    ready, reason, _ = asyncio.run(_verify_onboarding_end_to_end_test(conn, uuid4()))
    assert ready is False
    assert 'mensaje de prueba' in reason


def test_verifier_step7_rejects_inbound_from_other_contact():
    """An unrelated customer reply must NOT complete the E2E onboarding step.

    The verifier must filter inbound messages by the recorded admin wa_id, not
    just by tenant + timestamp.
    """
    from app.api.v1.routes import _verify_onboarding_end_to_end_test

    progress = {
        'last_completed_step': 6,
        'steps': {
            '7': {'test_message_sent_at': '2026-05-01T00:00:00+00:00', 'target_wa_id': '573001112233'},
        },
    }

    class Conn:
        async def fetchrow(self, query, *args):
            if 'from app.tenant_settings' in query:
                return {'onboarding_progress': progress}
            if 'from app.messages m' in query:
                # The verifier MUST pass the wa_id as the 3rd argument.
                assert args[2] == '573001112233', f'verifier did not filter by wa_id, got args={args}'
                return None  # no inbound from the admin contact
            raise AssertionError(query)

    ready, reason, details = asyncio.run(_verify_onboarding_end_to_end_test(Conn(), uuid4()))
    assert ready is False
    assert '573001112233' in reason
    assert details['target_wa_id'] == '573001112233'


def test_verifier_step7_accepts_inbound_from_matching_admin_contact():
    from app.api.v1.routes import _verify_onboarding_end_to_end_test
    from datetime import datetime, UTC as _UTC

    progress = {
        'last_completed_step': 6,
        'steps': {
            '7': {'test_message_sent_at': '2026-05-01T00:00:00+00:00', 'target_wa_id': '573001112233'},
        },
    }
    inbound_at = datetime.now(_UTC)

    class Conn:
        async def fetchrow(self, query, *args):
            if 'from app.tenant_settings' in query:
                return {'onboarding_progress': progress}
            if 'from app.messages m' in query:
                assert args[2] == '573001112233'
                return {'id': uuid4(), 'created_at': inbound_at, 'wa_id': '573001112233'}
            raise AssertionError(query)

    ready, reason, details = asyncio.run(_verify_onboarding_end_to_end_test(Conn(), uuid4()))
    assert ready is True
    assert 'inbound del wa_id del admin' in reason
    assert details['target_wa_id'] == '573001112233'
    assert details['inbound_message_id']


def test_verifier_step7_requires_recorded_target_wa_id():
    """If the wizard somehow records sent_at without target_wa_id, the verifier blocks."""
    from app.api.v1.routes import _verify_onboarding_end_to_end_test

    class Conn:
        async def fetchrow(self, query, *args):
            if 'from app.tenant_settings' in query:
                return {
                    'onboarding_progress': {
                        'last_completed_step': 6,
                        'steps': {'7': {'test_message_sent_at': '2026-05-01T00:00:00+00:00'}},
                    },
                }
            raise AssertionError(query)

    ready, reason, _ = asyncio.run(_verify_onboarding_end_to_end_test(Conn(), uuid4()))
    assert ready is False
    assert 'wa_id' in reason


# ─────────────────────────────────────────────────────────────────────────────
# 3. Readiness integration
# ─────────────────────────────────────────────────────────────────────────────


def test_readiness_response_includes_onboarding_progress(monkeypatch):
    import app.api.v1.routes as routes
    monkeypatch.setattr(routes, 'token_ref_is_configured', lambda r: True)
    monkeypatch.setattr(routes, 'secret_ref_is_configured', lambda r: True)
    monkeypatch.setattr(routes, 'build_grounded_answer', lambda *a, **kw: {'answer': 'ok', 'sufficient_context': True})
    monkeypatch.setattr(routes, 'rank_chunks', lambda *a, **kw: [])

    class Conn:
        async def fetchrow(self, query, *args):
            if 'from app.tenants' in query:
                return {'id': args[0], 'slug': 'demo', 'display_name': 'Demo', 'status': 'active', 'deleted_at': None}
            if 'from app.tenant_settings' in query:
                return {
                    'locale': 'es-CO',
                    'business_hours': {'monday': ['09:00-17:00']},
                    'escalation_policy': {
                        'enabled': True, 'queue': 'q',
                        'triggers': {'keywords': ['a'], 'after_bot_turns': 3},
                        'handoff_message': 'hi',
                    },
                    'pii_policy': {'no_train': True},
                    'no_train': True,
                    'onboarding_progress': {'last_completed_step': 3, 'steps': {'1': {}}},
                }
            if 'from app.tenant_channels' in query:
                return {
                    'id': uuid4(), 'provider': 'whatsapp_cloud_api',
                    'business_id': 'b', 'waba_id': 'w', 'phone_number_id': 'p',
                    'token_ref': 'r', 'app_secret_ref': 'r',
                    'verify_token_hash_configured': True, 'account_mode': 'live', 'status': 'active',
                }
            if 'count(distinct kd.id)' in query:
                return {'active_documents': 1, 'active_chunks': 1}
            raise AssertionError(query)

        async def fetch(self, query, *args):
            if 'from app.knowledge_chunks' in query:
                return []
            if 'from app.whatsapp_templates' in query:
                return []
            raise AssertionError(query)

        async def fetchval(self, query, *args):
            return 1

    report = asyncio.run(routes.build_tenant_readiness_report(Conn(), uuid4()))
    assert 'onboarding_progress' in report
    assert report['onboarding_progress']['last_completed_step'] == 3
    assert report['onboarding_progress']['step'] == 4
    assert report['onboarding_progress']['total'] == 7


# ─────────────────────────────────────────────────────────────────────────────
# 4. Admin panel wiring
# ─────────────────────────────────────────────────────────────────────────────


def test_admin_modules_registry_lists_onboarding_wizard():
    src = MODULES.read_text()
    assert "id: 'onboarding-wizard'" in src
    assert 'TASK-0069' in src


def test_core_api_exposes_onboarding_helpers():
    src = CORE_API.read_text()
    for fn in (
        'getTenantOnboarding',
        'verifyOnboardingStep',
        'completeOnboardingStep',
        'recordOnboardingTestMessageSent',
    ):
        assert f'export function {fn}' in src
    assert "/onboarding/steps/${step}/verify" in src
    assert "/onboarding/steps/${step}/complete" in src


def test_admin_layout_renders_onboarding_module():
    # UI-007.2: the registry now points at the redesigned feature module.
    src = ADMIN_LAYOUT.read_text()
    assert "from '../features/owner-admin/onboarding/index.js'" in src
    assert "'onboarding-wizard': {" in src
    assert 'Onboarding' in src
    # The legacy module path must be fully gone (no parallel implementation).
    assert 'components/modules/onboarding/OnboardingWizard' not in src


def test_wizard_component_declares_seven_step_flow():
    # UI-007.2: the 7-step catalogue moved to the pure `onboardingSteps.js`
    # helper; the API wiring lives in `Onboarding.jsx`; the blocked-state copy
    # lives in the per-step component.
    steps_src = WIZARD_STEPS.read_text()
    assert 'ONBOARDING_STEPS' in steps_src
    for key in (
        "key: 'business_details'",
        "key: 'locale_currency'",
        "key: 'whatsapp_channel'",
        "key: 'consent_template'",
        "key: 'service_catalog'",
        "key: 'business_hours'",
        "key: 'end_to_end_test'",
    ):
        assert key in steps_src

    wizard_src = WIZARD.read_text()
    assert 'getTenantOnboarding' in wizard_src
    assert 'verifyOnboardingStep' in wizard_src
    assert 'completeOnboardingStep' in wizard_src
    assert 'recordOnboardingTestMessageSent' in wizard_src

    # Mensaje claro de bloqueo cuando un paso anterior no está completo.
    assert 'Bloqueado' in wizard_src
    assert 'Bloqueado' in WIZARD_STEP_COMPONENT.read_text()
