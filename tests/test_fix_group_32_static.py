"""Fix-group 32: BUG-180..BUG-184 — 5 P2 de Codex Review.

- BUG-180 (P2 sobre BUG-044): `list_appointments` filtraba `starts_at`
  contra `from_date::date` en TZ de SESIÓN (UTC). Para tenants en
  `America/Bogota` (UTC-5), citas locales nocturnas se almacenan al día
  siguiente UTC → excluidas de `from=hoy&to=hoy`. Fix: comparar
  `(a.starts_at AT TIME ZONE t.timezone)::date`.
- BUG-181 (P2 sobre BUG-112): la query `mrr_by_plan` bucketeaba por
  `sp.currency` (current price) en vez de
  `coalesce(cs.price_locked_currency, sp.currency)`. Cambiar el currency
  del plan reasignaba el revenue locked (COP) al nuevo currency (USD)
  en el reporte. Las otras queries (tenant/country/failed) ya usaban
  el coalesce; alineamos.
- BUG-182 (P2 sobre BUG-119): `redact_incident_payload` leía
  `value.get('emails')` y `value.get('whatsapps')` (plural), pero
  `normalize_alert_channels` guarda las arrays bajo las keys SINGULAR
  `email`/`whatsapp`. El feed siempre reportaba `email_count: 0` y
  `whatsapp_count: 0` aunque se hubieran notificado operadores. Fix:
  leer la singular primero (la real), plural como fallback defensivo.
- BUG-183 (P2 sobre BUG-135): mismo defecto que BUG-179 corrigió en
  `operator_alerts.py` — el payload del digest WhatsApp no llevaba el
  bloque `template` pre-formateado. `event_worker` pasaba `None` a
  `build_whatsapp_message_payload` → ValueError → digest `failed`. Fix:
  pre-construir con `build_template_message_payload`.
- BUG-184 (P2 sobre BUG-135): idempotency key
  `digest-{cadence}-{tenant}-{YYYYMMDD}` era idéntica para todos los
  recipients del mismo tenant en el mismo día. `app.domain_events`
  tiene `UNIQUE (tenant_id, idempotency_key)`, así que el segundo
  recipient insertaba `app.messages` pero su `message.queued` event
  colisionaba con `ON CONFLICT DO NOTHING` → manager #2/#3/... nunca
  recibían el digest. Fix: incluir `_wa_id_from_phone(recipient)` en
  la key.
"""
from __future__ import annotations

from pathlib import Path
from tests._routes_aggregator import routes_aggregated_source


PLATFORM_INCIDENTS = Path('app/services/platform_incidents.py')
DIGEST_WORKER = Path('app/workers/digest_worker.py')


# ───── BUG-180 — appointments date filter en tenant local tz ─────────────


def test_bug_180_list_appointments_filters_in_tenant_local_timezone():
    src = routes_aggregated_source()
    fn_idx = src.find('async def list_appointments(')
    assert fn_idx > 0
    next_def = src.find('\n@tenant_ops_router.post(\'/appointments\'', fn_idx)
    block = src[fn_idx:next_def]
    # Debe JOINear app.tenants para acceder a t.timezone.
    assert 'join app.tenants t on t.id=a.tenant_id' in block, (
        'BUG-180: la query debe joinear `app.tenants t` para acceder a '
        '`t.timezone` y filtrar en TZ local del tenant.'
    )
    # Filtro: (starts_at AT TIME ZONE t.timezone)::date
    assert '(a.starts_at at time zone t.timezone)::date >= $5::date' in block, (
        'BUG-180: el filtro `from_date` debe comparar contra '
        '`(a.starts_at AT TIME ZONE t.timezone)::date`, no contra `starts_at` '
        'directo (que evalúa en TZ de sesión = UTC).'
    )
    assert '(a.starts_at at time zone t.timezone)::date <= $6::date' in block, (
        'BUG-180: el filtro `to_date` debe usar el mismo cast a TZ local '
        'del tenant para ser simétrico con `from_date`.'
    )


# ───── BUG-181 — MRR plan buckets usan locked currency ───────────────────


