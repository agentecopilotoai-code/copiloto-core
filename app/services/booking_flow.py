"""Guided booking flow over WhatsApp interactive messages.

The flow advances through these steps, persisting state in
``conversations.metadata.booking_flow``:

1. ``awaiting_service`` — present catalogue as interactive list.
2. ``awaiting_resource`` — present resources for the picked service.
3. ``awaiting_date`` — Today / Tomorrow / Other buttons.
4. ``awaiting_slot`` — first 3 free slots for the picked date.
5. ``completed`` — appointment created and confirmation sent.

Each user reply arrives as an interactive ``button_reply`` or ``list_reply``
whose ``id`` is prefixed with ``book_service:``, ``book_resource:``,
``book_date:`` or ``book_slot:``. The prefix identifies which step is being
answered, so the flow is resilient to out-of-order replies.
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

import structlog

from app.services.audit import audit
from app.services.campaign_attribution import attribute_appointment
from app.services.notifications import create_appointment_reminder_jobs
from app.services.promotions import attach_active_promo, queue_promo_message
from app.services.segments import evaluate_rules
from app.services.whatsapp import (
    build_interactive_button_payload,
    build_interactive_list_payload,
)

if TYPE_CHECKING:
    import asyncpg

log = structlog.get_logger()


STEP_AWAITING_SERVICE = 'awaiting_service'
STEP_AWAITING_PACKAGE = 'awaiting_package'
STEP_AWAITING_BRANCH = 'awaiting_branch'
STEP_AWAITING_RESOURCE = 'awaiting_resource'
STEP_AWAITING_DATE = 'awaiting_date'
STEP_AWAITING_SLOT = 'awaiting_slot'
STEP_COMPLETED = 'completed'

PREFIX_SERVICE = 'book_service'
PREFIX_PACKAGE = 'book_package'
PREFIX_BRANCH = 'book_branch'
PREFIX_RESOURCE = 'book_resource'
PREFIX_DATE = 'book_date'
PREFIX_SLOT = 'book_slot'

PACKAGE_USE_NEW = 'new'  # value sent when the customer prefers paying instead of using a package

WEEKDAY_KEYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
DEFAULT_DURATION_MINUTES = 60
MAX_FUTURE_DAYS = 30


def _parse_json(value: Any, fallback: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return fallback
    return value if value is not None else fallback


def _booking_state(conversation: Any) -> dict[str, Any]:
    meta = _parse_json(conversation.get('metadata'), {})
    if not isinstance(meta, dict):
        return {}
    state = meta.get('booking_flow')
    return state if isinstance(state, dict) else {}


def _interactive_id(inbound_message: Any) -> tuple[str | None, str | None]:
    """Return (prefix, value) for an inbound interactive reply, or (None, None)."""
    payload = _parse_json(inbound_message.get('payload'), {})
    if not isinstance(payload, dict):
        return None, None
    interactive_id = payload.get('interactive_id')
    if not isinstance(interactive_id, str) or ':' not in interactive_id:
        return None, None
    prefix, _, value = interactive_id.partition(':')
    return prefix, value


async def _list_active_services(
    conn: asyncpg.Connection, tenant_id: UUID
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select id, name, category, description, price_amount, price_currency,
               duration_minutes, preparation_notes, applies_when
        from app.service_catalog
        where tenant_id=$1 and is_active=true
        order by sort_order asc, name asc
        limit 10
        """,
        tenant_id,
    )
    return [dict(row) for row in rows]


def _qualification_facts_from_conversation(conversation: Any) -> dict[str, Any]:
    """TASK-0054: pull the keyed qualification facts persisted by the
    qualification flow into a flat dict the ``applies_when`` evaluator can use.

    The qualification flow snapshots both the raw ``answered`` map (keyed by
    question UUID) and the derived presets (``budget_tier``, ``urgency_level``)
    into ``conversations.metadata.qualification``. Newer tenants opt-in by
    setting ``qualification_questions.key`` and storing keyed facts in
    ``metadata.qualification.facts``. We honour the keyed map first and
    silently fall back to presets so older snapshots keep filtering by them.
    """
    meta = _parse_json(conversation.get('metadata'), {})
    if not isinstance(meta, dict):
        return {}
    qualification = meta.get('qualification')
    if not isinstance(qualification, dict):
        return {}
    facts: dict[str, Any] = {}
    keyed = qualification.get('facts')
    if isinstance(keyed, dict):
        facts.update({k: v for k, v in keyed.items() if isinstance(k, str)})
    budget_tier = qualification.get('budget_tier')
    if isinstance(budget_tier, dict):
        facts.setdefault('budget_tier', budget_tier.get('tier_value'))
        facts.setdefault('budget_label', budget_tier.get('tier_label'))
    urgency_level = qualification.get('urgency_level')
    if urgency_level is not None:
        facts.setdefault('urgency_level', urgency_level)
    return facts


def _filter_services_by_qualification(
    services: list[dict[str, Any]], facts: dict[str, Any]
) -> list[dict[str, Any]]:
    """Drop services whose ``applies_when`` rule rejects the current facts.

    A service with empty/null ``applies_when`` always survives. The filter is
    a no-op when ``facts`` is empty so callers without qualification still
    see the full catalogue.
    """
    if not facts:
        return services
    filtered: list[dict[str, Any]] = []
    for service in services:
        if evaluate_rules(service.get('applies_when'), facts):
            filtered.append(service)
    return filtered


