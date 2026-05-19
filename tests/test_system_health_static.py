"""Static + functional tests for UI-006.2: GET /v1/platform/metrics/health.

Covers:

* The endpoint is wired on ``platform_admin_router`` (which carries
  ``authenticate_request`` + ``require_platform_owner`` +
  ``require_mfa_for_privileged`` at the router level) and never on a
  tenant-scoped router.
* ``metrics.collect_health_snapshot`` materialises the in-process Prometheus
  registry into the documented structure.
* ``metrics.evaluate_health_alerts`` derives alerts from breached thresholds.
* ``metrics._histogram_quantile`` interpolates over cumulative buckets.
"""
from __future__ import annotations


import pytest
from tests._routes_aggregator import routes_aggregated_source

@pytest.fixture(scope='module')
def routes_source() -> str:
    return routes_aggregated_source()


# ── Endpoint lives on platform_admin_router ──────────────────────────────────


def test_system_health_endpoint_on_platform_admin_router(routes_source: str) -> None:
    assert "@platform_admin_router.get('/platform/metrics/health')" in routes_source, (
        'GET /v1/platform/metrics/health must be exposed on platform_admin_router (UI-006.2)'
    )


def test_system_health_not_on_tenant_routers(routes_source: str) -> None:
    """Defense in depth: never let a tenant-scoped role reach the fleet health."""
    for router in ('tenant_admin_router', 'tenant_ops_router', 'tenant_user_router'):
        assert f"@{router}.get('/platform/metrics/health')" not in routes_source


def test_system_health_handler_uses_metrics_module(routes_source: str) -> None:
    assert 'metrics.collect_health_snapshot()' in routes_source
    assert 'metrics.evaluate_health_alerts(' in routes_source


# ── collect_health_snapshot ──────────────────────────────────────────────────


def test_collect_health_snapshot_has_documented_shape() -> None:
    from app.services import metrics

    snapshot = metrics.collect_health_snapshot()
    for key in (
        'messages',
        'response_latency',
        'llm_calls',
        'circuit_breakers',
        'workers',
        'outbound_dlq',
    ):
        assert key in snapshot, f'snapshot is missing {key}'
    assert isinstance(snapshot['circuit_breakers'], list)
    assert isinstance(snapshot['workers'], list)


def test_collect_health_snapshot_reflects_registry_gauges() -> None:
    from app.services import metrics

    metrics.set_circuit_breaker_state(provider='meta_health_test', state='open')
    metrics.set_worker_queue_depth(worker='health_test_worker', depth=1500)

    snapshot = metrics.collect_health_snapshot()
    breaker = next(
        b for b in snapshot['circuit_breakers'] if b['provider'] == 'meta_health_test'
    )
    assert breaker['state'] == 'open'
    assert breaker['state_value'] == 2

    worker = next(
        w for w in snapshot['workers'] if w['worker'] == 'health_test_worker'
    )
    assert worker['queue_depth'] == 1500


# ── evaluate_health_alerts ───────────────────────────────────────────────────


def test_evaluate_health_alerts_fires_on_breached_thresholds() -> None:
    from app.services import metrics

    snapshot = {
        'messages': {'outbound_error_rate': 0.5},
        'response_latency': {'p95': 9.0},
        'workers': [{'worker': 'event_worker', 'queue_depth': 1500}],
        'circuit_breakers': [
            {'provider': 'meta', 'state': 'open', 'state_value': 2},
        ],
    }
    names = {alert['name'] for alert in metrics.evaluate_health_alerts(snapshot)}
    assert names == {
        'BotResponseLatencyP95High',
        'HighOutboundErrorRate',
        'WorkerQueueBacklog',
        'CircuitBreakerOpenSustained',
    }


def test_evaluate_health_alerts_quiet_when_healthy() -> None:
    from app.services import metrics

    snapshot = {
        'messages': {'outbound_error_rate': 0.0},
        'response_latency': {'p95': 1.2},
        'workers': [{'worker': 'event_worker', 'queue_depth': 12}],
        'circuit_breakers': [
            {'provider': 'anthropic', 'state': 'closed', 'state_value': 0},
        ],
    }
    assert metrics.evaluate_health_alerts(snapshot) == []


# ── _histogram_quantile ──────────────────────────────────────────────────────


def test_histogram_quantile_interpolates_within_bucket() -> None:
    from app.services import metrics

    # 10 observations, all in the (5, 10] bucket.
    buckets = [(0.5, 0), (1.0, 0), (2.0, 0), (5.0, 0), (10.0, 10), (float('inf'), 10)]
    p50 = metrics._histogram_quantile(buckets, 0.5)
    assert p50 == pytest.approx(7.5)


def test_histogram_quantile_returns_none_for_empty() -> None:
    from app.services import metrics

    assert metrics._histogram_quantile([], 0.95) is None
    assert metrics._histogram_quantile([(1.0, 0), (float('inf'), 0)], 0.95) is None
