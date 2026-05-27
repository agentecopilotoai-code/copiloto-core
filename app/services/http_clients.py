"""Singletons compartidos de `httpx.AsyncClient` por servicio externo (PERF-001).

Bug observado en audit 2026-05-27: cada handler creaba/destruía su propio
`httpx.AsyncClient(...)` por call. Eso fuerza un TLS handshake nuevo por
cada request (Auth0, Resend, JWKS), incluso para el MISMO endpoint en la
misma request. Un login del admin podía generar 5+ handshakes
distintos (auth0/token, auth0/userinfo, jwks, core/v1/me, etc.).

Diseño:

  - Un client por SERVICIO (no por endpoint). Cada servicio define su
    `base_url`, `timeout` y `limits` apropiados.
  - Clients construidos lazy en `get_*_client()` y vivos por toda la
    vida del proceso. El cleanup vive en `app.main.lifespan`.
  - Tests pueden monkeypatchear `_clients` para inyectar stubs o
    `httpx.MockTransport`.

Servicios cubiertos hoy:

  - **auth0**: Management API + /oauth/token + /userinfo + /.well-known/jwks.
    Pool reusa conn a `*.auth0.com`. Timeout 10s default.
  - **resend**: API REST en api.resend.com. Timeout 10s.
  - **core_bff**: el BFF llama al Core (host interno `api:8000`). Timeout 10s.
    Sin TLS — pero igualmente ahorra el setup de connection-pool por call.

Si necesitás un client one-off para un servicio nuevo, agregalo acá y
documentalo. Lo importante es NO crear `httpx.AsyncClient(...)` inline en
handlers nuevos — usa el singleton.
"""
from __future__ import annotations

import asyncio
from typing import Final

import httpx


# Conn pool defaults. `max_keepalive_connections` mantiene N conexiones
# vivas para reuso; `max_connections` es el techo absoluto (después se
# bloquea esperando una libre). 100/20 cubre cualquier carga razonable.
_DEFAULT_LIMITS: Final = httpx.Limits(
    max_keepalive_connections=20,
    max_connections=100,
    keepalive_expiry=30.0,
)

# Registry de clients activos. Key = nombre del servicio. Lazy-init en
# `get_*_client()`. Cleanup en `close_all()` (invocado desde lifespan).
_clients: dict[str, httpx.AsyncClient] = {}
_clients_lock = asyncio.Lock()


def _build_client(*, base_url: str | None, timeout: float) -> httpx.AsyncClient:
    """Factory canónica con defaults consistentes."""
    return httpx.AsyncClient(
        base_url=base_url or '',
        timeout=timeout,
        limits=_DEFAULT_LIMITS,
        # `http2=False` por default — la mayoría de los endpoints públicos
        # ya negocian h2 si el server lo soporta, pero h2 en httpx requiere
        # `h2` opcional dep. Mantenemos h1 explícito para portabilidad.
        http2=False,
    )


async def _get_or_create(key: str, *, base_url: str | None, timeout: float) -> httpx.AsyncClient:
    """Lazy create + cache. Threadsafe via `_clients_lock`."""
    client = _clients.get(key)
    if client is not None:
        return client
    async with _clients_lock:
        client = _clients.get(key)  # double-check despues del lock
        if client is None:
            client = _build_client(base_url=base_url, timeout=timeout)
            _clients[key] = client
    return client


async def get_auth0_client() -> httpx.AsyncClient:
    """Client para todos los endpoints Auth0 (Management API + OIDC).

    Sin `base_url` fijo porque hay 3 hostnames: el tenant Auth0 normal
    + el issuer del JWT (puede diferir si custom domain). Caller pasa
    URL absoluta.
    """
    return await _get_or_create('auth0', base_url=None, timeout=10.0)


async def get_resend_client() -> httpx.AsyncClient:
    """Client para la API de Resend (api.resend.com)."""
    return await _get_or_create(
        'resend', base_url='https://api.resend.com', timeout=10.0,
    )


async def get_core_bff_client() -> httpx.AsyncClient:
    """Client interno BFF → Core. Sin TLS (red Docker / k8s ClusterIP).

    Si en algún momento el Core se expone externamente con TLS, cambiar
    el caller para pasar URL absoluta vs depender del `base_url` aquí.
    """
    return await _get_or_create('core_bff', base_url=None, timeout=10.0)


async def close_all() -> None:
    """Cierra todos los clients abiertos. Invocar desde `app.lifespan`
    al shutdown para liberar sockets limpiamente."""
    async with _clients_lock:
        clients = list(_clients.values())
        _clients.clear()
    for client in clients:
        try:
            await client.aclose()
        except Exception as exc:  # noqa: BLE001
            # Q-4 (audit #3) — `aclose` puede fallar si socket roto. NO
            # abortar shutdown, pero loggear para diagnosticar leaks
            # de socket en producción (sin esto, lifespan completa
            # silenciosamente con conexiones colgadas).
            import structlog  # noqa: PLC0415
            structlog.get_logger().debug(
                'http_clients.aclose_failed', error=type(exc).__name__,
            )


def _reset_for_tests() -> None:
    """Test-only — limpia el registry sin awaitar (tests usan
    `httpx.MockTransport` y no necesitan cleanup graceful)."""
    _clients.clear()