async def _fetch_service(
    conn: asyncpg.Connection, tenant_id: UUID, service_id: UUID
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, name, duration_minutes, preparation_notes
        from app.service_catalog
        where tenant_id=$1 and id=$2 and is_active=true
        """,
        tenant_id,
        service_id,
    )
    return dict(row) if row else None


async def _list_active_resources(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    branch_id: UUID | None = None,
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select r.id, r.name, r.code, r.capabilities,
               r.bio, r.specialty, r.license_number, r.years_of_experience,
               r.public_profile, r.photo_media_asset_id, r.branch_id,
               m.kind as photo_kind,
               m.mime_type as photo_mime_type,
               m.source_uri as photo_source_uri
        from app.resources r
        left join app.media_assets m
          on m.id = r.photo_media_asset_id and m.tenant_id = r.tenant_id
        where r.tenant_id=$1 and r.is_active=true and r.public_profile=true
          and ($2::uuid is null or r.branch_id = $2)
        order by r.name asc
        limit 10
        """,
        tenant_id,
        branch_id,
    )
    return [dict(row) for row in rows]


async def _list_active_contact_packages(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    contact_id: UUID,
    service_id: UUID,
) -> list[dict[str, Any]]:
    """TASK-0051: return active, paid, non-expired packages of the contact whose
    catalogue covers the picked service (an empty ``includes_service_ids`` means
    the package applies to any service).
    """
    rows = await conn.fetch(
        """
        select cp.id, cp.package_id, cp.remaining_sessions, cp.expires_at,
               tp.name as package_name, tp.includes_service_ids
        from app.contact_packages cp
        join app.treatment_packages tp
          on tp.id = cp.package_id and tp.tenant_id = cp.tenant_id
        where cp.tenant_id=$1
          and cp.contact_id=$2
          and cp.status='active'
          and cp.payment_status='paid'
          and cp.remaining_sessions > 0
          and (cp.expires_at is null or cp.expires_at > now())
          and (
            coalesce(array_length(tp.includes_service_ids, 1), 0) = 0
            or $3 = any(tp.includes_service_ids)
          )
        order by cp.expires_at asc nulls last, cp.purchased_at asc
        limit 5
        """,
        tenant_id,
        contact_id,
        service_id,
    )
    return [dict(row) for row in rows]


async def _present_packages(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    conversation: Any,
    channel_id: UUID,
    channel_account_mode: str,
    state: dict[str, Any],
    contact_id: UUID,
    service_uuid: UUID,
) -> dict[str, Any] | None:
    """Offer the customer to spend one of their existing package sessions.

    Returns ``None`` when no usable package is found so the caller can fall
    back to the standard branch/resource selection flow. WhatsApp's interactive
    buttons accept at most 3 entries; we list up to 2 packages plus a third
    "use a fresh booking" escape hatch.
    """
    packages = await _list_active_contact_packages(conn, tenant_id, contact_id, service_uuid)
    if not packages:
        return None
    buttons: list[dict[str, str]] = []
    for pkg in packages[:2]:
        title = f'Pkg: {pkg["remaining_sessions"]} restante'[:20]
        buttons.append({'id': f'{PREFIX_PACKAGE}:{pkg["id"]}', 'title': title})
    buttons.append({'id': f'{PREFIX_PACKAGE}:{PACKAGE_USE_NEW}', 'title': 'Cita normal'})
    body_lines = ['Tienes paquetes activos para este servicio:']
    for pkg in packages[:2]:
        body_lines.append(
            f'• {pkg["package_name"]} — quedan {pkg["remaining_sessions"]} sesiones'
        )
    body_lines.append('¿Quieres usar una sesión o pagar la cita por separado?')
    body_text = '\n'.join(body_lines)
    interactive = build_interactive_button_payload(body_text=body_text, buttons=buttons)
    await _queue_interactive_message(
        conn,
        tenant_id=tenant_id,
        conversation_id=conversation['id'],
        channel_id=channel_id,
        channel_account_mode=channel_account_mode,
        body_text=body_text,
        interactive_payload=interactive,
        booking_step=STEP_AWAITING_PACKAGE,
    )
    return {
        **state,
        'step': STEP_AWAITING_PACKAGE,
        'available_package_ids': [str(pkg['id']) for pkg in packages[:2]],
    }


async def _list_active_branches(
    conn: asyncpg.Connection, tenant_id: UUID
) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        """
        select id, name, code, address, city, maps_url, phone_e164, timezone
        from app.branches
        where tenant_id=$1 and is_active=true
        order by sort_order asc, name asc
        limit 10
        """,
        tenant_id,
    )
    return [dict(row) for row in rows]


