"""Fix-group 28: BUG-158..BUG-162.

- BUG-158: VIGENTE. Cuando `policy_engine` retornaba
  `reason='intent_complaint_or_risk'`, `_do_handoff` corría pero
  NINGÚN call enqueueaba el `ALERT_KIND_COMPLAINT` definido en
  `operator_alerts`. La constante quedaba muerta y los managers
  no recibían notificación cuando un cliente reportaba queja/riesgo.
  Fix: en `rag_orchestrator`, antes del `_do_handoff` cuando
  `reason == 'intent_complaint_or_risk'`, llamar
  `enqueue_operator_alert(kind=ALERT_KIND_COMPLAINT, payload={...})`
  con best-effort (try/except). El handoff corre aunque el alert falle.
- BUG-159: VIGENTE. `process_pending_operator_alerts` reagendaba la
  fila entera cuando cualquier canal fallaba (`if trace['errors']:
  reschedule`). Si email OK + webhook 500, el email se reenviaba en
  cada attempt hasta que el webhook cierre OK. Fix: nueva columna
  `operator_alerts.delivered_channels text[]` + dispatcher skipea
  canales ya entregados + UPDATEs persisten los nuevos delivered.
- BUG-160: VIGENTE. `_persist_state` en appointment_self_service
  hardcodeaba `status='waiting_user'`, incluso cuando la conversación
  ya estaba en `waiting_agent`/`human_active` por un handoff abierto.
  El comment del call site del auto-rebook ya avisaba, pero solo
  evitaba EL llamado, no fixea el helper. Fix: agregar `case when`
  que preserve `waiting_agent`/`human_active`/`human_required`.
- BUG-161: VIGENTE. `widget.js::readReferrerContactId` aceptaba
  cualquier string en `?ref=` o `data-ref`. El backend validaba
  forma UUID antes de linkear, pero el client mandaba junk al body
  igual (consumiendo slots de rate-limit). Fix: regex UUID v1-v5
  client-side; si no matchea, retornar undefined.
- BUG-162: NOT-APPLICABLE. `_equal` en `segments.py` ya documenta
  explícitamente que evita el patrón `bool(ca)==bool(cb)` (líneas
  608-611). Solo compara como booleans cuando AMBOS lados
  normalizaron a bool — un string libre como 'consultation' NO
  matchea un `eq true`.
"""
from __future__ import annotations

from pathlib import Path


RAG_ORCHESTRATOR = Path('app/services/rag_orchestrator.py')
OPERATOR_ALERTS = Path('app/services/operator_alerts.py')
APPT_SELF_SERVICE = Path('app/services/appointment_self_service.py')
WIDGET = Path('admin-panel/public/widget.js')
SEGMENTS = Path('app/services/segments.py')
SCHEMA = Path('infra/postgres/01-schema.sql')
MIGRATIONS = Path('infra/postgres/03-migrations.sql')


# ───── BUG-158 — complaint alert enqueueado en handoff por queja ─────────


def test_bug_158_rag_orchestrator_imports_complaint_alert_helpers():
    src = RAG_ORCHESTRATOR.read_text()
    assert 'from app.services.operator_alerts import ALERT_KIND_COMPLAINT, enqueue_operator_alert' in src, (
        "BUG-158: el orquestador debe importar `ALERT_KIND_COMPLAINT` y "
        "`enqueue_operator_alert` para poder notificar al operador cuando el "
        "policy engine escala por queja."
    )


def test_bug_158_orchestrator_enqueues_complaint_alert_before_handoff():
    src = RAG_ORCHESTRATOR.read_text()
    # El bloque debe disparar enqueue antes de _do_handoff cuando reason
    # == 'intent_complaint_or_risk'.
    handoff_idx = src.find("if policy_result.action == 'require_handoff':")
    assert handoff_idx > 0
    next_def = src.find('\n    # Idempotency check', handoff_idx)
    block = src[handoff_idx:next_def]
    assert "policy_result.reason == 'intent_complaint_or_risk'" in block, (
        "BUG-158: el orquestador debe testear `reason == 'intent_complaint_or_risk'` "
        "para decidir si enqueuear el alert."
    )
    assert 'enqueue_operator_alert(' in block and 'kind=ALERT_KIND_COMPLAINT' in block, (
        "BUG-158: cuando reason es complaint/risk, debe llamarse "
        "`enqueue_operator_alert(..., kind=ALERT_KIND_COMPLAINT, payload={...})`."
    )
    # Best-effort: try/except para que el alert no tumbe el handoff.
    assert 'except Exception' in block, (
        "BUG-158: el call de enqueue debe ser best-effort (try/except). El "
        "handoff humano es la garantía primaria; el alert es notificación adicional."
    )


# ───── BUG-159 — delivered_channels tracking en operator_alerts ──────────


def test_bug_159_schema_has_delivered_channels_array():
    src = SCHEMA.read_text()
    oa_idx = src.find('create table app.operator_alerts (')
    assert oa_idx > 0
    end = src.find(');', oa_idx)
    block = src[oa_idx:end]
    assert "delivered_channels text[] not null default '{}'" in block, (
        "BUG-159: `operator_alerts.delivered_channels text[]` debe existir "
        "para rastrear qué canales ya cerraron OK y skipear en retry."
    )


