"""More tests for `app/core/security.py` covering Auth0 JWKS fetch + auth paths."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from time import monotonic

import pytest
from fastapi import HTTPException


# ═══ _fetch_auth0_jwks (cache + http) ════════════════════════════════════


def test_fetch_auth0_jwks_uses_cache():
    """When cached entry is fresh, returns it without hitting the network."""
    from app.core import security

    issuer = 'https://tenant.auth0.com/'
    fresh_jwks = {'keys': [{'kid': 'k1', 'kty': 'RSA'}]}
    security._jwks_cache[issuer] = (monotonic() + 1000, fresh_jwks)

    async def _go():
        return await security._fetch_auth0_jwks('tenant.auth0.com', 300)

    out = asyncio.run(_go())
    assert out == fresh_jwks

    security.clear_jwks_cache()


def test_fetch_auth0_jwks_fetches_when_empty(monkeypatch):
    """When cache empty, hits the network and updates cache."""
    from app.core import security
    security.clear_jwks_cache()

    fresh_jwks = {'keys': [{'kid': 'k2', 'kty': 'RSA'}]}

    class _FakeResponse:
        def json(self):
            return fresh_jwks
        def raise_for_status(self):
            pass

    class _FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *exc):
            return None
        async def get(self, url):
            return _FakeResponse()

    monkeypatch.setattr(security.httpx, 'AsyncClient', _FakeAsyncClient)

    async def _go():
        return await security._fetch_auth0_jwks('tenant.auth0.com', 300)

    out = asyncio.run(_go())
    assert out == fresh_jwks
    assert 'https://tenant.auth0.com/' in security._jwks_cache
    security.clear_jwks_cache()


# ═══ _enforce_session_not_revoked ══════════════════════════════════════


def test_enforce_session_not_revoked_no_pool_skips():
    """If db.pool is None, the check fails-open (returns without raising)."""
    from app.core import security

    async def _go():
        await security._enforce_session_not_revoked('any-session-id')

    asyncio.run(_go())  # no raise


def test_enforce_session_not_revoked_raises_when_revoked():
    """If the row has revoked_at set, raises 401."""
    from app.core import security
    from datetime import UTC, datetime

    class _FakeConn:
        async def fetchrow(self, sql, *args):
            return {'revoked_at': datetime.now(UTC)}

    class _FakePool:
        def acquire(self):
            return self
        async def __aenter__(self):
            return _FakeConn()
        async def __aexit__(self, *exc):
            return None

    class _FakeDb:
        pool = _FakePool()

    import app.db.pool
    original_db = app.db.pool.db
    app.db.pool.db = _FakeDb()
    try:
        async def _go():
            await security._enforce_session_not_revoked('revoked-session')

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(_go())
        assert exc_info.value.status_code == 401
    finally:
        app.db.pool.db = original_db


def test_enforce_session_not_revoked_fail_open_on_exception():
    """If the DB query throws, fail-open (no raise)."""
    from app.core import security

    class _BrokenConn:
        async def fetchrow(self, sql, *args):
            raise RuntimeError('db down')

    class _FakePool:
        def acquire(self):
            return self
        async def __aenter__(self):
            return _BrokenConn()
        async def __aexit__(self, *exc):
            return None

    class _FakeDb:
        pool = _FakePool()

    import app.db.pool
    original_db = app.db.pool.db
    app.db.pool.db = _FakeDb()
    try:
        async def _go():
            await security._enforce_session_not_revoked('any-id')

        asyncio.run(_go())  # no raise
    finally:
        app.db.pool.db = original_db


def test_enforce_session_not_revoked_passes_when_active():
    """When the row exists with revoked_at=None, passes silently."""
    from app.core import security

    class _FakeConn:
        async def fetchrow(self, sql, *args):
            return {'revoked_at': None}

    class _FakePool:
        def acquire(self):
            return self
        async def __aenter__(self):
            return _FakeConn()
        async def __aexit__(self, *exc):
            return None

    class _FakeDb:
        pool = _FakePool()

    import app.db.pool
    original_db = app.db.pool.db
    app.db.pool.db = _FakeDb()
    try:
        async def _go():
            await security._enforce_session_not_revoked('active-session')

        asyncio.run(_go())  # no raise
    finally:
        app.db.pool.db = original_db


# ═══ authenticate_request edge cases ═════════════════════════════════════


def test_authenticate_request_no_auth_with_x_tenant_id_raises():
    """X-Tenant-Id without Authorization → 401."""
    from app.core.security import authenticate_request
    from uuid import uuid4

    class _Req:
        def __init__(self):
            class _State: pass
            self.state = _State()
            self.cookies = {}

    async def _go():
        await authenticate_request(_Req(), authorization=None, x_tenant_id=uuid4())

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_go())
    assert exc_info.value.status_code == 401


def test_authenticate_request_invalid_bearer_scheme():
    from app.core.security import authenticate_request

    class _Req:
        def __init__(self):
            class _State: pass
            self.state = _State()
            self.cookies = {}

    async def _go():
        await authenticate_request(_Req(), authorization='Basic abc', x_tenant_id=None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_go())
    assert exc_info.value.status_code == 401


def test_authenticate_request_bearer_no_token():
    from app.core.security import authenticate_request

    class _Req:
        def __init__(self):
            class _State: pass
            self.state = _State()
            self.cookies = {}

    async def _go():
        await authenticate_request(_Req(), authorization='Bearer ', x_tenant_id=None)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_go())
    assert exc_info.value.status_code == 401


def test_authenticate_request_anonymous_pass():
    """No auth, no X-Tenant-Id → anonymous (no raise)."""
    from app.core.security import authenticate_request

    class _Req:
        def __init__(self):
            class _State: pass
            self.state = _State()
            self.cookies = {}

    request = _Req()

    async def _go():
        await authenticate_request(request, authorization=None, x_tenant_id=None)

    asyncio.run(_go())
    assert request.state.actor_type == 'anonymous'
