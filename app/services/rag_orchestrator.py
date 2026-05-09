"""Orchestrates automatic bot replies and human handoffs for inbound WhatsApp messages."""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from app.services.audit import audit
from app.services.rag_retrieval import build_grounded_answer, rank_chunks, retrieval_match_to_dict

if TYPE_CHECKING:
    import asyncpg

log = structlog.get_logger()

_DEFAULT_HUMAN_KEYWORDS = {'humano', 'asesor', 'agente', 'reclamo', 'persona'}


def _parse_escalation_policy(raw: Any) -> dict[str, Any]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            raw = {}
    return raw if isinstance(raw, dict) else {}


def _keyword_triggers(policy: dict[str, Any]) -> set[str]:
    triggers = policy.get('triggers') or {}
    if isinstance(triggers, str):
        try:
            triggers = json.loads(triggers)
        except (json.JSONDecodeError, TypeError):
            triggers = {}
    keywords = triggers.get('keywords') or []
    result = {kw.strip().lower() for kw in keywords if isinstance(kw, str) and kw.strip()}
    return result or _DEFAULT_HUMAN_KEYWORDS


async def orchestrate_inbound_message(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    channel_id: UUID,
    channel_account_mode: str,
    conversation: asyncpg.Record,
    contact: asyncpg.Record,
    inbound_message: asyncpg.Record,
) -> dict[str, Any]:
    """Decide whether to reply automatically via RAG or escalate to a human agent."""

    body_text: str = inbound_message['body_text'] or ''
    if inbound_message['message_type'] != 'text' or not body_text.strip():
        return {'action': 'skipped', 'reason': 'non_text_message'}

    if conversation['status'] == 'human_active':
        return {'action': 'skipped', 'reason': 'human_active'}

    opt_in = contact.get('opt_in_status') or 'unknown'
    if opt_in in ('revoked', 'suppressed'):
        return {'action': 'skipped', 'reason': f'contact_opt_in_{opt_in}'}

    # Load tenant settings
    settings_row = await conn.fetchrow(
        'select escalation_policy, max_bot_turns from app.tenant_settings where tenant_id=$1',
        tenant_id,
    )
    max_bot_turns: int = (settings_row['max_bot_turns'] if settings_row else None) or 8
    raw_policy = (settings_row['escalation_policy'] if settings_row else None) or {}
    policy = _parse_escalation_policy(raw_policy)

    # Keyword trigger check
    body_lower = body_text.lower()
    triggered_keyword = next((kw for kw in _keyword_triggers(policy) if kw in body_lower), None)
    if triggered_keyword:
        return await _do_handoff(
            conn,
            tenant_id=tenant_id,
            channel_id=channel_id,
            conversation=conversation,
            inbound_message=inbound_message,
            policy=policy,
            reason='keyword_trigger',
            reason_detail=f'keyword={triggered_keyword}',
        )

    # Max bot turns check
    bot_turn_count: int = await conn.fetchval(
        """
        select count(*) from app.messages
        where conversation_id=$1
          and direction='outbound'
          and sender_actor_type='bot'
        """,
        conversation['id'],
    ) or 0
    if bot_turn_count >= max_bot_turns:
        return await _do_handoff(
            conn,
            tenant_id=tenant_id,
            channel_id=channel_id,
            conversation=conversation,
            inbound_message=inbound_message,
            policy=policy,
            reason='max_bot_turns_exceeded',
            reason_detail=f'limit={max_bot_turns}',
        )

    # Idempotency check (deduplication)
    idempotency_key = f'bot_reply:{inbound_message["id"]}'
    if await conn.fetchval(
        'select id from app.domain_events where tenant_id=$1 and idempotency_key=$2',
        tenant_id, idempotency_key,
    ):
        return {'action': 'skipped', 'reason': 'already_processed'}

    # Retrieve active knowledge chunks and run RAG
    rows = await conn.fetch(
        """
        select kc.id, kc.document_id,
               kd.title as document_title, kd.source_uri, kd.source_type,
               kd.document_type, kd.visibility,
               kc.chunk_index, kc.section_path, kc.chunk_text, kc.token_count, kc.metadata
        from app.knowledge_chunks kc
        join app.knowledge_documents kd on kd.id = kc.document_id and kd.tenant_id = kc.tenant_id
        where kc.tenant_id=$1
          and kd.status='active'
        order by kd.updated_at desc, kc.chunk_index asc
        """,
        tenant_id,
    )
    chunks = [dict(row) for row in rows]
    matches = rank_chunks(body_text, chunks)
    decision = build_grounded_answer(body_text, matches)

    top_score = matches[0].score if matches else None
    top_document = matches[0].document_title if matches else None

    if decision['sufficient_context']:
        return await _send_bot_reply(
            conn,
            tenant_id=tenant_id,
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
            conversation=conversation,
            inbound_message=inbound_message,
            answer_text=decision['answer'],
            matches=matches,
            idempotency_key=idempotency_key,
            top_score=top_score,
            top_document=top_document,
        )

    return await _do_handoff(
        conn,
        tenant_id=tenant_id,
        channel_id=channel_id,
        conversation=conversation,
        inbound_message=inbound_message,
        policy=policy,
        reason='knowledge_context_insufficient',
        reason_detail='no_active_evidence',
    )


