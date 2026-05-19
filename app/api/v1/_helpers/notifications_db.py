"""Operations-change notification helper extracted from app/api/v1/routes.py."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

import asyncpg


async def notify_operations_change(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    event: str,
    *,
    conversation_id: UUID | str | None = None,
    message_id: UUID | str | None = None,
) -> None:
    payload = {
        'type': event,
        'tenant_id': str(tenant_id),
        'conversation_id': str(conversation_id) if conversation_id else None,
        'message_id': str(message_id) if message_id else None,
        'occurred_at': datetime.now(UTC).isoformat(),
    }
    await conn.execute("select pg_notify('tenant_operations_events', $1)", json.dumps(payload))
