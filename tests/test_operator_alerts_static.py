"""Static tests for TASK-0057 — Operator alerts on negative feedback / complaints.

Covers:
- Schema (table + RLS + check constraint + scheduler tick).
- Notification settings include ``complaint_alert_channels`` defaults.
- ``operator_alerts`` helpers (channel normalization, HMAC, comment preview,
  desk link, email/whatsapp bodies).
- ``enqueue_operator_alert`` skips when no channels are configured and inserts
  otherwise.
- ``dispatch_operator_alert`` calls each sender exactly once when configured
  and aggregates per-channel errors.
- ``process_pending_operator_alerts`` retries with exponential backoff and
  marks ``failed`` after ``alerts_max_attempts``.
- Admin Panel renders the "Alertas al equipo" block + normalizer.
- ``_escalate_negative_feedback`` enqueues the alert with the rating, comment
  preview, conversation URL and ``contact_name``.
"""
from __future__ import annotations

import asyncio
import hmac
import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from app.core.config import Settings, get_settings
from app.services.notifications import DEFAULT_NOTIFICATION_SETTINGS, normalize_notification_settings
from app.services.operator_alerts import (
    ALERT_KIND_NEGATIVE_FEEDBACK,
    WHATSAPP_ALERT_TEMPLATE,
    build_comment_preview,
    build_desk_link,
    build_email_body,
    build_email_message,
    build_whatsapp_template_components,
    channels_configured,
    dispatch_operator_alert,
    enqueue_operator_alert,
    next_retry_at,
    normalize_alert_channels,
    process_pending_operator_alerts,
    sign_webhook_payload,
)
from app.services.feedback_flow import maybe_record_feedback


SCHEMA = Path('infra/postgres/01-schema.sql')
SCHEDULER = Path('app/workers/scheduler.py')
ADMIN_PANEL = Path('admin-panel/src/components/modules/tenantSetup/TenantSetupWizard.jsx')


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://example')
    monkeypatch.setenv('JWT_SECRET', 'local-secret-with-min-length')
    monkeypatch.setenv('SERVICE_TOKEN', 'service-token-with-min-length')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 's3-secret')
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# ───── Schema ──────────────────────────────────────────────────────────────


def test_schema_creates_operator_alerts_table_with_rls():
    source = SCHEMA.read_text()
    assert 'create table app.operator_alerts (' in source
    assert "kind text not null check (kind in ('negative_feedback','complaint'))" in source
    assert "status text not null default 'pending' check (status in ('pending','sent','failed'))" in source
    assert 'attempts integer not null default 0' in source
    assert 'scheduled_for timestamptz not null default now()' in source
    assert 'alter table app.operator_alerts enable row level security' in source
    assert "'operator_alerts'" in source  # in policy loop array
    assert 'trg_operator_alerts_touch' in source
    assert 'ix_operator_alerts_due' in source


def test_scheduler_processes_operator_alerts_each_tick():
    source = SCHEDULER.read_text()
    assert 'from app.services.operator_alerts import process_pending_operator_alerts' in source
    assert 'await process_pending_operator_alerts(conn)' in source


# ───── Settings defaults ───────────────────────────────────────────────────


def test_default_notification_settings_include_complaint_channels():
    assert 'complaint_alert_channels' in DEFAULT_NOTIFICATION_SETTINGS
    assert DEFAULT_NOTIFICATION_SETTINGS['complaint_alert_channels'] == {
        'email': [],
        'whatsapp': [],
        'webhook_url': '',
    }


def test_normalize_alert_channels_keeps_three_keys():
    out = normalize_alert_channels({'email': ['a@b.com', '  ', 'c@d.com'], 'whatsapp': None})
    assert out == {'email': ['a@b.com', 'c@d.com'], 'whatsapp': [], 'webhook_url': ''}
    assert normalize_alert_channels('not a dict') == {'email': [], 'whatsapp': [], 'webhook_url': ''}
    assert channels_configured({'email': [], 'whatsapp': [], 'webhook_url': ''}) is False
    assert channels_configured({'email': ['x@y.com']}) is True


def test_normalize_notification_settings_merges_complaint_channels():
    merged = normalize_notification_settings({'complaint_alert_channels': {'email': ['ops@example.com']}})
    assert merged['complaint_alert_channels'] == {'email': ['ops@example.com']}


# ───── Helpers: previews, signing, builders ────────────────────────────────


def test_build_comment_preview_truncates():
    long = 'a' * 500
    out = build_comment_preview(long, limit=80)
    assert len(out) == 80
    assert out.endswith('…')
    assert build_comment_preview(None) == ''
    assert build_comment_preview('  hola  ') == 'hola'


