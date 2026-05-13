"""TASK-0062: doble opt-in + ledger auditable de autorizaciones.

This module enforces Ley 1581 / GDPR consent rules for inbound WhatsApp
traffic.  The orchestrator calls :func:`enforce_inbound_consent` before any
business flow runs.  Behaviour:

* If the inbound payload is a reply to the consent template (``consent:yes``
  or ``consent:no``) the ledger receives a ``granted`` / ``revoked`` row,
  the contact's ``opt_in_status`` is updated, and an outbound thank-you /
  goodbye message is queued.
* If the contact has ``opt_in_status='unknown'`` (never accepted, never
  rejected) the consent_request template is queued and the inbound message
  is **not** forwarded to the business flow.  The orchestrator must skip.
* Otherwise this function returns ``None`` and the orchestrator continues
  with the existing flow (opt-in granted or already revoked).

The :class:`ConsentDecision` returned encodes the outcome.  ``handled=True``
means the orchestrator must stop here.

Reaffirmation jobs are enqueued by :func:`enqueue_consent_reaffirmations`
which the scheduler runs once per loop.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog

log = structlog.get_logger()


CONSENT_PREFIX = 'consent'
CONSENT_BUTTON_YES = f'{CONSENT_PREFIX}:yes'
CONSENT_BUTTON_NO = f'{CONSENT_PREFIX}:no'

CONSENT_REQUEST_BODY = (
    'Hola, somos {business_name}. Para responder por WhatsApp necesitamos '
    'tu autorización para tratar tus datos personales (Ley 1581 de 2012). '
    '¿Aceptas que te contactemos por este canal para gestionar tus citas y '
    'consultas?'
)
CONSENT_REQUEST_PURPOSE = 'consent_request'
CONSENT_REAFFIRM_PURPOSE = 'consent_reaffirm'
CONSENT_LEGAL_BASIS = 'Ley 1581 de 2012 (Decreto 1377), art. 9 — autorización del titular'
CONSENT_PURPOSE_TEXT = (
    'Gestionar citas, recordatorios, seguimientos y comunicaciones operativas '
    'del servicio contratado por el canal WhatsApp.'
)

REAFFIRM_INTERVAL_MONTHS_DEFAULT = 12

THANKS_GRANTED = (
    '¡Gracias! Quedó registrada tu autorización. Ya puedo ayudarte por aquí.'
)
THANKS_REVOKED = (
    'Entendido, no te molestaremos. Si cambias de opinión, escríbenos otra vez.'
)
AWAITING_CONSENT_BODY = (
    'Necesitamos tu autorización para continuar. Por favor responde el mensaje '
    'anterior con "Acepto" o "No acepto".'
)


def _parse_payload(raw: object) -> dict[str, Any]:
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return raw if isinstance(raw, dict) else {}


def _interactive_id(inbound_message: Any) -> str | None:
    """Return the ``interactive_id`` carried by an inbound interactive reply."""
    payload = _parse_payload(inbound_message.get('payload') if isinstance(inbound_message, dict) else None)
    interactive_id = payload.get('interactive_id')
    return interactive_id if isinstance(interactive_id, str) else None


def is_consent_reply(inbound_message: Any) -> bool:
    """True iff the inbound message is the user's tap on the consent template."""
    iid = _interactive_id(inbound_message)
    return iid in (CONSENT_BUTTON_YES, CONSENT_BUTTON_NO)


def build_consent_request_payload(business_name: str) -> dict[str, Any]:
    """Build the interactive button payload for the double opt-in template.

    Falls back to a plain interactive button shape so the WhatsApp worker
    can ship it via the regular outbound path even before the Meta-approved
    template exists in the templates table.  The scheduler-driven path
    (reaffirmation) does require an approved template.
    """
    body_text = CONSENT_REQUEST_BODY.format(business_name=business_name or 'nuestro negocio')
    return {
        'type': 'button',
        'body': {'text': body_text},
        'action': {
            'buttons': [
                {'type': 'reply', 'reply': {'id': CONSENT_BUTTON_YES, 'title': 'Acepto'}},
                {'type': 'reply', 'reply': {'id': CONSENT_BUTTON_NO, 'title': 'No acepto'}},
            ],
        },
    }