async def _fetch_branch(
    conn: asyncpg.Connection, tenant_id: UUID, branch_id: UUID
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, name, code, address, city, maps_url, phone_e164, timezone
        from app.branches
        where tenant_id=$1 and id=$2 and is_active=true
        """,
        tenant_id,
        branch_id,
    )
    return dict(row) if row else None


async def _fetch_resource(
    conn: asyncpg.Connection, tenant_id: UUID, resource_id: UUID
) -> dict[str, Any] | None:
    row = await conn.fetchrow(
        """
        select id, name, code, capabilities
        from app.resources
        where tenant_id=$1 and id=$2 and is_active=true
        """,
        tenant_id,
        resource_id,
    )
    return dict(row) if row else None


def _specialist_caption(resource: dict[str, Any]) -> str:
    """Compose a WhatsApp-safe caption from the specialist profile.

    Format: ``<name> • <specialty>\n<bio>`` truncated to 140 chars (the cap
    WhatsApp image captions enforce in practice).
    """
    head = (resource.get('name') or '').strip()
    specialty = (resource.get('specialty') or '').strip()
    if specialty:
        head = f'{head} • {specialty}'
    bio = (resource.get('bio') or '').strip()
    text = f'{head}\n{bio}' if bio else head
    if len(text) > 140:
        text = text[:137].rstrip() + '…'
    return text


async def _queue_specialist_photo(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    channel_id: UUID,
    channel_account_mode: str,
    resource: dict[str, Any],
    booking_step: str,
) -> UUID | None:
    """Queue an image+caption message presenting the specialist profile.

    Falls back to a text-only message when the resource has no photo media.
    """
    caption = _specialist_caption(resource)
    photo_uri = resource.get('photo_source_uri')
    photo_kind = resource.get('photo_kind')
    photo_mime = resource.get('photo_mime_type')
    message_type = 'text'
    payload: dict[str, Any] = {
        'booking_step': booking_step,
        'resource_id': str(resource['id']),
    }
    if photo_uri and photo_kind == 'image':
        message_type = 'image'
        payload['media_source_uri'] = photo_uri
        payload['media_mime_type'] = photo_mime
        payload['caption'] = caption
    outbound = await conn.fetchrow(
        """
        insert into app.messages (
          tenant_id, conversation_id, direction, sender_actor_type,
          body_text, message_type, status, payload, mime_type
        )
        values ($1, $2, 'outbound', 'bot', $3, $4, 'queued', $5::jsonb, $6)
        returning id
        """,
        tenant_id,
        conversation_id,
        caption,
        message_type,
        json.dumps(payload),
        photo_mime if message_type != 'text' else None,
    )
    idempotency_key = f'bot_specialist:{outbound["id"]}'
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
            'channel_account_mode': channel_account_mode,
            'body_text': caption,
            'message_type': message_type,
            'resource_id': str(resource['id']),
        }),
    )
    return outbound['id']


def _working_hours_for_date(
    capabilities: Any, target: date
) -> list[dict[str, str]]:
    config = _parse_json(capabilities, {})
    if not isinstance(config, dict):
        return []
    working_hours = config.get('working_hours')
    if not isinstance(working_hours, dict):
        return []
    weekday_key = WEEKDAY_KEYS[target.weekday()]
    franjas = working_hours.get(weekday_key) or []
    if not isinstance(franjas, list):
        return []
    normalized: list[dict[str, str]] = []
    for franja in franjas:
        if not isinstance(franja, dict):
            continue
        start = franja.get('start')
        end = franja.get('end')
        if isinstance(start, str) and isinstance(end, str) and start and end:
            normalized.append({'start': start, 'end': end})
    return normalized


def _hhmm_to_minutes(value: str) -> int:
    h, _, m = value.partition(':')
    return int(h) * 60 + int(m or 0)


def _minutes_to_hhmm(minutes: int) -> str:
    return f'{minutes // 60:02d}:{minutes % 60:02d}'


def compute_free_slots(
    franjas: list[dict[str, str]],
    busy: list[tuple[int, int]],
    duration_minutes: int,
) -> list[dict[str, str]]:
    if duration_minutes <= 0:
        return []
    slots: list[dict[str, str]] = []
    for franja in franjas:
        start = _hhmm_to_minutes(franja['start'])
        end = _hhmm_to_minutes(franja['end'])
        cursor = start
        while cursor + duration_minutes <= end:
            slot_start = cursor
            slot_end = cursor + duration_minutes
            overlaps = any(
                slot_start < busy_end and busy_start < slot_end
                for busy_start, busy_end in busy
            )
            if not overlaps:
                slots.append({
                    'start_time': _minutes_to_hhmm(slot_start),
                    'end_time': _minutes_to_hhmm(slot_end),
                })
            cursor += duration_minutes
    return slots


async def _busy_intervals(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    resource_id: UUID,
    target_date: date,
) -> list[tuple[int, int]]:
    day_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=UTC)
    day_end = day_start + timedelta(days=1)
    rows = await conn.fetch(
        """
        select starts_at, ends_at
        from app.appointments
        where tenant_id=$1
          and resource_id=$2
          and status in ('scheduled','confirmed')
          and starts_at < $4 and ends_at > $3
        """,
        tenant_id,
        resource_id,
        day_start,
        day_end,
    )
    busy: list[tuple[int, int]] = []
    for row in rows:
        starts = row['starts_at'].astimezone(UTC).replace(tzinfo=None)
        ends = row['ends_at'].astimezone(UTC).replace(tzinfo=None)
        if starts.date() != target_date:
            continue
        busy.append((
            starts.hour * 60 + starts.minute,
            ends.hour * 60 + ends.minute,
        ))
    return busy


async def _queue_interactive_message(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    channel_id: UUID,
    channel_account_mode: str,
    body_text: str,
    interactive_payload: dict[str, Any],
    booking_step: str,
) -> UUID:
    """Insert an outbound interactive message and enqueue the delivery event."""
    payload = {
        'interactive': interactive_payload,
        'booking_step': booking_step,
    }
    outbound = await conn.fetchrow(
        """
        insert into app.messages (
          tenant_id, conversation_id, direction, sender_actor_type,
          body_text, message_type, status, payload
        )
        values ($1, $2, 'outbound', 'bot', $3, 'interactive', 'queued', $4::jsonb)
        returning id
        """,
        tenant_id,
        conversation_id,
        body_text,
        json.dumps(payload),
    )
    idempotency_key = f'bot_booking:{outbound["id"]}'
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
            'channel_account_mode': channel_account_mode,
            'body_text': body_text,
            'booking_step': booking_step,
        }),
    )
    return outbound['id']


async def _queue_text_message(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    channel_id: UUID,
    channel_account_mode: str,
    body_text: str,
    booking_step: str,
) -> UUID:
    outbound = await conn.fetchrow(
        """
        insert into app.messages (
          tenant_id, conversation_id, direction, sender_actor_type,
          body_text, message_type, status, payload
        )
        values ($1, $2, 'outbound', 'bot', $3, 'text', 'queued', $4::jsonb)
        returning id
        """,
        tenant_id,
        conversation_id,
        body_text,
        json.dumps({'booking_step': booking_step}),
    )
    idempotency_key = f'bot_booking_text:{outbound["id"]}'
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
            'channel_account_mode': channel_account_mode,
            'body_text': body_text,
            'booking_step': booking_step,
        }),
    )
    return outbound['id']


async def _persist_state(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    conversation: Any,
    state: dict[str, Any],
) -> None:
    meta = _parse_json(conversation.get('metadata'), {})
    if not isinstance(meta, dict):
        meta = {}
    meta['booking_flow'] = state
    await conn.execute(
        """
        update app.conversations
        set metadata=$1::jsonb, status='waiting_user', updated_at=now()
        where tenant_id=$2 and id=$3
        """,
        json.dumps(meta),
        tenant_id,
        conversation['id'],
    )


def _format_price(amount: Any, currency: str | None) -> str:
    if amount is None:
        return ''
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return ''
    code = (currency or 'COP').upper()
    return f'{value:,.0f} {code}'


async def _present_services(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    conversation: Any,
    channel_id: UUID,
    channel_account_mode: str,
) -> dict[str, Any] | None:
    services = await _list_active_services(conn, tenant_id)
    if not services:
        return None
    # TASK-0054: filter by ``applies_when`` against the qualification facts.
    # If exactly one service remains, auto-select it and skip straight to
    # packages/branches/resources so the customer doesn't pick from a list
    # of one. If none remain, return None so the orchestrator escalates the
    # conversation to a human (no service matched the qualification answers).
    facts = _qualification_facts_from_conversation(conversation)
    eligible = _filter_services_by_qualification(services, facts)
    if not eligible:
        log.info(
            'booking_flow.no_services_match_qualification',
            tenant_id=str(tenant_id),
            conversation_id=str(conversation['id']),
            fact_keys=list(facts.keys()),
        )
        return None
    if len(eligible) == 1:
        only = eligible[0]
        base_state = {'selected_service_id': str(only['id'])}
        log.info(
            'booking_flow.auto_selected_service',
            tenant_id=str(tenant_id),
            conversation_id=str(conversation['id']),
            service_id=str(only['id']),
        )
        next_state = await _present_branches(
            conn,
            tenant_id=tenant_id,
            conversation=conversation,
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
            state=base_state,
        )
        if next_state is None:
            next_state = await _present_resources(
                conn,
                tenant_id=tenant_id,
                conversation=conversation,
                channel_id=channel_id,
                channel_account_mode=channel_account_mode,
                state=base_state,
            )
        return next_state
    services = eligible
    # TASK-0046: send the active promo (image + text) of the first service
    # that has one so the customer sees the offer before picking.
    for service in services:
        promo = await attach_active_promo(conn, tenant_id, service['id'])
        if promo:
            try:
                await queue_promo_message(
                    conn,
                    tenant_id=tenant_id,
                    conversation_id=conversation['id'],
                    channel_id=channel_id,
                    channel_account_mode=channel_account_mode,
                    promo=promo,
                )
            except Exception:
                log.exception(
                    'booking_flow.promo_send_failed',
                    tenant_id=str(tenant_id),
                    promo_id=str(promo.get('id')),
                )
            break
    rows: list[dict[str, str]] = []
    for service in services:
        title = service['name'][:24]
        description_parts = []
        price = _format_price(service.get('price_amount'), service.get('price_currency'))
        if price:
            description_parts.append(price)
        if service.get('duration_minutes'):
            description_parts.append(f"{service['duration_minutes']} min")
        rows.append({
            'id': f'{PREFIX_SERVICE}:{service["id"]}',
            'title': title,
            'description': ' · '.join(description_parts)[:72] if description_parts else None,
        })
    interactive = build_interactive_list_payload(
        body_text='¿Qué servicio te gustaría agendar?',
        button_label='Ver servicios',
        sections=[{'title': 'Servicios disponibles', 'rows': rows}],
    )
    await _queue_interactive_message(
        conn,
        tenant_id=tenant_id,
        conversation_id=conversation['id'],
        channel_id=channel_id,
        channel_account_mode=channel_account_mode,
        body_text='¿Qué servicio te gustaría agendar?',
        interactive_payload=interactive,
        booking_step=STEP_AWAITING_SERVICE,
    )
    return {'step': STEP_AWAITING_SERVICE}


async def _present_branches(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    conversation: Any,
    channel_id: UUID,
    channel_account_mode: str,
    state: dict[str, Any],
) -> dict[str, Any] | None:
    """TASK-0050: present branches if the tenant has >1 active branch.

    Returns ``None`` when no active branch exists so the caller can fall back
    to a tenant-wide flow. With a single branch, auto-selects it and routes
    straight to ``_present_resources`` (no extra question for the customer).
    """
    branches = await _list_active_branches(conn, tenant_id)
    if not branches:
        return None
    if len(branches) == 1:
        only = branches[0]
        return await _present_resources(
            conn,
            tenant_id=tenant_id,
            conversation=conversation,
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
            state={**state, 'selected_branch_id': str(only['id'])},
        )
    rows: list[dict[str, str]] = []
    for branch in branches:
        title = branch['name'][:24]
        description_parts: list[str] = []
        if branch.get('city'):
            description_parts.append(str(branch['city']))
        elif branch.get('address'):
            description_parts.append(str(branch['address']))
        rows.append({
            'id': f'{PREFIX_BRANCH}:{branch["id"]}',
            'title': title,
            'description': ' · '.join(description_parts)[:72] if description_parts else None,
        })
    interactive = build_interactive_list_payload(
        body_text='¿En qué sede prefieres tu cita?',
        button_label='Ver sedes',
        sections=[{'title': 'Sedes disponibles', 'rows': rows}],
    )
    await _queue_interactive_message(
        conn,
        tenant_id=tenant_id,
        conversation_id=conversation['id'],
        channel_id=channel_id,
        channel_account_mode=channel_account_mode,
        body_text='¿En qué sede prefieres tu cita?',
        interactive_payload=interactive,
        booking_step=STEP_AWAITING_BRANCH,
    )
    return {**state, 'step': STEP_AWAITING_BRANCH}


async def _present_resources(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    conversation: Any,
    channel_id: UUID,
    channel_account_mode: str,
    state: dict[str, Any],
) -> dict[str, Any] | None:
    branch_id_raw = state.get('selected_branch_id')
    branch_uuid = UUID(branch_id_raw) if branch_id_raw else None
    resources = await _list_active_resources(conn, tenant_id, branch_uuid)
    if not resources:
        return None
    if len(resources) == 1:
        resource = resources[0]
        try:
            if resource.get('bio') or resource.get('specialty') or resource.get('photo_source_uri'):
                await _queue_specialist_photo(
                    conn,
                    tenant_id=tenant_id,
                    conversation_id=conversation['id'],
                    channel_id=channel_id,
                    channel_account_mode=channel_account_mode,
                    resource=resource,
                    booking_step=STEP_AWAITING_DATE,
                )
        except Exception:
            log.exception(
                'booking_flow.specialist_send_failed',
                tenant_id=str(tenant_id),
                resource_id=str(resource.get('id')),
            )
        state = {**state, 'selected_resource_id': str(resource['id']), 'step': STEP_AWAITING_DATE}
        return await _present_date(
            conn,
            tenant_id=tenant_id,
            conversation=conversation,
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
            state=state,
        )
    for resource in resources:
        if not (resource.get('bio') or resource.get('specialty') or resource.get('photo_source_uri')):
            continue
        try:
            await _queue_specialist_photo(
                conn,
                tenant_id=tenant_id,
                conversation_id=conversation['id'],
                channel_id=channel_id,
                channel_account_mode=channel_account_mode,
                resource=resource,
                booking_step=STEP_AWAITING_RESOURCE,
            )
        except Exception:
            log.exception(
                'booking_flow.specialist_send_failed',
                tenant_id=str(tenant_id),
                resource_id=str(resource.get('id')),
            )
    rows = [
        {'id': f'{PREFIX_RESOURCE}:{resource["id"]}', 'title': resource['name'][:24]}
        for resource in resources
    ]
    interactive = build_interactive_list_payload(
        body_text='¿Con quién prefieres tu cita?',
        button_label='Ver opciones',
        sections=[{'title': 'Disponibles', 'rows': rows}],
    )
    await _queue_interactive_message(
        conn,
        tenant_id=tenant_id,
        conversation_id=conversation['id'],
        channel_id=channel_id,
        channel_account_mode=channel_account_mode,
        body_text='¿Con quién prefieres tu cita?',
        interactive_payload=interactive,
        booking_step=STEP_AWAITING_RESOURCE,
    )
    return {**state, 'step': STEP_AWAITING_RESOURCE}


async def _present_date(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    conversation: Any,
    channel_id: UUID,
    channel_account_mode: str,
    state: dict[str, Any],
) -> dict[str, Any]:
    buttons = [
        {'id': f'{PREFIX_DATE}:today', 'title': 'Hoy'},
        {'id': f'{PREFIX_DATE}:tomorrow', 'title': 'Mañana'},
        {'id': f'{PREFIX_DATE}:other', 'title': 'Otro día'},
    ]
    interactive = build_interactive_button_payload(
        body_text='¿Qué día prefieres?',
        buttons=buttons,
    )
    await _queue_interactive_message(
        conn,
        tenant_id=tenant_id,
        conversation_id=conversation['id'],
        channel_id=channel_id,
        channel_account_mode=channel_account_mode,
        body_text='¿Qué día prefieres?',
        interactive_payload=interactive,
        booking_step=STEP_AWAITING_DATE,
    )
    return {**state, 'step': STEP_AWAITING_DATE}


async def _present_slots(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    conversation: Any,
    channel_id: UUID,
    channel_account_mode: str,
    state: dict[str, Any],
    target_date: date,
) -> dict[str, Any]:
    resource_id = UUID(state['selected_resource_id'])
    service_id = state.get('selected_service_id')
    service_row = (
        await _fetch_service(conn, tenant_id, UUID(service_id)) if service_id else None
    )
    duration = (
        service_row['duration_minutes']
        if service_row
        else DEFAULT_DURATION_MINUTES
    )
    resource_row = await _fetch_resource(conn, tenant_id, resource_id)
    if not resource_row:
        await _queue_text_message(
            conn,
            tenant_id=tenant_id,
            conversation_id=conversation['id'],
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
            body_text='El profesional ya no está disponible. Empezamos de nuevo: ¿qué servicio te gustaría?',
            booking_step=STEP_AWAITING_SERVICE,
        )
        return {'step': STEP_AWAITING_SERVICE}
    franjas = _working_hours_for_date(resource_row['capabilities'], target_date)
    busy = await _busy_intervals(conn, tenant_id, resource_id, target_date)
    slots = compute_free_slots(franjas, busy, duration)[:3]
    if not slots:
        next_date = await _suggest_next_available_date(
            conn,
            tenant_id=tenant_id,
            resource_id=resource_id,
            duration=duration,
            after=target_date,
        )
        if next_date:
            await _queue_text_message(
                conn,
                tenant_id=tenant_id,
                conversation_id=conversation['id'],
                channel_id=channel_id,
                channel_account_mode=channel_account_mode,
                body_text=(
                    f'No tengo cupos el {target_date.strftime("%d/%m")}. '
                    f'¿Te sirve el {next_date.strftime("%d/%m")}? '
                    'Si sí, responde "sí" y te muestro los horarios.'
                ),
                booking_step=STEP_AWAITING_DATE,
            )
            return {**state, 'step': STEP_AWAITING_DATE, 'proposed_date': next_date.isoformat()}
        await _queue_text_message(
            conn,
            tenant_id=tenant_id,
            conversation_id=conversation['id'],
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
            body_text='No tengo cupos en los próximos días. Te conecto con un asesor.',
            booking_step=STEP_AWAITING_SLOT,
        )
        return {**state, 'step': STEP_AWAITING_SLOT}
    buttons = [
        {
            'id': f'{PREFIX_SLOT}:{slot["start_time"]}',
            'title': slot['start_time'],
        }
        for slot in slots
    ]
    interactive = build_interactive_button_payload(
        body_text=f'Horarios libres el {target_date.strftime("%d/%m")}',
        buttons=buttons,
    )
    await _queue_interactive_message(
        conn,
        tenant_id=tenant_id,
        conversation_id=conversation['id'],
        channel_id=channel_id,
        channel_account_mode=channel_account_mode,
        body_text=f'Horarios libres el {target_date.strftime("%d/%m")}',
        interactive_payload=interactive,
        booking_step=STEP_AWAITING_SLOT,
    )
    return {
        **state,
        'step': STEP_AWAITING_SLOT,
        'proposed_date': target_date.isoformat(),
        'proposed_slots': [slot['start_time'] for slot in slots],
        'duration_minutes': duration,
    }


async def _suggest_next_available_date(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    resource_id: UUID,
    duration: int,
    after: date,
) -> date | None:
    resource_row = await _fetch_resource(conn, tenant_id, resource_id)
    if not resource_row:
        return None
    capabilities = resource_row['capabilities']
    for offset in range(1, MAX_FUTURE_DAYS + 1):
        candidate = after + timedelta(days=offset)
        franjas = _working_hours_for_date(capabilities, candidate)
        if not franjas:
            continue
        busy = await _busy_intervals(conn, tenant_id, resource_id, candidate)
        if compute_free_slots(franjas, busy, duration):
            return candidate
    return None


async def _create_appointment(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    contact: Any,
    conversation: Any,
    channel_id: UUID,
    channel_account_mode: str,
    state: dict[str, Any],
    slot_start: str,
) -> dict[str, Any]:
    target_date = date.fromisoformat(state['proposed_date'])
    duration = int(state.get('duration_minutes') or DEFAULT_DURATION_MINUTES)
    start_hour, start_minute = (int(p) for p in slot_start.split(':'))
    starts_at = datetime.combine(
        target_date, datetime.min.time()
    ).replace(hour=start_hour, minute=start_minute, tzinfo=UTC)
    ends_at = starts_at + timedelta(minutes=duration)
    resource_id = UUID(state['selected_resource_id'])
    service_id_raw = state.get('selected_service_id')
    service_uuid = UUID(service_id_raw) if service_id_raw else None
    service_row = (
        await _fetch_service(conn, tenant_id, service_uuid) if service_uuid else None
    )
    service_code = (service_row['name'] if service_row else 'general')[:80]
    branch_id_raw = state.get('selected_branch_id')
    branch_uuid = UUID(branch_id_raw) if branch_id_raw else None
    if branch_uuid is None:
        # TASK-0050: derive branch from the chosen resource if the booking flow
        # ran without an explicit branch step (single-branch tenants).
        branch_uuid = await conn.fetchval(
            'select branch_id from app.resources where tenant_id=$1 and id=$2',
            tenant_id,
            resource_id,
        )
    contact_package_id_raw = state.get('selected_contact_package_id')
    contact_package_uuid: UUID | None = None
    if contact_package_id_raw:
        try:
            contact_package_uuid = UUID(contact_package_id_raw)
        except ValueError:
            contact_package_uuid = None
    try:
        appointment = await conn.fetchrow(
            """
            insert into app.appointments (
              tenant_id, contact_id, conversation_id, service_id,
              resource_id, service_code, starts_at, ends_at, status, branch_id
            )
            values ($1, $2, $3, $4, $5, $6, $7, $8, 'scheduled', $9)
            returning id, starts_at, ends_at
            """,
            tenant_id,
            contact['id'],
            conversation['id'],
            service_uuid,
            resource_id,
            service_code,
            starts_at,
            ends_at,
            branch_uuid,
        )
    except Exception as exc:  # asyncpg.ExclusionViolationError or other
        log.warning(
            'booking_flow.slot_conflict',
            tenant_id=str(tenant_id),
            resource_id=str(resource_id),
            slot=slot_start,
            error=str(exc)[:200],
        )
        await _queue_text_message(
            conn,
            tenant_id=tenant_id,
            conversation_id=conversation['id'],
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
            body_text=(
                'Ese horario se acaba de ocupar. Vamos a buscar otro: '
                '¿qué día prefieres?'
            ),
            booking_step=STEP_AWAITING_DATE,
        )
        new_state = {**state, 'step': STEP_AWAITING_DATE}
        new_state.pop('proposed_slots', None)
        return new_state

    # TASK-0051: bind the appointment to the chosen package so the on-completion
    # trigger discounts a session. Validates the package is still active and
    # belongs to the same contact to avoid replay/race issues.
    if contact_package_uuid is not None:
        package_check = await conn.fetchrow(
            """
            select id, remaining_sessions
            from app.contact_packages
            where tenant_id=$1
              and id=$2
              and contact_id=$3
              and status='active'
              and remaining_sessions > 0
              and (expires_at is null or expires_at > now())
            """,
            tenant_id,
            contact_package_uuid,
            contact['id'],
        )
        if package_check:
            await conn.execute(
                """
                insert into app.appointment_package_links (
                  appointment_id, contact_package_id, tenant_id
                )
                values ($1, $2, $3)
                on conflict (appointment_id) do nothing
                """,
                appointment['id'],
                contact_package_uuid,
                tenant_id,
            )

    resource_row = await _fetch_resource(conn, tenant_id, resource_id)
    summary_lines = [
        '✅ Tu cita quedó agendada:',
        f'• Servicio: {service_row["name"] if service_row else service_code}',
        f'• Fecha: {target_date.strftime("%d/%m/%Y")}',
        f'• Hora: {slot_start} ({duration} min)',
    ]
    if contact_package_uuid is not None:
        summary_lines.append('• Usa 1 sesión de tu paquete activo')
    if resource_row:
        summary_lines.append(f'• Profesional: {resource_row["name"]}')
    if service_row and service_row.get('preparation_notes'):
        summary_lines.append(f'\n📋 Antes de tu cita: {service_row["preparation_notes"]}')

    await _queue_text_message(
        conn,
        tenant_id=tenant_id,
        conversation_id=conversation['id'],
        channel_id=channel_id,
        channel_account_mode=channel_account_mode,
        body_text='\n'.join(summary_lines),
        booking_step=STEP_COMPLETED,
    )

    # TASK-0046: if the chosen service has an active promo, send it after the
    # booking summary so the customer remembers the offer when they review the
    # confirmation. Failures are logged but never block the booking.
    if service_uuid:
        try:
            booking_promo = await attach_active_promo(conn, tenant_id, service_uuid)
            if booking_promo:
                await queue_promo_message(
                    conn,
                    tenant_id=tenant_id,
                    conversation_id=conversation['id'],
                    channel_id=channel_id,
                    channel_account_mode=channel_account_mode,
                    promo=booking_promo,
                )
        except Exception:
            log.exception(
                'booking_flow.promo_close_failed',
                tenant_id=str(tenant_id),
                service_id=str(service_uuid),
            )

    try:
        await create_appointment_reminder_jobs(conn, tenant_id, appointment['id'])
    except Exception:
        log.exception(
            'booking_flow.notifications_failed',
            tenant_id=str(tenant_id),
            appointment_id=str(appointment['id']),
        )

    try:
        await attribute_appointment(
            conn,
            tenant_id=tenant_id,
            appointment_id=appointment['id'],
            contact_id=contact['id'],
        )
    except Exception:
        log.exception(
            'booking_flow.attribution_failed',
            tenant_id=str(tenant_id),
            appointment_id=str(appointment['id']),
        )

    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type='bot',
        actor_id='booking_flow',
        action='bot.appointment_created',
        entity_type='appointment',
        entity_id=str(appointment['id']),
        metadata={
            'service_id': str(service_uuid) if service_uuid else None,
            'resource_id': str(resource_id),
            'starts_at': starts_at.isoformat(),
        },
    )

    log.info(
        'booking_flow.appointment_created',
        tenant_id=str(tenant_id),
        appointment_id=str(appointment['id']),
        starts_at=starts_at.isoformat(),
    )

    return {
        'step': STEP_COMPLETED,
        'appointment_id': str(appointment['id']),
        'selected_service_id': str(service_uuid) if service_uuid else None,
        'selected_resource_id': str(resource_id),
        'selected_contact_package_id': str(contact_package_uuid) if contact_package_uuid else None,
        'starts_at': starts_at.isoformat(),
    }


def _resolve_date_choice(value: str) -> date | None:
    today = datetime.now(UTC).date()
    if value == 'today':
        return today
    if value == 'tomorrow':
        return today + timedelta(days=1)
    return None


async def maybe_run_booking_flow(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    channel_id: UUID,
    channel_account_mode: str,
    conversation: Any,
    contact: Any,
    inbound_message: Any,
    intent: str,
    has_catalog: bool,
    prefilled_service_id: str | None = None,
) -> dict[str, Any] | None:
    """Run the guided booking flow if the conversation is mid-flow or the
    inbound message indicates the user wants to book and the catalog is non-empty.

    Returns a dict like ``{'action': 'booking_step_sent', 'step': '<step>'}``
    when the flow handled the message, or ``None`` to let the existing
    orchestrator continue.
    """
    if not has_catalog:
        return None

    state = _booking_state(conversation)
    prefix, value = _interactive_id(inbound_message)

    if not state and prefix is None and intent != 'book_appointment':
        return None

    idempotency_key = f'booking_flow:{inbound_message["id"]}'
    if await conn.fetchval(
        'select id from app.domain_events where tenant_id=$1 and idempotency_key=$2',
        tenant_id,
        idempotency_key,
    ):
        return {'action': 'skipped', 'reason': 'already_processed'}

    new_state: dict[str, Any] | None = None

    if prefix == PREFIX_SERVICE and value:
        try:
            service_uuid = UUID(value)
        except ValueError:
            service_uuid = None
        if service_uuid:
            service = await _fetch_service(conn, tenant_id, service_uuid)
            if service:
                base_state = {'selected_service_id': str(service_uuid)}
                # TASK-0051: if the contact has active packages that cover the
                # picked service, ask first whether they want to spend one.
                new_state = await _present_packages(
                    conn,
                    tenant_id=tenant_id,
                    conversation=conversation,
                    channel_id=channel_id,
                    channel_account_mode=channel_account_mode,
                    state=base_state,
                    contact_id=contact['id'],
                    service_uuid=service_uuid,
                )
                if new_state is None:
                    # TASK-0050: branch selection if multi-sede, otherwise resources.
                    new_state = await _present_branches(
                        conn,
                        tenant_id=tenant_id,
                        conversation=conversation,
                        channel_id=channel_id,
                        channel_account_mode=channel_account_mode,
                        state=base_state,
                    )
                    if new_state is None:
                        new_state = await _present_resources(
                            conn,
                            tenant_id=tenant_id,
                            conversation=conversation,
                            channel_id=channel_id,
                            channel_account_mode=channel_account_mode,
                            state=base_state,
                        )
    elif prefix == PREFIX_PACKAGE and value:
        # TASK-0051: customer chose between using a saved package session
        # or paying for a fresh appointment.
        if value == PACKAGE_USE_NEW:
            new_state = await _present_branches(
                conn,
                tenant_id=tenant_id,
                conversation=conversation,
                channel_id=channel_id,
                channel_account_mode=channel_account_mode,
                state={k: v for k, v in state.items() if k != 'available_package_ids'},
            )
            if new_state is None:
                new_state = await _present_resources(
                    conn,
                    tenant_id=tenant_id,
                    conversation=conversation,
                    channel_id=channel_id,
                    channel_account_mode=channel_account_mode,
                    state={k: v for k, v in state.items() if k != 'available_package_ids'},
                )
        else:
            allowed = set(state.get('available_package_ids') or [])
            if value in allowed:
                next_state = {
                    **{k: v for k, v in state.items() if k != 'available_package_ids'},
                    'selected_contact_package_id': value,
                }
                new_state = await _present_branches(
                    conn,
                    tenant_id=tenant_id,
                    conversation=conversation,
                    channel_id=channel_id,
                    channel_account_mode=channel_account_mode,
                    state=next_state,
                )
                if new_state is None:
                    new_state = await _present_resources(
                        conn,
                        tenant_id=tenant_id,
                        conversation=conversation,
                        channel_id=channel_id,
                        channel_account_mode=channel_account_mode,
                        state=next_state,
                    )
    elif prefix == PREFIX_BRANCH and value:
        try:
            branch_uuid = UUID(value)
        except ValueError:
            branch_uuid = None
        if branch_uuid:
            branch = await _fetch_branch(conn, tenant_id, branch_uuid)
            if branch:
                new_state = await _present_resources(
                    conn,
                    tenant_id=tenant_id,
                    conversation=conversation,
                    channel_id=channel_id,
                    channel_account_mode=channel_account_mode,
                    state={**state, 'selected_branch_id': str(branch_uuid)},
                )
    elif prefix == PREFIX_RESOURCE and value:
        try:
            resource_uuid = UUID(value)
        except ValueError:
            resource_uuid = None
        if resource_uuid:
            resource = await _fetch_resource(conn, tenant_id, resource_uuid)
            if resource:
                new_state = await _present_date(
                    conn,
                    tenant_id=tenant_id,
                    conversation=conversation,
                    channel_id=channel_id,
                    channel_account_mode=channel_account_mode,
                    state={**state, 'selected_resource_id': str(resource_uuid)},
                )
    elif prefix == PREFIX_DATE and value:
        target_date = _resolve_date_choice(value)
        if target_date is None:
            await _queue_text_message(
                conn,
                tenant_id=tenant_id,
                conversation_id=conversation['id'],
                channel_id=channel_id,
                channel_account_mode=channel_account_mode,
                body_text=(
                    'Indícame la fecha que prefieres (formato DD/MM, por ejemplo 12/06) '
                    'y te muestro los horarios disponibles.'
                ),
                booking_step=STEP_AWAITING_DATE,
            )
            new_state = {**state, 'step': STEP_AWAITING_DATE}
        else:
            new_state = await _present_slots(
                conn,
                tenant_id=tenant_id,
                conversation=conversation,
                channel_id=channel_id,
                channel_account_mode=channel_account_mode,
                state=state,
                target_date=target_date,
            )
    elif prefix == PREFIX_SLOT and value and state.get('proposed_date'):
        new_state = await _create_appointment(
            conn,
            tenant_id=tenant_id,
            contact=contact,
            conversation=conversation,
            channel_id=channel_id,
            channel_account_mode=channel_account_mode,
            state=state,
            slot_start=value,
        )
    elif intent == 'book_appointment' and not state:
        if prefilled_service_id:
            try:
                prefilled_uuid = UUID(prefilled_service_id)
            except ValueError:
                prefilled_uuid = None
            if prefilled_uuid:
                service = await _fetch_service(conn, tenant_id, prefilled_uuid)
                if service:
                    base_state = {'selected_service_id': str(prefilled_uuid)}
                    new_state = await _present_packages(
                        conn,
                        tenant_id=tenant_id,
                        conversation=conversation,
                        channel_id=channel_id,
                        channel_account_mode=channel_account_mode,
                        state=base_state,
                        contact_id=contact['id'],
                        service_uuid=prefilled_uuid,
                    )
                    if new_state is None:
                        new_state = await _present_branches(
                            conn,
                            tenant_id=tenant_id,
                            conversation=conversation,
                            channel_id=channel_id,
                            channel_account_mode=channel_account_mode,
                            state=base_state,
                        )
                    if new_state is None:
                        new_state = await _present_resources(
                            conn,
                            tenant_id=tenant_id,
                            conversation=conversation,
                            channel_id=channel_id,
                            channel_account_mode=channel_account_mode,
                            state=base_state,
                        )
        if new_state is None:
            new_state = await _present_services(
                conn,
                tenant_id=tenant_id,
                conversation=conversation,
                channel_id=channel_id,
                channel_account_mode=channel_account_mode,
            )

    if new_state is None:
        return None

    await _persist_state(conn, tenant_id, conversation, new_state)
    await conn.execute(
        """
        insert into app.domain_events (
          tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload
        )
        values ($1, 'conversation', $2, 'booking_flow.handled', $3, $4::jsonb)
        on conflict (tenant_id, idempotency_key) do nothing
        """,
        tenant_id,
        conversation['id'],
        idempotency_key,
        json.dumps({
            'step': new_state.get('step'),
            'inbound_message_id': str(inbound_message['id']),
            'booking_session_id': str(uuid4()),
        }),
    )
    log.info(
        'booking_flow.handled',
        tenant_id=str(tenant_id),
        conversation_id=str(conversation['id']),
        step=new_state.get('step'),
        prefix=prefix,
    )
    return {'action': 'booking_step_sent', 'step': new_state.get('step')}
