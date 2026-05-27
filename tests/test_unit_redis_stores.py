"""Tests para RedisSessionStore + RedisOAuthStateStore usando `fakeredis`
(audit #2 — gap en coverage de los paths Redis).

Antes, los tests cubrían InMemory + factory + el error path "redis no
instalado". El código real de los stores Redis quedaba sin tests
(150 LOC). Acá cubrimos:
  - get/set/delete + cache local TTL (PERF-019)
  - mark_consumed con NX (race-safe single-use)
  - fault tolerance (INT-NEW-2): Redis caído → políticas correctas
  - JSON corrupto: borra y devuelve None
"""
from __future__ import annotations

import asyncio
import time

import pytest


# ─── Fixtures ────────────────────────────────────────────────────────────


def _fake_redis_client():
    """Construye un client fake con fakeredis.asyncio (in-memory)."""
    try:
        import fakeredis.aioredis
    except ImportError:
        pytest.skip('fakeredis no instalado — skip Redis path tests')
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


def _build_redis_session_store_with_fake():
    """Crea un RedisSessionStore inyectando un fake client."""
    from collections import OrderedDict
    from app.admin.session_store import RedisSessionStore
    store = RedisSessionStore.__new__(RedisSessionStore)
    store._client = _fake_redis_client()
    store._prefix = 'test:session:'
    store._local_cache_ttl = 0.1  # corto para tests
    store._local_cache_max_entries = 2000  # PERF-NEW-1
    store._local_cache = OrderedDict()
    return store


def _build_redis_oauth_state_store_with_fake():
    from app.admin.oauth_state_store import RedisOAuthStateStore
    store = RedisOAuthStateStore.__new__(RedisOAuthStateStore)
    store._client = _fake_redis_client()
    store._prefix = 'test:oauth:'
    return store


# ─── RedisSessionStore: happy paths ──────────────────────────────────────


def test_redis_session_set_then_get():
    store = _build_redis_session_store_with_fake()
    asyncio.run(store.set('sid-1', {'profile': {'email': 'x@y.co'}}, 60))
    out = asyncio.run(store.get('sid-1'))
    assert out is not None
    assert out['profile']['email'] == 'x@y.co'


def test_redis_session_delete_existing_returns_true():
    store = _build_redis_session_store_with_fake()
    asyncio.run(store.set('sid-1', {'p': 1}, 60))
    deleted = asyncio.run(store.delete('sid-1'))
    assert deleted is True
    assert asyncio.run(store.get('sid-1')) is None


def test_redis_session_delete_missing_returns_false():
    store = _build_redis_session_store_with_fake()
    assert asyncio.run(store.delete('no-such')) is False


def test_redis_session_local_cache_hit_skips_redis():
    """PERF-019 — segundo get reusa local cache sin tocar Redis."""
    store = _build_redis_session_store_with_fake()
    asyncio.run(store.set('sid-1', {'p': 1, 'expires_at': time.time() + 60}, 60))
    first = asyncio.run(store.get('sid-1'))
    # Mutar Redis "a espaldas" del cache local — el cache local debe
    # seguir devolviendo el valor viejo hasta que el TTL caduce.
    asyncio.run(store._client.set('test:session:sid-1', '{"p":2,"expires_at":9999999999}'))
    second = asyncio.run(store.get('sid-1'))
    assert second == first  # cache hit, no refetch


def test_redis_session_set_invalidates_local_cache():
    """PERF-019 — set explícito invalida el cache para forzar refresh."""
    store = _build_redis_session_store_with_fake()
    asyncio.run(store.set('sid-1', {'v': 1}, 60))
    asyncio.run(store.get('sid-1'))  # populates cache
    asyncio.run(store.set('sid-1', {'v': 2}, 60))  # should invalidate
    out = asyncio.run(store.get('sid-1'))
    assert out['v'] == 2  # cache invalidated → fresh value


