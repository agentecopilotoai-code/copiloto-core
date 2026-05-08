from pathlib import Path

EVENT_WORKER = Path('app/workers/event_worker.py')
WHATSAPP = Path('app/services/whatsapp.py')
WHATSAPP_ONBOARDING = Path('admin-panel/src/components/modules/whatsapp/WhatsAppOnboarding.jsx')
OPERATIONS_DESK = Path('admin-panel/src/components/modules/operations/OperationsDesk.jsx')
CORE_API = Path('admin-panel/src/services/coreApi.js')
API_SCHEMAS = Path('app/api/v1/schemas.py')
API_ROUTES = Path('app/api/v1/routes.py')
DB_SCHEMA = Path('infra/postgres/01-schema.sql')
DOCKER_COMPOSE = Path('docker-compose.yml')


def test_worker_marks_delivery_failures_and_logs_provider_result():
    source = EVENT_WORKER.read_text()

    assert "'message_delivery_attempt'" in source
    assert "'message_delivery_sent'" in source
    assert "'message_delivery_mocked'" in source
    assert "'message_delivery_failed'" in source
    assert "pg_notify('tenant_operations_events'" in source
    assert 'm.conversation_id' in source
    assert "status='failed'" in source
    assert 'failed_at=now()' in source
    assert 'error_message=$2' in source


def test_whatsapp_delivery_mode_controls_mocking_per_tenant_channel():
    worker_source = EVENT_WORKER.read_text()
    service_source = WHATSAPP.read_text()
    schema_source = API_SCHEMAS.read_text()
    routes_source = API_ROUTES.read_text()
    db_source = DB_SCHEMA.read_text()

    assert 'c.account_mode' in worker_source
    assert 'c.token_ref' in worker_source
    assert "row['account_mode'] or 'mock'" in worker_source
    assert "row['token_ref']" in worker_source
    assert "delivery_mode: str = 'mock'" in service_source
    assert "if delivery_mode != 'live'" in service_source
    assert 'resolve_secret_ref' in service_source
    assert "ref.startswith('secrets/')" in service_source
    assert "'..' in Path(secret_name).parts" in service_source
    assert 'os.getenv' not in service_source
    assert 'fallback_env' not in service_source
    assert 'verify_signature(body' not in service_source
    assert 'normalize_meta_app_secret' in service_source
    assert 'token_ref did not resolve to a real Meta access token' in service_source
    assert "account_mode: str = Field(default='mock', pattern='^(mock|live)$')" in schema_source
    assert 'token_ref: str' not in schema_source
    assert 'app_secret_ref: str' not in schema_source
    assert 'account_mode=excluded.account_mode' in routes_source
    assert 'meta_access_token_configured' in routes_source
    assert 'app_secret_configured' in routes_source
    assert 'verify_token_configured' in routes_source
    assert 'delivery_ready' in routes_source
    assert "token_ref = tenant_secret_ref(tenant_id, 'meta_access_token')" in routes_source
    assert "app_secret_ref = tenant_secret_ref(tenant_id, 'whatsapp_app_secret')" in routes_source
    assert "verify_token_ref = tenant_secret_ref(tenant_id, 'whatsapp_verify_token')" in routes_source
    assert "write_tenant_secret(verify_token_ref, payload.verify_token)" in routes_source
    assert "resolve_secret_ref(tenant_secret_ref(row['tenant_id'], 'whatsapp_verify_token'))" in routes_source
    assert 'verify_token_hash(hub_verify_token)' not in routes_source
    assert 'verify_signature_with_secret' in routes_source
    assert 'whatsapp_phone_number_id_from_payload(payload)' in routes_source
    assert 'select id, tenant_id, app_secret_ref' in routes_source
    assert "resolve_secret_ref(channel['app_secret_ref'])" in routes_source
    assert "select set_config('app.tenant_id', $1, true)" in routes_source
    assert 'insert into app.webhook_events_raw (tenant_id, provider, event_type, headers, payload, payload_sha256)' in routes_source
    assert "channel['tenant_id']" in routes_source
    assert "raise HTTPException(status_code=404, detail='WhatsApp channel not found')" in routes_source
    assert "settings.whatsapp_app_secret" not in routes_source
    assert "account_mode text not null default 'mock' check (account_mode in ('mock','live'))" in db_source


