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


def test_admin_panel_exposes_go_live_readiness_module():
    assert 'getTenantReadiness' in CORE_API.read_text()
    assert "id: 'go-live-readiness'" in MODULES.read_text()
    ui = READINESS_UI.read_text()
    assert 'Generar reporte' in ui
    assert 'Razones de not_ready' in ui
    assert 'getTenantReadiness' in ui
