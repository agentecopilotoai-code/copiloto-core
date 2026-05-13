"""TASK-0057: outbound operator alerts for negative feedback and complaints.

When a customer leaves a 1–2★ rating or a complaint event fires, this module
enqueues a row in ``app.operator_alerts`` and the alerts worker dispatches it
through whichever channels the tenant configured under
``notification_settings.complaint_alert_channels`` (email, WhatsApp template,
generic webhook). Each channel can be set independently and any subset is
valid; if no channel is configured the alert is dropped silently after one
``ack_skipped`` log line.

Retry is exponential (``alerts_retry_base_seconds`` × 2**attempts) and capped
at ``alerts_max_attempts`` attempts before the row is marked ``failed``.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

from app.core.config import Settings, get_settings

if TYPE_CHECKING:
    import asyncpg

log = structlog.get_logger()


ALERT_KIND_NEGATIVE_FEEDBACK = 'negative_feedback'
ALERT_KIND_COMPLAINT = 'complaint'
WHATSAPP_ALERT_TEMPLATE = 'complaint_alert_v1'
WHATSAPP_ALERT_TEMPLATE_LOCALE = 'es'


def _coerce_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
    return value if isinstance(value, dict) else {}


def normalize_alert_channels(value: Any) -> dict[str, Any]:
    """Return ``complaint_alert_channels`` with all three keys present."""
    raw = _coerce_dict(value)
    email = raw.get('email') if isinstance(raw.get('email'), list) else []
    whatsapp = raw.get('whatsapp') if isinstance(raw.get('whatsapp'), list) else []
    webhook = raw.get('webhook_url') if isinstance(raw.get('webhook_url'), str) else ''
    return {
        'email': [str(e).strip() for e in email if isinstance(e, str) and e.strip()],
        'whatsapp': [str(w).strip() for w in whatsapp if isinstance(w, str) and w.strip()],
        'webhook_url': webhook.strip(),
    }


def channels_configured(channels: dict[str, Any]) -> bool:
    normalized = normalize_alert_channels(channels)
    return bool(
        normalized['email']
        or normalized['whatsapp']
        or normalized['webhook_url']
    )


def build_desk_link(public_url: str | None, tenant_id: UUID, conversation_id: UUID | None) -> str:
    base = (public_url or '').rstrip('/')
    if not base:
        return ''
    if conversation_id is None:
        return f'{base}/admin?tenant={tenant_id}#operations'
    return f'{base}/admin?tenant={tenant_id}#operations/{conversation_id}'


def build_comment_preview(comment: str | None, limit: int = 160) -> str:
    if not comment:
        return ''
    cleaned = comment.strip().replace('\n', ' ')
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + '…'


async def enqueue_operator_alert(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    kind: str,
    payload: dict[str, Any],
) -> UUID | None:
    """Insert a ``pending`` row in ``operator_alerts``.

    Returns ``None`` if the tenant has no channels configured (the alert is
    discarded to avoid stale ``pending`` rows). The caller does not need to
    inspect the result.
    """
    settings_row = await conn.fetchval(
        'select notification_settings from app.tenant_settings where tenant_id=$1',
        tenant_id,
    )
    channels = normalize_alert_channels(
        _coerce_dict(settings_row).get('complaint_alert_channels')
    )
    if not channels_configured(channels):
        log.info(
            'operator_alert.skipped_no_channels',
            tenant_id=str(tenant_id),
            kind=kind,
        )
        return None
    payload_with_channels = {**payload, 'channels': channels}
    row = await conn.fetchrow(
        """
        insert into app.operator_alerts (tenant_id, kind, payload)
        values ($1, $2, $3::jsonb)
        returning id
        """,
        tenant_id,
        kind,
        json.dumps(payload_with_channels),
    )
    log.info(
        'operator_alert.enqueued',
        tenant_id=str(tenant_id),
        kind=kind,
        alert_id=str(row['id']),
    )
    return row['id']


def read_webhook_secret(tenant_id: UUID) -> str | None:
    """Read ``.secrets/tenants/<tenant_id>/alerts_webhook_secret`` if present.

    Returns ``None`` when the secret file is missing — the webhook is then
    posted unsigned and the receiver should accept based on URL alone.
    """
    secret_path = Path('.secrets/tenants') / str(tenant_id) / 'alerts_webhook_secret'
    try:
        if secret_path.is_file():
            return secret_path.read_text(encoding='utf-8').strip() or None
    except OSError:
        return None
    return None


def sign_webhook_payload(secret: str | None, body: bytes) -> str | None:
    if not secret:
        return None
    digest = hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()
    return f'sha256={digest}'


def build_email_message(
    *,
    sender: str,
    recipients: list[str],
    subject: str,
    body: str,
) -> EmailMessage:
    msg = EmailMessage()
    msg['From'] = sender
    msg['To'] = ', '.join(recipients)
    msg['Subject'] = subject
    msg.set_content(body)
    return msg


def build_email_body(payload: dict[str, Any]) -> tuple[str, str]:
    contact = payload.get('contact_name') or 'cliente'
    rating = payload.get('rating')
    preview = payload.get('comment_preview') or ''
    link = payload.get('conversation_url') or ''
    rating_line = f'Calificación: {rating}/5' if rating is not None else 'Queja registrada'
    subject = f'[CopilotoIA] Alerta operativa — {contact} ({rating_line})'
    body_lines = [
        f'Se registró feedback negativo de {contact}.',
        '',
        rating_line,
    ]
    if preview:
        body_lines += ['', f'Mensaje: {preview}']
    if link:
        body_lines += ['', f'Abrir conversación: {link}']
    body_lines += [
        '',
        'Este aviso se envió automáticamente. Configura los canales en el',
        'Admin Panel → Tenant Setup → Notificaciones → Alertas al equipo.',
    ]
    return subject, '\n'.join(body_lines)


def build_whatsapp_template_components(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Variables 1..4 for ``complaint_alert_v1``."""
    rating = payload.get('rating')
    rating_text = f'{rating}/5' if rating is not None else 'queja'
    return [
        {
            'type': 'body',
            'parameters': [
                {'type': 'text', 'text': str(payload.get('contact_name') or 'cliente')},
                {'type': 'text', 'text': rating_text},
                {'type': 'text', 'text': payload.get('comment_preview') or '—'},
                {'type': 'text', 'text': payload.get('conversation_url') or '—'},
            ],
        }
    ]


