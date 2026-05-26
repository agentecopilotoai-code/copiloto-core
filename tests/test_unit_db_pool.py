"""M45 — cobertura del módulo `app.db.pool` (antes 32% → casi 100%).

No abre un Pool real (eso requiere Postgres). Mockea `asyncpg.create_pool`
+ los métodos de conexión para ejercitar TODO el code path: pool
config, connection context manager, set_config de tenant/support_mode,
helpers de serialización (record_to_dict, _json_safe_value), y el
dependency `get_db`.

Patrón de testing async tomado de `tests/test_audit.py`: tests sync que
envuelven coroutines en `asyncio.run(run_test())` para evitar agregar
pytest-asyncio como dep.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.db import pool as pool_module
from app.db.pool import (
    Database,
    _json_safe_value,
    get_db,
    record_to_dict,
)


# ─── _json_safe_value ──────────────────────────────────────────────────────


def test_json_safe_value_bytes():
    assert _json_safe_value(b'\xff\x00') == 'ff00'


def test_json_safe_value_dict():
    out = _json_safe_value({'k': b'\x01\x02', 'n': 1})
    assert out == {'k': '0102', 'n': 1}


def test_json_safe_value_list():
    out = _json_safe_value([b'\xab', 1, 'x'])
    assert out == ['ab', 1, 'x']


def test_json_safe_value_tuple():
    out = _json_safe_value((b'\xab', 1))
    assert out == ('ab', 1)


def test_json_safe_value_primitive_passthrough():
    assert _json_safe_value(1) == 1
    assert _json_safe_value('s') == 's'
    assert _json_safe_value(None) is None
    assert _json_safe_value(True) is True


def test_json_safe_value_nested():
    inp = {'a': [b'\x01', {'b': b'\xff'}]}
    out = _json_safe_value(inp)
    assert out == {'a': ['01', {'b': 'ff'}]}


# ─── record_to_dict ───────────────────────────────────────────────────────


def test_record_to_dict_none():
    assert record_to_dict(None) is None


def test_record_to_dict_with_dict_like():
    class FakeRecord(dict):
        pass

    rec = FakeRecord({'id': UUID('12345678-1234-1234-1234-123456789012'), 'data': b'\xab'})
    out = record_to_dict(rec)
    # UUID es opaco — _json_safe_value lo passthrough.
    assert out['id'] == UUID('12345678-1234-1234-1234-123456789012')
    assert out['data'] == 'ab'


# ─── Database.connect / close ─────────────────────────────────────────────


def test_database_connect_uses_settings(monkeypatch):
    captured = {}

    async def fake_create_pool(dsn, **kwargs):
        captured['dsn'] = dsn
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(pool_module.asyncpg, 'create_pool', fake_create_pool)
    db = Database()
    asyncio.run(db.connect('postgresql://localhost/test'))
    assert captured['dsn'] == 'postgresql://localhost/test'
    assert captured['min_size'] >= 1
    assert captured['max_size'] >= captured['min_size']
    assert captured['command_timeout'] > 0


def test_database_connect_falls_back_when_settings_fail(monkeypatch):
    """Si `get_settings()` levanta, usa defaults 1/10/30."""
    captured = {}

    async def fake_create_pool(dsn, **kwargs):
        captured.update(kwargs)
        return MagicMock()

    monkeypatch.setattr(pool_module.asyncpg, 'create_pool', fake_create_pool)
    import app.core.config as cfg

    def boom():
        raise RuntimeError('no settings')

    monkeypatch.setattr(cfg, 'get_settings', boom)
    db = Database()
    asyncio.run(db.connect('postgresql://localhost/test'))
    assert captured['min_size'] == 1
    assert captured['max_size'] == 10
    assert captured['command_timeout'] == 30.0


def test_database_close_idempotent():
    async def run_test():
        db = Database()
        # close sin pool → no-op (línea `if self.pool`).
        await db.close()
        assert db.pool is None
        # con pool → cierra y limpia.
        pool_mock = MagicMock()
        pool_mock.close = AsyncMock()
        db.pool = pool_mock
        await db.close()
        pool_mock.close.assert_awaited_once()
        assert db.pool is None

    asyncio.run(run_test())


# ─── Database.connection — el async context manager ──────────────────────


def _fake_pool_with_conn(conn_mock):
    """Builds an asyncpg-like pool whose acquire() yields conn_mock and whose
    transaction() returns a no-op async context manager."""
    pool = MagicMock()

    class AcquireCtx:
        async def __aenter__(self_inner):
            return conn_mock

        async def __aexit__(self_inner, *exc):
            return False

    pool.acquire = MagicMock(return_value=AcquireCtx())
    return pool


def test_connection_raises_when_pool_not_initialized():
    async def run_test():
        db = Database()
        db.pool = None
        with pytest.raises(RuntimeError, match='Database pool is not initialized'):
            async with db.connection():
                pass

    asyncio.run(run_test())


def test_connection_sets_tenant_and_support_mode():
    async def run_test():
        conn = AsyncMock()

        class TxCtx:
            async def __aenter__(self_inner):
                return None

            async def __aexit__(self_inner, *exc):
                return False

        conn.transaction = MagicMock(return_value=TxCtx())
        conn.execute = AsyncMock(return_value='SET')
        db = Database()
        db.pool = _fake_pool_with_conn(conn)
        tid = uuid4()
        async with db.connection(tenant_id=tid, support_mode=True) as c:
            assert c is conn
        # ejecutó SET para tenant_id + support_mode true.
        calls = conn.execute.await_args_list
        assert len(calls) == 2
        assert "set_config('app.tenant_id'" in calls[0].args[0]
        assert str(tid) == calls[0].args[1]
        assert "set_config('app.support_mode'" in calls[1].args[0]
        assert calls[1].args[1] == 'true'

    asyncio.run(run_test())


def test_connection_without_tenant_sets_support_mode_false():
    async def run_test():
        conn = AsyncMock()

        class TxCtx:
            async def __aenter__(self_inner):
                return None

            async def __aexit__(self_inner, *e):
                return False

        conn.transaction = MagicMock(return_value=TxCtx())
        conn.execute = AsyncMock()
        db = Database()
        db.pool = _fake_pool_with_conn(conn)
        async with db.connection() as _c:
            pass
        calls = conn.execute.await_args_list
        assert len(calls) == 1
        assert "support_mode" in calls[0].args[0]
        assert calls[0].args[1] == 'false'

    asyncio.run(run_test())


# ─── get_db dependency ─────────────────────────────────────────────────────


def test_get_db_yields_conn_with_state(monkeypatch):
    async def run_test():
        conn = AsyncMock()

        class TxCtx:
            async def __aenter__(self_inner):
                return None

            async def __aexit__(self_inner, *e):
                return False

        conn.transaction = MagicMock(return_value=TxCtx())
        conn.execute = AsyncMock()
        monkeypatch.setattr(pool_module.db, 'pool', _fake_pool_with_conn(conn))
        tid = uuid4()
        request = SimpleNamespace(state=SimpleNamespace(tenant_id=tid, support_mode=True))
        gen = get_db(request)
        yielded = await gen.__anext__()
        assert yielded is conn
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

    asyncio.run(run_test())


def test_get_db_defaults_when_state_empty(monkeypatch):
    async def run_test():
        conn = AsyncMock()

        class TxCtx:
            async def __aenter__(self_inner):
                return None

            async def __aexit__(self_inner, *e):
                return False

        conn.transaction = MagicMock(return_value=TxCtx())
        conn.execute = AsyncMock()
        monkeypatch.setattr(pool_module.db, 'pool', _fake_pool_with_conn(conn))
        request = SimpleNamespace(state=SimpleNamespace())
        gen = get_db(request)
        yielded = await gen.__anext__()
        assert yielded is conn
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

    asyncio.run(run_test())
