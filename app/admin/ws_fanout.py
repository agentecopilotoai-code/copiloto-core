"""LISTEN/NOTIFY fanout for the admin conversation stream WebSocket.

AUDIT-47 / BUG-50 (2026-05-18) — Pool exhaustion fix.

Previous design: every active WebSocket subscriber acquired a connection
from the asyncpg pool and held it for the entire socket lifetime to
``LISTEN tenant_operations_events``. With `db_pool_max_size` defaulted to
10 and zero coordination across sockets, any malicious or buggy client
opening 10 simultaneous tabs (or browsers) could exhaust the pool and
take down the whole API for every other tenant in the fleet.

New design:
    * A single process-wide ``_PubSubFanout`` owns ONE pool connection.
    * The connection does ``LISTEN tenant_operations_events`` once.
    * When an event arrives, the fanout splits it across all in-process
      subscribers whose `tenant_id` matches.
    * The connection is opened lazily on the first subscriber and closed
      automatically when the last subscriber disconnects.

The fanout is keyed by ``str(tenant_id)`` to skip a UUID parse on every
notification (the payload arrives as a plain string from Postgres).
Each subscriber gets its own ``asyncio.Queue`` of size 100; if the
queue is full we drop the oldest entry (same shedding policy the original
endpoint used) so a slow socket never blocks the fanout dispatcher.

Concurrency notes:
    * ``subscribe`` / ``unsubscribe`` run under ``_lock`` so the
      subscriber set, the supervisor task and the LISTEN connection are
      mutated atomically.
    * The asyncpg LISTEN callback is synchronous; we only call
      ``Queue.put_nowait``/``get_nowait`` from it (zero awaits, zero
      blocking). Dispatch lives entirely in the asyncpg event loop.
    * Cancellation safety: when the supervisor task is cancelled by
      ``unsubscribe`` we ``await`` it to drain ``remove_listener`` +
      ``UNLISTEN`` so the next subscriber starts from a clean state.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import UUID

import asyncpg
import structlog

log = structlog.get_logger()

CHANNEL = 'tenant_operations_events'
QUEUE_MAX_SIZE = 100
# How long the supervisor sleeps between idleness checks. It's a fallback
# only — `unsubscribe` proactively cancels the task when the last
# subscriber leaves; this just keeps the asyncio loop happy.
_SUPERVISOR_IDLE_SLEEP_SECONDS = 3600


class _PubSubFanout:
    def __init__(self) -> None:
        # tenant_id (as string) → set of subscriber queues.
        self._subscribers: dict[str, set[asyncio.Queue[str]]] = {}
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None
        self._ready = asyncio.Event()
        self._pool: Any | None = None  # injected by `subscribe`

    @property
    def subscriber_count(self) -> int:
        return sum(len(s) for s in self._subscribers.values())

    @property
    def tenant_count(self) -> int:
        return len(self._subscribers)

    def _dispatch(self, payload: str) -> None:
        """asyncpg synchronous callback. Fan payload out to matching subs."""
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            log.warning('ws_fanout.dropped_invalid_json', payload_preview=payload[:80])
            return
        tenant_id = event.get('tenant_id')
        if not tenant_id:
            return
        subs = self._subscribers.get(str(tenant_id))
        if not subs:
            return
        for queue in list(subs):
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                # Drop oldest, push newest — keeps the WS from falling
                # behind unboundedly on a slow client.
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(payload)
                except asyncio.QueueFull:
                    # Still full (extremely unlikely with maxsize=100):
                    # log + give up on this delivery.
                    log.warning(
                        'ws_fanout.dropped_message_queue_full',
                        tenant_id=tenant_id,
                    )

    async def _supervise(self) -> None:
        """Long-running task: holds the LISTEN connection until cancelled.

        AUDIT-49 / re-audit §1.1 (2026-05-18): si add_listener / LISTEN
        levantan excepción durante el setup (DB down, permisos), antes
        dejábamos `self._task` poblado pero el task ya muerto — el siguiente
        `subscribe()` veía `self._task is not None` y se colgaba para siempre
        en `await self._ready.wait()`. Ahora cualquier excepción (incluido
        durante el setup) resetea el estado de instance ANTES del raise para
        que el próximo subscriber respawnee el supervisor.
        """
        try:
            assert self._pool is not None, 'pool must be injected before supervise'
            async with self._pool.acquire() as conn:
                callback = self._on_notify_factory(conn)
                await conn.add_listener(CHANNEL, callback)
                await conn.execute(f'listen {CHANNEL}')
                self._ready.set()
                try:
                    while True:
                        await asyncio.sleep(_SUPERVISOR_IDLE_SLEEP_SECONDS)
                finally:
                    try:
                        await conn.remove_listener(CHANNEL, callback)
                        await conn.execute(f'unlisten {CHANNEL}')
                    except (asyncpg.PostgresError, OSError) as exc:
                        log.warning('ws_fanout.cleanup_failed', error=str(exc))
        except asyncio.CancelledError:
            log.info('ws_fanout.supervisor_cancelled')
            raise
        except Exception:
            log.exception('ws_fanout.supervisor_crashed')
            # AUDIT-49 / re-audit §1.1: limpiar el estado de instance ANTES
            # del raise — sino `_task is not None` queda True con un task
            # ya muerto y el próximo `subscribe()` cuelga en
            # `self._ready.wait()` para siempre. Además SET el _ready event
            # para destrabar los subscribers que estaban esperando — ellos
            # detectan el crash en `subscribe()` (check `_task is None or
            # _task.done()`) y reintentan respawneando el supervisor.
            self._task = None
            self._pool = None
            self._ready.set()
            raise

    def _on_notify_factory(self, _conn):
        """Returns the sync callback asyncpg expects (4 positional args)."""
        def _on(_connection, _pid, _channel, payload: str) -> None:
            self._dispatch(payload)
        return _on

    async def subscribe(self, pool: Any, tenant_id: UUID) -> asyncio.Queue[str]:
        """Register a new subscriber and start the supervisor if needed.

        AUDIT-49 / re-audit §1.1: si el supervisor murió (crash en setup), el
        _ready event puede señalizarse como "false-ready" — el subscribe lo
        detecta y respawnea el supervisor antes de fallar. Hasta 2 reintentos
        (initial + 1) para no loop infinito si el upstream sigue caído.
        """
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
        attempts = 0
        while True:
            attempts += 1
            async with self._lock:
                self._subscribers.setdefault(str(tenant_id), set()).add(queue)
                if self._task is None:
                    self._pool = pool
                    self._ready = asyncio.Event()
                    self._task = asyncio.create_task(
                        self._supervise(), name='ws_fanout_supervisor'
                    )
                task = self._task
            # Wait until LISTEN is registered before returning — otherwise the
            # caller could miss notifications fired right after subscribe().
            await self._ready.wait()
            # Detect false-ready: supervisor died during setup (crashed +
            # set _ready before raising). Cleanup queue + retry with fresh
            # supervisor. Max 2 attempts to avoid infinite loop if DB stays down.
            if task.done() and attempts < 2:
                log.warning(
                    'ws_fanout.subscribe_retry_after_supervisor_crash',
                    tenant_id=str(tenant_id),
                    attempt=attempts,
                )
                # The crashed supervisor already reset self._task/_pool/_ready.
                # Continue the loop to respawn.
                continue
            if task.done():
                # Second attempt also failed → bail with a clear error so
                # the WS handler can close the socket with 1011.
                async with self._lock:
                    self._subscribers.get(str(tenant_id), set()).discard(queue)
                raise RuntimeError('ws_fanout supervisor crashed; LISTEN unavailable')
            return queue

    async def unsubscribe(self, tenant_id: UUID, queue: asyncio.Queue[str]) -> None:
        """Detach a subscriber; stop the supervisor when none remain."""
        async with self._lock:
            tenant_subs = self._subscribers.get(str(tenant_id))
            if tenant_subs is not None:
                tenant_subs.discard(queue)
                if not tenant_subs:
                    self._subscribers.pop(str(tenant_id), None)
            # Tear down ONLY when zero subscribers across all tenants.
            if not self._subscribers and self._task is not None:
                task = self._task
                self._task = None
                self._pool = None
                self._ready.clear()
        # Drain the cancellation outside the lock to avoid deadlock with
        # the supervisor's own conn cleanup paths.
        if not self._subscribers and 'task' in locals():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass


# Module-level singleton — the fanout is process-wide and stateless across
# requests, so a single instance is enough. Tests reset it via
# `reset_fanout_for_tests()`.
fanout = _PubSubFanout()


def reset_fanout_for_tests() -> None:
    """Create a fresh fanout instance. ONLY for tests."""
    global fanout
    fanout = _PubSubFanout()
