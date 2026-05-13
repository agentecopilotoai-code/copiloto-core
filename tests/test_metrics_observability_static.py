"""Static tests for TASK-0060 — Prometheus metrics + alerts.

Coverage (≥8 tests):
 1.  `app.services.metrics` declara los counters/histograms/gauges del contrato.
 2.  `record_message` solo acepta direcciones/estados conocidos.
 3.  `observe_response_latency` ignora segundos negativos.
 4.  `set_circuit_breaker_state` mapea closed/half_open/open a 0/1/2.
 5.  `parse_ip_allowlist` produce un set inmutable a partir de CSV.
 6.  `ip_allowed` exige match exacto y rechaza IP None.
 7.  `render_latest` devuelve bytes + content-type prometheus.
 8.  `app.main.create_app` registra el endpoint `/metrics` (403 sin allowlist).
 9.  El archivo `infra/observability/alerts.yaml` parsea como YAML válido con
     ≥ 6 reglas seed.
10.  `docker-compose.yml` define el servicio `prometheus` con profile
     `observability` y monta `alerts.yaml`.
11.  El circuit breaker actualiza el gauge `cpi_circuit_breaker_state` al
     abrir/cerrar.
12.  El worker `event_worker.process_once` actualiza `cpi_worker_queue_depth`.
13.  `cloud_llm_answer._call_provider` reporta `cpi_llm_calls_total` con
     status success/error/rejected.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


def test_metrics_module_declares_required_collectors() -> None:
    from app.services import metrics

    for attr in (
        'messages_total',
        'response_latency_seconds',
        'llm_calls_total',
        'appointments_total',
        'handoff_total',
        'circuit_breaker_state',
        'worker_queue_depth',
    ):
        assert hasattr(metrics, attr), f'metrics module is missing {attr}'

    # Los nombres canónicos cpi_* deben aparecer en el texto exportado para
    # que Prometheus los pueda raspar exactamente como el contrato indica.
    payload, _ = metrics.render_latest()
    text = payload.decode()
    for name in (
        'cpi_messages_total',
        'cpi_response_latency_seconds',
        'cpi_llm_calls_total',
        'cpi_appointments_total',
        'cpi_handoff_total',
        'cpi_circuit_breaker_state',
        'cpi_worker_queue_depth',
    ):
        assert name in text, f'{name} not exposed in /metrics payload'


def test_record_message_rejects_unknown_direction_or_status() -> None:
    from app.services import metrics

    metrics.record_message(
        tenant_id='t1',
        direction='inbound',
        channel='whatsapp',
        status='accepted',
    )
    # Unknown direction → no-op (no exception).
    metrics.record_message(
        tenant_id='t1',
        direction='sideways',
        channel='whatsapp',
        status='accepted',
    )
    # Unknown status → no-op.
    metrics.record_message(
        tenant_id='t1',
        direction='outbound',
        channel='whatsapp',
        status='zzz',
    )

    samples = {
        sample.labels['status']
        for metric in metrics.messages_total.collect()
        for sample in metric.samples
        if sample.name.endswith('_total')
    }
    assert 'zzz' not in samples
    assert 'accepted' in samples


def test_observe_response_latency_ignores_negative_values() -> None:
    from app.services import metrics

    before = sum(
        sample.value
        for metric in metrics.response_latency_seconds.collect()
        for sample in metric.samples
        if sample.name.endswith('_count')
    )
    metrics.observe_response_latency(tenant_id='t1', tier='template', seconds=-3.0)
    after = sum(
        sample.value
        for metric in metrics.response_latency_seconds.collect()
        for sample in metric.samples
        if sample.name.endswith('_count')
    )
    assert after == before


def test_set_circuit_breaker_state_maps_state_to_numeric_value() -> None:
    from app.services import metrics

    metrics.set_circuit_breaker_state(provider='claude_test', state='closed')
    metrics.set_circuit_breaker_state(provider='claude_test', state='half_open')
    metrics.set_circuit_breaker_state(provider='claude_test', state='open')

    samples = {
        sample.labels['provider']: sample.value
        for metric in metrics.circuit_breaker_state.collect()
        for sample in metric.samples
    }
    assert samples['claude_test'] == 2  # last set: open

    # Unknown state → no-op (no exception, no new label).
    metrics.set_circuit_breaker_state(provider='claude_test', state='exploded')
    samples_after = {
        sample.labels['provider']: sample.value
        for metric in metrics.circuit_breaker_state.collect()
        for sample in metric.samples
    }
    assert samples_after['claude_test'] == 2


def test_parse_ip_allowlist_handles_csv_and_blanks() -> None:
    from app.services.metrics import parse_ip_allowlist

    assert parse_ip_allowlist(None) == frozenset()
    assert parse_ip_allowlist('') == frozenset()
    assert parse_ip_allowlist('10.0.0.1, ,10.0.0.2') == frozenset({'10.0.0.1', '10.0.0.2'})
    # Inmutable: no se puede mutar el resultado por accidente.
    result = parse_ip_allowlist('10.0.0.1')
    assert isinstance(result, frozenset)


def test_ip_allowed_requires_exact_match() -> None:
    from app.services.metrics import ip_allowed

    allow = {'10.0.0.5'}
    assert ip_allowed('10.0.0.5', allow) is True
    assert ip_allowed('10.0.0.6', allow) is False
    assert ip_allowed(None, allow) is False
    assert ip_allowed('10.0.0.5', set()) is False


def test_render_latest_returns_prometheus_content_type() -> None:
    from prometheus_client import CONTENT_TYPE_LATEST

    from app.services.metrics import render_latest

    payload, content_type = render_latest()
    assert isinstance(payload, (bytes, bytearray))
    assert content_type == CONTENT_TYPE_LATEST


def test_main_wires_metrics_endpoint_and_allowlist_helpers() -> None:
    main_path = ROOT / 'app' / 'main.py'
    source = main_path.read_text()
    # El endpoint /metrics debe estar registrado en la app raíz, no bajo /v1.
    assert "@api.get('/metrics'" in source
    # Debe consultar la allowlist parseada desde la config.
    assert 'parse_ip_allowlist' in source
    assert 'ip_allowed' in source
    # Debe responder 403 cuando la IP no está autorizada (deny por defecto).
    assert 'status_code=403' in source
    # Debe servir el payload usando render_latest() con su content-type.
    assert 'render_latest' in source


def test_alerts_yaml_has_six_seed_rules() -> None:
    yaml = pytest.importorskip('yaml')
    path = ROOT / 'infra' / 'observability' / 'alerts.yaml'
    data = yaml.safe_load(path.read_text())

    assert 'groups' in data
    rules = [
        rule
        for group in data['groups']
        for rule in group.get('rules', [])
    ]
    alert_names = [rule['alert'] for rule in rules]
    assert len(alert_names) >= 6, alert_names
    # Cada regla seed debe tener expr y annotations.
    for rule in rules:
        assert rule.get('expr'), f'{rule.get("alert")} sin expr'
        assert rule.get('annotations'), f'{rule.get("alert")} sin annotations'


def test_compose_declares_prometheus_with_observability_profile() -> None:
    yaml = pytest.importorskip('yaml')
    compose = yaml.safe_load((ROOT / 'docker-compose.yml').read_text())

    services = compose['services']
    assert 'prometheus' in services
    prom = services['prometheus']
    assert 'observability' in prom['profiles']
    mounts = ' '.join(prom['volumes'])
    assert 'alerts.yaml' in mounts
    assert 'prometheus.yml' in mounts


def test_circuit_breaker_updates_metric_on_state_change() -> None:
    import asyncio

    from app.services import metrics
    from app.services.circuit_breaker import CircuitBreaker

    breaker = CircuitBreaker(name='cb_metric_test', failure_threshold=2, cooldown_seconds=10.0)

    async def boom() -> None:
        raise RuntimeError('boom')

    async def drive_failures() -> None:
        for _ in range(2):
            try:
                await breaker.call(boom)
            except RuntimeError:
                pass

    asyncio.run(drive_failures())

    samples = {
        sample.labels['provider']: sample.value
        for metric in metrics.circuit_breaker_state.collect()
        for sample in metric.samples
    }
    assert samples.get('cb_metric_test') == 2  # open

    # Forzar cierre.
    breaker._reset()
    samples_after = {
        sample.labels['provider']: sample.value
        for metric in metrics.circuit_breaker_state.collect()
        for sample in metric.samples
    }
    assert samples_after['cb_metric_test'] == 0


def test_event_worker_imports_metrics_helpers() -> None:
    from app.workers import event_worker

    source = inspect.getsource(event_worker)
    assert 'set_worker_queue_depth' in source
    assert 'record_message' in source
    # El gauge debe alimentarse del conteo de domain_events pendientes.
    assert "event_name='message.queued'" in source


def test_cloud_llm_call_provider_reports_metric_states() -> None:
    from app.services import cloud_llm_answer

    source = inspect.getsource(cloud_llm_answer._call_provider)
    assert "record_llm_call" in source
    assert "'success'" in source
    assert "'error'" in source
    assert "'rejected'" in source


def test_normalize_handoff_reason_buckets_freeform_text() -> None:
    from app.services.metrics import normalize_handoff_reason

    # Valores conocidos pasan tal cual (lowercased).
    assert normalize_handoff_reason('manual') == 'manual'
    assert normalize_handoff_reason('Policy') == 'policy'
    assert normalize_handoff_reason('max_turns') == 'max_turns'

    # Texto libre cae a 'other' para evitar explotar la cardinalidad.
    assert normalize_handoff_reason('cliente furioso por demora') == 'other'
    assert normalize_handoff_reason('123') == 'other'

    # None/vacío → 'unspecified'.
    assert normalize_handoff_reason(None) == 'unspecified'
    assert normalize_handoff_reason('') == 'unspecified'
    assert normalize_handoff_reason('   ') == 'unspecified'


def test_record_handoff_normalizes_label_value() -> None:
    from app.services import metrics

    metrics.record_handoff(tenant_id='t1', reason='este texto no está en el enum')
    metrics.record_handoff(tenant_id='t1', reason='manual')

    reasons = {
        sample.labels['reason']
        for metric in metrics.handoff_total.collect()
        for sample in metric.samples
        if sample.name.endswith('_total')
    }
    # El texto libre nunca aparece como label: solo el bucket.
    assert 'este texto no está en el enum' not in reasons
    assert 'other' in reasons
    assert 'manual' in reasons


def test_workers_expose_metrics_http_server() -> None:
    from app.services import metrics
    from app.workers import event_worker, scheduler

    # El helper debe estar declarado y delegar en prometheus_client.
    assert hasattr(metrics, 'start_metrics_http_server')

    event_src = inspect.getsource(event_worker.main)
    scheduler_src = inspect.getsource(scheduler.main)
    assert 'start_metrics_http_server' in event_src
    assert 'start_metrics_http_server' in scheduler_src

    # El scheduler también actualiza su gauge de queue depth.
    full_src = inspect.getsource(scheduler)
    assert "set_worker_queue_depth(worker='scheduler'" in full_src


def test_prometheus_config_scrapes_workers() -> None:
    yaml = pytest.importorskip('yaml')
    config = yaml.safe_load(
        (ROOT / 'infra' / 'observability' / 'prometheus.yml').read_text()
    )
    jobs = {sc['job_name']: sc for sc in config['scrape_configs']}
    assert 'copilotoia-workers' in jobs
    targets = jobs['copilotoia-workers']['static_configs'][0]['targets']
    assert any('event-worker' in t for t in targets)
    assert any('scheduler' in t for t in targets)


def test_compose_workers_expose_metrics_port() -> None:
    yaml = pytest.importorskip('yaml')
    compose = yaml.safe_load((ROOT / 'docker-compose.yml').read_text())
    for worker in ('event-worker', 'scheduler'):
        svc = compose['services'][worker]
        expose = [str(p) for p in svc.get('expose', [])]
        assert '9100' in expose, f'{worker} should expose port 9100 for metrics'
