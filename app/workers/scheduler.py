import asyncio
import json

import asyncpg
import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.campaigns import process_due_campaigns
from app.services.segments import refresh_due_segments

log = structlog.get_logger()


def jsonb_payload(value: object) -> str:
    if value is None:
        return '{}'
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _coerce_payload_dict(payload: object) -> dict | None:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            return None
    return payload if isinstance(payload, dict) else None


def _extract_purpose(payload: object) -> str | None:
    """Return ``payload->>'purpose'`` if present and a string."""
    data = _coerce_payload_dict(payload)
    if data is None:
        return None
    purpose = data.get('purpose')
    return purpose if isinstance(purpose, str) and purpose else None


async def _mark_conversation_pending_recall(
    conn: asyncpg.Connection,
    *,
    tenant_id: object,
    payload: object,
) -> None:
    """TASK-0052: stamp the conversation with the service whose recall just
    fired so the next inbound triggers ``book_appointment`` with
    ``prefilled_service_id`` pointing at the same service. We use a single
    ``pending_recall`` key under ``conversations.metadata`` so it's easy to
    inspect and clear by the orchestrator. If the appointment has no
    conversation, the recall message still goes out and the customer can start
    a fresh booking conversation manually.
    """
    data = _coerce_payload_dict(payload) or {}
    service_id = data.get('service_id')
    conversation_id = data.get('conversation_id')
    appointment_id = data.get('appointment_id')
    if not service_id or not conversation_id:
        return
    await conn.execute(
        """
        update app.conversations
        set metadata = jsonb_set(
              coalesce(metadata, '{}'::jsonb),
              '{pending_recall}',
              jsonb_build_object(
                'service_id', $3::text,
                'appointment_id', $4::text,
                'set_at', to_jsonb(now())
              ),
              true
            ),
            updated_at = now()
        where tenant_id = $1 and id = $2
        """,
        tenant_id,
        conversation_id,
        service_id,
        appointment_id or '',
    )


async def _has_approved_template(
    conn: asyncpg.Connection, tenant_id: object, purpose: str
) -> bool:
    return bool(
        await conn.fetchval(
            """
            select 1
            from app.whatsapp_templates
            where tenant_id=$1 and purpose=$2 and status='approved'
            limit 1
            """,
            tenant_id,
            purpose,
        )
    )


async def _process_pending_reminder_jobs(conn: asyncpg.Connection) -> int:
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
        purpose = _extract_purpose(row['payload'])
        if purpose and not await _has_approved_template(conn, row['tenant_id'], purpose):
            error = f'template_not_approved:{purpose}'
            await conn.execute(
                """
                update app.reminder_jobs
                set status='failed', last_error=$2, updated_at=now()
                where id=$1
                """,
                row['id'],
                error,
            )
            log.warning(
                'reminder_skipped_missing_template',
                reminder_id=str(row['id']),
                tenant_id=str(row['tenant_id']),
                purpose=purpose,
            )
            continue
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
        # TASK-0052: a recall just went out — flag the conversation so the
        # next inbound enters booking_flow with the same service prefilled.
        if purpose == 'service_recall':
            try:
                await _mark_conversation_pending_recall(
                    conn,
                    tenant_id=row['tenant_id'],
                    payload=row['payload'],
                )
            except Exception:
                log.exception(
                    'reminder_recall_mark_failed',
                    reminder_id=str(row['id']),
                    tenant_id=str(row['tenant_id']),
                )
        log.info('reminder_enqueued', reminder_id=str(row['id']))
    return len(rows)


async def main() -> None:
    configure_logging(get_settings().log_level)
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    await conn.execute("select set_config('app.support_mode', 'true', false)")
    try:
        while True:
            await _process_pending_reminder_jobs(conn)
            await process_due_campaigns(conn)
            await refresh_due_segments(conn)
            await asyncio.sleep(10)
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
