"""TASK-0067 — Worker dedicado del resumen periódico (digest).

Corre como contenedor propio (`docker compose up digest-worker`). Cada 10
minutos consulta las suscripciones activas, decide si toca despachar (08:00
hora del tenant para daily, lunes 08:00 para weekly), arma el payload con
``app.services.digest`` y lo despacha por:

- Email: SMTP vía ``operator_alerts._send_email_channel`` reutilizando la
  configuración de TASK-0057 (no duplicamos credenciales).
- WhatsApp: encolamos un ``messages`` con ``message_type='template'`` para que
  ``event_worker`` lo entregue contra Meta. La plantilla
  ``digest_daily_v1``/``digest_weekly_v1`` debe existir aprobada.

La idempotencia descansa en ``digest_subscriptions.last_sent_at``: solo se
actualiza tras un despacho exitoso, así un fallo de SMTP no marca el día
como enviado.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.services.digest import (
    CADENCE_WEEKLY,
    WHATSAPP_DIGEST_TEMPLATE_LOCALE,
    build_daily_digest,
    build_weekly_digest,
    is_due,
    whatsapp_template_for_cadence,
)
# BUG-183 (codex P2 sobre BUG-135): el `event_worker` espera el bloque
# `template` pre-formateado (mismo defecto que BUG-179 corrigió en
# operator_alerts). Pre-construimos con `build_template_message_payload`.
from app.services.whatsapp import build_template_message_payload
from app.services.operator_alerts import (
    _send_email_smtp,
    build_email_message,
)

log = structlog.get_logger()


# Tick relativamente generoso: la entrega cae en una ventana de 60 min al día,
# así 10 min de tick mantiene la latencia de despacho < 10 min sin spamear la
# base. ``last_sent_at`` impide doble envío incluso si dos ticks caen dentro
# de la ventana.
TICK_SECONDS = 600


async def _fetch_due_subscriptions(
    conn: asyncpg.Connection,
) -> list[asyncpg.Record]:
    """Lista suscripciones habilitadas con timezone del tenant.

    Filtrar la ventana exacta en SQL exigiría manipular zonas en Postgres
    para cada tenant; lo hacemos en Python (``is_due``) porque la cardinalidad
    es baja (una fila por destinatario × cadencia).
    """
    # TASK-0073: `currency` ya vive como columna first-class de tenant_settings;
    # el digest la lee directo sin derivarla del locale.
    return await conn.fetch(
        """
        select
          s.id,
          s.tenant_id,
          s.recipient_email,
          s.recipient_whatsapp,
          s.cadence,
          s.last_sent_at,
          t.timezone as tz_name,
          ts.locale,
          ts.currency
        from app.digest_subscriptions s
        join app.tenants t on t.id = s.tenant_id
        join app.tenant_settings ts on ts.tenant_id = s.tenant_id
        where s.enabled = true
        order by s.tenant_id, s.cadence
        """,
    )


def _wa_id_from_phone(phone_e164: str) -> str:
    """Derive Meta `wa_id` (E.164 sin `+`) del teléfono del manager."""
    return phone_e164.lstrip('+')


async def _ensure_internal_digest_conversation(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    channel_id: UUID,
    recipient_phone: str,
) -> UUID:
    """Garantiza (contacto, conversación) interna para entregas de digest.

    `messages.conversation_id` es NOT NULL — los digests se entregan al
    teléfono del manager, que normalmente ya existe como contacto. Si no
    existe, lo creamos marcado con `source='internal_digest'` y un metadata
    flag para que el funnel/analytics no lo confunda con un cliente. Luego
    upsertamos una conversación dedicada con `metadata.kind='internal_digest'`
    y la reutilizamos en ticks subsiguientes (lookup por kind, no creamos una
    nueva cada vez).
    """
    wa_id = _wa_id_from_phone(recipient_phone)
    phone_hash = hashlib.sha256(recipient_phone.encode('utf-8')).digest()
    contact_id = await conn.fetchval(
        """
        insert into app.contacts (
          tenant_id, wa_id, phone_e164, phone_hash, source, metadata
        )
        values ($1, $2, $3, $4, 'internal_digest', $5::jsonb)
        on conflict (tenant_id, wa_id) do update
          set updated_at = now()
        returning id
        """,
        tenant_id,
        wa_id,
        recipient_phone,
        phone_hash,
        json.dumps({'internal_digest': True}),
    )
    conversation_id = await conn.fetchval(
        """
        select id from app.conversations
        where tenant_id = $1
          and contact_id = $2
          and channel_id = $3
          and metadata->>'kind' = 'internal_digest'
        order by created_at desc
        limit 1
        """,
        tenant_id, contact_id, channel_id,
    )
    if conversation_id is not None:
        return conversation_id
    return await conn.fetchval(
        """
        insert into app.conversations (
          tenant_id, contact_id, channel_id, status, opened_by, metadata
        )
        values ($1, $2, $3, 'open', 'system', $4::jsonb)
        returning id
        """,
        tenant_id,
        contact_id,
        channel_id,
        json.dumps({'kind': 'internal_digest'}),
    )


async def _queue_whatsapp_template(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    recipient: str,
    cadence: str,
    components: list[dict[str, Any]],
) -> bool:
    channel_id = await conn.fetchval(
        """
        select id from app.tenant_channels
        where tenant_id=$1 and provider='whatsapp_cloud_api'
        order by status='active' desc, created_at asc
        limit 1
        """,
        tenant_id,
    )
    if channel_id is None:
        log.warning(
            'digest.whatsapp_skipped_no_channel',
            tenant_id=str(tenant_id),
            cadence=cadence,
        )
        return False
    conversation_id = await _ensure_internal_digest_conversation(
        conn,
        tenant_id=tenant_id,
        channel_id=channel_id,
        recipient_phone=recipient,
    )
    template_name = whatsapp_template_for_cadence(cadence)
    # BUG-183 (codex P2 sobre BUG-135): pre-construir el bloque `template`
    # con shape `{name, language, components}`. El event_worker llama
    # `send_whatsapp_message(template_payload=message_payload.get('template'))`;
    # sin el bloque pre-formateado, `build_whatsapp_message_payload` raise
    # ValueError → digest WhatsApp marcado `failed` aun con mock mode.
    template_block = build_template_message_payload(
        template_name=template_name,
        locale=WHATSAPP_DIGEST_TEMPLATE_LOCALE,
        components=components,
    )
    # BUG-135: insertar la fila en `app.messages` no es suficiente — el
    # `event_worker` consume `domain_events WHERE event_name='message.queued'`
    # para disparar el dispatch outbound. Sin el evento, el digest WhatsApp
    # quedaba en `status='queued'` para siempre y nunca llegaba al manager.
    # Capturamos el message_id (RETURNING) y enqueueamos el evento con una
    # idempotency_key estable.
    message_row = await conn.fetchrow(
        """
        insert into app.messages (
          tenant_id, conversation_id, direction, sender_actor_type,
          message_type, status, payload, body_text
        )
        values ($1, $2, 'outbound', 'system', 'template', 'queued', $3::jsonb, $4)
        returning id
        """,
        tenant_id,
        conversation_id,
        json.dumps({
            'digest': True,
            'digest_cadence': cadence,
            'to_phone': recipient,
            'template_name': template_name,
            'template_locale': WHATSAPP_DIGEST_TEMPLATE_LOCALE,
            'channel_id': str(channel_id),
            'components': components,
            # BUG-183: bloque `template` pre-construido que el event_worker
            # pasa directo a Meta como `template_payload`.
            'template': template_block,
        }),
        f'[digest:{cadence}] manager',
    )
    # BUG-184 (codex P2 sobre BUG-135): la idempotency key antes era
    # `digest-{cadence}-{tenant}-{YYYYMMDD}` — IDÉNTICA para todos los
    # recipients del mismo tenant en el mismo día. `app.domain_events` tiene
    # UNIQUE `(tenant_id, idempotency_key)`, así que el SEGUNDO recipient
    # insertaba el `app.messages` pero su evento `message.queued` colisionaba
    # con `ON CONFLICT DO NOTHING` → manager #2/#3/... nunca recibían el
    # digest. Incluimos el wa_id del recipient en la key para que cada
    # destinatario tenga su propio evento.
    idempotency_key = (
        f'digest-{cadence}-{tenant_id}-{_wa_id_from_phone(recipient)}-'
        f'{datetime.now(UTC).strftime("%Y%m%d")}'
    )
    await conn.execute(
        """
        insert into app.domain_events
          (tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload)
        values ($1, 'message', $2, 'message.queued', $3, $4::jsonb)
        on conflict do nothing
        """,
        tenant_id,
        message_row['id'],
        idempotency_key,
        json.dumps({
            'conversation_id': str(conversation_id),
            'digest': True,
            'digest_cadence': cadence,
        }),
    )
    return True


async def _dispatch_one(
    conn: asyncpg.Connection,
    *,
    row: asyncpg.Record,
    config: Settings,
    now_utc: datetime,
    email_sender: Any | None = None,
    whatsapp_sender: Any | None = None,
) -> bool:
    cadence = row['cadence']
    tenant_id = row['tenant_id']
    tz_name = row['tz_name']
    if not is_due(
        cadence=cadence,
        now_utc=now_utc,
        tz_name=tz_name,
        last_sent_at=row['last_sent_at'],
    ):
        return False
    if cadence == CADENCE_WEEKLY:
        payload = await build_weekly_digest(
            conn,
            tenant_id=tenant_id,
            tz_name=tz_name,
            currency=row['currency'],
        )
    else:
        payload = await build_daily_digest(
            conn, tenant_id=tenant_id, tz_name=tz_name,
        )

    errors: list[str] = []
    delivered = False
    if row['recipient_email']:
        try:
            sender = email_sender or _send_email_smtp
            if not config.alerts_smtp_host or not config.alerts_smtp_from:
                raise RuntimeError('smtp_not_configured')
            msg = build_email_message(
                sender=config.alerts_smtp_from,
                recipients=[row['recipient_email']],
                subject=payload['subject'],
                body=payload['text'],
            )
            await sender(config, msg)
            delivered = True
        except Exception as exc:  # noqa: BLE001
            errors.append(f'email:{exc}')
    if row['recipient_whatsapp']:
        try:
            if whatsapp_sender is not None:
                await whatsapp_sender(
                    conn,
                    tenant_id=tenant_id,
                    recipient=row['recipient_whatsapp'],
                    cadence=cadence,
                    components=payload['whatsapp_components'],
                )
                delivered = True
            else:
                queued = await _queue_whatsapp_template(
                    conn,
                    tenant_id=tenant_id,
                    recipient=row['recipient_whatsapp'],
                    cadence=cadence,
                    components=payload['whatsapp_components'],
                )
                delivered = delivered or queued
        except Exception as exc:  # noqa: BLE001
            errors.append(f'whatsapp:{exc}')

    if delivered:
        await conn.execute(
            'update app.digest_subscriptions set last_sent_at=$2 where id=$1',
            row['id'], now_utc,
        )
        log.info(
            'digest.sent',
            subscription_id=str(row['id']),
            tenant_id=str(tenant_id),
            cadence=cadence,
            errors=errors,
        )
        return True
    log.warning(
        'digest.delivery_failed',
        subscription_id=str(row['id']),
        tenant_id=str(tenant_id),
        cadence=cadence,
        errors=errors,
    )
    return False


async def run_digest_cycle(
    conn: asyncpg.Connection,
    *,
    config: Settings | None = None,
    now_utc: datetime | None = None,
    email_sender: Any | None = None,
    whatsapp_sender: Any | None = None,
) -> int:
    """Procesa todas las suscripciones; devuelve cuántas se despacharon."""
    cfg = config or get_settings()
    now = now_utc or datetime.now(UTC)
    rows = await _fetch_due_subscriptions(conn)
    dispatched = 0
    for row in rows:
        try:
            sent = await _dispatch_one(
                conn,
                row=row,
                config=cfg,
                now_utc=now,
                email_sender=email_sender,
                whatsapp_sender=whatsapp_sender,
            )
            if sent:
                dispatched += 1
        except Exception:  # noqa: BLE001
            log.exception(
                'digest.dispatch_unhandled',
                subscription_id=str(row['id']),
                tenant_id=str(row['tenant_id']),
            )
    return dispatched


async def main() -> None:  # pragma: no cover - manual entrypoint
    configure_logging(get_settings().log_level)
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    await conn.execute("select set_config('app.support_mode', 'true', false)")
    try:
        while True:
            try:
                await run_digest_cycle(conn, config=settings)
            except Exception:
                log.exception('digest.cycle_failed')
            await asyncio.sleep(TICK_SECONDS)
    finally:
        await conn.close()


if __name__ == '__main__':  # pragma: no cover
    asyncio.run(main())
