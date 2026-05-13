"""TASK-0077 — Tenant-scoped authorization regression matrix.

Covers the nine BUGs (03/07/08/11/16/17/23/24/25) that the structural fix
in ``ensure_tenant_role`` / ``ensure_tenant_access`` is meant to close.

The suite is intentionally hermetic: it exercises the authorization helpers
and the ``patch_tenant``/``create_own_tenant``/``update_tenant_record``
contracts directly, using fake asyncpg connections.  The router-level
behavior (FastAPI dependency wiring) is asserted with static-source guards
where a full e2e would require Postgres + Auth0.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.v1.routes import (
    create_own_tenant,
    ensure_tenant_access,
    ensure_tenant_role,
    get_user_tenant_role,
    update_tenant_record,
)
from app.api.v1.schemas import PlatformTenantUpdate, TenantCreate, TenantUpdate
from app.core.security import require_min_role


ROUTES = Path('app/api/v1/routes.py')
ROUTES_SOURCE = ROUTES.read_text()


def _make_request() -> Request:
    return Request({'type': 'http', 'method': 'GET', 'path': '/', 'headers': []})


def _user_request(*, roles: list[str], tenant_id=None, actor_id='auth0|user') -> Request:
    request = _make_request()
    request.state.actor_type = 'user'
    request.state.actor_id = actor_id
    request.state.support_mode = False
    request.state.roles = roles
    request.state.tenant_id = tenant_id
    request.state.requested_tenant_id = tenant_id
    return request


class RoleConn:
    """Fake asyncpg.Connection that returns a list of roles for the actor.

    A single instance models the per-tenant DB rows the actor holds.  Methods
    not relevant to authorization (``execute``) are accepted to allow audit
    log fire-and-forget calls and ``set_config`` to no-op.
    """

    def __init__(self, roles: list[str] | None = None) -> None:
        self._roles = roles or []
        self.executed: list[tuple[str, tuple]] = []

    async def fetch(self, query: str, *_args, **_kwargs):
        if 'select utr.role' in query:
            return [{'role': role} for role in self._roles]
        return []

    async def fetchval(self, *_args, **_kwargs):
        return None

    async def fetchrow(self, *_args, **_kwargs):
        return None

    async def execute(self, query: str, *args, **_kwargs):
        self.executed.append((query, args))

    def transaction(self):
        class _Tx:
            async def __aenter__(self_inner):
                return self_inner
            async def __aexit__(self_inner, *exc):
                return False
        return _Tx()


# ---------------------------------------------------------------------------
# Core invariants of ensure_tenant_role (BUG16 / BUG25 root cause)
# ---------------------------------------------------------------------------


def test_ensure_tenant_role_jwt_admin_db_viewer_is_rejected():
    """BUG16 / BUG25: JWT admin (unscoped or scoped to home tenant) +
    DB viewer in the victim tenant must NOT pass an admin check."""
    async def run():
        request = _user_request(roles=['admin'], tenant_id=None)
        conn = RoleConn(['viewer'])

        with pytest.raises(HTTPException) as exc:
            await ensure_tenant_role(request, conn, uuid4(), 'admin')

        assert exc.value.status_code == 403
        assert 'tenant' in exc.value.detail.lower()

    asyncio.run(run())


def test_ensure_tenant_role_jwt_viewer_db_admin_is_rejected():
    """Defense-in-depth: even with admin in the target DB, a JWT that does
    not carry the role required by the endpoint must be rejected.  This is
    the invariant the PR-#111 review insisted on preserving."""
    async def run():
        request = _user_request(roles=['viewer'])
        conn = RoleConn(['admin'])

        with pytest.raises(HTTPException) as exc:
            await ensure_tenant_role(request, conn, uuid4(), 'admin')

        assert exc.value.status_code == 403

    asyncio.run(run())


def test_ensure_tenant_role_both_admin_succeeds():
    async def run():
        request = _user_request(roles=['admin'])
        conn = RoleConn(['admin'])
        await ensure_tenant_role(request, conn, uuid4(), 'admin')

    asyncio.run(run())


def test_ensure_tenant_role_service_actor_bypasses():
    async def run():
        request = _make_request()
        request.state.actor_type = 'service'
        request.state.support_mode = True
        request.state.roles = []
        await ensure_tenant_role(request, RoleConn([]), uuid4(), 'admin')

    asyncio.run(run())


