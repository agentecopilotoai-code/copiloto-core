"""Bulk campaigns to segmented contacts.

Responsibilities
----------------
- Evaluate a JSON ``segment_filter`` against ``contacts`` +
  ``contact_tag_assignments`` + ``appointments`` to derive the list of
  recipients for a campaign.
- Enqueue an approved WhatsApp ``template`` message per recipient as the
  scheduler dispatches a campaign.  Excludes contacts whose
  ``opt_in_status`` is ``revoked`` or ``suppressed``.
- Refresh the campaign delivery counters from ``app.messages`` so the
  webhook status updates roll up into the campaign metrics shown in the
  admin panel.

The worker logic lives in :func:`process_due_campaigns` and is invoked by
``app.workers.scheduler``.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Iterable
from uuid import UUID

import structlog

if TYPE_CHECKING:
    import asyncpg

log = structlog.get_logger()


# Status values on contacts that mean "we cannot reach this person".
SUPPRESSED_OPT_IN_STATUSES: tuple[str, ...] = ('revoked', 'suppressed')

# Maximum number of template messages enqueued per tenant per second.
# Matches the Meta Business API rate limit for non-tiered accounts and gives
# the worker headroom to schedule across multiple campaigns.
DEFAULT_RATE_LIMIT_PER_SECOND = 20

CAMPAIGN_VALID_STATUSES = ('draft', 'scheduled', 'running', 'completed', 'cancelled')


def coerce_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
    return value if isinstance(value, dict) else {}


def normalize_segment_filter(value: Any) -> dict[str, Any]:
    """Return a sanitized ``segment_filter`` dict.

    Unknown keys are dropped so we only accept the supported criteria, which
    keeps the SQL builder predictable and protects against accidental
    injection of arbitrary JSON.
    """
    raw = coerce_dict(value)
    normalized: dict[str, Any] = {}
    tags = raw.get('tags')
    if isinstance(tags, list):
        tag_ids = []
        for tag in tags:
            try:
                tag_ids.append(str(UUID(str(tag))))
            except (ValueError, TypeError):
                continue
        if tag_ids:
            normalized['tags'] = tag_ids
    for key in ('min_appointments', 'last_visit_before_days', 'last_visit_after_days'):
        if key in raw and raw[key] is not None:
            try:
                value_int = int(raw[key])
            except (TypeError, ValueError):
                continue
            if value_int < 0:
                continue
            normalized[key] = value_int
    if 'has_upcoming_appointment' in raw and raw['has_upcoming_appointment'] is not None:
        normalized['has_upcoming_appointment'] = bool(raw['has_upcoming_appointment'])
    return normalized


def build_recipients_query(segment_filter: dict[str, Any]) -> tuple[str, list[Any]]:
    """Return ``(sql, args)`` to fetch the contact ids of a segment.

    The SQL is parametrised so the worker can call ``conn.fetch`` directly.
    All optional criteria are appended as AND clauses; an empty filter
    matches all reachable contacts of the tenant.
    """
    filt = normalize_segment_filter(segment_filter)
    args: list[Any] = []
    placeholder = 1

    def next_placeholder() -> str:
        nonlocal placeholder
        result = f'${placeholder}'
        placeholder += 1
        return result

    tenant_ph = next_placeholder()
    args.append(None)  # tenant_id, filled by caller via _bind

    where_clauses = [
        f'c.tenant_id = {tenant_ph}',
        f"c.opt_in_status not in ('{SUPPRESSED_OPT_IN_STATUSES[0]}','{SUPPRESSED_OPT_IN_STATUSES[1]}')",
        "c.phone_e164 is not null",
    ]

    if 'tags' in filt:
        tag_ph = next_placeholder()
        where_clauses.append(
            f"""exists (
                select 1 from app.contact_tag_assignments cta
                where cta.tenant_id = {tenant_ph}
                  and cta.contact_id = c.id
                  and cta.tag_id = any({tag_ph}::uuid[])
            )"""
        )
        args.append(filt['tags'])

    if 'min_appointments' in filt:
        min_ph = next_placeholder()
        where_clauses.append(
            f"""(
                select count(*) from app.appointments a
                where a.tenant_id = {tenant_ph} and a.contact_id = c.id
            ) >= {min_ph}"""
        )
        args.append(filt['min_appointments'])

    if 'last_visit_before_days' in filt:
        days_ph = next_placeholder()
        where_clauses.append(
            f"""coalesce((
                select max(a.starts_at) from app.appointments a
                where a.tenant_id = {tenant_ph} and a.contact_id = c.id
                  and a.status in ('completed','confirmed','scheduled')
            ), c.created_at) <= now() - ({days_ph} * interval '1 day')"""
        )
        args.append(filt['last_visit_before_days'])

    if 'last_visit_after_days' in filt:
        days_ph = next_placeholder()
        where_clauses.append(
            f"""coalesce((
                select max(a.starts_at) from app.appointments a
                where a.tenant_id = {tenant_ph} and a.contact_id = c.id
                  and a.status in ('completed','confirmed','scheduled')
            ), c.created_at) >= now() - ({days_ph} * interval '1 day')"""
        )
        args.append(filt['last_visit_after_days'])

    if 'has_upcoming_appointment' in filt:
        if filt['has_upcoming_appointment']:
            where_clauses.append(
                f"""exists (
                    select 1 from app.appointments a
                    where a.tenant_id = {tenant_ph} and a.contact_id = c.id
                      and a.status in ('scheduled','confirmed')
                      and a.starts_at >= now()
                )"""
            )
        else:
            where_clauses.append(
                f"""not exists (
                    select 1 from app.appointments a
                    where a.tenant_id = {tenant_ph} and a.contact_id = c.id
                      and a.status in ('scheduled','confirmed')
                      and a.starts_at >= now()
                )"""
            )

    where_sql = ' and '.join(where_clauses)
    sql = f"""
        select c.id, c.wa_id, c.phone_e164, c.display_name, c.opt_in_status
        from app.contacts c
        where {where_sql}
        order by c.created_at
    """
    return sql, args


def _bind_tenant_id(args: list[Any], tenant_id: UUID) -> list[Any]:
    bound = list(args)
    if bound:
        bound[0] = tenant_id
    return bound


async def evaluate_segment(
    conn: 'asyncpg.Connection',
    tenant_id: UUID,
    segment_filter: Any,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return the list of contact rows that match ``segment_filter``."""
    sql, args = build_recipients_query(segment_filter)
    if limit is not None:
        sql = f'{sql} limit {int(limit)}'
    args = _bind_tenant_id(args, tenant_id)
    rows = await conn.fetch(sql, *args)
    return [dict(row) for row in rows]


