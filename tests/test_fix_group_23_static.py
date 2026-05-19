"""Fix-group 23: BUG-133..BUG-137.

- BUG-133: VIGENTE. `support` estaba en los 3 role ladders
  (`_ROLE_LEVELS` en security.py + routes.py + admin/routes.py) con
  nivel 50, encima de admin/owner. Pero `support` no es un rol — es
  un MODO (`support_mode` flag/cookie scoped). Un JWT con `support`
  en `roles[]` (Auth0 misconfig) bypassaba require_min_role por
  encima de admin/owner. Fix: removerlo de los 3 ladders.
- BUG-134: VIGENTE. `consent.py::enqueue_consent_reaffirm_jobs`
  inserta en `reminder_jobs` con `target_type='contact'`, pero el
  check constraint solo permitía
  `('appointment','quote','service_request','conversation','contact_subscription')`
  → CHECK violation. Fix: agregar `'contact'` al check + migration
  idempotente para DBs existentes.
- BUG-135: VIGENTE. `digest_worker._queue_whatsapp_template` insertaba
  la fila `queued` en `app.messages` pero NO enqueueaba el evento
  `message.queued` en `domain_events`. El `event_worker` consume ese
  evento para disparar el dispatch outbound → sin él, el digest
  WhatsApp quedaba colgado en queued para siempre. Fix: `RETURNING id`
  + insert en `domain_events` con idempotency key tenant+cadence+day.
- BUG-136: VIGENTE. `receive_subscription_webhook` deduplicaba el
  log raw (`on conflict (payload_sha256) do nothing`) pero NO el
  resto del flow (update sub status, audit, reminder_jobs,
  domain_events). Webhook duplicado → audit spam + reminder dobles.
  Fix: `returning id` + short-circuit con 200 cuando el raw ya
  existía.
- BUG-137: NOT-APPLICABLE. `bot_personality` SÍ se propaga a
  `_resolve_answer` en `rag_orchestrator.py:1000` (y dentro a los
  tier-2/3 helpers). El Q&A cascade NO está hardcoded a un tone.
"""
from __future__ import annotations

from pathlib import Path
from tests._routes_aggregator import routes_aggregated_source


SECURITY = Path('app/core/security.py')
ADMIN_ROUTES = Path('app/admin/routes.py')
CONSENT = Path('app/services/consent.py')
SCHEMA = Path('infra/postgres/01-schema.sql')
MIGRATIONS = Path('infra/postgres/03-migrations.sql')
DIGEST_WORKER = Path('app/workers/digest_worker.py')
RAG_ORCHESTRATOR = Path('app/services/rag_orchestrator.py')


# ───── BUG-133 — `support` removido de los 3 ladders ─────────────────────


def test_bug_133_security_role_levels_excludes_support():
    src = SECURITY.read_text()
    idx = src.find('_ROLE_LEVELS = {')
    assert idx > 0
    end = src.find('}', idx)
    block = src[idx:end]
    assert "'support'" not in block, (
        "BUG-133: `support` no es un rol (es modo). Removerlo del ladder "
        "de `_ROLE_LEVELS` en security.py para que un JWT con 'support' "
        "en roles[] no pase require_min_role por encima de admin/owner."
    )


def test_bug_133_routes_tenant_role_levels_excludes_support():
    src = routes_aggregated_source()
    idx = src.find('_TENANT_ROLE_LEVELS = {')
    assert idx > 0
    end = src.find('}', idx)
    block = src[idx:end]
    assert "'support'" not in block, (
        "BUG-133: `support` también debe quitarse de `_TENANT_ROLE_LEVELS` "
        "en routes.py (mismo ladder paralelo)."
    )


def test_bug_133_admin_routes_role_levels_excludes_support():
    src = ADMIN_ROUTES.read_text()
    idx = src.find('_ROLE_LEVELS = {')
    assert idx > 0
    end = src.find('}', idx)
    block = src[idx:end]
    assert "'support'" not in block, (
        "BUG-133: `support` también debe quitarse de `_ROLE_LEVELS` "
        "en admin/routes.py (tercer ladder)."
    )


# ───── BUG-134 — reminder_jobs check incluye 'contact' ───────────────────


def test_bug_134_schema_reminder_jobs_allows_contact_target():
    src = SCHEMA.read_text()
    rj_idx = src.find('create table app.reminder_jobs (')
    assert rj_idx > 0
    end = src.find(');', rj_idx)
    block = src[rj_idx:end]
    assert "'contact'" in block, (
        "BUG-134: el check de `reminder_jobs.target_type` debe incluir "
        "`'contact'` para que el consent reaffirm job no viole el constraint."
    )


