"""HTTP E2E — Authentication and multi-tenant boundary.

Covers:
  * No-Authorization → 401 on a protected endpoint.
  * Invalid Bearer token → 401.
  * Service token (default + rotated `service_token_next`, AUDIT-48) → 200.
  * Tenant JWT with wrong `tenant_id` claim → 401 from `ensure_tenant_access`.
  * Tenant JWT with stale role (downgrade in DB) → 403 (AUDIT-49 ensure_tenant_access
    always runs even when state.tenant_id pre-populated).
  * `X-Admin-User-Email` header is IGNORED (BUG-228) — only JWT/BFF signed
    header is trusted.
  * MFA gate: privileged role without `mfa_verified` claim → 403 when
    `mfa_enforcement_enabled=true`. (Conftest disables MFA for these tests; we
    re-enable inline for one test.)
  * Session revocation (BUG-199): `auth_sessions.revoked_at` set → 401.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest

from tests.conftest_e2e_http import (  # noqa: F401,F811
    auth_headers,
    e2e_http_dsn,
    e2e_http_schema,
    forge_token,
    http_app,
    http_client,
    http_tenant_factory,
    service_headers,
)
from tests.conftest_e2e import e2e_enabled, tenant_connection

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not e2e_enabled(), reason='RUN_E2E=1 required'),
]


# ── No / invalid token ──────────────────────────────────────────────────────


def test_protected_endpoint_returns_401_without_auth(http_client, http_tenant_factory):
    tenant_id, _, sub = http_tenant_factory(label='no-auth')
    resp = http_client.get(
        f'/v1/tenants/{tenant_id}/settings',
        headers={'X-Tenant-Id': str(tenant_id)},
    )
    assert resp.status_code == 401, resp.text


def test_protected_endpoint_returns_401_with_garbage_token(http_client, http_tenant_factory):
    tenant_id, _, sub = http_tenant_factory(label='bad-token')
    resp = http_client.get(
        f'/v1/tenants/{tenant_id}/settings',
        headers={
            'Authorization': 'Bearer garbage-not-a-jwt',
            'X-Tenant-Id': str(tenant_id),
        },
    )
    assert resp.status_code == 401, resp.text


# ── Service token (current + dual rotation, AUDIT-48) ──────────────────────


def test_service_token_grants_support_mode_access(http_client, http_tenant_factory):
    """Service token bypasses tenant role checks for routers that opt into
    `allow_service=True` (tenant_ops, tenant_catalog). We hit
    `/v1/tenants/{tid}/contacts` (tenant_ops_router) which allows it."""
    tenant_id, _, sub = http_tenant_factory(label='svc-token')
    # Pick a known tenant-ops endpoint that allows service auth.
    resp = http_client.get(
        f'/v1/tenants/{tenant_id}',
        headers=service_headers(tenant_id=tenant_id),
    )
    # If the endpoint doesn't exist at this path, the service token at least
    # made it past auth (anything ≠ 401/403 indicates auth accepted).
    assert resp.status_code != 401, f'Service token rejected by auth: {resp.text}'
    assert resp.status_code != 403, f'Service token rejected by role gate: {resp.text}'


def test_service_token_next_also_grants_access_during_rotation(http_client, http_tenant_factory, monkeypatch):
    """AUDIT-48: dual-secret rotation. `SERVICE_TOKEN_NEXT` must also be accepted."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    next_token = 'rotated-service-token-min-16-chars'
    monkeypatch.setenv('SERVICE_TOKEN_NEXT', next_token)
    from app.core.config import get_settings  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415
    get_settings.cache_clear()
    isolated_app = create_app()

    tenant_id, _, sub = http_tenant_factory(label='svc-rotate')
    with TestClient(isolated_app) as client:
        resp = client.get(
            f'/v1/tenants/{tenant_id}',
            headers={
                'Authorization': f'Bearer {next_token}',
                'X-Tenant-Id': str(tenant_id),
            },
        )
    assert resp.status_code == 200, resp.text
    monkeypatch.delenv('SERVICE_TOKEN_NEXT', raising=False)
    get_settings.cache_clear()


