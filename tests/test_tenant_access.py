import asyncio
from uuid import uuid4

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.v1.routes import ensure_tenant_access, tenant_id_from_request


def make_request() -> Request:
    return Request({'type': 'http', 'method': 'GET', 'path': '/', 'headers': []})


class FakeTenantRoleConnection:
    def __init__(self, has_role: bool) -> None:
        self.has_role = has_role
        self.configured_tenant_id = None

    async def fetchval(self, *_args, **_kwargs):
        return self.has_role

    async def execute(self, _query, tenant_id):
        self.configured_tenant_id = tenant_id


def test_unscoped_user_with_requested_tenant_still_requires_database_tenant_role():
    async def run_test():
        request = make_request()
        request.state.actor_type = 'user'
        request.state.actor_id = 'auth0|platform-user'
        request.state.support_mode = False
        request.state.tenant_id = None
        request.state.requested_tenant_id = uuid4()

        with pytest.raises(HTTPException) as exc_info:
            await ensure_tenant_access(request, request.state.requested_tenant_id, FakeTenantRoleConnection(False))

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == 'X-Tenant-Id header or tenant_id claim is required'

    asyncio.run(run_test())


def test_unscoped_user_with_database_tenant_role_can_use_requested_tenant_context():
    async def run_test():
        tenant_id = uuid4()
        request = make_request()
        request.state.actor_type = 'user'
        request.state.actor_id = 'auth0|platform-user'
        request.state.support_mode = False
        request.state.tenant_id = None
        request.state.requested_tenant_id = tenant_id
        conn = FakeTenantRoleConnection(True)

        resolved_tenant_id = await tenant_id_from_request(request, conn)

        assert resolved_tenant_id == tenant_id
        assert conn.configured_tenant_id == str(tenant_id)

    asyncio.run(run_test())