@dataclass
class ConsentDecision:
    """Outcome of :func:`enforce_inbound_consent`.

    ``handled`` indicates the orchestrator must stop processing the inbound.
    ``reason`` is a short stable string suitable for logging / observability.
    """

    handled: bool
    reason: str
    outbound_message_id: UUID | None = None
    ledger_event_id: UUID | None = None


async def _queue_consent_outbound(
    conn: Any,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    channel_id: UUID,
    channel_account_mode: str,
    body_text: str,
    interactive_payload: dict[str, Any] | None,
    step: str,
) -> UUID:
    message_type = 'interactive' if interactive_payload else 'text'
    trace: dict[str, Any] = {'consent_step': step}
    if interactive_payload:
        trace['interactive'] = interactive_payload
    row = await conn.fetchrow(
        """
        insert into app.messages (
          tenant_id, conversation_id, direction, sender_actor_type,
          body_text, message_type, status, payload
        )
        values ($1, $2, 'outbound', 'bot', $3, $4, 'queued', $5::jsonb)
        returning id
        """,
        tenant_id,
        conversation_id,
        body_text,
        message_type,
        json.dumps(trace),
    )
    idempotency_key = f'consent_{step}:{row["id"]}'
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
            'consent_step': step,
        }),
    )
    return row['id']


async def record_consent_event(
    conn: Any,
    *,
    tenant_id: UUID,
    contact_id: UUID,
    event: str,
    channel: str,
    copy_shown: str,
    legal_basis: str = CONSENT_LEGAL_BASIS,
    purpose: str = CONSENT_PURPOSE_TEXT,
    evidence_payload: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
) -> UUID:
    """Append a single row to ``app.consent_ledger``.

    The trigger ``trg_consent_ledger_no_update`` makes this table
    append-only; this function is the only writer used in production code.
    """
    if event not in ('granted', 'revoked', 'reaffirmed', 'suppressed'):
        raise ValueError(f'invalid consent event: {event!r}')
    if channel not in ('whatsapp', 'web', 'admin', 'import'):
        raise ValueError(f'invalid consent channel: {channel!r}')
    payload_json = json.dumps(evidence_payload or {})
    row = await conn.fetchrow(
        """
        insert into app.consent_ledger (
          tenant_id, contact_id, event, channel,
          legal_basis, purpose, copy_shown, evidence_payload, ip, user_agent
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8::jsonb, $9::inet, $10)
        returning id
        """,
        tenant_id,
        contact_id,
        event,
        channel,
        legal_basis,
        purpose,
        copy_shown,
        payload_json,
        ip,
        user_agent,
    )
    return row['id']


