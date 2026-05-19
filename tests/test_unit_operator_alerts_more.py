"""Extra tests for app/services/operator_alerts.py — DLQ formatters, channels."""
from __future__ import annotations

import asyncio
from uuid import uuid4


class _Row(dict):
    def keys(self):  # type: ignore[override]
        return super().keys()


class _FakeConn:
    def __init__(self, *, fetchval_results=None, fetchrow_results=None):
        self._fetchval = list(fetchval_results or [])
        self._fetchrow = list(fetchrow_results or [])
        self.executed = []

    async def fetchval(self, sql, *args):
        if not self._fetchval:
            return None
        return self._fetchval.pop(0)

    async def fetchrow(self, sql, *args):
        if not self._fetchrow:
            return None
        return self._fetchrow.pop(0)

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


def _run(c):
    return asyncio.run(c)


# ─── _resolve_alert_kind ──────────────────────────────────────────────────


def test_resolve_alert_kind_from_underscore_kind():
    from app.services.operator_alerts import _resolve_alert_kind
    assert _resolve_alert_kind({'_kind': 'outbound_dlq_threshold'}) == 'outbound_dlq_threshold'


def test_resolve_alert_kind_from_kind_key():
    from app.services.operator_alerts import _resolve_alert_kind
    assert _resolve_alert_kind({'kind': 'foo'}) == 'foo'


def test_resolve_alert_kind_default_negative_feedback():
    from app.services.operator_alerts import _resolve_alert_kind, ALERT_KIND_NEGATIVE_FEEDBACK
    assert _resolve_alert_kind({}) == ALERT_KIND_NEGATIVE_FEEDBACK


def test_resolve_alert_kind_invalid_value():
    from app.services.operator_alerts import _resolve_alert_kind, ALERT_KIND_NEGATIVE_FEEDBACK
    assert _resolve_alert_kind({'_kind': 42}) == ALERT_KIND_NEGATIVE_FEEDBACK


# ─── _build_outbound_dlq_email ────────────────────────────────────────────


def test_build_outbound_dlq_email_basic():
    from app.services.operator_alerts import _build_outbound_dlq_email
    subj, body = _build_outbound_dlq_email({
        'total': 15, 'threshold': 10, 'window_minutes': 10,
        'by_error_code': [{'error_code': '131026', 'count': 12}],
        'preview': [{'at': '2026-05-18', 'error_code': '131026', 'error_message': 'Long error message'}],
    })
    assert '15' in subj
    assert '131026' in body
    assert 'Long error message' in body


def test_build_outbound_dlq_email_no_by_code():
    from app.services.operator_alerts import _build_outbound_dlq_email
    subj, body = _build_outbound_dlq_email({'total': 5, 'threshold': 3, 'window_minutes': 10})
    assert 'sin datos' in body.lower()


def test_build_outbound_dlq_email_long_message_truncated():
    from app.services.operator_alerts import _build_outbound_dlq_email
    long_msg = 'x' * 500
    subj, body = _build_outbound_dlq_email({
        'total': 1, 'threshold': 1, 'window_minutes': 5,
        'preview': [{'error_code': '1', 'error_message': long_msg}],
    })
    assert '…' in body


# ─── _build_negative_feedback_email ──────────────────────────────────────


def test_build_negative_feedback_email_full():
    from app.services.operator_alerts import _build_negative_feedback_email
    subj, body = _build_negative_feedback_email({
        'contact_name': 'Juan', 'rating': 2,
        'comment_preview': 'Servicio malo', 'conversation_url': 'https://desk',
    })
    assert 'Juan' in subj
    assert '2/5' in subj
    assert 'Servicio malo' in body
    assert 'https://desk' in body


def test_build_negative_feedback_email_no_rating():
    from app.services.operator_alerts import _build_negative_feedback_email
    subj, body = _build_negative_feedback_email({})
    assert 'cliente' in subj
    assert 'Queja registrada' in body


# ─── build_email_body ─────────────────────────────────────────────────────


def test_build_email_body_dlq_kind():
    from app.services.operator_alerts import build_email_body, ALERT_KIND_OUTBOUND_DLQ_THRESHOLD
    subj, body = build_email_body({
        '_kind': ALERT_KIND_OUTBOUND_DLQ_THRESHOLD,
        'total': 5, 'threshold': 3, 'window_minutes': 10,
    })
    assert 'DLQ outbound' in subj


def test_build_email_body_default_negative_feedback():
    from app.services.operator_alerts import build_email_body
    subj, body = build_email_body({'contact_name': 'X'})
    assert 'Alerta operativa' in subj


# ─── _build_outbound_dlq_template_components ─────────────────────────────


