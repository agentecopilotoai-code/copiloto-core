"""TASK-0072: load suite (Locust) — static guarantees.

The Locust scenario lives at ``tests/load/test_journey_load.py`` and is run
by the ``load-test`` GitHub Actions job, not by the default pytest CI.
These static tests guarantee that the scenario, the aggregator and the CI
job stay aligned with the SLA contract documented in ``docs/sla.md``.
"""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
LOCUSTFILE = REPO_ROOT / 'tests' / 'load' / 'test_journey_load.py'
SEED = REPO_ROOT / 'tests' / 'load' / 'seed_load_tenant.py'
AGGREGATE = REPO_ROOT / 'tests' / 'load' / 'aggregate_results.py'
SLA_DOC = REPO_ROOT / 'docs' / 'sla.md'
WORKFLOW = REPO_ROOT / '.github' / 'workflows' / 'load-test.yml'
PYPROJECT = REPO_ROOT / 'pyproject.toml'
CONFTEST = REPO_ROOT / 'tests' / 'conftest.py'


# 1 ── Files exist
def test_load_suite_files_exist():
    for path in (LOCUSTFILE, SEED, AGGREGATE, SLA_DOC, WORKFLOW):
        assert path.is_file(), f'expected {path} to exist'


# 2 ── Locustfile declares the mixed 7/2/1 weight profile
def test_locustfile_declares_mixed_traffic_weights():
    src = LOCUSTFILE.read_text(encoding='utf-8')
    assert '@task(7)' in src, '70% inbound must be weighted as @task(7)'
    assert '@task(2)' in src, '20% panel must be weighted as @task(2)'
    assert '@task(1)' in src, '10% admin must be weighted as @task(1)'
    # The three named endpoints should be present.
    assert "POST /v1/webhooks/whatsapp" in src
    assert "GET /v1/health" in src
    assert "GET /v1/tenants/[tid]/services" in src


# 3 ── Locustfile signs the webhook with HMAC SHA256
def test_locustfile_signs_inbound_with_hmac():
    src = LOCUSTFILE.read_text(encoding='utf-8')
    assert 'hmac.new' in src
    assert "'X-Hub-Signature-256'" in src
    assert 'hashlib.sha256' in src


# 4 ── Locustfile fails on SLA breach in the quitting hook
def test_locustfile_enforces_p95_target_at_quit():
    src = LOCUSTFILE.read_text(encoding='utf-8')
    assert 'LOAD_TEST_P95_MS' in src
    assert "'2000'" in src, 'default p95 target must be 2000 ms per SLA'
    assert 'process_exit_code = 1' in src


# 5 ── Seed script writes the load test secrets to .secrets/
def test_seed_writes_secrets_files():
    src = SEED.read_text(encoding='utf-8')
    for name in (
        'load_test_app_secret',
        'load_test_tenant_id',
        'load_test_phone_number_id',
    ):
        assert name in src, f'seed must persist {name}'
    # Idempotent: looks up existing tenant by slug before inserting.
    assert "select id from app.tenants where slug=$1" in src
    # Channel must be active + linked to the secret_ref the API resolves.
    assert "'secrets/load_test_app_secret'" in src
    assert "provider='whatsapp_cloud_api'" in src
    assert "status='active'" in src


# 6 ── Aggregator regenerates the docs/sla.md results section
def test_aggregator_uses_markers_and_table():
    src = AGGREGATE.read_text(encoding='utf-8')
    assert '<!-- load-test-results:start -->' in src
    assert '<!-- load-test-results:end -->' in src
    # The CSV reader pulls the Aggregated row.
    assert "Aggregated" in src or "'aggregated'" in src
    # The aggregator enforces both p95 and RPS targets.
    assert '--enforce-sla' in src
    assert 'p95_target_ms' in src
    assert 'rps_target' in src


# 7 ── docs/sla.md contains the SLA targets and the auto-regenerated block
def test_sla_doc_has_targets_and_results_markers():
    src = SLA_DOC.read_text(encoding='utf-8')
    # SLA targets as per the backlog.
    assert '99.9' in src
    assert 'p95 < 2.0 s' in src
    assert '50 msg/s' in src or '50 msg/s' in src.replace('\xa0', ' ')
    # Auto-regenerated block must be present so the aggregator can edit it.
    assert '<!-- load-test-results:start -->' in src
    assert '<!-- load-test-results:end -->' in src


# 8 ── GitHub Actions: load-test job exists with the right wiring
def test_workflow_runs_locust_against_ephemeral_compose():
    src = WORKFLOW.read_text(encoding='utf-8')
    # Triggers required by the backlog (release) + safety net (main).
    assert 'release:' in src
    assert 'workflow_dispatch:' in src
    # Services block provisions an ephemeral Postgres for the run.
    assert 'pgvector/pgvector:pg16' in src
    # Seed → start API → run Locust → aggregate → enforce SLA.
    assert 'python -m tests.load.seed_load_tenant' in src
    assert 'locust -f tests/load/test_journey_load.py' in src
    assert 'python -m tests.load.aggregate_results' in src
    assert '--enforce-sla' in src
    # 50 users default per backlog (≈50 msg/s with the 1–3s think time).
    assert "'50'" in src


