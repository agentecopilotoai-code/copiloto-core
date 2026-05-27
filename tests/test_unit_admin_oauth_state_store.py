"""Tests para `app.admin.oauth_state_store` (P1-10 audit 2026-05-27).

Verifica single-use enforcement del OAuth state token. RedisOAuthStateStore
no se testea acá (requiere broker live); tests cubren InMemory + factory +
integration con el callback handler en `test_unit_admin_bff_more.py`."""
from __future__ import annotations

import asyncio
import time

import pytest


# ─── InMemoryOAuthStateStore ─────────────────────────────────────────────


def test_inmemory_mark_consumed_first_returns_true():
    from app.admin.oauth_state_store import InMemoryOAuthStateStore
    store = InMemoryOAuthStateStore()
    assert asyncio.run(store.mark_consumed('state-1', 600)) is True


def test_inmemory_mark_consumed_replay_returns_false():
    """Replay attempt: el mismo state intentado 2× retorna False segunda vez."""
    from app.admin.oauth_state_store import InMemoryOAuthStateStore
    store = InMemoryOAuthStateStore()
    assert asyncio.run(store.mark_consumed('state-1', 600)) is True
    assert asyncio.run(store.mark_consumed('state-1', 600)) is False  # replay


def test_inmemory_distinct_states_independent():
    from app.admin.oauth_state_store import InMemoryOAuthStateStore
    store = InMemoryOAuthStateStore()
    assert asyncio.run(store.mark_consumed('state-a', 600)) is True
    assert asyncio.run(store.mark_consumed('state-b', 600)) is True
    # Cada uno solo se rechaza si SE repite individualmente.
    assert asyncio.run(store.mark_consumed('state-a', 600)) is False
    assert asyncio.run(store.mark_consumed('state-b', 600)) is False


def test_inmemory_expired_state_can_be_re_consumed():
    """Después del TTL, el state se purga lazy y un nuevo intento pasa.

    NO debería pasar en práctica (los states son cripto-random 32 bytes),
    pero el cleanup TTL existe para evitar memory growth ilimitado."""
    from app.admin.oauth_state_store import InMemoryOAuthStateStore
    store = InMemoryOAuthStateStore()
    asyncio.run(store.mark_consumed('state-1', 1))  # TTL 1s
    time.sleep(1.1)
    # El próximo intento triggerea cleanup interno + acepta el state.
    assert asyncio.run(store.mark_consumed('state-1', 600)) is True


def test_inmemory_close_clears_state():
    from app.admin.oauth_state_store import InMemoryOAuthStateStore
    store = InMemoryOAuthStateStore()
    asyncio.run(store.mark_consumed('a', 600))
    asyncio.run(store.mark_consumed('b', 600))
    assert store.size == 2
    asyncio.run(store.close())
    assert store.size == 0


# ─── Factory ────────────────────────────────────────────────────────────


def test_factory_returns_inmemory_when_no_redis(monkeypatch):
    from types import SimpleNamespace

    from app.admin import config, oauth_state_store
    oauth_state_store.set_oauth_state_store_for_tests(None)
    monkeypatch.setattr(
        config, 'get_admin_settings',
        lambda: SimpleNamespace(redis_url=None),
    )
    store = oauth_state_store.get_oauth_state_store()
    assert isinstance(store, oauth_state_store.InMemoryOAuthStateStore)


def test_factory_caches_singleton():
    from app.admin import oauth_state_store
    oauth_state_store.set_oauth_state_store_for_tests(None)
    s1 = oauth_state_store.get_oauth_state_store()
    s2 = oauth_state_store.get_oauth_state_store()
    assert s1 is s2


def test_redis_raises_if_dep_missing():
    import sys

    from app.admin import oauth_state_store
    if 'redis' in sys.modules:
        pytest.skip('redis dep instalada — skip negative test')
    with pytest.raises(RuntimeError, match='redis-py'):
        oauth_state_store.RedisOAuthStateStore('redis://x', 'x:')