async def count_recipients(
    conn: 'asyncpg.Connection',
    tenant_id: UUID,
    segment_filter: Any,
) -> int:
    sql, args = build_recipients_query(segment_filter)
    count_sql = f'select count(*) from ({sql}) sub'
    args = _bind_tenant_id(args, tenant_id)
    return int(await conn.fetchval(count_sql, *args) or 0)


async def _resolve_channel_for_template(
    conn: 'asyncpg.Connection',
    tenant_id: UUID,
    template_id: UUID,
) -> tuple[UUID | None, str | None]:
    """Find the WhatsApp channel that should deliver the template."""
    row = await conn.fetchrow(
        """
        select t.channel_id as template_channel_id, t.status,
               c.id as channel_id, c.account_mode
        from app.whatsapp_templates t
        left join app.tenant_channels c
          on c.tenant_id = t.tenant_id
         and (c.id = t.channel_id or (t.channel_id is null and c.provider='whatsapp_cloud_api'))
        where t.tenant_id=$1 and t.id=$2
        order by case when c.id = t.channel_id then 0 else 1 end
        limit 1
        """,
        tenant_id,
        template_id,
    )
    if not row:
        return None, None
    return row['channel_id'], row['account_mode']


def build_template_message_payload(
    template_name: str,
    locale: str,
    variables: dict[str, Any] | None,
) -> dict[str, Any]:
    """Render the ``payload.template`` block sent to the event worker."""
    payload: dict[str, Any] = {
        'name': template_name,
        'language': {'code': locale or 'es'},
    }
    if variables:
        ordered_keys = sorted(
            (k for k in variables.keys()),
            key=lambda k: int(k) if str(k).isdigit() else 0,
        )
        parameters = [
            {'type': 'text', 'text': str(variables[key])} for key in ordered_keys
        ]
        payload['components'] = [{'type': 'body', 'parameters': parameters}]
    return payload