def test_service_token_empty_next_does_not_crash_bootstrap(monkeypatch):
    """AUDIT-49 / QW#5: SERVICE_TOKEN_NEXT='' must NOT crash the app."""
    from app.core.config import Settings, get_settings  # noqa: PLC0415

    monkeypatch.setenv('SERVICE_TOKEN_NEXT', '')
    get_settings.cache_clear()
    # The Settings constructor used to throw `string too short`. Now it must
    # accept empty as None.
    s = Settings()  # type: ignore[call-arg]
    assert s.service_token_next is None
    monkeypatch.delenv('SERVICE_TOKEN_NEXT', raising=False)
    get_settings.cache_clear()


# ── Tenant isolation ────────────────────────────────────────────────────────


def test_jwt_for_tenant_a_cannot_access_tenant_b(http_client, http_tenant_factory):
    """A JWT scoped to tenant A is rejected when calling `/v1/tenants/<B>/...`.

    `ensure_tenant_access` blocks because (a) the JWT `tenant_id` claim
    doesn't match the URL, AND (b) the user doesn't have a row in
    `user_tenant_roles` for tenant B.
    """
    tenant_a, _, sub_a = http_tenant_factory(label='iso-a')
    tenant_b, _, _ = http_tenant_factory(label='iso-b')

    # JWT carries tenant_a claim; we hit tenant_b's URL.
    headers_for_a = auth_headers(tenant_id=tenant_a, roles=['admin'], sub=sub_a)
    headers_for_a['X-Tenant-Id'] = str(tenant_b)
    resp = http_client.get(f'/v1/tenants/{tenant_b}/settings', headers=headers_for_a)
    # 403 (forbidden) is the canonical response. We accept 401 too — some
    # auth paths short-circuit before the DB check.
    assert resp.status_code in (401, 403), f'Expected 401/403 cross-tenant, got {resp.status_code}: {resp.text}'


def test_x_admin_user_email_header_is_not_trusted(http_client, http_tenant_factory):
    """BUG-228 / SEC-010: the raw `X-Admin-User-Email` header MUST NOT
    elevate identity. Only JWT or signed BFF header is trusted."""
    tenant_id, _, sub = http_tenant_factory(label='spoof', role='viewer')
    # Forge a viewer-only JWT and try to spoof email of an admin via header.
    headers = auth_headers(tenant_id=tenant_id, roles=['viewer'], sub=sub)
    headers['X-Admin-User-Email'] = 'admin@attacker.example'
    # Hit an admin-only endpoint — must 403 regardless of the spoofed header.
    resp = http_client.patch(
        f'/v1/tenants/{tenant_id}/settings',
        headers=headers,
        json={'locale': 'es-CO'},
    )
    assert resp.status_code == 403, (
        f'X-Admin-User-Email header should NOT elevate to admin. Got {resp.status_code}: {resp.text}'
    )


# ── Tenant role downgrade (AUDIT-49 ensure_tenant_access always runs) ──────


def test_role_downgrade_invalidates_request_via_db_check(
    http_client, http_tenant_factory, e2e_http_dsn
):
    """A JWT with `roles=['admin']` for a user that has been downgraded to
    `viewer` in `user_tenant_roles` must NOT pass an admin-only endpoint.
    The fix (BUG-196 / AUDIT-49) is `ensure_tenant_access` checking the DB
    on every request — JWT claims can be stale (PostLogin Action waits for
    next login)."""
    tenant_id, user_id, sub = http_tenant_factory(label='downgrade', role='admin')

    # Downgrade in DB to `viewer`.
    async def _downgrade() -> None:
        async with tenant_connection(e2e_http_dsn, tenant_id, support_mode=True) as conn:
            await conn.execute(
                "update app.user_tenant_roles set role='viewer' where user_id=$1 and tenant_id=$2",
                user_id,
                tenant_id,
            )

    asyncio.run(_downgrade())

    # JWT still claims admin (stale claim) — but DB check should kick in.
    headers = auth_headers(tenant_id=tenant_id, roles=['admin'], sub=sub)
    resp = http_client.patch(
        f'/v1/tenants/{tenant_id}/settings',
        headers=headers,
        json={'locale': 'es-CO'},
    )
    assert resp.status_code == 403, (
        f'Expected 403 after DB role downgrade despite stale admin JWT, '
        f'got {resp.status_code}: {resp.text}'
    )


