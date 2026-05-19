"""Messenger contact DB helpers extracted from app/api/v1/routes.py."""
from __future__ import annotations

import hashlib
import json
from uuid import UUID

import asyncpg

from app.services.web_widget import build_lead_source


async def _upsert_messenger_contact(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    provider: str,
    psid: str,
    display_name: str | None,
):
    """Upsert a contact identified by a Messenger PSID.

    Instagram/Facebook PSIDs are opaque numeric strings tied to the page+user
    pair. They are not phone numbers, so we stash them in ``wa_id`` (acts as
    the canonical external id) and synthesize a placeholder ``phone_e164``
    of the form ``+ig:<psid>`` / ``+fb:<psid>``. This keeps the existing
    ``unique (tenant_id, phone_e164)`` constraint usable without altering
    the schema or requiring real phones for social channels.
    """
    prefix = 'ig' if provider == 'instagram_messenger' else 'fb'
    pseudo_phone = f'+{prefix}:{psid}'
    phone_hash = hashlib.sha256(pseudo_phone.encode()).digest()
    existing = await conn.fetchrow(
        """
        select *
        from app.contacts
        where tenant_id=$1 and wa_id=$2
        limit 1
        """,
        tenant_id,
        psid,
    )
    if existing:
        return await conn.fetchrow(
            """
            update app.contacts
            set display_name=coalesce($3, display_name),
                source=coalesce($4, source),
                updated_at=now()
            where tenant_id=$1 and id=$2
            returning *
            """,
            tenant_id,
            existing['id'],
            display_name,
            provider,
        )
    default_lead_source = build_lead_source(channel=provider)
    return await conn.fetchrow(
        """
        insert into app.contacts (
            tenant_id, wa_id, phone_e164, phone_hash, display_name, source, metadata, lead_source
        )
        values ($1, $2, $3, $4, $5, $6, '{}'::jsonb, $7::jsonb)
        returning *
        """,
        tenant_id,
        psid,
        pseudo_phone,
        phone_hash,
        display_name,
        provider,
        json.dumps(default_lead_source),
    )
