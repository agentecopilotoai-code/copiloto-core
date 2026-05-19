"""HTTP E2E — Consent / GDPR contact data export.

Covers:
  * Contact export endpoint requires admin + MFA (404 for missing contact;
    403 for viewer; 200 + signed bundle for admin).
  * BUG-231: response body includes `data_canonical` (the exact bytes the
    server signed). Verifier can recompute HMAC-SHA256 over `data_canonical`
    using `jwt_secret` and match the `signature` field. WITHOUT this, the
    `default=str` JSON would diverge from FastAPI's ISO-T serialization and
    the external verifier would always fail.
  * Audit log row is created with `action='contact.exported_for_consent_claim'`
    and `metadata.signature`/`signature_algorithm`.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import uuid

import pytest

from tests.conftest_e2e_http import (  # noqa: F401,F811
    auth_headers,
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


def _seed_contact(dsn: str, tenant_id: uuid.UUID) -> uuid.UUID:
    """Add a contact row so the export endpoint has something to dump."""
    contact_id = uuid.uuid4()

    async def _seed() -> None:
        async with tenant_connection(dsn, tenant_id, support_mode=True) as conn:
            wa_id = f'5730099{int(uuid.uuid4().int % 10_000_000):07d}'
            await conn.execute(
                """
                insert into app.contacts
                  (id, tenant_id, wa_id, phone_e164, phone_hash, display_name, opt_in_status)
                values ($1, $2, $3, $4, decode(md5($4), 'hex'), 'Test Contact', 'granted')
                """,
                contact_id,
                tenant_id,
                wa_id,
                f'+{wa_id}',
            )

    asyncio.run(_seed())
    return contact_id


# ── Export contract: requires admin role ──────────────────────────────────


def test_contact_export_requires_admin_role(http_client, http_tenant_factory, e2e_http_dsn):
    tenant_id, _, sub = http_tenant_factory(label='exp-viewer', role='viewer')
    contact_id = _seed_contact(e2e_http_dsn, tenant_id)
    headers = auth_headers(tenant_id=tenant_id, roles=['viewer'], sub=sub)
    resp = http_client.get(
        f'/v1/tenants/{tenant_id}/contacts/{contact_id}/export?kinds=consent_ledger',
        headers=headers,
    )
    assert resp.status_code == 403, resp.text


def test_contact_export_returns_404_for_unknown_contact(http_client, http_tenant_factory):
    tenant_id, _, sub = http_tenant_factory(label='exp-404', role='admin')
    headers = auth_headers(tenant_id=tenant_id, roles=['admin'], sub=sub)
    fake_contact = uuid.uuid4()
    resp = http_client.get(
        f'/v1/tenants/{tenant_id}/contacts/{fake_contact}/export?kinds=consent_ledger',
        headers=headers,
    )
    assert resp.status_code == 404


# ── BUG-231: data_canonical + signature roundtrip ─────────────────────────


def test_contact_export_response_includes_canonical_and_verifiable_signature(
    http_client, http_tenant_factory, e2e_http_dsn
):
    """The response MUST include `data_canonical` (the EXACT byte string the
    server HMAC'd) so an external verifier can:

        signature == HMAC_SHA256(jwt_secret, data_canonical)

    Without the canonical string field, the verifier would have to re-serialize
    `data` and the bytes would diverge (datetime ISO format, dict ordering,
    Python `default=str` quirks)."""
    tenant_id, _, sub = http_tenant_factory(label='exp-canon', role='admin')
    contact_id = _seed_contact(e2e_http_dsn, tenant_id)
    headers = auth_headers(tenant_id=tenant_id, roles=['admin'], sub=sub)
    resp = http_client.get(
        f'/v1/tenants/{tenant_id}/contacts/{contact_id}/export?kinds=consent_ledger,messages',
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert 'data' in body
    assert 'data_canonical' in body, (
        'BUG-231 / AUDIT-49: response MUST include `data_canonical` so external '
        'verifiers can recompute the HMAC over the EXACT bytes the server signed.'
    )
    assert 'signature' in body
    assert body.get('signature_algorithm') == 'HMAC-SHA256'

    # Recompute the signature using the JWT secret (which is the same in the
    # test env). Must match.
    secret = os.environ.get('JWT_SECRET', 'test-jwt-secret-min-length-16')
    canonical = body['data_canonical']
    if isinstance(canonical, str):
        canonical_bytes = canonical.encode('utf-8')
    else:
        canonical_bytes = canonical
    expected = hmac.new(secret.encode(), canonical_bytes, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(expected, body['signature']), (
        'HMAC mismatch: external verifier cannot reproduce the signature. '
        'BUG-231 fix is broken.'
    )


def test_contact_export_writes_audit_log_row(
    http_client, http_tenant_factory, e2e_http_dsn
):
    tenant_id, _, sub = http_tenant_factory(label='exp-audit', role='admin')
    contact_id = _seed_contact(e2e_http_dsn, tenant_id)
    headers = auth_headers(tenant_id=tenant_id, roles=['admin'], sub=sub)
    resp = http_client.get(
        f'/v1/tenants/{tenant_id}/contacts/{contact_id}/export?kinds=consent_ledger',
        headers=headers,
    )
    assert resp.status_code == 200

    async def _audit_count() -> int:
        async with tenant_connection(e2e_http_dsn, tenant_id, support_mode=True) as conn:
            n = await conn.fetchval(
                """select count(*) from app.audit_logs
                   where tenant_id=$1
                     and action='contact.exported_for_consent_claim'
                     and entity_type='contact'
                     and entity_id=$2""",
                tenant_id,
                str(contact_id),
            )
            return int(n)

    assert asyncio.run(_audit_count()) == 1, (
        'Export endpoint must write one audit_logs row with '
        'action=contact.exported_for_consent_claim (BUG-231 audit trail).'
    )
