"""Fix-group 38: Codex Security HIGH+MEDIUM — booking-flow integrity.

Cierra 7 findings (BUG-47 sobre LLM-driven service_requests queda para
fix-group-44, donde tratamos state-machine bugs del orchestrator):

- **BUG-203** (MEDIUM, `app/services/booking_flow.py`): `_list_active_services`
  removió el LIMIT en TASK-0054. Sin cap, un tenant con miles de servicios
  activos (o admin malicioso) podía explotar el booking flow (reachable vía
  webhook entrante sin auth) para DoS — fetch + Python eval del catalogue
  entero. Cap a 500 rows.
- **BUG-204** (MEDIUM, `app/services/booking_flow.py`): `_fetch_service` no
  re-evaluaba `applies_when` cuando el service id venía de un interactive
  reply (`book_service:<uuid>`). Cliente con id stale del listing pre-filtrado
  podía replayar la elección y bookear servicios para los que NO cumple
  los facts de qualification.
- **BUG-205** (MEDIUM, `app/services/booking_flow.py`): `_fetch_resource` no
  filtraba por `branch_id`. Cliente podía elegir branch A y después un
  resource de branch B → notificaciones con address/maps de branch B mientras
  el calendario interno apuntaba a branch A.
- **BUG-206** (MEDIUM, `app/services/booking_flow.py`): el `book_slot:<value>`
  handler pasaba `value` raw a `_create_appointment` sin verificar que era
  uno de los `proposed_slots` ofrecidos. Cliente podía bookear cualquier hora
  arbitraria (mientras no colisione — el exclusion constraint no enforce
  working hours).
- **BUG-207** (HIGH, `app/services/booking_flow.py`): el binding de
  appointment_package_links solo chequeaba `remaining_sessions > 0` pero no
  contaba pending unconsumed links. Cliente con `remaining=1` podía bookear
  N appointments back-to-back y todos quedaban linkeados al mismo package
  → fuga de revenue cuando se completaban.
- **BUG-208** (MEDIUM, `app/services/appointment_self_service.py`):
  `_execute_cancel` / `_execute_reschedule` mutaban la cita sin re-verificar
  payment_status / starts_at / status mid-flow. Cliente abría el flow cuando
  todo estaba pristine, esperaba a que pago o min-hours-window cambiaran, y
  el botón viejo seguía cancelando.
- **BUG-209** (MEDIUM, `app/services/appointment_self_service.py`):
  `start_auto_rebook_flow` no aplicaba los gates de paid/min-hours-window
  que sí aplica el entry-point regular de self-service. Cliente con
  "no"/"cambiar" en la confirmación bypaseba la política.
"""
from __future__ import annotations

from pathlib import Path


BOOKING = Path('app/services/booking_flow.py')
SELF_SERVICE = Path('app/services/appointment_self_service.py')


# ───── BUG-203 — catalog hard cap ────────────────────────────────────────


def test_bug_203_list_active_services_has_hard_cap():
    src = BOOKING.read_text()
    assert 'SERVICE_CATALOG_HARD_CAP = 500' in src, (
        'BUG-203: debe existir la constante `SERVICE_CATALOG_HARD_CAP = 500` '
        'que el SELECT del catalogue activo usa como LIMIT.'
    )
    fn_idx = src.find('async def _list_active_services(')
    assert fn_idx > 0
    next_def = src.find('\ndef _qualification_facts_from_conversation', fn_idx)
    block = src[fn_idx:next_def]
    assert 'limit $2' in block, (
        'BUG-203: el SELECT debe tener `limit $2` para bound el fetch.'
    )
    assert 'SERVICE_CATALOG_HARD_CAP' in block, (
        'BUG-203: la query debe usar la constante como parámetro del LIMIT.'
    )


# ───── BUG-204 — _fetch_service incluye applies_when + handler re-valida ─


