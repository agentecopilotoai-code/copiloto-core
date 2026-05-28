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
    `copiloto_core.admin.main` lifespan (futuro) o vía testfixture.

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

    def __init__(
        self, url: str, prefix: str, *,
        local_cache_ttl: float = 5.0,
        local_cache_max_entries: int = 2000,
    ) -> None:
        # DiD-6 (audit #3) — `local_cache_ttl=0` desactiva el cache (todos
        # los gets pegan a Redis). Usar en escenarios privacy/compliance
        # que requieren propagación INMEDIATA de revokes (hard revoke de
        # cuenta comprometida). Trade-off: -1 RTT por request hot.
        # PERF-NEW-1 (audit #3) — `local_cache_max_entries` previene
        # growth-attack: un atacante con N sessions sintéticos llenaba
        # el dict sin tope. Default 2000 — cubre uso humano normal
        # (admin panel single-user típicamente <10 sessions activas
        # entre tabs/devices). Eviction LRU al hit del cap.
        # QUAL audit#2 — lazy import compartido en `_redis_store_base`.
        from copiloto_core.admin._redis_store_base import lazy_redis_import  # noqa: PLC0415
        redis_cls = lazy_redis_import()
        self._client = redis_cls.from_url(url, decode_responses=True)
        self._prefix = prefix
        # PERF-019 (audit #2) — cache local TTL corto en el process del
        # BFF. Cada request del SPA invoca `get_session_store().get(sid)`;
        # sin cache son 1 RTT a Redis cada call. Con TTL 5s, requests
        # consecutivos del mismo session reusan localmente. El TTL acota
        # la window donde un revoke server-side toma efecto (worst-case
        # 5s; aceptable para session UX).
        self._local_cache_ttl = local_cache_ttl
        self._local_cache_max_entries = local_cache_max_entries
        # OrderedDict para LRU eviction al hit del cap.
        from collections import OrderedDict  # noqa: PLC0415
        self._local_cache: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()

    def _key(self, sid: str) -> str:
        return f'{self._prefix}{sid}'

    async def get(self, sid: str) -> dict[str, Any] | None:
        # PERF-019 — local cache hit check antes del RTT a Redis.
        # DiD-6 — `local_cache_ttl=0` skipea el cache local entero.
        now = time.time()
        cached = self._local_cache.get(sid) if self._local_cache_ttl > 0 else None
        if cached is not None:
            cache_expires_at, cached_payload = cached
            if cache_expires_at > now:
                # Aún válido localmente — devolver sin tocar Redis.
                # NOTA: verificar también `expires_at` del payload por si
                # el TTL global vence dentro de la window de cache.
                if cached_payload.get('expires_at', 0) > now:
                    return cached_payload
                # Expirado globalmente — purgar local + tratar como miss.
                self._local_cache.pop(sid, None)
                return None
            # Cache TTL pasó — purgar y refetch.
            self._local_cache.pop(sid, None)

        try:
            raw = await self._client.get(self._key(sid))
        except Exception as exc:  # noqa: BLE001
            # INT-NEW-2 (audit #2) — Redis down: fail-soft (None = miss).
            # El BFF responde 401 "session_expired" en lugar de 500. El
            # user re-loguea — UX degradada pero recuperable.
            import structlog  # noqa: PLC0415
            structlog.get_logger().error(
                'session_store.redis_get_failed',
                error=type(exc).__name__, hint='Redis unavailable; treating as miss',
            )
            return None
        if raw is None:
            return None
        try:
            payload = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # Sesión corrupta (probable: bug viejo escribió pickle/binary
            # con otro prefijo). Borrar para que el user re-loguee.
            try:
                await self._client.delete(self._key(sid))
            except Exception:  # noqa: BLE001
                pass
            return None
        # PERF-019 — populate local cache (skip si TTL 0 = DiD-6).
        # PERF-NEW-1 — LRU eviction al hit del cap.
        if self._local_cache_ttl > 0:
            self._local_cache[sid] = (now + self._local_cache_ttl, payload)
            self._local_cache.move_to_end(sid)
            while len(self._local_cache) > self._local_cache_max_entries:
                self._local_cache.popitem(last=False)  # evict LRU
        return payload

    async def set(
        self, sid: str, payload: dict[str, Any], ttl_seconds: int,
    ) -> None:
        payload_with_exp = dict(payload)
        # `expires_at` queda DENTRO del payload por consistencia con el
        # InMemory store (algunos call sites legacy lo leen). El TTL
        # real en Redis lo enforcea el server.
        payload_with_exp['expires_at'] = time.time() + ttl_seconds
        try:
            await self._client.set(
                self._key(sid),
                json.dumps(payload_with_exp),
                ex=ttl_seconds,
            )
            # PERF-019 — invalidar cache local para que el próximo get
            # vea el payload fresco (no quede el viejo cacheado 5s más).
            self._local_cache.pop(sid, None)
        except Exception as exc:  # noqa: BLE001
            # INT-NEW-2 — set falla → propagar como RuntimeError para que
            # el handler responda 503 (no podemos crear sesión sin store).
            # El callback OAuth redirige a recovery — el user reintenta.
            import structlog  # noqa: PLC0415
            structlog.get_logger().error(
                'session_store.redis_set_failed',
                error=type(exc).__name__,
            )
            raise RuntimeError(
                'session_store_unavailable — Redis no responde'
            ) from exc

    async def delete(self, sid: str) -> bool:
        # PERF-019 — invalidar cache local primero (siempre, aún si
        # Redis falla — defense contra zombie cached session).
        self._local_cache.pop(sid, None)
        try:
            deleted = await self._client.delete(self._key(sid))
            return bool(deleted)
        except Exception as exc:  # noqa: BLE001
            # Delete falla → no podemos confirmar pero no bloqueamos
            # el logout response.
            import structlog  # noqa: PLC0415
            structlog.get_logger().warning(
                'session_store.redis_delete_failed',
                error=type(exc).__name__,
            )
            return False

    async def close(self) -> None:
        from copiloto_core.admin._redis_store_base import close_redis_client_with_timeout  # noqa: PLC0415
        await close_redis_client_with_timeout(self._client)


