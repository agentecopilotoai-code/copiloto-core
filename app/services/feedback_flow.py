"""Detect and persist inbound replies for TASK-0036 flows.

When the bot sends a no-show confirmation request, the customer's reply
(``sí``/``no``) updates ``appointments.confirmation_status``. When the bot
sends a feedback request after the appointment, a numeric reply (1–5) is
persisted in ``appointment_feedback``.

The orchestrator calls ``handle_post_appointment_reply`` after intent
classification; it inspects ``conversations.metadata.last_bot_purpose`` or
correlation columns to decide which appointment the reply refers to. We keep
the logic simple: the most recent appointment for the contact is used.
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

if TYPE_CHECKING:
    import asyncpg

log = structlog.get_logger()


NEGATIVE_FEEDBACK_THRESHOLD = 2
NEGATIVE_FEEDBACK_TAG_NAME = 'Atención prioritaria'
NEGATIVE_FEEDBACK_TAG_COLOR = '#dc2626'
NEGATIVE_FEEDBACK_HANDOFF_REASON = 'negative_feedback'
DEFAULT_NEGATIVE_FEEDBACK_REPLY = (
    'Lamentamos mucho oír eso. Un agente se va a comunicar contigo enseguida.'
)


def _coerce_json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
    return value if isinstance(value, dict) else {}


def negative_feedback_reply(notification_settings: Any) -> str:
    settings = _coerce_json_dict(notification_settings)
    text = settings.get('negative_feedback_reply')
    if isinstance(text, str) and text.strip():
        return text.strip()
    return DEFAULT_NEGATIVE_FEEDBACK_REPLY


def is_negative_rating(rating: int | None) -> bool:
    return rating is not None and rating <= NEGATIVE_FEEDBACK_THRESHOLD


CONFIRM_PATTERNS = re.compile(
    r'\b(s[ií]|confirmo|confirmar|asisto|asistir[eé]|all[íi] estar[eé]|llegar[eé])\b',
    re.IGNORECASE,
)
DECLINE_PATTERNS = re.compile(
    r'\b(no\s*(puedo|asisto|asistir[eé]|voy)?|cancelar?|no podr[eé]|reagendar?|cambiar)\b',
    re.IGNORECASE,
)
RATING_PATTERN = re.compile(r'^\s*([1-5])\s*(?:[/⭐\*]|estrellas?)?\s*$', re.IGNORECASE)


def parse_rating(body_text: str | None) -> int | None:
    if not body_text:
        return None
    match = RATING_PATTERN.match(body_text.strip())
    if not match:
        return None
    return int(match.group(1))


def parse_confirmation(body_text: str | None) -> str | None:
    """Return 'confirmed' for affirmative, 'declined' for negative, else None."""
    if not body_text:
        return None
    text = body_text.strip().lower()
    if CONFIRM_PATTERNS.search(text):
        return 'confirmed'
    if DECLINE_PATTERNS.search(text):
        return 'declined'
    return None


async def _latest_appointment_for_contact(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    contact_id: UUID,
    statuses: tuple[str, ...],
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, starts_at, ends_at, status, confirmation_status
        from app.appointments
        where tenant_id=$1 and contact_id=$2 and status = any($3::text[])
        order by starts_at desc
        limit 1
        """,
        tenant_id,
        contact_id,
        list(statuses),
    )
    return dict(row) if row else None


async def _ensure_negative_feedback_tag(
    conn: asyncpg.Connection, tenant_id: UUID
) -> UUID:
    """Return the id of the ``Atención prioritaria`` tag for the tenant,
    creating it if it doesn't exist yet. Idempotent by ``(tenant_id, name)``."""
    await conn.execute(
        """
        insert into app.contact_tags (tenant_id, name, color, description)
        values ($1, $2, $3, $4)
        on conflict (tenant_id, name) do nothing
        """,
        tenant_id,
        NEGATIVE_FEEDBACK_TAG_NAME,
        NEGATIVE_FEEDBACK_TAG_COLOR,
        'Cliente con feedback negativo — requiere service recovery.',
    )
    return await conn.fetchval(
        'select id from app.contact_tags where tenant_id=$1 and name=$2',
        tenant_id,
        NEGATIVE_FEEDBACK_TAG_NAME,
    )


async def _queue_text_message_for_negative_feedback(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    conversation: Any,
    channel_id: UUID,
    channel_account_mode: str,
    body_text: str,
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
        conversation['id'],
        body_text,
        json.dumps({'negative_feedback_reply': True}),
    )
    idempotency_key = f'bot_negative_feedback:{row["id"]}'
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
            'conversation_id': str(conversation['id']),
            'channel_id': str(channel_id),
            'channel_account_mode': channel_account_mode,
            'body_text': body_text,
        }),
    )
    return row['id']


