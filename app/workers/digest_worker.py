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
import json
from datetime import UTC, datetime
from email.message import EmailMessage
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.services.digest import (
    CADENCE_DAILY,
    CADENCE_WEEKLY,
    WHATSAPP_DIGEST_TEMPLATE_LOCALE,
    build_daily_digest,
    build_weekly_digest,
    is_due,
    whatsapp_template_for_cadence,
)
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
          coalesce(ts.locale, 'es-CO') as locale
        from app.digest_subscriptions s
        join app.tenants t on t.id = s.tenant_id
        left join app.tenant_settings ts on ts.tenant_id = s.tenant_id
        where s.enabled = true
        order by s.tenant_id, s.cadence
        """,
    )


def _currency_for_locale(locale: str) -> str:
    """Mapeo simple locale→moneda hasta que TASK-0073 lo haga first-class.

    El digest no es transaccional; un default razonable basta para no
    bloquear el rollout multi-país. El símbolo se concatena con miles.
    """
    locale_norm = (locale or '').lower()
    if locale_norm.startswith('es-mx'):
        return 'MXN'
    if locale_norm.startswith('es-ar'):
        return 'ARS'
    if locale_norm.startswith('es-cl'):
        return 'CLP'
    if locale_norm.startswith('es-pe'):
        return 'PEN'
    return 'COP'


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
    template_name = whatsapp_template_for_cadence(cadence)
    await conn.execute(
        """
        insert into app.messages (
          tenant_id, conversation_id, direction, sender_actor_type,
          message_type, status, payload, body_text
        )
        values ($1, null, 'outbound', 'system', 'template', 'queued', $2::jsonb, $3)
        """,
        tenant_id,
        json.dumps({
            'digest': True,
            'digest_cadence': cadence,
            'to_phone': recipient,
            'template_name': template_name,
            'template_locale': WHATSAPP_DIGEST_TEMPLATE_LOCALE,
            'channel_id': str(channel_id),
            'components': components,
        }),
        f'[digest:{cadence}] manager',
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
            currency=_currency_for_locale(row['locale']),
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