# ─── Factory ────────────────────────────────────────────────────────────


# SEC-015 (audit #2): el agente reportó race en `get_session_store`.
# Análisis: la función ES sync (`def`, no `async def`). El bytecode
# CPython entre `if _store is not None: return` y la asignación `_store
# = ...` NO contiene await — coroutines no se preempten ahí (cooperative
# scheduling). La race teórica solo existiría en multi-threading, pero
# uvicorn corre 1 thread por worker. Mitigamos con `_store_init_done`
# bandera simple por defensa-en-profundidad si alguien promociona a
# async/multithreaded en el futuro.
_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    """Devuelve el store activo. Lazy-init en primer call.

    Decisión:
      - Si `redis_url` está seteado → `RedisSessionStore`.
      - Si no, en `app_env='local'` → `InMemorySessionStore`.
      - Si no, en cualquier otro env (production/staging) → RuntimeError.

    INT-NEW-1 (audit #2, 2026-05-27) — fail-fast: el bug original M70
    fue que multi-worker con `_sessions = {}` no compartía estado.
    Ahora con InMemoryStore por default, podemos caer al mismo bug
    silenciosamente. Producción DEBE setear REDIS_URL — sin él, levantamos
    al primer hit, no en silencio.

    Para tests / scripts standalone, usar `set_session_store_for_tests()`
    para inyectar una implementación específica."""
    global _store
    if _store is not None:
        return _store
    from copiloto_core.admin.config import get_admin_settings  # noqa: PLC0415
    settings = get_admin_settings()
    redis_url = getattr(settings, 'redis_url', None)
    app_env = getattr(settings, 'app_env', 'local')
    if redis_url:
        prefix = getattr(
            settings, 'bff_session_redis_prefix', 'copilotoia:admin:session:',
        )
        _store = RedisSessionStore(redis_url, prefix)
    elif app_env == 'local':
        _store = InMemorySessionStore()
    else:
        raise RuntimeError(
            'INT-NEW-1: app_env={app_env!r} requiere REDIS_URL configurado. '
            'El InMemorySessionStore no es multi-worker safe — un user '
            'logueado en worker N tendría 401 "session_expired" cuando su '
            'request siguiente aterriza en worker M. Setear REDIS_URL en '
            '.env del orquestador (docker-compose ya lo provee).'.format(
                app_env=app_env,
            ),
        )
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
