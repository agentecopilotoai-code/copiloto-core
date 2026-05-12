"""Active-promotion helpers (TASK-0046).

`attach_active_promo` returns the highest-priority promotion that is currently
active for a given service (or ``None``). The booking flow uses it to send the
promo's image and text before presenting services, and again at the booking
recap so the customer sees the offer right when they're about to commit.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

if TYPE_CHECKING:
    import asyncpg

log = structlog.get_logger()


PROMO_COLUMNS = (
    'p.id, p.name, p.description, p.coupon_code, p.discount_percent, '
    'p.valid_from, p.valid_until, p.applies_to_service_ids, p.is_active, '
    'p.sort_order, p.media_asset_id, '
    'm.id as media_id, m.kind as media_kind, m.label as media_label, '
    'm.source_uri as media_source_uri, m.object_key as media_object_key, '
    'm.storage_backend as media_storage_backend, m.storage_bucket as media_storage_bucket, '
    'm.mime_type as media_mime_type'
)


async def attach_active_promo(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    service_id: UUID | None,
    *,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Return the active promotion for ``service_id`` or ``None``.

    A promotion is considered active when:
    - ``is_active`` is true;
    - ``valid_from`` is null or <= now;
    - ``valid_until`` is null or >= now;
    - ``applies_to_service_ids`` either is empty (tenant-wide) or contains
      ``service_id``.

    When several rows match, the lowest ``sort_order`` wins (ties broken by
    ``created_at desc``). The returned dict embeds the linked media asset
    fields with ``media_*`` keys so the caller can render it without a second
    fetch.
    """
    current = now or datetime.now(UTC)
    row = await conn.fetchrow(
        f"""
        select {PROMO_COLUMNS}
        from app.promotions p
        left join app.media_assets m
          on m.id = p.media_asset_id and m.tenant_id = p.tenant_id
        where p.tenant_id = $1
          and p.is_active = true
          and (p.valid_from is null or p.valid_from <= $2)
          and (p.valid_until is null or p.valid_until >= $2)
          and (
            coalesce(array_length(p.applies_to_service_ids, 1), 0) = 0
            or ($3::uuid is not null and $3::uuid = any(p.applies_to_service_ids))
          )
        order by p.sort_order asc, p.created_at desc
        limit 1
        """,
        tenant_id,
        current,
        service_id,
    )
    if not row:
        return None
    return dict(row)


def promo_caption(promo: dict[str, Any]) -> str:
    """Build the human-friendly text that goes with the promo image."""
    parts: list[str] = []
    name = promo.get('name')
    if name:
        parts.append(f'🎁 {name}')
    description = promo.get('description')
    if description:
        parts.append(str(description))
    discount = promo.get('discount_percent')
    coupon = promo.get('coupon_code')
    if discount:
        try:
            pct = float(discount)
        except (TypeError, ValueError):
            pct = None
        if pct:
            line = f'{pct:g}% de descuento'
            if coupon:
                line += f' con el código {coupon}'
            parts.append(line)
    elif coupon:
        parts.append(f'Código promocional: {coupon}')
    valid_until = promo.get('valid_until')
    if valid_until:
        try:
            parts.append(f'Válido hasta {valid_until.strftime("%d/%m/%Y")}')
        except Exception:
            pass
    return '\n'.join(parts) if parts else 'Promoción activa'


async def queue_promo_message(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
    channel_id: UUID,
    channel_account_mode: str,
    promo: dict[str, Any],
) -> UUID | None:
    """Queue the outbound media message (image/video/pdf) for the promo, or a
    plain text fallback if there is no media or the media kind is unsupported
    for the outbound channel. Emits ``promo.media_send_failed`` as a soft
    signal if the insert fails so retries can pick it up later.
    """
    caption = promo_caption(promo)
    media_source = promo.get('media_source_uri')
    media_kind = promo.get('media_kind')
    media_mime = promo.get('media_mime_type')

    message_type = 'text'
    payload: dict[str, Any] = {'promo_id': str(promo['id'])}
    body_text = caption
    media_id: str | None = None
    if media_source and media_kind in {'image', 'video'}:
        message_type = media_kind
        payload['media_source_uri'] = media_source
        payload['media_mime_type'] = media_mime
        payload['caption'] = caption
        body_text = caption
    elif media_source and media_kind == 'pdf':
        message_type = 'document'
        payload['media_source_uri'] = media_source
        payload['media_mime_type'] = media_mime
        payload['caption'] = caption

    try:
        outbound = await conn.fetchrow(
            """
            insert into app.messages (
              tenant_id, conversation_id, direction, sender_actor_type,
              body_text, message_type, status, payload, media_id, mime_type
            )
            values ($1, $2, 'outbound', 'bot', $3, $4, 'queued', $5::jsonb, $6, $7)
            returning id
            """,
            tenant_id,
            conversation_id,
            body_text,
            message_type,
            json.dumps(payload),
            media_id,
            media_mime,
        )
    except Exception as exc:
        log.warning(
            'promo.media_send_failed',
            tenant_id=str(tenant_id),
            promo_id=str(promo.get('id')),
            error=str(exc)[:200],
        )
        await conn.execute(
            """
            insert into app.domain_events (
              tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload
            )
            values ($1, 'promotion', $2, 'promo.media_send_failed', $3, $4::jsonb)
            on conflict (tenant_id, idempotency_key) do nothing
            """,
            tenant_id,
            promo['id'],
            f'promo.media_send_failed:{conversation_id}:{promo["id"]}',
            json.dumps({
                'promo_id': str(promo['id']),
                'conversation_id': str(conversation_id),
                'error': str(exc)[:200],
            }),
        )
        return None
    idempotency_key = f'bot_promo:{outbound["id"]}'
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
            'message_type': message_type,
            'promo_id': str(promo['id']),
        }),
    )
    return outbound['id']
