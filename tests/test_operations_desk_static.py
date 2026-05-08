from pathlib import Path

API_ROUTES = Path('app/api/v1/routes.py')
ADMIN_LAYOUT = Path('admin-panel/src/components/layout/AdminLayout.jsx')
OPERATIONS_DESK = Path('admin-panel/src/components/modules/operations/OperationsDesk.jsx')
CORE_API = Path('admin-panel/src/services/coreApi.js')


def test_operations_routes_support_handoff_accept_release_and_audit():
    source = API_ROUTES.read_text()

    assert "@tenant_ops_router.post('/conversations/start'" in source
    assert "action='conversation.started_by_agent'" in source
    assert 'operations.conversations.listed' in source
    assert 'operations.conversation.start_requested' in source
    assert 'operations.conversation.detail_not_found' in source
    assert 'await asyncio.sleep(0.1)' in source
    assert "@tenant_ops_router.post('/conversations/{conversation_id}/handoff/accept'" in source
    assert "where tenant_id=$1 and conversation_id=$2 and status='open'" in source
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
    assert 'Iniciar conversación' in component_source
    assert 'setConversationDetail(conversation)' in component_source
    assert 'conversationDetail?.id === selectedConversationId' in component_source
    assert 'Tomar conversación' in component_source
    assert 'Liberar al bot' in component_source
    assert 'startConversation' in api_source
    assert 'sendConversationMessage' in api_source
    assert 'acceptConversationHandoff' in api_source
    assert 'openConversationStream' in api_source
    assert 'new WebSocket' in api_source
    assert 'openConversationStream(session, tenant.id)' in component_source
    assert 'window.setInterval' not in component_source


def test_tenant_ops_reads_set_rls_context_from_requested_tenant():
    source = API_ROUTES.read_text()

    assert 'async def tenant_id_from_request' in source
    assert "request.state, 'requested_tenant_id', None" in source
    assert 'await ensure_tenant_access(request, tenant_id, conn)' in source
    assert "await conn.execute(\"select set_config('app.tenant_id', $1, true)\", str(tenant_id))" in source
