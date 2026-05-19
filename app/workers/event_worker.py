import asyncio
import json
import os
from datetime import datetime, timezone

import asyncpg
import httpx
import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.meta_messenger import (
    META_MESSENGER_PROVIDERS,
    OutsideServiceWindowError,
    is_within_service_window,
    send_messenger_message,
)
from app.services.metrics import (
    record_message,
    record_outbound_dlq,
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


def delivery_error_code(exc: Exception) -> str:
    """Extrae el ``error.code`` que devuelve Meta cuando un envío falla.

    El payload típico de error de Graph API es::

        {"error": {"message": "...", "type": "...", "code": 131026, ...}}

    Si no se puede parsear, se usa el HTTP status (`http_<status>`) o
    ``transport_error`` cuando ni siquiera hubo respuesta HTTP (timeout,
    DNS, etc.).
    """
    if isinstance(exc, httpx.HTTPStatusError):
        try:
            body = exc.response.json()
            code = body.get('error', {}).get('code')
            if code is not None:
                return str(code)
        except (json.JSONDecodeError, ValueError, AttributeError, TypeError):
            pass
        return f'http_{exc.response.status_code}'
    return 'transport_error'


EVENT_WORKER_BATCH_SIZE = 10


async def process_once(conn: asyncpg.Connection) -> int:
    """BUG-058 + BUG-173: procesar hasta `EVENT_WORKER_BATCH_SIZE` eventos,
    UNO POR TRANSACCIÓN.

    Cada iteración:
      1. Abre transacción
      2. SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1 (locka 1 fila)
      3. Envía a Meta + UPDATE `published_at`
      4. COMMIT (libera el lock + persiste el "ya entregado")

    Por qué per-row vs el wrapper batch original:
    - **BUG-058** (concurrent workers): cada worker compite por filas via
      SKIP LOCKED — sin esto, dos workers seleccionaban las MISMAS filas y
      mandaban duplicados a Meta. Preservado: el SELECT FOR UPDATE
      SKIP LOCKED sigue dentro de la transacción.
    - **BUG-173** (codex P1 sobre fix-group-08): wrappear TODO el batch en
      una sola transacción significaba que los `conn.transaction()` per-row
      pasaban a ser savepoints. Si el worker moría/era cancelado o un row
      tardío fallaba con error inesperado, el outer transaction rollbackeaba
      TODAS las actualizaciones — incluidos eventos ya enviados a Meta —
      y en el próximo tick el mismo `published_at IS NULL` los re-seleccionaba
      y los re-enviaba = duplicate delivery al usuario.

    Per-row commit garantiza que "entregado a Meta" + "marca como published"
    son atómicos, y un crash entre rows no invalida el progreso.
    """
    processed = 0
    for _ in range(EVENT_WORKER_BATCH_SIZE):
        async with conn.transaction():
            handled = await _process_locked_batch(conn)
        if handled == 0:
            break
        processed += handled
    return processed


async def _process_locked_batch(conn: asyncpg.Connection) -> int:
    # BUG-173: LIMIT 1 (era LIMIT 10). El loop está afuera en `process_once`
    # para que cada row se procese en su propia transacción y el commit
    # sea per-row.
    rows = await conn.fetch(
        """
        select e.id, e.tenant_id, e.aggregate_id, m.conversation_id, m.body_text,
               m.message_type, m.media_id, m.mime_type, m.payload,
               c.provider, c.phone_number_id, c.page_id, c.instagram_account_id,
               c.account_mode, c.token_ref, c.service_window_hours,
               cv.service_window_expires_at,
               ct.phone_e164, ct.wa_id
        from app.domain_events e
        join app.messages m on m.id = e.aggregate_id and m.tenant_id = e.tenant_id
        join app.conversations cv on cv.id = m.conversation_id and cv.tenant_id = e.tenant_id
        join app.contacts ct on ct.id = cv.contact_id and ct.tenant_id = e.tenant_id
        join app.tenant_channels c on c.id = cv.channel_id and c.tenant_id = e.tenant_id
        where e.published_at is null and e.event_name='message.queued'
          and c.provider in ('whatsapp_cloud_api','instagram_messenger','facebook_messenger')
        order by e.occurred_at
        limit 1
        for update of e skip locked
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
        provider = row['provider'] or 'whatsapp_cloud_api'
        channel_label = 'whatsapp' if provider == 'whatsapp_cloud_api' else provider
        try:
            message_payload = row['payload'] or {}
            if isinstance(message_payload, str):
                message_payload = json.loads(message_payload)
            if provider in META_MESSENGER_PROVIDERS:
                # 24h service window gate. The expiry was set on inbound by
                # the messenger webhook; we double-check here in case it was
                # nudged forward by ops or replaced by a later inbound.
                window_expires = row['service_window_expires_at']
                window_open = False
                if isinstance(window_expires, datetime):
                    expires = window_expires
                    if expires.tzinfo is None:
                        expires = expires.replace(tzinfo=timezone.utc)
                    window_open = datetime.now(timezone.utc) <= expires
                else:
                    window_open = is_within_service_window(
                        None,
                        window_hours=int(row['service_window_hours'] or 24),
                    )
                recipient_account_id = (
                    row['instagram_account_id']
                    if provider == 'instagram_messenger'
                    else row['page_id']
                )
                if not recipient_account_id:
                    raise RuntimeError(
                        f'{provider} channel missing recipient_account_id'
                    )
                result = await send_messenger_message(
                    provider,
                    recipient_account_id,
                    row['wa_id'],
                    text=row['body_text'] or '',
                    media_url=message_payload.get('media_url'),
                    media_type=row['message_type'] if row['message_type'] in {
                        'image', 'video', 'audio', 'file', 'document'
                    } else None,
                    delivery_mode=row['account_mode'] or 'mock',
                    token_ref=row['token_ref'],
                    within_service_window=window_open,
                )
            else:
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
            if isinstance(exc, OutsideServiceWindowError):
                error_code = 'outside_service_window'
                error_message = (
                    f'{provider} 24h service window expired; outbound bloqueado.'
                )
            else:
                error_message = delivery_error_message(exc)
                error_code = delivery_error_code(exc)
            record_message(
                tenant_id=row['tenant_id'],
                direction='outbound',
                channel=channel_label,
                status='failed',
            )
            # TASK-0065: contador de DLQ por error_code para alertas Prometheus
            # y dashboards. Se incrementa una sola vez por fallo definitivo,
            # alineado con el insert en ``messages.status='failed'``.
            record_outbound_dlq(
                tenant_id=row['tenant_id'],
                error_code=error_code,
            )
            async with conn.transaction():
                await conn.execute(
                    """
                    update app.messages
                    set status='failed', failed_at=now(), error_message=$2, error_code=$3
                    where id=$1
                    """,
                    row['aggregate_id'],
                    error_message,
                    error_code,
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
                error_code=error_code,
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
            channel=channel_label,
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


async def main() -> None:  # pragma: no cover - manual entrypoint
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