async def _conversation_for_campaign(
    conn: 'asyncpg.Connection',
    tenant_id: UUID,
    contact_id: UUID,
    channel_id: UUID,
) -> UUID:
    row = await conn.fetchrow(
        """
        select id
        from app.conversations
        where tenant_id=$1 and contact_id=$2 and channel_id=$3
          and status not in ('closed','archived')
        order by updated_at desc
        limit 1
        """,
        tenant_id,
        contact_id,
        channel_id,
    )
    if row:
        return row['id']
    created = await conn.fetchrow(
        """
        insert into app.conversations (tenant_id, contact_id, channel_id, status, opened_by)
        values ($1, $2, $3, 'open', 'system')
        returning id
        """,
        tenant_id,
        contact_id,
        channel_id,
    )
    return created['id']


async def enqueue_campaign_message(
    conn: 'asyncpg.Connection',
    *,
    tenant_id: UUID,
    campaign_id: UUID,
    contact_id: UUID,
    channel_id: UUID,
    template_name: str,
    template_locale: str,
    template_variables: dict[str, Any],
) -> UUID:
    """Insert the outbound template message and enqueue ``message.queued``."""
    conversation_id = await _conversation_for_campaign(
        conn, tenant_id, contact_id, channel_id
    )
    template_payload = build_template_message_payload(
        template_name, template_locale, template_variables
    )
    outbound = await conn.fetchrow(
        """
        insert into app.messages (
          tenant_id, conversation_id, direction, sender_actor_type,
          message_type, status, payload, campaign_id
        )
        values ($1, $2, 'outbound', 'system', 'template', 'queued', $3::jsonb, $4)
        returning id
        """,
        tenant_id,
        conversation_id,
        json.dumps({'template': template_payload, 'campaign_id': str(campaign_id)}),
        campaign_id,
    )
    idempotency_key = f'campaign:{campaign_id}:{outbound["id"]}'
    await conn.execute(
        """
        insert into app.domain_events (
          tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload
        )
        values ($1, 'message', $2, 'message.queued', $3, $4::jsonb)
        on conflict (tenant_id, idempotency_key) do nothing
        """,
        tenant_id,
        outbound['id'],
        idempotency_key,
        json.dumps({
            'message_id': str(outbound['id']),
            'conversation_id': str(conversation_id),
            'channel_id': str(channel_id),
            'campaign_id': str(campaign_id),
            'template': template_payload,
        }),
    )
    return outbound['id']