def test_build_desk_link_handles_optional_conversation():
    tid = UUID('11111111-1111-1111-1111-111111111111')
    cid = UUID('22222222-2222-2222-2222-222222222222')
    assert build_desk_link(None, tid, cid) == ''
    assert (
        build_desk_link('https://panel.example.com/', tid, cid)
        == f'https://panel.example.com/admin?tenant={tid}#operations/{cid}'
    )
    assert (
        build_desk_link('https://panel.example.com', tid, None)
        == f'https://panel.example.com/admin?tenant={tid}#operations'
    )


def test_sign_webhook_payload_uses_hmac_sha256():
    body = b'{"hello":"world"}'
    signed = sign_webhook_payload('s3cr3t', body)
    expected = hmac.new(b's3cr3t', body, hashlib.sha256).hexdigest()
    assert signed == f'sha256={expected}'
    assert sign_webhook_payload(None, body) is None
    assert sign_webhook_payload('', body) is None


def test_build_email_body_includes_rating_and_link():
    subject, body = build_email_body({
        'contact_name': 'Ana',
        'rating': 1,
        'comment_preview': 'pésimo',
        'conversation_url': 'https://panel/x',
    })
    assert 'Ana' in subject
    assert '1/5' in subject
    assert 'pésimo' in body
    assert 'https://panel/x' in body


def test_build_email_message_sets_headers():
    msg = build_email_message(
        sender='ops@copilotoia.com',
        recipients=['m@e.com', 'd@e.com'],
        subject='Alerta',
        body='Hola',
    )
    assert msg['From'] == 'ops@copilotoia.com'
    assert msg['To'] == 'm@e.com, d@e.com'
    assert msg['Subject'] == 'Alerta'
    assert msg.get_content().strip() == 'Hola'


def test_build_whatsapp_template_components_uses_four_vars():
    components = build_whatsapp_template_components({
        'contact_name': 'Bob',
        'rating': 2,
        'comment_preview': 'tarde',
        'conversation_url': 'https://x',
    })
    assert components[0]['type'] == 'body'
    params = components[0]['parameters']
    assert [p['text'] for p in params] == ['Bob', '2/5', 'tarde', 'https://x']


# ───── enqueue / dispatch / worker loop ────────────────────────────────────


class _Conn:
    def __init__(self, *, notification_settings=None, channel_id=None):
        self.notification_settings = notification_settings
        self.channel_id = channel_id
        self.inserted_alerts: list[dict] = []
        self.alert_updates: list[tuple[str, tuple]] = []
        self.message_inserts: list[dict] = []
        self.fetch_rows: list[dict] = []
        self.fetched = []

    async def fetchval(self, query, *args):
        if 'select notification_settings from app.tenant_settings' in query:
            return self.notification_settings
        if "from app.tenant_channels" in query and "whatsapp_cloud_api" in query:
            return self.channel_id
        if 'select display_name from app.contacts' in query:
            return 'Lucía'
        return None

    async def fetchrow(self, query, *args):
        if 'insert into app.operator_alerts' in query:
            row_id = uuid4()
            payload = json.loads(args[2])
            self.inserted_alerts.append({
                'id': row_id,
                'tenant_id': args[0],
                'kind': args[1],
                'payload': payload,
            })
            return {'id': row_id}
        return None

    async def fetch(self, query, *args):
        if 'update app.operator_alerts' in query and 'returning *' in query:
            return self.fetch_rows
        return []

    async def execute(self, query, *args):
        if 'insert into app.messages' in query:
            self.message_inserts.append({'tenant_id': args[0], 'payload': json.loads(args[1])})
            return None
        if 'update app.operator_alerts' in query:
            self.alert_updates.append((query, args))
            return None
        self.fetched.append((query, args))
        return None


def test_enqueue_skips_when_no_channels_configured():
    conn = _Conn(notification_settings={})
    alert_id = asyncio.run(
        enqueue_operator_alert(
            conn,
            tenant_id=uuid4(),
            kind=ALERT_KIND_NEGATIVE_FEEDBACK,
            payload={'rating': 1},
        )
    )
    assert alert_id is None
    assert conn.inserted_alerts == []


def test_enqueue_persists_when_channels_configured():
    conn = _Conn(
        notification_settings={
            'complaint_alert_channels': {
                'email': ['m@e.com'],
                'whatsapp': ['+57300'],
                'webhook_url': 'https://x',
            }
        }
    )
    alert_id = asyncio.run(
        enqueue_operator_alert(
            conn,
            tenant_id=uuid4(),
            kind=ALERT_KIND_NEGATIVE_FEEDBACK,
            payload={'rating': 1, 'contact_name': 'Ana'},
        )
    )
    assert alert_id is not None
    assert conn.inserted_alerts and conn.inserted_alerts[0]['kind'] == ALERT_KIND_NEGATIVE_FEEDBACK
    payload = conn.inserted_alerts[0]['payload']
    assert payload['channels']['email'] == ['m@e.com']
    assert payload['contact_name'] == 'Ana'