async def _send_email_channel(
    config: Settings,
    *,
    recipients: list[str],
    payload: dict[str, Any],
) -> None:
    if not recipients:
        return
    if not config.alerts_smtp_host or not config.alerts_smtp_from:
        raise RuntimeError('smtp_not_configured')
    subject, body = build_email_body(payload)
    msg = build_email_message(
        sender=config.alerts_smtp_from,
        recipients=recipients,
        subject=subject,
        body=body,
    )
    await _send_email_smtp(config, msg)


async def _send_email_smtp(config: Settings, msg: EmailMessage) -> None:  # pragma: no cover - I/O
    import aiosmtplib

    await aiosmtplib.send(
        msg,
        hostname=config.alerts_smtp_host,
        port=config.alerts_smtp_port,
        username=config.alerts_smtp_username,
        password=config.alerts_smtp_password,
        start_tls=config.alerts_smtp_use_tls,
        timeout=15,
    )


async def _send_whatsapp_channel(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    recipients: list[str],
    payload: dict[str, Any],
) -> int:
    if not recipients:
        return 0
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
        raise RuntimeError('whatsapp_channel_not_provisioned')
    components = build_whatsapp_template_components(payload)
    queued = 0
    for to in recipients:
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
                'operator_alert': True,
                'to_phone': to,
                'template_name': WHATSAPP_ALERT_TEMPLATE,
                'template_locale': WHATSAPP_ALERT_TEMPLATE_LOCALE,
                'channel_id': str(channel_id),
                'components': components,
            }),
            f'[operator_alert] {payload.get("contact_name") or "cliente"}',
        )
        queued += 1
    return queued


async def _send_webhook_channel(
    *,
    tenant_id: UUID,
    url: str,
    payload: dict[str, Any],
    http_client: Any | None = None,
) -> None:
    if not url:
        return
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    secret = read_webhook_secret(tenant_id)
    headers = {'Content-Type': 'application/json'}
    signature = sign_webhook_payload(secret, body)
    if signature:
        headers['X-CopilotoIA-Signature'] = signature
    if http_client is None:  # pragma: no cover - real network
        import httpx

        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, content=body, headers=headers)
            response.raise_for_status()
        return
    response = await http_client.post(url, content=body, headers=headers)
    if hasattr(response, 'raise_for_status'):
        response.raise_for_status()


async def dispatch_operator_alert(
    conn: asyncpg.Connection,
    *,
    alert_row: Any,
    config: Settings | None = None,
    email_sender: Any | None = None,
    whatsapp_sender: Any | None = None,
    webhook_sender: Any | None = None,
) -> dict[str, Any]:
    """Send one alert through every configured channel.

    ``email_sender``/``whatsapp_sender``/``webhook_sender`` are optional async
    callables used in tests to avoid touching SMTP/HTTP. The default
    implementations dispatch real I/O via aiosmtplib / httpx.
    """
    cfg = config or get_settings()
    payload = _coerce_dict(alert_row['payload'])
    channels = normalize_alert_channels(payload.get('channels'))
    trace: dict[str, Any] = {
        'email_sent': 0,
        'whatsapp_queued': 0,
        'webhook_sent': False,
        'errors': [],
    }
    if email_sender is None:
        email_sender = _send_email_channel
    if whatsapp_sender is None:
        whatsapp_sender = _send_whatsapp_channel
    if webhook_sender is None:
        webhook_sender = _send_webhook_channel
    try:
        if channels['email']:
            await email_sender(cfg, recipients=channels['email'], payload=payload)
            trace['email_sent'] = len(channels['email'])
    except Exception as exc:  # noqa: BLE001
        trace['errors'].append(f'email:{exc}')
    try:
        if channels['whatsapp']:
            queued = await whatsapp_sender(
                conn,
                tenant_id=alert_row['tenant_id'],
                recipients=channels['whatsapp'],
                payload=payload,
            )
            trace['whatsapp_queued'] = queued or 0
    except Exception as exc:  # noqa: BLE001
        trace['errors'].append(f'whatsapp:{exc}')
    try:
        if channels['webhook_url']:
            await webhook_sender(
                tenant_id=alert_row['tenant_id'],
                url=channels['webhook_url'],
                payload=payload,
            )
            trace['webhook_sent'] = True
    except Exception as exc:  # noqa: BLE001
        trace['errors'].append(f'webhook:{exc}')
    return trace