def test_bug_181_mrr_plan_buckets_use_locked_currency():
    src = routes_aggregated_source()
    # Encontrar la query plan_rows (entre el comment de BUG-181 y el siguiente CTE).
    bug181_idx = src.find('BUG-181 (codex P2 sobre BUG-112):')
    assert bug181_idx > 0
    plan_idx = src.find('plan_rows = await conn.fetch(', bug181_idx)
    next_query = src.find('country_rows = await conn.fetch(', plan_idx)
    block = src[plan_idx:next_query]
    # Column currency = coalesce
    assert 'coalesce(cs.price_locked_currency, sp.currency) as currency' in block, (
        "BUG-181: `mrr_by_plan` debe seleccionar "
        "`coalesce(cs.price_locked_currency, sp.currency) as currency` "
        "(no `sp.currency`) para que coincida con el currency del "
        "`price_locked_amount` que se está sumando."
    )
    # GROUP BY también incluye el coalesce.
    assert 'coalesce(cs.price_locked_currency, sp.currency)' in block.split('group by')[1], (
        'BUG-181: el `GROUP BY` debe bucketear por el mismo '
        '`coalesce(cs.price_locked_currency, sp.currency)`, sino '
        'rows con currency diferente se mezclan.'
    )


# ───── BUG-182 — incidents redact lee singular email/whatsapp ────────────


def test_bug_182_incidents_redact_reads_singular_channel_keys():
    src = PLATFORM_INCIDENTS.read_text()
    # Debe leer `value.get('email')` PRIMERO (la real), plural como fallback.
    assert "value.get('email') or value.get('emails')" in src, (
        "BUG-182: el redactor debe leer la key SINGULAR `email` primero "
        "(es la que `normalize_alert_channels` guarda), con plural como "
        "fallback defensivo. Sin esto, `email_count` siempre = 0."
    )
    assert "value.get('whatsapp') or value.get('whatsapps')" in src, (
        "BUG-182: idem para `whatsapp` singular primero."
    )


# ───── BUG-183 — digest_worker pre-builds template block ─────────────────


def test_bug_183_digest_worker_imports_template_builder():
    src = DIGEST_WORKER.read_text()
    assert 'from app.services.whatsapp import build_template_message_payload' in src, (
        "BUG-183: `digest_worker` debe importar "
        "`build_template_message_payload` para pre-formatear el bloque "
        "template que el event_worker pasará a Meta."
    )


def test_bug_183_digest_worker_payload_includes_template_block():
    src = DIGEST_WORKER.read_text()
    fn_idx = src.find('async def _queue_whatsapp_template(')
    assert fn_idx > 0
    next_def = src.find('\n\nasync def ', fn_idx)
    block = src[fn_idx:next_def] if next_def > 0 else src[fn_idx:]
    # Pre-build del bloque antes del insert.
    assert 'template_block = build_template_message_payload(' in block, (
        "BUG-183: el helper debe construir `template_block` antes del "
        "insert en `app.messages`."
    )
    # El payload incluye la key 'template'.
    assert "'template': template_block" in block, (
        "BUG-183: el `app.messages.payload` debe incluir "
        "`'template': template_block` para que el event_worker pase el "
        "bloque pre-formateado a `send_whatsapp_message`."
    )


# ───── BUG-184 — idempotency key incluye recipient ───────────────────────


def test_bug_184_digest_idempotency_key_includes_recipient_wa_id():
    src = DIGEST_WORKER.read_text()
    fn_idx = src.find('async def _queue_whatsapp_template(')
    assert fn_idx > 0
    next_def = src.find('\n\nasync def ', fn_idx)
    block = src[fn_idx:next_def] if next_def > 0 else src[fn_idx:]
    # La key debe incluir _wa_id_from_phone(recipient).
    assert '_wa_id_from_phone(recipient)' in block, (
        "BUG-184: la idempotency key debe incluir "
        "`_wa_id_from_phone(recipient)` para que cada destinatario tenga "
        "un evento distinto. Sin esto, manager #2/#3/... colisionan con "
        "`UNIQUE (tenant_id, idempotency_key)` y nunca reciben el digest."
    )
    # El formato concreto: digest-{cadence}-{tenant_id}-{wa_id}-{YYYYMMDD}
    assert "f'digest-{cadence}-{tenant_id}-{_wa_id_from_phone(recipient)}-'" in src, (
        "BUG-184: la key debe seguir el shape "
        "`digest-{cadence}-{tenant_id}-{wa_id}-{YYYYMMDD}` para que sea "
        "estable y única por recipient/día."
    )
