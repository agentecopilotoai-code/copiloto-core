"""Payments pure helpers extracted from app/api/v1/routes.py."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from app.db.pool import record_to_dict
from app.services.whatsapp import secret_ref_is_configured


def _normalize_payment_settings(value: Any) -> dict[str, Any]:
    """Read tenant payment_settings jsonb into a dict with predictable keys."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {}
    if not isinstance(value, dict):
        value = {}
    provider = value.get('provider') or 'none'
    if provider not in {'mercadopago', 'stripe', 'none'}:
        provider = 'none'
    return {
        'provider': provider,
        'currency': (value.get('currency') or 'COP').upper()[:3],
        'default_amount': value.get('default_amount'),
        'api_key_ref': value.get('api_key_ref'),
        'webhook_secret_ref': value.get('webhook_secret_ref'),
    }


def _public_payment_settings(tenant_id: UUID, settings: dict[str, Any]) -> dict[str, Any]:
    """Strip secrets from payment settings before returning them to the panel."""
    normalized = _normalize_payment_settings(settings)
    return {
        'provider': normalized['provider'],
        'currency': normalized['currency'],
        'default_amount': normalized['default_amount'],
        'api_key_configured': secret_ref_is_configured(normalized['api_key_ref']),
        'webhook_secret_configured': secret_ref_is_configured(normalized['webhook_secret_ref']),
        'tenant_id': str(tenant_id),
    }


def _appointment_payment_external_ref(tenant_id: UUID, appointment_id: UUID) -> str:
    return f'tenant:{tenant_id}:appointment:{appointment_id}'


def _parse_appointment_external_ref(ref: str | None) -> UUID | None:
    if not ref:
        return None
    tokens = ref.split(':')
    for index, token in enumerate(tokens):
        if token == 'appointment' and index + 1 < len(tokens):
            try:
                return UUID(tokens[index + 1])
            except ValueError:
                return None
    return None


def _appointment_payment_summary(row: asyncpg.Record) -> dict[str, Any]:
    appointment = record_to_dict(row)
    return {
        'appointment_id': appointment.get('id'),
        'payment_status': appointment.get('payment_status'),
        'payment_amount': appointment.get('payment_amount'),
        'payment_currency': appointment.get('payment_currency'),
        'payment_link': appointment.get('payment_link'),
        'payment_provider': appointment.get('payment_provider'),
        'payment_provider_reference': appointment.get('payment_provider_reference'),
        'payment_link_generated_at': appointment.get('payment_link_generated_at'),
        'payment_link_sent_at': appointment.get('payment_link_sent_at'),
        'payment_paid_at': appointment.get('payment_paid_at'),
    }
