"""Single-use marker para el OAuth state del BFF (P1-10, audit 2026-05-27).

Antes: el `state_cookie` solo validaba `state == cookie.state` + freshness
(`created_at + 600s > now`). Era reusable: si un attacker captura el
callback URL antes que el browser legítimo lo procese (raro pero posible
con SameSite=lax + control del client local), puede re-ejecutar el
callback y crear una sesión paralela.

Diseño:

  - `OAuthStateStore` Protocol con `mark_consumed(state, ttl) -> bool`.
    Retorna True si SE MARCÓ (primer uso). False si ya estaba marcado
    (replay attempt). Comportamiento atómico — Redis SET NX o
    `_data.setdefault` para InMemory.
  - `InMemoryOAuthStateStore` — dict `{state: expires_at}`. Lazy cleanup.
    No multi-worker safe; usar Redis en prod.
  - `RedisOAuthStateStore` — `SET key 1 NX EX ttl` atomico.
  - Factory `get_oauth_state_store()` con `@lru_cache` decide según
    `settings.redis_url`.

Usa el MISMO Redis del session_store pero con prefix distinto para no
colisionar. Sin nueva dep ni nueva conexión.
"""
from __future__ import annotations

import time
from typing import Protocol


class OAuthStateStore(Protocol):
    """Single-use marker para state tokens del OAuth callback."""

    async def mark_consumed(self, state: str, ttl_seconds: int) -> bool:
        """Intenta marcar `state` como consumido. Retorna:
          - True si fue exitoso (primera vez que se ve este state).
          - False si ya estaba marcado (replay attempt — rechazar).
        """
        ...

    async def close(self) -> None: ...


# ─── InMemory ───────────────────────────────────────────────────────────


class InMemoryOAuthStateStore:
    """Default — dict en memoria del proceso. Multi-worker UNSAFE.

    Anti-spoof real para attack scenario; para multi-worker prod usar
    `RedisOAuthStateStore`."""

    def __init__(self) -> None:
        self._data: dict[str, float] = {}

    def _cleanup(self, now: float) -> None:
        """Purga keys expiradas — lazy, llamado en `mark_consumed`."""
        expired = [k for k, exp in self._data.items() if exp < now]
        for k in expired:
            self._data.pop(k, None)

    async def mark_consumed(self, state: str, ttl_seconds: int) -> bool:
        now = time.time()
        self._cleanup(now)
        if state in self._data:
            return False  # ya consumido — replay
        self._data[state] = now + ttl_seconds
        return True

    async def close(self) -> None:
        self._data.clear()

    @property
    def size(self) -> int:
        return len(self._data)


# ─── Redis ──────────────────────────────────────────────────────────────


class RedisOAuthStateStore:
    """Backed por Redis con `SET NX EX`. Atomic, multi-worker safe."""

    def __init__(self, url: str, prefix: str) -> None:
        try:
            from redis.asyncio import Redis  # noqa: PLC0415
        except ImportError as exc:
            raise RuntimeError(
                'P1-10 — redis-py no instalado. Agregar `redis>=5.0` o '
                'desactivar REDIS_URL para usar InMemory.'
            ) from exc
        self._client = Redis.from_url(url, decode_responses=True)
        self._prefix = prefix

    def _key(self, state: str) -> str:
        return f'{self._prefix}{state}'

    async def mark_consumed(self, state: str, ttl_seconds: int) -> bool:
        # SET con NX (only-if-not-exists) + EX (TTL). Retorna 'OK' o None.
        try:
            result = await self._client.set(
                self._key(state), '1', nx=True, ex=ttl_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            # INT-NEW-2: fail-CLOSED — si Redis cae, rechazar el state.
            # Mejor que el user re-loguee a permitir un replay potencial.
            import structlog  # noqa: PLC0415
            structlog.get_logger().error(
                'oauth_state_store.redis_failed',
                error=type(exc).__name__,
                hint='fail-closed: rejecting state to prevent replay',
            )
            return False
        return result is not None  # None = key already existed → replay

    async def close(self) -> None:
        import asyncio  # noqa: PLC0415
        try:
            await asyncio.wait_for(self._client.aclose(), timeout=2.0)
        except (Exception, asyncio.TimeoutError):  # noqa: BLE001
            pass


# ─── Factory ────────────────────────────────────────────────────────────


_store: OAuthStateStore | None = None


def get_oauth_state_store() -> OAuthStateStore:
    """Factory con fail-fast en non-local sin REDIS_URL (INT-NEW-1
    audit #2). InMemory permite replay attacks cross-worker — un OAuth
    callback consumido en worker A NO se marca en worker B y queda
    abierto a re-uso."""
    global _store
    if _store is not None:
        return _store
    from app.admin.config import get_admin_settings  # noqa: PLC0415
    settings = get_admin_settings()
    redis_url = getattr(settings, 'redis_url', None)
    app_env = getattr(settings, 'app_env', 'local')
    if redis_url:
        prefix = 'copilotoia:admin:oauth_state:'
        _store = RedisOAuthStateStore(redis_url, prefix)
    elif app_env == 'local':
        _store = InMemoryOAuthStateStore()
    else:
        raise RuntimeError(
            f'INT-NEW-1: app_env={app_env!r} requiere REDIS_URL para el '
            'OAuth state store. InMemory permite replay cross-worker — '
            'un state consumido en worker A no se marca en worker B.'
        )
    return _store


def set_oauth_state_store_for_tests(store: OAuthStateStore | None) -> None:
    global _store
    _store = store


async def close_oauth_state_store() -> None:
    global _store
    if _store is not None:
        try:
            await _store.close()
        except Exception:  # noqa: BLE001
            pass
        _store = None
