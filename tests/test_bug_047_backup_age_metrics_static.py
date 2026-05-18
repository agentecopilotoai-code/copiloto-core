"""BUG-047: alertas `cpi_backup_last_*` nunca registradas → expression
vacía → backups stale nunca paginan.

`infra/observability/alerts.yaml` declara dos reglas:
- `BackupCloudStale`: `max(cpi_backup_last_success_age_seconds{kind="cloud_dump"}) > 108000`
- `BackupVerifyFailed`: `max(cpi_backup_last_verify_failed_age_seconds) < 86400`

Pero `app/services/metrics.py` no exportaba esas series. Fix: 2 gauges
en `metrics.py` + `refresh_backup_age_metrics(conn)` helper que el
endpoint `/metrics` invoca antes de `render_latest()` para recalcular
desde `app.backup_runs` en cada scrape.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


METRICS = Path('app/services/metrics.py')
MAIN = Path('app/main.py')
ALERTS = Path('infra/observability/alerts.yaml')


def test_bug_047_metrics_module_exports_backup_age_gauges():
    src = METRICS.read_text()
    assert "backup_last_success_age_seconds = Gauge(" in src, (
        "BUG-047: el gauge `backup_last_success_age_seconds` debe existir "
        "como Gauge labelnames=('kind',) en metrics.py."
    )
    assert "'cpi_backup_last_success_age_seconds'" in src, (
        "BUG-047: el nombre exportado a Prometheus debe ser "
        "`cpi_backup_last_success_age_seconds` (mismo que usa "
        "`BackupCloudStale.expr`)."
    )
    assert "backup_last_verify_failed_age_seconds = Gauge(" in src, (
        "BUG-047: el gauge `backup_last_verify_failed_age_seconds` debe existir."
    )
    assert "'cpi_backup_last_verify_failed_age_seconds'" in src, (
        "BUG-047: el nombre exportado debe ser "
        "`cpi_backup_last_verify_failed_age_seconds` (mismo que usa "
        "`BackupVerifyFailed.expr`)."
    )


def test_bug_047_refresh_helper_exists_and_queries_backup_runs():
    src = METRICS.read_text()
    fn_idx = src.find('async def refresh_backup_age_metrics(')
    assert fn_idx > 0, (
        "BUG-047: debe existir `async def refresh_backup_age_metrics(conn)` "
        "para alimentar los gauges desde `app.backup_runs` en cada scrape."
    )
    # Bound the block at the next top-level def/async def, NOT the next
    # double newline (which lands inside the docstring).
    next_topdef = src.find('\nasync def ', fn_idx + 1)
    if next_topdef < 0:
        next_topdef = src.find('\ndef ', fn_idx + 1)
    block = src[fn_idx:next_topdef] if next_topdef > 0 else src[fn_idx:]
    # Query del cloud_dump exitoso.
    assert 'from app.backup_runs' in block, (
        "BUG-047: el helper debe leer `app.backup_runs`."
    )
    assert "status = 'ok'" in block, (
        "BUG-047: el helper debe filtrar por `status='ok'` para la edad "
        "del último éxito."
    )
    assert "status = 'failed'" in block, (
        "BUG-047: el helper debe filtrar por `status='failed'` para la edad "
        "del último verify fallido."
    )
    assert "kind = 'cloud_verify'" in block, (
        "BUG-047: el verify_failed_age debe restringirse a `kind='cloud_verify'` "
        "para no contar también dumps fallidos (que tienen su propia métrica)."
    )


def test_bug_047_main_calls_refresh_before_render():
    src = MAIN.read_text()
    assert 'refresh_backup_age_metrics' in src, (
        "BUG-047: `app/main.py` debe importar `refresh_backup_age_metrics`."
    )
    # Y debe invocarlo dentro del handler /metrics antes de render_latest.
    metrics_idx = src.find("@api.get('/metrics'")
    assert metrics_idx > 0
    next_route = src.find('\n    @api.', metrics_idx + 10)
    block = src[metrics_idx:next_route]
    refresh_pos = block.find('refresh_backup_age_metrics(conn)')
    render_pos = block.find('render_latest()')
    assert refresh_pos > 0 and render_pos > 0, (
        "BUG-047: el handler /metrics debe llamar `refresh_backup_age_metrics` "
        "y luego `render_latest`."
    )
    assert refresh_pos < render_pos, (
        "BUG-047: `refresh_backup_age_metrics` debe correr ANTES de "
        "`render_latest()` — sino los valores actualizados no quedan en el snapshot."
    )


def test_bug_047_metric_names_match_alert_expressions():
    """Defensa cruzada: si alguien renombra un gauge o cambia la expression
    del alert, ambos lados deben moverse juntos.
    """
    metrics_src = METRICS.read_text()
    alerts_src = ALERTS.read_text()
    for metric_name in (
        'cpi_backup_last_success_age_seconds',
        'cpi_backup_last_verify_failed_age_seconds',
    ):
        assert metric_name in metrics_src, (
            f"BUG-047: `{metric_name}` debe estar exportado en metrics.py."
        )
        assert metric_name in alerts_src, (
            f"BUG-047: `{metric_name}` debe seguir referenciado por la "
            "regla de alertas en alerts.yaml."
        )


def test_bug_047_refresh_is_resilient_to_db_errors():
    """Smoke: el helper no debe propagar la excepción si la query falla
    (escenario: pool no inicializada, DB caída). El endpoint /metrics
    seguiría sirviendo el snapshot en memoria sin crashear.
    """
    try:
        from app.services import metrics as metrics_mod
    except ModuleNotFoundError as exc:
        # Env local sin `prometheus_client` instalado — CI sí lo tiene.
        pytest.skip(f'prometheus_client not installed: {exc}')

    class _ErrorConn:
        async def fetch(self, *_args, **_kwargs):
            raise RuntimeError('db_down_for_test')

        async def fetchval(self, *_args, **_kwargs):
            raise RuntimeError('db_down_for_test')

    # No debe raise — best-effort por design.
    asyncio.run(metrics_mod.refresh_backup_age_metrics(_ErrorConn()))
