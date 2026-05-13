"""Generate payment links via external providers (MercadoPago, Stripe).

This module integrates with provider-hosted payment link APIs. No card data
is handled in-app. The link URL is stored in the appointment and sent to the
contact through the existing WhatsApp/conversation channel.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
import structlog

from app.core.config import get_settings
from app.services.circuit_breaker import CircuitOpenError, get_breaker

log = structlog.get_logger()

__all__ = (
    'PaymentLink',
    'PaymentProviderError',
    'CircuitOpenError',
    'generate_payment_link',
    'normalize_provider',
    'verify_mercadopago_signature',
    'verify_stripe_signature',
    'extract_external_ref',
    'extract_payment_status',
)


def _payment_breaker(provider: str):
    try:
        settings = get_settings()
        threshold = settings.circuit_breaker_failure_threshold
        cooldown = settings.circuit_breaker_cooldown_seconds
    except Exception:  # noqa: BLE001
        threshold, cooldown = 5, 30.0
    return get_breaker(
        f'payment:{provider}',
        failure_threshold=threshold,
        cooldown_seconds=cooldown,
    )

SUPPORTED_PROVIDERS = ('mercadopago', 'stripe', 'none')
PAID_STATES = {'paid'}


@dataclass(frozen=True)
class PaymentLink:
    url: str
    provider_reference: str
    raw: dict[str, Any]


class PaymentProviderError(RuntimeError):
    """Raised when a payment provider rejects a request or returns an error."""


def normalize_provider(value: str | None) -> str:
    provider = (value or '').strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise PaymentProviderError(f'Unsupported payment provider: {provider!r}')
    return provider


def _amount_to_cents(amount: Decimal | float | int | str) -> int:
    decimal_amount = Decimal(str(amount))
    return int((decimal_amount * 100).quantize(Decimal('1')))


async def generate_payment_link(
    provider: str,
    api_key: str,
    amount: Decimal | float | int | str,
    currency: str,
    description: str,
    external_ref: str,
    *,
    notification_url: str | None = None,
    success_url: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> PaymentLink:
    """Create a payment link with the given provider and return the URL.

    `external_ref` is stored by the provider and echoed back by the webhook so
    we can map the payment back to the appointment.
    """
    provider = normalize_provider(provider)
    if provider == 'none':
        raise PaymentProviderError('Tenant has no payment provider configured')
    if not api_key:
        raise PaymentProviderError('Payment provider API key is missing')
    try:
        amount_decimal = Decimal(str(amount))
    except Exception as exc:  # noqa: BLE001
        raise PaymentProviderError('Invalid payment amount') from exc
    if amount_decimal <= 0:
        raise PaymentProviderError('Payment amount must be greater than zero')
    currency_code = (currency or 'COP').upper()
    if len(currency_code) != 3:
        raise PaymentProviderError('Invalid currency code')

    breaker = _payment_breaker(provider)
    if provider == 'mercadopago':
        return await breaker.call(
            _create_mercadopago_preference,
            api_key=api_key,
            amount=amount_decimal,
            currency=currency_code,
            description=description,
            external_ref=external_ref,
            notification_url=notification_url,
            success_url=success_url,
            transport=transport,
        )
    if provider == 'stripe':
        return await breaker.call(
            _create_stripe_payment_link,
            api_key=api_key,
            amount=amount_decimal,
            currency=currency_code,
            description=description,
            external_ref=external_ref,
            transport=transport,
        )
    raise PaymentProviderError(f'Provider {provider!r} not implemented')


async def _create_mercadopago_preference(
    *,
    api_key: str,
    amount: Decimal,
    currency: str,
    description: str,
    external_ref: str,
    notification_url: str | None,
    success_url: str | None,
    transport: httpx.AsyncBaseTransport | None,
) -> PaymentLink:
    payload: dict[str, Any] = {
        'items': [
            {
                'title': description or 'Servicio',
                'quantity': 1,
                'unit_price': float(amount),
                'currency_id': currency,
            }
        ],
        'external_reference': external_ref,
    }
    if notification_url:
        payload['notification_url'] = notification_url
    if success_url:
        payload['back_urls'] = {'success': success_url, 'pending': success_url, 'failure': success_url}
        payload['auto_return'] = 'approved'
    async with httpx.AsyncClient(timeout=15, transport=transport) as client:
        response = await client.post(
            'https://api.mercadopago.com/checkout/preferences',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json',
            },
            json=payload,
        )
    if response.status_code >= 400:
        raise PaymentProviderError(
            f'MercadoPago error {response.status_code}: {response.text[:200]}'
        )
    body = response.json()
    url = body.get('init_point') or body.get('sandbox_init_point')
    if not url:
        raise PaymentProviderError('MercadoPago response missing init_point')
    return PaymentLink(url=url, provider_reference=str(body.get('id') or ''), raw=body)


async def _create_stripe_payment_link(
    *,
    api_key: str,
    amount: Decimal,
    currency: str,
    description: str,
    external_ref: str,
    transport: httpx.AsyncBaseTransport | None,
) -> PaymentLink:
    # Stripe requires creating a Price first; we create an inline price tied to a
    # one-shot product. The Payment Link API accepts existing prices only, so we
    # create an ad-hoc product + price via the Prices API.
    async with httpx.AsyncClient(timeout=15, transport=transport) as client:
        price_response = await client.post(
            'https://api.stripe.com/v1/prices',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            data={
                'unit_amount': str(_amount_to_cents(amount)),
                'currency': currency.lower(),
                'product_data[name]': description or 'Servicio',
            },
        )
        if price_response.status_code >= 400:
            raise PaymentProviderError(
                f'Stripe price error {price_response.status_code}: {price_response.text[:200]}'
            )
        price_id = price_response.json().get('id')
        if not price_id:
            raise PaymentProviderError('Stripe price response missing id')
        link_response = await client.post(
            'https://api.stripe.com/v1/payment_links',
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            data={
                'line_items[0][price]': price_id,
                'line_items[0][quantity]': '1',
                'metadata[external_ref]': external_ref,
            },
        )
    if link_response.status_code >= 400:
        raise PaymentProviderError(
            f'Stripe payment_link error {link_response.status_code}: {link_response.text[:200]}'
        )
    body = link_response.json()
    url = body.get('url')
    reference = body.get('id')
    if not url or not reference:
        raise PaymentProviderError('Stripe payment_link response missing url/id')
    return PaymentLink(url=url, provider_reference=str(reference), raw=body)


def verify_mercadopago_signature(
    payload_bytes: bytes,
    signature_header: str | None,
    secret: str | None,
    *,
    request_id: str | None = None,
    data_id: str | None = None,
) -> bool:
    """Verify MercadoPago webhook signature using HMAC-SHA256.

    Newer MP webhooks include `x-signature` like "ts=1700,v1=<hex>". The
    signed manifest is `id:<data_id>;request-id:<request_id>;ts:<ts>;` when
    available, otherwise we fall back to verifying the raw payload digest.
    """
    if not secret or not signature_header:
        return False
    parts = {}
    for chunk in signature_header.split(','):
        if '=' in chunk:
            k, v = chunk.split('=', 1)
            parts[k.strip()] = v.strip()
    expected_hex = parts.get('v1')
    ts = parts.get('ts')
    if not expected_hex:
        return False
    candidates: list[str] = []
    if ts and data_id and request_id:
        candidates.append(f'id:{data_id};request-id:{request_id};ts:{ts};')
    candidates.append(payload_bytes.decode('utf-8', errors='ignore'))
    secret_bytes = secret.encode('utf-8')
    for manifest in candidates:
        computed = hmac.new(secret_bytes, manifest.encode('utf-8'), hashlib.sha256).hexdigest()
        if hmac.compare_digest(computed, expected_hex):
            return True
    return False


def verify_stripe_signature(
    payload_bytes: bytes,
    signature_header: str | None,
    secret: str | None,
    *,
    tolerance_seconds: int = 300,
    now_ts: int | None = None,
) -> bool:
    """Verify Stripe webhook signature (Stripe-Signature header)."""
    if not secret or not signature_header:
        return False
    parts = {}
    signatures: list[str] = []
    for chunk in signature_header.split(','):
        if '=' in chunk:
            k, v = chunk.split('=', 1)
            k = k.strip()
            v = v.strip()
            if k == 'v1':
                signatures.append(v)
            else:
                parts[k] = v
    ts = parts.get('t')
    if not ts or not signatures:
        return False
    try:
        ts_int = int(ts)
    except ValueError:
        return False
    if now_ts is not None and abs(now_ts - ts_int) > tolerance_seconds:
        return False
    signed_payload = f'{ts}.{payload_bytes.decode("utf-8", errors="ignore")}'
    expected = hmac.new(
        secret.encode('utf-8'), signed_payload.encode('utf-8'), hashlib.sha256
    ).hexdigest()
    return any(hmac.compare_digest(expected, sig) for sig in signatures)


def extract_external_ref(provider: str, payload: dict[str, Any]) -> str | None:
    """Pull our external_ref / metadata identifier back from a webhook payload."""
    provider = normalize_provider(provider)
    if provider == 'mercadopago':
        ref = payload.get('external_reference')
        if ref:
            return str(ref)
        data = payload.get('data') if isinstance(payload, dict) else None
        if isinstance(data, dict):
            ref = data.get('external_reference')
            if ref:
                return str(ref)
        resource = payload.get('resource')
        if isinstance(resource, dict):
            ref = resource.get('external_reference')
            if ref:
                return str(ref)
        return None
    if provider == 'stripe':
        data = payload.get('data', {}) if isinstance(payload, dict) else {}
        obj = data.get('object', {}) if isinstance(data, dict) else {}
        metadata = obj.get('metadata') if isinstance(obj, dict) else None
        if isinstance(metadata, dict) and metadata.get('external_ref'):
            return str(metadata['external_ref'])
        return None
    return None


def extract_payment_status(provider: str, payload: dict[str, Any]) -> str | None:
    """Map provider event to our payment_status enum value."""
    provider = normalize_provider(provider)
    if provider == 'mercadopago':
        candidates = []
        if isinstance(payload, dict):
            candidates.append(payload.get('status'))
            data = payload.get('data')
            if isinstance(data, dict):
                candidates.append(data.get('status'))
            resource = payload.get('resource')
            if isinstance(resource, dict):
                candidates.append(resource.get('status'))
        for status in candidates:
            if status == 'approved':
                return 'paid'
            if status in ('rejected', 'cancelled'):
                return 'failed'
            if status in ('refunded', 'charged_back'):
                return 'refunded'
        return None
    if provider == 'stripe':
        event_type = payload.get('type') if isinstance(payload, dict) else None
        if event_type in {'checkout.session.completed', 'payment_intent.succeeded'}:
            return 'paid'
        if event_type in {'payment_intent.payment_failed', 'checkout.session.async_payment_failed'}:
            return 'failed'
        if event_type in {'charge.refunded', 'payment_intent.refunded'}:
            return 'refunded'
        return None
    return None