# 9 ── pyproject ships locust under the `load` extras only
def test_pyproject_keeps_locust_in_load_extras():
    src = PYPROJECT.read_text(encoding='utf-8')
    assert re.search(r'^load\s*=\s*\["locust', src, re.MULTILINE), (
        'pyproject must define an [load] extras with locust'
    )
    # Locust must NOT leak into the `dev` extras (keeps unit CI fast).
    dev_line = re.search(r'^dev\s*=\s*\[[^\]]*\]', src, re.MULTILINE)
    assert dev_line
    assert 'locust' not in dev_line.group(0)


# 10 ── pytest must skip tests/load/ so unit CI does not need locust
def test_conftest_excludes_load_dir_from_collection():
    src = CONFTEST.read_text(encoding='utf-8')
    assert "collect_ignore_glob" in src
    assert "'load/*'" in src or '"load/*"' in src


# 11 ── Aggregator parses a synthetic Locust CSV without crashing
def test_aggregator_renders_section_from_synthetic_csv(tmp_path):
    # Build a Locust-stats-shaped CSV with one Aggregated row.
    fieldnames = [
        'Type', 'Name', 'Request Count', 'Failure Count',
        'Median Response Time', 'Average Response Time',
        'Min Response Time', 'Max Response Time',
        'Average Content Size', 'Requests/s', 'Failures/s',
        '50%', '66%', '75%', '80%', '90%', '95%', '98%', '99%', '99.9%', '99.99%', '100%',
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    base_row = {k: '' for k in fieldnames}
    inbound = {**base_row, 'Type': 'POST', 'Name': 'POST /v1/webhooks/whatsapp',
               'Request Count': '14000', 'Failure Count': '0',
               'Requests/s': '46.7', '50%': '180', '95%': '850', '99%': '1300',
               'Average Response Time': '210'}
    aggregated = {**base_row, 'Type': '', 'Name': 'Aggregated',
                  'Request Count': '20000', 'Failure Count': '0',
                  'Requests/s': '66.7', '50%': '170', '95%': '900', '99%': '1500',
                  'Average Response Time': '200'}
    writer.writerow(inbound)
    writer.writerow(aggregated)

    csv_path = tmp_path / 'run_stats.csv'
    csv_path.write_text(buf.getvalue(), encoding='utf-8')

    sla_path = tmp_path / 'sla.md'
    sla_path.write_text(
        'header\n<!-- load-test-results:start -->old<!-- load-test-results:end -->\nfooter\n',
        encoding='utf-8',
    )

    import importlib.util
    spec = importlib.util.spec_from_file_location('aggregate_results', AGGREGATE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    rc = module.main([
        '--csv-prefix', str(tmp_path / 'run'),
        '--sla-file', str(sla_path),
        '--enforce-sla',
        '--p95-target-ms', '2000',
        '--rps-target', '25',
    ])
    assert rc == 0
    rewritten = sla_path.read_text(encoding='utf-8')
    assert '66.70 req/s' in rewritten
    assert '900 ms' in rewritten
    # The header / footer of the SLA doc are preserved verbatim.
    assert rewritten.startswith('header\n')
    assert rewritten.rstrip().endswith('footer')


# 12 ── Aggregator returns exit 1 when p95 breaches the SLA target
def test_aggregator_enforces_sla_failure(tmp_path):
    fieldnames = [
        'Type', 'Name', 'Request Count', 'Failure Count',
        'Median Response Time', 'Average Response Time',
        'Min Response Time', 'Max Response Time',
        'Average Content Size', 'Requests/s', 'Failures/s',
        '50%', '66%', '75%', '80%', '90%', '95%', '98%', '99%', '99.9%', '99.99%', '100%',
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    base = {k: '' for k in fieldnames}
    writer.writerow({**base, 'Name': 'Aggregated', 'Request Count': '1',
                     'Requests/s': '50.0', '95%': '2500'})
    (tmp_path / 'run_stats.csv').write_text(buf.getvalue(), encoding='utf-8')
    (tmp_path / 'sla.md').write_text(
        '<!-- load-test-results:start -->x<!-- load-test-results:end -->',
        encoding='utf-8',
    )

    import importlib.util
    spec = importlib.util.spec_from_file_location('aggregate_results_2', AGGREGATE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    rc = module.main([
        '--csv-prefix', str(tmp_path / 'run'),
        '--sla-file', str(tmp_path / 'sla.md'),
        '--enforce-sla',
        '--p95-target-ms', '2000',
        '--rps-target', '25',
    ])
    assert rc == 1, 'aggregator must exit non-zero when p95 breaches SLA'


# 13 ── Locustfile is importable even without locust installed (shim path)
def test_locustfile_importable_without_locust(monkeypatch):
    # Force the ImportError branch by removing locust from sys.modules cache.
    import sys
    for mod in list(sys.modules):
        if mod == 'locust' or mod.startswith('locust.'):
            sys.modules.pop(mod, None)
    monkeypatch.setitem(sys.modules, 'locust', None)

    import importlib.util
    spec = importlib.util.spec_from_file_location('journey_load', LOCUSTFILE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    try:
        spec.loader.exec_module(module)
    except Exception as exc:  # pragma: no cover - defensive
        pytest.fail(f'load file must import without locust installed: {exc}')

    # The class is exposed and the @task-decorated callables survive the shim.
    assert hasattr(module, 'JourneyUser')
    for name in ('inbound_message', 'panel_reads', 'admin_actions'):
        attr = getattr(module.JourneyUser, name)
        assert callable(attr)
