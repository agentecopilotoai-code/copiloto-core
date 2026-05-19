"""Handlers extracted from routes.py for tenant_analytics_router.

Original location: app/api/v1/routes.py (refactor step 3).
"""
from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import asyncpg
from fastapi import Depends, Query, Request

from app.api.v1._helpers.analytics import (
    _funnel_step,
    _range_bounds,
    _resolve_analytics_range,
)
from app.api.v1.routes import (
    tenant_analytics_router,
    tenant_id_from_request,
)
from app.core.security import require_min_role
from app.db.pool import get_db


@tenant_analytics_router.get('/analytics/overview')
async def analytics_overview(
    request: Request,
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    start, end = _resolve_analytics_range(from_date, to_date)
    range_start, range_end = _range_bounds(start, end)
    retention_start = range_end - timedelta(days=90)

    conv_row = await conn.fetchrow(
        """
        select
          count(*) as total,
          count(*) filter (where status in ('open','waiting_user','waiting_agent')) as open_count,
          count(*) filter (where status in ('resolved','closed','archived')) as resolved_count,
          count(*) filter (where status in ('human_required','human_active') or handoff_required) as handoff_count
        from app.conversations
        where tenant_id = $1 and created_at >= $2 and created_at < $3
        """,
        tenant_id, range_start, range_end,
    )
    appt_row = await conn.fetchrow(
        """
        select
          count(*) as created,
          count(*) filter (where status = 'confirmed') as confirmed,
          count(*) filter (where status = 'completed') as completed,
          count(*) filter (where status = 'cancelled') as cancelled,
          count(*) filter (where status = 'no_show') as no_shows
        from app.appointments
        where tenant_id = $1 and created_at >= $2 and created_at < $3
        """,
        tenant_id, range_start, range_end,
    )
    revenue_row = await conn.fetchrow(
        """
        select coalesce(sum(s.price_amount), 0)::float as revenue
        from app.appointments a
        left join app.service_catalog s on s.id = a.service_id and s.tenant_id = a.tenant_id
        where a.tenant_id = $1 and a.status = 'completed'
          and a.starts_at >= $2 and a.starts_at < $3
        """,
        tenant_id, range_start, range_end,
    )
    feedback_row = await conn.fetchrow(
        """
        select coalesce(avg(rating), 0)::float as avg_rating, count(*) as ratings_count
        from app.appointment_feedback
        where tenant_id = $1 and created_at >= $2 and created_at < $3
        """,
        tenant_id, range_start, range_end,
    )
    msg_row = await conn.fetchrow(
        """
        select
          count(*) filter (where direction = 'inbound') as inbound,
          count(*) filter (where direction = 'outbound') as outbound
        from app.messages
        where tenant_id = $1 and created_at >= $2 and created_at < $3
        """,
        tenant_id, range_start, range_end,
    )
    retention_row = await conn.fetchrow(
        """
        with completed as (
          select contact_id, count(*) as ct
          from app.appointments
          where tenant_id = $1 and status = 'completed'
            and starts_at >= $2 and starts_at < $3
          group by contact_id
        )
        select
          count(*) filter (where ct >= 2)::int as recurring_contacts,
          count(*)::int as total_contacts
        from completed
        """,
        tenant_id, retention_start, range_end,
    )

    lead_source_rows = await conn.fetch(
        """
        select coalesce(nullif(lead_source->>'channel', ''), 'unknown') as channel,
               count(*)::int as count
        from app.contacts
        where tenant_id = $1 and created_at >= $2 and created_at < $3
        group by 1
        order by count desc
        """,
        tenant_id, range_start, range_end,
    )

    conv_total = conv_row['total'] or 0
    handoff_count = conv_row['handoff_count'] or 0
    handoff_rate = (handoff_count / conv_total * 100) if conv_total else 0.0
    completed = appt_row['completed'] or 0
    no_shows = appt_row['no_shows'] or 0
    no_show_base = completed + no_shows
    no_show_rate = (no_shows / no_show_base * 100) if no_show_base else 0.0
    recurring = retention_row['recurring_contacts'] or 0
    total_retention = retention_row['total_contacts'] or 0
    retention_rate = (recurring / total_retention * 100) if total_retention else 0.0

    return {
        'range': {'from_date': start.isoformat(), 'to_date': end.isoformat()},
        'conversations': {
            'total': conv_total,
            'open': conv_row['open_count'] or 0,
            'resolved': conv_row['resolved_count'] or 0,
            'handoff': handoff_count,
            'handoff_rate_pct': round(handoff_rate, 2),
        },
        'appointments': {
            'created': appt_row['created'] or 0,
            'confirmed': appt_row['confirmed'] or 0,
            'completed': completed,
            'cancelled': appt_row['cancelled'] or 0,
            'no_shows': no_shows,
            'no_show_rate_pct': round(no_show_rate, 2),
        },
        'revenue': {
            'estimated_amount': round(revenue_row['revenue'] or 0.0, 2),
        },
        'feedback': {
            'average_rating': round(feedback_row['avg_rating'] or 0.0, 2),
            'ratings_count': feedback_row['ratings_count'] or 0,
        },
        'messages': {
            'inbound': msg_row['inbound'] or 0,
            'outbound': msg_row['outbound'] or 0,
        },
        'retention': {
            'recurring_contacts': recurring,
            'total_contacts_completed': total_retention,
            'retention_rate_pct': round(retention_rate, 2),
            'window_days': 90,
        },
        'lead_sources': [
            {'channel': row['channel'], 'count': row['count']}
            for row in lead_source_rows
        ],
    }


@tenant_analytics_router.get('/analytics/conversations')
async def analytics_conversations(
    request: Request,
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    start, end = _resolve_analytics_range(from_date, to_date)
    range_start, range_end = _range_bounds(start, end)

    intents = await conn.fetch(
        """
        select coalesce(current_intent, 'unknown') as intent, count(*) as count
        from app.conversations
        where tenant_id = $1 and created_at >= $2 and created_at < $3
        group by 1
        order by count desc
        limit 10
        """,
        tenant_id, range_start, range_end,
    )
    statuses = await conn.fetch(
        """
        select status, count(*) as count
        from app.conversations
        where tenant_id = $1 and created_at >= $2 and created_at < $3
        group by status
        order by count desc
        """,
        tenant_id, range_start, range_end,
    )
    first_response_row = await conn.fetchrow(
        """
        with first_inbound as (
          select conversation_id, min(created_at) as inbound_at
          from app.messages
          where tenant_id = $1 and direction = 'inbound'
            and created_at >= $2 and created_at < $3
          group by conversation_id
        ), first_bot as (
          select m.conversation_id, min(m.created_at) as bot_at
          from app.messages m
          where m.tenant_id = $1 and m.direction = 'outbound' and m.sender_actor_type = 'bot'
            and m.created_at >= $2 and m.created_at < $3
          group by m.conversation_id
        )
        select coalesce(
          avg(extract(epoch from (b.bot_at - i.inbound_at))),
          0
        )::float as avg_seconds
        from first_inbound i
        join first_bot b on b.conversation_id = i.conversation_id
        where b.bot_at >= i.inbound_at
        """,
        tenant_id, range_start, range_end,
    )
    daily = await conn.fetch(
        """
        select date_trunc('day', created_at)::date as date, count(*) as count
        from app.conversations
        where tenant_id = $1 and created_at >= $2 and created_at < $3
        group by 1
        order by 1
        """,
        tenant_id, range_start, range_end,
    )
    total_intents = sum(row['count'] for row in intents) or 1
    return {
        'range': {'from_date': start.isoformat(), 'to_date': end.isoformat()},
        'top_intents': [
            {
                'intent': row['intent'],
                'count': row['count'],
                'percentage': round(row['count'] / total_intents * 100, 2),
            }
            for row in intents
        ],
        'status_distribution': [
            {'status': row['status'], 'count': row['count']} for row in statuses
        ],
        'avg_first_bot_response_seconds': round(first_response_row['avg_seconds'] or 0.0, 2),
        'daily_evolution': [
            {'date': row['date'].isoformat(), 'count': row['count']} for row in daily
        ],
    }


@tenant_analytics_router.get('/analytics/appointments')
async def analytics_appointments(
    request: Request,
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    branch_id: UUID | None = Query(default=None),
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    start, end = _resolve_analytics_range(from_date, to_date)
    range_start, range_end = _range_bounds(start, end)

    top_services = await conn.fetch(
        """
        select coalesce(s.name, a.service_code) as service_name,
               coalesce(s.id::text, a.service_code) as service_key,
               count(*) as count
        from app.appointments a
        left join app.service_catalog s on s.id = a.service_id and s.tenant_id = a.tenant_id
        where a.tenant_id = $1 and a.created_at >= $2 and a.created_at < $3
          and ($4::uuid is null or a.branch_id = $4)
        group by 1, 2
        order by count desc
        limit 10
        """,
        tenant_id, range_start, range_end, branch_id,
    )
    statuses = await conn.fetch(
        """
        select status, count(*) as count
        from app.appointments
        where tenant_id = $1 and created_at >= $2 and created_at < $3
          and ($4::uuid is null or branch_id = $4)
        group by status
        order by count desc
        """,
        tenant_id, range_start, range_end, branch_id,
    )
    no_shows_dow = await conn.fetch(
        """
        select extract(dow from starts_at)::int as dow, count(*) as count
        from app.appointments
        where tenant_id = $1 and status = 'no_show'
          and starts_at >= $2 and starts_at < $3
          and ($4::uuid is null or branch_id = $4)
        group by 1
        order by 1
        """,
        tenant_id, range_start, range_end, branch_id,
    )
    daily = await conn.fetch(
        """
        select date_trunc('day', created_at)::date as date,
               count(*) as created,
               count(*) filter (where status = 'completed') as completed
        from app.appointments
        where tenant_id = $1 and created_at >= $2 and created_at < $3
          and ($4::uuid is null or branch_id = $4)
        group by 1
        order by 1
        """,
        tenant_id, range_start, range_end, branch_id,
    )
    return {
        'range': {'from_date': start.isoformat(), 'to_date': end.isoformat()},
        'top_services': [
            {
                'service_key': row['service_key'],
                'service_name': row['service_name'],
                'count': row['count'],
            }
            for row in top_services
        ],
        'status_distribution': [
            {'status': row['status'], 'count': row['count']} for row in statuses
        ],
        'no_shows_by_weekday': [
            {'weekday': row['dow'], 'count': row['count']} for row in no_shows_dow
        ],
        'daily_evolution': [
            {
                'date': row['date'].isoformat(),
                'created': row['created'],
                'completed': row['completed'],
            }
            for row in daily
        ],
    }


@tenant_analytics_router.get('/analytics/contacts')
async def analytics_contacts(
    request: Request,
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    start, end = _resolve_analytics_range(from_date, to_date)
    range_start, range_end = _range_bounds(start, end)

    new_vs_recurring = await conn.fetchrow(
        """
        with new_contacts as (
          select id from app.contacts
          where tenant_id = $1 and created_at >= $2 and created_at < $3
        ), active_contacts as (
          select distinct contact_id as id from app.appointments
          where tenant_id = $1 and created_at >= $2 and created_at < $3
        )
        select
          (select count(*) from new_contacts) as new_count,
          (select count(*) from active_contacts a
             where a.id not in (select id from new_contacts)) as recurring_count
        """,
        tenant_id, range_start, range_end,
    )
    top_tags = await conn.fetch(
        """
        select t.id, t.name, t.color, count(cta.contact_id) as count
        from app.contact_tags t
        left join app.contact_tag_assignments cta on cta.tag_id = t.id and cta.tenant_id = t.tenant_id
        where t.tenant_id = $1
        group by t.id
        order by count desc
        limit 10
        """,
        tenant_id,
    )
    opt_row = await conn.fetchrow(
        """
        select
          count(*) as total,
          count(*) filter (where opt_in_status in ('revoked','suppressed')) as opted_out
        from app.contacts
        where tenant_id = $1
        """,
        tenant_id,
    )
    sources = await conn.fetch(
        """
        select coalesce(source, 'unknown') as source, count(*) as count
        from app.contacts
        where tenant_id = $1
        group by 1
        order by count desc
        """,
        tenant_id,
    )

    total_contacts = opt_row['total'] or 0
    opted_out = opt_row['opted_out'] or 0
    opt_out_rate = (opted_out / total_contacts * 100) if total_contacts else 0.0

    return {
        'range': {'from_date': start.isoformat(), 'to_date': end.isoformat()},
        'new_contacts': new_vs_recurring['new_count'] or 0,
        'recurring_contacts': new_vs_recurring['recurring_count'] or 0,
        'top_tags': [
            {
                'id': str(row['id']),
                'name': row['name'],
                'color': row['color'],
                'count': row['count'],
            }
            for row in top_tags
        ],
        'opt_out_rate_pct': round(opt_out_rate, 2),
        'total_contacts': total_contacts,
        'opted_out': opted_out,
        'source_distribution': [
            {'source': row['source'], 'count': row['count']} for row in sources
        ],
    }


@tenant_analytics_router.get('/analytics/funnel')
async def analytics_funnel(
    request: Request,
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    conn: asyncpg.Connection = Depends(get_db),
):
    """Conversion funnel: leads → engaged → scheduled → completed → repeat.

    Returns aggregated counts plus a per-channel breakdown using
    ``contacts.lead_source->>'channel'``.
    """
    tenant_id = await tenant_id_from_request(request, conn)
    start, end = _resolve_analytics_range(from_date, to_date)
    range_start, range_end = _range_bounds(start, end)
    repeat_window_start = range_end - timedelta(days=90)

    funnel_rows = await conn.fetch(
        """
        with leads as (
          select
            id as contact_id,
            coalesce(nullif(lead_source->>'channel', ''), 'unknown') as channel
          from app.contacts
          where tenant_id = $1 and created_at >= $2 and created_at < $3
        ),
        engaged as (
          select distinct conv.contact_id
          from app.conversations conv
          join app.messages m on m.tenant_id = conv.tenant_id
                              and m.conversation_id = conv.id
          where conv.tenant_id = $1
            and m.direction = 'outbound'
            and m.sender_actor_type in ('bot','agent')
            and m.created_at >= $2 and m.created_at < $3
        ),
        scheduled as (
          select distinct contact_id
          from app.appointments
          where tenant_id = $1
            and created_at >= $2 and created_at < $3
        ),
        completed as (
          select distinct contact_id
          from app.appointments
          where tenant_id = $1
            and status = 'completed'
            and starts_at >= $2 and starts_at < $3
        ),
        repeat_customers as (
          select contact_id
          from app.appointments
          where tenant_id = $1
            and status = 'completed'
            and starts_at >= $4 and starts_at < $3
          group by contact_id
          having count(*) >= 2
        )
        select
          l.channel as channel,
          count(distinct l.contact_id) as leads,
          count(distinct e.contact_id) as engaged,
          count(distinct s.contact_id) as scheduled,
          count(distinct c.contact_id) as completed,
          count(distinct r.contact_id) as repeat_customers
        from leads l
        left join engaged e on e.contact_id = l.contact_id
        left join scheduled s on s.contact_id = l.contact_id
        left join completed c on c.contact_id = l.contact_id
        left join repeat_customers r on r.contact_id = l.contact_id
        group by l.channel
        order by leads desc
        """,
        tenant_id, range_start, range_end, repeat_window_start,
    )

    total_leads = sum(int(row['leads'] or 0) for row in funnel_rows)
    total_engaged = sum(int(row['engaged'] or 0) for row in funnel_rows)
    total_scheduled = sum(int(row['scheduled'] or 0) for row in funnel_rows)
    total_completed = sum(int(row['completed'] or 0) for row in funnel_rows)
    total_repeat = sum(int(row['repeat_customers'] or 0) for row in funnel_rows)

    total_steps = [
        _funnel_step('leads', total_leads, total_leads, total_leads),
        _funnel_step('engaged', total_engaged, total_leads, total_leads),
        _funnel_step('appointments_scheduled', total_scheduled, total_engaged, total_leads),
        _funnel_step('appointments_completed', total_completed, total_scheduled, total_leads),
        _funnel_step('repeat_customers', total_repeat, total_completed, total_leads),
    ]

    by_channel = []
    for row in funnel_rows:
        leads = int(row['leads'] or 0)
        engaged = int(row['engaged'] or 0)
        scheduled = int(row['scheduled'] or 0)
        completed = int(row['completed'] or 0)
        repeat = int(row['repeat_customers'] or 0)
        by_channel.append({
            'channel': row['channel'],
            'steps': [
                _funnel_step('leads', leads, leads, leads),
                _funnel_step('engaged', engaged, leads, leads),
                _funnel_step('appointments_scheduled', scheduled, engaged, leads),
                _funnel_step('appointments_completed', completed, scheduled, leads),
                _funnel_step('repeat_customers', repeat, completed, leads),
            ],
        })

    return {
        'range': {'from_date': start.isoformat(), 'to_date': end.isoformat()},
        'repeat_window_days': 90,
        'total': total_steps,
        'by_channel': by_channel,
    }


@tenant_analytics_router.get('/analytics/campaigns')
async def analytics_campaigns(
    request: Request,
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    conn: asyncpg.Connection = Depends(get_db),
):
    """Per-campaign performance with attributed appointments and revenue.

    Includes campaigns whose ``started_at`` (or ``created_at`` if not yet
    launched) falls within the range. ``appointments_attributed`` and
    ``revenue_attributed`` come from ``app.campaign_attributions`` joined
    with service prices.
    """
    tenant_id = await tenant_id_from_request(request, conn)
    start, end = _resolve_analytics_range(from_date, to_date)
    range_start, range_end = _range_bounds(start, end)

    rows = await conn.fetch(
        """
        with cam as (
          select
            c.id, c.name, c.status, c.scheduled_at, c.started_at, c.completed_at,
            c.recipient_count, c.sent_count, c.delivered_count, c.read_count,
            c.failed_count, c.cost_amount, c.cost_currency,
            c.attribution_window_days
          from app.campaigns c
          where c.tenant_id = $1
            and coalesce(c.started_at, c.created_at) >= $2
            and coalesce(c.started_at, c.created_at) < $3
        ),
        replies as (
          -- A "reply" is any inbound message that lands in the same conversation
          -- as a campaign-tagged outbound, within that campaign's attribution
          -- window. We can't rely on inbound rows carrying campaign_id (the
          -- WhatsApp webhook never sets it) nor on reply_to_external_message_id
          -- (only present when the contact uses the native quote affordance),
          -- so we stitch by conversation+time exactly like campaign_attributions
          -- already does for appointments.
          select om.campaign_id, count(distinct om.conversation_id) as replied
          from app.messages om
          join app.campaigns c
            on c.tenant_id = om.tenant_id and c.id = om.campaign_id
          where om.tenant_id = $1
            and om.direction = 'outbound'
            and om.campaign_id is not null
            and exists (
              select 1
              from app.messages im
              where im.tenant_id = om.tenant_id
                and im.conversation_id = om.conversation_id
                and im.direction = 'inbound'
                and im.received_at >= coalesce(om.sent_at, om.created_at)
                and im.received_at < coalesce(om.sent_at, om.created_at)
                                      + (c.attribution_window_days || ' days')::interval
            )
          group by om.campaign_id
        ),
        attribution as (
          select
            ca.campaign_id,
            count(*) as attributed_count,
            count(*) filter (where a.status = 'completed') as attributed_completed,
            coalesce(sum(s.price_amount) filter (where a.status = 'completed'), 0)::float
              as revenue_attributed
          from app.campaign_attributions ca
          join app.appointments a on a.tenant_id = ca.tenant_id
                                  and a.id = ca.appointment_id
          left join app.service_catalog s on s.tenant_id = a.tenant_id
                                          and s.id = a.service_id
          where ca.tenant_id = $1
          group by ca.campaign_id
        )
        select
          cam.*,
          coalesce(replies.replied, 0) as replied,
          coalesce(attribution.attributed_count, 0) as appointments_attributed,
          coalesce(attribution.attributed_completed, 0) as appointments_completed,
          coalesce(attribution.revenue_attributed, 0.0) as revenue_attributed
        from cam
        left join replies on replies.campaign_id = cam.id
        left join attribution on attribution.campaign_id = cam.id
        order by revenue_attributed desc, cam.started_at desc nulls last
        """,
        tenant_id, range_start, range_end,
    )

    items = []
    for row in rows:
        recipients = int(row['recipient_count'] or 0)
        delivered = int(row['delivered_count'] or 0)
        read = int(row['read_count'] or 0)
        replied = int(row['replied'] or 0)
        cost_amount = float(row['cost_amount']) if row['cost_amount'] is not None else None
        revenue = float(row['revenue_attributed'] or 0.0)
        roi = None
        if cost_amount and cost_amount > 0:
            roi = round(revenue / cost_amount, 2)
        items.append({
            'campaign_id': str(row['id']),
            'name': row['name'],
            'status': row['status'],
            'started_at': row['started_at'].isoformat() if row['started_at'] else None,
            'recipients': recipients,
            'sent': int(row['sent_count'] or 0),
            'delivered': delivered,
            'read': read,
            'replied': replied,
            'failed': int(row['failed_count'] or 0),
            'response_rate_pct': (
                round(replied / delivered * 100, 1) if delivered else 0.0
            ),
            'appointments_attributed': int(row['appointments_attributed'] or 0),
            'appointments_completed': int(row['appointments_completed'] or 0),
            'revenue_attributed': round(revenue, 2),
            'cost_amount': round(cost_amount, 2) if cost_amount is not None else None,
            'cost_currency': row['cost_currency'],
            'roi_estimated': roi,
            'attribution_window_days': int(row['attribution_window_days'] or 14),
        })

    totals = {
        'campaigns': len(items),
        'appointments_attributed': sum(item['appointments_attributed'] for item in items),
        'appointments_completed': sum(item['appointments_completed'] for item in items),
        'revenue_attributed': round(
            sum(item['revenue_attributed'] for item in items), 2
        ),
    }

    return {
        'range': {'from_date': start.isoformat(), 'to_date': end.isoformat()},
        'totals': totals,
        'items': items,
    }


@tenant_analytics_router.get('/analytics/referrals')
async def analytics_referrals(
    request: Request,
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    conn: asyncpg.Connection = Depends(get_db),
):
    """TASK-0055: top 20 referrers with their contribution.

    A "referral" is counted when a contact's ``referrer_contact_id`` points at
    another contact in the same tenant and the *referred* contact was created
    inside the requested range. ``appointments_generated`` and
    ``revenue_generated`` aggregate completed appointments of the referred
    contacts whose ``starts_at`` falls inside the same window — so the metrics
    line up with the rest of the analytics dashboard.
    """
    tenant_id = await tenant_id_from_request(request, conn)
    start, end = _resolve_analytics_range(from_date, to_date)
    range_start, range_end = _range_bounds(start, end)

    rows = await conn.fetch(
        """
        with referrals as (
          select referrer_contact_id, id as referred_contact_id
          from app.contacts
          where tenant_id = $1
            and referrer_contact_id is not null
            and created_at >= $2 and created_at < $3
        ),
        per_referrer as (
          select
            r.referrer_contact_id,
            count(*)::int as count_referrals,
            count(distinct a.id) filter (where a.status = 'completed')::int
              as appointments_generated,
            coalesce(
              sum(s.price_amount) filter (where a.status = 'completed'),
              0
            )::float as revenue_generated
          from referrals r
          left join app.appointments a on a.tenant_id = $1
                                       and a.contact_id = r.referred_contact_id
                                       and a.starts_at >= $2
                                       and a.starts_at < $3
          left join app.service_catalog s on s.tenant_id = $1
                                          and s.id = a.service_id
          group by r.referrer_contact_id
        )
        select
          p.referrer_contact_id as id,
          c.display_name,
          c.phone_e164,
          p.count_referrals,
          p.appointments_generated,
          p.revenue_generated
        from per_referrer p
        join app.contacts c on c.tenant_id = $1 and c.id = p.referrer_contact_id
        order by p.revenue_generated desc, p.count_referrals desc,
                 c.display_name asc nulls last
        limit 20
        """,
        tenant_id, range_start, range_end,
    )

    items = [
        {
            'contact_id': str(row['id']),
            'display_name': row['display_name'] or row['phone_e164'] or '—',
            'phone_e164': row['phone_e164'],
            'count_referrals': int(row['count_referrals'] or 0),
            'appointments_generated': int(row['appointments_generated'] or 0),
            'revenue_generated': round(float(row['revenue_generated'] or 0.0), 2),
        }
        for row in rows
    ]
    totals = {
        'referrers': len(items),
        'referrals': sum(item['count_referrals'] for item in items),
        'appointments_generated': sum(item['appointments_generated'] for item in items),
        'revenue_generated': round(
            sum(item['revenue_generated'] for item in items), 2
        ),
    }
    return {
        'range': {'from_date': start.isoformat(), 'to_date': end.isoformat()},
        'totals': totals,
        'items': items,
    }


@tenant_analytics_router.get(
    '/analytics/agents',
    dependencies=[Depends(require_min_role('manager'))],
)
async def analytics_agents(
    request: Request,
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    conn: asyncpg.Connection = Depends(get_db),
):
    """TASK-0068: per-agent performance KPIs.

    Returns metrics for every user with role ``agent`` in this tenant:
    messages sent on the desk, handoffs accepted/resolved, average response
    time after a customer inbound, appointments confirmed by them through the
    desk, revenue attributed to those appointments (price_amount of completed
    ones) and feedback rating on their closed appointments. The "top
    performer of the month" flag points at the agent with the highest
    ``revenue_attributed`` inside the requested range; ties broken by
    ``appointments_confirmed`` then ``handoffs_resolved``.

    BUG-171: gated to manager+ per-route (router is viewer+ for other
    analytics endpoints).
    """
    tenant_id = await tenant_id_from_request(request, conn)
    start, end = _resolve_analytics_range(from_date, to_date)
    range_start, range_end = _range_bounds(start, end)

    rows = await conn.fetch(
        """
        with agents as (
          select u.id as user_id, u.display_name, u.email
          from app.users u
          join app.user_tenant_roles r on r.user_id = u.id
          where r.tenant_id = $1 and r.role = 'agent'
        ),
        messages_sent as (
          select sender_actor_id as user_id, count(*)::int as count
          from app.messages
          where tenant_id = $1
            and direction = 'outbound'
            and sender_actor_type = 'agent'
            and sender_actor_id is not null
            and created_at >= $2 and created_at < $3
          group by sender_actor_id
        ),
        handoffs_accepted as (
          select assigned_to as user_id, count(*)::int as count
          from app.handoffs
          where tenant_id = $1
            and assigned_to is not null
            and status in ('accepted','resolved')
            and updated_at >= $2 and updated_at < $3
          group by assigned_to
        ),
        handoffs_resolved as (
          select assigned_to as user_id, count(*)::int as count
          from app.handoffs
          where tenant_id = $1
            and assigned_to is not null
            and status = 'resolved'
            and updated_at >= $2 and updated_at < $3
          group by assigned_to
        ),
        agent_responses as (
          select m.sender_actor_id as user_id,
                 extract(epoch from (m.created_at - prev_inbound.created_at)) as response_seconds
          from app.messages m
          join lateral (
            select i.created_at
            from app.messages i
            where i.tenant_id = m.tenant_id
              and i.conversation_id = m.conversation_id
              and i.direction = 'inbound'
              and i.created_at < m.created_at
            order by i.created_at desc
            limit 1
          ) as prev_inbound on true
          where m.tenant_id = $1
            and m.direction = 'outbound'
            and m.sender_actor_type = 'agent'
            and m.sender_actor_id is not null
            and m.created_at >= $2 and m.created_at < $3
        ),
        response_times as (
          select user_id, avg(response_seconds)::float as avg_seconds
          from agent_responses
          where response_seconds is not null and response_seconds >= 0
          group by user_id
        ),
        appts_closed as (
          -- BUG-003 fix: qualify with `a.` — both `app.appointments` and the
          -- joined `app.service_catalog` expose a `metadata` column, so an
          -- unqualified `metadata->>...` raises AmbiguousColumnError before
          -- the row even renders. The GROUP BY + WHERE already use `a.metadata`;
          -- the SELECT was the only outlier.
          select a.metadata->>'closed_by_user_id' as user_id,
                 count(*) filter (where a.status = 'confirmed')::int as confirmed_count,
                 coalesce(
                   sum(s.price_amount) filter (where a.status = 'completed'),
                   0
                 )::float as revenue,
                 count(a.id) filter (where a.status = 'completed')::int as completed_count
          from app.appointments a
          left join app.service_catalog s on s.tenant_id = a.tenant_id and s.id = a.service_id
          where a.tenant_id = $1
            and a.metadata ? 'closed_by_user_id'
            and a.created_at >= $2 and a.created_at < $3
          group by a.metadata->>'closed_by_user_id'
        ),
        feedback_per_agent as (
          select a.metadata->>'closed_by_user_id' as user_id,
                 avg(f.rating)::float as avg_rating,
                 count(f.id)::int as ratings_count
          from app.appointment_feedback f
          join app.appointments a on a.tenant_id = f.tenant_id and a.id = f.appointment_id
          where f.tenant_id = $1
            and a.metadata ? 'closed_by_user_id'
            and f.created_at >= $2 and f.created_at < $3
          group by a.metadata->>'closed_by_user_id'
        )
        select
          ag.user_id,
          ag.display_name,
          ag.email,
          coalesce(ms.count, 0)::int as messages_sent,
          coalesce(ha.count, 0)::int as handoffs_accepted,
          coalesce(hr.count, 0)::int as handoffs_resolved,
          coalesce(rt.avg_seconds, 0)::float as avg_response_time_seconds,
          coalesce(ac.confirmed_count, 0)::int as appointments_confirmed,
          coalesce(ac.completed_count, 0)::int as appointments_completed,
          coalesce(ac.revenue, 0)::float as revenue_attributed,
          coalesce(fp.avg_rating, 0)::float as feedback_avg_rating,
          coalesce(fp.ratings_count, 0)::int as feedback_ratings_count
        from agents ag
        left join messages_sent ms on ms.user_id = ag.user_id::text
        left join handoffs_accepted ha on ha.user_id = ag.user_id
        left join handoffs_resolved hr on hr.user_id = ag.user_id
        left join response_times rt on rt.user_id = ag.user_id::text
        left join appts_closed ac on ac.user_id = ag.user_id::text
        left join feedback_per_agent fp on fp.user_id = ag.user_id::text
        order by revenue_attributed desc,
                 appointments_confirmed desc,
                 handoffs_resolved desc,
                 ag.display_name asc nulls last
        """,
        tenant_id, range_start, range_end,
    )

    items = [
        {
            'user_id': str(row['user_id']),
            'display_name': row['display_name'],
            'email': row['email'],
            'messages_sent': int(row['messages_sent'] or 0),
            'handoffs_accepted': int(row['handoffs_accepted'] or 0),
            'handoffs_resolved': int(row['handoffs_resolved'] or 0),
            'avg_response_time_seconds': round(float(row['avg_response_time_seconds'] or 0.0), 2),
            'appointments_confirmed': int(row['appointments_confirmed'] or 0),
            'appointments_completed': int(row['appointments_completed'] or 0),
            'revenue_attributed': round(float(row['revenue_attributed'] or 0.0), 2),
            'feedback_avg_rating': round(float(row['feedback_avg_rating'] or 0.0), 2),
            'feedback_ratings_count': int(row['feedback_ratings_count'] or 0),
        }
        for row in rows
    ]
    top_performer_id: str | None = None
    for item in items:
        if (
            item['revenue_attributed'] > 0
            or item['appointments_confirmed'] > 0
            or item['handoffs_resolved'] > 0
        ):
            top_performer_id = item['user_id']
            break
    totals = {
        'agents': len(items),
        'messages_sent': sum(item['messages_sent'] for item in items),
        'handoffs_accepted': sum(item['handoffs_accepted'] for item in items),
        'handoffs_resolved': sum(item['handoffs_resolved'] for item in items),
        'appointments_confirmed': sum(item['appointments_confirmed'] for item in items),
        'appointments_completed': sum(item['appointments_completed'] for item in items),
        'revenue_attributed': round(
            sum(item['revenue_attributed'] for item in items), 2
        ),
    }
    return {
        'range': {'from_date': start.isoformat(), 'to_date': end.isoformat()},
        'totals': totals,
        'top_performer_user_id': top_performer_id,
        'items': items,
    }

