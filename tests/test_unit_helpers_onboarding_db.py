"""Unit tests for app/api/v1/_helpers/onboarding_db.py.

Uses _FakeConn to simulate asyncpg without a real DB.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi import HTTPException


class _Row(dict):
    """asyncpg.Record stand-in."""

    def keys(self):  # type: ignore[override]
        return super().keys()


class _FakeConn:
    def __init__(self, *, fetchrow_results=None, fetchval_results=None):
        self._fetchrow = list(fetchrow_results or [])
        self._fetchval = list(fetchval_results or [])

    async def fetchrow(self, sql, *args):
        if not self._fetchrow:
            return None
        return self._fetchrow.pop(0)

    async def fetchval(self, sql, *args):
        if not self._fetchval:
            return None
        return self._fetchval.pop(0)


def _run(coro):
    return asyncio.run(coro)


# ─── _verify_onboarding_business_details ──────────────────────────────────


def test_verify_business_details_tenant_not_found():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_business_details
    conn = _FakeConn(fetchrow_results=[None])
    ok, msg, details = _run(_verify_onboarding_business_details(conn, uuid4()))
    assert ok is False
    assert 'no encontrado' in msg.lower()


def test_verify_business_details_missing_fields():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_business_details
    row = _Row(
        slug=None, legal_name='', display_name='Foo',
        vertical_code='vert', country_code='CO', timezone='America/Bogota',
        status='active', deleted_at=None,
    )
    conn = _FakeConn(fetchrow_results=[row])
    ok, msg, details = _run(_verify_onboarding_business_details(conn, uuid4()))
    assert ok is False
    assert 'slug' in details['missing']
    assert 'legal_name' in details['missing']


def test_verify_business_details_tenant_deleted():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_business_details
    row = _Row(
        slug='s', legal_name='L', display_name='D',
        vertical_code='vert', country_code='CO', timezone='America/Bogota',
        status='active', deleted_at=datetime(2026, 5, 18, tzinfo=UTC),
    )
    conn = _FakeConn(fetchrow_results=[row])
    ok, msg, details = _run(_verify_onboarding_business_details(conn, uuid4()))
    assert ok is False
    assert 'eliminado' in msg.lower()


def test_verify_business_details_complete():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_business_details
    row = _Row(
        slug='biz-co', legal_name='Co SAS', display_name='Co',
        vertical_code='salon', country_code='CO', timezone='America/Bogota',
        status='active', deleted_at=None,
    )
    conn = _FakeConn(fetchrow_results=[row])
    ok, msg, details = _run(_verify_onboarding_business_details(conn, uuid4()))
    assert ok is True
    assert details['slug'] == 'biz-co'
    assert details['vertical_code'] == 'salon'


# ─── _verify_onboarding_locale_currency ───────────────────────────────────


def test_verify_locale_currency_missing_settings():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_locale_currency
    conn = _FakeConn(fetchrow_results=[
        _Row(timezone='America/Bogota'),
        None,  # settings missing
    ])
    ok, msg, _ = _run(_verify_onboarding_locale_currency(conn, uuid4()))
    assert ok is False


def test_verify_locale_currency_missing_fields():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_locale_currency
    conn = _FakeConn(fetchrow_results=[
        _Row(timezone=''),
        _Row(locale='', payment_settings='{}'),
    ])
    ok, msg, details = _run(_verify_onboarding_locale_currency(conn, uuid4()))
    assert ok is False
    assert 'timezone' in details['missing']
    assert 'locale' in details['missing']
    assert 'currency' in details['missing']


def test_verify_locale_currency_with_dict_payment_settings():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_locale_currency
    conn = _FakeConn(fetchrow_results=[
        _Row(timezone='America/Bogota'),
        _Row(locale='es-CO', payment_settings={'currency': 'COP'}),
    ])
    ok, msg, details = _run(_verify_onboarding_locale_currency(conn, uuid4()))
    assert ok is True
    assert details['currency'] == 'COP'


def test_verify_locale_currency_payment_settings_as_string():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_locale_currency
    conn = _FakeConn(fetchrow_results=[
        _Row(timezone='America/Bogota'),
        _Row(locale='es-CO', payment_settings='{"currency":"USD"}'),
    ])
    ok, msg, details = _run(_verify_onboarding_locale_currency(conn, uuid4()))
    assert ok is True
    assert details['currency'] == 'USD'


def test_verify_locale_currency_payment_settings_non_dict():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_locale_currency
    conn = _FakeConn(fetchrow_results=[
        _Row(timezone='America/Bogota'),
        # list, not a dict — currency stays empty
        _Row(locale='es-CO', payment_settings='[1,2,3]'),
    ])
    ok, msg, details = _run(_verify_onboarding_locale_currency(conn, uuid4()))
    assert ok is False
    assert 'currency' in details['missing']


# ─── _verify_onboarding_whatsapp_channel ──────────────────────────────────


def test_verify_whatsapp_channel_missing():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_whatsapp_channel
    conn = _FakeConn(fetchrow_results=[None])
    ok, msg, _ = _run(_verify_onboarding_whatsapp_channel(conn, uuid4()))
    assert ok is False
    assert 'no aprovisionado' in msg.lower()


def test_verify_whatsapp_channel_not_active():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_whatsapp_channel
    conn = _FakeConn(fetchrow_results=[_Row(
        business_id='b', waba_id='w', phone_number_id='p',
        token_ref='r', app_secret_ref='s',
        verify_token_hash_configured=True, status='pending',
    )])
    ok, msg, details = _run(_verify_onboarding_whatsapp_channel(conn, uuid4()))
    assert ok is False
    assert details['status'] == 'pending'


def test_verify_whatsapp_channel_missing_ids():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_whatsapp_channel
    conn = _FakeConn(fetchrow_results=[_Row(
        business_id='b', waba_id=None, phone_number_id='p',
        token_ref='r', app_secret_ref='s',
        verify_token_hash_configured=True, status='active',
    )])
    ok, msg, _ = _run(_verify_onboarding_whatsapp_channel(conn, uuid4()))
    assert ok is False
    assert 'business_id, waba_id' in msg


def test_verify_whatsapp_channel_token_not_configured(monkeypatch):
    from app.api.v1._helpers import onboarding_db
    monkeypatch.setattr(onboarding_db, 'token_ref_is_configured', lambda r: False)
    monkeypatch.setattr(onboarding_db, 'secret_ref_is_configured', lambda r: True)
    conn = _FakeConn(fetchrow_results=[_Row(
        business_id='b', waba_id='w', phone_number_id='p',
        token_ref='r', app_secret_ref='s',
        verify_token_hash_configured=True, status='active',
    )])
    ok, msg, _ = _run(onboarding_db._verify_onboarding_whatsapp_channel(conn, uuid4()))
    assert ok is False
    assert 'token meta' in msg.lower()


def test_verify_whatsapp_channel_app_secret_not_configured(monkeypatch):
    from app.api.v1._helpers import onboarding_db
    monkeypatch.setattr(onboarding_db, 'token_ref_is_configured', lambda r: True)
    # First call (app_secret) returns False; second call (verify token) returns True
    calls = iter([False, True])
    monkeypatch.setattr(onboarding_db, 'secret_ref_is_configured', lambda r: next(calls))
    conn = _FakeConn(fetchrow_results=[_Row(
        business_id='b', waba_id='w', phone_number_id='p',
        token_ref='r', app_secret_ref='s',
        verify_token_hash_configured=True, status='active',
    )])
    ok, msg, _ = _run(onboarding_db._verify_onboarding_whatsapp_channel(conn, uuid4()))
    assert ok is False
    assert 'app secret' in msg.lower()


def test_verify_whatsapp_channel_verify_hash_not_configured(monkeypatch):
    from app.api.v1._helpers import onboarding_db
    monkeypatch.setattr(onboarding_db, 'token_ref_is_configured', lambda r: True)
    monkeypatch.setattr(onboarding_db, 'secret_ref_is_configured', lambda r: True)
    conn = _FakeConn(fetchrow_results=[_Row(
        business_id='b', waba_id='w', phone_number_id='p',
        token_ref='r', app_secret_ref='s',
        verify_token_hash_configured=False, status='active',
    )])
    ok, msg, _ = _run(onboarding_db._verify_onboarding_whatsapp_channel(conn, uuid4()))
    assert ok is False
    assert 'verify token' in msg.lower()


def test_verify_whatsapp_channel_verify_token_ref_not_resolved(monkeypatch):
    from app.api.v1._helpers import onboarding_db
    monkeypatch.setattr(onboarding_db, 'token_ref_is_configured', lambda r: True)
    # First call (app_secret) ok, second call (verify_token_ref) not ok
    calls = iter([True, False])
    monkeypatch.setattr(onboarding_db, 'secret_ref_is_configured', lambda r: next(calls))
    conn = _FakeConn(fetchrow_results=[_Row(
        business_id='b', waba_id='w', phone_number_id='p',
        token_ref='r', app_secret_ref='s',
        verify_token_hash_configured=True, status='active',
    )])
    ok, msg, _ = _run(onboarding_db._verify_onboarding_whatsapp_channel(conn, uuid4()))
    assert ok is False
    assert 'no resuelto' in msg.lower()


def test_verify_whatsapp_channel_ok(monkeypatch):
    from app.api.v1._helpers import onboarding_db
    monkeypatch.setattr(onboarding_db, 'token_ref_is_configured', lambda r: True)
    monkeypatch.setattr(onboarding_db, 'secret_ref_is_configured', lambda r: True)
    conn = _FakeConn(fetchrow_results=[_Row(
        business_id='biz', waba_id='waba', phone_number_id='ph',
        token_ref='r', app_secret_ref='s',
        verify_token_hash_configured=True, status='active',
    )])
    ok, msg, details = _run(onboarding_db._verify_onboarding_whatsapp_channel(conn, uuid4()))
    assert ok is True
    assert details['business_id'] == 'biz'
    assert details['waba_id'] == 'waba'
    assert details['phone_number_id'] == 'ph'


# ─── _verify_onboarding_consent_template ──────────────────────────────────


def test_verify_consent_template_missing():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_consent_template
    conn = _FakeConn(fetchrow_results=[None])
    ok, msg, _ = _run(_verify_onboarding_consent_template(conn, uuid4()))
    assert ok is False
    assert 'no existe el template' in msg.lower()


def test_verify_consent_template_not_approved():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_consent_template
    conn = _FakeConn(fetchrow_results=[_Row(status='pending')])
    ok, msg, details = _run(_verify_onboarding_consent_template(conn, uuid4()))
    assert ok is False
    assert details['status'] == 'pending'


def test_verify_consent_template_approved():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_consent_template
    conn = _FakeConn(fetchrow_results=[_Row(status='approved')])
    ok, msg, details = _run(_verify_onboarding_consent_template(conn, uuid4()))
    assert ok is True
    assert details['status'] == 'approved'


# ─── _verify_onboarding_service_catalog ───────────────────────────────────


def test_verify_service_catalog_empty():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_service_catalog
    conn = _FakeConn(fetchval_results=[0])
    ok, msg, details = _run(_verify_onboarding_service_catalog(conn, uuid4()))
    assert ok is False
    assert details['active_services'] == 0


def test_verify_service_catalog_with_services():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_service_catalog
    conn = _FakeConn(fetchval_results=[5])
    ok, msg, details = _run(_verify_onboarding_service_catalog(conn, uuid4()))
    assert ok is True
    assert details['active_services'] == 5


def test_verify_service_catalog_handles_none():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_service_catalog
    conn = _FakeConn(fetchval_results=[None])
    ok, msg, details = _run(_verify_onboarding_service_catalog(conn, uuid4()))
    assert ok is False


# ─── _verify_onboarding_business_hours ────────────────────────────────────


def test_verify_business_hours_no_settings():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_business_hours
    conn = _FakeConn(fetchrow_results=[None])
    ok, msg, _ = _run(_verify_onboarding_business_hours(conn, uuid4()))
    assert ok is False


def test_verify_business_hours_empty_dict():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_business_hours
    conn = _FakeConn(fetchrow_results=[_Row(business_hours={})])
    ok, msg, _ = _run(_verify_onboarding_business_hours(conn, uuid4()))
    assert ok is False
    assert 'vacíos' in msg.lower() or 'vacio' in msg.lower()


def test_verify_business_hours_no_populated_days():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_business_hours
    conn = _FakeConn(fetchrow_results=[_Row(business_hours={'weekly_schedule': {'mon': [], 'tue': []}})])
    ok, msg, _ = _run(_verify_onboarding_business_hours(conn, uuid4()))
    assert ok is False


def test_verify_business_hours_with_weekly_schedule():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_business_hours
    conn = _FakeConn(fetchrow_results=[_Row(business_hours={
        'weekly_schedule': {'mon': [{'open': '08:00', 'close': '17:00'}], 'tue': [{'open': '09:00', 'close': '18:00'}]},
    })])
    ok, msg, details = _run(_verify_onboarding_business_hours(conn, uuid4()))
    assert ok is True
    assert len(details['days_configured']) == 2


def test_verify_business_hours_with_flat_form():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_business_hours
    conn = _FakeConn(fetchrow_results=[_Row(business_hours={'mon': [{'open': '08:00'}]})])
    ok, msg, details = _run(_verify_onboarding_business_hours(conn, uuid4()))
    assert ok is True
    assert 'mon' in details['days_configured']


def test_verify_business_hours_from_jsonb_string():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_business_hours
    conn = _FakeConn(fetchrow_results=[_Row(business_hours='{"mon": [{"open":"08:00"}]}')])
    ok, msg, details = _run(_verify_onboarding_business_hours(conn, uuid4()))
    assert ok is True


# ─── _verify_onboarding_end_to_end_test ───────────────────────────────────


def test_verify_e2e_no_sent_at():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_end_to_end_test
    conn = _FakeConn(fetchrow_results=[_Row(onboarding_progress={
        'last_completed_step': 0,
        'steps': {'7': {}},
    })])
    ok, msg, _ = _run(_verify_onboarding_end_to_end_test(conn, uuid4()))
    assert ok is False
    assert 'mensaje de prueba' in msg.lower()


def test_verify_e2e_no_target_wa_id():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_end_to_end_test
    conn = _FakeConn(fetchrow_results=[_Row(onboarding_progress={
        'last_completed_step': 0,
        'steps': {'7': {'test_message_sent_at': '2026-05-18T00:00:00+00:00'}},
    })])
    ok, msg, details = _run(_verify_onboarding_end_to_end_test(conn, uuid4()))
    assert ok is False
    assert 'sent_at' in details


def test_verify_e2e_no_inbound():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_end_to_end_test
    conn = _FakeConn(fetchrow_results=[
        _Row(onboarding_progress={
            'last_completed_step': 0,
            'steps': {'7': {
                'test_message_sent_at': '2026-05-18T00:00:00+00:00',
                'target_wa_id': '+5730099',
            }},
        }),
        None,  # inbound query
    ])
    ok, msg, details = _run(_verify_onboarding_end_to_end_test(conn, uuid4()))
    assert ok is False
    assert details['target_wa_id'] == '+5730099'


def test_verify_e2e_success():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_end_to_end_test
    inbound_id = uuid4()
    created = datetime(2026, 5, 18, 11, 0, tzinfo=UTC)
    conn = _FakeConn(fetchrow_results=[
        _Row(onboarding_progress={
            'last_completed_step': 0,
            'steps': {'7': {
                'test_message_sent_at': '2026-05-18T00:00:00+00:00',
                'target_wa_id': '+5730099',
            }},
        }),
        _Row(id=inbound_id, created_at=created, wa_id='+5730099'),
    ])
    ok, msg, details = _run(_verify_onboarding_end_to_end_test(conn, uuid4()))
    assert ok is True
    assert details['inbound_message_id'] == str(inbound_id)


def test_verify_e2e_settings_missing_progress_falls_back():
    from app.api.v1._helpers.onboarding_db import _verify_onboarding_end_to_end_test
    # settings row exists but onboarding_progress is None/empty
    conn = _FakeConn(fetchrow_results=[_Row(onboarding_progress=None)])
    ok, msg, _ = _run(_verify_onboarding_end_to_end_test(conn, uuid4()))
    assert ok is False


# ─── _load_onboarding_progress ────────────────────────────────────────────


def test_load_onboarding_progress_missing_raises_404():
    from app.api.v1._helpers.onboarding_db import _load_onboarding_progress
    conn = _FakeConn(fetchrow_results=[None])
    with pytest.raises(HTTPException) as exc:
        _run(_load_onboarding_progress(conn, uuid4()))
    assert exc.value.status_code == 404


def test_load_onboarding_progress_returns_normalized():
    from app.api.v1._helpers.onboarding_db import _load_onboarding_progress
    conn = _FakeConn(fetchrow_results=[_Row(onboarding_progress={'last_completed_step': 3, 'steps': {}})])
    out = _run(_load_onboarding_progress(conn, uuid4()))
    assert out['last_completed_step'] == 3


def test_load_onboarding_progress_parses_jsonb_string():
    from app.api.v1._helpers.onboarding_db import _load_onboarding_progress
    conn = _FakeConn(fetchrow_results=[_Row(onboarding_progress='{"last_completed_step":2,"steps":{}}')])
    out = _run(_load_onboarding_progress(conn, uuid4()))
    assert out['last_completed_step'] == 2


# ─── ONBOARDING_VERIFIERS dispatch table ──────────────────────────────────


def test_onboarding_verifiers_has_all_seven_steps():
    from app.api.v1._helpers.onboarding_db import ONBOARDING_VERIFIERS
    assert set(ONBOARDING_VERIFIERS.keys()) == {1, 2, 3, 4, 5, 6, 7}
    for v in ONBOARDING_VERIFIERS.values():
        assert callable(v)
