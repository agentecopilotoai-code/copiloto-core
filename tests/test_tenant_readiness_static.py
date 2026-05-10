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


def _make_fake_connection(escalation_policy, account_mode='live', audit_count=1, max_bot_turns=8):
    from uuid import uuid4

    class FakeConn:
        async def fetchrow(self, query, *args):
            if 'from app.tenants' in query:
                return {'id': args[0], 'slug': 'demo', 'display_name': 'Demo', 'status': 'active', 'deleted_at': None}
            if 'from app.tenant_settings' in query:
                return {
                    'locale': 'es-CO',
                    'business_hours': {'monday': ['09:00-17:00']},
                    'escalation_policy': escalation_policy,
                    'pii_policy': {'no_train': True},
                    'no_train': True,
                    'max_bot_turns': max_bot_turns,
                }
            if 'from app.tenant_channels' in query:
                return {
                    'id': uuid4(),
                    'provider': 'whatsapp_cloud_api',
                    'business_id': 'biz-1',
                    'waba_id': 'waba-1',
                    'phone_number_id': 'phone-1',
                    'token_ref': 'secrets/token',
                    'app_secret_ref': 'secrets/app-secret',
                    'verify_token_hash_configured': True,
                    'account_mode': account_mode,
                    'status': 'active',
                }
            if 'count(distinct kd.id)' in query:
                return {'active_documents': 1, 'active_chunks': 5}
            raise AssertionError(f'unexpected fetchrow: {query}')

        async def fetch(self, query, *args):
            if 'from app.knowledge_chunks' in query:
                return [
                    {
                        'id': '00000000-0000-0000-0000-000000000001',
                        'document_id': '00000000-0000-0000-0000-000000000002',
                        'document_title': 'Test doc',
                        'source_uri': None,
                        'source_type': 'manual',
                        'document_type': 'reference',
                        'visibility': 'tenant',
                        'chunk_index': 0,
                        'section_path': None,
                        'chunk_text': 'horarios de atención lunes a viernes',
                        'token_count': 10,
                        'metadata': {},
                    }
                ]
            raise AssertionError(f'unexpected fetch: {query}')

        async def fetchval(self, query, *args):
            if 'from app.audit_logs' in query:
                return audit_count
            raise AssertionError(f'unexpected fetchval: {query}')

    return FakeConn()


def test_handoff_readiness_passes_with_full_modern_policy(monkeypatch):
    import asyncio
    from uuid import uuid4
    import app.api.v1.routes as routes

    monkeypatch.setattr(routes, 'token_ref_is_configured', lambda ref: True)
    monkeypatch.setattr(routes, 'secret_ref_is_configured', lambda ref: True)
    monkeypatch.setattr(routes, 'build_grounded_answer', lambda *a, **kw: {'answer': 'ok', 'sufficient_context': True})
    monkeypatch.setattr(routes, 'rank_chunks', lambda *a, **kw: [])

    policy = {
        'queue': 'default-support',
        'enabled': True,
        'priority': 'normal',
        'triggers': {
            'keywords': ['humano', 'asesor', 'agente', 'reclamo'],
            'after_bot_turns': 5,
            'confidence_below': 0.55,
        },
        'handoff_message': 'Te conecto con una persona del equipo para ayudarte mejor.',
    }
    report = asyncio.run(routes.build_tenant_readiness_report(_make_fake_connection(policy), uuid4()))
    handoff_check = next(c for c in report['checks'] if c['key'] == 'handoff')
    assert handoff_check['ready'] is True, f'Expected ready but got: {handoff_check["reason"]}'
    assert handoff_check['reason'] == 'Política de handoff configurada.'


def test_handoff_readiness_fails_when_enabled_false(monkeypatch):
    import asyncio
    from uuid import uuid4
    import app.api.v1.routes as routes

    monkeypatch.setattr(routes, 'token_ref_is_configured', lambda ref: True)
    monkeypatch.setattr(routes, 'secret_ref_is_configured', lambda ref: True)
    monkeypatch.setattr(routes, 'build_grounded_answer', lambda *a, **kw: {'answer': 'ok', 'sufficient_context': True})
    monkeypatch.setattr(routes, 'rank_chunks', lambda *a, **kw: [])

    policy = {
        'queue': 'default-support',
        'enabled': False,
        'triggers': {'keywords': ['humano'], 'after_bot_turns': 5},
        'handoff_message': 'Te conecto con alguien.',
    }
    report = asyncio.run(routes.build_tenant_readiness_report(_make_fake_connection(policy), uuid4()))
    handoff_check = next(c for c in report['checks'] if c['key'] == 'handoff')
    assert handoff_check['ready'] is False
    assert 'enabled=false' in handoff_check['reason']