def test_bug_204_fetch_service_returns_applies_when():
    src = BOOKING.read_text()
    fn_idx = src.find('async def _fetch_service(')
    assert fn_idx > 0
    next_def = src.find('\nasync def _list_active_resources(', fn_idx)
    block = src[fn_idx:next_def]
    assert 'preparation_notes, applies_when' in block, (
        'BUG-204: el SELECT de `_fetch_service` debe incluir `applies_when` '
        'para que el caller pueda re-evaluar elegibility cuando el service id '
        'viene de un interactive reply.'
    )


def test_bug_204_book_service_reply_revalidates_applies_when():
    src = BOOKING.read_text()
    handler_idx = src.find('if prefix == PREFIX_SERVICE and value:')
    assert handler_idx > 0
    # ~1500 chars debería cubrir la rama hasta el _present_branches/resources.
    block = src[handler_idx:handler_idx + 2000]
    assert "qualification_facts = _qualification_facts_from_conversation(conversation)" in block, (
        'BUG-204: el handler de PREFIX_SERVICE debe extraer los facts de '
        'qualification de la conversation.'
    )
    assert "not evaluate_rules(" in block and "service.get('applies_when'), qualification_facts" in block, (
        'BUG-204: el handler debe llamar `evaluate_rules(service.applies_when, '
        'qualification_facts)` y dropear el service si retorna False.'
    )


# ───── BUG-205 — _fetch_resource acepta branch_id + handler lo pasa ──────


def test_bug_205_fetch_resource_accepts_branch_id_filter():
    src = BOOKING.read_text()
    fn_idx = src.find('async def _fetch_resource(')
    assert fn_idx > 0
    next_def = src.find('\ndef _specialist_caption(', fn_idx)
    block = src[fn_idx:next_def]
    assert 'branch_id: UUID | None = None' in block, (
        'BUG-205: `_fetch_resource` debe aceptar `branch_id: UUID | None = None`.'
    )
    assert '($3::uuid is null or branch_id = $3)' in block, (
        'BUG-205: el SELECT debe filtrar por branch_id cuando viene seteado.'
    )


def test_bug_205_book_resource_handler_passes_branch_id():
    src = BOOKING.read_text()
    handler_idx = src.find('elif prefix == PREFIX_RESOURCE and value:')
    assert handler_idx > 0
    block = src[handler_idx:handler_idx + 1500]
    assert 'selected_branch_id_raw = state.get(' in block, (
        'BUG-205: el handler de PREFIX_RESOURCE debe leer `selected_branch_id` '
        'del state.'
    )
    assert 'branch_id=branch_uuid_for_check' in block, (
        'BUG-205: el call a `_fetch_resource` debe pasar `branch_id=` para '
        'forzar el filtro.'
    )


# ───── BUG-206 — book_slot valida contra proposed_slots ──────────────────


def test_bug_206_book_slot_handler_validates_against_proposed_slots():
    src = BOOKING.read_text()
    handler_idx = src.find('elif prefix == PREFIX_SLOT and value and state.get')
    assert handler_idx > 0
    block = src[handler_idx:handler_idx + 2500]
    assert "proposed_slots = state.get('proposed_slots') or []" in block, (
        'BUG-206: el handler debe extraer `proposed_slots` del state.'
    )
    assert 'if value not in proposed_starts:' in block, (
        'BUG-206: el handler debe verificar que `value` está en el set de '
        '`proposed_starts` antes de invocar `_create_appointment`.'
    )


# ───── BUG-207 — package reuse: FOR UPDATE + pending count ──────────────


