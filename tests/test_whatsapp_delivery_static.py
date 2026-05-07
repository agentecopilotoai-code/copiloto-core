from pathlib import Path

EVENT_WORKER = Path('app/workers/event_worker.py')
WHATSAPP = Path('app/services/whatsapp.py')
OPERATIONS_DESK = Path('admin-panel/src/components/modules/operations/OperationsDesk.jsx')


def test_worker_marks_delivery_failures_and_logs_provider_result():
    source = EVENT_WORKER.read_text()

    assert "'message_delivery_attempt'" in source
    assert "'message_delivery_sent'" in source
    assert "'message_delivery_mocked'" in source
    assert "'message_delivery_failed'" in source
    assert "status='failed'" in source
    assert 'failed_at=now()' in source
    assert 'error_message=$2' in source


def test_local_mock_token_does_not_call_meta_graph_api():
    source = WHATSAPP.read_text()

    assert "startswith('local-mock')" in source
    assert "'mocked': True" in source


def test_operations_desk_explains_queued_sent_failed_statuses():
    source = OPERATIONS_DESK.read_text()

    assert 'queued/sent/failed' in source
    assert 'Simulado local: no salió a WhatsApp' in source
    assert 'Aceptado por WhatsApp' in source
