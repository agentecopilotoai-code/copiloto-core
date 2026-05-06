from uuid import UUID

import asyncpg


async def audit(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID | None,
    actor_type: str,
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    metadata: dict | None = None,
) -> None:
    await conn.execute(
        """
        insert into app.audit_logs (tenant_id, actor_type, actor_id, action, entity_type, entity_id, metadata)
        values ($1, $2, $3, $4, $5, $6, $7::jsonb)
        """,
        tenant_id,
        actor_type,
        actor_id,
        action,
        entity_type,
        entity_id,
        metadata or {},
    )
