import asyncio
import json
import os

import asyncpg
import httpx
import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.metrics import (
    record_message,
    set_worker_queue_depth,
    start_metrics_http_server,
)
from app.services.whatsapp import send_whatsapp_message

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
        select e.id, e.tenant_id, e.aggregate_id, m.conversation_id, m.body_text, m.message_type, m.media_id, m.mime_type, m.payload, c.phone_number_id, c.account_mode, c.token_ref, ct.phone_e164
        from app.domain_events e
        join app.messages m on m.id = e.aggregate_id and m.tenant_id = e.tenant_id
        join app.conversations cv on cv.id = m.conversation_id and cv.tenant_id = e.tenant_id
        join app.contacts ct on ct.id = cv.contact_id and ct.tenant_id = e.tenant_id
        join app.tenant_channels c on c.id = cv.channel_id and c.tenant_id = e.tenant_id
        where e.published_at is null and e.event_name='message.queued'
          and c.provider = 'whatsapp_cloud_api'
        order by e.occurred_at
        limit 10
        """
    )
    pending_total = await conn.fetchval(
        """
        select count(*) from app.domain_events
        where published_at is null and event_name='message.queued'
        """
    )
    set_worker_queue_depth(worker='event_worker', depth=int(pending_total or 0))
    for row in rows:
        log.info(
            'message_delivery_attempt',
            event_id=str(row['id']),
            message_id=str(row['aggregate_id']),
            tenant_id=str(row['tenant_id']),
            phone_number_id=row['phone_number_id'],
            delivery_mode=row['account_mode'] or 'mock',
            token_ref=row['token_ref'],
            to_last4=row['phone_e164'][-4:] if row['phone_e164'] else None,
        )
        try:
            message_payload = row['payload'] or {}
            if isinstance(message_payload, str):
                message_payload = json.loads(message_payload)
            result = await send_whatsapp_message(
                row['phone_number_id'],
                row['phone_e164'],
                row['message_type'] or 'text',
                row['body_text'] or '',
                row['account_mode'] or 'mock',
                row['token_ref'],
                row['media_id'],
                message_payload.get('media_url'),
                message_payload.get('caption'),
                message_payload.get('interactive'),
                message_payload.get('template'),
            )
        except Exception as exc:
            error_message = delivery_error_message(exc)
            record_message(
                tenant_id=row['tenant_id'],
                direction='outbound',
                channel='whatsapp',
                status='failed',
            )
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
                await conn.execute(
                    "select pg_notify('tenant_operations_events', $1)",
                    json.dumps({
                        'type': 'conversation.changed',
                        'tenant_id': str(row['tenant_id']),
                        'conversation_id': str(row['conversation_id']),
                        'message_id': str(row['aggregate_id']),
                    }),
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
            await conn.execute(
                "select pg_notify('tenant_operations_events', $1)",
                json.dumps({
                    'type': 'conversation.changed',
                    'tenant_id': str(row['tenant_id']),
                    'conversation_id': str(row['conversation_id']),
                    'message_id': str(row['aggregate_id']),
                }),
            )
        mocked = bool(result.get('mocked'))
        record_message(
            tenant_id=row['tenant_id'],
            direction='outbound',
            channel='whatsapp',
            status='sent',
        )
        log.info(
            'message_delivery_mocked' if mocked else 'message_delivery_sent',
            event_id=str(row['id']),
            message_id=str(row['aggregate_id']),
            tenant_id=str(row['tenant_id']),
            provider_message_id=external_message_id,
            delivery_mode=row['account_mode'] or 'mock',
            mocked=mocked,
        )
    return len(rows)


async def main() -> None:
    configure_logging(get_settings().log_level)
    settings = get_settings()
    start_metrics_http_server(settings.worker_metrics_port)
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