def test_ensure_tenant_role_support_mode_bypasses():
    async def run():
        request = _make_request()
        request.state.actor_type = 'user'
        request.state.actor_id = 'auth0|support'
        request.state.support_mode = True
        request.state.roles = []
        await ensure_tenant_role(request, RoleConn([]), uuid4(), 'admin')

    asyncio.run(run())


def test_ensure_tenant_role_platform_owner_unscoped_bypasses():
    """``platform_owner`` JWTs are issued unscoped (no tenant_id claim) and
    are never written to ``user_tenant_roles``; they must still be able to
    administer any tenant."""
    async def run():
        request = _user_request(roles=['platform_owner'], tenant_id=None)
        await ensure_tenant_role(request, RoleConn([]), uuid4(), 'admin')

    asyncio.run(run())


def test_ensure_tenant_role_platform_owner_scoped_does_not_bypass():
    """A scoped token claiming ``platform_owner`` is suspicious; the bypass
    only applies when the token is unscoped (no tenant_id claim)."""
    async def run():
        request = _user_request(roles=['platform_owner'], tenant_id=uuid4())
        with pytest.raises(HTTPException):
            await ensure_tenant_role(request, RoleConn(['viewer']), uuid4(), 'admin')

    asyncio.run(run())


# ---------------------------------------------------------------------------
# ensure_tenant_access + require_min_role propagation
# ---------------------------------------------------------------------------


def test_require_min_role_records_required_tenant_role():
    """The router-level dependency must publish its minimum on
    ``request.state`` so the handler-level ``ensure_tenant_access`` can apply
    the same gate against the DB role table."""
    async def run():
        request = _user_request(roles=['admin'])
        await require_min_role('admin')(request)
        assert request.state.required_tenant_role == 'admin'

    asyncio.run(run())


def test_ensure_tenant_access_enforces_required_tenant_role_from_state():
    """BUG16: when the router announces ``required_tenant_role='admin'``, a
    DB viewer in the target tenant must be rejected even if the JWT token
    nominally scopes to that tenant."""
    async def run():
        tenant_id = uuid4()
        request = _user_request(roles=['admin'], tenant_id=tenant_id)
        request.state.required_tenant_role = 'admin'

        with pytest.raises(HTTPException) as exc:
            await ensure_tenant_access(request, tenant_id, RoleConn(['viewer']))

        assert exc.value.status_code == 403

    asyncio.run(run())


def test_ensure_tenant_access_allows_when_db_role_meets_required():
    async def run():
        tenant_id = uuid4()
        request = _user_request(roles=['admin'], tenant_id=tenant_id)
        request.state.required_tenant_role = 'admin'

        await ensure_tenant_access(request, tenant_id, RoleConn(['admin']))

    asyncio.run(run())


def test_ensure_tenant_access_legacy_mode_when_no_router_min_role():
    """``tenant_user_router`` endpoints don't install ``require_min_role``;
    in that legacy mode any membership row remains sufficient."""
    async def run():
        tenant_id = uuid4()
        request = _user_request(roles=[], tenant_id=tenant_id)

        await ensure_tenant_access(request, tenant_id, RoleConn(['viewer']))

    asyncio.run(run())