async def refresh_campaign_counters(
    conn: 'asyncpg.Connection',
    tenant_id: UUID,
    campaign_id: UUID,
) -> dict[str, int]:
    """Recompute counters from ``app.messages`` and persist them."""
    row = await conn.fetchrow(
        """
        select
          count(*) filter (where status in ('sent','delivered','read')) as sent_count,
          count(*) filter (where status in ('delivered','read'))         as delivered_count,
          count(*) filter (where status = 'read')                       as read_count,
          count(*) filter (where status = 'failed')                     as failed_count,
          count(*)                                                       as total
        from app.messages
        where tenant_id=$1 and campaign_id=$2
        """,
        tenant_id,
        campaign_id,
    )
    counters = {
        'sent_count': int(row['sent_count'] or 0) if row else 0,
        'delivered_count': int(row['delivered_count'] or 0) if row else 0,
        'read_count': int(row['read_count'] or 0) if row else 0,
        'failed_count': int(row['failed_count'] or 0) if row else 0,
        'total': int(row['total'] or 0) if row else 0,
    }
    await conn.execute(
        """
        update app.campaigns
        set sent_count=$3,
            delivered_count=$4,
            read_count=$5,
            failed_count=$6,
            updated_at=now()
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        campaign_id,
        counters['sent_count'],
        counters['delivered_count'],
        counters['read_count'],
        counters['failed_count'],
    )
    return counters


async def dispatch_campaign(
    conn: 'asyncpg.Connection',
    tenant_id: UUID,
    campaign: dict[str, Any],
    *,
    rate_limit_per_second: int = DEFAULT_RATE_LIMIT_PER_SECOND,
    sleep_func=asyncio.sleep,
) -> dict[str, Any]:
    """Enqueue the template message for every recipient of the campaign.

    Caller is responsible for transitioning the campaign to ``running``
    before invoking this function and to ``completed`` after.
    """
    template = await conn.fetchrow(
        """
        select id, name, locale, status, channel_id
        from app.whatsapp_templates
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        campaign['template_id'],
    )
    if not template:
        return {'enqueued': 0, 'error': 'template_not_found'}
    if template['status'] != 'approved':
        return {'enqueued': 0, 'error': f'template_not_approved:{template["status"]}'}

    channel_id, _account_mode = await _resolve_channel_for_template(
        conn, tenant_id, template['id']
    )
    if not channel_id:
        return {'enqueued': 0, 'error': 'channel_not_found'}

    recipients = await evaluate_segment(conn, tenant_id, campaign.get('segment_filter'))
    variables = coerce_dict(campaign.get('template_variables'))

    rate = max(1, int(rate_limit_per_second))
    enqueued = 0
    for index, recipient in enumerate(recipients):
        await enqueue_campaign_message(
            conn,
            tenant_id=tenant_id,
            campaign_id=campaign['id'],
            contact_id=recipient['id'],
            channel_id=channel_id,
            template_name=template['name'],
            template_locale=template['locale'] or 'es',
            template_variables=variables,
        )
        enqueued += 1
        # Cooperative rate limiting: pause after every ``rate`` messages to
        # stay under the per-tenant cap configured for Meta delivery.
        if rate > 0 and (index + 1) % rate == 0:
            await sleep_func(1.0)

    return {'enqueued': enqueued, 'recipient_count': len(recipients)}


async def process_due_campaigns(conn: 'asyncpg.Connection') -> int:
    """Pick up scheduled campaigns whose time has arrived and dispatch them.

    Returns the number of campaigns processed in this iteration.
    """
    # Claim a batch of due campaigns atomically.
    rows = await conn.fetch(
        """
        update app.campaigns
        set status='running', started_at=coalesce(started_at, now()), updated_at=now()
        where id in (
          select id from app.campaigns
          where status='scheduled'
            and scheduled_at is not null
            and scheduled_at <= now()
          order by scheduled_at
          limit 5
          for update skip locked
        )
        returning *
        """
    )
    processed = 0
    for row in rows:
        tenant_id = row['tenant_id']
        await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
        campaign = dict(row)
        # asyncpg returns the jsonb columns as strings; coerce them so the
        # service helpers can work with native dicts.
        campaign['segment_filter'] = coerce_dict(campaign.get('segment_filter'))
        campaign['template_variables'] = coerce_dict(campaign.get('template_variables'))
        try:
            result = await dispatch_campaign(conn, tenant_id, campaign)
        except Exception as exc:  # pragma: no cover - defensive logging
            log.exception(
                'campaign.dispatch_failed',
                tenant_id=str(tenant_id),
                campaign_id=str(campaign['id']),
                error=str(exc),
            )
            await conn.execute(
                """
                update app.campaigns
                set status='cancelled', completed_at=now(), updated_at=now()
                where tenant_id=$1 and id=$2
                """,
                tenant_id,
                campaign['id'],
            )
            continue
        await conn.execute(
            """
            update app.campaigns
            set status='completed',
                completed_at=now(),
                recipient_count=$3,
                sent_count=$3,
                updated_at=now()
            where tenant_id=$1 and id=$2
            """,
            tenant_id,
            campaign['id'],
            int(result.get('enqueued', 0)),
        )
        log.info(
            'campaign.dispatched',
            tenant_id=str(tenant_id),
            campaign_id=str(campaign['id']),
            enqueued=result.get('enqueued'),
            recipient_count=result.get('recipient_count'),
        )
        processed += 1
    return processed
