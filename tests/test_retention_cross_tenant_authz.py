"""Regression test for cross-tenant retention policy authorization.

The PUT /v1/tenants/{tenant_id}/retention/policies endpoint must reject a
caller who only has a non-admin membership in the target tenant, even if
the JWT's session role is ``admin`` (issued in the context of a different
tenant where they are an administrator).

See: ``ensure_tenant_role`` and the ``put_retention_policies`` handler.
"""
from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.v1.routes import ensure_tenant_role
from tests._routes_aggregator import routes_aggregated_source


def _make_request() -> Request:
    return Request({'type': 'http', 'method': 'PUT', 'path': '/', 'headers': []})


class _FakeRolesConn:
    def __init__(self, roles_for_target: list[str]) -> None:
        self._roles = roles_for_target

    async def fetch(self, *_args, **_kwargs):
        return [{'role': role} for role in self._roles]


def test_viewer_in_target_tenant_cannot_satisfy_admin_check():
    async def run_test():
        request = _make_request()
        request.state.actor_type = 'user'
        request.state.actor_id = 'auth0|cross-tenant-attacker'
        request.state.support_mode = False
        # The attacker is admin in their *home* tenant (JWT roles), but only
        # ``viewer`` in the victim tenant.
        request.state.roles = ['admin']
        request.state.tenant_id = uuid4()

        victim_tenant_id = uuid4()
        conn = _FakeRolesConn(['viewer'])

        with pytest.raises(HTTPException) as exc_info:
            await ensure_tenant_role(request, conn, victim_tenant_id, 'admin')

        assert exc_info.value.status_code == 403

    asyncio.run(run_test())


def test_agent_in_target_tenant_cannot_satisfy_admin_check():
    async def run_test():
        request = _make_request()
        request.state.actor_type = 'user'
        request.state.actor_id = 'auth0|user'
        request.state.support_mode = False
        request.state.roles = ['admin']
        request.state.tenant_id = uuid4()

        conn = _FakeRolesConn(['agent', 'viewer'])

        with pytest.raises(HTTPException) as exc_info:
            await ensure_tenant_role(request, conn, uuid4(), 'admin')

        assert exc_info.value.status_code == 403

    asyncio.run(run_test())


def test_admin_in_target_tenant_passes_admin_check():
    """TASK-0077: both halves must agree.  When the JWT carries admin and the
    DB also confirms admin in the target tenant, the call succeeds."""
    async def run_test():
        request = _make_request()
        request.state.actor_type = 'user'
        request.state.actor_id = 'auth0|user'
        request.state.support_mode = False
        request.state.roles = ['admin']
        request.state.tenant_id = uuid4()

        conn = _FakeRolesConn(['admin'])

        await ensure_tenant_role(request, conn, uuid4(), 'admin')

    asyncio.run(run_test())


def test_owner_in_target_tenant_passes_admin_check():
    async def run_test():
        request = _make_request()
        request.state.actor_type = 'user'
        request.state.actor_id = 'auth0|user'
        request.state.support_mode = False
        request.state.roles = ['owner']
        request.state.tenant_id = uuid4()

        conn = _FakeRolesConn(['owner'])

        await ensure_tenant_role(request, conn, uuid4(), 'admin')

    asyncio.run(run_test())


def test_db_admin_without_jwt_admin_is_rejected():
    """TASK-0077: defense-in-depth — a DB admin row without a JWT carrying the
    required role must still fail.  The JWT half is the token-portability
    invariant the bot review flagged in PR #111."""
    async def run_test():
        request = _make_request()
        request.state.actor_type = 'user'
        request.state.actor_id = 'auth0|user'
        request.state.support_mode = False
        request.state.roles = ['viewer']
        request.state.tenant_id = uuid4()

        conn = _FakeRolesConn(['admin'])

        with pytest.raises(HTTPException) as exc_info:
            await ensure_tenant_role(request, conn, uuid4(), 'admin')

        assert exc_info.value.status_code == 403

    asyncio.run(run_test())


def test_support_mode_bypasses_tenant_role_check():
    async def run_test():
        request = _make_request()
        request.state.actor_type = 'user'
        request.state.actor_id = 'auth0|support-user'
        request.state.support_mode = True
        request.state.roles = []
        request.state.tenant_id = None

        conn = _FakeRolesConn([])

        await ensure_tenant_role(request, conn, uuid4(), 'admin')

    asyncio.run(run_test())


def test_support_role_does_not_pass_admin_check():
    """BUG-133: ``support`` is NOT a role — it's a mode (`support_mode` flag/
    cookie). Removing it from `_ROLE_LEVELS` / `_TENANT_ROLE_LEVELS` means
    a JWT (or DB membership) carrying ``support`` no longer outranks anything;
    it now fails admin checks like any unknown role. The legitimate way to
    elevate cross-tenant is via the support_mode endpoint (cookie + audit),
    not a role string.
    """
    async def run_test():
        request = _make_request()
        request.state.actor_type = 'user'
        request.state.actor_id = 'auth0|support'
        request.state.support_mode = False
        request.state.roles = ['support']
        request.state.tenant_id = uuid4()

        conn = _FakeRolesConn(['support'])

        with pytest.raises(HTTPException) as exc_info:
            await ensure_tenant_role(request, conn, uuid4(), 'admin')

        # JWT role gate fails first (`support` is no longer in the ladder).
        assert exc_info.value.status_code == 403

    asyncio.run(run_test())


def test_service_actor_bypasses_tenant_role_check():
    async def run_test():
        request = _make_request()
        request.state.actor_type = 'service'
        request.state.actor_id = None
        request.state.support_mode = False
        request.state.roles = []

        conn = _FakeRolesConn([])

        await ensure_tenant_role(request, conn, uuid4(), 'admin')

    asyncio.run(run_test())


def test_put_retention_policies_handler_calls_ensure_tenant_role():
    """Static guard: the destructive PUT handler must consult the per-tenant
    role table, not just the router-level ``require_min_role('admin')`` which
    is satisfied by any JWT carrying admin for *some* tenant."""
    source = routes_aggregated_source()
    handler_start = source.index(
        "@tenant_admin_router.put('/tenants/{tenant_id}/retention/policies')"
    )
    handler_end = source.index('@tenant_admin_router', handler_start + 1)
    handler_source = source[handler_start:handler_end]
    assert "ensure_tenant_role(request, conn, tenant_id, 'admin')" in handler_source