# ---------------------------------------------------------------------------
# BUG03 / BUG07 / BUG08 / BUG23: tenant-admin endpoints — static guards
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    'route_decorator',
    [
        # BUG03: media / promotions
        "@tenant_admin_router.get('/tenants/{tenant_id}/media')",
        "@tenant_admin_router.post('/tenants/{tenant_id}/media', status_code=201)",
        "@tenant_admin_router.patch('/tenants/{tenant_id}/media/{asset_id}')",
        "@tenant_admin_router.delete('/tenants/{tenant_id}/media/{asset_id}', status_code=204)",
        "@tenant_admin_router.get('/tenants/{tenant_id}/promotions')",
        "@tenant_admin_router.post('/tenants/{tenant_id}/promotions', status_code=201)",
        "@tenant_admin_router.patch('/tenants/{tenant_id}/promotions/{promotion_id}')",
        "@tenant_admin_router.delete('/tenants/{tenant_id}/promotions/{promotion_id}', status_code=204)",
        # BUG07: whatsapp templates
        "@tenant_admin_router.post('/tenants/{tenant_id}/whatsapp/templates', status_code=201)",
        "@tenant_admin_router.get('/tenants/{tenant_id}/whatsapp/templates')",
        "@tenant_admin_router.get('/tenants/{tenant_id}/whatsapp/templates/{template_id}')",
        "@tenant_admin_router.patch('/tenants/{tenant_id}/whatsapp/templates/{template_id}')",
        "@tenant_admin_router.post('/tenants/{tenant_id}/whatsapp/templates/sync')",
        "@tenant_admin_router.delete('/tenants/{tenant_id}/whatsapp/templates/{template_id}', status_code=204)",
        # BUG08: service catalog writes
        "@tenant_admin_router.post('/tenants/{tenant_id}/services', status_code=201)",
        "@tenant_admin_router.patch('/tenants/{tenant_id}/services/{service_id}')",
        "@tenant_admin_router.delete('/tenants/{tenant_id}/services/{service_id}', status_code=204)",
        "@tenant_admin_router.post('/tenants/{tenant_id}/services/reorder')",
    ],
)
def test_tenant_admin_handler_calls_ensure_tenant_access(route_decorator: str):
    """Every tenant-admin handler must call ``ensure_tenant_access`` so the
    JWT+DB role gate (set up by ``require_min_role('admin')`` at the router
    level) actually fires.  This guards BUG03 / BUG07 / BUG08 against future
    handlers being added that skip the helper."""
    start = ROUTES_SOURCE.index(route_decorator)
    # Find the end of this handler by looking for the next decorator.
    next_decorator = ROUTES_SOURCE.find('@', start + len(route_decorator) + 1)
    handler_source = ROUTES_SOURCE[start:next_decorator]
    assert 'ensure_tenant_access(request, tenant_id, conn)' in handler_source, (
        f'{route_decorator} no longer calls ensure_tenant_access — '
        'tenant role enforcement would be bypassed.'
    )


def test_knowledge_studio_handlers_enforce_tenant_role():
    """BUG23: Knowledge Studio list/get/update/delete live under
    ``tenant_admin_router`` and resolve the tenant via
    ``tenant_id_from_request`` which calls ``ensure_tenant_access``.  Static
    guard against future drift."""
    for decorator in (
        "@tenant_admin_router.get('/knowledge/documents')",
        "@tenant_admin_router.post('/knowledge/documents', status_code=201)",
        "@tenant_admin_router.get('/knowledge/documents/{document_id}')",
        "@tenant_admin_router.patch('/knowledge/documents/{document_id}')",
        "@tenant_admin_router.delete('/knowledge/documents/{document_id}', status_code=204)",
    ):
        start = ROUTES_SOURCE.index(decorator)
        next_decorator = ROUTES_SOURCE.find('@', start + len(decorator) + 1)
        handler = ROUTES_SOURCE[start:next_decorator]
        assert 'tenant_id_from_request(request, conn)' in handler or \
               'ensure_tenant_access(request' in handler, (
            f'{decorator} no longer routes through the tenant access helpers'
        )


# ---------------------------------------------------------------------------
# BUG11: tenant status mutation gated to platform_owner
# ---------------------------------------------------------------------------


def test_patch_tenant_status_is_platform_admin_only():
    """BUG11: the ``/tenants/{tenant_id}/status`` endpoint must be on
    ``platform_admin_router`` (which requires ``require_platform_owner``),
    not ``tenant_admin_router`` (which any tenant admin can reach)."""
    assert (
        "@platform_admin_router.patch('/tenants/{tenant_id}/status')" in ROUTES_SOURCE
    )
    # Negative: must not appear under tenant_admin_router any more.
    assert (
        "@tenant_admin_router.patch('/tenants/{tenant_id}/status')" not in ROUTES_SOURCE
    )


def test_tenant_update_schema_does_not_carry_status():
    """BUG11: ``TenantUpdate`` (the tenant-admin payload) must not let a
    tenant admin write ``status``.  ``PlatformTenantUpdate`` is the
    platform-only superset."""
    assert 'status' not in TenantUpdate.model_fields
    assert 'status' in PlatformTenantUpdate.model_fields


def test_update_tenant_record_rejects_status_for_non_platform_owner():
    """Defense-in-depth: even if a ``PlatformTenantUpdate`` somehow reaches
    the helper without the platform-owner flag, ``status`` writes are
    refused."""
    async def run():
        payload = PlatformTenantUpdate(status='suspended')
        with pytest.raises(HTTPException) as exc:
            await update_tenant_record(RoleConn([]), uuid4(), payload)
        assert exc.value.status_code == 403

    asyncio.run(run())


# ---------------------------------------------------------------------------
# BUG17: data-export double-check
# ---------------------------------------------------------------------------


