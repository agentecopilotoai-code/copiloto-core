"""Shared helpers for Meta's Messenger Platform (Instagram DM + Facebook Messenger).

The Messenger Platform groups Instagram DM and Facebook Messenger under the
same webhook contract:

    {
      "object": "instagram" | "page",
      "entry": [
        {
          "id": "<page_id or ig_account_id>",
          "messaging": [
            {
              "sender": {"id": "<user_psid>"},
              "recipient": {"id": "<page_or_ig_id>"},
              "timestamp": 1700000000000,
              "message": {"mid": "...", "text": "Hola"}
            }
          ]
        }
      ]
    }

Outbound uses the Graph API ``POST /{page_id|ig_account_id}/messages`` endpoint
with a JSON body ``{"recipient": {"id": "<psid>"}, "message": {"text": "..."}}``.

The 24h service window is a Meta policy: outbound is only allowed within 24h of
the user's last inbound, unless using an approved message tag. The policy
engine already enforces it via ``conversations.service_window_expires_at``;
this module computes that expiry per inbound.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.whatsapp import (
    meta_token_is_configured,
    normalize_meta_app_secret,
    resolve_secret_ref,
)


META_MESSENGER_PROVIDERS: frozenset[str] = frozenset({
    'instagram_messenger',
    'facebook_messenger',
})


PROVIDER_OBJECT: dict[str, str] = {
    'instagram_messenger': 'instagram',
    'facebook_messenger': 'page',
}


@dataclass
class NormalizedMessengerEvent:
    """Canonical inbound event after normalizing Meta's Messenger payload.

    The orchestrator only needs ``sender_id``, ``external_message_id`` and the
    text/attachment payload; this dataclass mirrors what WhatsApp's webhook
    handler synthesizes so we can reuse the same downstream flow.
    """

    provider: str
    recipient_id: str
    sender_id: str
    external_message_id: str
    timestamp: datetime | None
    message_type: str
    body_text: str | None
    media_id: str | None
    mime_type: str | None
    raw: dict[str, Any]
    reply_to_external_id: str | None


def verify_messenger_signature(body: bytes, signature: str | None, app_secret: str | None) -> bool:
    """HMAC validation. Identical algorithm to WhatsApp Cloud (Meta-wide).

    Reuses ``normalize_meta_app_secret`` to accept either ``<secret>`` or
    ``<app_id>|<secret>``.
    """
    normalized_secret = normalize_meta_app_secret(app_secret)
    if not signature or not normalized_secret:
        return False
    expected = 'sha256=' + hmac.new(
        normalized_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def expected_object_for_provider(provider: str) -> str | None:
    return PROVIDER_OBJECT.get(provider)


def recipient_id_from_payload(provider: str, payload: dict[str, Any]) -> str | None:
    """Locate the page_id / ig_account_id of the receiving channel.

    Instagram + Facebook embed the recipient as ``entry[].id`` and again as
    ``messaging[].recipient.id``. We prefer the per-event recipient to be
    robust against multi-page webhooks.
    """
    if not isinstance(payload, dict):
        return None
    expected_object = expected_object_for_provider(provider)
    payload_object = payload.get('object')
    if expected_object and payload_object and payload_object != expected_object:
        return None
    for entry in payload.get('entry', []):
        if not isinstance(entry, dict):
            continue
        for event in entry.get('messaging', []) or []:
            if not isinstance(event, dict):
                continue
            recipient = event.get('recipient') or {}
            rid = recipient.get('id') if isinstance(recipient, dict) else None
            if rid:
                return str(rid)
        entry_id = entry.get('id')
        if entry_id:
            return str(entry_id)
    return None


def _parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    try:
        millis = int(value)
    except (TypeError, ValueError):
        return None
    try:
        return datetime.fromtimestamp(millis / 1000.0, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _normalize_attachment(attachments: Any) -> tuple[str, str | None, str | None]:
    """Map Messenger's ``attachments`` array into our ``message_type`` family.

    Returns ``(message_type, media_id, mime_type_or_url)``. Messenger doesn't
    expose a separate ``mime_type``; we store the original payload URL there
    so the inbox can fetch it later. ``media_id`` mirrors WhatsApp's shape:
    Messenger uses URLs, not opaque ids, so we leave the id null and persist
    the link as the mime field — downstream code only reads the payload anyway.
    """
    if not isinstance(attachments, list) or not attachments:
        return 'text', None, None
    first = attachments[0]
    if not isinstance(first, dict):
        return 'text', None, None
    att_type = first.get('type')
    payload = first.get('payload') or {}
    url = payload.get('url') if isinstance(payload, dict) else None
    if att_type in {'image', 'video', 'audio'}:
        return att_type, None, url if isinstance(url, str) else None
    if att_type == 'file':
        return 'document', None, url if isinstance(url, str) else None
    return 'text', None, None


def normalize_messenger_events(
    provider: str,
    payload: dict[str, Any],
) -> list[NormalizedMessengerEvent]:
    """Walk the webhook payload and emit one event per inbound message.

    Skips echoes (``message.is_echo``), delivery receipts, reads, and any
    payload shape that doesn't match an inbound message.
    """
    if provider not in META_MESSENGER_PROVIDERS:
        return []
    events: list[NormalizedMessengerEvent] = []
    if not isinstance(payload, dict):
        return events
    for entry in payload.get('entry', []) or []:
        if not isinstance(entry, dict):
            continue
        for event in entry.get('messaging', []) or []:
            if not isinstance(event, dict):
                continue
            message = event.get('message')
            if not isinstance(message, dict):
                continue
            if message.get('is_echo'):
                continue
            sender = event.get('sender') or {}
            recipient = event.get('recipient') or {}
            sender_id = sender.get('id') if isinstance(sender, dict) else None
            recipient_id = recipient.get('id') if isinstance(recipient, dict) else None
            if not sender_id or not recipient_id:
                continue
            mid = message.get('mid')
            if not isinstance(mid, str) or not mid:
                continue
            text = message.get('text') if isinstance(message.get('text'), str) else None
            attachments = message.get('attachments')
            message_type, media_id, mime_or_url = _normalize_attachment(attachments)
            if text is None and message_type == 'text':
                # No text and no recognised attachment — skip.
                continue
            reply_to_external_id: str | None = None
            reply_to = message.get('reply_to')
            if isinstance(reply_to, dict):
                candidate = reply_to.get('mid')
                if isinstance(candidate, str) and candidate:
                    reply_to_external_id = candidate
            events.append(
                NormalizedMessengerEvent(
                    provider=provider,
                    recipient_id=str(recipient_id),
                    sender_id=str(sender_id),
                    external_message_id=str(mid),
                    timestamp=_parse_timestamp(event.get('timestamp')),
                    message_type=message_type,
                    body_text=text,
                    media_id=media_id,
                    mime_type=mime_or_url,
                    raw=event,
                    reply_to_external_id=reply_to_external_id,
                )
            )
    return events


def is_within_service_window(
    last_inbound_at: datetime | None,
    window_hours: int = 24,
    now: datetime | None = None,
) -> bool:
    """Meta's 24h Messenger window: outbound allowed only within ``window_hours``."""
    if last_inbound_at is None:
        return False
    if last_inbound_at.tzinfo is None:
        last_inbound_at = last_inbound_at.replace(tzinfo=timezone.utc)
    reference = now or datetime.now(timezone.utc)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    return reference - last_inbound_at <= timedelta(hours=max(1, window_hours))


