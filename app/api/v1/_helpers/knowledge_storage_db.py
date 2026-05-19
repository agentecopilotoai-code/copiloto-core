"""Knowledge storage DB helpers extracted from app/api/v1/routes.py."""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from app.api.v1._helpers.knowledge_storage_config import normalize_knowledge_storage_config


async def fetch_tenant_knowledge_storage_config(
    conn: asyncpg.Connection, tenant_id: UUID
) -> dict[str, Any]:
    value = await conn.fetchval(
        'select knowledge_storage from app.tenant_settings where tenant_id=$1', tenant_id
    )
    return normalize_knowledge_storage_config(tenant_id, value)
