"""TASK-0057: dedicated entrypoint for the operator alerts loop.

The scheduler tick already polls ``operator_alerts`` via
``app.services.operator_alerts.process_pending_operator_alerts``. This module
exposes a standalone ``main()`` for deployments that want a separate process
(useful when SMTP / webhook latency would otherwise stall the reminder loop).
"""
from __future__ import annotations

import asyncio

import asyncpg
import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.operator_alerts import process_pending_operator_alerts

log = structlog.get_logger()


async def main() -> None:  # pragma: no cover - manual entrypoint
    configure_logging(get_settings().log_level)
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    await conn.execute("select set_config('app.support_mode', 'true', false)")
    try:
        while True:
            try:
                count = await process_pending_operator_alerts(conn)
                if count:
                    log.info('operator_alerts.tick_processed', count=count)
            except Exception:
                log.exception('operator_alerts.tick_failed')
            await asyncio.sleep(10)
    finally:
        await conn.close()


if __name__ == '__main__':  # pragma: no cover
    asyncio.run(main())
