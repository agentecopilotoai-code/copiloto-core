"""Campaign DB helpers extracted from app/api/v1/routes.py."""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import HTTPException

from app.api.v1._helpers.projections import CAMPAIGN_PROJECTION
from app.services.campaigns import normalize_segment_filter


def _campaign_segment_filter_dict(payload_segment) -> dict[str, Any]:
    if payload_segment is None:
        return {}
    if hasattr(payload_segment, 'model_dump'):
        raw = payload_segment.model_dump(exclude_none=True)
    elif isinstance(payload_segment, dict):
        raw = payload_segment
    else:
        raw = {}
    # UUIDs in the pydantic dump come back as UUID instances; the helper
    # converts them to strings so the JSON encoder doesn't trip up.
    if isinstance(raw.get('tags'), list):
        raw['tags'] = [str(tag) for tag in raw['tags']]
    return normalize_segment_filter(raw)


async def _fetch_campaign_or_404(
    conn: asyncpg.Connection, tenant_id: UUID, campaign_id: UUID
) -> asyncpg.Record:
    row = await conn.fetchrow(
        f'select {CAMPAIGN_PROJECTION} from app.campaigns where tenant_id=$1 and id=$2',
        tenant_id,
        campaign_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Campaign not found')
    return row


async def _ensure_template_approved(
    conn: asyncpg.Connection, tenant_id: UUID, template_id: UUID
) -> asyncpg.Record:
    row = await conn.fetchrow(
        'select id, name, status, category from app.whatsapp_templates where tenant_id=$1 and id=$2',
        tenant_id,
        template_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Template not found')
    if row['status'] != 'approved':
        raise HTTPException(
            status_code=400,
            detail='Campaign templates must be approved by Meta before launch',
        )
    return row
