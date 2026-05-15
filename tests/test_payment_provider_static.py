"""Static tests for payment_provider service and payment API surface.

These tests cover the pure-Python helpers (signature verification, payload
parsing, link-builder happy path with a mock provider) and verify that the
new endpoints, schema columns, and admin panel hooks are wired in place.
"""

import asyncio
import hashlib
import hmac
import json
from pathlib import Path

import httpx
import pytest

from app.services.payment_provider import (
    PaymentLink,
    PaymentProviderError,
    extract_external_ref,
    extract_payment_status,
    generate_payment_link,
    normalize_provider,
    verify_mercadopago_signature,
    verify_stripe_signature,
)


SCHEMA = Path('infra/postgres/01-schema.sql')
API_ROUTES = Path('app/api/v1/routes.py')
API_SCHEMAS = Path('app/api/v1/schemas.py')
PAYMENT_SERVICE = Path('app/services/payment_provider.py')
CORE_API = Path('admin-panel/src/services/coreApi.js')
TENANT_SETUP_FEATURE = Path('admin-panel/src/features/owner-admin/tenant-setup')

def _tenant_setup_source() -> str:
    return '\n'.join(p.read_text() for p in sorted(TENANT_SETUP_FEATURE.rglob('*.js*')))

OPERATIONS_DESK = Path('admin-panel/src/features/agente/inbox')


def _operations_desk_source() -> str:
    """Combined source of the Operación · Inbox feature dir (UI-009.1 split).

    OperationsDesk.jsx (2088 LOC) was split into features/agente/inbox/; the
    static assertions below run against the concatenated feature source.
    """
    return '\n'.join(p.read_text() for p in sorted(OPERATIONS_DESK.rglob('*.js*')))


# ───── Provider normalization ─────


def test_normalize_provider_accepts_supported():
    assert normalize_provider('mercadopago') == 'mercadopago'
    assert normalize_provider('STRIPE') == 'stripe'
    assert normalize_provider(' none ') == 'none'


def test_normalize_provider_rejects_unknown():
    with pytest.raises(PaymentProviderError):
        normalize_provider('paypal')


# ───── Signature verification ─────


def test_verify_stripe_signature_accepts_valid_signature():
    payload = b'{"type":"checkout.session.completed"}'
    secret = 'whsec_test'
    ts = '1700000000'
    signed = f'{ts}.{payload.decode()}'.encode()
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    header = f't={ts},v1={expected}'
    assert verify_stripe_signature(payload, header, secret, now_ts=int(ts)) is True


def test_verify_stripe_signature_rejects_tampered_payload():
    payload = b'{"type":"checkout.session.completed"}'
    secret = 'whsec_test'
    ts = '1700000000'
    signed = f'{ts}.{payload.decode()}'.encode()
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    header = f't={ts},v1={expected}'
    tampered = b'{"type":"different.event"}'
    assert verify_stripe_signature(tampered, header, secret, now_ts=int(ts)) is False


def test_verify_stripe_signature_rejects_missing_secret():
    assert verify_stripe_signature(b'{}', 't=1,v1=abc', None) is False
    assert verify_stripe_signature(b'{}', None, 'secret') is False


def test_verify_mercadopago_signature_accepts_raw_payload():
    payload = b'{"action":"payment.updated","data":{"id":"123"}}'
    secret = 'mp_secret'
    expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    header = f'ts=1700,v1={expected}'
    assert verify_mercadopago_signature(payload, header, secret) is True


def test_verify_mercadopago_signature_rejects_unsigned():
    assert verify_mercadopago_signature(b'{}', None, 'secret') is False
    assert verify_mercadopago_signature(b'{}', 'ts=1,v1=abc', None) is False


# ───── External ref / status extraction ─────


def test_extract_external_ref_mercadopago_top_level():
    payload = {'external_reference': 'tenant:t1:appointment:a1'}
    assert extract_external_ref('mercadopago', payload) == 'tenant:t1:appointment:a1'


def test_extract_external_ref_stripe_metadata():
    payload = {
        'type': 'checkout.session.completed',
        'data': {'object': {'metadata': {'external_ref': 'tenant:t1:appointment:a1'}}},
    }
    assert extract_external_ref('stripe', payload) == 'tenant:t1:appointment:a1'


def test_extract_payment_status_mercadopago_approved():
    assert extract_payment_status('mercadopago', {'status': 'approved'}) == 'paid'
    assert extract_payment_status('mercadopago', {'data': {'status': 'rejected'}}) == 'failed'


def test_extract_payment_status_stripe_events():
    assert extract_payment_status('stripe', {'type': 'checkout.session.completed'}) == 'paid'
    assert (
        extract_payment_status('stripe', {'type': 'payment_intent.payment_failed'}) == 'failed'
    )
    assert extract_payment_status('stripe', {'type': 'charge.refunded'}) == 'refunded'


# ───── Link generation (mocked transport) ─────


def _mock_transport(handler):
    return httpx.MockTransport(handler)


def test_generate_payment_link_rejects_unconfigured_provider():
    async def runner():
        with pytest.raises(PaymentProviderError):
            await generate_payment_link('none', 'apikey', 100, 'COP', 'desc', 'ref')

    asyncio.run(runner())


def test_generate_payment_link_requires_api_key():
    async def runner():
        with pytest.raises(PaymentProviderError):
            await generate_payment_link('mercadopago', '', 100, 'COP', 'desc', 'ref')

    asyncio.run(runner())


