"""Unit tests for app/api/v1/_helpers/payments_pure.py."""
from __future__ import annotations

from uuid import uuid4


class _Row(dict):
    def keys(self):  # type: ignore[override]
        return super().keys()


def test_normalize_payment_settings_with_dict():
    from app.api.v1._helpers.payments_pure import _normalize_payment_settings
    out = _normalize_payment_settings({
        'provider': 'mercadopago',
        'currency': 'usd',
        'default_amount': 1000,
        'api_key_ref': 'sm://k',
        'webhook_secret_ref': 'sm://s',
    })
    assert out['provider'] == 'mercadopago'
    assert out['currency'] == 'USD'
    assert out['default_amount'] == 1000


def test_normalize_payment_settings_with_json_string():
    from app.api.v1._helpers.payments_pure import _normalize_payment_settings
    out = _normalize_payment_settings('{"provider":"stripe","currency":"eur"}')
    assert out['provider'] == 'stripe'
    assert out['currency'] == 'EUR'


def test_normalize_payment_settings_invalid_json_becomes_default():
    from app.api.v1._helpers.payments_pure import _normalize_payment_settings
    out = _normalize_payment_settings('not-json')
    assert out['provider'] == 'none'
    assert out['currency'] == 'COP'


def test_normalize_payment_settings_invalid_provider_falls_back_to_none():
    from app.api.v1._helpers.payments_pure import _normalize_payment_settings
    out = _normalize_payment_settings({'provider': 'paypal'})
    assert out['provider'] == 'none'


def test_normalize_payment_settings_non_dict_non_str():
    from app.api.v1._helpers.payments_pure import _normalize_payment_settings
    out = _normalize_payment_settings(42)
    assert out['provider'] == 'none'
    assert out['currency'] == 'COP'


def test_normalize_payment_settings_truncates_currency():
    from app.api.v1._helpers.payments_pure import _normalize_payment_settings
    out = _normalize_payment_settings({'currency': 'usdgarbage'})
    assert len(out['currency']) == 3
    assert out['currency'] == 'USD'


def test_public_payment_settings_redacts_secrets():
    from app.api.v1._helpers.payments_pure import _public_payment_settings
    tenant = uuid4()
    out = _public_payment_settings(tenant, {
        'provider': 'stripe',
        'currency': 'cop',
        'default_amount': 500,
        'api_key_ref': None,
        'webhook_secret_ref': None,
    })
    assert out['provider'] == 'stripe'
    assert out['tenant_id'] == str(tenant)
    assert out['api_key_configured'] is False
    assert out['webhook_secret_configured'] is False
    assert 'api_key_ref' not in out
    assert 'webhook_secret_ref' not in out


def test_appointment_payment_external_ref_format():
    from app.api.v1._helpers.payments_pure import _appointment_payment_external_ref
    t = uuid4()
    a = uuid4()
    ref = _appointment_payment_external_ref(t, a)
    assert ref == f'tenant:{t}:appointment:{a}'


def test_parse_appointment_external_ref_valid():
    from app.api.v1._helpers.payments_pure import (
        _appointment_payment_external_ref,
        _parse_appointment_external_ref,
    )
    t = uuid4()
    a = uuid4()
    ref = _appointment_payment_external_ref(t, a)
    assert _parse_appointment_external_ref(ref) == a


def test_parse_appointment_external_ref_empty_string():
    from app.api.v1._helpers.payments_pure import _parse_appointment_external_ref
    assert _parse_appointment_external_ref('') is None
    assert _parse_appointment_external_ref(None) is None


def test_parse_appointment_external_ref_no_appointment_token():
    from app.api.v1._helpers.payments_pure import _parse_appointment_external_ref
    assert _parse_appointment_external_ref('tenant:abc:other:def') is None


def test_parse_appointment_external_ref_invalid_uuid():
    from app.api.v1._helpers.payments_pure import _parse_appointment_external_ref
    assert _parse_appointment_external_ref('tenant:x:appointment:not-a-uuid') is None


def test_parse_appointment_external_ref_appointment_at_end():
    from app.api.v1._helpers.payments_pure import _parse_appointment_external_ref
    # 'appointment' is the last token, no UUID follows
    assert _parse_appointment_external_ref('tenant:foo:appointment') is None


def test_appointment_payment_summary_returns_fields():
    from app.api.v1._helpers.payments_pure import _appointment_payment_summary
    row = _Row(
        id=str(uuid4()),
        payment_status='pending',
        payment_amount=100,
        payment_currency='COP',
        payment_link='https://x',
        payment_provider='mercadopago',
        payment_provider_reference='ext-123',
        payment_link_generated_at=None,
        payment_link_sent_at=None,
        payment_paid_at=None,
    )
    out = _appointment_payment_summary(row)
    assert out['appointment_id'] == row['id']
    assert out['payment_status'] == 'pending'
    assert out['payment_amount'] == 100
    assert out['payment_link'] == 'https://x'
