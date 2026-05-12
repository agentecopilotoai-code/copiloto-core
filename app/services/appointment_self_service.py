"""Self-service appointment cancellation and reschedule over WhatsApp (TASK-0043).

The orchestrator detects ``cancel_appointment``/``reschedule_appointment`` intents,
but until this module the bot only forwarded them to a human agent. Now the bot
runs a guided mini-flow:

* ``maybe_run_cancel_flow``     — ask "¿Sí, cancelar / No, mantener?" and on
  confirmation set ``status='cancelled'`` and cancel pending reminder jobs.
* ``maybe_run_reschedule_flow`` — offer 3 free slots using the same resource
  and service of the upcoming appointment, then ``UPDATE`` ``starts_at`` /
  ``ends_at`` and regenerate the reminder jobs. Slot conflicts raise an
  ``asyncpg.ExclusionViolationError`` that we catch to re-offer slots.

Policy gate: if the appointment is closer than
``tenant_settings.escalation_policy.self_service.min_hours_before_start`` (default
2h), the bot does not act — it just hands off to a human with reason
``too_close_to_start``. Paid appointments also escalate (to avoid refund noise).

State is persisted in ``conversations.metadata.self_service`` with shape:
``{"flow": "cancel"|"reschedule", "step": "...", "appointment_id": "..."}``.

Idempotency: each inbound message inserts one ``domain_events('self_service.handled')``.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from app.services.audit import audit
from app.services.booking_flow import (
    _busy_intervals,
    _fetch_resource,
    _working_hours_for_date,
    compute_free_slots,
)
from app.services.notifications import (
    cancel_appointment_reminder_jobs,
    regenerate_appointment_reminder_jobs,
)
from app.services.whatsapp import build_interactive_button_payload

if TYPE_CHECKING:
    import asyncpg

log = structlog.get_logger()


FLOW_CANCEL = 'cancel'
FLOW_RESCHEDULE = 'reschedule'

STEP_AWAITING_CANCEL_CONFIRM = 'awaiting_cancel_confirm'
STEP_AWAITING_RESCHEDULE_SLOT = 'awaiting_reschedule_slot'
STEP_COMPLETED = 'completed'

PREFIX_CANCEL_CONFIRM = 'cancel_confirm'
PREFIX_RESCHED_SLOT = 'resched_slot'

DEFAULT_MIN_HOURS_BEFORE_START = 2
MAX_FUTURE_DAYS = 14
SLOTS_TO_OFFER = 3

INTENT_CANCEL = 'cancel_appointment'
INTENT_RESCHEDULE = 'reschedule_appointment'


def _parse_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return fallback
    return value if value is not None else fallback


def _self_service_state(conversation: Any) -> dict[str, Any]:
    meta = _parse_json(conversation.get('metadata'), {})
    if not isinstance(meta, dict):
        return {}
    state = meta.get('self_service')
    return state if isinstance(state, dict) else {}


def _interactive_id(inbound_message: Any) -> tuple[str | None, str | None]:
    payload = _parse_json(inbound_message.get('payload'), {})
    if not isinstance(payload, dict):
        return None, None
    interactive_id = payload.get('interactive_id')
    if not isinstance(interactive_id, str) or ':' not in interactive_id:
        return None, None
    prefix, _, value = interactive_id.partition(':')
    return prefix, value


def min_hours_before_start(escalation_policy: Any) -> float:
    policy = _parse_json(escalation_policy, {})
    if not isinstance(policy, dict):
        return float(DEFAULT_MIN_HOURS_BEFORE_START)
    self_service = policy.get('self_service') or {}
    if not isinstance(self_service, dict):
        return float(DEFAULT_MIN_HOURS_BEFORE_START)
    raw = self_service.get('min_hours_before_start')
    try:
        value = float(raw)
        if value < 0:
            return float(DEFAULT_MIN_HOURS_BEFORE_START)
        return value
    except (TypeError, ValueError):
        return float(DEFAULT_MIN_HOURS_BEFORE_START)


async def _fetch_upcoming_appointment(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    contact_id: UUID,
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, contact_id, resource_id, service_id, service_code,
               starts_at, ends_at, status, payment_status
        from app.appointments
        where tenant_id=$1
          and contact_id=$2
          and status in ('scheduled','confirmed')
          and starts_at >= now()
        order by starts_at asc
        limit 1
        """,
        tenant_id,
        contact_id,
    )
    return dict(row) if row else None


