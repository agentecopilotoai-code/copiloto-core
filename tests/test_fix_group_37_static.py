"""Fix-group 37: Codex Security HIGH — webhook replay & cross-tenant routing.

Cierra 3 findings del CSV `codex-security-findings-2026-05-18`:

- **BUG-201** (HIGH, `app/services/payment_provider.py` + `app/api/v1/routes.py`):
  `verify_stripe_signature` solo enforce el tolerance window cuando el caller
  pasa `now_ts`, pero AMBOS handlers de webhooks (`/v1/webhooks/payments/{provider}`
  línea 8909 y `/v1/webhooks/subscriptions/{provider}` línea 9071) lo invocaban
  sin ese param. `verify_mercadopago_signature` directamente nunca validaba
  freshness aunque el `ts` venía en el header. Resultado: cualquier webhook
  signed payload válido capturado se podía replayear indefinidamente para
  forzar transiciones de `payment_status` o `contact_subscription.status`.
- **BUG-202** (HIGH, `app/services/meta_messenger.py` + `app/api/v1/routes.py:12598`):
  Meta Messenger / Instagram webhook itera `events = normalize_messenger_events(...)`
  pero NUNCA chequea que cada `event.recipient_id` matchee el `page_id` /
  `instagram_account_id` del channel resuelto por la firma. Análogo al
  TASK-0081/BUG20 que cerró este mismo bug en WhatsApp — un atacante que
  controle su propio channel puede craftar un payload donde el PRIMER
  recipient pertenece a él (pasa la firma) y los siguientes pertenecen a
  OTRO tenant, contaminando contacts/conversations/messages del tenant víctima.
"""
from __future__ import annotations

from pathlib import Path
from tests._routes_aggregator import routes_aggregated_source


PAYMENT_PROVIDER = Path('app/services/payment_provider.py')


# ───── BUG-201 — webhook signature freshness ─────────────────────────────


def test_bug_201_mercadopago_verifier_accepts_now_ts_and_tolerance():
    src = PAYMENT_PROVIDER.read_text()
    fn_idx = src.find('def verify_mercadopago_signature(')
    assert fn_idx > 0
    next_def = src.find('\ndef verify_stripe_signature(', fn_idx)
    block = src[fn_idx:next_def]
    assert 'tolerance_seconds: int = 300' in block, (
        'BUG-201: `verify_mercadopago_signature` debe aceptar '
        '`tolerance_seconds` con default 300 (5 min, mismo que Stripe).'
    )
    assert 'now_ts: int | None = None' in block, (
        'BUG-201: `verify_mercadopago_signature` debe aceptar `now_ts`.'
    )
    # BUG-201 + BUG-230 (fix-group-44 follow-up): el bloque ahora entra
    # SIEMPRE que `now_ts is not None` y FALLA si el header omite `ts` —
    # antes el bloque se skippeaba sin ts y caía al fallback raw payload
    # (un atacante que strippea `ts` bypaseaba el fix de replay).
    assert 'if now_ts is not None:' in block, (
        'BUG-201 + BUG-230: el bloque de freshness debe entrar cuando '
        '`now_ts is not None`, independiente de si el header trae `ts`.'
    )
    assert 'if not ts:\n            return False' in block, (
        'BUG-230: cuando el caller pasa now_ts y el header omite `ts`, '
        'fail-closed (raw payload fallback bypaseaba el replay fix).'
    )
    assert 'abs(now_ts - ts_int) > tolerance_seconds' in block, (
        'BUG-201: el check de freshness debe ser `abs(now_ts - ts) > tolerance`.'
    )


def test_bug_201_payments_route_passes_now_ts_to_verifiers():
    src = routes_aggregated_source()
    # Buscar el primer handler (payments) — incluye webhook_now_ts antes del if mercadopago.
    payments_idx = src.find("/payments/{provider}")
    assert payments_idx > 0
    block = src[payments_idx:payments_idx + 4500]
    # Debe inicializar webhook_now_ts.
    assert 'webhook_now_ts = int(datetime.now(UTC).timestamp())' in block, (
        'BUG-201: el handler de payments debe inicializar `webhook_now_ts` '
        'desde `datetime.now(UTC).timestamp()` antes de invocar verifiers.'
    )
    # Debe pasarlo a ambos verifiers.
    assert 'verify_stripe_signature(body, sig_header, secret, now_ts=webhook_now_ts)' in block, (
        'BUG-201: `verify_stripe_signature` debe ser invocado con `now_ts=webhook_now_ts`.'
    )
    # Y a mercadopago.
    assert 'verify_mercadopago_signature(' in block and 'now_ts=webhook_now_ts' in block, (
        'BUG-201: `verify_mercadopago_signature` debe ser invocado con `now_ts=webhook_now_ts`.'
    )


def test_bug_201_subscriptions_route_passes_now_ts_to_verifiers():
    src = routes_aggregated_source()
    subs_idx = src.find("/subscriptions/{provider}")
    assert subs_idx > 0
    block = src[subs_idx:subs_idx + 4500]
    assert 'webhook_now_ts = int(datetime.now(UTC).timestamp())' in block, (
        'BUG-201: el handler de subscriptions también debe inicializar '
        '`webhook_now_ts` para el freshness gate.'
    )
    assert 'verify_stripe_signature(body, sig_header, secret, now_ts=webhook_now_ts)' in block, (
        'BUG-201: `verify_stripe_signature` en subscriptions debe pasar `now_ts`.'
    )


# ───── BUG-202 — Meta Messenger per-event recipient validation ──────────


def test_bug_202_meta_messenger_drops_events_with_recipient_mismatch():
    src = routes_aggregated_source()
    # Buscar el bloque del receive_messenger_webhook handler (después del
    # comentario TASK-0081 / WhatsApp pattern).
    meta_idx = src.find('events = normalize_messenger_events(provider, payload)')
    assert meta_idx > 0
    # Tomar ~2500 chars después del marker (cubre el if + audit + continue).
    block = src[meta_idx:meta_idx + 2500]
    assert 'signed_channel_recipient_id' in block, (
        'BUG-202: el handler de Meta Messenger debe extraer '
        '`signed_channel_recipient_id` del channel resuelto (`page_id` o '
        '`instagram_account_id` según el provider).'
    )
    assert "if provider == 'instagram_messenger'" in block, (
        'BUG-202: el campo de matching depende del provider — '
        '`instagram_account_id` para Instagram, `page_id` para Messenger.'
    )
    assert 'webhook.recipient_id_mismatch' in block, (
        'BUG-202: cuando el `event.recipient_id` no matchea el del channel '
        'firmado, debe auditarse `webhook.recipient_id_mismatch` y skippear '
        'el evento con `continue` (análogo a TASK-0081/BUG20 en WhatsApp).'
    )
    assert 'continue' in block, (
        'BUG-202: el evento con recipient_id mismatch debe `continue` para '
        'que el siguiente evento siga procesándose (no rechazar el batch entero).'
    )
