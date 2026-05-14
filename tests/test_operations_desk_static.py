from pathlib import Path

API_ROUTES = Path('app/api/v1/routes.py')
ADMIN_LAYOUT = Path('admin-panel/src/app/moduleRegistry.js')
OPERATIONS_DESK = Path('admin-panel/src/features/agente/inbox')
CORE_API = Path('admin-panel/src/services/coreApi.js')
ADMIN_ROUTES = Path('app/admin/routes.py')


def _operations_desk_source() -> str:
    """Combined source of the Operación · Inbox feature dir (UI-009.1 split).

    OperationsDesk.jsx (2088 LOC) was split into features/agente/inbox/; the
    static assertions below run against the concatenated feature source.
    """
    return '\n'.join(p.read_text() for p in sorted(OPERATIONS_DESK.rglob('*.js*')))


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
    component_source = _operations_desk_source()
    api_source = CORE_API.read_text()

    assert "import { OperationsDesk }" in layout_source
    assert "'operations-desk': {" in layout_source
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


def test_operations_websocket_authorizes_tenant_role_from_database_and_backoff_reconnects():
    admin_source = ADMIN_ROUTES.read_text()
    component_source = _operations_desk_source()

    assert 'async def _session_can_stream_tenant' in admin_source
    assert 'join app.user_tenant_roles utr on utr.user_id = u.id' in admin_source
    assert 'where u.auth_subject=$1 and utr.tenant_id=$2' in admin_source
    assert "tenant_agent_role_required" in admin_source
    assert 'streamSocketRef' in component_source
    assert 'streamReconnectAttemptRef' in component_source
    assert 'Math.min(30000' in component_source
    assert 'event.code === 1008' in component_source
    assert "session?.api?.baseUrl" in component_source
