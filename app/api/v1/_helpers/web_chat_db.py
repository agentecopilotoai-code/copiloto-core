"""Web chat sync delivery helper extracted from app/api/v1/routes.py."""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg


async def _persist_bot_reply_sync(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
) -> dict[str, Any] | None:
    """After the orchestrator runs, claim the latest pending outbound message.

    The RAG orchestrator queues the bot's outbound message via
    ``message.queued`` for the event worker (WhatsApp delivery). For the web
    channel we deliver synchronously: we mark the message as ``sent`` and
    publish the event right here so the response is returned to the browser
    immediately.
    """
    row = await conn.fetchrow(
        """
        select id, body_text, message_type, payload, created_at
        from app.messages
        where tenant_id=$1 and conversation_id=$2
          and direction='outbound' and status='queued'
        order by created_at desc
        limit 1
        """,
        tenant_id,
        conversation_id,
    )
    if not row:
        return None
    await conn.execute(
        """
        update app.messages
        set status='sent', sent_at=now()
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        row['id'],
    )
    await conn.execute(
        """
        update app.domain_events
        set published_at=now()
        where tenant_id=$1 and aggregate_id=$2 and event_name='message.queued'
          and published_at is null
        """,
        tenant_id,
        row['id'],
    )
    return {
        'id': str(row['id']),
        'body_text': row['body_text'] or '',
        'message_type': row['message_type'],
        'created_at': row['created_at'].isoformat() if row.get('created_at') else None,
    }
