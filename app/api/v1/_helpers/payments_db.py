"""Payments DB helpers extracted from app/api/v1/routes.py."""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg

from app.api.v1._helpers.payments_pure import _normalize_payment_settings


async def _fetch_tenant_payment_settings(
    conn: asyncpg.Connection, tenant_id: UUID
) -> dict[str, Any]:
    value = await conn.fetchval(
        'select payment_settings from app.tenant_settings where tenant_id=$1', tenant_id
    )
    return _normalize_payment_settings(value)
