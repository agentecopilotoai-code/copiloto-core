"""Cover the request-bound deps still in routes.py:
get_user_tenant_role, user_tenant_roles_for, _audit_authz_denied,
ensure_tenant_access, ensure_tenant_role, require_tenant, tenant_id_from_request,
user_email_from_request, current_user_id_from_request, _ensure_caller_can_target_role.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException


class _FakeConn:
    def __init__(self, *, fetch_results=None, fetchrow_results=None, fetchval_results=None):
        self._fetch = list(fetch_results or [])
        self._fetchrow = list(fetchrow_results or [])
        self._fetchval = list(fetchval_results or [])
        self.executed = []

    async def fetch(self, sql, *args):
        return self._fetch.pop(0) if self._fetch else []

    async def fetchrow(self, sql, *args):
        return self._fetchrow.pop(0) if self._fetchrow else None

    async def fetchval(self, sql, *args):
        return self._fetchval.pop(0) if self._fetchval else None

    async def execute(self, sql, *args):
        self.executed.append((sql, args))


def _req(state_kw=None, headers=None, scope_path='/test'):
    defaults = {
        'actor_id': None,
        'actor_type': 'user',
        'tenant_id': None,
        'requested_tenant_id': None,
        'roles': [],
        'support_mode': False,
        'email': None,
    }
    defaults.update(state_kw or {})
    state = SimpleNamespace(**defaults)
    return SimpleNamespace(
        state=state,
        headers=headers or {},
        scope={'path': scope_path},
    )


# ═══ get_user_tenant_role ═════════════════════════════════════════════


def test_get_user_tenant_role_no_actor_returns_none():
    from app.api.v1.routes import get_user_tenant_role
    req = _req()  # actor_id=None

    async def _go():
        return await get_user_tenant_role(_FakeConn(), req, uuid4())

    assert asyncio.run(_go()) is None


def test_get_user_tenant_role_no_rows_returns_none():
    from app.api.v1.routes import get_user_tenant_role
    req = _req({'actor_id': 'auth0|x'})
    conn = _FakeConn(fetch_results=[[]])

    async def _go():
        return await get_user_tenant_role(conn, req, uuid4())

    assert asyncio.run(_go()) is None


def test_get_user_tenant_role_returns_highest():
    from app.api.v1.routes import get_user_tenant_role
    req = _req({'actor_id': 'auth0|x'})
    # Two rows: viewer + admin → admin wins (higher rank)
    conn = _FakeConn(fetch_results=[[{'role': 'viewer'}, {'role': 'admin'}]])

    async def _go():
        return await get_user_tenant_role(conn, req, uuid4())

    assert asyncio.run(_go()) == 'admin'


# ═══ user_tenant_roles_for ═══════════════════════════════════════════


def test_user_tenant_roles_for_no_actor_returns_empty():
    from app.api.v1.routes import user_tenant_roles_for
    req = _req()

    async def _go():
        return await user_tenant_roles_for(_FakeConn(), req, uuid4())

    assert asyncio.run(_go()) == []


def test_user_tenant_roles_for_returns_list():
    from app.api.v1.routes import user_tenant_roles_for
    req = _req({'actor_id': 'auth0|x'})
    conn = _FakeConn(fetch_results=[[{'role': 'admin'}, {'role': 'agent'}]])

    async def _go():
        return await user_tenant_roles_for(conn, req, uuid4())

    out = asyncio.run(_go())
    assert sorted(out) == ['admin', 'agent']


# ═══ _audit_authz_denied ═══════════════════════════════════════════════


def test_audit_authz_denied_no_conn_returns():
    from app.api.v1.routes import _audit_authz_denied
    req = _req()

    async def _go():
        await _audit_authz_denied(req, None, tenant_id=uuid4(), reason='x')

    asyncio.run(_go())  # no raise


def test_audit_authz_denied_with_conn_swallows_exception(monkeypatch):
    from app.api.v1 import routes

    async def _broken_audit(*args, **kw):
        raise RuntimeError('audit table missing')

    monkeypatch.setattr(routes, 'audit', _broken_audit)
    req = _req()

    async def _go():
        await routes._audit_authz_denied(req, _FakeConn(), tenant_id=uuid4(), reason='x')

    asyncio.run(_go())  # swallowed


def test_audit_authz_denied_writes_record(monkeypatch):
    from app.api.v1 import routes

    calls = []

    async def _capture(conn, **kw):
        calls.append(kw)

    monkeypatch.setattr(routes, 'audit', _capture)
    req = _req({'actor_id': 'u1', 'actor_type': 'user'})

    async def _go():
        await routes._audit_authz_denied(req, _FakeConn(), tenant_id=uuid4(), reason='bad')

    asyncio.run(_go())
    assert len(calls) == 1
    assert calls[0]['action'] == 'authz.denied'
    assert calls[0]['metadata']['reason'] == 'bad'


# ═══ ensure_tenant_access ════════════════════════════════════════════════


def test_ensure_tenant_access_service_token_bypasses():
    from app.api.v1.routes import ensure_tenant_access
    req = _req({'actor_type': 'service'})

    async def _go():
        await ensure_tenant_access(req, uuid4(), _FakeConn())

    asyncio.run(_go())  # no raise


def test_ensure_tenant_access_support_mode_bypasses():
    from app.api.v1.routes import ensure_tenant_access
    req = _req({'support_mode': True})

    async def _go():
        await ensure_tenant_access(req, uuid4(), _FakeConn())

    asyncio.run(_go())


def test_ensure_tenant_access_platform_owner_unscoped_bypasses():
    from app.api.v1.routes import ensure_tenant_access
    req = _req({'roles': ['platform_owner']})  # tenant_id=None

    async def _go():
        await ensure_tenant_access(req, uuid4(), _FakeConn())

    asyncio.run(_go())


def test_ensure_tenant_access_no_required_role_token_scope_matches():
    """Legacy: when no required role + token tenant matches → allow."""
    from app.api.v1.routes import ensure_tenant_access
    tid = uuid4()
    req = _req({'tenant_id': tid, 'actor_id': 'u1'})

    async def _go():
        await ensure_tenant_access(req, tid, _FakeConn())

    asyncio.run(_go())


def test_ensure_tenant_access_no_required_role_db_membership_allows():
    from app.api.v1.routes import ensure_tenant_access
    req = _req({'tenant_id': uuid4(), 'actor_id': 'u1'})
    conn = _FakeConn(fetch_results=[[{'role': 'viewer'}]])

    async def _go():
        await ensure_tenant_access(req, uuid4(), conn)

    asyncio.run(_go())


def test_ensure_tenant_access_no_tenant_scope_raises_400():
    from app.api.v1.routes import ensure_tenant_access
    req = _req({'actor_id': 'u1'})  # tenant_id=None
    conn = _FakeConn(fetch_results=[[]])  # no rows

    async def _go():
        await ensure_tenant_access(req, uuid4(), conn)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_go())
    assert exc_info.value.status_code == 400


def test_ensure_tenant_access_tenant_scope_mismatch_raises_403():
    from app.api.v1.routes import ensure_tenant_access
    req = _req({'tenant_id': uuid4(), 'actor_id': 'u1'})  # different tenant
    conn = _FakeConn(fetch_results=[[]])

    async def _go():
        await ensure_tenant_access(req, uuid4(), conn)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_go())
    assert exc_info.value.status_code == 403


def test_ensure_tenant_access_with_required_role_db_admin_allows():
    from app.api.v1.routes import ensure_tenant_access
    req = _req({'actor_id': 'u1', 'required_tenant_role': 'admin'})
    conn = _FakeConn(fetch_results=[[{'role': 'admin'}]])

    async def _go():
        await ensure_tenant_access(req, uuid4(), conn)

    asyncio.run(_go())


def test_ensure_tenant_access_with_required_role_db_viewer_rejected():
    """JWT-admin + DB-viewer → 403 (BUG16/25 protection)."""
    from app.api.v1.routes import ensure_tenant_access
    req = _req({'actor_id': 'u1', 'required_tenant_role': 'admin'})
    conn = _FakeConn(fetch_results=[[{'role': 'viewer'}]])

    async def _go():
        await ensure_tenant_access(req, uuid4(), conn)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_go())
    assert exc_info.value.status_code == 403


# ═══ ensure_tenant_role ═══════════════════════════════════════════════


def test_ensure_tenant_role_service_bypasses():
    from app.api.v1.routes import ensure_tenant_role
    req = _req({'actor_type': 'service'})

    async def _go():
        await ensure_tenant_role(req, _FakeConn(), uuid4(), 'admin')

    asyncio.run(_go())


def test_ensure_tenant_role_platform_owner_unscoped_bypasses():
    from app.api.v1.routes import ensure_tenant_role
    req = _req({'roles': ['platform_owner']})

    async def _go():
        await ensure_tenant_role(req, _FakeConn(), uuid4(), 'admin')

    asyncio.run(_go())


def test_ensure_tenant_role_jwt_insufficient_raises():
    from app.api.v1.routes import ensure_tenant_role
    req = _req({'actor_id': 'u1', 'roles': ['viewer']})

    async def _go():
        await ensure_tenant_role(req, _FakeConn(), uuid4(), 'admin')

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_go())
    assert exc_info.value.status_code == 403


def test_ensure_tenant_role_jwt_ok_db_ok_allows():
    from app.api.v1.routes import ensure_tenant_role
    req = _req({'actor_id': 'u1', 'roles': ['admin']})
    conn = _FakeConn(fetch_results=[[{'role': 'admin'}]])

    async def _go():
        await ensure_tenant_role(req, conn, uuid4(), 'admin')

    asyncio.run(_go())


def test_ensure_tenant_role_jwt_ok_db_viewer_raises():
    from app.api.v1.routes import ensure_tenant_role
    req = _req({'actor_id': 'u1', 'roles': ['admin']})
    conn = _FakeConn(fetch_results=[[{'role': 'viewer'}]])

    async def _go():
        await ensure_tenant_role(req, conn, uuid4(), 'admin')

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_go())
    assert exc_info.value.status_code == 403


# ═══ require_tenant + tenant_id_from_request ════════════════════════════


def test_require_tenant_no_tenant_raises():
    from app.api.v1.routes import require_tenant
    req = _req()

    async def _go():
        return await require_tenant(req)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_go())
    assert exc_info.value.status_code == 400


def test_require_tenant_returns_id():
    from app.api.v1.routes import require_tenant
    tid = uuid4()
    req = _req({'tenant_id': tid})

    async def _go():
        return await require_tenant(req)

    assert asyncio.run(_go()) == tid


def test_tenant_id_from_request_no_scope_raises():
    from app.api.v1.routes import tenant_id_from_request
    req = _req()

    async def _go():
        await tenant_id_from_request(req, _FakeConn())

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_go())
    assert exc_info.value.status_code == 400


def test_tenant_id_from_request_uses_state_tenant_id():
    from app.api.v1.routes import tenant_id_from_request
    tid = uuid4()
    req = _req({'tenant_id': tid, 'actor_type': 'service'})
    conn = _FakeConn()

    async def _go():
        return await tenant_id_from_request(req, conn)

    out = asyncio.run(_go())
    assert out == tid


# ═══ user_email_from_request ════════════════════════════════════════════


def test_user_email_from_request_uses_jwt_email():
    from app.api.v1.routes import user_email_from_request
    req = _req({'email': 'user@example.com'})
    assert user_email_from_request(req) == 'user@example.com'


def test_user_email_from_request_fallback_to_synthetic():
    from app.api.v1.routes import user_email_from_request
    req = _req({'actor_id': 'auth0|abc'})  # email=None
    out = user_email_from_request(req)
    assert out.endswith('@auth.local')