def test_bug_207_create_appointment_uses_for_update_and_counts_pending():
    src = BOOKING.read_text()
    fn_idx = src.find('async def _create_appointment(')
    assert fn_idx > 0
    next_def = src.find('\ndef _resolve_date_choice(', fn_idx)
    block = src[fn_idx:next_def]
    # SELECT FOR UPDATE para lockear el package row.
    assert 'for update' in block.lower(), (
        'BUG-207: el SELECT de `contact_packages` debe ser `SELECT ... FOR UPDATE` '
        'para prevenir race en concurrent bookings.'
    )
    # Conteo de pending links.
    assert 'pending_links = await conn.fetchval(' in block, (
        'BUG-207: debe contar `appointment_package_links` cuyos appointments '
        "están en `('scheduled','confirmed')` (= pending sin completar)."
    )
    assert "a.status in ('scheduled','confirmed')" in block, (
        'BUG-207: el count de pending debe filtrar appointment.status en '
        "('scheduled','confirmed')."
    )
    # Check ANTES de bindear el link.
    assert 'pending_count + 1 <= int(package_check[' in block, (
        'BUG-207: solo bindear el package si `pending_count + 1 <= remaining_sessions`.'
    )


# ───── BUG-208 — _execute_cancel / _execute_reschedule recheck ──────────


def test_bug_208_execute_cancel_rechecks_policy():
    src = SELF_SERVICE.read_text()
    fn_idx = src.find('async def _execute_cancel(')
    assert fn_idx > 0
    next_def = src.find('\nasync def _execute_reschedule(', fn_idx)
    block = src[fn_idx:next_def]
    assert 'fresh = await _fetch_appointment(conn, tenant_id, appointment[' in block, (
        'BUG-208: `_execute_cancel` debe re-fetchear el appointment ANTES '
        'de mutar (mid-flow staleness check).'
    )
    assert "fresh.get('status') in ('cancelled', 'completed', 'no_show')" in block, (
        'BUG-208: debe rechazar si el status ya es terminal.'
    )
    assert "str(fresh.get('payment_status') or '').lower() == 'paid'" in block, (
        'BUG-208: debe rechazar si la cita ya fue pagada.'
    )
    assert 'await _too_close_to_start(conn, tenant_id, fresh)' in block, (
        'BUG-208: debe re-aplicar el min-hours-before-start gate sobre fresh.'
    )


def test_bug_208_execute_reschedule_rechecks_policy():
    src = SELF_SERVICE.read_text()
    fn_idx = src.find('async def _execute_reschedule(')
    assert fn_idx > 0
    next_def = src.find('\nasync def _record_handled(', fn_idx)
    block = src[fn_idx:next_def]
    assert 'fresh = await _fetch_appointment(conn, tenant_id, appointment[' in block, (
        'BUG-208: `_execute_reschedule` debe re-fetchear el appointment.'
    )
    assert "fresh.get('status') in ('cancelled', 'completed', 'no_show')" in block, (
        'BUG-208: status terminal rechaza el reschedule.'
    )
    assert "str(fresh.get('payment_status') or '').lower() == 'paid'" in block, (
        'BUG-208: paid rechaza el reschedule.'
    )


# ───── BUG-209 — start_auto_rebook_flow respeta gates ───────────────────


def test_bug_209_auto_rebook_blocks_paid_and_too_close():
    src = SELF_SERVICE.read_text()
    fn_idx = src.find('async def start_auto_rebook_flow(')
    assert fn_idx > 0
    # Acotamos al siguiente def.
    next_def = src.find('\nasync def ', fn_idx + 1)
    block = src[fn_idx:next_def] if next_def > 0 else src[fn_idx:fn_idx + 4000]
    assert "appointment.get('payment_status') or '').lower() == 'paid'" in block, (
        'BUG-209: `start_auto_rebook_flow` debe rechazar si '
        '`payment_status=paid` (igual que el entry-point regular).'
    )
    assert 'await _too_close_to_start(conn, tenant_id, appointment)' in block, (
        'BUG-209: `start_auto_rebook_flow` debe rechazar si '
        '`_too_close_to_start` retorna True.'
    )
    assert "'reason': 'paid_appointment_requires_human'" in block, (
        'BUG-209: el escalation reason para paid debe ser explícito.'
    )
    assert "'reason': 'too_close_to_start'" in block, (
        'BUG-209: el escalation reason para too-close debe ser explícito.'
    )
