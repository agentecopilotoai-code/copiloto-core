"""Tests para `app.admin.session_store` (M70 / P0-3 audit 2026-05-27).

Cubre el InMemorySessionStore (el RedisSessionStore requiere broker live,
testeable solo en integration suite — los tests acá monkeypatchean
`redis.asyncio.Redis` si se necesitara cubrir el code path inline).
"""
from __future__ import annotations

import asyncio
import time

import pytest


# ─── InMemorySessionStore ────────────────────────────────────────────────


def test_inmemory_get_miss_returns_none():
    from app.admin.session_store import InMemorySessionStore
    store = InMemorySessionStore()
    assert asyncio.run(store.get('no-such-sid')) is None


def test_inmemory_set_then_get_returns_payload():
    from app.admin.session_store import InMemorySessionStore
    store = InMemorySessionStore()
    asyncio.run(store.set('sid-1', {'profile': {'email': 'x@y.co'}}, 3600))
    out = asyncio.run(store.get('sid-1'))
    assert out is not None
    assert out['profile']['email'] == 'x@y.co'
    # set inyecta `expires_at` automático.
    assert out['expires_at'] > time.time()


def test_inmemory_set_with_ttl_expires_on_get():
    """Lazy expiration: el siguiente get tras TTL retorna None y purga."""
    from app.admin.session_store import InMemorySessionStore
    store = InMemorySessionStore()
    asyncio.run(store.set('sid-1', {'profile': {}}, ttl_seconds=1))
    time.sleep(1.1)
    assert asyncio.run(store.get('sid-1')) is None
    assert store.size == 0  # purged


def test_inmemory_delete_returns_true_when_existed():
    from app.admin.session_store import InMemorySessionStore
    store = InMemorySessionStore()
    asyncio.run(store.set('sid-1', {'p': 1}, 60))
    assert asyncio.run(store.delete('sid-1')) is True
    assert asyncio.run(store.get('sid-1')) is None


def test_inmemory_delete_returns_false_when_missing():
    from app.admin.session_store import InMemorySessionStore
    store = InMemorySessionStore()
    assert asyncio.run(store.delete('no-such-sid')) is False


def test_inmemory_close_clears_state():
    from app.admin.session_store import InMemorySessionStore
    store = InMemorySessionStore()
    asyncio.run(store.set('sid-1', {'p': 1}, 60))
    asyncio.run(store.set('sid-2', {'p': 2}, 60))
    assert store.size == 2
    asyncio.run(store.close())
    assert store.size == 0


# ─── Factory get_session_store() ─────────────────────────────────────────


def test_factory_returns_inmemory_when_no_redis_url(monkeypatch):
    from app.admin import config, session_store
    from types import SimpleNamespace

    # Reset cached store (conftest autouse already does it, redundant).
    session_store.set_session_store_for_tests(None)
    monkeypatch.setattr(
        config, 'get_admin_settings',
        lambda: SimpleNamespace(redis_url=None, bff_session_redis_prefix='x:'),
    )
    store = session_store.get_session_store()
    assert isinstance(store, session_store.InMemorySessionStore)


def test_factory_caches_store_between_calls(monkeypatch):
    from app.admin import session_store
    session_store.set_session_store_for_tests(None)
    s1 = session_store.get_session_store()
    s2 = session_store.get_session_store()
    assert s1 is s2


def test_set_session_store_for_tests_replaces():
    from app.admin import session_store
    custom = session_store.InMemorySessionStore()
    session_store.set_session_store_for_tests(custom)
    assert session_store.get_session_store() is custom


def test_close_session_store_resets():
    from app.admin import session_store
    custom = session_store.InMemorySessionStore()
    session_store.set_session_store_for_tests(custom)
    asyncio.run(session_store.close_session_store())
    # Next call lazy-creates new.
    new = session_store.get_session_store()
    assert new is not custom


# ─── RedisSessionStore — solo error path (sin redis dep instalada) ───────


def test_redis_store_raises_if_dep_missing(monkeypatch):
    """Si el lazy import falla, el constructor levanta error claro."""
    from app.admin import session_store
    # Forzamos ImportError haciendo que el módulo no exista.
    import sys
    if 'redis' in sys.modules:
        pytest.skip('redis dep está instalada en este venv — skip negative test')
    with pytest.raises(RuntimeError, match='redis-py'):
        session_store.RedisSessionStore('redis://x', 'x:')