def test_handoff_readiness_fails_when_policy_absent(monkeypatch):
    import asyncio
    from uuid import uuid4
    import app.api.v1.routes as routes

    monkeypatch.setattr(routes, 'token_ref_is_configured', lambda ref: True)
    monkeypatch.setattr(routes, 'secret_ref_is_configured', lambda ref: True)
    monkeypatch.setattr(routes, 'build_grounded_answer', lambda *a, **kw: {'answer': 'ok', 'sufficient_context': True})
    monkeypatch.setattr(routes, 'rank_chunks', lambda *a, **kw: [])

    report = asyncio.run(routes.build_tenant_readiness_report(_make_fake_connection(None), uuid4()))
    handoff_check = next(c for c in report['checks'] if c['key'] == 'handoff')
    assert handoff_check['ready'] is False
    assert 'ausente' in handoff_check['reason']


def test_handoff_readiness_fails_when_no_queue(monkeypatch):
    import asyncio
    from uuid import uuid4
    import app.api.v1.routes as routes

    monkeypatch.setattr(routes, 'token_ref_is_configured', lambda ref: True)
    monkeypatch.setattr(routes, 'secret_ref_is_configured', lambda ref: True)
    monkeypatch.setattr(routes, 'build_grounded_answer', lambda *a, **kw: {'answer': 'ok', 'sufficient_context': True})
    monkeypatch.setattr(routes, 'rank_chunks', lambda *a, **kw: [])

    policy = {
        'enabled': True,
        'triggers': {'keywords': ['humano'], 'after_bot_turns': 5},
        'handoff_message': 'Te conecto.',
    }
    report = asyncio.run(routes.build_tenant_readiness_report(_make_fake_connection(policy), uuid4()))
    handoff_check = next(c for c in report['checks'] if c['key'] == 'handoff')
    assert handoff_check['ready'] is False
    assert 'queue' in handoff_check['reason']


def test_handoff_readiness_fails_when_no_triggers_and_no_message(monkeypatch):
    import asyncio
    from uuid import uuid4
    import app.api.v1.routes as routes

    monkeypatch.setattr(routes, 'token_ref_is_configured', lambda ref: True)
    monkeypatch.setattr(routes, 'secret_ref_is_configured', lambda ref: True)
    monkeypatch.setattr(routes, 'build_grounded_answer', lambda *a, **kw: {'answer': 'ok', 'sufficient_context': True})
    monkeypatch.setattr(routes, 'rank_chunks', lambda *a, **kw: [])

    policy = {'enabled': True, 'queue': 'default-support'}
    report = asyncio.run(routes.build_tenant_readiness_report(_make_fake_connection(policy), uuid4()))
    handoff_check = next(c for c in report['checks'] if c['key'] == 'handoff')
    assert handoff_check['ready'] is False
    assert 'triggers' in handoff_check['reason']


def test_handoff_readiness_passes_with_legacy_handoff_required(monkeypatch):
    import asyncio
    from uuid import uuid4
    import app.api.v1.routes as routes

    monkeypatch.setattr(routes, 'token_ref_is_configured', lambda ref: True)
    monkeypatch.setattr(routes, 'secret_ref_is_configured', lambda ref: True)
    monkeypatch.setattr(routes, 'build_grounded_answer', lambda *a, **kw: {'answer': 'ok', 'sufficient_context': True})
    monkeypatch.setattr(routes, 'rank_chunks', lambda *a, **kw: [])

    policy = {'handoff_required': True}
    report = asyncio.run(routes.build_tenant_readiness_report(_make_fake_connection(policy), uuid4()))
    handoff_check = next(c for c in report['checks'] if c['key'] == 'handoff')
    assert handoff_check['ready'] is True
    assert 'legacy' in handoff_check['reason']


def test_readiness_ui_has_escalation_navigation():
    ui = READINESS_UI.read_text()
    assert 'onGoToEscalation' in ui
    assert 'Ir a Escalamiento' in ui
    assert 'Aplicar política mínima recomendada' in ui
    assert 'updateTenantSettings' in ui


def test_tenant_setup_wizard_accepts_initial_tab():
    source = Path('admin-panel/src/components/modules/tenantSetup/TenantSetupWizard.jsx').read_text()
    assert 'initialTab' in source
