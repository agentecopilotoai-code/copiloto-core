from pathlib import Path

ROUTES = Path('app/api/v1/routes.py')
CORE_API = Path('admin-panel/src/services/coreApi.js')
READINESS_UI = Path('admin-panel/src/components/modules/readiness/GoLiveReadiness.jsx')
MODULES = Path('admin-panel/src/data/modules.js')


def test_readiness_endpoint_returns_ready_or_not_ready_report():
    source = ROUTES.read_text()
    assert "@tenant_admin_router.get('/tenants/{tenant_id}/readiness')" in source
    assert "'status': 'ready' if ready else 'not_ready'" in source
    assert "'reasons': reasons" in source
    assert "action='tenant.readiness_checked'" in source


def test_readiness_checks_cover_go_live_scope():
    source = ROUTES.read_text()
    for key in [
        'tenant_active',
        'tenant_settings',
        'whatsapp_channel',
        'knowledge_retrieval',
        'handoff',
        'audit',
    ]:
        assert f"'{key}'" in source
    assert 'rank_chunks(smoke_question' in source
    assert 'build_grounded_answer(smoke_question' in source
    assert 'token_ref_is_configured' in source
    assert 'secret_ref_is_configured' in source
    assert "channel['account_mode'] == 'live'" in source


def test_admin_panel_exposes_go_live_readiness_module():
    assert 'getTenantReadiness' in CORE_API.read_text()
    assert "id: 'go-live-readiness'" in MODULES.read_text()
    ui = READINESS_UI.read_text()
    assert 'Generar reporte' in ui
    assert 'Razones de not_ready' in ui
    assert 'getTenantReadiness' in ui


def test_readiness_report_handles_nullable_legacy_settings_without_500():
    import asyncio
    from uuid import uuid4

    from app.api.v1.routes import build_tenant_readiness_report

    class FakeConnection:
        async def fetchrow(self, query, *args):
            if 'from app.tenants' in query:
                return {
                    'id': args[0],
                    'slug': 'demo',
                    'display_name': 'Demo',
                    'status': 'active',
                    'deleted_at': None,
                }
            if 'from app.tenant_settings' in query:
                return {
                    'locale': 'es-CO',
                    'business_hours': {},
                    'escalation_policy': None,
                    'pii_policy': {'no_train': True},
                    'no_train': True,
                    'max_bot_turns': None,
                }
            if 'from app.tenant_channels' in query:
                return None
            if 'count(distinct kd.id)' in query:
                return {'active_documents': 0, 'active_chunks': 0}
            raise AssertionError(f'unexpected fetchrow query: {query}')

        async def fetch(self, query, *args):
            if 'from app.knowledge_chunks' in query:
                return []
            raise AssertionError(f'unexpected fetch query: {query}')

        async def fetchval(self, query, *args):
            if 'from app.audit_logs' in query:
                return None
            raise AssertionError(f'unexpected fetchval query: {query}')

    report = asyncio.run(build_tenant_readiness_report(FakeConnection(), uuid4()))

    assert report['status'] == 'not_ready'
    settings_check = next(check for check in report['checks'] if check['key'] == 'tenant_settings')
    assert settings_check['ready'] is False


def test_readiness_requires_live_whatsapp_mode_even_when_secrets_are_configured(monkeypatch):
    import asyncio
    from uuid import uuid4

    import app.api.v1.routes as routes

    monkeypatch.setattr(routes, 'token_ref_is_configured', lambda token_ref: True)
    monkeypatch.setattr(routes, 'secret_ref_is_configured', lambda secret_ref: True)

    class FakeConnection:
        async def fetchrow(self, query, *args):
            if 'from app.tenants' in query:
                return {
                    'id': args[0],
                    'slug': 'demo',
                    'display_name': 'Demo',
                    'status': 'active',
                    'deleted_at': None,
                }
            if 'from app.tenant_settings' in query:
                return {
                    'locale': 'es-CO',
                    'business_hours': {'monday': ['09:00-17:00']},
                    'escalation_policy': {'handoff_required': True},
                    'pii_policy': {'no_train': True},
                    'no_train': True,
                    'max_bot_turns': 8,
                }
            if 'from app.tenant_channels' in query:
                return {
                    'id': uuid4(),
                    'provider': 'whatsapp_cloud_api',
                    'business_id': 'business-123',
                    'waba_id': 'waba-123',
                    'phone_number_id': 'phone-123',
                    'token_ref': 'secrets/token',
                    'app_secret_ref': 'secrets/app-secret',
                    'verify_token_hash_configured': True,
                    'account_mode': 'mock',
                    'status': 'active',
                }
            if 'count(distinct kd.id)' in query:
                return {'active_documents': 0, 'active_chunks': 0}
            raise AssertionError(f'unexpected fetchrow query: {query}')

        async def fetch(self, query, *args):
            if 'from app.knowledge_chunks' in query:
                return []
            raise AssertionError(f'unexpected fetch query: {query}')

        async def fetchval(self, query, *args):
            if 'from app.audit_logs' in query:
                return 1
            raise AssertionError(f'unexpected fetchval query: {query}')

    report = asyncio.run(routes.build_tenant_readiness_report(FakeConnection(), uuid4()))

    whatsapp_check = next(check for check in report['checks'] if check['key'] == 'whatsapp_channel')
    assert whatsapp_check['ready'] is False
    assert whatsapp_check['details']['delivery_mode_live'] is False
    assert 'modo live' in whatsapp_check['reason']
