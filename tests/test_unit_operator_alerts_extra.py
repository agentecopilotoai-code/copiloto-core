"""Targeted tests for `app/services/operator_alerts.py` — pure builders,
channel normalizers, retry helpers, kind-specific email + template formatters,
and the `dispatch_operator_alert` orchestrator with stubbed senders."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from uuid import UUID, uuid4

import pytest


# ───────── _coerce_dict ───────────────────────────────────────────────────


def test_coerce_dict_passthrough():
    from app.services.operator_alerts import _coerce_dict
    d = {'a': 1}
    assert _coerce_dict(d) is d


def test_coerce_dict_string_decodes():
    from app.services.operator_alerts import _coerce_dict
    assert _coerce_dict('{"x": 2}') == {'x': 2}


def test_coerce_dict_string_invalid_returns_empty():
    from app.services.operator_alerts import _coerce_dict
    assert _coerce_dict('not json') == {}


def test_coerce_dict_unknown_returns_empty():
    from app.services.operator_alerts import _coerce_dict
    assert _coerce_dict(None) == {}
    assert _coerce_dict(42) == {}


# ───────── normalize_alert_channels (relaxed mode) ───────────────────────


def test_normalize_alert_channels_empty_input():
    from app.services.operator_alerts import normalize_alert_channels
    out = normalize_alert_channels({})
    assert out == {'email': [], 'whatsapp': [], 'webhook_url': ''}


def test_normalize_alert_channels_filters_blanks_and_non_strings():
    from app.services.operator_alerts import normalize_alert_channels
    out = normalize_alert_channels({
        'email': ['  a@b.com', '', None, 5],
        'whatsapp': ['+57300', '  '],
        'webhook_url': '  https://hooks.example.com/abc  ',
    })
    assert out['email'] == ['a@b.com']
    assert out['whatsapp'] == ['+57300']
    assert out['webhook_url'] == 'https://hooks.example.com/abc'


def test_normalize_alert_channels_strict_mode_rejects_unsafe_url():
    from app.services.operator_alerts import normalize_alert_channels
    from app.services.url_guard import UnsafeOutboundURLError
    with pytest.raises(UnsafeOutboundURLError):
        normalize_alert_channels(
            {'webhook_url': 'http://127.0.0.1/x'}, strict=True,
        )


def test_normalize_alert_channels_accepts_string_input():
    from app.services.operator_alerts import normalize_alert_channels
    out = normalize_alert_channels(
        '{"email": ["a@b.com"], "whatsapp": [], "webhook_url": ""}',
    )
    assert out['email'] == ['a@b.com']


# ───────── channels_configured ────────────────────────────────────────────


def test_channels_configured_true_with_any_channel():
    from app.services.operator_alerts import channels_configured
    assert channels_configured({'email': ['a@b.com']}) is True
    assert channels_configured({'whatsapp': ['+57300']}) is True
    assert channels_configured(
        {'webhook_url': 'https://hooks.example.com/abc'},
    ) is True


def test_channels_configured_false_when_empty():
    from app.services.operator_alerts import channels_configured
    assert channels_configured({}) is False
    assert channels_configured(
        {'email': [], 'whatsapp': [], 'webhook_url': ''}) is False


# ───────── build_desk_link ───────────────────────────────────────────────


def test_build_desk_link_returns_empty_when_no_public_url():
    from app.services.operator_alerts import build_desk_link
    assert build_desk_link(None, uuid4(), None) == ''
    assert build_desk_link('', uuid4(), None) == ''


def test_build_desk_link_without_conversation():
    from app.services.operator_alerts import build_desk_link
    tid = uuid4()
    link = build_desk_link('https://app.example.com/', tid, None)
    assert link == f'https://app.example.com/admin?tenant={tid}#operations'


def test_build_desk_link_with_conversation():
    from app.services.operator_alerts import build_desk_link
    tid = uuid4()
    cid = uuid4()
    link = build_desk_link('https://app.example.com', tid, cid)
    assert link.endswith(f'#operations/{cid}')


# ───────── build_comment_preview ─────────────────────────────────────────


def test_build_comment_preview_empty_returns_empty():
    from app.services.operator_alerts import build_comment_preview
    assert build_comment_preview(None) == ''
    assert build_comment_preview('') == ''


def test_build_comment_preview_strips_whitespace_and_newlines():
    from app.services.operator_alerts import build_comment_preview
    assert build_comment_preview('  hello\nworld  ') == 'hello world'


def test_build_comment_preview_truncates_with_ellipsis():
    from app.services.operator_alerts import build_comment_preview
    out = build_comment_preview('x' * 200, limit=50)
    assert len(out) == 50
    assert out.endswith('…')


# ───────── read_webhook_secret + sign_webhook_payload ───────────────────


def test_read_webhook_secret_missing_returns_none(tmp_path, monkeypatch):
    from app.services import operator_alerts as oa
    monkeypatch.chdir(tmp_path)
    assert oa.read_webhook_secret(uuid4()) is None


def test_read_webhook_secret_reads_file(tmp_path, monkeypatch):
    from app.services import operator_alerts as oa
    monkeypatch.chdir(tmp_path)
    tid = uuid4()
    secrets_dir = tmp_path / '.secrets' / 'tenants' / str(tid)
    secrets_dir.mkdir(parents=True)
    (secrets_dir / 'alerts_webhook_secret').write_text('TOP-SECRET\n')
    assert oa.read_webhook_secret(tid) == 'TOP-SECRET'


def test_read_webhook_secret_empty_file_returns_none(tmp_path, monkeypatch):
    from app.services import operator_alerts as oa
    monkeypatch.chdir(tmp_path)
    tid = uuid4()
    secrets_dir = tmp_path / '.secrets' / 'tenants' / str(tid)
    secrets_dir.mkdir(parents=True)
    (secrets_dir / 'alerts_webhook_secret').write_text('   \n')
    assert oa.read_webhook_secret(tid) is None


def test_sign_webhook_payload_returns_none_without_secret():
    from app.services.operator_alerts import sign_webhook_payload
    assert sign_webhook_payload(None, b'body') is None
    assert sign_webhook_payload('', b'body') is None


def test_sign_webhook_payload_returns_sha256_hex():
    from app.services.operator_alerts import sign_webhook_payload
    sig = sign_webhook_payload('secret', b'body')
    expected = 'sha256=' + hmac.new(
        b'secret', b'body', hashlib.sha256,
    ).hexdigest()
    assert sig == expected


# ───────── build_email_message ───────────────────────────────────────────


def test_build_email_message_basic():
    from app.services.operator_alerts import build_email_message
    msg = build_email_message(
        sender='alerts@example.com',
        recipients=['a@b.com', 'c@d.com'],
        subject='Test',
        body='Hello',
    )
    assert msg['From'] == 'alerts@example.com'
    assert msg['To'] == 'a@b.com, c@d.com'
    assert msg['Subject'] == 'Test'
    assert msg.get_content().strip() == 'Hello'


# ───────── build_email_body — kind dispatch ──────────────────────────────


def test_build_email_body_negative_feedback_default():
    from app.services.operator_alerts import build_email_body
    subj, body = build_email_body({
        'contact_name': 'María',
        'rating': 1,
        'comment_preview': 'No me gustó',
        'conversation_url': 'https://app/x',
    })
    assert 'María' in subj
    assert '1/5' in subj or 'Calificación' in body
    assert 'No me gustó' in body
    assert 'https://app/x' in body


def test_build_email_body_negative_feedback_no_rating():
    from app.services.operator_alerts import build_email_body
    subj, body = build_email_body({
        'contact_name': 'Juan',
        'comment_preview': '',
        'conversation_url': '',
    })
    assert 'Juan' in subj
    # 'Queja registrada' appears when rating is None
    assert 'Queja' in body or 'feedback' in body


def test_build_email_body_outbound_dlq():
    from app.services.operator_alerts import build_email_body
    subj, body = build_email_body({
        '_kind': 'outbound_dlq_threshold',
        'total': 12, 'threshold': 5, 'window_minutes': 10,
        'by_error_code': [
            {'error_code': '131026', 'count': 8},
            {'error_code': '131047', 'count': 4},
        ],
        'preview': [
            {'at': '2026-05-18T10:00', 'error_code': '131026', 'error_message': 'Too long ' * 50},
        ],
    })
    assert 'DLQ' in subj
    assert '12' in subj
    assert '131026: 8' in body
    assert '131047: 4' in body
    assert '…' in body  # error message truncated


def test_build_email_body_outbound_dlq_no_data():
    from app.services.operator_alerts import build_email_body
    subj, body = build_email_body({
        '_kind': 'outbound_dlq_threshold',
        'total': 0, 'threshold': 5, 'window_minutes': 10,
    })
    assert 'sin datos' in body


# ───────── whatsapp_template_for_kind ────────────────────────────────────


def test_whatsapp_template_for_kind_dlq():
    from app.services.operator_alerts import (
        WHATSAPP_DLQ_ALERT_TEMPLATE,
        whatsapp_template_for_kind,
    )
    name, locale = whatsapp_template_for_kind('outbound_dlq_threshold')
    assert name == WHATSAPP_DLQ_ALERT_TEMPLATE
    assert locale == 'es'


def test_whatsapp_template_for_kind_default_complaint():
    from app.services.operator_alerts import (
        WHATSAPP_ALERT_TEMPLATE,
        whatsapp_template_for_kind,
    )
    name, _ = whatsapp_template_for_kind('negative_feedback')
    assert name == WHATSAPP_ALERT_TEMPLATE


# ───────── build_whatsapp_template_components ────────────────────────────


def test_build_whatsapp_template_components_negative_feedback():
    from app.services.operator_alerts import build_whatsapp_template_components
    comps = build_whatsapp_template_components({
        'contact_name': 'Ana', 'rating': 2,
        'comment_preview': 'Mal servicio',
        'conversation_url': 'https://x',
    })
    body = next(c for c in comps if c['type'] == 'body')
    texts = [p['text'] for p in body['parameters']]
    assert 'Ana' in texts
    assert '2/5' in texts


def test_build_whatsapp_template_components_dlq():
    from app.services.operator_alerts import build_whatsapp_template_components
    comps = build_whatsapp_template_components({
        '_kind': 'outbound_dlq_threshold',
        'total': 7, 'window_minutes': 15,
        'by_error_code': [{'error_code': '131026', 'count': 5}],
        'panel_url': 'https://x/admin',
    })
    body = next(c for c in comps if c['type'] == 'body')
    texts = [p['text'] for p in body['parameters']]
    assert '7' in texts
    assert '15' in texts
    assert 'https://x/admin' in texts


def test_build_whatsapp_template_components_dlq_empty():
    from app.services.operator_alerts import build_whatsapp_template_components
    comps = build_whatsapp_template_components({
        '_kind': 'outbound_dlq_threshold',
    })
    body = next(c for c in comps if c['type'] == 'body')
    assert body['parameters'][3]['text'] == '—'


def test_resolve_alert_kind_falls_back():
    from app.services.operator_alerts import _resolve_alert_kind
    assert _resolve_alert_kind({}) == 'negative_feedback'
    assert _resolve_alert_kind({'kind': 'outbound_dlq_threshold'}) == 'outbound_dlq_threshold'
    assert _resolve_alert_kind({'_kind': 'complaint'}) == 'complaint'


# ───────── _wa_id_from_phone ────────────────────────────────────────────


def test_wa_id_from_phone_strips_plus():
    from app.services.operator_alerts import _wa_id_from_phone
    assert _wa_id_from_phone('+5730099887766') == '5730099887766'
    assert _wa_id_from_phone('5730099887766') == '5730099887766'


# ───────── next_retry_at ─────────────────────────────────────────────────


def test_next_retry_at_returns_future_datetime():
    from datetime import UTC, datetime
    from app.services.operator_alerts import next_retry_at
    now = datetime.now(UTC)
    nxt = next_retry_at(2, 10)  # 10 * 2^2 = 40 seconds
    delta = (nxt - now).total_seconds()
    assert 39 <= delta <= 41


def test_next_retry_at_clamps_negative_attempts():
    from app.services.operator_alerts import next_retry_at
    # 2^max(-1,0) = 2^0 = 1
    from datetime import UTC, datetime
    now = datetime.now(UTC)
    nxt = next_retry_at(-1, 10)
    delta = (nxt - now).total_seconds()
    assert 9 <= delta <= 11


# ───────── _send_email_channel ────────────────────────────────────────────


def test_send_email_channel_skips_no_recipients(monkeypatch):
    from app.core.config import get_settings
    from app.services.operator_alerts import _send_email_channel

    async def _go():
        cfg = get_settings()
        return await _send_email_channel(cfg, recipients=[], payload={})

    # Should NOT raise — returns immediately
    asyncio.run(_go())


def test_send_email_channel_requires_smtp_config():
    from app.core.config import Settings
    from app.services.operator_alerts import _send_email_channel

    cfg = Settings.model_construct(
        alerts_smtp_host=None, alerts_smtp_from=None,
    )

    async def _go():
        return await _send_email_channel(
            cfg, recipients=['a@b.com'], payload={'contact_name': 'X'},
        )

    with pytest.raises(RuntimeError, match='smtp_not_configured'):
        asyncio.run(_go())


# ───────── dispatch_operator_alert with stubbed senders ─────────────────


def test_dispatch_operator_alert_all_channels_success():
    """All three senders complete without error → no errors in trace."""
    from app.services.operator_alerts import dispatch_operator_alert

    sent = {'email': 0, 'whatsapp': 0, 'webhook': 0}

    async def fake_email(config, *, recipients, payload):
        sent['email'] = len(recipients)

    async def fake_whatsapp(conn, *, tenant_id, recipients, payload):
        sent['whatsapp'] = len(recipients)
        return len(recipients)

    async def fake_webhook(*, tenant_id, url, payload):
        sent['webhook'] = 1

    alert_row = {
        'id': uuid4(),
        'tenant_id': uuid4(),
        'kind': 'negative_feedback',
        'payload': {
            'contact_name': 'Pedro',
            'rating': 1,
            'channels': {
                'email': ['a@b.com'],
                'whatsapp': ['+57300'],
                'webhook_url': 'https://hooks.example.com/x',
            },
        },
        'delivered_channels': [],
    }

    async def _go():
        return await dispatch_operator_alert(
            None,  # conn unused
            alert_row=alert_row,
            email_sender=fake_email,
            whatsapp_sender=fake_whatsapp,
            webhook_sender=fake_webhook,
        )

    trace = asyncio.run(_go())
    assert trace['errors'] == []
    assert trace['email_sent'] == 1
    assert trace['whatsapp_queued'] == 1
    assert trace['webhook_sent'] is True
    assert sorted(trace['newly_delivered']) == ['email', 'webhook', 'whatsapp']


def test_dispatch_operator_alert_email_failure_caught():
    from app.services.operator_alerts import dispatch_operator_alert

    async def fake_email(*args, **kwargs):
        raise RuntimeError('smtp_down')

    async def fake_whatsapp(*args, **kwargs):
        return 1

    async def fake_webhook(*args, **kwargs):
        pass

    alert_row = {
        'id': uuid4(),
        'tenant_id': uuid4(),
        'kind': 'negative_feedback',
        'payload': {
            'channels': {
                'email': ['a@b.com'],
                'whatsapp': ['+57300'],
                'webhook_url': '',
            },
        },
        'delivered_channels': [],
    }

    async def _go():
        return await dispatch_operator_alert(
            None,
            alert_row=alert_row,
            email_sender=fake_email,
            whatsapp_sender=fake_whatsapp,
            webhook_sender=fake_webhook,
        )

    trace = asyncio.run(_go())
    assert any('email' in e for e in trace['errors'])
    assert trace['whatsapp_queued'] == 1


def test_dispatch_operator_alert_skips_already_delivered():
    """If a channel is in `delivered_channels`, it's NOT re-sent."""
    from app.services.operator_alerts import dispatch_operator_alert

    calls = {'email': 0, 'whatsapp': 0, 'webhook': 0}

    async def fake_email(*args, **kwargs):
        calls['email'] += 1

    async def fake_whatsapp(*args, **kwargs):
        calls['whatsapp'] += 1
        return 1

    async def fake_webhook(*args, **kwargs):
        calls['webhook'] += 1

    alert_row = {
        'id': uuid4(),
        'tenant_id': uuid4(),
        'kind': 'negative_feedback',
        'payload': {
            'channels': {
                'email': ['a@b.com'],
                'whatsapp': ['+57300'],
                'webhook_url': 'https://hooks.example.com/x',
            },
        },
        'delivered_channels': ['email', 'whatsapp'],
    }

    async def _go():
        return await dispatch_operator_alert(
            None,
            alert_row=alert_row,
            email_sender=fake_email,
            whatsapp_sender=fake_whatsapp,
            webhook_sender=fake_webhook,
        )

    trace = asyncio.run(_go())
    assert calls['email'] == 0
    assert calls['whatsapp'] == 0
    assert calls['webhook'] == 1
    assert trace['newly_delivered'] == ['webhook']
