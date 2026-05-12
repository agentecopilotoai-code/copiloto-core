"""Conversational pre-booking qualification flow (TASK-0042).

When the tenant has at least one configured ``qualification_question``, this
flow runs **before** ``booking_flow.maybe_run_booking_flow`` to gather the
answers needed to route the customer to the right service. Persists state in
``conversations.metadata.qualification`` and snapshots the last completed set
of answers in ``contacts.qualification``.

Render rules over WhatsApp:
- ``yes_no``                  → 2-button interactive (Sí / No).
- ``single_choice``  (≤3)     → button interactive.
- ``single_choice``  (>3)     → list interactive (up to 10 rows).
- ``multi_choice``            → list interactive (one option per reply, the
                                 user can keep replying until ``listo``).
- ``free_text`` / ``number``  → plain text request with input validation.
"""
from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from app.services.audit import audit
from app.services.whatsapp import (
    build_interactive_button_payload,
    build_interactive_list_payload,
)

if TYPE_CHECKING:
    import asyncpg

log = structlog.get_logger()


PREFIX_QUALIFY = 'qualify'
DONE_TOKEN = 'done'

KIND_FREE_TEXT = 'free_text'
KIND_SINGLE_CHOICE = 'single_choice'
KIND_MULTI_CHOICE = 'multi_choice'
KIND_YES_NO = 'yes_no'
KIND_NUMBER = 'number'

INTERACTIVE_KINDS = {KIND_SINGLE_CHOICE, KIND_MULTI_CHOICE, KIND_YES_NO}
TEXT_KINDS = {KIND_FREE_TEXT, KIND_NUMBER}

OPT_OUT_PATTERN = re.compile(r'^\s*(stop|baja|cancelar)\s*$', re.IGNORECASE)
NUMBER_PATTERN = re.compile(r'^-?\d+([.,]\d+)?$')


BOOKING_TRIGGER_INTENTS = {'book_appointment', 'check_availability'}


def _parse_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return fallback
    return value if value is not None else fallback


def _qualification_state(conversation: Any) -> dict[str, Any]:
    meta = _parse_json(conversation.get('metadata'), {})
    if not isinstance(meta, dict):
        return {}
    state = meta.get('qualification')
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


