import asyncio
import json

import asyncpg
import structlog

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.campaigns import process_due_campaigns
from app.services.metrics import set_worker_queue_depth, start_metrics_http_server
from app.services.operator_alerts import process_pending_operator_alerts
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


def _extract_kind(payload: object) -> str | None:
    """Return ``payload->>'kind'`` if present and a string.

    TASK-0056: ``reminder_jobs`` use ``kind`` for non-templated worker actions
    (e.g. ``auto_rebook_timeout``) that should not be gated by an approved
    WhatsApp template.
    """
    data = _coerce_payload_dict(payload)
    if data is None:
        return None
    kind = data.get('kind')
    return kind if isinstance(kind, str) and kind else None


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


async def _dispatch_auto_rebook_timeout(
    conn: asyncpg.Connection, row: asyncpg.Record
) -> None:
    """Run the TASK-0056 silent-decline escalation for one timeout job.

    Imported lazily so the scheduler module stays importable even if the
    self-service module is being edited.
    """
    from uuid import UUID

    from app.services.appointment_self_service import execute_auto_rebook_timeout

    payload = _coerce_payload_dict(row['payload']) or {}
    conversation_id = payload.get('conversation_id')
    appointment_id = payload.get('appointment_id')
    if not conversation_id or not appointment_id:
        await conn.execute(
            """
            update app.reminder_jobs
            set status='failed', last_error=$2, updated_at=now()
            where id=$1
            """,
            row['id'],
            'auto_rebook_timeout_invalid_payload',
        )
        log.warning(
            'auto_rebook_timeout_invalid_payload',
            reminder_id=str(row['id']),
            tenant_id=str(row['tenant_id']),
        )
        return
    try:
        trace = await execute_auto_rebook_timeout(
            conn,
            tenant_id=row['tenant_id'],
            conversation_id=UUID(conversation_id),
            appointment_id=UUID(appointment_id),
            job_id=row['id'],
        )
    except Exception as exc:
        await conn.execute(
            """
            update app.reminder_jobs
            set status='failed', last_error=$2, updated_at=now()
            where id=$1
            """,
            row['id'],
            f'auto_rebook_timeout_exception:{str(exc)[:200]}',
        )
        log.exception(
            'auto_rebook_timeout_failed',
            reminder_id=str(row['id']),
            tenant_id=str(row['tenant_id']),
        )
        return
    await conn.execute("update app.reminder_jobs set status='sent' where id=$1", row['id'])
    log.info(
        'auto_rebook_timeout_dispatched',
        reminder_id=str(row['id']),
        tenant_id=str(row['tenant_id']),
        cancelled=trace.get('cancelled', False),
        skipped_reason=trace.get('skipped_reason'),
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
        kind = _extract_kind(row['payload'])
        # TASK-0056: silent-decline escalation. The auto-rebook timeout is a
        # pure worker action — no WhatsApp template is sent — so it is
        # dispatched via ``execute_auto_rebook_timeout`` and the row is marked
        # ``sent`` directly without emitting ``reminder.due``.
        if kind == 'auto_rebook_timeout':
            await _dispatch_auto_rebook_timeout(conn, row)
            continue
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


async def _update_scheduler_queue_depth(conn: asyncpg.Connection) -> None:
    pending = await conn.fetchval(
        """
        select count(*) from app.reminder_jobs
        where status = 'pending' and run_at <= now()
        """
    )
    set_worker_queue_depth(worker='scheduler', depth=int(pending or 0))


async def main() -> None:
    configure_logging(get_settings().log_level)
    settings = get_settings()
    start_metrics_http_server(settings.worker_metrics_port)
    conn = await asyncpg.connect(settings.database_url)
    await conn.execute("select set_config('app.support_mode', 'true', false)")
    try:
        while True:
            await _update_scheduler_queue_depth(conn)
            await _process_pending_reminder_jobs(conn)
            await process_due_campaigns(conn)
            await refresh_due_segments(conn)
            await process_pending_operator_alerts(conn)
            await asyncio.sleep(10)
    finally:
        await conn.close()


if __name__ == '__main__':
    asyncio.run(main())