async def _fetch_appointment(
    conn: asyncpg.Connection, tenant_id: UUID, appointment_id: UUID
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, contact_id, resource_id, service_id, service_code,
               starts_at, ends_at, status, payment_status
        from app.appointments
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        appointment_id,
    )
    return dict(row) if row else None


async def _fetch_tenant_settings(
    conn: asyncpg.Connection, tenant_id: UUID
) -> dict[str, Any]:
    row = await conn.fetchrow(
        'select escalation_policy from app.tenant_settings where tenant_id=$1',
        tenant_id,
    )
    if not row:
        return {}
    return {'escalation_policy': row['escalation_policy']}


async def _persist_state(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    conversation: Any,
    state: dict[str, Any] | None,
) -> None:
    meta = _parse_json(conversation.get('metadata'), {})
    if not isinstance(meta, dict):
        meta = {}
    if state is None:
        meta.pop('self_service', None)
    else:
        meta['self_service'] = state
    await conn.execute(
        """
        update app.conversations
        set metadata=$1::jsonb, status='waiting_user', updated_at=now()
        where tenant_id=$2 and id=$3
        """,
        json.dumps(meta),
        tenant_id,
        conversation['id'],
    )


async def _queue_text_message(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    channel_id: UUID,
    channel_account_mode: str,
    body_text: str,
    step: str,
) -> UUID:
    row = await conn.fetchrow(
        """
        insert into app.messages (
          tenant_id, conversation_id, direction, sender_actor_type,
          body_text, message_type, status, payload
        )
        values ($1, $2, 'outbound', 'bot', $3, 'text', 'queued', $4::jsonb)
        returning id
        """,
        tenant_id,
        conversation_id,
        body_text,
        json.dumps({'self_service_step': step}),
    )
    idempotency_key = f'bot_self_service_text:{row["id"]}'
    await conn.execute(
        """
        insert into app.domain_events (
          tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload
        )
        values ($1, 'message', $2, 'message.queued', $3, $4::jsonb)
        on conflict (tenant_id, idempotency_key) do nothing
        """,
        tenant_id,
        row['id'],
        idempotency_key,
        json.dumps({
            'message_id': str(row['id']),
            'conversation_id': str(conversation_id),
            'channel_id': str(channel_id),
            'channel_account_mode': channel_account_mode,
            'body_text': body_text,
            'self_service_step': step,
        }),
    )
    return row['id']


async def _queue_interactive_message(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    channel_id: UUID,
    channel_account_mode: str,
    body_text: str,
    interactive_payload: dict[str, Any],
    step: str,
) -> UUID:
    payload = {'interactive': interactive_payload, 'self_service_step': step}
    row = await conn.fetchrow(
        """
        insert into app.messages (
          tenant_id, conversation_id, direction, sender_actor_type,
          body_text, message_type, status, payload
        )
        values ($1, $2, 'outbound', 'bot', $3, 'interactive', 'queued', $4::jsonb)
        returning id
        """,
        tenant_id,
        conversation_id,
        body_text,
        json.dumps(payload),
    )
    idempotency_key = f'bot_self_service:{row["id"]}'
    await conn.execute(
        """
        insert into app.domain_events (
          tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload
        )
        values ($1, 'message', $2, 'message.queued', $3, $4::jsonb)
        on conflict (tenant_id, idempotency_key) do nothing
        """,
        tenant_id,
        row['id'],
        idempotency_key,
        json.dumps({
            'message_id': str(row['id']),
            'conversation_id': str(conversation_id),
            'channel_id': str(channel_id),
            'channel_account_mode': channel_account_mode,
            'body_text': body_text,
            'self_service_step': step,
        }),
    )
    return row['id']


