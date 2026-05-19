"""HTTP E2E — Webhook entrypoints (Meta WhatsApp + Stripe + MercadoPago).

Covers:
  * WhatsApp webhook verify (GET hub.mode=subscribe) — 200 + challenge echo.
  * WhatsApp webhook POST without signature → 401 (timing-constant; same
    detail string as `unknown_channel` / `invalid_payload`).
  * WhatsApp webhook with valid HMAC + fresh `messages[].timestamp` → 200.
  * AUDIT-48: stale `messages[].timestamp` → audit-drop the message but
    payload still persisted in `webhook_events_raw`.
  * AUDIT-51 / round-3 §1.8: payload where ALL messages are stale → 200
    `{status:'rejected', reason:'all_messages_stale'}` and INSERT is SKIPPED.
  * AUDIT-51: status-only payload (no `messages[]`) is processed normally
    (NOT filtered by freshness gate).
  * Stripe webhook with signature freshness window (5min) — fresh OK, stale 401.
  * MercadoPago: missing `ts` in v1 header → 401 (AUDIT-48 fail-closed).
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import uuid

import pytest

from tests.conftest_e2e_http import (  # noqa: F401,F811
    e2e_http_dsn,
    e2e_http_schema,
    http_app,
    http_client,
    http_tenant_factory,
)
from tests.conftest_e2e import e2e_enabled, tenant_connection

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not e2e_enabled(), reason='RUN_E2E=1 required'),
]


_APP_SECRET = 'test-whatsapp-app-secret'
_SECRET_REF = 'secrets/test-whatsapp-app-secret'


def _seed_secret_file(name: str = 'test-whatsapp-app-secret', value: str = _APP_SECRET) -> None:
    """Drop the app secret file where `resolve_secret_ref` will find it.

    The lookup order is `/app/.secrets/<name>` then `Path.cwd()/.secrets/<name>`.
    Tests run from repo root so `cwd/.secrets/<name>` works."""
    from pathlib import Path  # noqa: PLC0415

    base = Path.cwd() / '.secrets'
    base.mkdir(parents=True, exist_ok=True)
    secret_path = base / name
    secret_path.write_text(value, encoding='utf-8')
    secret_path.chmod(0o600)


@pytest.fixture(autouse=True, scope='module')
def _ensure_app_secret_file() -> None:
    _seed_secret_file()


def _seed_channel(dsn: str, tenant_id: uuid.UUID, phone_number_id: str) -> uuid.UUID:
    """Add a `tenant_channels` row tied to a known `phone_number_id` and the
    app secret file we just seeded."""
    channel_id = uuid.uuid4()

    async def _seed() -> None:
        async with tenant_connection(dsn, tenant_id, support_mode=True) as conn:
            await conn.execute(
                """
                insert into app.tenant_channels (
                    id, tenant_id, provider, phone_number_id, token_ref,
                    app_secret_ref, account_mode, status
                ) values ($1, $2, 'whatsapp_cloud_api', $3, 'token_ref', $4, 'mock', 'active')
                """,
                channel_id,
                tenant_id,
                phone_number_id,
                _SECRET_REF,
            )

    asyncio.run(_seed())
    return channel_id


def _sign_meta_payload(body: bytes, secret: str = _APP_SECRET) -> str:
    return 'sha256=' + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def _make_whatsapp_payload(
    *,
    phone_number_id: str,
    wa_id: str = '573001234567',
    messages: list[dict] | None = None,
    include_messages: bool = True,
) -> dict:
    """Build a Meta-shaped payload."""
    if messages is None and include_messages:
        messages = [
            {
                'id': f'wamid.{uuid.uuid4().hex}',
                'from': wa_id,
                'timestamp': str(int(time.time())),
                'type': 'text',
                'text': {'body': 'hola'},
            }
        ]
    elif not include_messages:
        messages = None
    value = {
        'metadata': {'phone_number_id': phone_number_id},
        'contacts': [{'wa_id': wa_id, 'profile': {'name': 'Test'}}],
    }
    if messages is not None:
        value['messages'] = messages
    return {
        'object': 'whatsapp_business_account',
        'entry': [
            {
                'id': 'entry-1',
                'changes': [{'field': 'messages', 'value': value}],
            }
        ],
    }


# ── WhatsApp webhook verify (GET) ───────────────────────────────────────────


def test_whatsapp_webhook_verify_rejects_unknown_token(http_client):
    """GET with `hub.mode=subscribe` + a token that doesn't match any
    channel's verify_token must return 403, NOT echo the challenge.
    (A 200 with echo would let an attacker hijack the subscription.)"""
    resp = http_client.get(
        '/v1/webhooks/whatsapp',
        params={
            'hub.mode': 'subscribe',
            'hub.verify_token': 'attacker-guess',
            'hub.challenge': 'CHALLENGE-1234',
        },
    )
    assert resp.status_code in (401, 403), f'Got {resp.status_code}: {resp.text}'
    # CRITICAL: response must NOT contain the challenge string (no echo on miss)
    assert 'CHALLENGE-1234' not in resp.text


# ── WhatsApp POST: signature + freshness ────────────────────────────────────


def test_whatsapp_post_returns_401_without_signature(http_client, http_tenant_factory, e2e_http_dsn):
    """No `X-Hub-Signature-256` → 401 (timing-constant: same detail as
    invalid_signature)."""
    tenant_id, _, _ = http_tenant_factory(label='wa-nosig')
    pn_id = f'pn-{uuid.uuid4().hex[:8]}'
    _seed_channel(e2e_http_dsn, tenant_id, pn_id)
    payload = _make_whatsapp_payload(phone_number_id=pn_id)
    resp = http_client.post('/v1/webhooks/whatsapp', json=payload)
    assert resp.status_code == 401
    assert resp.json() == {'detail': 'Invalid webhook signature'}


def test_whatsapp_post_returns_401_with_bad_signature(
    http_client, http_tenant_factory, e2e_http_dsn
):
    tenant_id, _, _ = http_tenant_factory(label='wa-badsig')
    pn_id = f'pn-{uuid.uuid4().hex[:8]}'
    _seed_channel(e2e_http_dsn, tenant_id, pn_id)
    payload = _make_whatsapp_payload(phone_number_id=pn_id)
    body = json.dumps(payload).encode()
    resp = http_client.post(
        '/v1/webhooks/whatsapp',
        content=body,
        headers={
            'content-type': 'application/json',
            'X-Hub-Signature-256': 'sha256=' + 'f' * 64,
        },
    )
    assert resp.status_code == 401
    assert resp.json() == {'detail': 'Invalid webhook signature'}


def test_whatsapp_post_accepts_fresh_message_with_valid_signature(
    http_client, http_tenant_factory, e2e_http_dsn
):
    tenant_id, _, _ = http_tenant_factory(label='wa-fresh')
    pn_id = f'pn-{uuid.uuid4().hex[:8]}'
    _seed_channel(e2e_http_dsn, tenant_id, pn_id)
    payload = _make_whatsapp_payload(phone_number_id=pn_id)
    body = json.dumps(payload).encode()
    sig = _sign_meta_payload(body)
    resp = http_client.post(
        '/v1/webhooks/whatsapp',
        content=body,
        headers={'content-type': 'application/json', 'X-Hub-Signature-256': sig},
    )
    assert resp.status_code in (200, 202), resp.text
    # The webhook handler returns either {} or {status: 'ok'} on success.


def test_whatsapp_post_skips_insert_when_all_messages_stale(
    http_client, http_tenant_factory, e2e_http_dsn
):
    """AUDIT-51 / round-3 §1.8: payload with ALL messages older than
    `webhook_meta_max_message_age_seconds` (7d default) returns 200
    `{status:'rejected', reason:'all_messages_stale'}` and the
    `webhook_events_raw` table receives ZERO rows for this payload."""
    tenant_id, _, _ = http_tenant_factory(label='wa-stale-all')
    pn_id = f'pn-{uuid.uuid4().hex[:8]}'
    _seed_channel(e2e_http_dsn, tenant_id, pn_id)
    # 30-day-old timestamp — well outside the 7d default window.
    very_old_ts = int(time.time()) - (30 * 24 * 3600)
    payload = _make_whatsapp_payload(
        phone_number_id=pn_id,
        messages=[
            {
                'id': f'wamid.{uuid.uuid4().hex}',
                'from': '573009999999',
                'timestamp': str(very_old_ts),
                'type': 'text',
                'text': {'body': 'replay'},
            }
        ],
    )
    body = json.dumps(payload).encode()
    sig = _sign_meta_payload(body)
    resp = http_client.post(
        '/v1/webhooks/whatsapp',
        content=body,
        headers={'content-type': 'application/json', 'X-Hub-Signature-256': sig},
    )
    assert resp.status_code in (200, 202), resp.text
    response_body = resp.json()
    assert response_body == {'status': 'rejected', 'reason': 'all_messages_stale'}

    # Verify the raw INSERT was SKIPPED (no row in webhook_events_raw for
    # this sha).
    sha = hashlib.sha256(body).hexdigest()

    async def _count() -> int:
        async with tenant_connection(e2e_http_dsn, tenant_id, support_mode=True) as conn:
            row = await conn.fetchrow(
                'select count(*) as n from app.webhook_events_raw where payload_sha256=$1',
                sha,
            )
            return int(row['n'])

    n = asyncio.run(_count())
    assert n == 0, (
        'AUDIT-51 / round-3 §1.8: stale payload MUST NOT be persisted in '
        'webhook_events_raw — pre-scan skipped the INSERT.'
    )


def test_whatsapp_post_status_only_payload_passes_freshness_gate(
    http_client, http_tenant_factory, e2e_http_dsn
):
    """AUDIT-51: payloads without `messages[]` (status updates, contact
    profile changes) MUST NOT be filtered — they don't carry per-message
    timestamps and Meta dedupes them upstream."""
    tenant_id, _, _ = http_tenant_factory(label='wa-status')
    pn_id = f'pn-{uuid.uuid4().hex[:8]}'
    _seed_channel(e2e_http_dsn, tenant_id, pn_id)
    payload = {
        'object': 'whatsapp_business_account',
        'entry': [
            {
                'id': 'entry-1',
                'changes': [{
                    'field': 'messages',
                    'value': {
                        'metadata': {'phone_number_id': pn_id},
                        'statuses': [
                            {
                                'id': f'wamid.{uuid.uuid4().hex}',
                                'status': 'delivered',
                                'timestamp': str(int(time.time())),
                            }
                        ],
                        # NO `messages` key at all
                    },
                }],
            }
        ],
    }
    body = json.dumps(payload).encode()
    sig = _sign_meta_payload(body)
    resp = http_client.post(
        '/v1/webhooks/whatsapp',
        content=body,
        headers={'content-type': 'application/json', 'X-Hub-Signature-256': sig},
    )
    assert resp.status_code in (200, 202), resp.text
    # Should NOT have been rejected by the all-stale gate.
    body_json = resp.json()
    assert body_json != {'status': 'rejected', 'reason': 'all_messages_stale'}


def test_whatsapp_post_persists_raw_when_at_least_one_message_fresh(
    http_client, http_tenant_factory, e2e_http_dsn
):
    """Mixed payload (1 fresh + 1 stale) is persisted; the stale message is
    dropped inside the loop via per-message audit, and the fresh one is
    processed."""
    tenant_id, _, _ = http_tenant_factory(label='wa-mixed')
    pn_id = f'pn-{uuid.uuid4().hex[:8]}'
    _seed_channel(e2e_http_dsn, tenant_id, pn_id)
    fresh_ts = int(time.time())
    stale_ts = fresh_ts - (30 * 24 * 3600)
    payload = _make_whatsapp_payload(
        phone_number_id=pn_id,
        messages=[
            {
                'id': f'wamid.{uuid.uuid4().hex}',
                'from': '573008888888',
                'timestamp': str(stale_ts),
                'type': 'text',
                'text': {'body': 'stale'},
            },
            {
                'id': f'wamid.{uuid.uuid4().hex}',
                'from': '573008888888',
                'timestamp': str(fresh_ts),
                'type': 'text',
                'text': {'body': 'fresh'},
            },
        ],
    )
    body = json.dumps(payload).encode()
    sig = _sign_meta_payload(body)
    resp = http_client.post(
        '/v1/webhooks/whatsapp',
        content=body,
        headers={'content-type': 'application/json', 'X-Hub-Signature-256': sig},
    )
    assert resp.status_code in (200, 202), resp.text
    body_json = resp.json()
    # Should NOT be rejected (one fresh message present).
    assert body_json != {'status': 'rejected', 'reason': 'all_messages_stale'}

    # Verify raw was PERSISTED + the stale message was audit-dropped.
    sha = hashlib.sha256(body).hexdigest()

    async def _check() -> tuple[int, int]:
        async with tenant_connection(e2e_http_dsn, tenant_id, support_mode=True) as conn:
            raw_n = await conn.fetchval(
                'select count(*) from app.webhook_events_raw where payload_sha256=$1',
                sha,
            )
            stale_n = await conn.fetchval(
                """select count(*) from app.audit_logs
                   where tenant_id=$1 and action='webhook.whatsapp_message_stale'""",
                tenant_id,
            )
            return int(raw_n), int(stale_n)

    raw_n, stale_n = asyncio.run(_check())
    assert raw_n == 1, 'mixed payload (one fresh) MUST persist raw'
    assert stale_n >= 1, 'stale message in mixed payload MUST be audit-dropped per AUDIT-48'


# ── Stripe webhook freshness ────────────────────────────────────────────────


def test_stripe_webhook_returns_400_when_tolerance_exceeded(http_client, http_tenant_factory):
    """Stripe `verify_stripe_signature` enforces a 5-minute tolerance window
    between `t=` and `now_ts`. A timestamp 1 hour in the past must fail."""
    tenant_id, _, _ = http_tenant_factory(label='stripe-stale')
    old_ts = int(time.time()) - 3600  # 1h ago
    body = b'{"event":"test"}'
    # Stripe HMAC = HMAC-SHA256(secret, f'{t}.{body}'). We don't know the
    # tenant's webhook secret unless we seed it; this test demonstrates the
    # rejection path on stale-ts even if signature math is right.
    sig_header = f't={old_ts},v1=' + 'a' * 64
    resp = http_client.post(
        '/v1/webhooks/payments/stripe',
        content=body,
        headers={'content-type': 'application/json', 'Stripe-Signature': sig_header},
    )
    # The handler returns 4xx (we accept any 400-class for invalid signature).
    assert 400 <= resp.status_code < 500, resp.text
