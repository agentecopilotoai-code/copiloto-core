"""HTTP E2E — App lifecycle, health, metrics endpoint, middleware contracts.

Covers:
  * App boots cleanly with the lifespan context manager (DB pool opens).
  * `/v1/health` is public and returns the expected shape.
  * `/metrics` requires the request IP to be in the allowlist (403 otherwise),
    and exposes ALL the AUDIT-51 gauges + counters.
  * Rate-limit middleware: 429 + `Retry-After` when the bucket is exhausted.
  * CORS middleware on `/v1/web/*` endpoints (web widget).
  * Unknown route returns 404 (FastAPI default), not 500.
"""
from __future__ import annotations


import pytest

from tests.conftest_e2e_http import (  # noqa: F401,F811  -- pytest discovery
    auth_headers,
    e2e_http_dsn,
    e2e_http_schema,
    http_app,
    http_client,
    http_tenant_factory,
    service_headers,
)
from tests.conftest_e2e import e2e_enabled

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not e2e_enabled(), reason='RUN_E2E=1 required'),
]


# ── Health / smoke ──────────────────────────────────────────────────────────


def test_health_endpoint_is_public_and_returns_ok(http_client):
    """`/v1/health` MUST NOT require auth (load balancer probes hit it)."""
    resp = http_client.get('/v1/health')
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert 'status' in body or body == {}  # tolerate either shape


def test_unknown_path_returns_404_not_500(http_client):
    resp = http_client.get('/v1/this-route-does-not-exist')
    assert resp.status_code == 404


# ── /metrics endpoint + AUDIT-51 gauges ─────────────────────────────────────


def test_metrics_endpoint_serves_prometheus_payload(http_client):
    """The `/metrics` endpoint must:
    * Be allowed for `127.0.0.1` (set in OBSERVABILITY_ALLOWED_IPS by conftest).
    * Serve text/plain; version=0.0.4 (prom format).
    * Include the AUDIT-51 gauges and counters even before any traffic.
    """
    resp = http_client.get('/metrics')
    assert resp.status_code == 200, resp.text
    body = resp.text
    # Pre-existing gauges (sanity)
    assert 'cpi_circuit_breaker_state' in body or 'cpi_worker_queue_depth' in body
    # AUDIT-51: new metrics MUST be declared (even if value=0)
    for metric in (
        'cpi_ws_fanout_subscriber_count',
        'cpi_ws_fanout_tenant_count',
        'cpi_ws_fanout_dropped_total',
        'cpi_ws_fanout_supervisor_crashes_total',
        'cpi_rate_limit_buckets_current',
        'cpi_rate_limit_buckets_evicted_total',
    ):
        assert metric in body, f'AUDIT-51 metric `{metric}` MUST be exposed at /metrics'


def test_metrics_endpoint_blocks_when_ip_not_in_allowlist(http_app, monkeypatch):
    """If the allowlist is empty the endpoint is inaccessible (defense in
    depth — operator must opt in IPs explicitly)."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    # Rebuild app with empty allowlist to verify the 403 path.
    monkeypatch.setenv('OBSERVABILITY_ALLOWED_IPS', '')
    from app.core.config import get_settings  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415
    get_settings.cache_clear()
    isolated_app = create_app()
    with TestClient(isolated_app) as client:
        resp = client.get('/metrics')
    assert resp.status_code == 403
    # Restore for other tests
    monkeypatch.setenv('OBSERVABILITY_ALLOWED_IPS', 'testclient,127.0.0.1')
    get_settings.cache_clear()


# ── Rate limit middleware ───────────────────────────────────────────────────


def test_rate_limit_returns_429_with_retry_after_when_exhausted(http_app, monkeypatch):
    """Force a tight bucket and verify 429 + Retry-After header."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    # Build an isolated app with `rate_limit_per_min=2` so we can exhaust quickly.
    monkeypatch.setenv('RATE_LIMIT_PER_MIN', '2')
    monkeypatch.setenv('RATE_LIMIT_WEBHOOK_PER_MIN', '2')
    from app.core.config import get_settings  # noqa: PLC0415
    from app.main import create_app  # noqa: PLC0415
    get_settings.cache_clear()
    isolated_app = create_app()
    with TestClient(isolated_app) as client:
        ok1 = client.get('/v1/health')
        ok2 = client.get('/v1/health')
        rejected = client.get('/v1/health')
    assert ok1.status_code == 200
    assert ok2.status_code == 200
    assert rejected.status_code == 429
    # Retry-After header is present and parseable as int seconds
    assert 'retry-after' in {k.lower() for k in rejected.headers.keys()}
    retry_after = rejected.headers.get('retry-after') or rejected.headers.get('Retry-After')
    assert retry_after and int(retry_after) >= 1
    # Restore
    monkeypatch.setenv('RATE_LIMIT_PER_MIN', '10000')
    monkeypatch.setenv('RATE_LIMIT_WEBHOOK_PER_MIN', '10000')
    get_settings.cache_clear()


def test_rate_limit_buckets_current_gauge_reflects_traffic(http_app, http_client):
    """After firing a few requests, the rate_limit gauge must be > 0 at scrape time."""
    for _ in range(3):
        http_client.get('/v1/health')
    metrics = http_client.get('/metrics').text
    # Find the `cpi_rate_limit_buckets_current N.0` line
    matches = [
        line for line in metrics.splitlines()
        if line.startswith('cpi_rate_limit_buckets_current ')
        and not line.startswith('cpi_rate_limit_buckets_current{')  # skip TYPE/HELP
    ]
    assert matches, f'cpi_rate_limit_buckets_current gauge missing from /metrics:\n{metrics}'
    value = float(matches[-1].split()[-1])
    assert value >= 1.0, f'Expected ≥1 bucket after traffic, got {value}'


# ── CORS for web widget ─────────────────────────────────────────────────────


def test_web_widget_path_returns_cors_headers(http_client):
    """`/v1/web/*` endpoints must allow cross-origin requests from arbitrary
    sites (the widget runs on the customer's domain)."""
    resp = http_client.options(
        '/v1/web/chat/start',
        headers={
            'origin': 'https://customer-site.example.com',
            'access-control-request-method': 'POST',
            'access-control-request-headers': 'content-type',
        },
    )
    # OPTIONS preflight returns 204 (configured in main.py).
    assert resp.status_code in (200, 204)
    h = {k.lower(): v for k, v in resp.headers.items()}
    assert h.get('access-control-allow-origin') == 'https://customer-site.example.com'
    assert 'POST' in (h.get('access-control-allow-methods') or '')


def test_non_widget_path_does_not_get_cors_headers(http_client):
    """`/v1/me`-style paths SHOULD NOT advertise wide CORS (those are admin-panel
    only and the BFF is same-origin)."""
    resp = http_client.options(
        '/v1/health',
        headers={'origin': 'https://attacker.example.com'},
    )
    # We don't assert a specific status — only that the CORS allow-origin is
    # NOT a permissive echo of the attacker domain.
    h = {k.lower(): v for k, v in resp.headers.items()}
    assert h.get('access-control-allow-origin') != 'https://attacker.example.com'
