from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    import asyncpg


logger = logging.getLogger(__name__)


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
        # BUG-041: `default=str` para que UUIDs, datetimes y otros tipos
        # no-JSON-native se serialicen como strings en lugar de revientar
        # con TypeError. Antes, `go-live` auditaba metadata con `checks`
        # que incluían UUIDs y el primer go-live exitoso reventaba el
        # audit log (sin rollback porque la TX ya había commiteado el
        # update, dejando auditoría incompleta).
        json.dumps(metadata or {}, default=str),
    )


# Nota: `audit_durably` se eliminó junto con sus tests (M3 de la auditoría).
# Era para audits sobreviviendo a un rollback de la request (webhooks
# rechazados, etc.). Sin webhooks en el core post-purga no había callers.
# Si un módulo opt-in lo necesita en el futuro: reimplementarlo allá
# (mantiene el coupling localizado al módulo que lo usa).
