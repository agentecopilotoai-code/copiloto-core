from pathlib import Path

EVENT_WORKER = Path('app/workers/event_worker.py')
WHATSAPP = Path('app/services/whatsapp.py')
WHATSAPP_ONBOARDING = Path('admin-panel/src/components/modules/whatsapp/WhatsAppOnboarding.jsx')
OPERATIONS_DESK = Path('admin-panel/src/components/modules/operations/OperationsDesk.jsx')
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


def test_compose_mounts_secrets_for_api_and_worker():
    source = DOCKER_COMPOSE.read_text()

    assert './.secrets:/app/.secrets' in source
    assert './.secrets:/app/.secrets:ro' in source
    assert 'command: python3 -m app.workers.event_worker' in source