async def _escalate_negative_feedback(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    contact_id: UUID,
    appointment_id: UUID,
    feedback_id: UUID,
    rating: int,
    comment: str | None,
    conversation: Any | None,
    channel_id: UUID | None,
    channel_account_mode: str | None,
) -> dict[str, Any]:
    """Mark the conversation for human handoff, tag the contact, emit the
    domain event and send the empathic reply. Returns the trace of what was
    actually applied so the orchestrator can short-circuit replies."""
    trace: dict[str, Any] = {
        'tag_assigned': False,
        'handoff_marked': False,
        'reply_sent': False,
        'event_emitted': False,
    }

    tag_id = await _ensure_negative_feedback_tag(conn, tenant_id)
    if tag_id is not None:
        await conn.execute(
            """
            insert into app.contact_tag_assignments (tenant_id, contact_id, tag_id)
            values ($1, $2, $3)
            on conflict (contact_id, tag_id) do nothing
            """,
            tenant_id,
            contact_id,
            tag_id,
        )
        trace['tag_assigned'] = True
        trace['tag_id'] = str(tag_id)

    if conversation is not None:
        await conn.execute(
            """
            update app.conversations
            set handoff_required=true,
                status=case when status in ('human_active') then status else 'waiting_agent' end,
                updated_at=now()
            where tenant_id=$1 and id=$2
            """,
            tenant_id,
            conversation['id'],
        )
        existing = await conn.fetchrow(
            """
            select id from app.handoffs
            where tenant_id=$1 and conversation_id=$2 and status='open'
            order by created_at desc limit 1
            """,
            tenant_id,
            conversation['id'],
        )
        if not existing:
            await conn.execute(
                """
                insert into app.handoffs (tenant_id, conversation_id, reason, status)
                values ($1, $2, $3, 'open')
                """,
                tenant_id,
                conversation['id'],
                NEGATIVE_FEEDBACK_HANDOFF_REASON,
            )
        trace['handoff_marked'] = True

    notification_settings = await conn.fetchval(
        'select notification_settings from app.tenant_settings where tenant_id=$1',
        tenant_id,
    )
    reply_text = negative_feedback_reply(notification_settings)
    if conversation is not None and channel_id is not None:
        await _queue_text_message_for_negative_feedback(
            conn,
            tenant_id=tenant_id,
            conversation=conversation,
            channel_id=channel_id,
            channel_account_mode=channel_account_mode or 'mock',
            body_text=reply_text,
        )
        trace['reply_sent'] = True
        trace['reply_text'] = reply_text

    idempotency_key = f'feedback.negative_received:{feedback_id}'
    await conn.execute(
        """
        insert into app.domain_events (
          tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload
        )
        values ($1, 'appointment', $2, 'feedback.negative_received', $3, $4::jsonb)
        on conflict (tenant_id, idempotency_key) do nothing
        """,
        tenant_id,
        appointment_id,
        idempotency_key,
        json.dumps({
            'appointment_id': str(appointment_id),
            'feedback_id': str(feedback_id),
            'contact_id': str(contact_id),
            'rating': rating,
            'comment': comment,
            'handoff_reason': NEGATIVE_FEEDBACK_HANDOFF_REASON,
        }),
    )
    trace['event_emitted'] = True

    log.info(
        'feedback.negative_escalated',
        tenant_id=str(tenant_id),
        appointment_id=str(appointment_id),
        rating=rating,
        feedback_id=str(feedback_id),
    )
    return trace


async def maybe_record_feedback(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    contact_id: UUID,
    inbound_message: Any,
    conversation: Any | None = None,
    channel_id: UUID | None = None,
    channel_account_mode: str | None = None,
) -> dict[str, Any] | None:
    """Record a 1–5 rating reply when an appointment recently ended.

    TASK-0045: if ``rating <= 2`` also escalate to a human (tag the contact
    with ``Atención prioritaria``, mark the conversation for handoff with
    ``reason='negative_feedback'``, send an empathic reply and emit the
    ``feedback.negative_received`` domain event).
    """
    rating = parse_rating(inbound_message.get('body_text'))
    if rating is None:
        return None
    appt = await _latest_appointment_for_contact(
        conn,
        tenant_id,
        contact_id,
        statuses=('completed', 'scheduled', 'confirmed'),
    )
    if not appt:
        return None
    row = await conn.fetchrow(
        """
        insert into app.appointment_feedback
          (tenant_id, appointment_id, contact_id, rating, comment)
        values ($1, $2, $3, $4, $5)
        returning id
        """,
        tenant_id,
        appt['id'],
        contact_id,
        rating,
        inbound_message.get('body_text'),
    )
    log.info(
        'feedback.recorded',
        tenant_id=str(tenant_id),
        appointment_id=str(appt['id']),
        rating=rating,
        feedback_id=str(row['id']),
    )
    result: dict[str, Any] = {
        'action': 'feedback_recorded',
        'appointment_id': str(appt['id']),
        'feedback_id': str(row['id']),
        'rating': rating,
    }
    if is_negative_rating(rating):
        escalation = await _escalate_negative_feedback(
            conn,
            tenant_id=tenant_id,
            contact_id=contact_id,
            appointment_id=appt['id'],
            feedback_id=row['id'],
            rating=rating,
            comment=inbound_message.get('body_text'),
            conversation=conversation,
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
        )
        result['negative_escalation'] = escalation
        result['action'] = 'feedback_negative_escalated'
    return result