def test_bug_159_migration_adds_delivered_channels_idempotently():
    src = MIGRATIONS.read_text()
    assert 'add column if not exists delivered_channels text[]' in src, (
        "BUG-159: migración idempotente de `delivered_channels` debe estar "
        "en `03-migrations.sql` para DBs existentes."
    )


def test_bug_159_dispatcher_skips_already_delivered_channels():
    src = OPERATOR_ALERTS.read_text()
    dispatch_idx = src.find('async def dispatch_operator_alert(')
    assert dispatch_idx > 0
    next_def = src.find('\n\ndef next_retry_at(', dispatch_idx)
    block = src[dispatch_idx:next_def]
    assert "already_delivered = set(alert_row['delivered_channels']" in block, (
        "BUG-159: el dispatcher debe leer `alert_row['delivered_channels']` "
        "para skipear canales ya entregados."
    )
    # Las 3 ramas (email, whatsapp, webhook) deben condicionalizar el send.
    for ch in ('email', 'whatsapp', 'webhook'):
        guard = f"'{ch}' not in already_delivered"
        assert guard in block, (
            f"BUG-159: la rama del canal `{ch}` debe condicionalizar el send con "
            f"`{guard}` para no re-disparar canales ya OK."
        )
    # El trace debe acumular newly_delivered para que el UPDATE lo persista.
    assert "trace['newly_delivered']" in block or 'newly_delivered' in block, (
        "BUG-159: el dispatcher debe acumular `newly_delivered` para que el "
        "UPDATE de process_pending lo merge a `delivered_channels`."
    )


def test_bug_159_process_pending_persists_delivered_channels():
    src = OPERATOR_ALERTS.read_text()
    # Los UPDATEs de sent/failed/retry deben todos merge delivered_channels.
    assert 'delivered_channels = (' in src and 'array_agg(distinct c)' in src, (
        "BUG-159: los UPDATEs de status (sent/failed/retry) deben todos "
        "hacer merge a `delivered_channels` para que el state se acumule "
        "entre attempts."
    )


# ───── BUG-160 — _persist_state preserva waiting_agent ────────────────────


def test_bug_160_persist_state_preserves_waiting_agent_status():
    src = APPT_SELF_SERVICE.read_text()
    fn_idx = src.find('async def _persist_state(')
    assert fn_idx > 0
    next_def = src.find('\nasync def _queue_text_message(', fn_idx)
    block = src[fn_idx:next_def]
    # El SQL debe usar case-when para preservar waiting_agent/human_active.
    assert 'case' in block.lower() and 'waiting_agent' in block and 'human_active' in block, (
        "BUG-160: `_persist_state` debe usar `case when status in ('waiting_agent', "
        "'human_active', ...) then status else 'waiting_user' end` para no "
        "clobberar un handoff abierto al volver al usuario."
    )


# ───── BUG-161 — widget valida UUID antes de mandar ref ──────────────────


def test_bug_161_widget_validates_uuid_shape_before_returning_ref():
    src = WIDGET.read_text()
    assert 'UUID_RE' in src or 'UUID_RE = ' in src, (
        "BUG-161: el widget debe declarar un regex UUID (`UUID_RE`) para validar "
        "el `?ref=` y `data-ref` antes de enviarlo al backend."
    )
    # Patrón estándar UUID v1-v5.
    assert '[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}' in src, (
        "BUG-161: el regex debe ser UUID v1-v5 estándar (con version + variant)."
    )
    # readReferrerContactId debe retornar undefined si no matchea.
    fn_idx = src.find('function readReferrerContactId()')
    assert fn_idx > 0
    next_fn = src.find('\n  function ', fn_idx + 1)
    block = src[fn_idx:next_fn]
    assert 'UUID_RE.test(' in block, (
        "BUG-161: la función debe llamar `UUID_RE.test(candidate)` antes de "
        "devolver el valor; sino retornar undefined."
    )


# ───── BUG-162 — NOT-APPLICABLE (segments._equal evita bool(any-string)) ─


def test_bug_162_segments_equal_avoids_bool_coercion_of_strings():
    src = SEGMENTS.read_text()
    fn_idx = src.find('def _equal(')
    assert fn_idx > 0
    next_def = src.find('\n\ndef _evaluate_predicate(', fn_idx)
    block = src[fn_idx:next_def]
    # La defensa específica: solo compara como bool si AMBOS sides son bool.
    assert 'if isinstance(ca, bool) and isinstance(cb, bool):' in block, (
        "BUG-162: `_equal` debe comparar como booleans SOLO cuando ambos "
        "lados son bool. Sin esto, `eq true` matchearía cualquier string "
        "no-vacío (`bool('consultation') == True`)."
    )
    # Y debe fallar (False) cuando solo UN lado es bool — sino string vs bool
    # podrían cross-match.
    assert 'if isinstance(ca, bool) or isinstance(cb, bool):' in block, (
        "BUG-162: si solo UN lado normaliza a bool, deben NO ser iguales "
        "(retornar False antes del fallback string-compare)."
    )
