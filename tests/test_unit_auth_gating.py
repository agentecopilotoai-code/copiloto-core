"""Tests para `copiloto_core.auth.gating` (Fase 4) — Depends
`require_module` y `require_capability`.

Cubre:
- Factory inputs (raise para invalid args).
- Resolución exitosa (gate pasa).
- Rechazos 401/403 con detail estructurado.
- Cache hit + invalidación.
- Fail-closed cuando la DB falla → 503.
"""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from copiloto_core.auth.gating import (
    _GATE_CACHE_TTL_SECONDS,
    _capability_cache,
    _module_gate_cache,
    _reset_gate_caches,
    invalidate_gate_caches,
    require_capability,
    require_module,
)


@pytest.fixture(autouse=True)
def _clean_caches():
    _reset_gate_caches()
    yield
    _reset_gate_caches()


def _make_request(*, tenant_id=None, actor_id=None):
    return SimpleNamespace(state=SimpleNamespace(
        tenant_id=tenant_id, actor_id=actor_id,
    ))


def _mock_db_conn_context(fetchrow_result):
    """Devuelve un mock context manager que entrega un conn con
    fetchrow mockeado."""

    class _MockConn:
        async def fetchrow(self, sql, *args):
            return fetchrow_result

    class _MockCtx:
        async def __aenter__(self):
            return _MockConn()

        async def __aexit__(self, *exc):
            return None

    class _MockDb:
        def connection(self, **_kwargs):
            return _MockCtx()

    return _MockDb()


# ─── factory validation ──────────────────────────────────────────────────


def test_require_module_empty_code_raises():
    with pytest.raises(ValueError):
        require_module('')


def test_require_module_non_str_code_raises():
    with pytest.raises(ValueError):
        require_module(None)  # type: ignore[arg-type]


def test_require_capability_no_colon_raises():
    with pytest.raises(ValueError, match='formato'):
        require_capability('foo')


def test_require_capability_non_str_raises():
    with pytest.raises(ValueError):
        require_capability(None)  # type: ignore[arg-type]


# ─── require_module ──────────────────────────────────────────────────────


