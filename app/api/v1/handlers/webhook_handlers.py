"""Handlers extracted from routes.py for webhook_router.

Original location: app/api/v1/routes.py (refactor step 3).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import UTC, datetime
from typing import Any

import asyncpg
import structlog
from fastapi import Depends, Header, HTTPException, Query, Request, Response

from app.api.v1._helpers.messenger_db import _upsert_messenger_contact
from app.api.v1._helpers.notifications_db import notify_operations_change
from app.api.v1._helpers.payments_db import _fetch_tenant_payment_settings
from app.api.v1._helpers.payments_pure import (
    _appointment_payment_summary,
    _parse_appointment_external_ref,
)
from app.api.v1._helpers.secrets import tenant_secret_ref
from app.api.v1._helpers.whatsapp_db import upsert_whatsapp_contact
from app.api.v1._helpers.whatsapp_pure import (
    _WHATSAPP_WEBHOOK_DUMMY_SECRET,
    whatsapp_phone_number_id_from_payload,
)
from app.api.v1.routes import webhook_router
from app.core.config import get_settings
from app.db.pool import get_db
from app.services.audit import audit, audit_durably
from app.services.meta_messenger import (
    META_MESSENGER_PROVIDERS,
    expected_object_for_provider,
    normalize_messenger_events,
    recipient_id_from_payload,
    serialize_event_for_storage,
    service_window_expiry,
    verify_messenger_signature,
)
from app.services.metrics import record_message
from app.services.payment_provider import (
    PaymentProviderError,
    extract_external_ref,
    extract_payment_status,
    normalize_provider as normalize_payment_provider,
    verify_mercadopago_signature,
    verify_stripe_signature,
)
from app.services.rag_orchestrator import orchestrate_inbound_message
from app.services.subscriptions import (
    INVOICE_FAILED_PURPOSE,
    INVOICE_FAILED_TEMPLATE,
    extract_subscription_event,
)
from app.services.whatsapp import (
    is_meta_message_fresh,
    parse_interactive_reply,
    resolve_secret_ref,
    verify_signature_with_secret,
)

log = structlog.get_logger()


@webhook_router.post('/payments/{provider}', status_code=202)
async def receive_payment_webhook(
    provider: str,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    try:
        normalized_provider = normalize_payment_provider(provider)
    except PaymentProviderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if normalized_provider == 'none':
        raise HTTPException(status_code=404, detail='Unknown payment provider')
    body = await request.body()
    try:
        payload = json.loads(body or b'{}')
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail='Invalid payment webhook payload') from exc

    external_ref = extract_external_ref(normalized_provider, payload)
    appointment_id = _parse_appointment_external_ref(external_ref)
    if not appointment_id:
        raise HTTPException(status_code=400, detail='Payment webhook payload missing external_reference')

    await conn.execute("select set_config('app.support_mode', 'true', true)")
    appointment = await conn.fetchrow(
        'select tenant_id, id, conversation_id, contact_id from app.appointments where id=$1',
        appointment_id,
    )
    if not appointment:
        raise HTTPException(status_code=404, detail='Appointment not found for payment webhook')
    tenant_id = appointment['tenant_id']
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    payment_settings = await _fetch_tenant_payment_settings(conn, tenant_id)
    secret = resolve_secret_ref(payment_settings.get('webhook_secret_ref'))
    if not secret:
        # TASK-0083 / BUG04: fail-closed with 503 when the tenant has not
        # configured a webhook signing secret. We must NOT process the payload
        # — a forged event with a known appointment UUID would otherwise mark
        # the appointment as paid. Audit the rejection so operators can spot
        # the misconfiguration in dashboards.
        # SEC-010 fix: `audit_durably` para que el log sobreviva al ROLLBACK
        # disparado por el `raise HTTPException(...)` de abajo. Con el `audit`
        # normal (atado a la connection del request) el INSERT se perdía y los
        # dashboards no veían los rechazos.
        await audit_durably(
            tenant_id=tenant_id,
            actor_type='system',
            actor_id=None,
            action='payment.webhook_rejected',
            entity_type='appointment',
            entity_id=str(appointment_id),
            metadata={'reason': 'missing_secret', 'provider': normalized_provider},
        )
        raise HTTPException(
            status_code=503,
            detail='payment.webhook_unconfigured',
        )
    # BUG-201 (codex HIGH): pasar `now_ts` a los verifiers para que
    # rechacen firmas viejas (replay window = 5 min default). Sin esto, un
    # atacante con cualquier webhook signed payload válido capturado podía
    # replayearlo indefinidamente para forzar transiciones de payment_status.
    webhook_now_ts = int(datetime.now(UTC).timestamp())
    if normalized_provider == 'mercadopago':
        sig_header = request.headers.get('x-signature')
        request_id = request.headers.get('x-request-id')
        data_id = None
        data = payload.get('data') if isinstance(payload, dict) else None
        if isinstance(data, dict):
            data_id = data.get('id')
        signature_ok = verify_mercadopago_signature(
            body, sig_header, secret,
            request_id=request_id,
            data_id=str(data_id) if data_id else None,
            now_ts=webhook_now_ts,
        )
    else:
        sig_header = request.headers.get('stripe-signature')
        signature_ok = verify_stripe_signature(body, sig_header, secret, now_ts=webhook_now_ts)
    if not signature_ok:
        # SEC-010 fix: ver comentario sobre `audit_durably` arriba.
        await audit_durably(
            tenant_id=tenant_id,
            actor_type='system',
            actor_id=None,
            action='payment.webhook_rejected',
            entity_type='appointment',
            entity_id=str(appointment_id),
            metadata={'reason': 'bad_signature', 'provider': normalized_provider},
        )
        raise HTTPException(status_code=401, detail='Invalid payment webhook signature')

    sha = hashlib.sha256(body).hexdigest()
    await conn.execute(
        """
        insert into app.webhook_events_raw (tenant_id, provider, event_type, headers, payload, payload_sha256)
        values ($1, $2, $3, $4::jsonb, $5::jsonb, $6)
        on conflict (payload_sha256) do nothing
        """,
        tenant_id,
        normalized_provider,
        str(payload.get('type') or payload.get('action') or 'payment'),
        json.dumps(dict(request.headers)),
        json.dumps(payload),
        sha,
    )

    new_status = extract_payment_status(normalized_provider, payload)
    if not new_status:
        return {'status': 'ignored', 'reason': 'no_status_mapped'}

    row = await conn.fetchrow(
        """
        update app.appointments
        set payment_status=$3,
            payment_paid_at=case when $3='paid' then now() else payment_paid_at end
        where tenant_id=$1 and id=$2
        returning *
        """,
        tenant_id,
        appointment_id,
        new_status,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type='service',
        actor_id=f'payment_provider:{normalized_provider}',
        action='appointment.payment_webhook',
        entity_type='appointment',
        entity_id=str(appointment_id),
        metadata={'payment_status': new_status, 'provider': normalized_provider},
    )

    if new_status == 'paid' and appointment['conversation_id']:
        confirmation_text = '✅ Pago recibido. Tu cita queda confirmada.'
        message = await conn.fetchrow(
            """
            insert into app.messages
              (tenant_id, conversation_id, direction, sender_actor_type, body_text, message_type, payload, status)
            values ($1,$2,'outbound','system',$3,'text','{}','queued')
            returning id
            """,
            tenant_id,
            appointment['conversation_id'],
            confirmation_text,
        )
        await conn.execute(
            "insert into app.domain_events (tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload) values ($1,'message',$2,'message.queued',$3,$4::jsonb) on conflict do nothing",
            tenant_id,
            message['id'],
            f'payment-confirmation-{appointment_id}',
            json.dumps({'conversation_id': str(appointment['conversation_id']), 'appointment_id': str(appointment_id)}),
        )

    return _appointment_payment_summary(row)


@webhook_router.post('/subscriptions/{provider}', status_code=202)
async def receive_subscription_webhook(
    provider: str,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    """Handle recurring-billing webhooks for ``contact_subscriptions``.

    Stripe sends ``invoice.payment_succeeded`` / ``invoice.payment_failed``
    with the provider subscription id in ``data.object.subscription``.
    MercadoPago emits ``subscription_authorized_payment`` updates with the
    preapproval id. We translate both into our ``active`` / ``past_due``
    states and queue a WhatsApp template on failure so the customer can
    retry the charge with a fresh card.
    """
    try:
        normalized_provider = normalize_payment_provider(provider)
    except PaymentProviderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if normalized_provider == 'none':
        raise HTTPException(status_code=404, detail='Unknown payment provider')
    body = await request.body()
    try:
        payload = json.loads(body or b'{}')
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail='Invalid subscription webhook payload') from exc

    event = extract_subscription_event(normalized_provider, payload)
    if not event:
        return {'status': 'ignored', 'reason': 'not_a_subscription_event'}

    await conn.execute("select set_config('app.support_mode', 'true', true)")
    subscription = await conn.fetchrow(
        """
        select cs.*, c.phone_e164 as contact_phone_e164, sp.name as plan_name
        from app.contact_subscriptions cs
        join app.contacts c on c.id=cs.contact_id and c.tenant_id=cs.tenant_id
        join app.subscription_plans sp on sp.id=cs.plan_id and sp.tenant_id=cs.tenant_id
        where cs.payment_provider=$1
          and cs.payment_provider_subscription_id=$2
        limit 1
        """,
        normalized_provider,
        event.provider_subscription_id,
    )
    if not subscription:
        raise HTTPException(status_code=404, detail='Subscription not found for webhook')
    tenant_id = subscription['tenant_id']
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    payment_settings = await _fetch_tenant_payment_settings(conn, tenant_id)
    secret = resolve_secret_ref(payment_settings.get('webhook_secret_ref'))
    if not secret:
        # TASK-0083 / BUG04 (subscriptions): same fail-closed rule as the
        # appointment payments webhook above. Without a configured signing
        # secret we refuse the event and audit the rejection.
        # SEC-010 fix: `audit_durably` para sobrevivir el ROLLBACK del raise.
        await audit_durably(
            tenant_id=tenant_id,
            actor_type='system',
            actor_id=None,
            action='payment.webhook_rejected',
            entity_type='contact_subscription',
            entity_id=str(subscription['id']),
            metadata={'reason': 'missing_secret', 'provider': normalized_provider, 'flow': 'subscription'},
        )
        raise HTTPException(
            status_code=503,
            detail='payment.webhook_unconfigured',
        )
    # BUG-201: ver comentario en el handler de payments arriba — mismo fix
    # de freshness para subscription webhooks (replay window 5 min).
    webhook_now_ts = int(datetime.now(UTC).timestamp())
    if normalized_provider == 'mercadopago':
        sig_header = request.headers.get('x-signature')
        request_id = request.headers.get('x-request-id')
        data_id = None
        data = payload.get('data') if isinstance(payload, dict) else None
        if isinstance(data, dict):
            data_id = data.get('id')
        signature_ok = verify_mercadopago_signature(
            body, sig_header, secret,
            request_id=request_id,
            data_id=str(data_id) if data_id else None,
            now_ts=webhook_now_ts,
        )
    else:
        sig_header = request.headers.get('stripe-signature')
        signature_ok = verify_stripe_signature(body, sig_header, secret, now_ts=webhook_now_ts)
    if not signature_ok:
        # SEC-010 fix: ver comentario sobre `audit_durably` arriba.
        await audit_durably(
            tenant_id=tenant_id,
            actor_type='system',
            actor_id=None,
            action='payment.webhook_rejected',
            entity_type='contact_subscription',
            entity_id=str(subscription['id']),
            metadata={'reason': 'bad_signature', 'provider': normalized_provider, 'flow': 'subscription'},
        )
        raise HTTPException(status_code=401, detail='Invalid subscription webhook signature')

    # BUG-136: idempotencia real del webhook. Antes el `on conflict (payload_sha256)
    # do nothing` solo deduplicaba el log raw, pero el resto del flow (update
    # subscription, audit, reminder_jobs, domain_events) se ejecutaba en cada
    # delivery → duplicados de cobro fallido, audit spam, reminders dobles.
    # Ahora capturamos el insert: si no devuelve fila (conflict), el webhook
    # ya se procesó → short-circuit con 200.
    sha = hashlib.sha256(body).hexdigest()
    raw_inserted = await conn.fetchrow(
        """
        insert into app.webhook_events_raw (tenant_id, provider, event_type, headers, payload, payload_sha256)
        values ($1, $2, $3, $4::jsonb, $5::jsonb, $6)
        on conflict (payload_sha256) do nothing
        returning id
        """,
        tenant_id,
        normalized_provider,
        event.event_kind,
        json.dumps(dict(request.headers)),
        json.dumps(payload),
        sha,
    )
    if raw_inserted is None:
        log.info(
            'subscription_webhook.duplicate_skipped',
            tenant_id=str(tenant_id),
            provider=normalized_provider,
            event_kind=event.event_kind,
            payload_sha256=sha[:12],
        )
        return {'status': 'duplicate', 'event_kind': event.event_kind}

    await conn.fetchrow(
        """
        update app.contact_subscriptions
        set status=$3,
            retry_payment_link=case when $3='past_due' then $4 else null end,
            last_invoice_status=$5,
            last_invoice_at=now()
        where tenant_id=$1 and id=$2
        returning *
        """,
        tenant_id,
        subscription['id'],
        event.new_status,
        event.retry_url,
        event.event_kind,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type='service',
        actor_id=f'payment_provider:{normalized_provider}',
        action='contact_subscription.invoice_webhook',
        entity_type='contact_subscription',
        entity_id=str(subscription['id']),
        metadata={'status': event.new_status, 'event': event.event_kind, 'provider': normalized_provider},
    )

    if event.new_status == 'past_due':
        retry_url = event.retry_url or ''
        reminder_payload = {
            'subscription_id': str(subscription['id']),
            'contact_id': str(subscription['contact_id']),
            'contact_phone_e164': subscription['contact_phone_e164'],
            'plan_name': subscription['plan_name'],
            'retry_payment_link': retry_url,
            # BUG-056: `purpose` debe ser el enum del schema
            # (`subscription_payment_failed`), NO el name del template
            # (`subscription_payment_failed_v1`). El scheduler buscaba
            # `whatsapp_templates WHERE purpose=$2` con `_v1` y nunca
            # matcheaba → todos los retries se marcaban `template_not_approved`.
            'purpose': INVOICE_FAILED_PURPOSE,
        }
        await conn.execute(
            """
            insert into app.reminder_jobs
              (tenant_id, target_type, target_id, template_name, template_locale, payload, scheduled_for, status)
            values ($1, 'contact_subscription', $2, $3, 'es_CO', $4::jsonb, now(), 'pending')
            on conflict do nothing
            """,
            tenant_id,
            subscription['id'],
            INVOICE_FAILED_TEMPLATE,
            json.dumps(reminder_payload),
        )
        await conn.execute(
            "insert into app.domain_events (tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload) values ($1,'contact_subscription',$2,'subscription.payment_failed',$3,$4::jsonb) on conflict do nothing",
            tenant_id,
            subscription['id'],
            f'subscription-payment-failed-{subscription["id"]}-{sha[:12]}',
            json.dumps(reminder_payload),
        )

    return {'status': 'ok', 'new_status': event.new_status, 'subscription_id': str(subscription['id'])}


@webhook_router.get('/whatsapp')
async def verify_whatsapp_webhook(
    hub_mode: str | None = Query(default=None, alias='hub.mode'),
    hub_verify_token: str | None = Query(default=None, alias='hub.verify_token'),
    hub_challenge: str | None = Query(default=None, alias='hub.challenge'),
    conn: asyncpg.Connection = Depends(get_db),
):
    if hub_mode != 'subscribe' or not hub_verify_token:
        raise HTTPException(status_code=403, detail='Invalid verify token')
    await conn.execute("select set_config('app.support_mode', 'true', true)")
    rows = await conn.fetch(
        """
        select tenant_id
        from app.tenant_channels
        where provider='whatsapp_cloud_api'
          and status='active'
        """,
    )
    for row in rows:
        verify_token = resolve_secret_ref(tenant_secret_ref(row['tenant_id'], 'whatsapp_verify_token'))
        if verify_token and hmac.compare_digest(verify_token, hub_verify_token):
            return Response(content=hub_challenge or '', media_type='text/plain')
    raise HTTPException(status_code=403, detail='Invalid verify token')


@webhook_router.post('/whatsapp', status_code=202)
async def receive_whatsapp_webhook(request: Request, conn: asyncpg.Connection = Depends(get_db), x_hub_signature_256: str | None = Header(default=None, alias='X-Hub-Signature-256')):
    body = await request.body()
    # SEC-010 fix — Webhook status codes expose active WhatsApp channel IDs.
    # Antes: parse error → 400, phone_number_id ausente → 404, channel no
    # encontrado → 404, firma inválida → 401. Diferentes status codes
    # permitían enumerar phone_number_ids activos en la plataforma.
    # Ahora: TODO rechazo retorna el mismo 401 con el mismo detail. Además
    # ejecutamos el HMAC contra `_WHATSAPP_WEBHOOK_DUMMY_SECRET` cuando no
    # hay channel real para que el tiempo de respuesta (O(n) sobre el body)
    # tampoco distinga "channel inexistente" de "channel existe + firma
    # mala". El payload sigue siendo opcional de parsear sin gatear el
    # rechazo: si falla el JSON, igual computamos el HMAC dummy para
    # uniformar timing.
    payload: dict[str, Any] | None
    try:
        payload = json.loads(body or b'{}')
        if not isinstance(payload, dict):
            payload = None
    except json.JSONDecodeError:
        payload = None

    phone_number_id = (
        whatsapp_phone_number_id_from_payload(payload) if payload is not None else None
    )

    channel = None
    if phone_number_id:
        await conn.execute("select set_config('app.support_mode', 'true', true)")
        channel = await conn.fetchrow(
            """
            select id, tenant_id, app_secret_ref, account_mode
            from app.tenant_channels
            where provider='whatsapp_cloud_api'
              and phone_number_id=$1
              and status='active'
            """,
            phone_number_id,
        )

    # SEC-010 fix — resolver el secret real si hay channel, dummy si no.
    # `_WHATSAPP_WEBHOOK_DUMMY_SECRET` es nonce estable del proceso,
    # imposible que matchee con una firma legítima (ver constante).
    if channel:
        app_secret = (
            resolve_secret_ref(channel['app_secret_ref'])
            or _WHATSAPP_WEBHOOK_DUMMY_SECRET
        )
    else:
        app_secret = _WHATSAPP_WEBHOOK_DUMMY_SECRET

    signature_ok = verify_signature_with_secret(body, x_hub_signature_256, app_secret)

    if not channel or not signature_ok:
        # SEC-010 fix — auditamos durably para mantener forensia de los
        # intentos rechazados (sobrevive al rollback del raise). El
        # `metadata.reason` interno distingue causa real (unknown_channel
        # vs invalid_signature vs invalid_payload) sin que esa info se
        # filtre por el status code/body al caller. Operadores ven el
        # detalle en `app.audit_logs`; el atacante solo ve 401 idéntico.
        if not payload:
            reason = 'invalid_payload'
        elif not phone_number_id:
            reason = 'missing_phone_number_id'
        elif not channel:
            reason = 'unknown_channel'
        else:
            reason = 'invalid_signature'
        await audit_durably(
            tenant_id=channel['tenant_id'] if channel else None,
            actor_type='system',
            actor_id=None,
            action='webhook.whatsapp_rejected',
            entity_type='tenant_channel',
            entity_id=str(channel['id']) if channel else None,
            metadata={
                'reason': reason,
                'phone_number_id_present': bool(phone_number_id),
                'signature_present': bool(x_hub_signature_256),
            },
        )
        # Mismo status + mismo body sin importar la causa real — cierra el oracle.
        raise HTTPException(status_code=401, detail='Invalid webhook signature')

    await conn.execute("select set_config('app.tenant_id', $1, true)", str(channel['tenant_id']))

    # AUDIT-51 / round-3 §1.8 + re-audit §1.8 (2026-05-18): freshness
    # pre-scan ANTES del INSERT a `webhook_events_raw`. Antes el INSERT
    # ocurría siempre y stale payloads (replays de 30+ días) quedaban
    # persistidos ocupando espacio + impidiendo dedupe de deliveries
    # legítimos con el mismo body. Pre-scan: si NINGÚN message del
    # payload está fresco, audit + skip. Cuando hay al menos uno fresco,
    # se persiste y el loop interno sigue droppeando los stale por message
    # (defensa en profundidad sobre `payload_sha256` unique).
    _settings = get_settings()
    _max_age = _settings.webhook_meta_max_message_age_seconds
    _now_ts = int(time.time())
    _has_fresh_message = False
    _total_messages = 0
    for _entry in payload.get('entry', []):
        for _change in _entry.get('changes', []):
            for _message in _change.get('value', {}).get('messages', []):
                _total_messages += 1
                if is_meta_message_fresh(_message, now_ts=_now_ts, max_age_seconds=_max_age):
                    _has_fresh_message = True
                    break
            if _has_fresh_message:
                break
        if _has_fresh_message:
            break
    # Si el payload tiene mensajes y NINGUNO está fresco → skip raw + audit.
    # Para payloads sin `messages` (status updates, etc.) NO aplicamos el gate
    # — esos no llevan timestamp per-message en `messages[].timestamp` y la
    # freshness check no aplica (Meta los envía con su propio dedupe).
    if _total_messages > 0 and not _has_fresh_message:
        await audit(
            conn,
            tenant_id=channel['tenant_id'],
            actor_type='system',
            actor_id=None,
            action='webhook.whatsapp_payload_all_messages_stale',
            entity_type='tenant_channel',
            entity_id=str(channel['id']),
            metadata={
                'message_count': _total_messages,
                'max_age_seconds': _max_age,
                'payload_sha256_prefix': hashlib.sha256(body).hexdigest()[:16],
            },
        )
        return {'status': 'rejected', 'reason': 'all_messages_stale'}

    sha = hashlib.sha256(body).hexdigest()
    await conn.fetchrow(
        """
        insert into app.webhook_events_raw (tenant_id, provider, event_type, headers, payload, payload_sha256)
        values ($1, 'whatsapp_cloud_api', $2, $3::jsonb, $4::jsonb, $5)
        on conflict (payload_sha256) do nothing returning *
        """,
        channel['tenant_id'],
        payload.get('object', 'unknown'),
        json.dumps(dict(request.headers)),
        json.dumps(payload),
        sha,
    )

    # TASK-0081 / BUG20: the signature was verified against the channel
    # resolved from the FIRST phone_number_id in the payload. Each change in
    # entry → changes carries its own metadata.phone_number_id; if any of
    # those differ from the signature-verified channel, the change must be
    # dropped. Otherwise an attacker could ship a payload that mixes two
    # tenants' numbers: the first one passes the signature check and every
    # other change inherits the wrong tenant binding.
    signed_channel_phone_id = phone_number_id
    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            value = change.get('value', {})
            change_phone_id = (value.get('metadata') or {}).get('phone_number_id')
            if change_phone_id and str(change_phone_id) != signed_channel_phone_id:
                # Drop this change. We do not stop processing the rest of
                # the payload — only this specific change is suspect.
                await audit(
                    conn,
                    tenant_id=channel['tenant_id'],
                    actor_type='system',
                    actor_id=None,
                    action='webhook.phone_number_id_mismatch',
                    entity_type='tenant_channel',
                    entity_id=str(channel['id']),
                    metadata={
                        'signed_phone_number_id': signed_channel_phone_id,
                        'change_phone_number_id': str(change_phone_id),
                    },
                )
                continue
            contacts_by_wa_id = {
                str(contact.get('wa_id')): contact
                for contact in value.get('contacts', [])
                if contact.get('wa_id')
            }
            for message in value.get('messages', []):
                wa_id = str(message.get('from') or '').strip()
                external_message_id = str(message.get('id') or '').strip()
                if not wa_id or not external_message_id:
                    continue

                # AUDIT-48 (security #2, 2026-05-18): freshness check anti-replay.
                # Meta envía `timestamp` por message (epoch). Si está fuera de
                # ventana (>7d default), audit-drop el mensaje pero seguimos
                # procesando el resto del payload. Esta es defensa-en-profundidad
                # sobre el sha256 unique (que protege duplicate idénticos pero
                # se pierde si la fila expira por retention).
                settings = get_settings()
                max_age = settings.webhook_meta_max_message_age_seconds
                if not is_meta_message_fresh(message, now_ts=int(time.time()), max_age_seconds=max_age):
                    await audit(
                        conn,
                        tenant_id=channel['tenant_id'],
                        actor_type='system',
                        actor_id=None,
                        action='webhook.whatsapp_message_stale',
                        entity_type='tenant_channel',
                        entity_id=str(channel['id']),
                        metadata={
                            'external_message_id': external_message_id,
                            'wa_id_hash': hashlib.sha256(wa_id.encode()).hexdigest()[:16],
                            'message_timestamp': message.get('timestamp'),
                            'max_age_seconds': max_age,
                        },
                    )
                    continue

                contact_payload = contacts_by_wa_id.get(wa_id, {})
                display_name = contact_payload.get('profile', {}).get('name')
                phone_e164 = f'+{wa_id}' if not wa_id.startswith('+') else wa_id
                phone_hash = hashlib.sha256(phone_e164.encode()).digest()
                contact = await upsert_whatsapp_contact(
                    conn,
                    tenant_id=channel['tenant_id'],
                    wa_id=wa_id,
                    phone_e164=phone_e164,
                    phone_hash=phone_hash,
                    display_name=display_name,
                    metadata={'whatsapp_contact': contact_payload},
                    source='whatsapp_cloud_api',
                )

                conversation = await conn.fetchrow(
                    """
                    select *
                    from app.conversations
                    where tenant_id=$1
                      and contact_id=$2
                      and channel_id=$3
                      and status not in ('resolved','closed','archived')
                    order by updated_at desc
                    limit 1
                    """,
                    channel['tenant_id'],
                    contact['id'],
                    channel['id'],
                )
                if conversation:
                    conversation = await conn.fetchrow(
                        """
                        update app.conversations
                        set status=case
                                when status='human_active' then 'human_active'
                                when status='waiting_agent' and handoff_required then 'waiting_agent'
                                else 'waiting_user'
                            end,
                            handoff_required=case
                                when status='human_active' then handoff_required
                                when status='waiting_agent' and handoff_required then true
                                else false
                            end,
                            updated_at=now()
                        where tenant_id=$1 and id=$2
                        returning *
                        """,
                        channel['tenant_id'],
                        conversation['id'],
                    )
                else:
                    conversation = await conn.fetchrow(
                        """
                        insert into app.conversations (tenant_id, contact_id, channel_id, status, opened_by, handoff_required)
                        values ($1, $2, $3, 'open', 'user', false)
                        returning *
                        """,
                        channel['tenant_id'],
                        contact['id'],
                        channel['id'],
                    )

                message_type = message.get('type') or 'text'
                if message_type not in {'text', 'image', 'audio', 'video', 'document', 'interactive'}:
                    message_type = 'text'
                media_payload = message.get(message_type) if message_type in {'image', 'audio', 'video', 'document'} else None
                media_id = None
                mime_type = None
                if isinstance(media_payload, dict):
                    media_id = media_payload.get('id')
                    mime_type = media_payload.get('mime_type')
                body_text = message.get('text', {}).get('body') if isinstance(message.get('text'), dict) else None
                if body_text is None and isinstance(media_payload, dict):
                    body_text = media_payload.get('caption')
                interactive_reply = parse_interactive_reply(message) if message_type == 'interactive' else None
                if interactive_reply:
                    message = {**message, **interactive_reply}
                    if not body_text:
                        body_text = interactive_reply['interactive_title']
                timestamp = message.get('timestamp')
                received_at = None
                if timestamp:
                    try:
                        received_at = datetime.fromtimestamp(int(timestamp), UTC)
                    except (TypeError, ValueError, OSError):
                        received_at = None
                # WhatsApp surfaces the quoted message id in `context.id` when the
                # contact uses the native "reply" affordance. Persist it on the
                # column so reply-stitching (analytics, threading) can stop reading
                # from the raw payload.
                context_obj = message.get('context') if isinstance(message, dict) else None
                reply_to_external_id = None
                if isinstance(context_obj, dict):
                    candidate = context_obj.get('id')
                    if isinstance(candidate, str) and candidate:
                        reply_to_external_id = candidate
                inbound_message = await conn.fetchrow(
                    """
                    insert into app.messages (
                      tenant_id, conversation_id, external_message_id, direction, sender_actor_type, sender_actor_id,
                      body_text, message_type, media_id, mime_type, payload, status, received_at,
                      reply_to_external_message_id
                    )
                    values ($1, $2, $3, 'inbound', 'contact', $4, $5, $6, $7, $8, $9::jsonb, 'received', coalesce($10::timestamptz, now()), $11)
                    on conflict (tenant_id, external_message_id) do nothing
                    returning *
                    """,
                    channel['tenant_id'],
                    conversation['id'],
                    external_message_id,
                    wa_id,
                    body_text,
                    message_type,
                    str(media_id) if media_id else None,
                    str(mime_type) if mime_type else None,
                    json.dumps(message),
                    received_at,
                    reply_to_external_id,
                )
                if inbound_message:
                    await notify_operations_change(
                        conn,
                        channel['tenant_id'],
                        'conversation.changed',
                        conversation_id=conversation['id'],
                        message_id=inbound_message['id'],
                    )
                    record_message(
                        tenant_id=channel['tenant_id'],
                        direction='inbound',
                        channel='whatsapp',
                        status='accepted',
                    )
                    try:
                        await orchestrate_inbound_message(
                            conn,
                            tenant_id=channel['tenant_id'],
                            channel_id=channel['id'],
                            channel_account_mode=channel['account_mode'] or 'mock',
                            conversation=conversation,
                            contact=contact,
                            inbound_message=inbound_message,
                        )
                    except Exception:
                        log.exception(
                            'rag_orchestrator.error',
                            tenant_id=str(channel['tenant_id']),
                            conversation_id=str(conversation['id']),
                        )
    return {'accepted': True, 'payload_sha256': sha}


@webhook_router.get('/meta/{provider}')
async def verify_messenger_webhook(
    provider: str,
    hub_mode: str | None = Query(default=None, alias='hub.mode'),
    hub_verify_token: str | None = Query(default=None, alias='hub.verify_token'),
    hub_challenge: str | None = Query(default=None, alias='hub.challenge'),
    conn: asyncpg.Connection = Depends(get_db),
):
    if provider not in META_MESSENGER_PROVIDERS:
        raise HTTPException(status_code=404, detail='Unsupported Meta channel provider')
    if hub_mode != 'subscribe' or not hub_verify_token:
        raise HTTPException(status_code=403, detail='Invalid verify token')
    await conn.execute("select set_config('app.support_mode', 'true', true)")
    rows = await conn.fetch(
        """
        select tenant_id
        from app.tenant_channels
        where provider=$1
          and status='active'
        """,
        provider,
    )
    for row in rows:
        verify_token = resolve_secret_ref(
            tenant_secret_ref(row['tenant_id'], f'{provider}_verify_token')
        )
        if verify_token and hmac.compare_digest(verify_token, hub_verify_token):
            return Response(content=hub_challenge or '', media_type='text/plain')
    raise HTTPException(status_code=403, detail='Invalid verify token')


@webhook_router.post('/meta/{provider}', status_code=202)
async def receive_messenger_webhook(
    provider: str,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    x_hub_signature_256: str | None = Header(default=None, alias='X-Hub-Signature-256'),
):
    if provider not in META_MESSENGER_PROVIDERS:
        raise HTTPException(status_code=404, detail='Unsupported Meta channel provider')
    body = await request.body()
    try:
        payload = json.loads(body or b'{}')
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail='Invalid webhook payload') from exc

    expected_object = expected_object_for_provider(provider)
    if expected_object and payload.get('object') and payload.get('object') != expected_object:
        raise HTTPException(status_code=400, detail='Webhook object does not match provider')

    recipient_id = recipient_id_from_payload(provider, payload)
    if not recipient_id:
        raise HTTPException(status_code=404, detail='Meta channel not found for payload')

    lookup_column = (
        'instagram_account_id' if provider == 'instagram_messenger' else 'page_id'
    )
    await conn.execute("select set_config('app.support_mode', 'true', true)")
    channel = await conn.fetchrow(
        f"""
        select id, tenant_id, app_secret_ref, account_mode, service_window_hours,
               page_id, instagram_account_id
        from app.tenant_channels
        where provider=$1
          and {lookup_column}=$2
          and status='active'
        """,
        provider,
        recipient_id,
    )
    if not channel:
        raise HTTPException(status_code=404, detail='Meta channel not found')

    app_secret = resolve_secret_ref(channel['app_secret_ref'])
    if not verify_messenger_signature(body, x_hub_signature_256, app_secret):
        raise HTTPException(status_code=401, detail='Invalid webhook signature')

    await conn.execute("select set_config('app.tenant_id', $1, true)", str(channel['tenant_id']))
    sha = hashlib.sha256(body).hexdigest()
    await conn.fetchrow(
        """
        insert into app.webhook_events_raw (tenant_id, provider, event_type, headers, payload, payload_sha256)
        values ($1, $2, $3, $4::jsonb, $5::jsonb, $6)
        on conflict (payload_sha256) do nothing returning *
        """,
        channel['tenant_id'],
        provider,
        payload.get('object', 'unknown'),
        json.dumps(dict(request.headers)),
        json.dumps(payload),
        sha,
    )

    events = normalize_messenger_events(provider, payload)
    # BUG-202 (codex HIGH, análogo a TASK-0081/BUG20 en WhatsApp): la firma
    # se verificó contra el channel resuelto a partir del PRIMER recipient_id
    # del payload. Cada `event.recipient_id` lleva el page_id / ig_account_id
    # destinatario; si difiere del channel resuelto, hay que dropear el evento
    # — sino un payload mixto podría firmar válido (gracias al primer
    # recipient) y bindear mensajes de OTRO tenant a este channel.
    signed_channel_recipient_id = (
        channel['instagram_account_id']
        if provider == 'instagram_messenger'
        else channel['page_id']
    )
    signed_channel_recipient_id = (
        str(signed_channel_recipient_id) if signed_channel_recipient_id else None
    )
    window_hours = int(channel['service_window_hours'] or 24)
    # AUDIT-48 (security #2, 2026-05-18): freshness gate. `event.timestamp`
    # viene normalizado a datetime UTC desde el payload de Meta. Si está
    # fuera de ventana, drop el event con audit log; seguimos procesando
    # los demás (defensa en profundidad sobre payload_sha256 unique).
    settings = get_settings()
    max_age_seconds = settings.webhook_meta_max_message_age_seconds
    now_utc = datetime.now(UTC)
    for event in events:
        if (
            signed_channel_recipient_id
            and event.recipient_id
            and str(event.recipient_id) != signed_channel_recipient_id
        ):
            await audit(
                conn,
                tenant_id=channel['tenant_id'],
                actor_type='system',
                actor_id=None,
                action='webhook.recipient_id_mismatch',
                entity_type='tenant_channel',
                entity_id=str(channel['id']),
                metadata={
                    'provider': provider,
                    'signed_recipient_id': signed_channel_recipient_id,
                    'event_recipient_id': str(event.recipient_id),
                },
            )
            continue
        if max_age_seconds > 0:
            ev_ts = event.timestamp
            if ev_ts is None:
                await audit(
                    conn,
                    tenant_id=channel['tenant_id'],
                    actor_type='system',
                    actor_id=None,
                    action='webhook.messenger_event_missing_timestamp',
                    entity_type='tenant_channel',
                    entity_id=str(channel['id']),
                    metadata={'provider': provider, 'sender_id': event.sender_id},
                )
                continue
            age_seconds = (now_utc - ev_ts).total_seconds()
            if age_seconds > max_age_seconds or age_seconds < -3600:
                await audit(
                    conn,
                    tenant_id=channel['tenant_id'],
                    actor_type='system',
                    actor_id=None,
                    action='webhook.messenger_event_stale',
                    entity_type='tenant_channel',
                    entity_id=str(channel['id']),
                    metadata={
                        'provider': provider,
                        'sender_id': event.sender_id,
                        'event_timestamp': ev_ts.isoformat(),
                        'age_seconds': int(age_seconds),
                        'max_age_seconds': max_age_seconds,
                    },
                )
                continue
        contact = await _upsert_messenger_contact(
            conn,
            tenant_id=channel['tenant_id'],
            provider=provider,
            psid=event.sender_id,
            display_name=None,
        )
        received_at = event.timestamp or datetime.now(UTC)
        window_expires = service_window_expiry(received_at, window_hours)

        conversation = await conn.fetchrow(
            """
            select *
            from app.conversations
            where tenant_id=$1
              and contact_id=$2
              and channel_id=$3
              and status not in ('resolved','closed','archived')
            order by updated_at desc
            limit 1
            """,
            channel['tenant_id'],
            contact['id'],
            channel['id'],
        )
        if conversation:
            conversation = await conn.fetchrow(
                """
                update app.conversations
                set status=case
                        when status='human_active' then 'human_active'
                        when status='waiting_agent' and handoff_required then 'waiting_agent'
                        else 'waiting_user'
                    end,
                    handoff_required=case
                        when status='human_active' then handoff_required
                        when status='waiting_agent' and handoff_required then true
                        else false
                    end,
                    service_window_expires_at=$3,
                    updated_at=now()
                where tenant_id=$1 and id=$2
                returning *
                """,
                channel['tenant_id'],
                conversation['id'],
                window_expires,
            )
        else:
            conversation = await conn.fetchrow(
                """
                insert into app.conversations (
                    tenant_id, contact_id, channel_id, status, opened_by,
                    handoff_required, service_window_expires_at
                )
                values ($1, $2, $3, 'open', 'user', false, $4)
                returning *
                """,
                channel['tenant_id'],
                contact['id'],
                channel['id'],
                window_expires,
            )

        inbound_message = await conn.fetchrow(
            """
            insert into app.messages (
              tenant_id, conversation_id, external_message_id, direction, sender_actor_type, sender_actor_id,
              body_text, message_type, media_id, mime_type, payload, status, received_at,
              reply_to_external_message_id
            )
            values ($1, $2, $3, 'inbound', 'contact', $4, $5, $6, $7, $8, $9::jsonb, 'received', $10::timestamptz, $11)
            on conflict (tenant_id, external_message_id) do nothing
            returning *
            """,
            channel['tenant_id'],
            conversation['id'],
            event.external_message_id,
            event.sender_id,
            event.body_text,
            event.message_type,
            event.media_id,
            event.mime_type,
            serialize_event_for_storage(event),
            received_at,
            event.reply_to_external_id,
        )
        if inbound_message:
            await notify_operations_change(
                conn,
                channel['tenant_id'],
                'conversation.changed',
                conversation_id=conversation['id'],
                message_id=inbound_message['id'],
            )
            record_message(
                tenant_id=channel['tenant_id'],
                direction='inbound',
                channel=provider,
                status='accepted',
            )
            try:
                await orchestrate_inbound_message(
                    conn,
                    tenant_id=channel['tenant_id'],
                    channel_id=channel['id'],
                    channel_account_mode=channel['account_mode'] or 'mock',
                    conversation=conversation,
                    contact=contact,
                    inbound_message=inbound_message,
                )
            except Exception:
                log.exception(
                    'rag_orchestrator.error',
                    tenant_id=str(channel['tenant_id']),
                    conversation_id=str(conversation['id']),
                )

    return {'accepted': True, 'payload_sha256': sha, 'provider': provider}
