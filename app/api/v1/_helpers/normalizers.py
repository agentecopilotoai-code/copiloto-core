"""Record-to-dict normalizers extracted from app/api/v1/routes.py."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg

from app.api.v1._helpers.parsing import parse_json_object
from app.db.pool import record_to_dict
from app.services.whatsapp import secret_ref_is_configured, token_ref_is_configured


def _normalize_messenger_channel(row: asyncpg.Record | None) -> dict[str, Any] | None:
    channel = record_to_dict(row)
    if not channel:
        return None
    channel['token_configured'] = token_ref_is_configured(channel.get('token_ref'))
    channel['app_secret_configured'] = secret_ref_is_configured(channel.get('app_secret_ref'))
    channel['verify_token_configured'] = bool(channel.get('verify_token_hash'))
    # Avoid leaking raw bytes through JSON. The bool flag is enough.
    channel.pop('verify_token_hash', None)
    return channel


def _normalize_web_channel(row: asyncpg.Record | None) -> dict[str, Any] | None:
    channel = record_to_dict(row)
    if not channel:
        return None
    channel['allowed_origins'] = list(channel.get('allowed_origins') or [])
    channel['widget_config'] = parse_json_object(channel.get('widget_config'), default={})
    return channel


# TASK-0067: digest_subscriptions CRUD. Cada fila pinea un destinatario
# (email, whatsapp o ambos) a una cadencia (daily/weekly) — el worker
# `digest_worker` itera estas filas y dispara a las 08:00 hora local del
# tenant.
def _digest_subscription_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    return {
        'id': str(row['id']),
        'recipient_email': row['recipient_email'] or '',
        'recipient_whatsapp': row['recipient_whatsapp'] or '',
        'cadence': row['cadence'],
        'enabled': bool(row['enabled']),
        'last_sent_at': row['last_sent_at'].isoformat() if row['last_sent_at'] else None,
        'created_at': row['created_at'].isoformat() if row['created_at'] else None,
        'updated_at': row['updated_at'].isoformat() if row['updated_at'] else None,
    }


def normalize_service_catalog_row(row: asyncpg.Record | None) -> dict | None:
    service = record_to_dict(row)
    if not service:
        return None
    service['metadata'] = parse_json_object(service.get('metadata'), default={})
    # TASK-0054: applies_when is normalized when written, but rows persisted
    # before this column existed could surface here as null — coerce to {}.
    raw_rules = service.get('applies_when')
    if isinstance(raw_rules, str):
        try:
            service['applies_when'] = json.loads(raw_rules) if raw_rules else {}
        except json.JSONDecodeError:
            service['applies_when'] = {}
    elif raw_rules is None:
        service['applies_when'] = {}
    if service.get('price_amount') is not None:
        service['price_amount'] = float(service['price_amount'])
    return service


def normalize_qualification_question(row: asyncpg.Record | None) -> dict | None:
    question = record_to_dict(row)
    if not question:
        return None
    options = question.get('options')
    if isinstance(options, str):
        try:
            question['options'] = json.loads(options)
        except json.JSONDecodeError:
            question['options'] = []
    elif not isinstance(options, list):
        question['options'] = []
    applies = question.get('applies_to_service_ids') or []
    question['applies_to_service_ids'] = [str(item) for item in applies]
    return question


def normalize_media_asset(row: asyncpg.Record | None) -> dict | None:
    asset = record_to_dict(row)
    if not asset:
        return None
    asset['tags'] = list(asset.get('tags') or [])
    return asset


def normalize_promotion(row: asyncpg.Record | None) -> dict | None:
    promo = record_to_dict(row)
    if not promo:
        return None
    promo['applies_to_service_ids'] = [str(s) for s in (promo.get('applies_to_service_ids') or [])]
    if promo.get('discount_percent') is not None:
        promo['discount_percent'] = float(promo['discount_percent'])
    return promo


def normalize_segment_row(row: asyncpg.Record | None) -> dict | None:
    seg = record_to_dict(row)
    if not seg:
        return None
    seg['rules'] = parse_json_object(seg.get('rules'), default={})
    return seg


def normalize_campaign(row: asyncpg.Record | None) -> dict | None:
    campaign = record_to_dict(row)
    if not campaign:
        return None
    campaign['template_variables'] = parse_json_object(campaign.get('template_variables'), default={})
    campaign['segment_filter'] = parse_json_object(campaign.get('segment_filter'), default={})
    return campaign


def _legal_row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    return {
        'id': str(row['id']),
        'tenant_id': str(row['tenant_id']),
        'kind': row['kind'],
        'language': row['language'],
        'version': row['version'],
        'title': row['title'],
        'content_md': row['content_md'],
        'published_at': row['published_at'].isoformat() if row['published_at'] else None,
        'archived_at': row['archived_at'].isoformat() if row['archived_at'] else None,
        'created_at': row['created_at'].isoformat() if row['created_at'] else None,
    }


def _serialize_profile(prefs_row: asyncpg.Record, user_row: asyncpg.Record, user_id: UUID) -> dict:
    """Merge user_preferences (app cache) with app.users (Auth0-synced canonical fields)."""
    return {
        'user_id': str(user_id),
        'email': user_row['email'],
        # The cached display_name in user_preferences wins (the user explicitly
        # set it); fall back to the Auth0-synced one on app.users.
        'display_name': prefs_row['display_name'] or user_row['display_name'],
        'phone': prefs_row['phone'],
        'locale': prefs_row['locale'],
        'timezone': prefs_row['timezone'],
        'theme_override': prefs_row['theme_override'],
        'auth0_synced_at': (
            prefs_row['auth0_synced_at'].isoformat()
            if prefs_row['auth0_synced_at'] is not None
            else None
        ),
        'mfa_enabled': user_row['mfa_enabled'],
        'last_login_at': (
            user_row['last_login_at'].isoformat()
            if user_row['last_login_at'] is not None
            else None
        ),
    }