def test_build_outbound_dlq_template_components_with_top():
    from app.services.operator_alerts import _build_outbound_dlq_template_components
    comps = _build_outbound_dlq_template_components({
        'total': 10, 'window_minutes': 5,
        'by_error_code': [{'error_code': '131026', 'count': 8}],
        'panel_url': 'https://panel',
    })
    params = comps[0]['parameters']
    assert params[0]['text'] == '10'
    assert '131026' in params[2]['text']
    assert params[3]['text'] == 'https://panel'


def test_build_outbound_dlq_template_components_no_top():
    from app.services.operator_alerts import _build_outbound_dlq_template_components
    comps = _build_outbound_dlq_template_components({})
    params = comps[0]['parameters']
    assert params[0]['text'] == '0'
    assert params[2]['text'] == '—'


# ─── _build_negative_feedback_template_components ────────────────────────


def test_build_negative_feedback_template_components_with_rating():
    from app.services.operator_alerts import _build_negative_feedback_template_components
    comps = _build_negative_feedback_template_components({
        'contact_name': 'Ana', 'rating': 1, 'comment_preview': 'mal',
        'conversation_url': 'https://x',
    })
    params = comps[0]['parameters']
    assert params[0]['text'] == 'Ana'
    assert '1/5' in params[1]['text']


def test_build_negative_feedback_template_components_no_rating():
    from app.services.operator_alerts import _build_negative_feedback_template_components
    comps = _build_negative_feedback_template_components({})
    params = comps[0]['parameters']
    assert 'queja' in params[1]['text']
    assert params[0]['text'] == 'cliente'


# ─── build_whatsapp_template_components ──────────────────────────────────


def test_build_whatsapp_template_components_dlq():
    from app.services.operator_alerts import build_whatsapp_template_components, ALERT_KIND_OUTBOUND_DLQ_THRESHOLD
    comps = build_whatsapp_template_components({'_kind': ALERT_KIND_OUTBOUND_DLQ_THRESHOLD, 'total': 5})
    assert comps[0]['parameters'][0]['text'] == '5'


def test_build_whatsapp_template_components_neg_feedback():
    from app.services.operator_alerts import build_whatsapp_template_components
    comps = build_whatsapp_template_components({'contact_name': 'X'})
    assert comps[0]['parameters'][0]['text'] == 'X'


# ─── whatsapp_template_for_kind ──────────────────────────────────────────


def test_whatsapp_template_for_kind_dlq():
    from app.services.operator_alerts import whatsapp_template_for_kind, ALERT_KIND_OUTBOUND_DLQ_THRESHOLD
    name, locale = whatsapp_template_for_kind(ALERT_KIND_OUTBOUND_DLQ_THRESHOLD)
    assert name
    assert locale


def test_whatsapp_template_for_kind_neg_feedback():
    from app.services.operator_alerts import whatsapp_template_for_kind
    name, locale = whatsapp_template_for_kind('something_else')
    assert name


# ─── _wa_id_from_phone ───────────────────────────────────────────────────


def test_wa_id_from_phone_strips_plus():
    from app.services.operator_alerts import _wa_id_from_phone
    assert _wa_id_from_phone('+5730099') == '5730099'


def test_wa_id_from_phone_no_plus():
    from app.services.operator_alerts import _wa_id_from_phone
    assert _wa_id_from_phone('5730099') == '5730099'


# ─── _send_email_channel ─────────────────────────────────────────────────


def test_send_email_channel_no_recipients():
    from app.services.operator_alerts import _send_email_channel
    from app.core.config import Settings
    config = Settings.model_construct(
        alerts_smtp_host='', alerts_smtp_from='',
    )
    _run(_send_email_channel(config, recipients=[], payload={}))
    # no raise → ok


def test_send_email_channel_smtp_not_configured():
    from app.services.operator_alerts import _send_email_channel
    from app.core.config import Settings
    import pytest as _pytest
    config = Settings.model_construct(alerts_smtp_host='', alerts_smtp_from='')
    with _pytest.raises(RuntimeError, match='smtp_not_configured'):
        _run(_send_email_channel(config, recipients=['x@y.com'], payload={'contact_name': 'X'}))


def test_send_email_channel_calls_smtp(monkeypatch):
    from app.services import operator_alerts
    from app.services.operator_alerts import _send_email_channel
    from app.core.config import Settings

    calls = []

    async def _fake_smtp(config, msg):
        calls.append(msg)

    monkeypatch.setattr(operator_alerts, '_send_email_smtp', _fake_smtp)
    config = Settings.model_construct(
        alerts_smtp_host='localhost', alerts_smtp_from='from@x.com',
    )
    _run(_send_email_channel(config, recipients=['to@x.com'], payload={'contact_name': 'X'}))
    assert len(calls) == 1