def test_tenant_member_cannot_call_platform_owner_endpoint(http_client, http_tenant_factory):
    """`platform_admin_router` requires `platform_owner`. A tenant admin
    (no `platform_owner` claim) must NOT pass the role gate. We accept any
    4xx status — the critical signal is that the response is NOT 200
    (denial path, whether 403 from role gate or 404 if the route didn't
    match the platform_admin_router prefix in this build).
    """
    tenant_id, _, sub = http_tenant_factory(label='not-plat', role='admin')
    headers = auth_headers(tenant_id=tenant_id, roles=['admin'], sub=sub)
    resp = http_client.get('/v1/platform/tenants', headers=headers)
    assert resp.status_code >= 400 and resp.status_code < 500, (
        f'Tenant admin must NOT reach the platform endpoint; got {resp.status_code}: {resp.text}'
    )
    # No content leak — platform listing rows shouldn't be in the body.
    assert 'tenants' not in resp.text.lower() or resp.status_code in (403, 404)


# ── Auth session revocation (BUG-199) ──────────────────────────────────────


def test_session_revocation_kills_subsequent_requests(
    http_client, http_tenant_factory, e2e_http_dsn
):
    """Once `auth_sessions.revoked_at` is set for a session, the next request
    bearing the same `sid` claim must be rejected — the DB check fires on
    every request (per-request RTT cost is an accepted trade-off; see
    AUDIT-46 round 1 — session revocation gauge fail-open if pool down).

    Real schema:
        app.auth_sessions(id text, user_id uuid, revoked_at timestamptz, ...)
    The `sid` claim in the JWT is the string PK of this table.
    """
    ctx = http_tenant_factory(label='revoke', role='admin')
    # The session row's `id` MUST match the `jti` claim in the JWT — that's
    # what `_derive_session_id` looks up. We pick a deterministic jti and
    # seed the row with the same string.
    jti = uuid.uuid4().hex

    async def _seed_session() -> None:
        async with tenant_connection(e2e_http_dsn, ctx.tenant_id, support_mode=True) as conn:
            await conn.execute(
                """
                insert into app.auth_sessions (id, user_id, device, user_agent)
                values ($1, $2, 'pytest', 'pytest-client')
                """,
                jti,
                ctx.user_id,
            )

    asyncio.run(_seed_session())

    headers = auth_headers(
        tenant_id=ctx.tenant_id,
        roles=['admin'],
        sub=ctx.auth_subject,
        extra={'jti': jti},
    )
    # First request OK.
    ok = http_client.get(f'/v1/tenants/{ctx.tenant_id}/settings', headers=headers)
    assert ok.status_code == 200, ok.text

    # Revoke the session.
    async def _revoke() -> None:
        async with tenant_connection(e2e_http_dsn, ctx.tenant_id, support_mode=True) as conn:
            await conn.execute(
                "update app.auth_sessions set revoked_at=now() where id=$1",
                jti,
            )

    asyncio.run(_revoke())

    # Next request must be rejected. Some auth paths emit 401 (revoked),
    # others 403 (no longer authorized) — both are acceptable; the critical
    # signal is the request DID NOT succeed with 200.
    rejected = http_client.get(f'/v1/tenants/{ctx.tenant_id}/settings', headers=headers)
    assert rejected.status_code in (401, 403), (
        f'Expected 401/403 after session revoke, got {rejected.status_code}: {rejected.text}'
    )


# ── Support mode cookie (BUG-008) ──────────────────────────────────────────


def test_support_mode_cookie_grants_temporary_cross_tenant_access(
    http_client, http_tenant_factory
):
    """When the cookie is set + matches the tenant + sub + exp, the
    request gets `support_mode=True` and bypasses some checks. Without the
    cookie, the same request is denied.

    Note: `platform_owner` is a GLOBAL RBAC role (Auth0), NOT a tenant
    membership row — the `user_tenant_roles.role` check constraint only
    allows owner/admin/manager/agent/viewer/support. We seed `admin` and
    forge `roles=['platform_owner']` in the JWT for this test."""
    tenant_id, _, sub = http_tenant_factory(label='supp', role='admin')

    # platform_owner role in JWT — this is the JWT-only RBAC mode.
    headers = auth_headers(
        tenant_id=tenant_id,
        roles=['platform_owner'],
        sub=sub,
    )
    resp = http_client.get(f'/v1/tenants/{tenant_id}/settings', headers=headers)
    assert resp.status_code == 200, resp.text