def auto_rebook_enabled(notification_settings: Any) -> bool:
    """Read the ``auto_rebook_on_decline`` toggle from notification settings.

    Defaults to ``True`` so customers who decline are offered alternatives
    even before the tenant explicitly turns the feature on.
    """
    settings = notification_settings
    if isinstance(settings, str):
        import json as _json
        try:
            settings = _json.loads(settings)
        except (ValueError, TypeError):
            settings = {}
    if not isinstance(settings, dict):
        return True
    if 'auto_rebook_on_decline' not in settings:
        return True
    value = settings.get('auto_rebook_on_decline')
    if value is None:
        return True
    return bool(value)


async def maybe_record_confirmation(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    contact_id: UUID,
    inbound_message: Any,
    conversation: Any | None = None,
    channel_id: UUID | None = None,
    channel_account_mode: str | None = None,
) -> dict[str, Any] | None:
    """Apply confirmation_status updates from a 'sí'/'no' reply.

    TASK-0044: when the decision is ``declined`` and the tenant has
    ``notification_settings.auto_rebook_on_decline`` enabled (default ``True``),
    triggers the reschedule sub-flow (see
    ``appointment_self_service.start_auto_rebook_flow``) so the customer can
    pick another time without involving a human. The caller must pass the
    conversation, channel_id and channel_account_mode so the bot can reply on
    the same channel.
    """
    decision = parse_confirmation(inbound_message.get('body_text'))
    if decision is None:
        return None
    # When the conversation already has an active self-service flow (e.g.
    # auto-rebook just offered slots), let that flow handle the reply instead
    # of re-running confirmation. Otherwise a "no" mid-rebook would loop the
    # client back into another rebooking.
    if conversation is not None:
        import json as _json

        raw_meta = conversation.get('metadata')
        if isinstance(raw_meta, str):
            try:
                raw_meta = _json.loads(raw_meta)
            except (ValueError, TypeError):
                raw_meta = None
        if isinstance(raw_meta, dict):
            self_service_state = raw_meta.get('self_service')
            if (
                isinstance(self_service_state, dict)
                and self_service_state.get('step') not in (None, 'completed')
            ):
                return None
    appt = await _latest_appointment_for_contact(
        conn,
        tenant_id,
        contact_id,
        statuses=('scheduled', 'confirmed'),
    )
    if not appt:
        return None
    await conn.execute(
        """
        update app.appointments
        set confirmation_status=$3, updated_at=now()
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        appt['id'],
        decision,
    )
    log.info(
        'feedback.confirmation_updated',
        tenant_id=str(tenant_id),
        appointment_id=str(appt['id']),
        decision=decision,
    )
    result: dict[str, Any] = {
        'action': 'confirmation_recorded',
        'appointment_id': str(appt['id']),
        'confirmation_status': decision,
    }

    if decision == 'declined' and conversation is not None and channel_id is not None:
        notification_settings = await conn.fetchval(
            'select notification_settings from app.tenant_settings where tenant_id=$1',
            tenant_id,
        )
        if auto_rebook_enabled(notification_settings):
            from app.services.appointment_self_service import (
                _fetch_appointment,
                start_auto_rebook_flow,
            )

            appointment = await _fetch_appointment(conn, tenant_id, appt['id'])
            if appointment is not None:
                rebook = await start_auto_rebook_flow(
                    conn,
                    tenant_id=tenant_id,
                    channel_id=channel_id,
                    channel_account_mode=channel_account_mode or 'mock',
                    conversation=conversation,
                    appointment=appointment,
                    inbound_message=inbound_message,
                )
                result['auto_rebook'] = rebook
    return result
