"""Tests para `app.core.identity` — helpers transversales de resolución de user_id."""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import Request
from starlette.datastructures import State

from app.core.identity import resolve_user_id, resolve_user_id_from_request


def _make_request(actor_id: str | None = None) -> Request:
    """Construye un Request mínimo con `state.actor_id` seteado."""
    scope = {
        'type': 'http',
        'method': 'GET',
        'path': '/',
        'headers': [],
        'query_string': b'',
    }
    req = Request(scope)
    req._state = State()  # noqa: SLF001 — Starlette no expone setter público
    if actor_id is not None:
        req.state.actor_id = actor_id
    return req


@pytest.mark.asyncio
class TestResolveUserId:
    async def test_actor_id_none_devuelve_none(self) -> None:
        conn = AsyncMock()
        result = await resolve_user_id(conn, None)
        assert result is None
        conn.fetchrow.assert_not_called()

    async def test_actor_id_vacio_devuelve_none(self) -> None:
        conn = AsyncMock()
        result = await resolve_user_id(conn, '')
        assert result is None
        conn.fetchrow.assert_not_called()

    async def test_actor_id_resuelve_a_uuid(self) -> None:
        user_uuid = uuid4()
        conn = AsyncMock()
        conn.fetchrow.return_value = {'id': user_uuid}
        result = await resolve_user_id(conn, 'google-oauth2|123')
        assert result == user_uuid
        # Verifica que el query usa el parámetro correcto.
        call = conn.fetchrow.call_args
        assert 'auth_subject' in call.args[0]
        assert call.args[1] == 'google-oauth2|123'

    async def test_user_inexistente_devuelve_none(self) -> None:
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        result = await resolve_user_id(conn, 'auth0|unknown')
        assert result is None


@pytest.mark.asyncio
class TestResolveUserIdFromRequest:
    async def test_lee_actor_id_y_cachea_resultado(self) -> None:
        user_uuid = uuid4()
        conn = AsyncMock()
        conn.fetchrow.return_value = {'id': user_uuid}
        req = _make_request(actor_id='google-oauth2|123')

        # Primera llamada → consulta DB.
        result1 = await resolve_user_id_from_request(req, conn)
        assert result1 == user_uuid
        assert req.state.user_id == user_uuid
        assert conn.fetchrow.await_count == 1

        # Segunda llamada → usa cache, NO consulta de nuevo.
        result2 = await resolve_user_id_from_request(req, conn)
        assert result2 == user_uuid
        assert conn.fetchrow.await_count == 1  # sigue siendo 1

    async def test_sin_actor_id_devuelve_none(self) -> None:
        conn = AsyncMock()
        req = _make_request(actor_id=None)
        result = await resolve_user_id_from_request(req, conn)
        assert result is None
        conn.fetchrow.assert_not_called()

    async def test_user_inexistente_no_cachea(self) -> None:
        # Si el lookup devuelve None, NO cacheamos — un user puede
        # registrarse después y debe resolverse en el próximo intento.
        conn = AsyncMock()
        conn.fetchrow.return_value = None
        req = _make_request(actor_id='auth0|unknown')
        result = await resolve_user_id_from_request(req, conn)
        assert result is None
        assert not hasattr(req.state, 'user_id') or req.state.user_id is None
