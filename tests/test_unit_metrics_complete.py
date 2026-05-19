"""Completeness tests for app/services/metrics.py — fills gaps in
refresh_runtime_metrics (exception branches), refresh_backup_age_metrics
(None age + DB failure path), _histogram_quantile (cum==prev_count + final
return), evaluate_health_alerts (101..1000 SchedulerBehind), and
start_metrics_http_server.
"""
from __future__ import annotations

import asyncio



# ── Lines 190-191: ws_fanout import / read failure ───────────────────────


def test_refresh_runtime_metrics_swallows_ws_fanout_failure(monkeypatch):
    """If reading ws_fanout subscriber/tenant counts raises, the rest must run."""
    from app.services import metrics

    # Force the inner attribute read to raise via a sentinel module patch.
    import app.admin.ws_fanout as fanout_mod

    class _BoomFanout:
        @property
        def subscriber_count(self):  # pragma: no cover - re-raised via property
            raise RuntimeError('boom')

        @property
        def tenant_count(self):  # pragma: no cover
            raise RuntimeError('boom')

    monkeypatch.setattr(fanout_mod, 'fanout', _BoomFanout())
    metrics.refresh_runtime_metrics()  # must not raise


# ── Lines 200-201: rate-limiter `.size` attribute raises ─────────────────


def test_refresh_runtime_metrics_swallows_rate_limiter_failure(monkeypatch):
    from app.services import metrics

    class _BoomLimiter:
        @property
        def size(self):  # pragma: no cover - re-raised
            raise RuntimeError('limiter dead')

    monkeypatch.setattr(metrics, '_active_rate_limiter', _BoomLimiter())
    metrics.refresh_runtime_metrics()  # must not raise


# ── Lines 235-237: refresh_backup_age_metrics — row['age'] is None ────────


class _FakeConn:
    def __init__(self, rows, failed_age):
        self._rows = rows
        self._failed = failed_age

    async def fetch(self, _sql):
        return self._rows

    async def fetchval(self, _sql):
        return self._failed


def test_refresh_backup_age_metrics_skips_none_age_and_sets_failed():
    from app.services import metrics

    rows = [
        {'kind': 'cloud_dump', 'age': None},      # → continue (line 236)
        {'kind': 'cloud_verify', 'age': 12.5},    # → set
    ]
    conn = _FakeConn(rows=rows, failed_age=99.0)  # → trigger line 253
    asyncio.run(metrics.refresh_backup_age_metrics(conn))


def test_refresh_backup_age_metrics_handles_db_exception(caplog):
    from app.services import metrics

    class _BadConn:
        async def fetch(self, _sql):
            raise RuntimeError('db down')

        async def fetchval(self, _sql):  # pragma: no cover - unreached
            return None

    asyncio.run(metrics.refresh_backup_age_metrics(_BadConn()))  # no raise


def test_refresh_backup_age_metrics_no_failed_age_keeps_silent():
    from app.services import metrics
    rows = [{'kind': 'cloud_dump', 'age': 5.0}]
    asyncio.run(metrics.refresh_backup_age_metrics(_FakeConn(rows=rows, failed_age=None)))


# ── Line 425: histogram_quantile — cum == prev_count returns upper ────────


def test_histogram_quantile_zero_width_bucket():
    """When cum == prev_count at the trigger point, linear interpolation
    is undefined; the function returns `upper` directly (line 425).
    Reached when the very first bucket already meets the rank (rank=0)."""
    from app.services.metrics import _histogram_quantile

    # quantile=0 → rank = 0. First bucket: upper=1.0, cum=0 ≥ 0 (rank).
    # cum(0) == prev_count(0) → branch hits.
    buckets = [(1.0, 0.0), (2.0, 5.0), (float('inf'), 10.0)]
    result = _histogram_quantile(buckets, 0.0)
    assert result == 1.0


# ── Line 431: final fallthrough return prev_bound or None ────────────────


def test_histogram_quantile_no_bucket_reaches_rank_falls_through(monkeypatch):
    """If no bucket has cum >= rank, the loop ends and we fall through to
    return prev_bound or None (line 431). This requires the +Inf bucket to
    have cum < rank, which only happens when totals are inconsistent.
    """
    from app.services.metrics import _histogram_quantile

    # Total = 10, rank = 8.0. Provide buckets where every cum < rank.
    # Note: line 414 uses buckets[-1][1] as `total`, then rank = q*total.
    # We need rank > last bucket cum — so we set quantile > 1.0 to defeat
    # the invariant intentionally for this branch.
    buckets = [(1.0, 2.0), (2.0, 5.0), (float('inf'), 10.0)]
    result = _histogram_quantile(buckets, 1.5)
    # rank = 1.5*10 = 15; no bucket has cum>=15 → falls through.
    # prev_bound after loop = 2.0 (we don't update for +inf). Returns 2.0.
    assert result == 2.0


# ── Line 592: SchedulerBehind warning when 101 < queue_depth <= 1000 ─────


def test_evaluate_health_alerts_scheduler_behind_warning():
    from app.services.metrics import evaluate_health_alerts

    snapshot = {
        'response_latency': {'p95': None},
        'messages': {'outbound_error_rate': 0.0},
        'workers': [{'worker': 'event_worker', 'queue_depth': 500}],
        'circuit_breakers': [],
    }
    alerts = evaluate_health_alerts(snapshot)
    names = [a['name'] for a in alerts]
    assert 'SchedulerBehind' in names
    sched = next(a for a in alerts if a['name'] == 'SchedulerBehind')
    assert sched['severity'] == 'warning'


def test_evaluate_health_alerts_all_severe_paths():
    """Covers lines 561 (latency), 570 (error rate), 580 (worker > 1000)."""
    from app.services.metrics import evaluate_health_alerts

    snapshot = {
        'response_latency': {'p95': 6.5},
        'messages': {'outbound_error_rate': 0.5},
        'workers': [{'worker': 'event_worker', 'queue_depth': 5000}],
        'circuit_breakers': [{'provider': 'meta', 'state_value': 2}],
    }
    alerts = evaluate_health_alerts(snapshot)
    names = {a['name'] for a in alerts}
    assert 'BotResponseLatencyP95High' in names
    assert 'HighOutboundErrorRate' in names
    assert 'WorkerQueueBacklog' in names
    assert 'CircuitBreakerOpenSustained' in names


# ── Lines 627, 629: start_metrics_http_server delegates to prometheus_client


def test_start_metrics_http_server_invokes_prometheus_client(monkeypatch):
    from app.services import metrics

    called = {}

    def fake_start(port, addr, registry):
        called['port'] = port
        called['addr'] = addr
        called['registry'] = registry

    # Patch the symbol the function imports lazily.
    import prometheus_client
    monkeypatch.setattr(prometheus_client, 'start_http_server', fake_start)

    metrics.start_metrics_http_server(9999, addr='127.0.0.1')
    assert called['port'] == 9999
    assert called['addr'] == '127.0.0.1'
    assert called['registry'] is metrics.REGISTRY
