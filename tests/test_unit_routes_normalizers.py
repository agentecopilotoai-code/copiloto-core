"""Pure-helper tests for normalizers in routes.py.

Targets: tenant_brand_logo_proxy_url, _digest_subscription_to_dict,
_validate_digest_recipients, _normalize_messenger_channel,
_normalize_web_channel, normalize_whatsapp_template.
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException


# ───────── tenant_brand_logo_proxy_url ───────────────────────────────────


def test_tenant_brand_logo_proxy_url_format():
    from app.api.v1.routes import tenant_brand_logo_proxy_url
    tid = uuid4()
    asset_id = uuid4()
    out = tenant_brand_logo_proxy_url(tid, asset_id)
    assert out == f'/v1/tenants/{tid}/media/{asset_id}/content'


# ───────── _digest_subscription_to_dict ──────────────────────────────────


def test_digest_subscription_to_dict_full_row():
    from app.api.v1.routes import _digest_subscription_to_dict
    sub_id = uuid4()
    now = datetime(2026, 5, 18, tzinfo=UTC)
    row = {
        'id': sub_id,
        'recipient_email': 'a@b.com',
        'recipient_whatsapp': '+57300',
        'cadence': 'weekly',
        'enabled': True,
        'last_sent_at': now,
        'created_at': now,
        'updated_at': now,
    }
    out = _digest_subscription_to_dict(row)
    assert out['id'] == str(sub_id)
    assert out['recipient_email'] == 'a@b.com'
    assert out['cadence'] == 'weekly'
    assert out['enabled'] is True
    assert out['last_sent_at'].startswith('2026-05-18')


def test_digest_subscription_to_dict_null_timestamps():
    from app.api.v1.routes import _digest_subscription_to_dict
    row = {
        'id': uuid4(),
        'recipient_email': None,
        'recipient_whatsapp': None,
        'cadence': 'daily',
        'enabled': False,
        'last_sent_at': None,
        'created_at': None,
        'updated_at': None,
    }
    out = _digest_subscription_to_dict(row)
    assert out['recipient_email'] == ''
    assert out['recipient_whatsapp'] == ''
    assert out['last_sent_at'] is None
    assert out['created_at'] is None


# ───────── _validate_digest_recipients ───────────────────────────────────


def test_validate_digest_recipients_email_only_ok():
    from app.api.v1.routes import _validate_digest_recipients
    # Should not raise
    _validate_digest_recipients('a@b.com', None)


def test_validate_digest_recipients_whatsapp_only_ok():
    from app.api.v1.routes import _validate_digest_recipients
    _validate_digest_recipients(None, '+57300')


def test_validate_digest_recipients_both_ok():
    from app.api.v1.routes import _validate_digest_recipients
    _validate_digest_recipients('a@b.com', '+57300')


def test_validate_digest_recipients_neither_raises():
    from app.api.v1.routes import _validate_digest_recipients
    with pytest.raises(HTTPException) as exc_info:
        _validate_digest_recipients(None, None)
    assert exc_info.value.status_code == 400


def test_validate_digest_recipients_empty_strings_rejected():
    from app.api.v1.routes import _validate_digest_recipients
    with pytest.raises(HTTPException):
        _validate_digest_recipients('', '')
    with pytest.raises(HTTPException):
        _validate_digest_recipients('   ', '  ')


# ───────── _normalize_messenger_channel ──────────────────────────────────


def test_normalize_messenger_channel_none():
    from app.api.v1.routes import _normalize_messenger_channel
    assert _normalize_messenger_channel(None) is None


def test_normalize_messenger_channel_strips_verify_token_hash():
    from app.api.v1.routes import _normalize_messenger_channel
    row = {
        'id': uuid4(), 'provider': 'facebook_messenger',
        'verify_token_hash': b'\x00\x01',
        'token_ref': None, 'app_secret_ref': None,
    }
    out = _normalize_messenger_channel(row)
    assert out is not None
    # Raw hash must NOT be returned
    assert 'verify_token_hash' not in out
    assert out['verify_token_configured'] is True


def test_normalize_messenger_channel_without_verify_token():
    from app.api.v1.routes import _normalize_messenger_channel
    row = {
        'id': uuid4(), 'provider': 'facebook_messenger',
        'verify_token_hash': None,
        'token_ref': None, 'app_secret_ref': None,
    }
    out = _normalize_messenger_channel(row)
    assert out['verify_token_configured'] is False
    assert out['token_configured'] is False
    assert out['app_secret_configured'] is False


# ───────── _normalize_web_channel ────────────────────────────────────────


def test_normalize_web_channel_none():
    from app.api.v1.routes import _normalize_web_channel
    assert _normalize_web_channel(None) is None


def test_normalize_web_channel_normalizes_allowed_origins_and_widget_config():
    from app.api.v1.routes import _normalize_web_channel
    row = {
        'id': uuid4(), 'allowed_origins': None,
        'widget_config': '{"color": "#ff0000"}',
    }
    out = _normalize_web_channel(row)
    assert out['allowed_origins'] == []
    assert out['widget_config'] == {'color': '#ff0000'}


def test_normalize_web_channel_with_list_origins():
    from app.api.v1.routes import _normalize_web_channel
    row = {
        'id': uuid4(),
        'allowed_origins': ['https://x.com', 'https://y.com'],
        'widget_config': {},
    }
    out = _normalize_web_channel(row)
    assert out['allowed_origins'] == ['https://x.com', 'https://y.com']


# ───────── normalize_whatsapp_template ───────────────────────────────────


def test_normalize_whatsapp_template_none():
    from app.api.v1.routes import normalize_whatsapp_template
    assert normalize_whatsapp_template(None) is None


def test_normalize_whatsapp_template_parses_components():
    from app.api.v1.routes import normalize_whatsapp_template
    row = {
        'id': uuid4(), 'name': 'hello',
        'components': '{"body": {"text": "Hola"}}',
    }
    out = normalize_whatsapp_template(row)
    assert out is not None
    assert out['components'] == {'body': {'text': 'Hola'}}


def test_normalize_whatsapp_template_already_dict():
    from app.api.v1.routes import normalize_whatsapp_template
    row = {
        'id': uuid4(), 'name': 'hello',
        'components': {'header': {'text': 'X'}},
    }
    out = normalize_whatsapp_template(row)
    assert out['components'] == {'header': {'text': 'X'}}


def test_normalize_whatsapp_template_invalid_components_defaults_to_empty():
    from app.api.v1.routes import normalize_whatsapp_template
    row = {'id': uuid4(), 'name': 't', 'components': 'not json'}
    out = normalize_whatsapp_template(row)
    assert out['components'] == {}
