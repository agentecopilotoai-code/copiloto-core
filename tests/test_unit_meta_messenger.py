"""Tests for `app/services/meta_messenger.py` — sig verify, normalization,
event parsing, 24h service window, send payload builder, mock send."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest


# ───────── verify_messenger_signature ────────────────────────────────────


def test_verify_messenger_signature_valid():
    from app.services.meta_messenger import verify_messenger_signature
    secret = 'fb_app_secret'
    body = b'{"object":"page"}'
    sig = 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_messenger_signature(body, sig, secret) is True


def test_verify_messenger_signature_invalid():
    from app.services.meta_messenger import verify_messenger_signature
    assert verify_messenger_signature(b'body', 'sha256=deadbeef', 'sec') is False


def test_verify_messenger_signature_missing_inputs():
    from app.services.meta_messenger import verify_messenger_signature
    assert verify_messenger_signature(b'body', None, 'sec') is False
    assert verify_messenger_signature(b'body', 'sha256=x', None) is False


# ───────── expected_object_for_provider ──────────────────────────────────


def test_expected_object_for_provider_known():
    from app.services.meta_messenger import expected_object_for_provider
    assert expected_object_for_provider('instagram_messenger') == 'instagram'
    assert expected_object_for_provider('facebook_messenger') == 'page'
    assert expected_object_for_provider('whatsapp_cloud_api') is None


# ───────── recipient_id_from_payload ─────────────────────────────────────


def test_recipient_id_from_payload_uses_messaging_recipient():
    from app.services.meta_messenger import recipient_id_from_payload
    payload = {
        'object': 'page',
        'entry': [
            {'id': 'page_id', 'messaging': [
                {'recipient': {'id': 'preferred_page_id'}},
            ]},
        ],
    }
    assert recipient_id_from_payload('facebook_messenger', payload) == 'preferred_page_id'


def test_recipient_id_from_payload_falls_back_to_entry_id():
    from app.services.meta_messenger import recipient_id_from_payload
    payload = {
        'object': 'page',
        'entry': [{'id': 'page_id', 'messaging': []}],
    }
    assert recipient_id_from_payload('facebook_messenger', payload) == 'page_id'


def test_recipient_id_from_payload_rejects_wrong_object():
    from app.services.meta_messenger import recipient_id_from_payload
    payload = {'object': 'instagram', 'entry': [{'id': 'x'}]}
    # Wrong object type → returns None
    assert recipient_id_from_payload('facebook_messenger', payload) is None


def test_recipient_id_from_payload_none_for_non_dict():
    from app.services.meta_messenger import recipient_id_from_payload
    assert recipient_id_from_payload('facebook_messenger', 'not a dict') is None
    assert recipient_id_from_payload('facebook_messenger', {'entry': []}) is None


# ───────── _parse_timestamp ──────────────────────────────────────────────


def test_parse_timestamp_millis():
    from app.services.meta_messenger import _parse_timestamp
    dt = _parse_timestamp(1_700_000_000_000)
    assert dt is not None
    assert dt.tzinfo == timezone.utc


def test_parse_timestamp_string():
    from app.services.meta_messenger import _parse_timestamp
    dt = _parse_timestamp('1700000000000')
    assert dt is not None


def test_parse_timestamp_invalid():
    from app.services.meta_messenger import _parse_timestamp
    assert _parse_timestamp(None) is None
    assert _parse_timestamp('not a number') is None


# ───────── _normalize_attachment ─────────────────────────────────────────


def test_normalize_attachment_text_default():
    from app.services.meta_messenger import _normalize_attachment
    assert _normalize_attachment(None) == ('text', None, None)
    assert _normalize_attachment([]) == ('text', None, None)


def test_normalize_attachment_image():
    from app.services.meta_messenger import _normalize_attachment
    out = _normalize_attachment([
        {'type': 'image', 'payload': {'url': 'https://x/img.jpg'}},
    ])
    assert out == ('image', None, 'https://x/img.jpg')


def test_normalize_attachment_video_no_url():
    from app.services.meta_messenger import _normalize_attachment
    out = _normalize_attachment([{'type': 'video', 'payload': {}}])
    assert out == ('video', None, None)


def test_normalize_attachment_file_maps_to_document():
    from app.services.meta_messenger import _normalize_attachment
    out = _normalize_attachment([
        {'type': 'file', 'payload': {'url': 'https://x/doc.pdf'}},
    ])
    assert out == ('document', None, 'https://x/doc.pdf')


def test_normalize_attachment_unknown_type_falls_to_text():
    from app.services.meta_messenger import _normalize_attachment
    assert _normalize_attachment([{'type': 'unknown'}]) == ('text', None, None)


# ───────── normalize_messenger_events ────────────────────────────────────


def test_normalize_messenger_events_simple_text():
    from app.services.meta_messenger import normalize_messenger_events
    payload = {
        'entry': [
            {'messaging': [
                {
                    'sender': {'id': 'u1'},
                    'recipient': {'id': 'p1'},
                    'timestamp': 1700000000000,
                    'message': {'mid': 'm1', 'text': 'Hola'},
                },
            ]},
        ],
    }
    events = normalize_messenger_events('facebook_messenger', payload)
    assert len(events) == 1
    assert events[0].body_text == 'Hola'
    assert events[0].message_type == 'text'
    assert events[0].sender_id == 'u1'
    assert events[0].recipient_id == 'p1'


def test_normalize_messenger_events_skips_echo():
    from app.services.meta_messenger import normalize_messenger_events
    payload = {
        'entry': [
            {'messaging': [
                {
                    'sender': {'id': 'u1'},
                    'recipient': {'id': 'p1'},
                    'message': {'mid': 'm1', 'text': 'Hi', 'is_echo': True},
                },
            ]},
        ],
    }
    assert normalize_messenger_events('facebook_messenger', payload) == []


def test_normalize_messenger_events_skips_missing_ids():
    from app.services.meta_messenger import normalize_messenger_events
    payload = {
        'entry': [
            {'messaging': [
                {'message': {'mid': 'm1', 'text': 'Hi'}},
            ]},
        ],
    }
    assert normalize_messenger_events('facebook_messenger', payload) == []


def test_normalize_messenger_events_skips_unknown_provider():
    from app.services.meta_messenger import normalize_messenger_events
    assert normalize_messenger_events('whatsapp', {'entry': []}) == []


def test_normalize_messenger_events_image_attachment():
    from app.services.meta_messenger import normalize_messenger_events
    payload = {
        'entry': [
            {'messaging': [
                {
                    'sender': {'id': 'u1'},
                    'recipient': {'id': 'p1'},
                    'message': {
                        'mid': 'm2',
                        'attachments': [
                            {'type': 'image', 'payload': {'url': 'https://x/i.jpg'}},
                        ],
                    },
                },
            ]},
        ],
    }
    events = normalize_messenger_events('facebook_messenger', payload)
    assert len(events) == 1
    assert events[0].message_type == 'image'
    assert events[0].mime_type == 'https://x/i.jpg'


def test_normalize_messenger_events_reply_to():
    from app.services.meta_messenger import normalize_messenger_events
    payload = {
        'entry': [
            {'messaging': [
                {
                    'sender': {'id': 'u1'},
                    'recipient': {'id': 'p1'},
                    'message': {
                        'mid': 'm3',
                        'text': 'gracias',
                        'reply_to': {'mid': 'm-prev'},
                    },
                },
            ]},
        ],
    }
    events = normalize_messenger_events('facebook_messenger', payload)
    assert events[0].reply_to_external_id == 'm-prev'


def test_normalize_messenger_events_non_dict_payload():
    from app.services.meta_messenger import normalize_messenger_events
    assert normalize_messenger_events('facebook_messenger', 'not a dict') == []


def test_normalize_messenger_events_skips_text_none_no_attachment():
    from app.services.meta_messenger import normalize_messenger_events
    # No text and no attachment → skipped
    payload = {
        'entry': [
            {'messaging': [
                {
                    'sender': {'id': 'u1'},
                    'recipient': {'id': 'p1'},
                    'message': {'mid': 'm1'},
                },
            ]},
        ],
    }
    assert normalize_messenger_events('facebook_messenger', payload) == []


# ───────── is_within_service_window / service_window_expiry ──────────────


def test_is_within_service_window_returns_false_when_no_last_inbound():
    from app.services.meta_messenger import is_within_service_window
    assert is_within_service_window(None) is False


def test_is_within_service_window_true_within_24h():
    from app.services.meta_messenger import is_within_service_window
    now = datetime.now(timezone.utc)
    assert is_within_service_window(now - timedelta(hours=12), now=now) is True


def test_is_within_service_window_false_outside_24h():
    from app.services.meta_messenger import is_within_service_window
    now = datetime.now(timezone.utc)
    assert is_within_service_window(now - timedelta(hours=48), now=now) is False


def test_is_within_service_window_handles_naive_datetime():
    """If last_inbound_at is naive, helper treats it as UTC."""
    from app.services.meta_messenger import is_within_service_window
    now = datetime.now(timezone.utc)
    naive = (now - timedelta(hours=10)).replace(tzinfo=None)
    assert is_within_service_window(naive, now=now) is True


def test_service_window_expiry_adds_24h():
    from app.services.meta_messenger import service_window_expiry
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    expiry = service_window_expiry(base)
    assert (expiry - base) == timedelta(hours=24)


def test_service_window_expiry_naive_input():
    from app.services.meta_messenger import service_window_expiry
    base_naive = datetime(2026, 1, 1)
    expiry = service_window_expiry(base_naive)
    assert expiry.tzinfo is timezone.utc


def test_service_window_expiry_custom_hours():
    from app.services.meta_messenger import service_window_expiry
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    expiry = service_window_expiry(base, window_hours=48)
    assert (expiry - base) == timedelta(hours=48)


# ───────── build_messenger_send_payload ──────────────────────────────────


def test_build_messenger_send_payload_text():
    from app.services.meta_messenger import build_messenger_send_payload
    body = build_messenger_send_payload(recipient_psid='psid1', text='hola')
    assert body['recipient']['id'] == 'psid1'
    assert body['messaging_type'] == 'RESPONSE'
    assert body['message']['text'] == 'hola'


def test_build_messenger_send_payload_image():
    from app.services.meta_messenger import build_messenger_send_payload
    body = build_messenger_send_payload(
        recipient_psid='psid1', media_url='https://x/i.jpg', media_type='image',
    )
    att = body['message']['attachment']
    assert att['type'] == 'image'
    assert att['payload']['url'] == 'https://x/i.jpg'


def test_build_messenger_send_payload_unknown_media_falls_to_image():
    from app.services.meta_messenger import build_messenger_send_payload
    body = build_messenger_send_payload(
        recipient_psid='p', media_url='https://x/x', media_type='sticker',
    )
    assert body['message']['attachment']['type'] == 'image'


def test_build_messenger_send_payload_rejects_no_recipient():
    from app.services.meta_messenger import build_messenger_send_payload
    with pytest.raises(ValueError):
        build_messenger_send_payload(recipient_psid='', text='x')


def test_build_messenger_send_payload_rejects_no_text_or_media():
    from app.services.meta_messenger import build_messenger_send_payload
    with pytest.raises(ValueError):
        build_messenger_send_payload(recipient_psid='psid', text=None)
    with pytest.raises(ValueError):
        build_messenger_send_payload(recipient_psid='psid', text='   ')


# ───────── send_messenger_message ────────────────────────────────────────


def test_send_messenger_message_rejects_unknown_provider():
    from app.services.meta_messenger import send_messenger_message

    async def _go():
        return await send_messenger_message(
            'whatsapp', recipient_account_id='x', recipient_psid='y', text='hi',
        )

    with pytest.raises(ValueError):
        asyncio.run(_go())


def test_send_messenger_message_outside_window_raises():
    from app.services.meta_messenger import (
        OutsideServiceWindowError,
        send_messenger_message,
    )

    async def _go():
        return await send_messenger_message(
            'facebook_messenger',
            recipient_account_id='page1', recipient_psid='psid1',
            text='hi', within_service_window=False,
        )

    with pytest.raises(OutsideServiceWindowError):
        asyncio.run(_go())


def test_send_messenger_message_mock_mode():
    from app.services.meta_messenger import send_messenger_message

    async def _go():
        return await send_messenger_message(
            'facebook_messenger',
            recipient_account_id='page1', recipient_psid='psid1',
            text='hola desde mock', delivery_mode='mock',
        )

    out = asyncio.run(_go())
    assert out['mocked'] is True
    assert out['provider'] == 'facebook_messenger'
    assert out['recipient_psid'] == 'psid1'


def test_send_messenger_message_live_without_token_raises():
    from app.services.meta_messenger import send_messenger_message

    async def _go():
        return await send_messenger_message(
            'facebook_messenger',
            recipient_account_id='page1', recipient_psid='psid1',
            text='hi', delivery_mode='live',
            token_ref='secrets/nonexistent',
        )

    with pytest.raises(RuntimeError, match='Meta access token'):
        asyncio.run(_go())


# ───────── serialize_event_for_storage ───────────────────────────────────


def test_serialize_event_for_storage_returns_json_string():
    from app.services.meta_messenger import (
        NormalizedMessengerEvent,
        serialize_event_for_storage,
    )
    event = NormalizedMessengerEvent(
        provider='facebook_messenger',
        recipient_id='p',
        sender_id='u',
        external_message_id='m1',
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        message_type='text',
        body_text='Hola',
        media_id=None,
        mime_type=None,
        raw={'foo': 'bar'},
        reply_to_external_id=None,
    )
    out = serialize_event_for_storage(event)
    parsed = json.loads(out)
    assert parsed['body_text'] == 'Hola'
    assert parsed['provider'] == 'facebook_messenger'
    assert parsed['timestamp'].startswith('2026-01-01')


def test_serialize_event_for_storage_with_null_timestamp():
    from app.services.meta_messenger import (
        NormalizedMessengerEvent,
        serialize_event_for_storage,
    )
    event = NormalizedMessengerEvent(
        provider='instagram_messenger', recipient_id='r', sender_id='s',
        external_message_id='m', timestamp=None, message_type='text',
        body_text=None, media_id=None, mime_type=None,
        raw={}, reply_to_external_id=None,
    )
    parsed = json.loads(serialize_event_for_storage(event))
    assert parsed['timestamp'] is None