def test_whatsapp_onboarding_exposes_delivery_mode_toggle():
    source = WHATSAPP_ONBOARDING.read_text()

    assert 'defaultFormForTenant' in source
    assert 'token_ref' not in source
    assert 'app_secret_ref' not in source
    assert 'Modo de entrega' in source
    assert 'Mock local (no envía a WhatsApp)' in source
    assert 'Real vía WhatsApp Cloud API' in source
    assert 'Meta access token del tenant' in source
    assert 'App secret del tenant' in source
    assert 'APP_ID|APP_SECRET' in source
    assert 'Verify token del webhook' in source
    assert 'whatsapp_verify_token' in source
    assert 'Falta o es mock' in source
    assert 'Modo real: el worker llama a Meta usando el secreto meta_access_token del tenant' in source
    assert 'secrets/tenants/<tenant_id>/meta_access_token' in source
    assert 'El usuario solo pega los tres valores secretos' in source


def test_operations_desk_explains_queued_sent_failed_statuses():
    source = OPERATIONS_DESK.read_text()

    assert 'queued/sent/failed' in source
    assert 'Simulado local: no salió a WhatsApp' in source
    assert 'Aceptado por WhatsApp' in source
    assert 'openConversationStream' in source
    assert 'new WebSocket' in CORE_API.read_text()
    assert 'window.setInterval' not in source
    assert "payload.type !== 'conversation.changed'" in source
    assert 'refreshDetail(currentConversationId, true)' in source
    assert 'messageThreadRef' in source


def test_compose_mounts_secrets_for_api_and_worker():
    source = DOCKER_COMPOSE.read_text()

    assert './.secrets:/app/.secrets' in source
    assert './.secrets:/app/.secrets:ro' in source
    assert 'command: python3 -m app.workers.event_worker' in source


def test_whatsapp_media_messages_supported_in_both_agent_flows_and_worker():
    worker_source = EVENT_WORKER.read_text()
    service_source = WHATSAPP.read_text()
    schema_source = API_SCHEMAS.read_text()
    routes_source = API_ROUTES.read_text()
    operations_source = OPERATIONS_DESK.read_text()

    assert 'send_whatsapp_message' in service_source
    assert "MEDIA_MESSAGE_TYPES = {'image', 'audio', 'video'}" in service_source
    assert "payload[normalized_type] = media_object" in service_source
    assert "media_object['link'] = media_url.strip()" in service_source
    assert "media_object['caption']" in service_source
    assert 'm.message_type, m.media_id, m.mime_type, m.payload' in worker_source
    assert "message_payload.get('media_url')" in worker_source
    assert "message_payload.get('caption')" in worker_source
    assert "initial_message_type: str = Field(default='text', pattern='^(text|image|audio|video)$')" in schema_source
    assert 'initial_media_id: str | None = None' in schema_source
    assert 'initial_media_url: str | None = None' in schema_source
    assert "message_type: str = Field(default='text', pattern='^(text|image|audio|video|document|interactive|template|system)$')" in schema_source
    assert 'media_id: str | None = None' in schema_source
    assert 'validate_outbound_message_content' in routes_source
    assert 'payload.initial_message_type' in routes_source
    assert 'payload.initial_media_id' in routes_source
    assert 'media_url_from_payload(message_payload)' in routes_source
    assert 'messageMedia' in operations_source
    assert '<option value="image">Imagen</option>' in operations_source
    assert '<option value="video">Video</option>' in operations_source
    assert '<option value="audio">Audio</option>' in operations_source
    assert 'renderMessageContent(message)' in operations_source


def test_whatsapp_webhook_persists_inbound_media_metadata():
    routes_source = API_ROUTES.read_text()

    assert "media_payload = message.get(message_type)" in routes_source
    assert "media_id = media_payload.get('id')" in routes_source
    assert "mime_type = media_payload.get('mime_type')" in routes_source
    assert "body_text = media_payload.get('caption')" in routes_source
    assert 'body_text, message_type, media_id, mime_type, payload, status, received_at' in routes_source
