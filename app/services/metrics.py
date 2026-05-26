"""Métricas Prometheus del core.

Solo expone:
  - Gauges runtime no-DB (WS fanout subscribers/tenants, rate limiter LRU
    size). Refrescados por scrape via `refresh_runtime_metrics()`.
  - Gauges de backup desde `app.backup_runs`. Refrescados por scrape via
    `refresh_backup_age_metrics()`.
  - Counters de drops (rate limiter, ws_fanout) consumidos directamente
    desde sus módulos source.
  - Health metric transversal de los proveedores IA del core.
  - Helpers para servir /metrics (`render_latest`, `parse_ip_allowlist`,
    `ip_allowed`).

Pre-purga este módulo tenía ~660 LOC con counters/histograms del chatbot
(`cpi_messages_total`, `cpi_response_latency_seconds`, `cpi_handoff_total`,
`cpi_appointments_total`, etc.) + collect_health_snapshot + evaluate_health_alerts
+ start_metrics_http_server (workers borrados). Todo eso se quitó porque no
tenía un solo caller en el core (M6 de la auditoría). Cuando un módulo
opt-in necesite sus propias métricas, las define en su propio archivo
referenciando este `REGISTRY` global.

Nada de PII (sin `phone_e164`, sin contenidos de mensajes); solo IDs y
agregados.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

import structlog
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    generate_latest,
)

if TYPE_CHECKING:  # pragma: no cover
    import asyncpg

log = structlog.get_logger()

REGISTRY = CollectorRegistry(auto_describe=True)


# ─── WS fanout (consumido desde app.admin.ws_fanout) ──────────────────────

ws_fanout_subscriber_count = Gauge(
    'cpi_ws_fanout_subscriber_count',
    'Subscribers actuales del WebSocket fanout (suma cross-tenant).',
    registry=REGISTRY,
)
ws_fanout_tenant_count = Gauge(
    'cpi_ws_fanout_tenant_count',
    'Tenants activos con al menos un subscriber en el WebSocket fanout.',
    registry=REGISTRY,
)
ws_fanout_dropped_total = Counter(
    'cpi_ws_fanout_dropped_total',
    'Mensajes droppeados por el fanout dispatcher (queue full o JSON invalido).',
    labelnames=('reason',),
    registry=REGISTRY,
)
ws_fanout_supervisor_crashes_total = Counter(
    'cpi_ws_fanout_supervisor_crashes_total',
    'Cuántas veces el supervisor del fanout crasheó (LISTEN/NOTIFY setup fail).',
    registry=REGISTRY,
)


# ─── Rate limiter LRU (consumido desde app.services.rate_limit) ───────────

rate_limit_buckets_current = Gauge(
    'cpi_rate_limit_buckets_current',
    'Buckets vivos en el rate limiter LRU.',
    registry=REGISTRY,
)
rate_limit_buckets_evicted_total = Counter(
    'cpi_rate_limit_buckets_evicted_total',
    'Buckets evictados del rate limiter LRU por TTL o por cap.',
    labelnames=('reason',),
    registry=REGISTRY,
)


# ─── Backup pipeline (consumido desde app.main:/metrics handler) ──────────
# BUG-047/176: `BackupCloudStale` + `BackupVerifyFailed` (alerts.yaml)
# leen estos gauges. Labeled `scope` evita false-positive en greenfield
# (un Gauge unlabeled exporta 0 → la regla `< 86400` matcheaba siempre).

backup_last_success_age_seconds = Gauge(
    'cpi_backup_last_success_age_seconds',
    'Segundos transcurridos desde el último backup exitoso por kind.',
    labelnames=('kind',),
    registry=REGISTRY,
)
backup_last_verify_failed_age_seconds = Gauge(
    'cpi_backup_last_verify_failed_age_seconds',
    'Segundos transcurridos desde el último cloud_verify status=failed. '
    'Labeled por `scope` para que la serie sea ABSENT hasta que haya un '
    'failure real.',
    labelnames=('scope',),
    registry=REGISTRY,
)


# ─── AI provider health (transversal del core) ────────────────────────────

ai_provider_health = Gauge(
    'ai_provider_health',
    'Salud del provider IA (1 = healthy, 0 = degraded/circuit-open).',
    labelnames=('provider', 'modality'),
    registry=REGISTRY,
)


# ─── Runtime refresh hooks ────────────────────────────────────────────────

_active_rate_limiter = None


def _set_active_rate_limiter(limiter) -> None:
    """Llamar UNA vez al startup desde `app.main:create_app` para que
    `refresh_runtime_metrics()` pueda leer `.size` sin import circular."""
    global _active_rate_limiter
    _active_rate_limiter = limiter


def refresh_runtime_metrics() -> None:
    """Refresca gauges runtime no-DB antes de cada scrape de /metrics.

    Best-effort: cualquier excepción (módulo no cargado, ws_fanout aún no
    inicializado) se traga; el scrape devuelve los últimos valores
    conocidos en memoria.
    """
    try:
        from app.admin.ws_fanout import fanout as _ws_fanout  # noqa: PLC0415
        ws_fanout_subscriber_count.set(float(_ws_fanout.subscriber_count))
        ws_fanout_tenant_count.set(float(_ws_fanout.tenant_count))
    except Exception:  # noqa: BLE001
        pass
    try:
        if _active_rate_limiter is not None:
            rate_limit_buckets_current.set(float(_active_rate_limiter.size))
    except Exception:  # noqa: BLE001
        pass


async def refresh_backup_age_metrics(conn: 'asyncpg.Connection') -> None:
    """Recalcula los gauges de backup desde `app.backup_runs`.

    Se invoca antes de cada `render_latest()` del endpoint /metrics. Es
    barata: dos queries con LIMIT 1 sobre `ix_backup_runs_kind_status_finished`.
    Best-effort: si la DB no está disponible, loguea y sigue.
    """
    try:
        rows = await conn.fetch(
            """
            select kind,
                   extract(epoch from now() - max(finished_at))::float as age
            from app.backup_runs
            where status = 'ok' and finished_at is not null
              and kind in ('cloud_dump', 'cloud_verify')
            group by kind
            """
        )
        for row in rows:
            if row['age'] is None:
                continue
            backup_last_success_age_seconds.labels(kind=row['kind']).set(
                float(row['age'])
            )
        failed_age = await conn.fetchval(
            """
            select extract(epoch from now() - max(finished_at))::float
            from app.backup_runs
            where kind = 'cloud_verify'
              and status = 'failed'
              and finished_at is not null
            """
        )
        if failed_age is not None:
            backup_last_verify_failed_age_seconds.labels(scope='cloud_verify').set(
                float(failed_age)
            )
    except Exception:  # noqa: BLE001
        log.exception('metrics.refresh_backup_age_failed')


# ─── Serving /metrics ─────────────────────────────────────────────────────


def render_latest() -> tuple[bytes, str]:
    """(payload, content_type) listo para servir desde el endpoint /metrics."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def parse_ip_allowlist(raw: str | None) -> frozenset[str]:
    """Convierte la env var `OBSERVABILITY_ALLOWED_IPS` (CSV) en un set inmutable.

    Cualquier blanco/None significa "vacío"; el handler trata vacío como
    "denegar todo" (la métrica solo debe exponerse a redes confiables).
    """
    if not raw:
        return frozenset()
    return frozenset(token.strip() for token in raw.split(',') if token.strip())


def ip_allowed(client_ip: str | None, allowlist: Iterable[str]) -> bool:
    """True si `client_ip` está en `allowlist`. No soporta CIDR — exact match.

    El operador debe listar las IPs de los Prometheus scrapers explícitamente.
    """
    if not client_ip:
        return False
    allowset = allowlist if isinstance(allowlist, (set, frozenset)) else frozenset(allowlist)
    return client_ip in allowset
