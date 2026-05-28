"""Helpers compartidos entre `session_store` y `oauth_state_store`
(QUAL audit #2 — dedupe mínimo).

Antes había duplicación en:
  - Lazy import de `redis.asyncio.Redis` con el mismo error message.
  - `close()` con `asyncio.wait_for(..., timeout=2.0)` para no
    bloquear shutdown si Redis está down.

Este módulo NO impone una clase base — los stores mantienen sus
interfaces y métodos especializados. Solo extrae los 2 fragmentos
mecánicos que SI estaban literalmente duplicados.

Si en el futuro agregás un 3er store Redis (rate-limit distribuido,
cache de JWKS, etc.), reusa estos helpers en lugar de copy-paste.
"""
from __future__ import annotations

import asyncio
from typing import Any


def lazy_redis_import() -> Any:
    """Importa `redis.asyncio.Redis` con mensaje de error claro si la dep
    no está instalada. Returns la clase para que el caller la instancie.

    Lazy: solo se ejecuta cuando el store concreto se construye
    (no en import del módulo) — instalaciones sin REDIS_URL no necesitan
    la dep instalada.
    """
    try:
        from redis.asyncio import Redis  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            'redis-py no instalado. Agregar `redis>=5.0` a dependencies '
            'o desactivar REDIS_URL para usar el InMemory store.'
        ) from exc
    return Redis


async def close_redis_client_with_timeout(
    client: Any, *, timeout: float = 2.0,
) -> None:
    """Cierra un Redis client con timeout para no bloquear el lifespan
    si el broker está muerto (INT-NEW-2 fix).

    Swallow de excepciones — el shutdown debe completar siempre. Para
    debug, el caller puede envolver en un try/except si necesita logear.
    """
    try:
        await asyncio.wait_for(client.aclose(), timeout=timeout)
    except (Exception, asyncio.TimeoutError):  # noqa: BLE001
        pass
