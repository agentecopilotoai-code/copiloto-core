"""WhatsApp DB helpers extracted from app/api/v1/routes.py."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import HTTPException

from app.api.v1._helpers.whatsapp_pure import WHATSAPP_TEMPLATE_PROJECTION
from app.services.web_widget import build_lead_source


async def upsert_whatsapp_contact(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    wa_id: str,
    phone_e164: str,
    phone_hash: bytes,
    display_name: str | None,
    metadata: dict[str, Any],
    source: str | None = 'whatsapp_cloud_api',
):
    existing = await conn.fetchrow(
        """
        select *
        from app.contacts
        where tenant_id=$1 and (wa_id=$2 or phone_e164=$3)
        order by case when wa_id=$2 then 0 else 1 end, updated_at desc
        limit 1
        """,
        tenant_id,
        wa_id,
        phone_e164,
    )
    if existing:
        return await conn.fetchrow(
            """
            update app.contacts
            set wa_id=$2,
                phone_e164=$3,
                phone_hash=$4,
                display_name=coalesce($5, display_name),
                source=coalesce($6, source),
                metadata=metadata || $7::jsonb,
                updated_at=now()
            where tenant_id=$1 and id=$8
            returning *
            """,
            tenant_id,
            wa_id,
            phone_e164,
            phone_hash,
            display_name,
            source,
            json.dumps(metadata),
            existing['id'],
        )
    default_lead_source = build_lead_source(channel='whatsapp')
    return await conn.fetchrow(
        """
        insert into app.contacts (tenant_id, wa_id, phone_e164, phone_hash, display_name, source, metadata, lead_source)
        values ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb)
        returning *
        """,
        tenant_id,
        wa_id,
        phone_e164,
        phone_hash,
        display_name,
        source,
        json.dumps(metadata),
        json.dumps(default_lead_source),
    )


async def _fetch_template_or_404(
    conn: asyncpg.Connection, tenant_id: UUID, template_id: UUID
) -> asyncpg.Record:
    row = await conn.fetchrow(
        f'select {WHATSAPP_TEMPLATE_PROJECTION} from app.whatsapp_templates where tenant_id=$1 and id=$2',
        tenant_id,
        template_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Template not found')
    return row


async def _resolve_channel_for_template(
    conn: asyncpg.Connection, tenant_id: UUID, channel_id: UUID | None
) -> asyncpg.Record:
    if channel_id:
        row = await conn.fetchrow(
            "select id, waba_id, token_ref, account_mode from app.tenant_channels where tenant_id=$1 and id=$2 and provider='whatsapp_cloud_api'",
            tenant_id,
            channel_id,
        )
    else:
        row = await conn.fetchrow(
            "select id, waba_id, token_ref, account_mode from app.tenant_channels where tenant_id=$1 and provider='whatsapp_cloud_api'",
            tenant_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail='WhatsApp channel not found')
    return row
