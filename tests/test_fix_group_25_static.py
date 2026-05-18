"""Fix-group 25: BUG-143..BUG-147 — all NOT-APPLICABLE (regression defense).

Todos arreglados en follow-ups que no marcaron el hilo de review. Test
defiende el statu-quo verificado contra el código actual.

- BUG-143: `build_daily_digest` filtra appointments_tomorrow con
  `statuses=('scheduled', 'confirmed')` — alineado con el check del
  schema (`scheduled|confirmed|completed|cancelled|no_show`). No usa
  los obsoletos `pending`/`rescheduled`.
- BUG-144: `build_weekly_digest` por default reporta la semana
  COMPLETADA (Lun..Dom de hace 7 días), no la que recién empieza.
  `current_monday - timedelta(days=7)`.
- BUG-145: el runbook `consent-violation-claim.md` usa los nombres
  correctos del schema (`event`, `evidence_payload`, `channel='admin'`).
- BUG-146: el runbook `rate-limit-meta-hit.md` usa `m.error_code`
  (columna real), no `m.metadata`.
- BUG-147: el runbook `worker-queue-backlog.md` usa `app.reminder_jobs`
  y `app.campaigns` (tablas reales), nunca el inexistente
  `app.scheduled_jobs`.
"""
from __future__ import annotations

from pathlib import Path


DIGEST = Path('app/services/digest.py')
SCHEMA = Path('infra/postgres/01-schema.sql')
RB_CONSENT = Path('docs/runbooks/consent-violation-claim.md')
RB_RATE_LIMIT = Path('docs/runbooks/rate-limit-meta-hit.md')
RB_QUEUE = Path('docs/runbooks/worker-queue-backlog.md')


# ───── BUG-143 — digest filtra appointments con statuses válidas ─────────


def test_bug_143_digest_uses_real_appointment_statuses_for_tomorrow():
    src = DIGEST.read_text()
    # El call a _appointments_for_day(tomorrow) debe usar el subset válido.
    assert "statuses=('scheduled', 'confirmed')" in src, (
        "BUG-143: el filtro de citas de mañana debe usar `('scheduled', "
        "'confirmed')` — el schema permite `scheduled|confirmed|completed|"
        "cancelled|no_show` y los recién creados están en `scheduled` (no "
        "`pending` ni `rescheduled`, que no existen en el enum)."
    )


def test_bug_143_appointment_status_check_matches_filter():
    """Defensa cruzada: el schema check de `appointments.status` debe contener
    los valores que el filtro del digest usa.
    """
    src = SCHEMA.read_text()
    appt_idx = src.find('create table app.appointments (')
    assert appt_idx > 0
    end = src.find(');', appt_idx)
    block = src[appt_idx:end]
    # Acotar a la línea del check del enum `status`.
    status_line_start = block.find("status text not null default 'scheduled'")
    assert status_line_start > 0
    status_line_end = block.find('\n', status_line_start)
    status_line = block[status_line_start:status_line_end]
    for status in ('scheduled', 'confirmed', 'completed', 'cancelled', 'no_show'):
        assert f"'{status}'" in status_line, (
            f"BUG-143 cruzada: `appointments.status` debe permitir `'{status}'`."
        )
    # No debe permitir los valores obsoletos en EL ENUM DE STATUS (otras
    # columnas como `confirmation_status` o `payment_status` sí tienen
    # `pending` legítimamente — solo nos importa el enum `status`).
    for old in ('rescheduled',):
        assert f"'{old}'" not in status_line, (
            f"BUG-143: `'{old}'` no debe estar en el enum de `appointments.status`."
        )


# ───── BUG-144 — weekly digest reporta semana COMPLETADA por default ─────


def test_bug_144_weekly_digest_defaults_to_previous_monday():
    src = DIGEST.read_text()
    fn_idx = src.find('async def build_weekly_digest(')
    assert fn_idx > 0
    next_def = src.find('\n\nasync def ', fn_idx)
    block = src[fn_idx:next_def]
    # Default: monday_local = current_monday - 7 días.
    assert 'current_monday - timedelta(days=7)' in block, (
        "BUG-144: el digest semanal por default debe reportar la semana "
        "COMPLETADA (Lun..Dom de hace 7 días), no la que recién empieza. "
        "Usar `current_monday - timedelta(days=7)`."
    )


# ───── BUG-145 — runbook consent usa columnas correctas ──────────────────


def test_bug_145_consent_runbook_uses_schema_column_names():
    """Aislar la inspección al INSERT INTO `app.consent_ledger` para no chocar
    con el SELECT de `audit_logs` que sí usa la columna `action` legítimamente
    en otra sección del runbook.
    """
    src = RB_CONSENT.read_text()
    insert_idx = src.find('INSERT INTO app.consent_ledger')
    assert insert_idx > 0, 'BUG-145: el runbook debe demostrar el INSERT en consent_ledger.'
    insert_end = src.find('COMMIT', insert_idx)
    block = src[insert_idx:insert_end]
    # Columnas reales: event, evidence_payload, channel='admin'.
    assert 'event' in block, (
        "BUG-145: el INSERT debe usar la columna `event` (no `action`)."
    )
    assert 'evidence_payload' in block, (
        "BUG-145: el INSERT debe usar `evidence_payload` (no `evidence`)."
    )
    assert "'admin'" in block, (
        "BUG-145: `channel` debe ser `'admin'` (no `'manual'`)."
    )
    # Los nombres obsoletos no deben aparecer dentro del INSERT.
    assert "'manual'" not in block, (
        "BUG-145: `'manual'` no es un valor válido del enum `channel`."
    )


# ───── BUG-146 — runbook rate-limit usa error_code ───────────────────────


def test_bug_146_rate_limit_runbook_uses_error_code_column():
    src = RB_RATE_LIMIT.read_text()
    assert 'm.error_code' in src, (
        "BUG-146: el runbook debe consultar `m.error_code` (columna real de "
        "`app.messages`), no `m.metadata`."
    )
    # No debe haber refs a m.metadata para errores.
    assert 'm.metadata' not in src, (
        "BUG-146: `m.metadata` no existe en `app.messages`; las columnas reales "
        "son `error_code`/`error_message`/`payload`."
    )


# ───── BUG-147 — runbook worker queue usa tablas reales ──────────────────


def test_bug_147_worker_queue_runbook_uses_real_tables():
    src = RB_QUEUE.read_text()
    assert 'app.reminder_jobs' in src, (
        "BUG-147: el runbook debe referenciar `app.reminder_jobs` (tabla real)."
    )
    assert 'app.campaigns' in src, (
        "BUG-147: el runbook debe referenciar `app.campaigns` (tabla real)."
    )
    assert 'scheduled_jobs' not in src, (
        "BUG-147: `app.scheduled_jobs` no existe — el runbook no debe "
        "referenciarla."
    )
