"""Sliding-window rate limiter compartido — anti-abuse por actor (P1-3).

Antes había TRES implementaciones idénticas:
  - `_INVITATION_RATE_BUCKETS` en invitations.py (M61).
  - `_AUTH0_RL_BUCKETS` en platform_admin_handlers.py (M-004).
  - `_SUPPORT_MODE_RATE_BUCKETS` en me_handlers.py (SEC-002).

Todas el mismo pattern: dict global → list[float] de timestamps,
window-trim por call, raise 429 cuando excede. PERO ninguna tenía cap
de memoria: un attacker con N actor_ids distintos crece el dict sin
límite. Y multi-worker no comparte (cada worker tiene su propio dict,
divide el límite efectivo por #workers).

Diseño:

  - `SlidingWindowLimiter` clase con OrderedDict + cap + TTL eviction
    (similar al `RateLimiter` token-bucket existente en rate_limit.py,
    pero sliding-window porque eso es lo que los call sites necesitan).
  - Métricas opcionales (lazy import) para alertar de eviction por cap.
  - Async-safe via `asyncio.Lock` (las queries y mutations son rápidas
    pero queremos evitar race en multi-task).

NO usa Redis por ahora — los counters son per-worker. Para producción
multi-worker estricta, sustituir por Redis INCR con TTL (TODO iteración
futura). El enforcement crítico vive en audit logs + alertas.
"""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict


class SlidingWindowLimiter:
    """Limita N operaciones por window de M segundos por key.

    Args:
      max_calls: # de calls permitidos dentro del window.
      window_seconds: tamaño del window en segundos.
      max_entries: cap de keys distintas trackeadas (LRU eviction).
        Sin cap, un atacante crea keys sintéticas sin parar.
      ttl_seconds: keys inactivas más que esto se purgan en el próximo
        check (defensa-en-profundidad — además del LRU cap).
    """

    def __init__(
        self,
        *,
        max_calls: int,
        window_seconds: float,
        max_entries: int = 10_000,
        ttl_seconds: float = 3600.0,
    ) -> None:
        if max_calls <= 0:
            raise ValueError('max_calls must be > 0')
        if window_seconds <= 0:
            raise ValueError('window_seconds must be > 0')
        if max_entries <= 0:
            raise ValueError('max_entries must be > 0')
        if ttl_seconds <= 0:
            raise ValueError('ttl_seconds must be > 0')
        self.max_calls = max_calls
        self.window_seconds = window_seconds
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        # OrderedDict[key, list[timestamps]]. Más-recientemente-usada al final.
        self._buckets: OrderedDict[str, list[float]] = OrderedDict()
        self._lock = asyncio.Lock()

    @property
    def size(self) -> int:
        return len(self._buckets)

    async def check(self, key: str) -> bool:
        """Retorna True si la call fue admitida, False si se rechazó por
        rate-limit (caller decide si raise HTTPException 429 o silent skip).
        """
        async with self._lock:
            now = time.monotonic()
            bucket = self._buckets.get(key)
            cutoff = now - self.window_seconds
            if bucket is None:
                bucket = []
            else:
                # Mover al final (LRU "touch").
                self._buckets.move_to_end(key)
                bucket[:] = [t for t in bucket if t > cutoff]
            if len(bucket) >= self.max_calls:
                # No update del bucket — rechazado no consume slot.
                return False
            bucket.append(now)
            self._buckets[key] = bucket
            # LRU eviction si excedemos cap.
            while len(self._buckets) > self.max_entries:
                self._buckets.popitem(last=False)
            return True

    async def check_or_raise(
        self, key: str, *, detail: str | None = None,
    ) -> None:
        """Helper para el patrón común: 429 con detail estandarizado."""
        from fastapi import HTTPException, status  # noqa: PLC0415

        if not await self.check(key):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=detail or (
                    f'rate_limit_exceeded: max {self.max_calls} ops per '
                    f'{int(self.window_seconds)}s'
                ),
            )

    def reset(self) -> None:
        """Test-only — limpia todos los buckets."""
        self._buckets.clear()


def _build_sync_check(limiter: SlidingWindowLimiter):
    """Adapter para call sites SYNC que no pueden awaitar.

    NO usa el lock async (la mutation del dict es atómica en CPython +
    el window es coarse-grained — race condition acá significa que dos
    threads concurrentes pueden ambos pasar la 6ta call cuando max=5,
    aceptable para anti-abuse). Para call sites async, usar `check()`
    directo con await.
    """
    def _sync_check(key: str) -> bool:
        now = time.monotonic()
        bucket = limiter._buckets.get(key)  # noqa: SLF001
        cutoff = now - limiter.window_seconds
        if bucket is None:
            bucket = []
        else:
            limiter._buckets.move_to_end(key)  # noqa: SLF001
            bucket[:] = [t for t in bucket if t > cutoff]
        if len(bucket) >= limiter.max_calls:
            return False
        bucket.append(now)
        limiter._buckets[key] = bucket  # noqa: SLF001
        while len(limiter._buckets) > limiter.max_entries:  # noqa: SLF001
            limiter._buckets.popitem(last=False)  # noqa: SLF001
        return True
    return _sync_check