# ─── _send_webhook_channel ──────────────────────────────────────────────


def test_send_webhook_channel_no_url():
    from app.services.operator_alerts import _send_webhook_channel
    _run(_send_webhook_channel(tenant_id=uuid4(), url='', payload={}, http_client=None))


def test_send_webhook_channel_blocked_url():
    from app.services.operator_alerts import _send_webhook_channel
    # Loopback URL should be blocked
    _run(_send_webhook_channel(
        tenant_id=uuid4(), url='http://127.0.0.1:1234',
        payload={}, http_client=None,
    ))


def test_send_webhook_channel_with_http_client(monkeypatch):
    from app.services.operator_alerts import _send_webhook_channel

    calls = []

    class _FakeClient:
        async def post(self, url, content=None, headers=None):
            calls.append({'url': url, 'content': content, 'headers': headers})

            class _R:
                def raise_for_status(self):
                    pass

            return _R()

    _run(_send_webhook_channel(
        tenant_id=uuid4(),
        url='https://example.com/webhook',
        payload={'x': 1},
        http_client=_FakeClient(),
    ))
    assert len(calls) == 1
    # The url_guard may transform but for example.com it's accepted
    assert calls[0]['headers']['Content-Type'] == 'application/json'


def test_send_webhook_channel_signs_with_secret(monkeypatch, tmp_path):
    """If `.secrets/tenants/<id>/alerts_webhook_secret` exists, sign the payload."""
    from app.services import operator_alerts

    tenant_id = uuid4()

    monkeypatch.setattr(operator_alerts, 'read_webhook_secret', lambda tid: 'shhhh')

    calls = []

    class _FakeClient:
        async def post(self, url, content=None, headers=None):
            calls.append(headers)

            class _R:
                def raise_for_status(self):
                    pass

            return _R()

    _run(operator_alerts._send_webhook_channel(
        tenant_id=tenant_id,
        url='https://example.com/webhook',
        payload={'a': 1},
        http_client=_FakeClient(),
    ))
    assert 'X-CopilotoIA-Signature' in calls[0]


# ─── _ensure_operator_alert_conversation ────────────────────────────────


def test_ensure_operator_alert_conversation_existing():
    from app.services.operator_alerts import _ensure_operator_alert_conversation
    contact_id = uuid4()
    conv_id = uuid4()
    conn = _FakeConn(fetchval_results=[contact_id, conv_id])
    out = _run(_ensure_operator_alert_conversation(
        conn, tenant_id=uuid4(), channel_id=uuid4(), recipient_phone='+5730099',
    ))
    assert out == conv_id


def test_ensure_operator_alert_conversation_creates_new():
    from app.services.operator_alerts import _ensure_operator_alert_conversation
    contact_id = uuid4()
    new_conv = uuid4()
    conn = _FakeConn(fetchval_results=[contact_id, None, new_conv])
    out = _run(_ensure_operator_alert_conversation(
        conn, tenant_id=uuid4(), channel_id=uuid4(), recipient_phone='+5730099',
    ))
    assert out == new_conv


# ─── _send_whatsapp_channel ─────────────────────────────────────────────


def test_send_whatsapp_channel_no_recipients():
    from app.services.operator_alerts import _send_whatsapp_channel
    conn = _FakeConn()
    out = _run(_send_whatsapp_channel(conn, tenant_id=uuid4(), recipients=[], payload={}))
    assert out == 0


def test_send_whatsapp_channel_no_channel_raises():
    from app.services.operator_alerts import _send_whatsapp_channel
    import pytest as _pytest
    conn = _FakeConn(fetchval_results=[None])  # channel lookup returns None
    with _pytest.raises(RuntimeError, match='whatsapp_channel_not_provisioned'):
        _run(_send_whatsapp_channel(
            conn, tenant_id=uuid4(), recipients=['+5730099'],
            payload={'contact_name': 'X'},
        ))


def test_send_whatsapp_channel_queues_message():
    from app.services.operator_alerts import _send_whatsapp_channel
    channel_id = uuid4()
    contact_id = uuid4()
    conv_id = uuid4()
    msg_id = uuid4()
    conn = _FakeConn(
        # First: select channel_id, then _ensure (contact + conv lookup [hit])
        fetchval_results=[channel_id, contact_id, conv_id],
        fetchrow_results=[_Row(id=msg_id)],  # insert message
    )
    out = _run(_send_whatsapp_channel(
        conn, tenant_id=uuid4(), recipients=['+5730099'],
        payload={'contact_name': 'Carla'},
    ))
    assert out == 1


# ─── dispatch_operator_alert ────────────────────────────────────────────