def next_retry_at(attempts: int, base_seconds: int) -> Any:
    """Return ``now() + base * 2**attempts`` exponential backoff offset.

    The scheduler reads ``scheduled_for`` to decide when to retry. We return
    the datetime offset to push into SQL via parameter binding.
    """
    from datetime import UTC, datetime

    return datetime.now(UTC) + timedelta(seconds=base_seconds * (2 ** max(attempts, 0)))


async def process_pending_operator_alerts(
    conn: asyncpg.Connection,
    *,
    config: Settings | None = None,
    email_sender: Any | None = None,
    whatsapp_sender: Any | None = None,
    webhook_sender: Any | None = None,
    batch_size: int = 25,
) -> int:
    """Lock and dispatch up to ``batch_size`` pending alerts.

    Returns the number of rows touched (sent or rescheduled). Called by the
    scheduler on every tick.
    """
    cfg = config or get_settings()
    rows = await conn.fetch(
        """
        update app.operator_alerts
        set attempts = attempts + 1
        where id in (
          select id from app.operator_alerts
          where status='pending' and scheduled_for <= now()
          order by scheduled_for
          limit $1
          for update skip locked
        )
        returning *
        """,
        batch_size,
    )
    for row in rows:
        trace = await dispatch_operator_alert(
            conn,
            alert_row=row,
            config=cfg,
            email_sender=email_sender,
            whatsapp_sender=whatsapp_sender,
            webhook_sender=webhook_sender,
        )
        if not trace['errors']:
            await conn.execute(
                """
                update app.operator_alerts
                set status='sent', sent_at=now(), last_error=null, updated_at=now()
                where id=$1
                """,
                row['id'],
            )
            log.info(
                'operator_alert.sent',
                alert_id=str(row['id']),
                tenant_id=str(row['tenant_id']),
                trace=trace,
            )
            continue
        attempts = row['attempts']
        error_text = '; '.join(trace['errors'])[:500]
        if attempts >= cfg.alerts_max_attempts:
            await conn.execute(
                """
                update app.operator_alerts
                set status='failed', last_error=$2, updated_at=now()
                where id=$1
                """,
                row['id'],
                error_text,
            )
            log.warning(
                'operator_alert.failed',
                alert_id=str(row['id']),
                tenant_id=str(row['tenant_id']),
                attempts=attempts,
                last_error=error_text,
            )
            continue
        await conn.execute(
            """
            update app.operator_alerts
            set status='pending', last_error=$2, scheduled_for=$3, updated_at=now()
            where id=$1
            """,
            row['id'],
            error_text,
            next_retry_at(attempts, cfg.alerts_retry_base_seconds),
        )
        log.info(
            'operator_alert.retry_scheduled',
            alert_id=str(row['id']),
            tenant_id=str(row['tenant_id']),
            attempts=attempts,
            next_attempt_at_offset_s=cfg.alerts_retry_base_seconds * (2 ** attempts),
        )
    return len(rows)


__all__ = [
    'ALERT_KIND_COMPLAINT',
    'ALERT_KIND_NEGATIVE_FEEDBACK',
    'WHATSAPP_ALERT_TEMPLATE',
    'build_comment_preview',
    'build_desk_link',
    'build_email_body',
    'build_email_message',
    'build_whatsapp_template_components',
    'channels_configured',
    'dispatch_operator_alert',
    'enqueue_operator_alert',
    'next_retry_at',
    'normalize_alert_channels',
    'process_pending_operator_alerts',
    'read_webhook_secret',
    'sign_webhook_payload',
]


async def _main() -> None:  # pragma: no cover - manual entrypoint
    import asyncpg

    from app.core.logging import configure_logging

    configure_logging(get_settings().log_level)
    settings = get_settings()
    conn = await asyncpg.connect(settings.database_url)
    await conn.execute("select set_config('app.support_mode', 'true', false)")
    try:
        while True:
            await process_pending_operator_alerts(conn)
            await asyncio.sleep(10)
    finally:
        await conn.close()


if __name__ == '__main__':  # pragma: no cover
    asyncio.run(_main())