async def _list_questions(
    conn: asyncpg.Connection, tenant_id: UUID
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select id, position, label, kind, options, required, applies_to_service_ids
        from app.qualification_questions
        where tenant_id=$1
        order by position asc, created_at asc
        """,
        tenant_id,
    )
    questions: list[dict[str, Any]] = []
    for row in rows:
        question = dict(row)
        question['options'] = _parse_json(question.get('options'), []) or []
        questions.append(question)
    return questions


def _options_for_render(question: dict[str, Any]) -> list[dict[str, str]]:
    """Return ``[{value, label}, ...]`` for choice-style questions."""
    options = question.get('options') or []
    normalized: list[dict[str, str]] = []
    for option in options:
        if not isinstance(option, dict):
            continue
        value = str(option.get('value') or option.get('id') or '').strip()
        label = str(option.get('label') or value).strip()
        if not value:
            continue
        normalized.append({'value': value, 'label': label[:24] or value[:24]})
    return normalized


def _next_pending_question(
    questions: list[dict[str, Any]], answered: dict[str, Any]
) -> dict[str, Any] | None:
    for question in questions:
        qid = str(question['id'])
        if qid in answered:
            continue
        if question.get('required') is False and answered.get(qid) is False:
            continue
        return question
    return None


def _validate_text_reply(question: dict[str, Any], body_text: str) -> Any | None:
    text = body_text.strip()
    if not text:
        return None
    if question['kind'] == KIND_NUMBER:
        if not NUMBER_PATTERN.match(text):
            return None
        try:
            return float(text.replace(',', '.'))
        except ValueError:
            return None
    return text


def _match_choice(question: dict[str, Any], raw_value: str) -> str | None:
    options = _options_for_render(question)
    if not options:
        return None
    candidate = raw_value.strip()
    for option in options:
        if option['value'] == candidate:
            return option['value']
    candidate_lower = candidate.lower()
    for option in options:
        if option['label'].lower() == candidate_lower:
            return option['value']
    return None


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
        json.dumps({'qualification_step': step}),
    )
    idempotency_key = f'bot_qualify_text:{row["id"]}'
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
            'qualification_step': step,
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
    payload = {'interactive': interactive_payload, 'qualification_step': step}
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
    idempotency_key = f'bot_qualify:{row["id"]}'
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
            'qualification_step': step,
        }),
    )
    return row['id']


async def _present_question(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    conversation: Any,
    channel_id: UUID,
    channel_account_mode: str,
    question: dict[str, Any],
) -> None:
    qid = str(question['id'])
    kind = question['kind']
    label = question['label']

    if kind == KIND_YES_NO:
        interactive = build_interactive_button_payload(
            body_text=label,
            buttons=[
                {'id': f'{PREFIX_QUALIFY}:{qid}:yes', 'title': 'Sí'},
                {'id': f'{PREFIX_QUALIFY}:{qid}:no', 'title': 'No'},
            ],
        )
        await _queue_interactive_message(
            conn,
            tenant_id=tenant_id,
            conversation_id=conversation['id'],
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
            body_text=label,
            interactive_payload=interactive,
            step=f'q:{qid}',
        )
        return

    if kind in {KIND_SINGLE_CHOICE, KIND_MULTI_CHOICE}:
        options = _options_for_render(question)
        if not options:
            await _queue_text_message(
                conn,
                tenant_id=tenant_id,
                conversation_id=conversation['id'],
                channel_id=channel_id,
                channel_account_mode=channel_account_mode,
                body_text=label,
                step=f'q:{qid}',
            )
            return
        body_text = label
        if kind == KIND_MULTI_CHOICE:
            body_text = f'{label}\n(Puedes elegir varias. Responde "listo" cuando termines.)'
        if len(options) <= 3 and kind == KIND_SINGLE_CHOICE:
            interactive = build_interactive_button_payload(
                body_text=body_text,
                buttons=[
                    {
                        'id': f'{PREFIX_QUALIFY}:{qid}:{option["value"]}',
                        'title': option['label'][:20],
                    }
                    for option in options
                ],
            )
        else:
            rows = [
                {
                    'id': f'{PREFIX_QUALIFY}:{qid}:{option["value"]}',
                    'title': option['label'][:24],
                }
                for option in options[:10]
            ]
            if kind == KIND_MULTI_CHOICE:
                rows.append({
                    'id': f'{PREFIX_QUALIFY}:{qid}:{DONE_TOKEN}',
                    'title': 'Listo',
                })
            interactive = build_interactive_list_payload(
                body_text=body_text,
                button_label='Ver opciones',
                sections=[{'title': 'Opciones', 'rows': rows}],
            )
        await _queue_interactive_message(
            conn,
            tenant_id=tenant_id,
            conversation_id=conversation['id'],
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
            body_text=body_text,
            interactive_payload=interactive,
            step=f'q:{qid}',
        )
        return

    # free_text / number → plain text request
    prompt = label
    if kind == KIND_NUMBER:
        prompt = f'{label}\n(Responde con un número, por ejemplo: 3)'
    await _queue_text_message(
        conn,
        tenant_id=tenant_id,
        conversation_id=conversation['id'],
        channel_id=channel_id,
        channel_account_mode=channel_account_mode,
        body_text=prompt,
        step=f'q:{qid}',
    )


def _derive_recommended_service(
    questions: list[dict[str, Any]], answered: dict[str, Any]
) -> str | None:
    """Pick the first single_choice answer whose option carries
    ``service_id``."""
    for question in questions:
        if question['kind'] != KIND_SINGLE_CHOICE:
            continue
        qid = str(question['id'])
        answer = answered.get(qid)
        if not isinstance(answer, str):
            continue
        for option in question.get('options') or []:
            if not isinstance(option, dict):
                continue
            if str(option.get('value')) == answer and option.get('service_id'):
                return str(option['service_id'])
    return None


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
        meta.pop('qualification', None)
    else:
        meta['qualification'] = state
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


async def _snapshot_contact(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    contact_id: UUID,
    answers: dict[str, Any],
) -> None:
    await conn.execute(
        """
        update app.contacts
        set qualification=$3::jsonb, updated_at=now()
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        contact_id,
        json.dumps(answers),
    )


