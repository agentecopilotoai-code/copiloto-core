"""Last-touch attribution of appointments to campaigns.

Given an appointment just created for a contact, look for the most recent
campaign message delivered to that contact within the campaign's
``attribution_window_days`` and record an entry in
``app.campaign_attributions``. Attribution is single-row per appointment
(uniqueness on ``tenant_id, appointment_id``) and idempotent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

import structlog

if TYPE_CHECKING:
    import asyncpg

log = structlog.get_logger(__name__)


async def attribute_appointment(
    conn: 'asyncpg.Connection',
    *,
    tenant_id: UUID,
    appointment_id: UUID,
    contact_id: UUID,
) -> UUID | None:
    """Attribute the appointment to the most recent eligible campaign.

    Returns the attribution row id (existing or newly inserted), or ``None``
    if no eligible campaign was found within the window.

    Eligibility:
      * Message direction is outbound and bound to a campaign (``campaign_id is not null``).
      * Message reached the contact (``delivered_at`` or ``sent_at`` is not null).
      * Message timestamp is within ``campaigns.attribution_window_days``
        before the appointment was created.
      * Wins the most recent ``delivered_at`` (fallback to ``sent_at``).
    """
    row = await conn.fetchrow(
        """
        with appointment as (
          select id, created_at
          from app.appointments
          where tenant_id=$1 and id=$2
        ), candidate as (
          select m.campaign_id,
                 coalesce(m.delivered_at, m.sent_at) as touch_at,
                 c.attribution_window_days
          from app.messages m
          join app.campaigns c on c.tenant_id=m.tenant_id and c.id=m.campaign_id
          join app.contacts ct on ct.tenant_id=m.tenant_id and ct.id=$3
          cross join appointment a
          where m.tenant_id=$1
            and m.direction='outbound'
            and m.campaign_id is not null
            and (m.delivered_at is not null or m.sent_at is not null)
            and exists (
              select 1 from app.conversations conv
              where conv.tenant_id=m.tenant_id and conv.id=m.conversation_id
                and conv.contact_id=$3
            )
            and coalesce(m.delivered_at, m.sent_at) <= a.created_at
            and coalesce(m.delivered_at, m.sent_at) >=
                a.created_at - (c.attribution_window_days * interval '1 day')
        )
        select campaign_id, touch_at
        from candidate
        order by touch_at desc
        limit 1
        """,
        tenant_id,
        appointment_id,
        contact_id,
    )
    if not row:
        return None
    inserted = await conn.fetchrow(
        """
        insert into app.campaign_attributions (
          tenant_id, campaign_id, contact_id, appointment_id, attributed_at
        )
        values ($1, $2, $3, $4, now())
        on conflict (tenant_id, appointment_id) do update
          set campaign_id = excluded.campaign_id,
              attributed_at = app.campaign_attributions.attributed_at
        returning id
        """,
        tenant_id,
        row['campaign_id'],
        contact_id,
        appointment_id,
    )
    log.info(
        'campaign_attribution.recorded',
        tenant_id=str(tenant_id),
        appointment_id=str(appointment_id),
        campaign_id=str(row['campaign_id']),
        touch_at=row['touch_at'].isoformat() if row['touch_at'] else None,
    )
    return inserted['id'] if inserted else None