def test_export_tenant_data_calls_ensure_tenant_role_owner():
    """BUG17: the data-export handler must call
    ``ensure_tenant_role(..., 'owner')``, not the weaker
    ``ensure_tenant_access`` alone, so owner-JWT-A + viewer-DB-B is rejected
    (and owner-JWT-A + no-membership-B too)."""
    start = ROUTES_SOURCE.index(
        "@tenant_admin_router.get('/tenants/{tenant_id}/data-export')"
    )
    next_decorator = ROUTES_SOURCE.find('@', start + 1)
    handler = ROUTES_SOURCE[start:next_decorator]
    assert "ensure_tenant_role(request, conn, tenant_id, 'owner')" in handler


def test_ensure_tenant_role_owner_jwt_a_viewer_db_b_is_rejected():
    """BUG17 rubric: owner JWT in *some* tenant + viewer DB in tenant B
    must NOT export tenant B."""
    async def run():
        request = _user_request(roles=['owner'], tenant_id=uuid4())
        conn = RoleConn(['viewer'])
        with pytest.raises(HTTPException) as exc:
            await ensure_tenant_role(request, conn, uuid4(), 'owner')
        assert exc.value.status_code == 403

    asyncio.run(run())


def test_ensure_tenant_role_admin_jwt_owner_db_is_rejected_for_owner_endpoint():
    """BUG17 rubric: admin JWT + owner DB in target — JWT half fails the
    owner requirement, so the call must be rejected."""
    async def run():
        request = _user_request(roles=['admin'])
        conn = RoleConn(['owner'])
        with pytest.raises(HTTPException) as exc:
            await ensure_tenant_role(request, conn, uuid4(), 'owner')
        assert exc.value.status_code == 403

    asyncio.run(run())


def test_ensure_tenant_role_owner_both_sides_passes():
    async def run():
        tenant_id = uuid4()
        request = _user_request(roles=['owner'], tenant_id=tenant_id)
        await ensure_tenant_role(request, RoleConn(['owner']), tenant_id, 'owner')

    asyncio.run(run())


# ---------------------------------------------------------------------------
# BUG24: tenant-signup must not hijack existing tenants
# ---------------------------------------------------------------------------


class _MembershipConn:
    def __init__(self, existing_tenant_id):
        self.existing_tenant_id = existing_tenant_id

    async def fetchval(self, *_args, **_kwargs):
        return self.existing_tenant_id

    async def fetchrow(self, *_args, **_kwargs):
        return None

    async def fetch(self, *_args, **_kwargs):
        return []

    async def execute(self, *_args, **_kwargs):
        return None


def test_tenant_signup_returns_409_when_actor_has_membership():
    """BUG24: if the caller already belongs to a tenant we MUST NOT update
    that tenant's profile from the unauthenticated-shape signup flow.  The
    previous behaviour silently overwrote the first membership's tenant."""
    async def run():
        request = _user_request(roles=['admin'])
        request.state.email = 'attacker@example.com'
        request.state.name = 'attacker'
        existing_tenant_id = uuid4()
        conn = _MembershipConn(existing_tenant_id)

        payload = TenantCreate(
            slug='hijacked',
            legal_name='HIJACKED',
            display_name='HIJACKED',
            vertical_code='retail',
        )

        with pytest.raises(HTTPException) as exc:
            await create_own_tenant(payload, request, conn)

        assert exc.value.status_code == 409

    asyncio.run(run())


# ---------------------------------------------------------------------------
# BUG25: has_user_tenant_role removed in favor of get_user_tenant_role
# ---------------------------------------------------------------------------


def test_has_user_tenant_role_is_removed():
    """BUG25: the legacy existence-only helper must be gone from the
    codebase.  ``get_user_tenant_role`` (returns the role or ``None``) is
    the replacement."""
    assert 'def has_user_tenant_role' not in ROUTES_SOURCE
    assert 'def get_user_tenant_role' in ROUTES_SOURCE


def test_get_user_tenant_role_returns_highest_role():
    async def run():
        request = _user_request(roles=[])
        conn = RoleConn(['viewer', 'admin', 'agent'])
        role = await get_user_tenant_role(conn, request, uuid4())
        assert role == 'admin'

    asyncio.run(run())


def test_get_user_tenant_role_returns_none_when_no_row():
    async def run():
        request = _user_request(roles=[])
        role = await get_user_tenant_role(RoleConn([]), request, uuid4())
        assert role is None

    asyncio.run(run())
