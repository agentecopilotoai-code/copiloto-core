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
ALERT_KIND_OUTBOUND_DLQ_THRESHOLD = 'outbound_dlq_threshold'
WHATSAPP_ALERT_TEMPLATE = 'complaint_alert_v1'
WHATSAPP_ALERT_TEMPLATE_LOCALE = 'es'
# TASK-0065: template separado para alertas de DLQ outbound. Es independiente
# del de queja (variables y tono distintos: hablamos de fallos de envío al
# operador, no de retroalimentación de un cliente).
WHATSAPP_DLQ_ALERT_TEMPLATE = 'operator_dlq_alert_v1'
WHATSAPP_DLQ_ALERT_TEMPLATE_LOCALE = 'es'


def _coerce_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
    return value if isinstance(value, dict) else {}


def normalize_alert_channels(value: Any, *, strict: bool = False) -> dict[str, Any]:
    """Return ``complaint_alert_channels`` with all three keys present.

    When ``strict`` is True (write path), the webhook URL must pass the
    full SSRF guard (HTTPS, no loopback/RFC1918/metadata/credentials, host
    must resolve to a public IP). The read/dispatch path is tolerant: it
    only shape-checks the URL and trusts ``_send_webhook_channel`` to
    re-validate (with DNS) at send time.
    """
    raw = _coerce_dict(value)
    email = raw.get('email') if isinstance(raw.get('email'), list) else []
    whatsapp = raw.get('whatsapp') if isinstance(raw.get('whatsapp'), list) else []
    webhook = raw.get('webhook_url') if isinstance(raw.get('webhook_url'), str) else ''
    webhook_clean = webhook.strip()
    if webhook_clean and strict:
        from app.services.url_guard import validate_outbound_url  # noqa: PLC0415

        # Strict mode raises ``UnsafeOutboundURLError`` to the caller; the
        # PATCH handler maps it to a 422 response.
        validate_outbound_url(webhook_clean)
    return {
        'email': [str(e).strip() for e in email if isinstance(e, str) and e.strip()],
        'whatsapp': [str(w).strip() for w in whatsapp if isinstance(w, str) and w.strip()],
        'webhook_url': webhook_clean,
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


def _resolve_alert_kind(payload: dict[str, Any]) -> str:
    """Return the alert ``kind`` stamped into the payload by the dispatcher.

    Falls back to ``negative_feedback`` for legacy payloads that predate the
    kind-aware formatters (TASK-0065). The dispatcher always stamps the kind,
    so this fallback only matters when the builders are called directly from
    tests.
    """
    kind = payload.get('_kind') or payload.get('kind')
    if isinstance(kind, str) and kind:
        return kind
    return ALERT_KIND_NEGATIVE_FEEDBACK


def _build_outbound_dlq_email(payload: dict[str, Any]) -> tuple[str, str]:
    total = payload.get('total') or 0
    threshold = payload.get('threshold') or 0
    window = payload.get('window_minutes') or 0
    by_code = payload.get('by_error_code') or []
    preview = payload.get('preview') or []
    subject = (
        f'[CopilotoIA] DLQ outbound — {total} fallos en {window} min '
        f'(umbral {threshold})'
    )
    lines = [
        f'En los últimos {window} minutos hubo {total} mensajes outbound que '
        f'terminaron en la DLQ (umbral configurado: {threshold}).',
        '',
        'Distribución por error_code:',
    ]
    if by_code:
        for group in by_code:
            code = group.get('error_code') or '—'
            count = group.get('count') or 0
            lines.append(f'  • {code}: {count}')
    else:
        lines.append('  (sin datos)')
    if preview:
        lines += ['', 'Últimos fallos:']
        for sample in preview[:5]:
            at = sample.get('at') or '—'
            code = sample.get('error_code') or '—'
            msg = (sample.get('error_message') or '').strip().replace('\n', ' ')
            if len(msg) > 200:
                msg = msg[:199] + '…'
            lines.append(f'  • [{at}] {code}: {msg or "—"}')
    lines += [
        '',
        'Abre el panel: Admin Panel → Outbound DLQ para inspeccionar el',
        'payload completo y reintentar los envíos.',
    ]
    return subject, '\n'.join(lines)


def _build_negative_feedback_email(payload: dict[str, Any]) -> tuple[str, str]:
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


def build_email_body(payload: dict[str, Any]) -> tuple[str, str]:
    """Render ``(subject, body)`` for the alert kind stamped in ``payload``.

    The dispatcher injects ``_kind`` from ``operator_alerts.kind`` before
    calling the channel senders, so the builder picks the right format
    (negative feedback / complaint vs DLQ saturation) without coupling the
    sender code to the kind.
    """
    if _resolve_alert_kind(payload) == ALERT_KIND_OUTBOUND_DLQ_THRESHOLD:
        return _build_outbound_dlq_email(payload)
    return _build_negative_feedback_email(payload)


def _build_outbound_dlq_template_components(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Variables 1..4 for ``operator_dlq_alert_v1``.

    {{1}} total, {{2}} ventana en minutos, {{3}} top error_code "131026 (12)",
    {{4}} link al panel (placeholder ``—`` si no se configura).
    """
    by_code = payload.get('by_error_code') or []
    if by_code:
        top = by_code[0]
        top_code = f"{top.get('error_code') or '—'} ({top.get('count') or 0})"
    else:
        top_code = '—'
    return [
        {
            'type': 'body',
            'parameters': [
                {'type': 'text', 'text': str(payload.get('total') or 0)},
                {'type': 'text', 'text': str(payload.get('window_minutes') or 0)},
                {'type': 'text', 'text': top_code},
                {'type': 'text', 'text': payload.get('panel_url') or '—'},
            ],
        }
    ]


def _build_negative_feedback_template_components(payload: dict[str, Any]) -> list[dict[str, Any]]:
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


def build_whatsapp_template_components(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Render template variables for the alert kind stamped in ``payload``."""
    if _resolve_alert_kind(payload) == ALERT_KIND_OUTBOUND_DLQ_THRESHOLD:
        return _build_outbound_dlq_template_components(payload)
    return _build_negative_feedback_template_components(payload)


def whatsapp_template_for_kind(kind: str) -> tuple[str, str]:
    """Return ``(template_name, template_locale)`` for an alert ``kind``."""
    if kind == ALERT_KIND_OUTBOUND_DLQ_THRESHOLD:
        return WHATSAPP_DLQ_ALERT_TEMPLATE, WHATSAPP_DLQ_ALERT_TEMPLATE_LOCALE
    return WHATSAPP_ALERT_TEMPLATE, WHATSAPP_ALERT_TEMPLATE_LOCALE


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


def _wa_id_from_phone(phone_e164: str) -> str:
    """Normalize an E.164 phone for use as a WhatsApp `wa_id` (no leading +).

    Mirrors the helper in `app/workers/digest_worker.py` — kept local to avoid
    a cross-cutting refactor. Both consumers strip the leading `+` so the
    same recipient phone produces the same `app.contacts` row on each call.
    """
    return phone_e164.lstrip('+')


async def _ensure_operator_alert_conversation(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    channel_id: UUID,
    recipient_phone: str,
) -> UUID:
    """BUG-029: garantiza (contacto, conversación) interna para alertas
    salientes al operador.

    Antes este path hacía `insert into app.messages (..., conversation_id, ...)
    values (..., null, ...)` que SIEMPRE fallaba porque la columna es
    `NOT NULL`. El outbound worker marcaba todo como `failed:whatsapp:...` y
    los managers nunca recibían alertas WhatsApp pese a tenerlas configuradas.

    Patrón idéntico al de `digest_worker._ensure_internal_digest_conversation`:
    upsert un contacto marcado `source='internal_operator_alert'` (no contamina
    el funnel/analytics) y reutiliza una conversación dedicada con
    `metadata.kind='internal_operator_alert'` — lookup por kind, no creamos
    una nueva en cada tick. El `app.contacts` UNIQUE(tenant_id, wa_id) hace
    upsert seguro; la conversación se cachea para los retries siguientes.
    """
    wa_id = _wa_id_from_phone(recipient_phone)
    phone_hash = hashlib.sha256(recipient_phone.encode('utf-8')).digest()
    contact_id = await conn.fetchval(
        """
        insert into app.contacts (
          tenant_id, wa_id, phone_e164, phone_hash, source, metadata
        )
        values ($1, $2, $3, $4, 'internal_operator_alert', $5::jsonb)
        on conflict (tenant_id, wa_id) do update
          set updated_at = now()
        returning id
        """,
        tenant_id,
        wa_id,
        recipient_phone,
        phone_hash,
        json.dumps({'internal_operator_alert': True}),
    )
    conversation_id = await conn.fetchval(
        """
        select id from app.conversations
        where tenant_id = $1
          and contact_id = $2
          and channel_id = $3
          and metadata->>'kind' = 'internal_operator_alert'
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
        json.dumps({'kind': 'internal_operator_alert'}),
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
    kind = _resolve_alert_kind(payload)
    template_name, template_locale = whatsapp_template_for_kind(kind)
    components = build_whatsapp_template_components(payload)
    if kind == ALERT_KIND_OUTBOUND_DLQ_THRESHOLD:
        body_label = (
            f'[operator_alert] outbound_dlq total={payload.get("total") or 0}'
        )
    else:
        body_label = f'[operator_alert] {payload.get("contact_name") or "cliente"}'
    queued = 0
    for to in recipients:
        # BUG-029: cada recipient necesita una conversación real (NOT NULL).
        # `_ensure_operator_alert_conversation` upserta contacto + conversación
        # internos por recipient; el lookup por `metadata.kind` los reutiliza
        # entre ticks así que no acumulamos basura por cada retry.
        conversation_id = await _ensure_operator_alert_conversation(
            conn,
            tenant_id=tenant_id,
            channel_id=channel_id,
            recipient_phone=to,
        )
        # BUG-170: capturamos el message_id (RETURNING) y enqueueamos el
        # evento `message.queued` en `app.domain_events`. Sin esto, el
        # `event_worker` no ve el row insertado y el message queda
        # `status='queued'` forever — el alert WhatsApp nunca llega al
        # operador aunque `_send_whatsapp_channel` reporte success. Mismo
        # defecto que BUG-135 corrigió en `digest_worker`. La idempotency
        # key incluye recipient para soportar el caso multi-destino.
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
                'operator_alert': True,
                'operator_alert_kind': kind,
                'to_phone': to,
                'template_name': template_name,
                'template_locale': template_locale,
                'channel_id': str(channel_id),
                'components': components,
            }),
            body_label,
        )
        idempotency_key = (
            f'operator-alert-{kind}-{tenant_id}-'
            f'{_wa_id_from_phone(to)}-{message_row["id"]}'
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
                'operator_alert': True,
                'operator_alert_kind': kind,
            }),
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
    # BUG01 defense-in-depth: re-validate even if the DB carries a legacy bad
    # URL (e.g. row predates the strict write-time validator).
    from app.services.url_guard import UnsafeOutboundURLError, validate_outbound_url  # noqa: PLC0415
    try:
        validated = validate_outbound_url(url)
    except UnsafeOutboundURLError as exc:
        log.warning(
            'alert_channel.webhook_blocked',
            tenant_id=str(tenant_id),
            error=str(exc),
        )
        return
    body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    secret = read_webhook_secret(tenant_id)
    headers = {'Content-Type': 'application/json'}
    signature = sign_webhook_payload(secret, body)
    if signature:
        headers['X-CopilotoIA-Signature'] = signature
    if http_client is None:  # pragma: no cover - real network
        import httpx

        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            response = await client.post(validated.canonical, content=body, headers=headers)
            response.raise_for_status()
        return
    response = await http_client.post(validated.canonical, content=body, headers=headers)
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
    # TASK-0065: stamp the alert ``kind`` into the payload so the channel
    # builders can pick the right subject / template without each sender
    # signature growing a new positional argument. ``alert_row`` may be an
    # asyncpg.Record (production) or a plain dict (tests); both support the
    # subscript access pattern below.
    try:
        kind_value = alert_row['kind']
    except (KeyError, TypeError):
        kind_value = None
    if isinstance(kind_value, str) and kind_value:
        payload['_kind'] = kind_value
    # TASK-0065: surface the panel URL once so both the WhatsApp template
    # and the email body link to the Outbound DLQ tab without leaking SMTP
    # config to the generic builder.
    if kind_value == ALERT_KIND_OUTBOUND_DLQ_THRESHOLD and not payload.get('panel_url'):
        base = (cfg.admin_panel_public_url or '').rstrip('/')
        if base:
            payload['panel_url'] = f'{base}/admin?tenant={alert_row["tenant_id"]}#outbound-dlq'
    channels = normalize_alert_channels(payload.get('channels'))
    # BUG-159: leer canales ya entregados de attempts anteriores. Si la fila
    # vino de un retry tras error parcial (ej. email OK + webhook 500), no
    # re-disparamos el canal que ya cerró exitoso.
    try:
        already_delivered = set(alert_row['delivered_channels'] or [])
    except (KeyError, TypeError):
        already_delivered = set()
    newly_delivered: list[str] = []
    trace: dict[str, Any] = {
        'email_sent': 0,
        'whatsapp_queued': 0,
        'webhook_sent': False,
        'errors': [],
        'skipped_already_delivered': sorted(already_delivered),
    }
    if email_sender is None:
        email_sender = _send_email_channel
    if whatsapp_sender is None:
        whatsapp_sender = _send_whatsapp_channel
    if webhook_sender is None:
        webhook_sender = _send_webhook_channel
    try:
        if channels['email'] and 'email' not in already_delivered:
            await email_sender(cfg, recipients=channels['email'], payload=payload)
            trace['email_sent'] = len(channels['email'])
            newly_delivered.append('email')
    except Exception as exc:  # noqa: BLE001
        trace['errors'].append(f'email:{exc}')
    try:
        if channels['whatsapp'] and 'whatsapp' not in already_delivered:
            queued = await whatsapp_sender(
                conn,
                tenant_id=alert_row['tenant_id'],
                recipients=channels['whatsapp'],
                payload=payload,
            )
            trace['whatsapp_queued'] = queued or 0
            newly_delivered.append('whatsapp')
    except Exception as exc:  # noqa: BLE001
        trace['errors'].append(f'whatsapp:{exc}')
    try:
        if channels['webhook_url'] and 'webhook' not in already_delivered:
            await webhook_sender(
                tenant_id=alert_row['tenant_id'],
                url=channels['webhook_url'],
                payload=payload,
            )
            trace['webhook_sent'] = True
            newly_delivered.append('webhook')
    except Exception as exc:  # noqa: BLE001
        trace['errors'].append(f'webhook:{exc}')
    trace['newly_delivered'] = newly_delivered
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
        # BUG-159: cualquier canal entregado en este attempt se acumula a
        # `delivered_channels` para que el próximo retry (si los demás canales
        # fallaron) lo skipee y no re-envíe.
        newly_delivered = trace.get('newly_delivered') or []
        if not trace['errors']:
            await conn.execute(
                """
                update app.operator_alerts
                set status='sent', sent_at=now(), last_error=null, updated_at=now(),
                    delivered_channels = (
                      select coalesce(array_agg(distinct c), '{}')
                      from unnest(delivered_channels || $2::text[]) as c
                    )
                where id=$1
                """,
                row['id'],
                list(newly_delivered),
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
                set status='failed', last_error=$2, updated_at=now(),
                    delivered_channels = (
                      select coalesce(array_agg(distinct c), '{}')
                      from unnest(delivered_channels || $3::text[]) as c
                    )
                where id=$1
                """,
                row['id'],
                error_text,
                list(newly_delivered),
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
            set status='pending', last_error=$2, scheduled_for=$3, updated_at=now(),
                delivered_channels = (
                  select coalesce(array_agg(distinct c), '{}')
                  from unnest(delivered_channels || $4::text[]) as c
                )
            where id=$1
            """,
            row['id'],
            error_text,
            next_retry_at(attempts, cfg.alerts_retry_base_seconds),
            list(newly_delivered),
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
    'ALERT_KIND_OUTBOUND_DLQ_THRESHOLD',
    'WHATSAPP_ALERT_TEMPLATE',
    'WHATSAPP_DLQ_ALERT_TEMPLATE',
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
    'whatsapp_template_for_kind',
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
