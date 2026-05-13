"""Recurring subscriptions / memberships with provider-managed billing.

This module owns the mapping from Stripe / MercadoPago invoice webhook events to
``app.contact_subscriptions`` state transitions, and queues a WhatsApp message
that points the customer to the retry payment link when a recurring charge
fails.

Plans are persisted locally; the actual subscription lifecycle (creating the
provider-side subscription, charging the card, retrying) is handled by the
payment provider. We only react to the events they fire back at us.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.payment_provider import normalize_provider as normalize_payment_provider

__all__ = (
    'SUBSCRIPTION_STATUSES',
    'BILLING_PERIODS',
    'INVOICE_FAILED_TEMPLATE',
    'SubscriptionInvoiceEvent',
    'extract_subscription_event',
)


SUBSCRIPTION_STATUSES = ('active', 'past_due', 'cancelled')
BILLING_PERIODS = ('monthly', 'quarterly', 'yearly')
INVOICE_FAILED_TEMPLATE = 'subscription_payment_failed_v1'


@dataclass(frozen=True)
class SubscriptionInvoiceEvent:
    """Provider-agnostic representation of a recurring invoice event.

    ``new_status`` is the status we should set on ``contact_subscriptions`` if
    the lookup by ``provider_subscription_id`` succeeds. ``retry_url`` is the
    hosted invoice URL that the bot will forward to the customer when the
    charge fails so they can re-enter their card.
    """

    provider: str
    event_kind: str  # 'invoice.payment_succeeded' | 'invoice.payment_failed'
    provider_subscription_id: str
    new_status: str  # 'active' | 'past_due'
    retry_url: str | None
    next_billing_at: str | None
    raw: dict[str, Any]


def extract_subscription_event(
    provider: str, payload: dict[str, Any]
) -> SubscriptionInvoiceEvent | None:
    """Translate a Stripe/MercadoPago webhook payload into a subscription event.

    Returns ``None`` when the payload is not a subscription invoice event we
    care about (e.g. one-shot payment links, refunds, or unsupported event
    types).
    """
    provider = normalize_payment_provider(provider)
    if provider == 'stripe':
        return _stripe_subscription_event(payload)
    if provider == 'mercadopago':
        return _mercadopago_subscription_event(payload)
    return None


def _stripe_subscription_event(payload: dict[str, Any]) -> SubscriptionInvoiceEvent | None:
    event_type = payload.get('type') if isinstance(payload, dict) else None
    if event_type not in {'invoice.payment_succeeded', 'invoice.payment_failed'}:
        return None
    data = payload.get('data', {}) if isinstance(payload, dict) else {}
    obj = data.get('object', {}) if isinstance(data, dict) else {}
    if not isinstance(obj, dict):
        return None
    subscription_id = obj.get('subscription')
    if not subscription_id:
        return None
    retry_url = obj.get('hosted_invoice_url') or obj.get('invoice_pdf')
    next_payment = obj.get('next_payment_attempt')
    new_status = 'active' if event_type == 'invoice.payment_succeeded' else 'past_due'
    return SubscriptionInvoiceEvent(
        provider='stripe',
        event_kind=event_type,
        provider_subscription_id=str(subscription_id),
        new_status=new_status,
        retry_url=str(retry_url) if retry_url else None,
        next_billing_at=str(next_payment) if next_payment else None,
        raw=payload,
    )


def _mercadopago_subscription_event(payload: dict[str, Any]) -> SubscriptionInvoiceEvent | None:
    if not isinstance(payload, dict):
        return None
    event_type = payload.get('type') or payload.get('action') or ''
    # MercadoPago "preapproval" / "subscription" billings emit type='subscription_authorized_payment'
    # with action 'updated', and the data.status is 'approved' / 'rejected'.
    if not isinstance(event_type, str) or 'subscription' not in event_type:
        return None
    data = payload.get('data')
    if not isinstance(data, dict):
        return None
    subscription_id = data.get('preapproval_id') or data.get('subscription_id') or data.get('id')
    status = (data.get('status') or '').lower()
    if not subscription_id or not status:
        return None
    if status == 'approved':
        kind = 'invoice.payment_succeeded'
        new_status = 'active'
    elif status in ('rejected', 'recurring_charges_failed'):
        kind = 'invoice.payment_failed'
        new_status = 'past_due'
    else:
        return None
    retry_url = data.get('init_point') or data.get('payment_url')
    next_billing = data.get('next_payment_date')
    return SubscriptionInvoiceEvent(
        provider='mercadopago',
        event_kind=kind,
        provider_subscription_id=str(subscription_id),
        new_status=new_status,
        retry_url=str(retry_url) if retry_url else None,
        next_billing_at=str(next_billing) if next_billing else None,
        raw=payload,
    )
