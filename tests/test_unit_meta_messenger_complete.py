"""Completeness tests for meta_messenger — covers payload-shape skips
(non-dict entry/event/message), timestamp parse failure, send_messenger_message
live path, and is_within_service_window with naive `now`.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest


# ── Lines 118, 121: recipient_id_from_payload skip non-dict entries/events


def test_recipient_id_skips_non_dict_entry_and_messaging():
    from app.services.meta_messenger import recipient_id_from_payload

    # entry list contains a string (non-dict) → continue
    # entry's messaging contains a list element that's not a dict
    payload = {
        'object': 'page',
        'entry': [
            'garbage',
            {'id': 'page-1', 'messaging': ['not-a-dict-event']},
        ],
    }
    assert recipient_id_from_payload('facebook_messenger', payload) == 'page-1'


# ── Lines 141-142: _parse_timestamp OverflowError/OSError ──────────────────


def test_parse_timestamp_overflow_returns_none():
    """Passing an extreme integer triggers OverflowError/ValueError in
    datetime.fromtimestamp — covers the except branch."""
    from app.services.meta_messenger import _parse_timestamp
    # 10**20 ms → far beyond the datetime range; raises OverflowError or
    # ValueError depending on platform.
    assert _parse_timestamp(10**25) is None
    # Negative extreme also triggers the branch on some platforms
    assert _parse_timestamp(-(10**25)) is None


def test_parse_timestamp_non_numeric():
    from app.services.meta_messenger import _parse_timestamp
    assert _parse_timestamp('not-a-number') is None
    assert _parse_timestamp(None) is None


# ── Line 158: _normalize_attachment when attachments[0] is not a dict ──────


def test_normalize_attachment_non_dict_first_element():
    from app.services.meta_messenger import _normalize_attachment
    # Empty / not a list / first element is not a dict → returns text fallback
    assert _normalize_attachment(['string']) == ('text', None, None)
    assert _normalize_attachment([]) == ('text', None, None)
    assert _normalize_attachment(None) == ('text', None, None)


# ── Lines 185, 188, 191, 202: normalize_messenger_events skips ─────────────


def test_normalize_events_skips_non_dict_pieces():
    from app.services.meta_messenger import normalize_messenger_events

    payload = {
        'object': 'page',
        'entry': [
            'not-a-dict',  # line 185
            {
                'id': 'page-1',
                'messaging': [
                    'not-a-dict',  # line 188
                    {'message': 'not-a-dict'},  # line 191 — message not dict
                    {  # line 202: mid not str
                        'sender': {'id': 's'},
                        'recipient': {'id': 'r'},
                        'message': {'mid': None, 'text': 'hi'},
                    },
                ],
            },
        ],
    }
    out = normalize_messenger_events('facebook_messenger', payload)
    assert out == []


def test_normalize_events_skips_unsupported_provider():
    from app.services.meta_messenger import normalize_messenger_events
    assert normalize_messenger_events('whatsapp', {}) == []


# ── Line 245: is_within_service_window with naive `now` ────────────────────


def test_service_window_with_naive_now_is_normalized():
    from app.services.meta_messenger import is_within_service_window
    # last_inbound: aware in UTC ; now: naive (no tzinfo) → coerced to UTC
    inbound = datetime.now(timezone.utc) - timedelta(hours=2)
    now_naive = datetime.utcnow()
    assert is_within_service_window(inbound, now=now_naive) is True


# ── Lines 340-343, 348-349: send_messenger_message live happy path ─────────


def test_send_messenger_message_live_calls_graph(monkeypatch):
    """Cover the live-delivery branch by stubbing resolve_secret_ref and
    httpx.AsyncClient so we don't perform a real network call."""
    from app.services import meta_messenger as mm

    monkeypatch.setattr(mm, 'resolve_secret_ref',
                        lambda ref: 'EAA' + ('x' * 60))
    monkeypatch.setattr(mm, 'meta_token_is_configured', lambda tok: True)

    captured = {}

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {'message_id': 'mid_abc', 'recipient_id': 'psid_1'}

    class _FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            captured['url'] = url
            captured['headers'] = headers
            captured['json'] = json
            return _FakeResponse()

    monkeypatch.setattr(mm.httpx, 'AsyncClient', _FakeAsyncClient)

    async def runner():
        return await mm.send_messenger_message(
            'facebook_messenger',
            'page_42',
            'psid_1',
            text='hello',
            delivery_mode='live',
            token_ref='secret://meta_token',
        )

    out = asyncio.run(runner())
    assert out == {'message_id': 'mid_abc', 'recipient_id': 'psid_1'}
    assert 'page_42/messages' in captured['url']
    assert captured['headers']['Authorization'].startswith('Bearer EAA')


def test_send_messenger_message_live_rejects_missing_token(monkeypatch):
    from app.services import meta_messenger as mm

    monkeypatch.setattr(mm, 'resolve_secret_ref', lambda ref: None)
    monkeypatch.setattr(mm, 'meta_token_is_configured', lambda tok: False)

    async def runner():
        with pytest.raises(RuntimeError, match='live'):
            await mm.send_messenger_message(
                'instagram_messenger', 'ig_1', 'psid_1',
                text='hi', delivery_mode='live', token_ref='secret://x',
            )

    asyncio.run(runner())
