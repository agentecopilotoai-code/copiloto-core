import asyncio

import json

import asyncpg
import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging

log = structlog.get_logger()


def jsonb_payload(value: object) -> str:
    if value is None:
        return '{}'
    if isinstance(value, str):
        return value
    return json.dumps(value)


async def main() -> None:
    configure_logging()
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    await conn.execute("select set_config('app.support_mode', 'true', false)")
    try:
        while True:
            rows = await conn.fetch(
                """
                update app.reminder_jobs
                set status='processing'
                where id in (
                  select id from app.reminder_jobs
                  where status='pending' and scheduled_for <= now()
                  order by scheduled_for
                  limit 25
                  for update skip locked
                )
                returning *
                """
            )
            for row in rows:
                await conn.execute(
                    """
                    insert into app.domain_events
                      (tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload)
                    values ($1, 'reminder_job', $2, 'reminder.due', $3, $4::jsonb)
                    on conflict (tenant_id, idempotency_key) do nothing
                    """,
                    row['tenant_id'],
                    row['id'],
                    f"reminder:{row['id']}",
                    jsonb_payload(row['payload']),
                )
                await conn.execute("update app.reminder_jobs set status='sent' where id=$1", row['id'])
                log.info('reminder_enqueued', reminder_id=str(row['id']))
            await asyncio.sleep(10)
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