def test_bug_134_migration_recreates_constraint_with_contact():
    src = MIGRATIONS.read_text()
    assert 'drop constraint if exists reminder_jobs_target_type_check' in src, (
        "BUG-134: la migración debe `drop constraint if exists` antes de "
        "re-agregar (idempotente para DBs que ya tienen el constraint viejo)."
    )
    assert "add constraint reminder_jobs_target_type_check" in src, (
        "BUG-134: la migración debe re-agregar el constraint con el set ampliado."
    )
    add_idx = src.find("add constraint reminder_jobs_target_type_check")
    add_block = src[add_idx:add_idx + 500]
    assert "'contact'" in add_block, (
        "BUG-134: el nuevo constraint debe incluir `'contact'`."
    )


# ───── BUG-135 — digest worker enqueue domain event ──────────────────────


def test_bug_135_digest_worker_enqueues_message_queued_event():
    src = DIGEST_WORKER.read_text()
    # El insert en messages debe capturar el id (RETURNING).
    assert 'returning id' in src, (
        "BUG-135: el insert en `app.messages` debe usar `RETURNING id` para "
        "poder enqueue el `message.queued` event."
    )
    assert "'message.queued'" in src, (
        "BUG-135: el worker debe enqueue el evento `message.queued` en "
        "`app.domain_events`, sino el event_worker nunca dispatcha el digest."
    )
    # Idempotency key derivada de tenant + cadence + day.
    assert 'idempotency_key' in src and 'digest-' in src, (
        "BUG-135: usar `idempotency_key = f'digest-{cadence}-{tenant_id}-{YYYYMMDD}'` "
        "para que un reinicio del scheduler no enqueue duplicados."
    )


# ───── BUG-136 — subscription webhook short-circuita en duplicado ────────


def test_bug_136_subscription_webhook_short_circuits_on_duplicate():
    src = routes_aggregated_source()
    # Buscar el endpoint del webhook de subscriptions.
    ep_idx = src.find("async def receive_subscription_webhook(")
    assert ep_idx > 0
    # Buscar el siguiente def para acotar el bloque.
    next_def = src.find('\nasync def ', ep_idx + 1)
    block = src[ep_idx:next_def]
    # El insert raw debe capturar resultado con RETURNING id.
    assert 'returning id' in block, (
        "BUG-136: el insert en `webhook_events_raw` debe usar `returning id` "
        "para poder detectar el conflict (None ⇒ duplicado)."
    )
    assert 'raw_inserted is None' in block, (
        "BUG-136: cuando el insert no devuelve fila (duplicado), el endpoint "
        "debe short-circuitar sin re-procesar audit/update/reminders."
    )
    assert "'status': 'duplicate'" in block, (
        "BUG-136: la respuesta para duplicados debe declarar `status: 'duplicate'` "
        "explícitamente para que el provider sepa que el evento se reconoció."
    )


# ───── BUG-137 — NOT-APPLICABLE (bot_personality llega al cascade) ───────


def test_bug_137_resolve_answer_receives_bot_personality():
    src = RAG_ORCHESTRATOR.read_text()
    # El call site debe pasar bot_personality a _resolve_answer. AUDIT-48
    # (2026-05-18) cambió la línea a multi-línea agregando `tenant_no_train`;
    # ahora chequeamos: (1) hay un await a `_resolve_answer(body_text, ...)`
    # y (2) en su llamada aparece `bot_personality=bot_personality`.
    # Acepta tanto multi-line como single-line (`await _resolve_answer(...)` + body_text/matches/settings en cualquier formato).
    import re as _re
    call_match = _re.search(
        r'await\s+_resolve_answer\s*\(\s*\n?\s*body_text\s*,\s*matches\s*,\s*settings\s*,',
        src,
    )
    assert call_match, (
        "BUG-137: el call site `await _resolve_answer(body_text, matches, settings, ...)` "
        "debería existir en rag_orchestrator (Q&A cascade)."
    )
    call_idx = call_match.start()
    # Tomamos los siguientes 400 chars del call site (cubre args múltiples
    # líneas hasta el `)` de cierre).
    call_window = src[call_idx:call_idx + 400]
    assert 'bot_personality=bot_personality' in call_window, (
        "BUG-137: `_resolve_answer` (Q&A cascade) debe recibir `bot_personality` "
        "para que el tone configurado del tenant también aplique al cascade, "
        "no solo al conversational tier."
    )
    # La signature de _resolve_answer acepta el parámetro.
    assert 'async def _resolve_answer(' in src
    sig_idx = src.find('async def _resolve_answer(')
    sig_end = src.find(')', sig_idx)
    sig = src[sig_idx:sig_end]
    assert 'bot_personality' in sig, (
        "BUG-137: la signature de `_resolve_answer` debe aceptar `bot_personality`."
    )
