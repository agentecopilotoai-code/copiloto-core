"""TASK-0061: dedicated entrypoint for the GDPR retention worker.

Runs once per day at ``retention_run_hour_utc`` (UTC). Each cycle iterates
through every active tenant, applies the per-entity policies in
``app.data_retention_policies`` and emits a ``retention.cycle_completed``
domain event with the per-entity counts plus an audit row per entity.

A separate worker process keeps the heavy DELETEs out of the reminder/event
loops; the scheduler tick stays tight.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import asyncpg
import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.retention import run_retention_cycle

log = structlog.get_logger()


def _seconds_until_next_run(hour_utc: int, now: datetime | None = None) -> float:
    now = now or datetime.now(UTC)
    target = now.replace(hour=hour_utc, minute=0, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return (target - now).total_seconds()


async def main() -> None:  # pragma: no cover - manual entrypoint
    configure_logging(get_settings().log_level)
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    # ``support_mode`` lets the worker bypass per-tenant RLS while still
    # writing tenant-scoped audit rows.
    await conn.execute("select set_config('app.support_mode', 'true', false)")
    try:
        while True:
            sleep_for = _seconds_until_next_run(settings.retention_run_hour_utc)
            log.info('retention.sleep', seconds=int(sleep_for))
            await asyncio.sleep(sleep_for)
            try:
                summary = await run_retention_cycle(conn)
                log.info('retention.cycle_done', tenants=len(summary))
            except Exception:
                log.exception('retention.cycle_top_level_failure')
    finally:
        await conn.close()


if __name__ == '__main__':  # pragma: no cover
    asyncio.run(main())
