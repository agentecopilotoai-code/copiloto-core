"""AUDIT-47 — Static regression tests for BUG-49 (WhatsApp media streaming
with size cap) and BUG-50 (WebSocket LISTEN/NOTIFY fanout that no longer
holds a pool conn per socket).

All tests are static (no DB, no network).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


# ───────────── BUG-49 — Stream WhatsApp media with size cap ────────────────


def test_download_whatsapp_media_uses_stream_not_buffer_all():
    src = (REPO_ROOT / 'app' / 'services' / 'whatsapp.py').read_text()
    block_start = src.index('async def download_whatsapp_media(')
    # We restrict the assertion window to the function body to avoid matching
    # other download paths in the same file.
    block = src[block_start:block_start + 5000]

    # No more raw `return response.content,` (the original buffer-all path).
    # We allow the literal in comments — only the executable form is forbidden.
    code_only = '\n'.join(
        line for line in block.splitlines()
        if not line.lstrip().startswith('#')
    )
    assert 'return response.content,' not in code_only, (
        'download_whatsapp_media must NOT return response.content directly '
        '(buffer-all); it must stream and enforce knowledge_file_max_bytes.'
    )
    # Streaming primitives in place.
    assert 'client.stream(' in code_only
    assert 'aiter_bytes()' in code_only
    # Size cap referencing the shared knowledge cap (10 MB).
    assert 'knowledge_file_max_bytes' in code_only
    # Both the optimistic Content-Length pre-check and the bytes-read guard
    # raise the typed exception so the route can map them to HTTP 413
    # (AUDIT-49 / re-audit §1.5; the original AUDIT-47 used RuntimeError
    # which the caller mapped to 502 — that has been replaced by a typed
    # `WhatsAppMediaTooLargeError` with `phase` discriminator).
    assert code_only.count('WhatsAppMediaTooLargeError(phase=') == 2


def test_download_whatsapp_media_still_validates_url_guard():
    """The streaming refactor must preserve the URL allowlist + redirect
    block from BUG19 / SEC-009 — without these, the bearer leaks."""
    src = (REPO_ROOT / 'app' / 'services' / 'whatsapp.py').read_text()
    block_start = src.index('async def download_whatsapp_media(')
    block = src[block_start:block_start + 5000]
    assert 'validate_outbound_url' in block
    assert 'META_MEDIA_HOST_ALLOWLIST' in block
    assert 'follow_redirects=False' in block


# ───────────── BUG-50 — WebSocket fanout (no pool conn per socket) ─────────


def test_ws_endpoint_no_longer_acquires_pool_per_socket():
    src = (REPO_ROOT / 'app' / 'admin' / 'routes.py').read_text()
    ws_start = src.index('admin_conversations_stream')
    # The full function lives in <2000 chars
    ws_block = src[ws_start:ws_start + 4000]
    # Critical regression guard: the per-socket pool acquire is gone.
    assert 'async with db.pool.acquire() as conn:' not in ws_block, (
        'WS endpoint must NOT acquire a pool conn per socket '
        '(BUG-50, pool exhaustion DoS). Use ws_fanout.subscribe instead.'
    )
    # And: the new fanout call sites ARE present.
    assert 'ws_fanout.subscribe(db.pool, tenant_id)' in ws_block
    assert 'ws_fanout.unsubscribe(tenant_id, queue)' in ws_block


def test_ws_fanout_module_exists_and_exposes_singleton():
    src = (REPO_ROOT / 'app' / 'admin' / 'ws_fanout.py').read_text()
    assert 'class _PubSubFanout' in src
    assert 'fanout = _PubSubFanout()' in src
    # Both async APIs the route calls must exist.
    assert 'async def subscribe(' in src
    assert 'async def unsubscribe(' in src


def test_ws_fanout_dispatch_routes_to_matching_subscribers():
    """Smoke: dispatch a JSON payload and verify only the matching tenant
    queue receives it."""
    from uuid import UUID

    from app.admin.ws_fanout import _PubSubFanout

    tenant_a = UUID('11111111-1111-1111-1111-111111111111')
    tenant_b = UUID('22222222-2222-2222-2222-222222222222')

    async def _go():
        fanout = _PubSubFanout()
        qa: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        qb: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
        fanout._subscribers[str(tenant_a)] = {qa}
        fanout._subscribers[str(tenant_b)] = {qb}

        payload_for_a = '{"tenant_id":"11111111-1111-1111-1111-111111111111","x":1}'
        payload_for_b = '{"tenant_id":"22222222-2222-2222-2222-222222222222","x":2}'

        fanout._dispatch(payload_for_a)
        fanout._dispatch(payload_for_b)

        got_a, got_b = [], []
        while not qa.empty():
            got_a.append(qa.get_nowait())
        while not qb.empty():
            got_b.append(qb.get_nowait())
        return got_a, got_b, payload_for_a, payload_for_b

    got_a, got_b, payload_for_a, payload_for_b = asyncio.new_event_loop().run_until_complete(_go())
    assert got_a == [payload_for_a]
    assert got_b == [payload_for_b]


def test_ws_fanout_drops_invalid_json_silently():
    from app.admin.ws_fanout import _PubSubFanout

    fanout = _PubSubFanout()
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
    fanout._subscribers['11111111-1111-1111-1111-111111111111'] = {q}
    # Malformed payload must NOT raise (would kill asyncpg listener loop)
    fanout._dispatch('not json')
    fanout._dispatch('')
    assert q.empty(), 'Invalid payloads must be silently dropped, not dispatched.'


def test_ws_fanout_shed_oldest_when_queue_full():
    """Slow subscribers must NOT block the fanout; oldest message gets dropped."""
    from app.admin.ws_fanout import _PubSubFanout

    fanout = _PubSubFanout()
    q: asyncio.Queue[str] = asyncio.Queue(maxsize=2)
    fanout._subscribers['11111111-1111-1111-1111-111111111111'] = {q}

    for i in range(5):
        fanout._dispatch(
            '{"tenant_id":"11111111-1111-1111-1111-111111111111","i":' + str(i) + '}'
        )

    # Queue holds at most 2; oldest are dropped.
    assert q.qsize() == 2
    drained = []
    while not q.empty():
        drained.append(q.get_nowait())
    # The two most recent indexes (3, 4) survive
    assert any('"i":3' in p for p in drained), f'expected i=3 in {drained}'
    assert any('"i":4' in p for p in drained), f'expected i=4 in {drained}'
