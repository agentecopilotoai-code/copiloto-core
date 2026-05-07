from pathlib import Path

API_ROUTES = Path('app/api/v1/routes.py')
ADMIN_LAYOUT = Path('admin-panel/src/components/layout/AdminLayout.jsx')
OPERATIONS_DESK = Path('admin-panel/src/components/modules/operations/OperationsDesk.jsx')
CORE_API = Path('admin-panel/src/services/coreApi.js')


def test_operations_routes_support_handoff_accept_release_and_audit():
    source = API_ROUTES.read_text()

    assert "@tenant_ops_router.post('/conversations/{conversation_id}/handoff/accept'" in source
    assert "action='handoff.accepted'" in source
    assert "action='conversation.released'" in source
    assert "set status='human_active'" in source
    assert "set status='resolved', updated_at=now()" in source


def test_admin_panel_mounts_operations_desk_module():
    layout_source = ADMIN_LAYOUT.read_text()
    component_source = OPERATIONS_DESK.read_text()
    api_source = CORE_API.read_text()

    assert "import { OperationsDesk }" in layout_source
    assert "activeModuleId === 'operations-desk'" in layout_source
    assert 'Tomar conversación' in component_source
    assert 'Liberar al bot' in component_source
    assert 'sendConversationMessage' in api_source
    assert 'acceptConversationHandoff' in api_source
