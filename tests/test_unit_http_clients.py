"""Tests para `copiloto_core.services.http_clients` (T-3 audit#3 — coverage gap).

Antes coverage 88.9% — las líneas 112-117 (aclose() raise path) sin
test. Acá cubrimos el path donde un client lanza al cerrar."""
from __future__ import annotations

import asyncio

import pytest


def test_get_auth0_client_returns_singleton():
    from copiloto_core.services import http_clients
    http_clients._reset_for_tests()
    c1 = asyncio.run(http_clients.get_auth0_client())
    c2 = asyncio.run(http_clients.get_auth0_client())
    assert c1 is c2


def test_get_resend_client_has_base_url():
    from copiloto_core.services import http_clients
    http_clients._reset_for_tests()
    client = asyncio.run(http_clients.get_resend_client())
    # httpx URL object con base_url='https://api.resend.com'.
    assert 'resend.com' in str(client.base_url)


def test_get_core_bff_client_distinct_from_auth0():
    from copiloto_core.services import http_clients
    http_clients._reset_for_tests()
    auth0 = asyncio.run(http_clients.get_auth0_client())
    core = asyncio.run(http_clients.get_core_bff_client())
    assert auth0 is not core


def test_close_all_handles_aclose_exception(monkeypatch):
    """T-3 (audit #3) — un client que lanza en aclose() no debe abortar
    el shutdown ni los siguientes close. Cubre líneas 112-117."""
    from copiloto_core.services import http_clients
    http_clients._reset_for_tests()

    # Inyectamos 2 fakes: el primero lanza, el segundo debe cerrar OK.
    closed_marker = {'second_closed': False}

    class _Boom:
        async def aclose(self):
            raise ConnectionError('socket already broken')

    class _OK:
        async def aclose(self):
            closed_marker['second_closed'] = True

    http_clients._clients['fake-boom'] = _Boom()  # type: ignore[assignment]
    http_clients._clients['fake-ok'] = _OK()  # type: ignore[assignment]

    # No raise — el except swallow trabaja.
    asyncio.run(http_clients.close_all())

    assert closed_marker['second_closed'] is True
    assert http_clients._clients == {}


def test_close_all_with_empty_registry():
    """No-op si no hay clients — no raise."""
    from copiloto_core.services import http_clients
    http_clients._reset_for_tests()
    asyncio.run(http_clients.close_all())  # ok


def test_reset_for_tests_clears_registry():
    from copiloto_core.services import http_clients
    asyncio.run(http_clients.get_auth0_client())
    assert len(http_clients._clients) > 0
    http_clients._reset_for_tests()
    assert http_clients._clients == {}