def service_window_expiry(
    last_inbound_at: datetime,
    window_hours: int = 24,
) -> datetime:
    if last_inbound_at.tzinfo is None:
        last_inbound_at = last_inbound_at.replace(tzinfo=timezone.utc)
    return last_inbound_at + timedelta(hours=max(1, window_hours))


def build_messenger_send_payload(
    recipient_psid: str,
    text: str | None = None,
    media_url: str | None = None,
    media_type: str | None = None,
) -> dict[str, Any]:
    """Construct the JSON body for ``POST /{id}/messages``.

    Only supports text and an attachment with URL. Interactive cards and
    quick replies are not part of this MVP scope (Meta's Messenger interactive
    APIs differ enough from WhatsApp's to deserve their own surface).
    """
    if not recipient_psid:
        raise ValueError('recipient_psid is required')
    body: dict[str, Any] = {
        'recipient': {'id': str(recipient_psid)},
        'messaging_type': 'RESPONSE',
    }
    if media_url:
        attachment_type = (media_type or 'image').lower()
        if attachment_type not in {'image', 'video', 'audio', 'file'}:
            attachment_type = 'image'
        body['message'] = {
            'attachment': {
                'type': attachment_type,
                'payload': {'url': str(media_url), 'is_reusable': False},
            },
        }
        return body
    if text is None or not str(text).strip():
        raise ValueError('Messenger send requires either text or media_url')
    body['message'] = {'text': str(text).strip()}
    return body


class OutsideServiceWindowError(RuntimeError):
    """Raised when an outbound message is rejected because the 24h window expired."""


async def send_messenger_message(
    provider: str,
    recipient_account_id: str,
    recipient_psid: str,
    *,
    text: str | None = None,
    media_url: str | None = None,
    media_type: str | None = None,
    delivery_mode: str = 'mock',
    token_ref: str | None = None,
    within_service_window: bool = True,
) -> dict[str, Any]:
    """Send a Messenger message via the Meta Graph API.

    The 24h gate is enforced by the caller (the worker) which computes
    ``within_service_window`` from ``conversations.service_window_expires_at``.
    A `False` value raises ``OutsideServiceWindowError`` with the canonical
    error code ``outside_service_window`` so the DLQ can surface it.
    """
    if provider not in META_MESSENGER_PROVIDERS:
        raise ValueError(f'Unsupported messenger provider: {provider}')
    if not within_service_window:
        raise OutsideServiceWindowError('outside_service_window')
    payload = build_messenger_send_payload(
        recipient_psid=recipient_psid,
        text=text,
        media_url=media_url,
        media_type=media_type,
    )
    if delivery_mode != 'live':
        return {
            'mocked': True,
            'delivery_mode': 'mock',
            'provider': provider,
            'recipient_account_id': recipient_account_id,
            'recipient_psid': recipient_psid,
            'message': payload,
        }
    access_token = resolve_secret_ref(token_ref)
    if not meta_token_is_configured(access_token):
        raise RuntimeError(
            f'{provider} delivery mode is live, but token_ref did not resolve to a real Meta access token.'
        )
    settings = get_settings()
    url = f'https://graph.facebook.com/{settings.meta_graph_version}/{recipient_account_id}/messages'
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            url,
            headers={'Authorization': f'Bearer {access_token}'},
            json=payload,
        )
        response.raise_for_status()
        return response.json()


def serialize_event_for_storage(event: NormalizedMessengerEvent) -> str:
    """Compact JSON for the ``messages.payload`` column."""
    serializable = {
        'provider': event.provider,
        'recipient_id': event.recipient_id,
        'sender_id': event.sender_id,
        'external_message_id': event.external_message_id,
        'timestamp': event.timestamp.isoformat() if event.timestamp else None,
        'message_type': event.message_type,
        'body_text': event.body_text,
        'media_id': event.media_id,
        'mime_type': event.mime_type,
        'reply_to_external_id': event.reply_to_external_id,
        'raw': event.raw,
    }
    return json.dumps(serializable)
