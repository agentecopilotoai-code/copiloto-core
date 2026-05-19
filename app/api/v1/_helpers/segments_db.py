"""Segment DB helpers extracted from app/api/v1/routes.py."""
from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import HTTPException

from app.api.v1._helpers.projections import SEGMENT_PROJECTION


async def _fetch_segment_or_404(
    conn: asyncpg.Connection, tenant_id: UUID, segment_id: UUID
) -> asyncpg.Record:
    row = await conn.fetchrow(
        f'select {SEGMENT_PROJECTION} from app.contact_segments where tenant_id=$1 and id=$2',
        tenant_id,
        segment_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Segment not found')
    return row
