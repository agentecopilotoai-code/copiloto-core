from pathlib import Path

EVENT_WORKER = Path('app/workers/event_worker.py')
WHATSAPP = Path('app/services/whatsapp.py')
WHATSAPP_ONBOARDING = Path('admin-panel/src/components/modules/whatsapp/WhatsAppOnboarding.jsx')
OPERATIONS_DESK = Path('admin-panel/src/components/modules/operations/OperationsDesk.jsx')
API_SCHEMAS = Path('app/api/v1/schemas.py')
API_ROUTES = Path('app/api/v1/routes.py')
DB_SCHEMA = Path('infra/postgres/01-schema.sql')


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
    assert "row['account_mode'] or 'mock'" in worker_source
    assert "delivery_mode: str = 'mock'" in service_source
    assert "if delivery_mode != 'live'" in service_source
    assert 'META_ACCESS_TOKEN is missing or configured as a local mock token' in service_source
    assert "account_mode: str = Field(default='mock', pattern='^(mock|live)$')" in schema_source
    assert 'account_mode=excluded.account_mode' in routes_source
    assert 'meta_access_token_configured' in routes_source
    assert 'delivery_ready' in routes_source
    assert "account_mode text not null default 'mock' check (account_mode in ('mock','live'))" in db_source


def test_whatsapp_onboarding_exposes_delivery_mode_toggle():
    source = WHATSAPP_ONBOARDING.read_text()

    assert "account_mode: 'mock'" in source
    assert 'Modo de entrega' in source
    assert 'Mock local (no envía a WhatsApp)' in source
    assert 'Real vía WhatsApp Cloud API' in source
    assert 'META_ACCESS_TOKEN real' in source
    assert 'Falta o es mock' in source
    assert 'Modo real: el worker llama a Meta usando META_ACCESS_TOKEN' in source


def test_operations_desk_explains_queued_sent_failed_statuses():
    source = OPERATIONS_DESK.read_text()

    assert 'queued/sent/failed' in source
    assert 'Simulado local: no salió a WhatsApp' in source
    assert 'Aceptado por WhatsApp' in source
