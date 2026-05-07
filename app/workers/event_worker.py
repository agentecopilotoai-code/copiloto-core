import asyncio
import json
import os

import asyncpg
import httpx
import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.whatsapp import send_text_message

log = structlog.get_logger()


def provider_message_id(result: dict) -> str | None:
    messages = result.get('messages')
    if not isinstance(messages, list) or not messages:
        return None
    first_message = messages[0]
    if not isinstance(first_message, dict):
        return None
    message_id = first_message.get('id')
    return message_id if isinstance(message_id, str) else None


def delivery_error_message(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        response_text = exc.response.text[:1000]
        return f'Meta Graph API HTTP {exc.response.status_code}: {response_text}'
    return str(exc)[:1000]


async def process_once(conn: asyncpg.Connection) -> int:
    rows = await conn.fetch(
        """
        select e.id, e.tenant_id, e.aggregate_id, m.body_text, c.phone_number_id, ct.phone_e164
        from app.domain_events e
        join app.messages m on m.id = e.aggregate_id and m.tenant_id = e.tenant_id
        join app.conversations cv on cv.id = m.conversation_id and cv.tenant_id = e.tenant_id
        join app.contacts ct on ct.id = cv.contact_id and ct.tenant_id = e.tenant_id
        join app.tenant_channels c on c.id = cv.channel_id and c.tenant_id = e.tenant_id
        where e.published_at is null and e.event_name='message.queued'
        order by e.occurred_at
        limit 10
        """
    )
    for row in rows:
        log.info(
            'message_delivery_attempt',
            event_id=str(row['id']),
            message_id=str(row['aggregate_id']),
            tenant_id=str(row['tenant_id']),
            phone_number_id=row['phone_number_id'],
            to_last4=row['phone_e164'][-4:] if row['phone_e164'] else None,
        )
        try:
            result = await send_text_message(
                row['phone_number_id'], row['phone_e164'], row['body_text'] or ''
            )
        except Exception as exc:
            error_message = delivery_error_message(exc)
            async with conn.transaction():
                await conn.execute(
                    """
                    update app.messages
                    set status='failed', failed_at=now(), error_message=$2
                    where id=$1
                    """,
                    row['aggregate_id'],
                    error_message,
                )
                await conn.execute(
                    """
                    update app.domain_events
                    set published_at=now(), payload=payload || $2::jsonb
                    where id=$1
                    """,
                    row['id'],
                    json.dumps({'delivery_failed': True, 'error_message': error_message}),
                )
            log.warning(
                'message_delivery_failed',
                event_id=str(row['id']),
                message_id=str(row['aggregate_id']),
                tenant_id=str(row['tenant_id']),
                error=error_message,
            )
            continue

        external_message_id = provider_message_id(result)
        async with conn.transaction():
            await conn.execute(
                """
                update app.messages
                set status='sent',
                    sent_at=now(),
                    external_message_id=coalesce($2, external_message_id),
                    payload=payload || $3::jsonb
                where id=$1
                """,
                row['aggregate_id'],
                external_message_id,
                json.dumps({'provider_result': result}),
            )
            await conn.execute('update app.domain_events set published_at=now() where id=$1', row['id'])
        log.info(
            'message_delivery_sent',
            event_id=str(row['id']),
            message_id=str(row['aggregate_id']),
            tenant_id=str(row['tenant_id']),
            provider_message_id=external_message_id,
            mocked=bool(result.get('mocked')),
        )
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