def test_dispatch_operator_alert_no_channels():
    from app.services.operator_alerts import dispatch_operator_alert
    from app.core.config import Settings

    async def _email(cfg, recipients, payload):
        pass

    async def _wa(conn, tenant_id, recipients, payload):
        return 0

    async def _wh(tenant_id, url, payload):
        pass

    alert_row = _Row(
        payload={'channels': {}},
        tenant_id=uuid4(),
        kind='negative_feedback',
        delivered_channels=None,
    )
    out = _run(dispatch_operator_alert(
        _FakeConn(),
        alert_row=alert_row,
        config=Settings.model_construct(admin_panel_public_url=''),
        email_sender=_email, whatsapp_sender=_wa, webhook_sender=_wh,
    ))
    assert out['email_sent'] == 0


def test_dispatch_operator_alert_with_email():
    from app.services.operator_alerts import dispatch_operator_alert
    from app.core.config import Settings

    sent = []

    async def _email(cfg, recipients, payload):
        sent.append(recipients)

    async def _wa(conn, tenant_id, recipients, payload):
        return len(recipients)

    async def _wh(tenant_id, url, payload):
        pass

    alert_row = _Row(
        payload={'channels': {'email': ['a@b.com'], 'whatsapp': ['+57300']}},
        tenant_id=uuid4(),
        kind='negative_feedback',
        delivered_channels=None,
    )
    out = _run(dispatch_operator_alert(
        _FakeConn(),
        alert_row=alert_row,
        config=Settings.model_construct(admin_panel_public_url=''),
        email_sender=_email, whatsapp_sender=_wa, webhook_sender=_wh,
    ))
    assert out['email_sent'] == 1
    assert out['whatsapp_queued'] == 1


def test_dispatch_operator_alert_email_raises_in_errors():
    from app.services.operator_alerts import dispatch_operator_alert
    from app.core.config import Settings

    async def _email(cfg, recipients, payload):
        raise RuntimeError('smtp_down')

    async def _wa(conn, **kw):
        return 0

    async def _wh(**kw):
        pass

    alert_row = _Row(
        payload={'channels': {'email': ['x@y.com']}},
        tenant_id=uuid4(),
        kind='negative_feedback',
        delivered_channels=[],
    )
    out = _run(dispatch_operator_alert(
        _FakeConn(),
        alert_row=alert_row,
        config=Settings.model_construct(admin_panel_public_url=''),
        email_sender=_email, whatsapp_sender=_wa, webhook_sender=_wh,
    ))
    assert any('email:' in e for e in out['errors'])


def test_dispatch_operator_alert_skip_already_delivered():
    from app.services.operator_alerts import dispatch_operator_alert
    from app.core.config import Settings

    async def _email(cfg, recipients, payload):
        raise AssertionError('should not be called')

    async def _wa(conn, **kw):
        return 0

    async def _wh(**kw):
        pass

    alert_row = _Row(
        payload={'channels': {'email': ['x@y.com']}},
        tenant_id=uuid4(),
        kind='negative_feedback',
        delivered_channels=['email'],
    )
    out = _run(dispatch_operator_alert(
        _FakeConn(),
        alert_row=alert_row,
        config=Settings.model_construct(admin_panel_public_url=''),
        email_sender=_email, whatsapp_sender=_wa, webhook_sender=_wh,
    ))
    assert 'email' in out['skipped_already_delivered']


def test_dispatch_operator_alert_dlq_panel_url_stamped():
    from app.services.operator_alerts import dispatch_operator_alert, ALERT_KIND_OUTBOUND_DLQ_THRESHOLD
    from app.core.config import Settings

    seen = []

    async def _email(cfg, recipients, payload):
        seen.append(payload)

    async def _wa(conn, **kw):
        return 0

    async def _wh(**kw):
        pass

    alert_row = _Row(
        payload={'channels': {'email': ['x@y.com']}, 'total': 5},
        tenant_id=uuid4(),
        kind=ALERT_KIND_OUTBOUND_DLQ_THRESHOLD,
        delivered_channels=[],
    )
    _run(dispatch_operator_alert(
        _FakeConn(),
        alert_row=alert_row,
        config=Settings.model_construct(admin_panel_public_url='https://panel.x'),
        email_sender=_email, whatsapp_sender=_wa, webhook_sender=_wh,
    ))
    assert seen[0]['panel_url'].startswith('https://panel.x')


# ─── next_retry_at ──────────────────────────────────────────────────────


def test_next_retry_at_returns_future_datetime():
    from datetime import UTC, datetime
    from app.services.operator_alerts import next_retry_at
    out = next_retry_at(2, 10)
    assert isinstance(out, datetime)
    # Should be greater than now
    assert out > datetime.now(UTC)
