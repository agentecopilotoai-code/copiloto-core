"""Fix-group 05: BUG-043..BUG-047.

- BUG-043: Backend computa `active_handoff_assigned_to_is_me` (boolean)
  por conversación; frontend lo usa para filtrar "Mis handoffs". Antes
  comparaba `profile.sub` (Auth0) contra `assigned_to` (UUID) — nunca
  matcheaba.
- BUG-044: `list_appointments` ahora acepta `from_date` / `to_date` y
  filtra server-side. Antes la query estaba hardcoded sin filtro de
  fecha + limit 250 → tenants con >250 citas perdían el día actual.
- BUG-045: NOT-APPLICABLE — `audit_durably` ya setea `app.tenant_id` GUC
  antes del INSERT (fix de BUG-010).
- BUG-046: NOT-APPLICABLE — `infra/observability/prometheus.yml` ya
  scrapea `event-worker:9100` y `scheduler:9100` además de `api:8000`.
- BUG-047: PENDING-INFRA — `cpi_backup_last_*` metrics no están
  registradas en `metrics.py`. Requiere wiring del backup verifier al
  registry de Prometheus (más invasivo que un fix puntual). Catalog
  marca como tal.
"""
from __future__ import annotations

import inspect
import textwrap
from pathlib import Path

from app.api.v1 import routes as routes_module


AUDIT = Path('app/services/audit.py')
PROMETHEUS = Path('infra/observability/prometheus.yml')
METRICS = Path('app/services/metrics.py')
HANDOFF_DATA = Path('admin-panel/src/features/agente/my-handoffs/myHandoffsData.js')
TODAY_HOOK = Path('admin-panel/src/features/agente/today-appointments/hooks/useTodayAppointmentsData.js')


def _source_of(name: str) -> str:
    return textwrap.dedent(inspect.getsource(getattr(routes_module, name)))


# ───── BUG-043 — handoff assigned_to_is_me ───────────────────────────────


def test_bug_043_list_conversations_computes_assigned_to_is_me():
    """Backend debe agregar `active_handoff_assigned_to_is_me` por conv."""
    source = _source_of('list_conversations')
    assert 'current_user_id_from_request' in source, (
        'BUG-043: list_conversations debe resolver el user_id actual.'
    )
    assert "'active_handoff_assigned_to_is_me'" in source, (
        'BUG-043: cada conversation debe llevar la flag '
        '`active_handoff_assigned_to_is_me`.'
    )
    assert 'str(assigned_to) == str(current_user_id)' in source, (
        'BUG-043: comparación canónica del flag.'
    )


def test_bug_043_frontend_filter_uses_is_me_boolean():
    """`filterMyHandoffs` debe consultar primero el boolean del backend."""
    src = HANDOFF_DATA.read_text()
    assert 'active_handoff_assigned_to_is_me' in src, (
        'BUG-043: el filtro frontend debe consultar el boolean nuevo en vez '
        'de comparar profile.sub vs UUID (que nunca matchea).'
    )
    assert "typeof conversation.active_handoff_assigned_to_is_me === 'boolean'" in src, (
        'BUG-043: typeof-check guarda compat con tests que no setean el flag.'
    )


# ───── BUG-044 — appointments date filter ────────────────────────────────


def test_bug_044_list_appointments_accepts_date_filters():
    source = _source_of('list_appointments')
    assert 'from_date: date | None' in source, (
        'BUG-044: list_appointments debe aceptar `from_date: date | None`.'
    )
    assert 'to_date: date | None' in source, (
        'BUG-044: list_appointments debe aceptar `to_date: date | None`.'
    )
    assert "a.starts_at >= $5::date" in source, (
        'BUG-044: el filtro `from_date` debe aplicarse a starts_at.'
    )
    assert "a.starts_at < ($6::date + interval '1 day')" in source, (
        'BUG-044: el filtro `to_date` debe ser exclusive del día siguiente '
        'para incluir todas las citas del día final.'
    )


def test_bug_044_today_appointments_passes_date_to_endpoint():
    src = TODAY_HOOK.read_text()
    assert 'listAppointments(session, tenantId, { from_date: selectedDay, to_date: selectedDay })' in src, (
        'BUG-044: useTodayAppointmentsData debe pasar `from_date`/`to_date` '
        'al endpoint para filtrar server-side (no client-side sobre 250 rows).'
    )
    assert 'selectedDay' in src, 'BUG-044: el effect debe depender de selectedDay'


# ───── BUG-045 — NOT-APPLICABLE (audit_durably setea GUC) ───────────────


def test_bug_045_audit_durably_sets_tenant_id_guc_before_insert():
    src = AUDIT.read_text()
    assert "set_config('app.tenant_id'" in src, (
        'BUG-045: `audit_durably` debe setear `app.tenant_id` GUC antes del '
        'INSERT (sino RLS rechaza para tenant_id != NULL).'
    )
    # Verificar que el `set_config` corre ANTES del insert.
    set_config_idx = src.find("set_config('app.tenant_id'")
    insert_idx = src.find('insert into app.audit_logs', set_config_idx)
    assert set_config_idx < insert_idx, (
        'BUG-045: el `set_config` debe correr ANTES del INSERT, no después.'
    )


# ───── BUG-046 — NOT-APPLICABLE (prometheus.yml ya scrapea workers) ─────


def test_bug_046_prometheus_scrapes_workers_separately():
    src = PROMETHEUS.read_text()
    assert "'event-worker:9100'" in src, (
        'BUG-046: prometheus.yml debe scrappear `event-worker:9100` además '
        'de `api:8000` — sino las métricas del worker no se reportan.'
    )
    assert "'scheduler:9100'" in src, (
        'BUG-046: prometheus.yml debe scrappear `scheduler:9100` también.'
    )


# ───── BUG-047 — PENDING-INFRA (backup metrics no registradas) ──────────


def test_bug_047_backup_metric_gauges_are_documented_as_pending():
    """Las alertas en `alerts.yaml` referencian `cpi_backup_last_*` pero
    `metrics.py` no las registra. Este test SOLO verifica que el catálogo
    refleja el estado real para que `fix-group-XX` futuro las agregue
    cuando el backup verifier se instrumente con Prometheus.
    """
    metrics_src = METRICS.read_text()
    # No queremos forzar la implementación todavía. Solo dejar evidencia.
    assert 'cpi_backup_last_success_age_seconds' not in metrics_src, (
        'BUG-047: si agregás `cpi_backup_last_success_age_seconds` al '
        'metrics registry, actualizá este test y el catálogo (BUG-047 → DONE).'
    )