async def maybe_run_qualification_flow(
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
    """Drive pre-booking qualification.

    Returns one of:
      - ``{'action': 'qualification_step_sent', ...}`` when a question was sent.
      - ``{'action': 'qualification_completed', 'recommended_service_id': ...}``
        when the last required answer was just captured. The orchestrator must
        forward this to ``booking_flow`` immediately.
      - ``{'action': 'qualification_aborted', 'reason': 'opt_out'}`` if the
        user typed ``stop``/``baja`` during the flow.
      - ``None`` when the flow is not applicable on this inbound.
    """
    questions = await _list_questions(conn, tenant_id)
    if not questions:
        return None

    state = _qualification_state(conversation)
    prefix, value = _interactive_id(inbound_message)

    answered: dict[str, Any] = dict(state.get('answered') or {})
    is_mid_flow = bool(state) and not state.get('completed')

    # Only start a fresh flow on booking-related intents.
    if not is_mid_flow and intent not in BOOKING_TRIGGER_INTENTS:
        return None

    # Idempotency: don't re-process the same inbound message.
    idempotency_key = f'qualification_flow:{inbound_message["id"]}'
    if await conn.fetchval(
        'select id from app.domain_events where tenant_id=$1 and idempotency_key=$2',
        tenant_id,
        idempotency_key,
    ):
        return {'action': 'skipped', 'reason': 'already_processed'}

    body_text = (inbound_message.get('body_text') or '').strip()
    if is_mid_flow and body_text and OPT_OUT_PATTERN.match(body_text):
        await _persist_state(conn, tenant_id, conversation, None)
        await conn.execute(
            """
            update app.contacts
            set opt_in_status='revoked', opt_out_at=now(), updated_at=now()
            where tenant_id=$1 and id=$2
            """,
            tenant_id,
            contact['id'],
        )
        await audit(
            conn,
            tenant_id=tenant_id,
            actor_type='bot',
            actor_id='qualification_flow',
            action='qualification.aborted_opt_out',
            entity_type='conversation',
            entity_id=str(conversation['id']),
        )
        await conn.execute(
            """
            insert into app.domain_events (
              tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload
            )
            values ($1, 'conversation', $2, 'qualification_flow.handled', $3, $4::jsonb)
            on conflict (tenant_id, idempotency_key) do nothing
            """,
            tenant_id,
            conversation['id'],
            idempotency_key,
            json.dumps({
                'inbound_message_id': str(inbound_message['id']),
                'reason': 'opt_out',
            }),
        )
        return {'action': 'qualification_aborted', 'reason': 'opt_out'}

    # Apply the inbound answer to the currently pending question, if any.
    pending = _next_pending_question(questions, answered)
    if is_mid_flow and pending is not None:
        qid = str(pending['id'])
        kind = pending['kind']
        new_answer: Any = None
        if prefix == PREFIX_QUALIFY and value and value.startswith(f'{qid}:'):
            raw = value[len(qid) + 1 :]
            if kind == KIND_YES_NO:
                if raw == 'yes':
                    new_answer = True
                elif raw == 'no':
                    new_answer = False
            elif kind == KIND_SINGLE_CHOICE:
                new_answer = _match_choice(pending, raw)
            elif kind == KIND_MULTI_CHOICE:
                existing = answered.get(qid)
                current = list(existing) if isinstance(existing, list) else []
                if raw == DONE_TOKEN:
                    if current:
                        new_answer = current
                    elif pending.get('required'):
                        new_answer = None
                    else:
                        new_answer = []
                else:
                    matched = _match_choice(pending, raw)
                    if matched and matched not in current:
                        current.append(matched)
                    if current:
                        # Stay on this question (multi-choice), record progress
                        # but don't advance — present the question again so the
                        # user can keep choosing or send "Listo".
                        answered[qid] = current
                        await _persist_state(
                            conn,
                            tenant_id,
                            conversation,
                            {'answered': answered, 'started_at': state.get('started_at')},
                        )
                        await _present_question(
                            conn,
                            tenant_id=tenant_id,
                            conversation=conversation,
                            channel_id=channel_id,
                            channel_account_mode=channel_account_mode,
                            question=pending,
                        )
                        await conn.execute(
                            """
                            insert into app.domain_events (
                              tenant_id, aggregate_type, aggregate_id,
                              event_name, idempotency_key, payload
                            )
                            values ($1, 'conversation', $2,
                              'qualification_flow.handled', $3, $4::jsonb)
                            on conflict (tenant_id, idempotency_key) do nothing
                            """,
                            tenant_id,
                            conversation['id'],
                            idempotency_key,
                            json.dumps({
                                'inbound_message_id': str(inbound_message['id']),
                                'question_id': qid,
                                'step': 'multi_partial',
                            }),
                        )
                        return {
                            'action': 'qualification_step_sent',
                            'step': f'q:{qid}',
                            'partial': True,
                        }
        elif body_text and kind in TEXT_KINDS:
            new_answer = _validate_text_reply(pending, body_text)
        elif body_text and kind == KIND_YES_NO:
            normalized = body_text.lower()
            if normalized in {'si', 'sí', 's'}:
                new_answer = True
            elif normalized in {'no', 'n'}:
                new_answer = False

        if new_answer is None:
            # Couldn't parse — re-present the same question.
            await _present_question(
                conn,
                tenant_id=tenant_id,
                conversation=conversation,
                channel_id=channel_id,
                channel_account_mode=channel_account_mode,
                question=pending,
            )
            await conn.execute(
                """
                insert into app.domain_events (
                  tenant_id, aggregate_type, aggregate_id,
                  event_name, idempotency_key, payload
                )
                values ($1, 'conversation', $2,
                  'qualification_flow.handled', $3, $4::jsonb)
                on conflict (tenant_id, idempotency_key) do nothing
                """,
                tenant_id,
                conversation['id'],
                idempotency_key,
                json.dumps({
                    'inbound_message_id': str(inbound_message['id']),
                    'question_id': qid,
                    'step': 'retry',
                }),
            )
            return {
                'action': 'qualification_step_sent',
                'step': f'q:{qid}',
                'retry': True,
            }

        answered[qid] = new_answer

    # Are there still required questions to ask?
    pending = _next_pending_question(questions, answered)
    if pending is not None:
        await _persist_state(
            conn,
            tenant_id,
            conversation,
            {'answered': answered, 'started_at': state.get('started_at')},
        )
        await _present_question(
            conn,
            tenant_id=tenant_id,
            conversation=conversation,
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
            question=pending,
        )
        await conn.execute(
            """
            insert into app.domain_events (
              tenant_id, aggregate_type, aggregate_id,
              event_name, idempotency_key, payload
            )
            values ($1, 'conversation', $2,
              'qualification_flow.handled', $3, $4::jsonb)
            on conflict (tenant_id, idempotency_key) do nothing
            """,
            tenant_id,
            conversation['id'],
            idempotency_key,
            json.dumps({
                'inbound_message_id': str(inbound_message['id']),
                'question_id': str(pending['id']),
                'step': 'asked',
            }),
        )
        log.info(
            'qualification_flow.question_sent',
            tenant_id=str(tenant_id),
            conversation_id=str(conversation['id']),
            question_id=str(pending['id']),
        )
        return {
            'action': 'qualification_step_sent',
            'step': f'q:{pending["id"]}',
        }

    # All required questions answered — snapshot + emit completion.
    recommended_service_id = _derive_recommended_service(questions, answered)
    await _persist_state(
        conn,
        tenant_id,
        conversation,
        {
            'answered': answered,
            'started_at': state.get('started_at'),
            'completed': True,
            'recommended_service_id': recommended_service_id,
        },
    )
    await _snapshot_contact(conn, tenant_id, contact['id'], answered)
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type='bot',
        actor_id='qualification_flow',
        action='qualification.answered',
        entity_type='conversation',
        entity_id=str(conversation['id']),
        metadata={
            'contact_id': str(contact['id']),
            'answers': answered,
            'recommended_service_id': recommended_service_id,
        },
    )
    await conn.execute(
        """
        insert into app.domain_events (
          tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload
        )
        values ($1, 'conversation', $2,
          'qualification_flow.handled', $3, $4::jsonb)
        on conflict (tenant_id, idempotency_key) do nothing
        """,
        tenant_id,
        conversation['id'],
        idempotency_key,
        json.dumps({
            'inbound_message_id': str(inbound_message['id']),
            'step': 'completed',
            'recommended_service_id': recommended_service_id,
        }),
    )
    log.info(
        'qualification_flow.completed',
        tenant_id=str(tenant_id),
        conversation_id=str(conversation['id']),
        recommended_service_id=recommended_service_id,
    )
    return {
        'action': 'qualification_completed',
        'recommended_service_id': recommended_service_id,
        'answered': answered,
    }