def test_generate_payment_link_rejects_zero_amount():
    async def runner():
        with pytest.raises(PaymentProviderError):
            await generate_payment_link('mercadopago', 'k', 0, 'COP', 'desc', 'ref')

    asyncio.run(runner())


def test_generate_payment_link_mercadopago_happy_path():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured['url'] = str(request.url)
        captured['auth'] = request.headers.get('authorization')
        captured['body'] = json.loads(request.content.decode())
        return httpx.Response(
            201,
            json={'id': 'pref_123', 'init_point': 'https://mp.example/checkout/pref_123'},
        )

    async def runner():
        link = await generate_payment_link(
            'mercadopago',
            'mp-key',
            50000.5,
            'COP',
            'Diagnóstico',
            'tenant:t1:appointment:a1',
            transport=_mock_transport(handler),
        )
        assert isinstance(link, PaymentLink)
        assert link.url == 'https://mp.example/checkout/pref_123'
        assert link.provider_reference == 'pref_123'

    asyncio.run(runner())
    assert 'mercadopago.com' in captured['url']
    assert captured['auth'] == 'Bearer mp-key'
    assert captured['body']['external_reference'] == 'tenant:t1:appointment:a1'
    assert captured['body']['items'][0]['currency_id'] == 'COP'


def test_generate_payment_link_stripe_happy_path():
    requests_seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests_seen.append(str(request.url))
        if request.url.path.endswith('/prices'):
            return httpx.Response(200, json={'id': 'price_abc'})
        return httpx.Response(
            200,
            json={'id': 'plink_xyz', 'url': 'https://buy.stripe.example/plink_xyz'},
        )

    async def runner():
        link = await generate_payment_link(
            'stripe',
            'sk_test_x',
            120,
            'USD',
            'Cita',
            'tenant:t1:appointment:a1',
            transport=_mock_transport(handler),
        )
        assert link.url == 'https://buy.stripe.example/plink_xyz'
        assert link.provider_reference == 'plink_xyz'

    asyncio.run(runner())
    assert any('prices' in url for url in requests_seen)
    assert any('payment_links' in url for url in requests_seen)


def test_generate_payment_link_stripe_propagates_api_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text='Invalid API key')

    async def runner():
        with pytest.raises(PaymentProviderError):
            await generate_payment_link(
                'stripe',
                'sk_bad',
                100,
                'USD',
                'Cita',
                'ref',
                transport=_mock_transport(handler),
            )

    asyncio.run(runner())


# ───── Schema and wiring checks ─────


def test_schema_has_payment_columns():
    text = SCHEMA.read_text(encoding='utf-8')
    assert 'payment_status text not null default' in text
    assert 'payment_amount numeric' in text
    assert 'payment_link text' in text
    assert 'payment_provider text' in text
    assert 'payment_provider_reference text' in text
    assert "check (payment_status in ('not_required','pending','link_sent','paid','failed','refunded'))" in text
    assert "payment_settings jsonb not null default" in text
    # Webhook events must accept payment providers.
    assert "'whatsapp_cloud_api','mercadopago','stripe'" in text


def test_routes_register_payment_endpoints():
    text = API_ROUTES.read_text(encoding='utf-8')
    assert "@tenant_admin_router.get('/tenants/{tenant_id}/payments/settings')" in text
    assert "@tenant_admin_router.put('/tenants/{tenant_id}/payments/settings')" in text
    assert "@tenant_ops_router.post('/appointments/{appointment_id}/payment-link')" in text
    assert "@tenant_ops_router.post('/appointments/{appointment_id}/send-payment'" in text
    assert "@tenant_ops_router.patch('/appointments/{appointment_id}/payment-status')" in text
    assert "@webhook_router.post('/payments/{provider}'" in text
    # Provider service must be wired into routes.
    assert 'provider_generate_payment_link' in text
    assert 'verify_mercadopago_signature' in text
    assert 'verify_stripe_signature' in text


def test_schemas_expose_payment_models():
    text = API_SCHEMAS.read_text(encoding='utf-8')
    assert 'class AppointmentPaymentLinkRequest' in text
    assert 'class AppointmentPaymentStatusUpdate' in text
    assert 'class TenantPaymentSettingsUpdate' in text
    assert "pattern='^(mercadopago|stripe|none)$'" in text
    assert "pattern='^(not_required|pending|link_sent|paid|failed|refunded)$'" in text


def test_admin_panel_exposes_payment_calls():
    text = CORE_API.read_text(encoding='utf-8')
    for fn in (
        'getTenantPaymentSettings',
        'updateTenantPaymentSettings',
        'generateAppointmentPaymentLink',
        'sendAppointmentPaymentLink',
        'updateAppointmentPaymentStatus',
    ):
        assert f'export function {fn}' in text


def test_tenant_wizard_renders_payments_tab():
    text = _tenant_setup_source()
    assert "{ id: 'pagos', label: 'Pagos' }" in text
    # UI-021: orchestrator now uses a `switch (activeTab)` to render panels.
    assert "case 'pagos':" in text
    assert 'updateTenantPaymentSettings' in text
    assert 'getTenantPaymentSettings' in text


def test_operations_desk_renders_payment_controls():
    text = _operations_desk_source()
    assert 'generateAppointmentPaymentLink' in text
    assert 'sendAppointmentPaymentLink' in text
    assert 'updateAppointmentPaymentStatus' in text
    assert 'handleGeneratePaymentLink' in text
    assert 'handleSendPaymentLink' in text
    assert 'Generar link' in text
    assert 'Enviar por WhatsApp' in text
