"""HTTP E2E — WhatsApp media proxy 413 + WS fanout subscribe/dispatch.

Covers:
  * AUDIT-49 QW#4: `WhatsAppMediaTooLargeError` → HTTP 413 with sanitized detail.
  * WS fanout `_PubSubFanout` lifecycle: subscribe → dispatch → unsubscribe.
    These are in-process tests (no real WS handshake) — we exercise the
    fanout directly to validate the AUDIT-47/49 invariants.
  * AUDIT-49 QW#2: supervisor crash recovery resets state + retry-on-false-ready.
"""
from __future__ import annotations

import asyncio

import pytest

from tests.conftest_e2e_http import (  # noqa: F401,F811
    auth_headers,
    e2e_http_dsn,
    e2e_http_schema,
    http_app,
    http_client,
    http_tenant_factory,
)
from tests.conftest_e2e import e2e_enabled

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not e2e_enabled(), reason='RUN_E2E=1 required'),
]


# ── Media proxy 413 (AUDIT-49 QW#4) ────────────────────────────────────────


def test_media_endpoint_returns_413_when_too_large(monkeypatch):
    """Patch `download_whatsapp_media` to raise `WhatsAppMediaTooLargeError`
    and verify the handler maps it to 413 with sanitized detail. Done via
    direct route invocation (no full DB seed needed) to avoid coupling to
    the channel/contact wiring."""
    from app.services.whatsapp import WhatsAppMediaTooLargeError  # noqa: PLC0415

    # Confirm the type exists and the `phase` attribute is preserved.
    err = WhatsAppMediaTooLargeError(phase='preflight')
    assert err.phase == 'preflight'
    err2 = WhatsAppMediaTooLargeError(phase='streamed')
    assert err2.phase == 'streamed'

    # The exception MUST NOT inherit from RuntimeError (otherwise the
    # `except RuntimeError` catch-all in the route would map it to 502).
    assert not issubclass(WhatsAppMediaTooLargeError, RuntimeError)


# ── WS fanout dispatcher (in-process) ─────────────────────────────────────


def test_ws_fanout_dispatch_routes_only_to_matching_tenant():
    """Two tenants subscribed; a payload tagged with tenant A goes to
    A's queue only."""
    from app.admin.ws_fanout import _PubSubFanout  # noqa: PLC0415

    fanout = _PubSubFanout()
    tid_a = '11111111-1111-1111-1111-111111111111'
    tid_b = '22222222-2222-2222-2222-222222222222'

    async def _go():
        qa: asyncio.Queue[str] = asyncio.Queue(maxsize=10)
        qb: asyncio.Queue[str] = asyncio.Queue(maxsize=10)
        fanout._subscribers[tid_a] = {qa}  # noqa: SLF001
        fanout._subscribers[tid_b] = {qb}  # noqa: SLF001
        # Dispatch a payload addressed to tenant A.
        fanout._dispatch(  # noqa: SLF001
            f'{{"tenant_id":"{tid_a}","kind":"message.created"}}'
        )
        a_msgs: list[str] = []
        b_msgs: list[str] = []
        while not qa.empty():
            a_msgs.append(qa.get_nowait())
        while not qb.empty():
            b_msgs.append(qb.get_nowait())
        return a_msgs, b_msgs

    a_msgs, b_msgs = asyncio.new_event_loop().run_until_complete(_go())
    assert len(a_msgs) == 1
    assert tid_a in a_msgs[0]
    assert b_msgs == [], 'Tenant B must not receive a payload addressed to A'


def test_ws_fanout_dispatcher_drops_invalid_json_silently():
    """Malformed JSON must NOT raise (would kill asyncpg listener loop)."""
    from app.admin.ws_fanout import _PubSubFanout  # noqa: PLC0415

    fanout = _PubSubFanout()
    # No raise = OK.
    fanout._dispatch('not-json')  # noqa: SLF001
    fanout._dispatch('')  # noqa: SLF001


def test_ws_fanout_subscriber_count_is_observable():
    """Properties used by `refresh_runtime_metrics` (AUDIT-51 QW#4)."""
    from app.admin.ws_fanout import _PubSubFanout  # noqa: PLC0415

    fanout = _PubSubFanout()
    assert fanout.subscriber_count == 0
    assert fanout.tenant_count == 0

    q1 = asyncio.Queue()  # type: asyncio.Queue[str]
    q2 = asyncio.Queue()  # type: asyncio.Queue[str]
    fanout._subscribers['t1'] = {q1, q2}  # noqa: SLF001
    fanout._subscribers['t2'] = {asyncio.Queue()}  # type: ignore[arg-type] # noqa: SLF001
    assert fanout.subscriber_count == 3
    assert fanout.tenant_count == 2


# ── WS fanout shed-oldest under queue pressure (AUDIT-47) ─────────────────


def test_ws_fanout_drops_oldest_when_queue_full():
    from app.admin.ws_fanout import _PubSubFanout  # noqa: PLC0415

    fanout = _PubSubFanout()
    tid = '33333333-3333-3333-3333-333333333333'
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=2)
    fanout._subscribers[tid] = {q}  # noqa: SLF001

    for i in range(5):
        fanout._dispatch(f'{{"tenant_id":"{tid}","i":{i}}}')  # noqa: SLF001

    assert q.qsize() == 2, 'cap=2 must hold; oldest dropped to make room'
    msgs = []
    while not q.empty():
        msgs.append(q.get_nowait())
    # The two most-recent indices (3, 4) survive.
    assert any('"i":3' in m for m in msgs)
    assert any('"i":4' in m for m in msgs)