async def enforce_inbound_consent(
    conn: Any,
    *,
    tenant_id: UUID,
    channel_id: UUID,
    channel_account_mode: str,
    conversation: Any,
    contact: Any,
    inbound_message: Any,
    business_name: str,
) -> ConsentDecision | None:
    """Gate inbound traffic on consent.

    Returns:
        * ``ConsentDecision(handled=True, ...)`` when the orchestrator must
          skip the rest of the business flow (consent template just sent,
          opt-in just granted, opt-out just registered, or contact already
          revoked).
        * ``ConsentDecision(handled=False, ...)`` after a successful
          ``granted`` so the orchestrator could chain the regular reply if
          desired (currently the orchestrator stops on ``handled=True``).
        * ``None`` when consent was already granted previously and the
          orchestrator should proceed with the normal flow.
    """
    opt_in = (contact.get('opt_in_status') if isinstance(contact, dict) else None) or 'unknown'
    contact_id = contact['id']
    conversation_id = conversation['id']
    inbound_payload = _parse_payload(inbound_message.get('payload') if isinstance(inbound_message, dict) else None)
    interactive_id = inbound_payload.get('interactive_id') if isinstance(inbound_payload, dict) else None

    # Consent reply ─ "Acepto" / "No acepto".
    if interactive_id == CONSENT_BUTTON_YES:
        copy_shown = CONSENT_REQUEST_BODY.format(business_name=business_name or 'nuestro negocio')
        ledger_id = await record_consent_event(
            conn,
            tenant_id=tenant_id,
            contact_id=contact_id,
            event='granted',
            channel='whatsapp',
            copy_shown=copy_shown,
            evidence_payload={
                'inbound_message_id': str(inbound_message['id']),
                'conversation_id': str(conversation_id),
                'button_id': CONSENT_BUTTON_YES,
            },
        )
        await conn.execute(
            """
            update app.contacts
            set opt_in_status='granted', opt_in_at=now(), updated_at=now()
            where tenant_id=$1 and id=$2
            """,
            tenant_id,
            contact_id,
        )
        outbound_id = await _queue_consent_outbound(
            conn,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
            body_text=THANKS_GRANTED,
            interactive_payload=None,
            step='granted_ack',
        )
        log.info(
            'consent.granted',
            tenant_id=str(tenant_id),
            contact_id=str(contact_id),
            conversation_id=str(conversation_id),
            ledger_event_id=str(ledger_id),
        )
        return ConsentDecision(
            handled=True,
            reason='consent_granted',
            outbound_message_id=outbound_id,
            ledger_event_id=ledger_id,
        )

    if interactive_id == CONSENT_BUTTON_NO:
        copy_shown = CONSENT_REQUEST_BODY.format(business_name=business_name or 'nuestro negocio')
        ledger_id = await record_consent_event(
            conn,
            tenant_id=tenant_id,
            contact_id=contact_id,
            event='revoked',
            channel='whatsapp',
            copy_shown=copy_shown,
            evidence_payload={
                'inbound_message_id': str(inbound_message['id']),
                'conversation_id': str(conversation_id),
                'button_id': CONSENT_BUTTON_NO,
            },
        )
        await conn.execute(
            """
            update app.contacts
            set opt_in_status='revoked', opt_out_at=now(), updated_at=now()
            where tenant_id=$1 and id=$2
            """,
            tenant_id,
            contact_id,
        )
        outbound_id = await _queue_consent_outbound(
            conn,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
            body_text=THANKS_REVOKED,
            interactive_payload=None,
            step='revoked_ack',
        )
        await conn.execute(
            """
            update app.conversations
            set status='closed', updated_at=now()
            where tenant_id=$1 and id=$2
            """,
            tenant_id,
            conversation_id,
        )
        log.info(
            'consent.revoked_by_button',
            tenant_id=str(tenant_id),
            contact_id=str(contact_id),
            conversation_id=str(conversation_id),
            ledger_event_id=str(ledger_id),
        )
        return ConsentDecision(
            handled=True,
            reason='consent_revoked',
            outbound_message_id=outbound_id,
            ledger_event_id=ledger_id,
        )

    # First-ever inbound from a brand-new contact ─ send the double opt-in.
    if opt_in == 'unknown':
        interactive_payload = build_consent_request_payload(business_name)
        outbound_id = await _queue_consent_outbound(
            conn,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
            body_text=CONSENT_REQUEST_BODY.format(business_name=business_name or 'nuestro negocio'),
            interactive_payload=interactive_payload,
            step='request',
        )
        log.info(
            'consent.request_sent',
            tenant_id=str(tenant_id),
            contact_id=str(contact_id),
            conversation_id=str(conversation_id),
        )
        return ConsentDecision(
            handled=True,
            reason='consent_request_sent',
            outbound_message_id=outbound_id,
        )

    # Contact already opted out — bot stays silent.
    if opt_in in ('revoked', 'suppressed'):
        log.info(
            'consent.skip_revoked',
            tenant_id=str(tenant_id),
            contact_id=str(contact_id),
            conversation_id=str(conversation_id),
            opt_in_status=opt_in,
        )
        return ConsentDecision(handled=True, reason=f'contact_opt_in_{opt_in}')

    # opt_in == 'granted' → fall through, orchestrator continues normally.
    return None