def test_dispatch_invokes_each_channel_sender_once():
    seen = {'email': 0, 'whatsapp': 0, 'webhook': 0}

    async def email_sender(_cfg, *, recipients, payload):
        seen['email'] += 1
        assert recipients == ['m@e.com']

    async def whatsapp_sender(_conn, *, tenant_id, recipients, payload):
        seen['whatsapp'] += 1
        assert recipients == ['+5730']
        return len(recipients)

    async def webhook_sender(*, tenant_id, url, payload):
        seen['webhook'] += 1
        assert url == 'https://x'

    alert_row = {
        'id': uuid4(),
        'tenant_id': uuid4(),
        'payload': {
            'channels': {
                'email': ['m@e.com'],
                'whatsapp': ['+5730'],
                'webhook_url': 'https://x',
            },
            'rating': 1,
        },
        'attempts': 1,
    }
    cfg = Settings(database_url='postgres://x', jwt_secret='x' * 16, service_token='y' * 16, s3_secret_access_key='z')
    trace = asyncio.run(
        dispatch_operator_alert(
            None,
            alert_row=alert_row,
            config=cfg,
            email_sender=email_sender,
            whatsapp_sender=whatsapp_sender,
            webhook_sender=webhook_sender,
        )
    )
    assert seen == {'email': 1, 'whatsapp': 1, 'webhook': 1}
    assert trace['email_sent'] == 1
    assert trace['whatsapp_queued'] == 1
    assert trace['webhook_sent'] is True
    assert trace['errors'] == []


def test_dispatch_collects_per_channel_errors():
    async def email_sender(_cfg, *, recipients, payload):
        raise RuntimeError('smtp_down')

    async def whatsapp_sender(_conn, *, tenant_id, recipients, payload):
        return len(recipients)

    async def webhook_sender(*, tenant_id, url, payload):
        raise RuntimeError('http_500')

    alert_row = {
        'id': uuid4(),
        'tenant_id': uuid4(),
        'payload': {
            'channels': {
                'email': ['m@e.com'],
                'whatsapp': ['+5730'],
                'webhook_url': 'https://x',
            },
        },
        'attempts': 0,
    }
    cfg = Settings(database_url='postgres://x', jwt_secret='x' * 16, service_token='y' * 16, s3_secret_access_key='z')
    trace = asyncio.run(
        dispatch_operator_alert(
            None,
            alert_row=alert_row,
            config=cfg,
            email_sender=email_sender,
            whatsapp_sender=whatsapp_sender,
            webhook_sender=webhook_sender,
        )
    )
    assert any('email' in e for e in trace['errors'])
    assert any('webhook' in e for e in trace['errors'])
    assert trace['whatsapp_queued'] == 1


def test_worker_retries_with_exponential_backoff_and_then_fails():
    cfg = Settings(
        database_url='postgres://x',
        jwt_secret='x' * 16,
        service_token='y' * 16,
        s3_secret_access_key='z',
        alerts_max_attempts=2,
        alerts_retry_base_seconds=60,
    )
    alert_id = uuid4()
    row = {
        'id': alert_id,
        'tenant_id': uuid4(),
        'attempts': 1,
        'payload': {
            'channels': {'email': ['m@e.com'], 'whatsapp': [], 'webhook_url': ''}
        },
    }
    conn = _Conn()
    conn.fetch_rows = [row]

    async def failing_email(_cfg, *, recipients, payload):
        raise RuntimeError('boom')

    asyncio.run(
        process_pending_operator_alerts(
            conn,
            config=cfg,
            email_sender=failing_email,
        )
    )
    # attempts == 1 < max_attempts (2) → reschedule
    reschedule = [u for u in conn.alert_updates if "scheduled_for=$3" in u[0]]
    assert reschedule, 'should reschedule on first failure'

    # Second pass: attempts becomes 2 → fail terminally.
    row['attempts'] = 2
    conn.alert_updates.clear()
    conn.fetch_rows = [row]
    asyncio.run(
        process_pending_operator_alerts(
            conn,
            config=cfg,
            email_sender=failing_email,
        )
    )
    failed = [u for u in conn.alert_updates if "status='failed'" in u[0]]
    assert failed, 'should mark as failed once attempts hit alerts_max_attempts'


def test_worker_marks_sent_when_dispatch_succeeds():
    cfg = Settings(
        database_url='postgres://x',
        jwt_secret='x' * 16,
        service_token='y' * 16,
        s3_secret_access_key='z',
    )
    row = {
        'id': uuid4(),
        'tenant_id': uuid4(),
        'attempts': 1,
        'payload': {'channels': {'email': ['m@e.com'], 'whatsapp': [], 'webhook_url': ''}},
    }
    conn = _Conn()
    conn.fetch_rows = [row]

    async def ok_email(_cfg, *, recipients, payload):
        return None

    asyncio.run(
        process_pending_operator_alerts(
            conn,
            config=cfg,
            email_sender=ok_email,
        )
    )
    sent = [u for u in conn.alert_updates if "status='sent'" in u[0]]
    assert sent