async def _send_bot_reply(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    channel_id: UUID,
    channel_account_mode: str,
    conversation: asyncpg.Record,
    inbound_message: asyncpg.Record,
    answer_text: str,
    matches: list,
    idempotency_key: str,
    top_score: float | None,
    top_document: str | None,
) -> dict[str, Any]:
    trace_payload = {
        'rag_decision': 'answered',
        'question': inbound_message['body_text'],
        'top_score': top_score,
        'top_document': top_document,
        'chunks_used': [retrieval_match_to_dict(m) for m in matches],
        'inbound_message_id': str(inbound_message['id']),
    }
    outbound = await conn.fetchrow(
        """
        insert into app.messages (
          tenant_id, conversation_id, direction, sender_actor_type,
          body_text, message_type, status, payload
        )
        values ($1, $2, 'outbound', 'bot', $3, 'text', 'queued', $4::jsonb)
        returning *
        """,
        tenant_id,
        conversation['id'],
        answer_text,
        json.dumps(trace_payload),
    )

    event_payload = {
        'message_id': str(outbound['id']),
        'conversation_id': str(conversation['id']),
        'body_text': answer_text,
        'channel_id': str(channel_id),
        'channel_account_mode': channel_account_mode,
    }
    await conn.execute(
        """
        insert into app.domain_events (
          tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload
        )
        values ($1, 'message', $2, 'message.queued', $3, $4::jsonb)
        on conflict (tenant_id, idempotency_key) do nothing
        """,
        tenant_id,
        outbound['id'],
        idempotency_key,
        json.dumps(event_payload),
    )

    await conn.execute(
        """
        update app.conversations
        set status='waiting_user', handoff_required=false, updated_at=now()
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        conversation['id'],
    )

    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type='bot',
        actor_id='rag_orchestrator',
        action='bot.replied',
        entity_type='message',
        entity_id=str(outbound['id']),
        metadata={
            'question': inbound_message['body_text'],
            'rag_decision': 'answered',
            'top_score': top_score,
            'top_document': top_document,
            'inbound_message_id': str(inbound_message['id']),
        },
    )

    log.info(
        'rag_orchestrator.replied',
        tenant_id=str(tenant_id),
        conversation_id=str(conversation['id']),
        top_score=top_score,
    )
    return {
        'action': 'bot_replied',
        'outbound_message_id': str(outbound['id']),
        'top_score': top_score,
        'top_document': top_document,
    }


async def _do_handoff(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    channel_id: UUID,
    conversation: asyncpg.Record,
    inbound_message: asyncpg.Record,
    policy: dict[str, Any],
    reason: str,
    reason_detail: str,
) -> dict[str, Any]:
    await conn.execute(
        """
        update app.conversations
        set status='waiting_agent', handoff_required=true, updated_at=now()
        where tenant_id=$1 and id=$2 and status != 'human_active'
        """,
        tenant_id,
        conversation['id'],
    )

    existing_handoff = await conn.fetchrow(
        """
        select id from app.handoffs
        where tenant_id=$1 and conversation_id=$2 and status='open'
        order by created_at desc limit 1
        """,
        tenant_id,
        conversation['id'],
    )
    if existing_handoff:
        handoff_id = existing_handoff['id']
    else:
        handoff_row = await conn.fetchrow(
            """
            insert into app.handoffs (tenant_id, conversation_id, reason, status)
            values ($1, $2, $3, 'open')
            returning *
            """,
            tenant_id,
            conversation['id'],
            reason,
        )
        handoff_id = handoff_row['id']

    # Send handoff_message if the policy defines one
    handoff_message_sent = False
    handoff_message_text: str = policy.get('handoff_message') or ''
    if handoff_message_text.strip():
        idempotency_key = f'handoff_msg:{inbound_message["id"]}'
        existing_event = await conn.fetchval(
            'select id from app.domain_events where tenant_id=$1 and idempotency_key=$2',
            tenant_id, idempotency_key,
        )
        if not existing_event:
            trace_payload = {
                'rag_decision': 'handoff',
                'reason': reason,
                'reason_detail': reason_detail,
                'inbound_message_id': str(inbound_message['id']),
            }
            outbound_msg = await conn.fetchrow(
                """
                insert into app.messages (
                  tenant_id, conversation_id, direction, sender_actor_type,
                  body_text, message_type, status, payload
                )
                values ($1, $2, 'outbound', 'bot', $3, 'text', 'queued', $4::jsonb)
                returning *
                """,
                tenant_id,
                conversation['id'],
                handoff_message_text,
                json.dumps(trace_payload),
            )
            event_payload = {
                'message_id': str(outbound_msg['id']),
                'conversation_id': str(conversation['id']),
                'body_text': handoff_message_text,
                'channel_id': str(channel_id),
            }
            await conn.execute(
                """
                insert into app.domain_events (
                  tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload
                )
                values ($1, 'message', $2, 'message.queued', $3, $4::jsonb)
                on conflict (tenant_id, idempotency_key) do nothing
                """,
                tenant_id,
                outbound_msg['id'],
                idempotency_key,
                json.dumps(event_payload),
            )
            handoff_message_sent = True

    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type='bot',
        actor_id='rag_orchestrator',
        action='bot.handoff',
        entity_type='handoff',
        entity_id=str(handoff_id),
        metadata={
            'reason': reason,
            'reason_detail': reason_detail,
            'inbound_message_id': str(inbound_message['id']),
            'handoff_message_sent': handoff_message_sent,
        },
    )

    log.info(
        'rag_orchestrator.handoff',
        tenant_id=str(tenant_id),
        conversation_id=str(conversation['id']),
        reason=reason,
    )
    return {
        'action': 'handoff',
        'handoff_id': str(handoff_id),
        'reason': reason,
        'handoff_message_sent': handoff_message_sent,
    }
