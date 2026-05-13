"""Static tests for TASK-0065 — Dead-letter queue de mensajes outbound.

Covers:
- Schema extends ``operator_alerts.kind`` with ``outbound_dlq_threshold``.
- Settings expose ``dlq_alert_threshold`` and ``dlq_alert_window_minutes``.
- Prometheus counter ``cpi_outbound_dlq_total`` exists and is exported via
  ``record_outbound_dlq``.
- ``event_worker`` records the DLQ counter and persists ``error_code`` on
  failure.
- ``outbound_dlq.list_dlq`` groups by ``error_code`` (the 12×131026 acceptance
  case) and clamps ``limit``.
- ``outbound_dlq.requeue_message`` resets the row to ``queued``, clears the
  error fields and emits a ``message.queued`` domain event idempotently.
- ``outbound_dlq.maybe_emit_dlq_threshold_alerts`` enqueues an operator alert
  with kind ``outbound_dlq_threshold`` once the count crosses the threshold,
  with up to 5 previews, and is debounced inside the window.
- ``infra/observability/alerts.yaml`` ships the ``OutboundDLQGrowing`` rule.
- Admin Panel renders the ``OutboundDLQ`` module and the navigation registers
  it in the sidebar.
- API endpoints ``GET /v1/tenants/{id}/outbound/dlq`` and
  ``POST .../retry`` are wired against the operations router.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.services.metrics import record_outbound_dlq
from app.services.outbound_dlq import (
    count_recent_failures,
    list_dlq,
    maybe_emit_dlq_threshold_alerts,
    normalize_error_code,
    requeue_message,
)


SCHEMA = Path('infra/postgres/01-schema.sql')
ALERTS_YAML = Path('infra/observability/alerts.yaml')
ROUTES = Path('app/api/v1/routes.py')
EVENT_WORKER = Path('app/workers/event_worker.py')
SCHEDULER = Path('app/workers/scheduler.py')
METRICS = Path('app/services/metrics.py')
ADMIN_LAYOUT = Path('admin-panel/src/components/layout/AdminLayout.jsx')
ADMIN_MODULES = Path('admin-panel/src/data/modules.js')
DLQ_PANEL = Path('admin-panel/src/components/modules/outbound/OutboundDLQ.jsx')
CORE_API = Path('admin-panel/src/services/coreApi.js')


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://example')
    monkeypatch.setenv('JWT_SECRET', 'local-secret-with-min-length')
    monkeypatch.setenv('SERVICE_TOKEN', 'service-token-with-min-length')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 's3-secret')
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ───── Schema, config, metric ──────────────────────────────────────────────


def test_schema_adds_outbound_dlq_threshold_kind():
    source = SCHEMA.read_text()
    assert (
        "kind in ('negative_feedback','complaint','backup_failure','outbound_dlq_threshold')"
        in source
    )


def test_settings_expose_dlq_alert_thresholds():
    settings = get_settings()
    assert settings.dlq_alert_threshold == 10
    assert 1 <= settings.dlq_alert_window_minutes <= 1440
    assert settings.dlq_alert_window_minutes == 60


def test_metric_cpi_outbound_dlq_total_declared_in_registry():
    source = METRICS.read_text()
    assert "cpi_outbound_dlq_total" in source
    assert "labelnames=('tenant_id', 'error_code')" in source
    assert 'def record_outbound_dlq' in source


def test_record_outbound_dlq_normalizes_blank_to_transport_error():
    # Smoke that calling the recorder with weird inputs does not raise.
    record_outbound_dlq(tenant_id=uuid4(), error_code=None)
    record_outbound_dlq(tenant_id=uuid4(), error_code='')
    record_outbound_dlq(tenant_id=uuid4(), error_code='131026')


def test_normalize_error_code_collapses_empty_to_transport():
    assert normalize_error_code(None) == 'transport_error'
    assert normalize_error_code('') == 'transport_error'
    assert normalize_error_code('  ') == 'transport_error'
    assert normalize_error_code(131026) == '131026'
    assert normalize_error_code('190') == '190'


# ───── event_worker wiring ─────────────────────────────────────────────────


def test_event_worker_records_dlq_and_persists_error_code():
    source = EVENT_WORKER.read_text()
    assert 'from app.services.metrics import' in source
    assert 'record_outbound_dlq' in source
    assert 'delivery_error_code' in source
    # The UPDATE on failure must now write `error_code` alongside `error_message`.
    assert "set status='failed', failed_at=now(), error_message=$2, error_code=$3" in source


def test_event_worker_extracts_meta_error_code_from_httpx_status():
    """``delivery_error_code`` parses Meta's JSON ``error.code`` and falls back
    to ``transport_error`` when there is no HTTPStatusError to inspect."""
    from app.workers.event_worker import delivery_error_code

    class _Resp:
        status_code = 400

        def json(self):
            return {'error': {'code': 131026, 'message': 'Recipient unreachable'}}

    class _HTTPStatusError(Exception):
        def __init__(self):
            self.response = _Resp()

    # Monkey-patch isinstance check by subclassing httpx.HTTPStatusError instead.
    import httpx

    class _Real(httpx.HTTPStatusError):
        def __init__(self):
            self.response = _Resp()  # type: ignore[assignment]

    err = _Real()
    assert delivery_error_code(err) == '131026'
    assert delivery_error_code(RuntimeError('boom')) == 'transport_error'


# ───── list_dlq + count_recent_failures ────────────────────────────────────


class _Conn:
    """Minimal asyncpg-like double that returns canned ``fetch`` rows."""

    def __init__(self):
        self.calls: list[tuple[str, tuple]] = []
        self.totals_rows: list[dict] = []
        self.items_rows: list[dict] = []
        self.alert_inserts: list[dict] = []
        self.executes: list[tuple[str, tuple]] = []
        self.preview_rows: list[dict] = []
        self.tenants: list[dict] = []
        self.existing_alert_for_tenant: dict[str, bool] = {}
        self._fetch_outcomes: list[list[dict]] | None = None

    async def fetch(self, query, *args):
        self.calls.append((query, args))
        # Order matters: each fetch in list_dlq returns totals then items.
        if 'group by 1' in query and 'limit' not in query and 'preview' not in query.lower():
            return self.totals_rows
        if 'select distinct m.tenant_id' in query:
            return self.tenants
        if 'order by coalesce(m.failed_at, m.created_at) desc' in query and 'limit 5' in query:
            return self.preview_rows
        if 'order by coalesce(m.failed_at, m.created_at) desc' in query:
            return self.items_rows
        return []

    async def fetchrow(self, query, *args):
        return None

    async def fetchval(self, query, *args):
        if "kind='outbound_dlq_threshold'" in query:
            return self.existing_alert_for_tenant.get(str(args[0]))
        return None

    async def execute(self, query, *args):
        self.executes.append((query, args))
        return None


def test_list_dlq_groups_by_error_code_and_clamps_limit():
    conn = _Conn()
    # 12 messages with 131026 + 1 with transport_error to assert the
    # acceptance criterion (count=12 for 131026).
    conn.totals_rows = [
        {'error_code': '131026', 'count': 12},
        {'error_code': 'transport_error', 'count': 1},
    ]
    conn.items_rows = [
        {
            'id': uuid4(),
            'conversation_id': uuid4(),
            'message_type': 'text',
            'body_text': 'hola',
            'error_code': '131026',
            'error_message': 'recipient unreachable',
            'failed_at': datetime.now(UTC),
            'created_at': datetime.now(UTC),
            'payload': {'k': 'v'},
            'contact_phone': '+5730099991234',
        }
    ]
    result = asyncio.run(
        list_dlq(
            conn,
            tenant_id=uuid4(),
            limit=999_999,  # ensure clamp at 500
        )
    )
    totals = result['totals_by_error_code']
    assert {t['error_code']: t['count'] for t in totals}['131026'] == 12
    assert result['items'][0]['error_code'] == '131026'
    assert result['items'][0]['contact_phone_last4'] == '1234'
    # The clamp shows up as the final ``$N`` parameter on the items query.
    items_query, items_params = conn.calls[-1]
    assert items_params[-1] == 500


def test_count_recent_failures_returns_total_and_preview():
    conn = _Conn()
    conn.totals_rows = [
        {'error_code': '131026', 'count': 8},
        {'error_code': '190', 'count': 3},
    ]
    conn.preview_rows = [
        {
            'id': uuid4(),
            'error_code': '190',
            'error_message': 'token expired',
            'at': datetime.now(UTC),
        }
    ]
    stats = asyncio.run(
        count_recent_failures(conn, tenant_id=uuid4(), window_minutes=60)
    )
    assert stats['total'] == 11
    assert stats['window_minutes'] == 60
    assert any(group['error_code'] == '131026' for group in stats['by_error_code'])
    assert stats['preview'] and stats['preview'][0]['error_code'] == '190'


# ───── requeue_message ─────────────────────────────────────────────────────


class _RequeueConn:
    def __init__(self, *, status='failed', direction='outbound', found=True):
        self.status = status
        self.direction = direction
        self.found = found
        self.executes: list[tuple[str, tuple]] = []

    async def fetchrow(self, query, *args):
        if not self.found:
            return None
        return {
            'id': args[1],
            'status': self.status,
            'direction': self.direction,
        }

    async def execute(self, query, *args):
        self.executes.append((query, args))
        return None


def test_requeue_message_resets_status_and_emits_domain_event():
    conn = _RequeueConn()
    tenant_id = uuid4()
    message_id = uuid4()
    result = asyncio.run(
        requeue_message(
            conn,
            tenant_id=tenant_id,
            message_id=message_id,
            requested_by='operator-7',
        )
    )
    assert result['requeued'] is True
    # First execute resets the row; second inserts the domain event.
    update_query, update_args = conn.executes[0]
    insert_query, insert_args = conn.executes[1]
    assert "update app.messages" in update_query
    assert "set status='queued'" in update_query
    assert 'error_code=null' in update_query
    assert 'error_message=null' in update_query
    assert "insert into app.domain_events" in insert_query
    assert "'message.queued'" in insert_query
    # The idempotency key carries the message id so reattempts collide cleanly.
    assert insert_args[2].startswith(f'message-retry:{message_id}:')


def test_requeue_message_is_idempotent_for_already_queued():
    conn = _RequeueConn(status='queued')
    result = asyncio.run(
        requeue_message(conn, tenant_id=uuid4(), message_id=uuid4())
    )
    assert result == {'requeued': False, 'reason': 'already_queued'}
    assert conn.executes == []


def test_requeue_message_returns_not_found():
    conn = _RequeueConn(found=False)
    result = asyncio.run(requeue_message(conn, tenant_id=uuid4(), message_id=uuid4()))
    assert result == {'requeued': False, 'reason': 'not_found'}


# ───── threshold alert ─────────────────────────────────────────────────────


def test_maybe_emit_dlq_threshold_alerts_fires_once_when_over_threshold():
    conn = _Conn()
    tenant_a = uuid4()
    conn.tenants = [{'tenant_id': tenant_a}]
    conn.totals_rows = [
        {'error_code': '131026', 'count': 12},
        {'error_code': '190', 'count': 1},
    ]
    conn.preview_rows = [
        {
            'id': uuid4(),
            'error_code': '131026',
            'error_message': 'recipient unreachable',
            'at': datetime.now(UTC),
        }
    ]
    enqueued: list[dict] = []

    async def fake_enqueue(c, *, tenant_id, kind, payload):
        enqueued.append({'tenant_id': tenant_id, 'kind': kind, 'payload': payload})
        return uuid4()

    emitted = asyncio.run(
        maybe_emit_dlq_threshold_alerts(
            conn,
            threshold=10,
            window_minutes=60,
            enqueue_alert=fake_enqueue,
        )
    )
    assert emitted == 1
    assert enqueued[0]['kind'] == 'outbound_dlq_threshold'
    payload = enqueued[0]['payload']
    assert payload['total'] == 13
    assert payload['threshold'] == 10
    assert payload['window_minutes'] == 60
    assert any(g['error_code'] == '131026' for g in payload['by_error_code'])
    assert payload['preview']


def test_maybe_emit_dlq_threshold_alerts_skips_below_threshold():
    conn = _Conn()
    conn.tenants = [{'tenant_id': uuid4()}]
    conn.totals_rows = [{'error_code': '131026', 'count': 3}]
    conn.preview_rows = []

    async def fake_enqueue(c, **kwargs):
        raise AssertionError('should not enqueue when below threshold')

    emitted = asyncio.run(
        maybe_emit_dlq_threshold_alerts(
            conn,
            threshold=10,
            window_minutes=60,
            enqueue_alert=fake_enqueue,
        )
    )
    assert emitted == 0


def test_maybe_emit_dlq_threshold_alerts_debounces_existing_alert():
    conn = _Conn()
    tenant_a = uuid4()
    conn.tenants = [{'tenant_id': tenant_a}]
    conn.totals_rows = [{'error_code': '131026', 'count': 25}]
    conn.preview_rows = []
    conn.existing_alert_for_tenant = {str(tenant_a): True}

    async def fake_enqueue(c, **kwargs):
        raise AssertionError('debounce broken')

    emitted = asyncio.run(
        maybe_emit_dlq_threshold_alerts(
            conn,
            threshold=10,
            window_minutes=60,
            enqueue_alert=fake_enqueue,
        )
    )
    assert emitted == 0


# ───── Scheduler + Prometheus rule ─────────────────────────────────────────


def test_scheduler_invokes_dlq_threshold_check_each_tick():
    source = SCHEDULER.read_text()
    assert 'from app.services.outbound_dlq import maybe_emit_dlq_threshold_alerts' in source
    assert 'await maybe_emit_dlq_threshold_alerts(' in source
    assert 'threshold=settings.dlq_alert_threshold' in source
    assert 'window_minutes=settings.dlq_alert_window_minutes' in source


def test_alerts_yaml_ships_outbound_dlq_growing_rule():
    yaml = ALERTS_YAML.read_text()
    assert 'alert: OutboundDLQGrowing' in yaml
    assert 'cpi_outbound_dlq_total' in yaml
    # Spec acceptance: >5 fails in 5 min.
    assert 'increase(cpi_outbound_dlq_total[5m])) > 5' in yaml


# ───── API wiring ──────────────────────────────────────────────────────────


def test_routes_register_dlq_endpoints_on_operations_router():
    source = ROUTES.read_text()
    assert "@tenant_ops_router.get('/tenants/{tenant_id}/outbound/dlq')" in source
    assert (
        "@tenant_ops_router.post('/tenants/{tenant_id}/outbound/dlq/{message_id}/retry')"
        in source
    )
    # The retry handler must audit the manual operation.
    assert "action='outbound.dlq.retried'" in source


# ───── Admin Panel ─────────────────────────────────────────────────────────


def test_admin_panel_registers_outbound_dlq_module():
    modules = ADMIN_MODULES.read_text()
    assert "id: 'outbound-dlq'" in modules
    assert 'Outbound DLQ' in modules

    layout = ADMIN_LAYOUT.read_text()
    assert "from '../modules/outbound/OutboundDLQ.jsx'" in layout
    assert "activeModuleId === 'outbound-dlq'" in layout


def test_outbound_dlq_panel_renders_filter_and_retry_action():
    panel = DLQ_PANEL.read_text()
    assert 'listOutboundDlq' in panel
    assert 'retryOutboundDlqMessage' in panel
    # Filter chips and retry button hooks for QA selectors.
    assert 'data-error-code' in panel
    assert 'data-action="retry"' in panel
    assert 'data-module="outbound-dlq"' in panel


def test_core_api_exposes_dlq_helpers():
    core = CORE_API.read_text()
    assert 'export function listOutboundDlq(' in core
    assert 'export function retryOutboundDlqMessage(' in core
    assert '/outbound/dlq' in core