async def record_opt_out_by_keyword(
    conn: Any,
    *,
    tenant_id: UUID,
    contact_id: UUID,
    inbound_message: Any,
) -> UUID:
    """TASK-0062: keyword-based opt-out path also writes to the ledger.

    The intent classifier matched ``INTENT_OPT_OUT`` so the user typed
    something like "STOP", "BAJA", "CANCELAR SUSCRIPCION".  We persist the
    raw text as ``copy_shown`` so the audit trail keeps the exact words the
    customer used.
    """
    body = inbound_message['body_text'] if isinstance(inbound_message, dict) else ''
    body = body or ''
    return await record_consent_event(
        conn,
        tenant_id=tenant_id,
        contact_id=contact_id,
        event='revoked',
        channel='whatsapp',
        copy_shown=body[:500],
        evidence_payload={
            'inbound_message_id': str(inbound_message['id']),
            'source': 'opt_out_keyword',
        },
    )


async def enqueue_consent_reaffirmations(
    conn: Any,
    *,
    interval_months: int = REAFFIRM_INTERVAL_MONTHS_DEFAULT,
    limit: int = 50,
) -> int:
    """Pick contacts whose latest consent is older than ``interval_months``
    and enqueue a ``reminder_jobs`` row with ``purpose=consent_reaffirm``.

    The scheduler dispatches only purposes backed by an approved
    ``whatsapp_templates`` row (see ``_has_approved_template``).  Tenants
    without an approved ``consent_reaffirm`` template will see the job marked
    ``failed`` with ``template_not_approved:consent_reaffirm`` — which is the
    expected behaviour until they upload one.

    Returns the count of enqueued rows.
    """
    if interval_months <= 0:
        return 0
    rows = await conn.fetch(
        f"""
        with latest as (
          select tenant_id, contact_id, max(occurred_at) as last_at
          from app.consent_ledger
          where event in ('granted','reaffirmed')
          group by tenant_id, contact_id
        ),
        already_queued as (
          select tenant_id, target_id
          from app.reminder_jobs
          where status in ('pending','processing')
            and (payload->>'purpose') = '{CONSENT_REAFFIRM_PURPOSE}'
        )
        select c.tenant_id, c.id as contact_id,
               (select id from app.tenant_channels tc
                 where tc.tenant_id = c.tenant_id
                   and tc.provider = 'whatsapp_cloud_api'
                 order by created_at limit 1) as channel_id
          from app.contacts c
          join latest l on l.tenant_id = c.tenant_id and l.contact_id = c.id
         where c.opt_in_status = 'granted'
           and l.last_at < now() - make_interval(months => $1)
           and not exists (
             select 1 from already_queued aq
              where aq.tenant_id = c.tenant_id
                and aq.target_id = c.id
           )
         limit $2
        """,
        interval_months,
        limit,
    )
    enqueued = 0
    for row in rows:
        if row['channel_id'] is None:
            continue
        await conn.execute(
            """
            insert into app.reminder_jobs (
              tenant_id, target_type, target_id, channel_id,
              template_name, template_locale, payload, scheduled_for
            )
            values ($1, 'contact', $2, $3, 'consent_reaffirm', 'es', $4::jsonb, now())
            """,
            row['tenant_id'],
            row['contact_id'],
            row['channel_id'],
            json.dumps({
                'purpose': CONSENT_REAFFIRM_PURPOSE,
                'contact_id': str(row['contact_id']),
                'reason': 'consent_age_threshold',
                'interval_months': interval_months,
            }),
        )
        enqueued += 1
    if enqueued:
        log.info('consent.reaffirm_enqueued', count=enqueued, interval_months=interval_months)
    return enqueued
