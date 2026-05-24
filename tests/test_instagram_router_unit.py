"""Tests unitarios para `app/influencer/instagram_router.py`.

Cubre los 3 endpoints (oauth_start, oauth_callback, oauth_disconnect)
y los stubs `_exchange_code` + `_store_secret`. Sin HTTP — invocamos
los handlers directos con mocks (mismo patrón que test_face_variations_static).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.influencer import instagram_router as ir


def _run(coro):
    return asyncio.run(coro)


def _make_request(tenant_id, user_id=None, support_mode=False):
    return SimpleNamespace(state=SimpleNamespace(
        tenant_id=tenant_id, user_id=user_id, support_mode=support_mode,
    ))


# ── helpers privados ───────────────────────────────────────────────────────


def test_state_secret_uses_env(monkeypatch):
    monkeypatch.setenv('JWT_SECRET', 'shhh-the-secret')
    assert ir._state_secret() == 'shhh-the-secret'


def test_config_returns_default_when_missing(monkeypatch):
    monkeypatch.delenv('TEST_VAR_THAT_DOESNT_EXIST', raising=False)
    assert ir._config('TEST_VAR_THAT_DOESNT_EXIST', 'fallback') == 'fallback'


def test_require_tenant_id_returns_uuid():
    tid = uuid4()
    req = _make_request(tid)
    assert ir._require_tenant_id(req) == tid


def test_require_tenant_id_no_tenant_404():
    req = SimpleNamespace(state=SimpleNamespace(tenant_id=None))
    with pytest.raises(HTTPException) as exc:
        ir._require_tenant_id(req)
    assert exc.value.status_code == 404


def test_require_tenant_id_string_coerces_to_uuid():
    tid = uuid4()
    req = SimpleNamespace(state=SimpleNamespace(tenant_id=str(tid)))
    assert ir._require_tenant_id(req) == tid


# ── oauth_start ────────────────────────────────────────────────────────────


def test_oauth_start_persona_not_found_404(monkeypatch):
    tenant_id = uuid4()
    persona_id = uuid4()
    request = _make_request(tenant_id)
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        _run(ir.oauth_start(persona_id=persona_id, request=request, conn=conn))
    assert exc.value.status_code == 404


def test_oauth_start_no_client_id_503(monkeypatch):
    tenant_id = uuid4()
    persona_id = uuid4()
    request = _make_request(tenant_id)
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value={'id': persona_id, 'status': 'active'})
    monkeypatch.delenv('INSTAGRAM_CLIENT_ID', raising=False)
    monkeypatch.delenv('INSTAGRAM_REDIRECT_URI', raising=False)

    with pytest.raises(HTTPException) as exc:
        _run(ir.oauth_start(persona_id=persona_id, request=request, conn=conn))
    assert exc.value.status_code == 503
    assert 'not configured' in exc.value.detail


def test_oauth_start_happy_path_returns_redirect(monkeypatch):
    tenant_id = uuid4()
    persona_id = uuid4()
    request = _make_request(tenant_id)
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value={'id': persona_id, 'status': 'active'})
    monkeypatch.setenv('INSTAGRAM_CLIENT_ID', 'fake-client-id')
    monkeypatch.setenv('INSTAGRAM_REDIRECT_URI', 'https://app.example/cb')
    monkeypatch.setenv('JWT_SECRET', 'test-secret-min-16-chars')

    resp = _run(ir.oauth_start(persona_id=persona_id, request=request, conn=conn))
    assert resp.status_code == 307
    # El Location header debe apuntar al endpoint de autorize de Meta.
    location = resp.headers['location']
    assert 'fake-client-id' in location


# ── oauth_callback ─────────────────────────────────────────────────────────


def test_oauth_callback_invalid_state_403(monkeypatch):
    tenant_id = uuid4()
    persona_id = uuid4()
    request = _make_request(tenant_id, user_id=uuid4())
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)

    # State con HMAC inválido → verify_oauth_state lanza ValueError.
    with pytest.raises(HTTPException) as exc:
        _run(ir.oauth_callback(
            persona_id=persona_id, request=request,
            code='abc', state='invalid-state-blob', conn=conn,
        ))
    assert exc.value.status_code == 403


def test_oauth_callback_happy_path_persists_connection(monkeypatch):
    from app.influencer.instagram_oauth import build_oauth_state

    tenant_id = uuid4()
    persona_id = uuid4()
    user_id = uuid4()
    request = _make_request(tenant_id, user_id=user_id)
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    # Mock del INSERT/UPDATE de platform_connections — devuelve row.
    inserted = {
        'id': uuid4(), 'persona_id': persona_id, 'platform': 'instagram',
        'external_handle': None, 'status': 'connected',
        'scopes': ['instagram_basic', 'pages_show_list'],
        'expires_at': datetime.now(timezone.utc) + timedelta(days=60),
    }
    conn.fetchrow = AsyncMock(return_value=inserted)

    # Mock del exchange_code para no llamar HTTP.
    async def _fake_exchange(code):
        return {'access_token': 'fake-token', 'user_id': '12345', 'expires_in': 5184000}
    monkeypatch.setattr(ir, '_exchange_code', _fake_exchange)

    # Mock del _store_secret para no llamar DB real.
    async def _fake_store(conn, ref, val, uid):
        return None
    monkeypatch.setattr(ir, '_store_secret', _fake_store)

    # Build un state válido.
    monkeypatch.setenv('JWT_SECRET', 'state-secret-min-16-chars-here')
    state = build_oauth_state(
        persona_id=persona_id, secret='state-secret-min-16-chars-here',
    )

    resp = _run(ir.oauth_callback(
        persona_id=persona_id, request=request,
        code='auth-code-from-meta', state=state, conn=conn,
    ))
    assert resp.status == 'connected'
    assert resp.platform == 'instagram'


# ── oauth_disconnect ───────────────────────────────────────────────────────


def test_oauth_disconnect_not_found_404(monkeypatch):
    tenant_id = uuid4()
    persona_id = uuid4()
    request = _make_request(tenant_id)
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)  # nada que desconectar

    with pytest.raises(HTTPException) as exc:
        _run(ir.oauth_disconnect(persona_id=persona_id, request=request, conn=conn))
    assert exc.value.status_code == 404


def test_oauth_disconnect_happy_path(monkeypatch):
    tenant_id = uuid4()
    persona_id = uuid4()
    request = _make_request(tenant_id)
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    updated_row = {
        'id': uuid4(), 'persona_id': persona_id, 'platform': 'instagram',
        'external_handle': '@sofia', 'status': 'disconnected',
        'scopes': ['instagram_basic'], 'expires_at': None,
    }
    conn.fetchrow = AsyncMock(return_value=updated_row)

    resp = _run(ir.oauth_disconnect(
        persona_id=persona_id, request=request, conn=conn,
    ))
    assert resp.status == 'disconnected'
    assert resp.external_handle == '@sofia'


# ── stubs ──────────────────────────────────────────────────────────────────


def test_exchange_code_raises_not_implemented():
    with pytest.raises(NotImplementedError):
        _run(ir._exchange_code('any-code'))


def test_store_secret_writes_insert_on_conflict():
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    _run(ir._store_secret(
        conn, 'instagram://persona-x/access-token', 'token-1234567890', uuid4(),
    ))
    conn.execute.assert_called_once()
    args = conn.execute.call_args[0]
    # El hint debe ser los últimos 4 chars.
    assert args[2] == '7890'


def test_store_secret_short_value_hint_is_full_value():
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    _run(ir._store_secret(conn, 'ref', 'ab', None))
    args = conn.execute.call_args[0]
    assert args[2] == 'ab'
