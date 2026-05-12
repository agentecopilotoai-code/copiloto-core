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

import re
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

if TYPE_CHECKING:
    import asyncpg

log = structlog.get_logger()


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


async def maybe_record_feedback(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    contact_id: UUID,
    inbound_message: Any,
) -> dict[str, Any] | None:
    """Record a 1–5 rating reply when an appointment recently ended."""
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
    return {
        'action': 'feedback_recorded',
        'appointment_id': str(appt['id']),
        'feedback_id': str(row['id']),
        'rating': rating,
    }


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