def test_next_retry_at_is_monotonic_with_attempts():
    later = next_retry_at(attempts=4, base_seconds=10)
    earlier = next_retry_at(attempts=0, base_seconds=10)
    assert later > earlier


# ───── Integration with feedback_flow ──────────────────────────────────────


class _FeedbackConn:
    """Minimal connection that supports the negative_feedback escalation path
    and tracks operator_alert inserts."""

    def __init__(self, *, notification_settings):
        self.notification_settings = notification_settings
        self.alerts: list[dict] = []
        self.messages: list[dict] = []
        self.events: list[dict] = []
        self.executed: list[tuple] = []
        self._appt_id = uuid4()
        self.feedback_id = uuid4()

    async def fetch(self, query, *args):
        return []

    async def fetchrow(self, query, *args):
        if 'from app.appointments' in query and 'contact_id=$2' in query:
            return {
                'id': self._appt_id,
                'starts_at': None,
                'ends_at': None,
                'status': 'completed',
                'confirmation_status': 'confirmed',
            }
        if 'insert into app.appointment_feedback' in query:
            return {'id': self.feedback_id}
        if 'insert into app.messages' in query:
            mid = uuid4()
            self.messages.append({'id': mid, 'body_text': args[2]})
            return {'id': mid}
        if 'insert into app.operator_alerts' in query:
            row_id = uuid4()
            self.alerts.append({
                'id': row_id,
                'tenant_id': args[0],
                'kind': args[1],
                'payload': json.loads(args[2]),
            })
            return {'id': row_id}
        if 'from app.handoffs' in query and "status='open'" in query:
            return None
        return None

    async def fetchval(self, query, *args):
        if 'select notification_settings from app.tenant_settings' in query:
            return self.notification_settings
        if 'select id from app.contact_tags' in query and 'name=$2' in query:
            return uuid4()
        if 'select display_name from app.contacts' in query:
            return 'Lucía'
        return None

    async def execute(self, query, *args):
        if 'insert into app.domain_events' in query:
            self.events.append({'idempotency_key': args[2], 'payload': json.loads(args[3])})
        else:
            self.executed.append((query, args))
        return None


def test_negative_feedback_enqueues_alert_with_channels_configured():
    conn = _FeedbackConn(
        notification_settings={
            'complaint_alert_channels': {
                'email': ['manager@empresa.com'],
                'whatsapp': [],
                'webhook_url': '',
            }
        }
    )
    result = asyncio.run(
        maybe_record_feedback(
            conn,
            tenant_id=uuid4(),
            contact_id=uuid4(),
            inbound_message={'id': uuid4(), 'body_text': '1', 'payload': {}},
            conversation={'id': uuid4(), 'metadata': {}},
            channel_id=uuid4(),
            channel_account_mode='mock',
        )
    )
    assert result['action'] == 'feedback_negative_escalated'
    trace = result['negative_escalation']
    assert 'operator_alert_id' in trace
    assert conn.alerts, 'expected alert insert'
    payload = conn.alerts[0]['payload']
    assert payload['rating'] == 1
    assert payload['contact_name'] == 'Lucía'
    assert payload['channels']['email'] == ['manager@empresa.com']
    assert payload['feedback_id'] == str(conn.feedback_id)


def test_negative_feedback_no_alert_when_no_channels():
    conn = _FeedbackConn(notification_settings={})
    result = asyncio.run(
        maybe_record_feedback(
            conn,
            tenant_id=uuid4(),
            contact_id=uuid4(),
            inbound_message={'id': uuid4(), 'body_text': '2', 'payload': {}},
            conversation={'id': uuid4(), 'metadata': {}},
            channel_id=uuid4(),
            channel_account_mode='mock',
        )
    )
    assert result['action'] == 'feedback_negative_escalated'
    assert conn.alerts == []
    assert 'operator_alert_id' not in result['negative_escalation']


# ───── Admin Panel ─────────────────────────────────────────────────────────


def test_admin_panel_renders_alerts_block():
    source = ADMIN_PANEL.read_text()
    assert 'Alertas al equipo (TASK-0057)' in source
    assert 'complaint_alert_channels' in source
    assert 'normalizeComplaintAlertChannels' in source
    assert 'data-wizard-field="complaint_alert_channels"' in source
    assert 'manager@empresa.com' in source
    assert 'alerts_webhook_secret' in source
    assert WHATSAPP_ALERT_TEMPLATE in source
