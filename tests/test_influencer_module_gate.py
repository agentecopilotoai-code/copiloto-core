"""Tests para `app/influencer/__init__.py` — el module gate."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app import influencer as inf


def _run(coro):
    return asyncio.run(coro)


def setup_function(_fn):
    inf._cache_invalidate()


def test_module_name_constant():
    assert inf.MODULE_NAME == 'influencer'


def test_cache_invalidate_clears_state():
    inf._MODULE_GATE_CACHE[('t-1', 'influencer')] = (9e99, True)
    assert ('t-1', 'influencer') in inf._MODULE_GATE_CACHE
    inf._cache_invalidate()
    assert inf._MODULE_GATE_CACHE == {}


# ── _is_module_enabled ──────────────────────────────────────────────────────


def test_is_module_enabled_row_present_true():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={'enabled': True})
    result = _run(inf._is_module_enabled(conn, 't-1', 'influencer'))
    assert result is True


def test_is_module_enabled_row_present_false():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={'enabled': False})
    result = _run(inf._is_module_enabled(conn, 't-1', 'influencer'))
    assert result is False


def test_is_module_enabled_no_row_returns_false():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    result = _run(inf._is_module_enabled(conn, 't-1', 'influencer'))
    assert result is False


# ── ensure_module_enabled ──────────────────────────────────────────────────


def test_ensure_module_enabled_no_tenant_404():
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=None))
    conn = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        _run(inf.ensure_module_enabled(request=request, conn=conn))
    assert exc.value.status_code == 404


def test_ensure_module_enabled_enabled_returns_none():
    """Cuando la BD dice enabled=true, retorna sin levantar."""
    tid = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tid))
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={'enabled': True})
    # No raises.
    result = _run(inf.ensure_module_enabled(request=request, conn=conn))
    assert result is None


def test_ensure_module_enabled_disabled_404():
    tid = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tid))
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={'enabled': False})
    with pytest.raises(HTTPException) as exc:
        _run(inf.ensure_module_enabled(request=request, conn=conn))
    assert exc.value.status_code == 404


def test_ensure_module_enabled_no_row_404():
    tid = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tid))
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        _run(inf.ensure_module_enabled(request=request, conn=conn))
    assert exc.value.status_code == 404


def test_ensure_module_enabled_cache_hit_enabled():
    """Si el cache dice enabled=true (no expirado), no llama a la BD."""
    import time
    tid = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tid))
    conn = AsyncMock()
    # Pre-popula cache con expires_at en el futuro lejano.
    inf._MODULE_GATE_CACHE[(str(tid), 'influencer')] = (
        time.monotonic() + 60, True,
    )

    result = _run(inf.ensure_module_enabled(request=request, conn=conn))
    assert result is None
    conn.fetchrow.assert_not_called()


def test_ensure_module_enabled_cache_hit_disabled_404():
    import time
    tid = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tid))
    conn = AsyncMock()
    inf._MODULE_GATE_CACHE[(str(tid), 'influencer')] = (
        time.monotonic() + 60, False,
    )

    with pytest.raises(HTTPException) as exc:
        _run(inf.ensure_module_enabled(request=request, conn=conn))
    assert exc.value.status_code == 404
    conn.fetchrow.assert_not_called()


def test_ensure_module_enabled_cache_expired_re_fetches():
    import time
    tid = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tid))
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={'enabled': True})
    # Cache entry expirado.
    inf._MODULE_GATE_CACHE[(str(tid), 'influencer')] = (
        time.monotonic() - 60, False,
    )

    result = _run(inf.ensure_module_enabled(request=request, conn=conn))
    assert result is None
    conn.fetchrow.assert_called_once()


def test_ensure_module_enabled_populates_cache():
    """Después de un fetch exitoso, el cache queda poblado."""
    tid = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tid))
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={'enabled': True})
    _run(inf.ensure_module_enabled(request=request, conn=conn))
    assert (str(tid), 'influencer') in inf._MODULE_GATE_CACHE
    expires_at, enabled = inf._MODULE_GATE_CACHE[(str(tid), 'influencer')]
    assert enabled is True