def test_require_module_no_tenant_raises_403():
    gate = require_module('mi_modulo')
    req = _make_request(tenant_id=None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(gate(req))
    assert exc.value.status_code == 403
    assert exc.value.detail['error'] == 'tenant_required'


def test_require_module_disabled_raises_403(monkeypatch):
    gate = require_module('mi_modulo')
    req = _make_request(tenant_id='t1')
    monkeypatch.setattr(
        'copiloto_core.auth.gating.db',
        _mock_db_conn_context(None),  # row None = no enabled
        raising=False,
    )
    with patch('copiloto_core.db.pool.db', _mock_db_conn_context(None)):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(gate(req))
        assert exc.value.status_code == 403
        assert exc.value.detail['error'] == 'module_not_enabled'
        assert exc.value.detail['module'] == 'mi_modulo'


def test_require_module_enabled_passes():
    gate = require_module('mi_modulo')
    req = _make_request(tenant_id='t1')
    with patch('copiloto_core.db.pool.db',
               _mock_db_conn_context({'enabled': True})):
        # No raise = OK
        asyncio.run(gate(req))


def test_require_module_db_failure_raises_503():
    gate = require_module('mi_modulo')
    req = _make_request(tenant_id='t1')

    class _BrokenDb:
        def connection(self, **_kwargs):
            class _Ctx:
                async def __aenter__(self):
                    raise RuntimeError('db connection refused')
                async def __aexit__(self, *exc):
                    return None
            return _Ctx()

    with patch('copiloto_core.db.pool.db', _BrokenDb()):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(gate(req))
        assert exc.value.status_code == 503
        assert exc.value.detail['error'] == 'module_check_failed'


# ─── require_module cache ────────────────────────────────────────────────


def test_module_gate_cache_hit_avoids_second_query():
    """Una vez resuelto, el segundo call NO debe pegar a la DB."""
    gate = require_module('mi_modulo')
    req = _make_request(tenant_id='t1')

    query_count = {'n': 0}

    class _CountingDb:
        def connection(self, **_kwargs):
            class _Conn:
                async def fetchrow(self_inner, sql, *args):
                    query_count['n'] += 1
                    return {'enabled': True}
            class _Ctx:
                async def __aenter__(self_inner):
                    return _Conn()
                async def __aexit__(self_inner, *exc):
                    return None
            return _Ctx()

    with patch('copiloto_core.db.pool.db', _CountingDb()):
        asyncio.run(gate(req))
        asyncio.run(gate(req))
        asyncio.run(gate(req))
    assert query_count['n'] == 1, 'cache no funcionó'


def test_module_gate_cache_expires_after_ttl(monkeypatch):
    """Después de TTL, se vuelve a consultar la DB."""
    gate = require_module('mi_modulo')
    req = _make_request(tenant_id='t1')

    query_count = {'n': 0}

    class _CountingDb:
        def connection(self, **_kwargs):
            class _Conn:
                async def fetchrow(self_inner, sql, *args):
                    query_count['n'] += 1
                    return {'enabled': True}
            class _Ctx:
                async def __aenter__(self_inner):
                    return _Conn()
                async def __aexit__(self_inner, *exc):
                    return None
            return _Ctx()

    with patch('copiloto_core.db.pool.db', _CountingDb()):
        asyncio.run(gate(req))
        # Forzar expiración: avanzar monotonic + TTL.
        for k in list(_module_gate_cache.keys()):
            exp, val = _module_gate_cache[k]
            _module_gate_cache[k] = (time.monotonic() - 1, val)
        asyncio.run(gate(req))
    assert query_count['n'] == 2


def test_invalidate_clears_module_cache():
    _module_gate_cache[('t1', 'm1')] = (time.monotonic() + 100, True)
    invalidate_gate_caches()
    assert len(_module_gate_cache) == 0


# ─── require_capability ──────────────────────────────────────────────────


def test_require_capability_no_actor_raises_401():
    gate = require_capability('mi_modulo:items:read')
    req = _make_request(actor_id=None)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(gate(req))
    assert exc.value.status_code == 401
    assert exc.value.detail['error'] == 'actor_required'


def test_require_capability_service_actor_bypasses_rbac():
    """`service:` actors no pasan por RBAC — el service token ya validó."""
    gate = require_capability('mi_modulo:items:read')
    req = _make_request(actor_id='service:worker')
    # No mock de DB — si llegara a consultar, fallaría.
    asyncio.run(gate(req))


def test_require_capability_granted_passes():
    gate = require_capability('mi_modulo:items:read')
    req = _make_request(actor_id='auth0|u1')
    with patch('copiloto_core.db.pool.db',
               _mock_db_conn_context({'granted': True})):
        asyncio.run(gate(req))


def test_require_capability_denied_raises_403():
    gate = require_capability('mi_modulo:items:write')
    req = _make_request(actor_id='auth0|u1')
    with patch('copiloto_core.db.pool.db',
               _mock_db_conn_context({'granted': False})):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(gate(req))
        assert exc.value.status_code == 403
        assert exc.value.detail['error'] == 'capability_required'
        assert exc.value.detail['capability'] == 'mi_modulo:items:write'


def test_require_capability_db_failure_raises_503():
    gate = require_capability('mi_modulo:items:read')
    req = _make_request(actor_id='auth0|u1')

    class _BrokenDb:
        def connection(self, **_kwargs):
            class _Ctx:
                async def __aenter__(self):
                    raise RuntimeError('db down')
                async def __aexit__(self, *exc):
                    return None
            return _Ctx()

    with patch('copiloto_core.db.pool.db', _BrokenDb()):
        with pytest.raises(HTTPException) as exc:
            asyncio.run(gate(req))
        assert exc.value.status_code == 503
        assert exc.value.detail['error'] == 'capability_check_failed'


def test_capability_cache_hit_avoids_second_query():
    gate = require_capability('mi_modulo:items:read')
    req = _make_request(actor_id='auth0|u1')

    query_count = {'n': 0}

    class _CountingDb:
        def connection(self, **_kwargs):
            class _Conn:
                async def fetchrow(self_inner, sql, *args):
                    query_count['n'] += 1
                    return {'granted': True}
            class _Ctx:
                async def __aenter__(self_inner):
                    return _Conn()
                async def __aexit__(self_inner, *exc):
                    return None
            return _Ctx()

    with patch('copiloto_core.db.pool.db', _CountingDb()):
        asyncio.run(gate(req))
        asyncio.run(gate(req))
    assert query_count['n'] == 1


def test_invalidate_clears_capability_cache():
    _capability_cache[('a', 'b:c')] = (time.monotonic() + 100, True)
    invalidate_gate_caches()
    assert len(_capability_cache) == 0
