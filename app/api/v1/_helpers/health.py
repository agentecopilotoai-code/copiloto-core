"""Health snapshot derivation helpers extracted from app/api/v1/routes.py."""
from __future__ import annotations


# `require_platform_owner` + `require_mfa_for_privileged`) — never relaxed at
# the handler level.
#
# Reads the in-process Prometheus `REGISTRY` (the same one `/metrics` exposes
# and Prometheus scrapes — TASK-0060) plus a live DB connectivity probe. It is a
# point-in-time snapshot; historical time-series (24h/7d/30d) require the
# Prometheus query API and are out of scope for UI-006.2.
def _derive_health_services(
    snapshot: dict, *, db_ok: bool, db_latency_ms: float | None
) -> list[dict]:
    """Synthesise the per-service health rows from the metrics snapshot.

    Status vocabulary: ``ok`` / ``warn`` / ``down``. The API row is always
    ``ok`` — if this handler runs, the API process is serving requests.
    """
    services: list[dict] = [
        {
            'key': 'api',
            'label': 'API · FastAPI',
            'status': 'ok',
            'detail': 'Atendiendo requests',
        },
        {
            'key': 'postgres',
            'label': 'Postgres · primary',
            'status': 'ok' if db_ok else 'down',
            'detail': (
                f'select 1 · {db_latency_ms}ms'
                if db_ok and db_latency_ms is not None
                else 'sin conexión'
            ),
        },
    ]
    for worker in snapshot['workers']:
        depth = worker['queue_depth']
        if depth > 1000:
            worker_status = 'down'
        elif depth > 100:
            worker_status = 'warn'
        else:
            worker_status = 'ok'
        services.append({
            'key': f"worker:{worker['worker']}",
            'label': f"Worker · {worker['worker']}",
            'status': worker_status,
            'detail': f"queue {depth}",
        })
    for breaker in snapshot['circuit_breakers']:
        state = breaker['state']
        if state == 'open':
            breaker_status = 'down'
        elif state == 'half_open':
            breaker_status = 'warn'
        else:
            breaker_status = 'ok'
        services.append({
            'key': f"provider:{breaker['provider']}",
            'label': f"Proveedor · {breaker['provider']}",
            'status': breaker_status,
            'detail': f"breaker {state}",
        })
    return services
