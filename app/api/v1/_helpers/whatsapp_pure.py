"""WhatsApp pure helpers + constants extracted from app/api/v1/routes.py."""
from __future__ import annotations

import hashlib
import secrets
from typing import Any

import asyncpg
from fastapi import HTTPException

from app.api.v1._helpers.parsing import parse_json_object
from app.db.pool import record_to_dict


def verify_token_hash(verify_token: str) -> bytes:
    return hashlib.sha256(verify_token.encode('utf-8')).digest()


_WHATSAPP_WEBHOOK_DUMMY_SECRET = secrets.token_hex(32)
"""SEC-010 fix — secret estable usado para defender el oracle del webhook
WhatsApp. Generado al arranque del proceso (token_hex(32) → 64 hex chars,
formato compatible con `normalize_meta_app_secret`), distinto entre
workers, nunca puede coincidir con un App Secret real de Meta (es noise
puro). Cuando el lookup de `tenant_channels` no encuentra el
`phone_number_id`, igual ejecutamos el HMAC contra este dummy para que
el tiempo de respuesta (O(n) sobre el body) sea indistinguible de un
channel real con firma mala — sin esto, un atacante podría enumerar
phone_number_ids activos midiendo la latencia respuesta o el status
code (los dos paths de rechazo retornaban 404 vs 401 distinguibles).
"""


def whatsapp_phone_number_id_from_payload(payload: dict[str, Any]) -> str | None:
    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            value = change.get('value', {})
            metadata = value.get('metadata', {})
            phone_number_id = metadata.get('phone_number_id')
            if phone_number_id:
                return str(phone_number_id)
    return None


MEDIA_MESSAGE_TYPES = {'image', 'audio', 'video'}
SUPPORTED_AGENT_MESSAGE_TYPES = {'text', *MEDIA_MESSAGE_TYPES}


def media_url_from_payload(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get('media_url') or payload.get('link')
    return value.strip() if isinstance(value, str) and value.strip() else None


def validate_outbound_message_content(
    message_type: str,
    body_text: str | None,
    media_id: str | None = None,
    media_url: str | None = None,
) -> None:
    if message_type not in SUPPORTED_AGENT_MESSAGE_TYPES:
        raise HTTPException(status_code=400, detail='Only text, image, audio, and video outbound WhatsApp messages are supported')
    if message_type == 'text' and not (body_text or '').strip():
        raise HTTPException(status_code=400, detail='Text messages require body_text')
    if message_type in MEDIA_MESSAGE_TYPES and not ((media_id or '').strip() or (media_url or '').strip()):
        raise HTTPException(status_code=400, detail=f'{message_type} messages require media_id or payload.media_url')
    # TASK-0079 / BUG19: reject crafted media_id values BEFORE they reach the
    # Graph URL interpolation path. The validator accepts numeric Meta IDs
    # only; anything else (path traversal, query string, NUL bytes) is dropped.
    cleaned_media_id = (media_id or '').strip() if media_id else ''
    if cleaned_media_id:
        from app.services.url_guard import (  # noqa: PLC0415
            UnsafeOutboundURLError,
            assert_whatsapp_media_id,
        )
        try:
            assert_whatsapp_media_id(cleaned_media_id)
        except UnsafeOutboundURLError as exc:
            raise HTTPException(status_code=422, detail=f'media_id rejected: {exc}')


WHATSAPP_TEMPLATE_COLUMNS = (
    'id',
    'tenant_id',
    'channel_id',
    'name',
    'locale',
    'category',
    'status',
    'purpose',
    'components',
    'meta_template_id',
    'rejection_reason',
    'created_at',
    'updated_at',
)
WHATSAPP_TEMPLATE_PROJECTION = ', '.join(WHATSAPP_TEMPLATE_COLUMNS)

WHATSAPP_TEMPLATE_REQUIRED_PURPOSES = (
    'appointment_confirmation',
    'appointment_reminder_24h',
)


def normalize_whatsapp_template(row: asyncpg.Record | None) -> dict | None:
    template = record_to_dict(row)
    if not template:
        return None
    template['components'] = parse_json_object(template.get('components'), default={})
    return template