async def _gather_alternative_slots(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    appointment: dict[str, Any],
) -> list[dict[str, str]]:
    """Return up to ``SLOTS_TO_OFFER`` slots on the same resource starting
    tomorrow."""
    resource = await _fetch_resource(conn, tenant_id, appointment['resource_id'])
    if not resource:
        return []
    duration = max(
        int((appointment['ends_at'] - appointment['starts_at']).total_seconds() // 60),
        15,
    )
    today = datetime.now(UTC).date()
    collected: list[dict[str, str]] = []
    for offset in range(0, MAX_FUTURE_DAYS + 1):
        candidate = today + timedelta(days=offset)
        franjas = _working_hours_for_date(resource['capabilities'], candidate)
        if not franjas:
            continue
        busy = await _busy_intervals(conn, tenant_id, appointment['resource_id'], candidate)
        slots = compute_free_slots(franjas, busy, duration)
        for slot in slots:
            # Skip the slot that matches the current appointment.
            slot_start_dt = datetime.combine(candidate, datetime.min.time()).replace(
                hour=int(slot['start_time'].split(':')[0]),
                minute=int(slot['start_time'].split(':')[1]),
                tzinfo=UTC,
            )
            if slot_start_dt <= datetime.now(UTC):
                continue
            if slot_start_dt == appointment['starts_at'].astimezone(UTC):
                continue
            collected.append({
                'date': candidate.isoformat(),
                'start_time': slot['start_time'],
            })
            if len(collected) >= SLOTS_TO_OFFER:
                return collected
    return collected


async def _too_close_to_start(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    appointment: dict[str, Any],
) -> bool:
    settings = await _fetch_tenant_settings(conn, tenant_id)
    threshold = min_hours_before_start(settings.get('escalation_policy'))
    now = datetime.now(UTC)
    starts_at = appointment['starts_at']
    if starts_at.tzinfo is None:
        starts_at = starts_at.replace(tzinfo=UTC)
    delta = (starts_at - now).total_seconds() / 3600.0
    return delta < threshold


async def _present_cancel_confirmation(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    conversation: Any,
    channel_id: UUID,
    channel_account_mode: str,
    appointment: dict[str, Any],
) -> None:
    starts_at = appointment['starts_at'].astimezone(UTC)
    body = (
        f'Encontré tu próxima cita: {starts_at.strftime("%d/%m %H:%M")}. '
        '¿Quieres cancelarla?'
    )
    interactive = build_interactive_button_payload(
        body_text=body,
        buttons=[
            {'id': f'{PREFIX_CANCEL_CONFIRM}:yes', 'title': 'Sí, cancelar'},
            {'id': f'{PREFIX_CANCEL_CONFIRM}:no', 'title': 'No, mantener'},
        ],
    )
    await _queue_interactive_message(
        conn,
        tenant_id=tenant_id,
        conversation_id=conversation['id'],
        channel_id=channel_id,
        channel_account_mode=channel_account_mode,
        body_text=body,
        interactive_payload=interactive,
        step=STEP_AWAITING_CANCEL_CONFIRM,
    )


async def _present_reschedule_slots(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    conversation: Any,
    channel_id: UUID,
    channel_account_mode: str,
    appointment: dict[str, Any],
) -> list[dict[str, str]] | None:
    slots = await _gather_alternative_slots(conn, tenant_id, appointment)
    if not slots:
        await _queue_text_message(
            conn,
            tenant_id=tenant_id,
            conversation_id=conversation['id'],
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
            body_text=(
                'No tengo horarios alternativos disponibles en los próximos días. '
                'Te conecto con un asesor.'
            ),
            step=STEP_AWAITING_RESCHEDULE_SLOT,
        )
        return None
    buttons = []
    for idx, slot in enumerate(slots):
        try:
            iso = date.fromisoformat(slot['date']).strftime('%d/%m')
        except ValueError:
            iso = slot['date']
        title = f'{iso} {slot["start_time"]}'[:20]
        buttons.append({
            'id': f'{PREFIX_RESCHED_SLOT}:{idx}',
            'title': title,
        })
    interactive = build_interactive_button_payload(
        body_text='Estos son los horarios disponibles. Elige uno:',
        buttons=buttons,
    )
    await _queue_interactive_message(
        conn,
        tenant_id=tenant_id,
        conversation_id=conversation['id'],
        channel_id=channel_id,
        channel_account_mode=channel_account_mode,
        body_text='Estos son los horarios disponibles. Elige uno:',
        interactive_payload=interactive,
        step=STEP_AWAITING_RESCHEDULE_SLOT,
    )
    return slots


async def _execute_cancel(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    conversation: Any,
    channel_id: UUID,
    channel_account_mode: str,
    appointment: dict[str, Any],
) -> None:
    await conn.execute(
        """
        update app.appointments
        set status='cancelled', updated_at=now()
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        appointment['id'],
    )
    try:
        await cancel_appointment_reminder_jobs(conn, tenant_id, appointment['id'])
    except Exception:
        log.exception(
            'self_service.cancel_jobs_failed',
            tenant_id=str(tenant_id),
            appointment_id=str(appointment['id']),
        )
    starts_at = appointment['starts_at'].astimezone(UTC)
    body = f'Listo, tu cita del {starts_at.strftime("%d/%m %H:%M")} se canceló.'
    await _queue_text_message(
        conn,
        tenant_id=tenant_id,
        conversation_id=conversation['id'],
        channel_id=channel_id,
        channel_account_mode=channel_account_mode,
        body_text=body,
        step=STEP_COMPLETED,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type='bot',
        actor_id='self_service',
        action='bot.appointment_cancelled',
        entity_type='appointment',
        entity_id=str(appointment['id']),
        metadata={
            'previous_starts_at': starts_at.isoformat(),
            'conversation_id': str(conversation['id']),
        },
    )


async def _execute_reschedule(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    conversation: Any,
    channel_id: UUID,
    channel_account_mode: str,
    appointment: dict[str, Any],
    slot: dict[str, str],
) -> bool:
    """Apply the reschedule. Returns ``True`` on success, ``False`` if the
    selected slot is no longer available (caller should re-offer slots)."""
    target_date = date.fromisoformat(slot['date'])
    hour, minute = (int(part) for part in slot['start_time'].split(':'))
    starts_at = datetime.combine(target_date, datetime.min.time()).replace(
        hour=hour, minute=minute, tzinfo=UTC
    )
    duration = max(
        int((appointment['ends_at'] - appointment['starts_at']).total_seconds() // 60),
        15,
    )
    ends_at = starts_at + timedelta(minutes=duration)
    previous_starts = appointment['starts_at'].astimezone(UTC)
    try:
        async with conn.transaction():
            await conn.execute(
                """
                update app.appointments
                set starts_at=$3, ends_at=$4, confirmation_status='pending', updated_at=now()
                where tenant_id=$1 and id=$2
                """,
                tenant_id,
                appointment['id'],
                starts_at,
                ends_at,
            )
    except Exception as exc:
        log.warning(
            'self_service.reschedule_conflict',
            tenant_id=str(tenant_id),
            appointment_id=str(appointment['id']),
            error=str(exc)[:200],
        )
        await _queue_text_message(
            conn,
            tenant_id=tenant_id,
            conversation_id=conversation['id'],
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
            body_text='Ese horario se acaba de ocupar. Te muestro otros disponibles.',
            step=STEP_AWAITING_RESCHEDULE_SLOT,
        )
        return False
    try:
        await regenerate_appointment_reminder_jobs(conn, tenant_id, appointment['id'])
    except Exception:
        log.exception(
            'self_service.regenerate_jobs_failed',
            tenant_id=str(tenant_id),
            appointment_id=str(appointment['id']),
        )
    body = (
        f'Listo. Tu cita quedó reagendada al '
        f'{target_date.strftime("%d/%m/%Y")} a las {slot["start_time"]}.'
    )
    await _queue_text_message(
        conn,
        tenant_id=tenant_id,
        conversation_id=conversation['id'],
        channel_id=channel_id,
        channel_account_mode=channel_account_mode,
        body_text=body,
        step=STEP_COMPLETED,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type='bot',
        actor_id='self_service',
        action='bot.appointment_rescheduled',
        entity_type='appointment',
        entity_id=str(appointment['id']),
        metadata={
            'previous_starts_at': previous_starts.isoformat(),
            'new_starts_at': starts_at.isoformat(),
            'conversation_id': str(conversation['id']),
        },
    )
    return True


async def _record_handled(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    conversation_id: UUID,
    inbound_message_id: UUID,
    *,
    flow: str,
    step: str,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        'flow': flow,
        'step': step,
        'inbound_message_id': str(inbound_message_id),
    }
    if extra:
        payload.update(extra)
    await conn.execute(
        """
        insert into app.domain_events (
          tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload
        )
        values ($1, 'conversation', $2, 'self_service.handled', $3, $4::jsonb)
        on conflict (tenant_id, idempotency_key) do nothing
        """,
        tenant_id,
        conversation_id,
        f'self_service:{inbound_message_id}',
        json.dumps(payload),
    )


async def start_auto_rebook_flow(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    channel_id: UUID,
    channel_account_mode: str,
    conversation: Any,
    appointment: dict[str, Any],
    inbound_message: Any,
) -> dict[str, Any]:
    """Trigger the reschedule sub-flow programmatically (TASK-0044).

    Used when the client replies "no" to the active confirmation and the tenant
    has ``notification_settings.auto_rebook_on_decline`` enabled. The empathic
    intro is sent first; if no alternative slot exists, the caller should run
    the normal handoff path.

    The persisted state is tagged with ``source='auto_rebook'`` so that a
    follow-up "no" mid-flow cancels the appointment and escalates instead of
    bouncing back to the start.
    """
    idempotency_key = f'self_service_auto_rebook:{inbound_message["id"]}'
    if await conn.fetchval(
        'select id from app.domain_events where tenant_id=$1 and idempotency_key=$2',
        tenant_id,
        idempotency_key,
    ):
        return {'action': 'skipped', 'reason': 'already_processed'}

    await _queue_text_message(
        conn,
        tenant_id=tenant_id,
        conversation_id=conversation['id'],
        channel_id=channel_id,
        channel_account_mode=channel_account_mode,
        body_text='Sin problema. ¿Quieres elegir otro horario?',
        step='auto_rebook_intro',
    )

    offered = await _present_reschedule_slots(
        conn,
        tenant_id=tenant_id,
        conversation=conversation,
        channel_id=channel_id,
        channel_account_mode=channel_account_mode,
        appointment=appointment,
    )
    if offered is None:
        await conn.execute(
            """
            insert into app.domain_events (
              tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload
            )
            values ($1, 'conversation', $2, 'self_service.handled', $3, $4::jsonb)
            on conflict (tenant_id, idempotency_key) do nothing
            """,
            tenant_id,
            conversation['id'],
            idempotency_key,
            json.dumps({
                'flow': FLOW_RESCHEDULE,
                'step': 'auto_rebook_no_slots',
                'appointment_id': str(appointment['id']),
            }),
        )
        return {
            'action': 'self_service_escalated',
            'reason': 'no_alternative_slots',
            'appointment_id': str(appointment['id']),
        }
    await _persist_state(
        conn,
        tenant_id,
        conversation,
        {
            'flow': FLOW_RESCHEDULE,
            'step': STEP_AWAITING_RESCHEDULE_SLOT,
            'appointment_id': str(appointment['id']),
            'offered_slots': offered,
            'source': 'auto_rebook',
        },
    )
    await conn.execute(
        """
        insert into app.domain_events (
          tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload
        )
        values ($1, 'conversation', $2, 'self_service.handled', $3, $4::jsonb)
        on conflict (tenant_id, idempotency_key) do nothing
        """,
        tenant_id,
        conversation['id'],
        idempotency_key,
        json.dumps({
            'flow': FLOW_RESCHEDULE,
            'step': STEP_AWAITING_RESCHEDULE_SLOT,
            'appointment_id': str(appointment['id']),
            'source': 'auto_rebook',
            'offered_count': len(offered),
        }),
    )
    log.info(
        'self_service.auto_rebook_started',
        tenant_id=str(tenant_id),
        appointment_id=str(appointment['id']),
        slots=len(offered),
    )
    return {
        'action': 'self_service_step_sent',
        'flow': FLOW_RESCHEDULE,
        'step': STEP_AWAITING_RESCHEDULE_SLOT,
        'source': 'auto_rebook',
    }


async def maybe_run_self_service_flow(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    channel_id: UUID,
    channel_account_mode: str,
    conversation: Any,
    contact: Any,
    inbound_message: Any,
    intent: str,
) -> dict[str, Any] | None:
    """Drive cancel/reschedule self-service.

    Returns a dict signalling what happened, or ``None`` if the inbound is
    unrelated. ``{'action': 'self_service_escalated'}`` is returned when the
    bot decides not to act (too close to start, paid appointment, no slots);
    the orchestrator should then run its normal handoff path.
    """
    state = _self_service_state(conversation)
    prefix, value = _interactive_id(inbound_message)
    is_mid_flow = bool(state) and state.get('step') != STEP_COMPLETED

    if not is_mid_flow and intent not in (INTENT_CANCEL, INTENT_RESCHEDULE):
        return None

    idempotency_key = f'self_service:{inbound_message["id"]}'
    if await conn.fetchval(
        'select id from app.domain_events where tenant_id=$1 and idempotency_key=$2',
        tenant_id,
        idempotency_key,
    ):
        return {'action': 'skipped', 'reason': 'already_processed'}

    # ── Mid-flow: process a button reply ────────────────────────────────────
    if is_mid_flow and state.get('appointment_id'):
        appointment_id = UUID(state['appointment_id'])
        appointment = await _fetch_appointment(conn, tenant_id, appointment_id)
        if not appointment:
            await _persist_state(conn, tenant_id, conversation, None)
            return None
        flow = state.get('flow')
        if flow == FLOW_CANCEL and prefix == PREFIX_CANCEL_CONFIRM:
            if value == 'yes':
                await _execute_cancel(
                    conn,
                    tenant_id=tenant_id,
                    conversation=conversation,
                    channel_id=channel_id,
                    channel_account_mode=channel_account_mode,
                    appointment=appointment,
                )
                await _persist_state(
                    conn,
                    tenant_id,
                    conversation,
                    {'flow': FLOW_CANCEL, 'step': STEP_COMPLETED,
                     'appointment_id': str(appointment_id)},
                )
                await _record_handled(
                    conn,
                    tenant_id,
                    conversation['id'],
                    inbound_message['id'],
                    flow=FLOW_CANCEL,
                    step=STEP_COMPLETED,
                    extra={'appointment_id': str(appointment_id)},
                )
                return {
                    'action': 'self_service_cancelled',
                    'appointment_id': str(appointment_id),
                }
            if value == 'no':
                await _queue_text_message(
                    conn,
                    tenant_id=tenant_id,
                    conversation_id=conversation['id'],
                    channel_id=channel_id,
                    channel_account_mode=channel_account_mode,
                    body_text='Listo, mantenemos tu cita como está. ¡Te esperamos!',
                    step=STEP_COMPLETED,
                )
                await _persist_state(conn, tenant_id, conversation, None)
                await _record_handled(
                    conn,
                    tenant_id,
                    conversation['id'],
                    inbound_message['id'],
                    flow=FLOW_CANCEL,
                    step='kept',
                )
                return {
                    'action': 'self_service_kept',
                    'appointment_id': str(appointment_id),
                }
        if (
            flow == FLOW_RESCHEDULE
            and state.get('source') == 'auto_rebook'
            and not prefix
            and inbound_message.get('body_text')
        ):
            from app.services.feedback_flow import parse_confirmation as _parse_conf

            decision = _parse_conf(inbound_message.get('body_text'))
            if decision == 'declined':
                await _execute_cancel(
                    conn,
                    tenant_id=tenant_id,
                    conversation=conversation,
                    channel_id=channel_id,
                    channel_account_mode=channel_account_mode,
                    appointment=appointment,
                )
                await _persist_state(conn, tenant_id, conversation, None)
                await _record_handled(
                    conn,
                    tenant_id,
                    conversation['id'],
                    inbound_message['id'],
                    flow=FLOW_RESCHEDULE,
                    step='auto_rebook_declined',
                    extra={
                        'appointment_id': str(appointment_id),
                        'source': 'auto_rebook',
                    },
                )
                return {
                    'action': 'self_service_escalated',
                    'reason': 'auto_rebook_declined',
                    'appointment_id': str(appointment_id),
                }
        if flow == FLOW_RESCHEDULE and prefix == PREFIX_RESCHED_SLOT:
            offered = state.get('offered_slots') or []
            try:
                idx = int(value)
            except (TypeError, ValueError):
                idx = -1
            if 0 <= idx < len(offered):
                slot = offered[idx]
                success = await _execute_reschedule(
                    conn,
                    tenant_id=tenant_id,
                    conversation=conversation,
                    channel_id=channel_id,
                    channel_account_mode=channel_account_mode,
                    appointment=appointment,
                    slot=slot,
                )
                if success:
                    await _persist_state(
                        conn,
                        tenant_id,
                        conversation,
                        {
                            'flow': FLOW_RESCHEDULE,
                            'step': STEP_COMPLETED,
                            'appointment_id': str(appointment_id),
                            'new_starts_at': f'{slot["date"]}T{slot["start_time"]}',
                        },
                    )
                    await _record_handled(
                        conn,
                        tenant_id,
                        conversation['id'],
                        inbound_message['id'],
                        flow=FLOW_RESCHEDULE,
                        step=STEP_COMPLETED,
                        extra={'appointment_id': str(appointment_id)},
                    )
                    return {
                        'action': 'self_service_rescheduled',
                        'appointment_id': str(appointment_id),
                        'new_starts_at': f'{slot["date"]}T{slot["start_time"]}',
                    }
                # Conflict: present fresh slots.
                refreshed_appointment = await _fetch_appointment(
                    conn, tenant_id, appointment_id
                )
                offered_again = await _present_reschedule_slots(
                    conn,
                    tenant_id=tenant_id,
                    conversation=conversation,
                    channel_id=channel_id,
                    channel_account_mode=channel_account_mode,
                    appointment=refreshed_appointment or appointment,
                ) or []
                await _persist_state(
                    conn,
                    tenant_id,
                    conversation,
                    {
                        'flow': FLOW_RESCHEDULE,
                        'step': STEP_AWAITING_RESCHEDULE_SLOT,
                        'appointment_id': str(appointment_id),
                        'offered_slots': offered_again,
                    },
                )
                await _record_handled(
                    conn,
                    tenant_id,
                    conversation['id'],
                    inbound_message['id'],
                    flow=FLOW_RESCHEDULE,
                    step='slot_conflict',
                )
                return {
                    'action': 'self_service_step_sent',
                    'flow': FLOW_RESCHEDULE,
                    'step': STEP_AWAITING_RESCHEDULE_SLOT,
                }
        # Mid-flow but couldn't parse the reply — re-present the same step.
        if flow == FLOW_CANCEL:
            await _present_cancel_confirmation(
                conn,
                tenant_id=tenant_id,
                conversation=conversation,
                channel_id=channel_id,
                channel_account_mode=channel_account_mode,
                appointment=appointment,
            )
        else:
            offered = await _present_reschedule_slots(
                conn,
                tenant_id=tenant_id,
                conversation=conversation,
                channel_id=channel_id,
                channel_account_mode=channel_account_mode,
                appointment=appointment,
            ) or []
            state['offered_slots'] = offered
            await _persist_state(conn, tenant_id, conversation, state)
        await _record_handled(
            conn,
            tenant_id,
            conversation['id'],
            inbound_message['id'],
            flow=flow or FLOW_CANCEL,
            step='retry',
        )
        return {
            'action': 'self_service_step_sent',
            'flow': flow,
            'step': state.get('step'),
            'retry': True,
        }

    # ── Fresh entry: classify which flow ────────────────────────────────────
    appointment = await _fetch_upcoming_appointment(conn, tenant_id, contact['id'])
    if not appointment:
        await _queue_text_message(
            conn,
            tenant_id=tenant_id,
            conversation_id=conversation['id'],
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
            body_text='No tengo una cita próxima registrada. ¿Quieres agendar una?',
            step=STEP_COMPLETED,
        )
        await _record_handled(
            conn,
            tenant_id,
            conversation['id'],
            inbound_message['id'],
            flow=FLOW_CANCEL if intent == INTENT_CANCEL else FLOW_RESCHEDULE,
            step='no_upcoming',
        )
        return {'action': 'self_service_no_appointment'}

    if appointment.get('payment_status') == 'paid':
        await _record_handled(
            conn,
            tenant_id,
            conversation['id'],
            inbound_message['id'],
            flow=FLOW_CANCEL if intent == INTENT_CANCEL else FLOW_RESCHEDULE,
            step='paid_escalate',
            extra={'appointment_id': str(appointment['id'])},
        )
        return {
            'action': 'self_service_escalated',
            'reason': 'paid_appointment',
            'appointment_id': str(appointment['id']),
        }

    if await _too_close_to_start(conn, tenant_id, appointment):
        await _record_handled(
            conn,
            tenant_id,
            conversation['id'],
            inbound_message['id'],
            flow=FLOW_CANCEL if intent == INTENT_CANCEL else FLOW_RESCHEDULE,
            step='too_close',
            extra={'appointment_id': str(appointment['id'])},
        )
        return {
            'action': 'self_service_escalated',
            'reason': 'too_close_to_start',
            'appointment_id': str(appointment['id']),
        }

    if intent == INTENT_CANCEL:
        await _present_cancel_confirmation(
            conn,
            tenant_id=tenant_id,
            conversation=conversation,
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
            appointment=appointment,
        )
        await _persist_state(
            conn,
            tenant_id,
            conversation,
            {
                'flow': FLOW_CANCEL,
                'step': STEP_AWAITING_CANCEL_CONFIRM,
                'appointment_id': str(appointment['id']),
            },
        )
        await _record_handled(
            conn,
            tenant_id,
            conversation['id'],
            inbound_message['id'],
            flow=FLOW_CANCEL,
            step=STEP_AWAITING_CANCEL_CONFIRM,
            extra={'appointment_id': str(appointment['id'])},
        )
        return {
            'action': 'self_service_step_sent',
            'flow': FLOW_CANCEL,
            'step': STEP_AWAITING_CANCEL_CONFIRM,
        }

    # Reschedule
    offered = await _present_reschedule_slots(
        conn,
        tenant_id=tenant_id,
        conversation=conversation,
        channel_id=channel_id,
        channel_account_mode=channel_account_mode,
        appointment=appointment,
    )
    if offered is None:
        await _record_handled(
            conn,
            tenant_id,
            conversation['id'],
            inbound_message['id'],
            flow=FLOW_RESCHEDULE,
            step='no_slots_escalate',
            extra={'appointment_id': str(appointment['id'])},
        )
        return {
            'action': 'self_service_escalated',
            'reason': 'no_alternative_slots',
            'appointment_id': str(appointment['id']),
        }
    await _persist_state(
        conn,
        tenant_id,
        conversation,
        {
            'flow': FLOW_RESCHEDULE,
            'step': STEP_AWAITING_RESCHEDULE_SLOT,
            'appointment_id': str(appointment['id']),
            'offered_slots': offered,
        },
    )
    await _record_handled(
        conn,
        tenant_id,
        conversation['id'],
        inbound_message['id'],
        flow=FLOW_RESCHEDULE,
        step=STEP_AWAITING_RESCHEDULE_SLOT,
        extra={
            'appointment_id': str(appointment['id']),
            'offered_count': len(offered),
        },
    )
    return {
        'action': 'self_service_step_sent',
        'flow': FLOW_RESCHEDULE,
        'step': STEP_AWAITING_RESCHEDULE_SLOT,
    }
