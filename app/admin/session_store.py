"""Session store abstracto para el BFF admin (P0-3, audit 2026-05-27).

Antes de M70, `_sessions = {}` era un dict in-memory del proceso uvicorn.
Eso rompía en cuanto se escalaba a multi-worker (gunicorn -w N): un user
logueado en worker 1 con request siguiente en worker 2 → cookie válida +
sesión no encontrada → 401 "session_expired" silencioso, browser
re-iniciaba flow OAuth, frustrante.

Diseño:

  - Protocol `SessionStore` con `get/set/delete` async.
  - `InMemorySessionStore` — equivalente al `_sessions = {}` viejo.
    Default cuando `redis_url` no está configurado. OK para single-process
    (dev local, tests). Mantiene `_data` público para que tests del
    callback puedan inyectar sesiones directo (back-compat).
  - `RedisSessionStore` — serializa el payload a JSON, persiste con TTL.
    Lazy import del paquete `redis` para no romper instalaciones que
    todavía no agregaron la dep.
  - Factory `get_session_store()` con `@lru_cache` decide según settings.

Lifecycle:
  - El cleanup se hace via `close_session_store()` invocado en
    `app.admin.main` lifespan (futuro) o vía testfixture.

NO usar `pickle`. Solo JSON. Si en el futuro se quieren guardar datetime
o UUID, agregar serializers explícitos.
"""
from __future__ import annotations

import json
import time
from typing import Any, Protocol


class SessionStore(Protocol):
    """Interfaz mínima de un session store del BFF.

    Todas las operaciones son async para uniformidad — el InMemory store
    no necesita asyncio por dentro, pero el contrato es async para que
    Redis (network IO) sea drop-in replacement."""

    async def get(self, sid: str) -> dict[str, Any] | None: ...

    async def set(
        self, sid: str, payload: dict[str, Any], ttl_seconds: int,
    ) -> None: ...

    async def delete(self, sid: str) -> bool:
        """Retorna True si la sesión existía (útil para audit/logs)."""
        ...

    async def close(self) -> None:
        """Cleanup graceful (cerrar conn Redis, vaciar dict, etc.)."""
        ...


# ─── InMemorySessionStore ────────────────────────────────────────────────


class InMemorySessionStore:
    """Default store — dict de Python en memoria del proceso.

    Mantiene una bandera `expires_at` en cada payload + chequea expiry
    on-read (lazy expiration; no hay sweep proactivo, pero las entradas
    expiradas se purgan al primer `get` que las encuentre).

    NO es multi-worker safe. Para producción, configurar `REDIS_URL` +
    usar `RedisSessionStore`."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Any]] = {}

    async def get(self, sid: str) -> dict[str, Any] | None:
        entry = self._data.get(sid)
        if entry is None:
            return None
        if entry.get('expires_at', 0) < time.time():
            # Lazy expiration.
            self._data.pop(sid, None)
            return None
        return entry

    async def set(
        self, sid: str, payload: dict[str, Any], ttl_seconds: int,
    ) -> None:
        # `expires_at` queda DENTRO del payload — el `_active_session_id`
        # legacy del BFF lo lee directo de ahí.
        payload_with_exp = dict(payload)
        payload_with_exp['expires_at'] = time.time() + ttl_seconds
        self._data[sid] = payload_with_exp

    async def delete(self, sid: str) -> bool:
        return self._data.pop(sid, None) is not None

    async def close(self) -> None:
        self._data.clear()

    # Test-only: acceso directo al dict subyacente. NO usar desde código
    # de producción — usá `get/set/delete`.
    @property
    def _raw(self) -> dict[str, dict[str, Any]]:
        return self._data

    @property
    def size(self) -> int:
        return len(self._data)


# ─── RedisSessionStore ──────────────────────────────────────────────────


class RedisSessionStore:
    """Backed por Redis. Multi-worker safe.

    Encoding: JSON UTF-8. Las keys incluyen un prefijo configurable
    (`bff_session_redis_prefix`) para evitar colisión con otros usos
    del mismo Redis. TTL se setea via Redis `EX` — el server purga
    automáticamente.

    Connection pooling: la lib `redis.asyncio` mantiene un pool interno
    por cliente. Un singleton de `RedisSessionStore` reutiliza conn.
    """

    def __init__(self, url: str, prefix: str) -> None:
        # Lazy import para no romper instalaciones sin redis dep.
        try:
            from redis.asyncio import Redis  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                'P0-3 — redis-py no instalado. Agregar `redis>=5.0` a '
                'dependencies o desactivar REDIS_URL para usar InMemory.'
            ) from exc
        self._client = Redis.from_url(url, decode_responses=True)
        self._prefix = prefix

    def _key(self, sid: str) -> str:
        return f'{self._prefix}{sid}'

    async def get(self, sid: str) -> dict[str, Any] | None:
        raw = await self._client.get(self._key(sid))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # Sesión corrupta (probable: bug viejo escribió pickle/binary
            # con otro prefijo). Borrar para que el user re-loguee.
            await self._client.delete(self._key(sid))
            return None

    async def set(
        self, sid: str, payload: dict[str, Any], ttl_seconds: int,
    ) -> None:
        payload_with_exp = dict(payload)
        # `expires_at` queda DENTRO del payload por consistencia con el
        # InMemory store (algunos call sites legacy lo leen). El TTL
        # real en Redis lo enforcea el server.
        payload_with_exp['expires_at'] = time.time() + ttl_seconds
        await self._client.set(
            self._key(sid),
            json.dumps(payload_with_exp),
            ex=ttl_seconds,
        )

    async def delete(self, sid: str) -> bool:
        deleted = await self._client.delete(self._key(sid))
        return bool(deleted)

    async def close(self) -> None:
        await self._client.aclose()


# ─── Factory ────────────────────────────────────────────────────────────


_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    """Devuelve el store activo. Lazy-init en primer call.

    Decisión:
      - Si `redis_url` está seteado → `RedisSessionStore`.
      - Si no → `InMemorySessionStore`.

    Para tests / scripts standalone, usar `set_session_store_for_tests()`
    para inyectar una implementación específica."""
    global _store
    if _store is not None:
        return _store
    from app.admin.config import get_admin_settings  # noqa: PLC0415
    settings = get_admin_settings()
    redis_url = getattr(settings, 'redis_url', None)
    if redis_url:
        prefix = getattr(
            settings, 'bff_session_redis_prefix', 'copilotoia:admin:session:',
        )
        _store = RedisSessionStore(redis_url, prefix)
    else:
        _store = InMemorySessionStore()
    return _store


def set_session_store_for_tests(store: SessionStore | None) -> None:
    """Test-only — reemplaza el store activo. Pasar `None` resetea."""
    global _store
    _store = store


async def close_session_store() -> None:
    """Cierra el store activo (cleanup del lifespan)."""
    global _store
    if _store is not None:
        try:
            await _store.close()
        except Exception:  # noqa: BLE001
            pass
        _store = None