def test_redis_session_corrupted_json_returns_none_and_deletes():
    """JSON inválido en Redis → return None + auto-delete del key."""
    store = _build_redis_session_store_with_fake()
    asyncio.run(store._client.set('test:session:sid-1', 'not json{{'))
    out = asyncio.run(store.get('sid-1'))
    assert out is None
    # Confirmar que el key fue purgado.
    raw = asyncio.run(store._client.get('test:session:sid-1'))
    assert raw is None


# ─── RedisSessionStore: fault tolerance (INT-NEW-2) ──────────────────────


def test_redis_session_get_returns_none_when_redis_down(monkeypatch):
    """Redis lanza ConnectionError → get devuelve None (fail-soft)."""
    store = _build_redis_session_store_with_fake()

    async def _raise(*a, **kw):
        raise ConnectionError('redis down')

    monkeypatch.setattr(store._client, 'get', _raise)
    assert asyncio.run(store.get('any')) is None


def test_redis_session_set_raises_when_redis_down(monkeypatch):
    """Redis lanza en set → propaga RuntimeError (handler responde 503)."""
    store = _build_redis_session_store_with_fake()

    async def _raise(*a, **kw):
        raise ConnectionError('redis down')

    monkeypatch.setattr(store._client, 'set', _raise)
    with pytest.raises(RuntimeError, match='session_store_unavailable'):
        asyncio.run(store.set('sid', {}, 60))


def test_redis_session_delete_returns_false_when_redis_down(monkeypatch):
    """Redis lanza en delete → return False, no propaga (logout no debe fallar)."""
    store = _build_redis_session_store_with_fake()

    async def _raise(*a, **kw):
        raise ConnectionError('redis down')

    monkeypatch.setattr(store._client, 'delete', _raise)
    assert asyncio.run(store.delete('any')) is False


# ─── RedisOAuthStateStore ────────────────────────────────────────────────


def test_redis_oauth_mark_consumed_first_returns_true():
    store = _build_redis_oauth_state_store_with_fake()
    assert asyncio.run(store.mark_consumed('state-1', 600)) is True


def test_redis_oauth_mark_consumed_replay_returns_false():
    """SET NX — segundo intento con mismo state retorna False."""
    store = _build_redis_oauth_state_store_with_fake()
    assert asyncio.run(store.mark_consumed('state-1', 600)) is True
    assert asyncio.run(store.mark_consumed('state-1', 600)) is False


def test_redis_oauth_distinct_states_independent():
    store = _build_redis_oauth_state_store_with_fake()
    assert asyncio.run(store.mark_consumed('a', 600)) is True
    assert asyncio.run(store.mark_consumed('b', 600)) is True
    assert asyncio.run(store.mark_consumed('a', 600)) is False
    assert asyncio.run(store.mark_consumed('b', 600)) is False


def test_redis_oauth_fail_closed_when_redis_down(monkeypatch):
    """INT-NEW-2 — Redis caído → return False (fail-CLOSED rechaza state)."""
    store = _build_redis_oauth_state_store_with_fake()

    async def _raise(*a, **kw):
        raise ConnectionError('redis down')

    monkeypatch.setattr(store._client, 'set', _raise)
    # Mejor rechazar el OAuth callback que permitir replay.
    assert asyncio.run(store.mark_consumed('any', 600)) is False


# ─── close() con timeout (INT-NEW-2) ─────────────────────────────────────


def test_redis_session_close_succeeds_normally():
    store = _build_redis_session_store_with_fake()
    asyncio.run(store.close())  # no raise


def test_redis_session_close_does_not_hang_when_redis_dies(monkeypatch):
    """close() debe completar incluso si Redis no responde — usamos
    timeout de 2s en el wrapper compartido."""
    store = _build_redis_session_store_with_fake()

    async def _hang():
        await asyncio.sleep(10)  # > timeout

    monkeypatch.setattr(store._client, 'aclose', _hang)
    start = time.monotonic()
    asyncio.run(store.close())
    elapsed = time.monotonic() - start
    assert elapsed < 3.0  # debe terminar dentro del timeout (2.0)
