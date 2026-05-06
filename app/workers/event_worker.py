import asyncio
import json
import os

import asyncpg
import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.whatsapp import send_text_message

log = structlog.get_logger()


async def process_once(conn: asyncpg.Connection) -> int:
    rows = await conn.fetch(
        """
        select e.id, e.tenant_id, e.aggregate_id, m.body_text, c.phone_number_id, ct.phone_e164
        from app.domain_events e
        join app.messages m on m.id = e.aggregate_id
        join app.conversations cv on cv.id = m.conversation_id
        join app.contacts ct on ct.id = cv.contact_id
        join app.tenant_channels c on c.id = cv.channel_id
        where e.published_at is null and e.event_name='message.queued'
        order by e.occurred_at
        limit 10
        """
    )
    for row in rows:
        async with conn.transaction():
            result = await send_text_message(
                row['phone_number_id'], row['phone_e164'], row['body_text'] or ''
            )
            await conn.execute(
                """
                update app.messages
                set status='sent', sent_at=now(), payload=payload || $2::jsonb
                where id=$1
                """,
                row['aggregate_id'],
                json.dumps({'provider_result': result}),
            )
            await conn.execute('update app.domain_events set published_at=now() where id=$1', row['id'])
            log.info('message_published', event_id=str(row['id']), tenant_id=str(row['tenant_id']))
    return len(rows)


async def main() -> None:
    configure_logging()
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    await conn.execute("select set_config('app.support_mode', 'true', false)")
    try:
        while True:
            processed = await process_once(conn)
            await asyncio.sleep(1 if processed else 5)
    finally:
        await conn.close()


if __name__ == '__main__' and os.getenv('RUN_WORKER', 'true') == 'true':
    asyncio.run(main())
