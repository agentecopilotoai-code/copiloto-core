"""TASK-0060 — Métricas Prometheus para observabilidad operativa.

Expone los counters/histograms/gauges que necesita Prometheus para construir
dashboards y disparar alertas. Nada de PII (sin `phone_e164`, sin contenidos
de mensajes); solo IDs y agregados.

Las funciones `record_*` son la API pública del módulo: el resto del código
las llama con los parámetros del dominio y este archivo decide cómo se
materializan en métricas.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

import structlog
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

if TYPE_CHECKING:  # pragma: no cover - solo para anotaciones de tipo
    import asyncpg

log = structlog.get_logger()

# Latency buckets en segundos: 0.5, 1, 2, 5, 10 + +Inf (default tail).
_LATENCY_BUCKETS = (0.5, 1.0, 2.0, 5.0, 10.0)


REGISTRY = CollectorRegistry(auto_describe=True)


messages_total = Counter(
    'cpi_messages_total',
    'Total de mensajes procesados (inbound + outbound).',
    labelnames=('tenant_id', 'direction', 'channel', 'status'),
    registry=REGISTRY,
)

response_latency_seconds = Histogram(
    'cpi_response_latency_seconds',
    'Latencia del bot al responder un mensaje, segmentado por tier del cascade.',
    labelnames=('tenant_id', 'tier'),
    buckets=_LATENCY_BUCKETS,
    registry=REGISTRY,
)

llm_calls_total = Counter(
    'cpi_llm_calls_total',
    'Llamadas al LLM (cloud o local), por proveedor y resultado.',
    labelnames=('provider', 'status'),
    registry=REGISTRY,
)

appointments_total = Counter(
    'cpi_appointments_total',
    'Citas creadas/canceladas/completadas/no_show, por tenant y status.',
    labelnames=('tenant_id', 'status'),
    registry=REGISTRY,
)

handoff_total = Counter(
    'cpi_handoff_total',
    'Cantidad de handoffs disparados al equipo humano, por motivo.',
    labelnames=('tenant_id', 'reason'),
    registry=REGISTRY,
)

circuit_breaker_state = Gauge(
    'cpi_circuit_breaker_state',
    'Estado del circuit breaker: 0=closed, 1=half_open, 2=open.',
    labelnames=('provider',),
    registry=REGISTRY,
)

worker_queue_depth = Gauge(
    'cpi_worker_queue_depth',
    'Tamaño de la cola pendiente por worker (eventos sin procesar).',
    labelnames=('worker',),
    registry=REGISTRY,
)

# AUDIT-51 / round-3 §1.3+§1.10 (2026-05-18): observabilidad del WS fanout
# y del rate limiter LRU. Sin esto, el operador no detecta degradación
# hasta que un cliente reporta lag (fanout) o hasta que la memoria del
# worker estalla (rate_limit). Ambos son gauges instantáneos seteados
# antes de cada scrape via `refresh_runtime_metrics()`.
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
rate_limit_buckets_current = Gauge(
    'cpi_rate_limit_buckets_current',
    'Buckets vivos en el rate limiter LRU (cuán cerca está del cap '
    '`rate_limit_bucket_max_entries`).',
    registry=REGISTRY,
)
rate_limit_buckets_evicted_total = Counter(
    'cpi_rate_limit_buckets_evicted_total',
    'Buckets evictados del rate limiter LRU por TTL o por cap.',
    labelnames=('reason',),
    registry=REGISTRY,
)

# TASK-0065: contador de mensajes outbound que terminaron en la dead-letter
# queue (status='failed' después de agotar reintentos del event_worker). El
# `error_code` se normaliza al código devuelto por Meta o ``transport_error``
# cuando el fallo fue de red. Permite alertar sobre crecimiento sostenido
# (regla ``OutboundDLQGrowing`` en ``infra/observability/alerts.yaml``).
outbound_dlq_total = Counter(
    'cpi_outbound_dlq_total',
    'Mensajes outbound que terminaron en la DLQ (fail definitivo), por tenant y error_code.',
    labelnames=('tenant_id', 'error_code'),
    registry=REGISTRY,
)

# BUG-047: gauges que alimentan las reglas `BackupCloudStale` y
# `BackupVerifyFailed` declaradas en `infra/observability/alerts.yaml`.
# Sin esta instrumentación, las expresiones `max(cpi_backup_last_*) ...`
# devolvían vacío y las alertas nunca paginaban — backups stale silentes.
# El valor es la edad EN SEGUNDOS del último evento relevante (calculada
# en `refresh_backup_age_metrics` por scrape — el endpoint /metrics la
# llama antes de `render_latest`).
backup_last_success_age_seconds = Gauge(
    'cpi_backup_last_success_age_seconds',
    'Segundos transcurridos desde el último backup exitoso por kind '
    '(cloud_dump / cloud_verify). Si no hay ninguno aún, no se setea.',
    labelnames=('kind',),
    registry=REGISTRY,
)

# BUG-176 (codex P1 sobre BUG-047): cuando este Gauge era UNLABELED,
# `prometheus_client` lo exportaba con valor 0 desde el import del módulo
# — `BackupVerifyFailed: max(...) < 86400` matcheaba 0 < 86400 = TRUE
# y disparaba false-positive en greenfield/healthy deployments aunque
# `refresh_backup_age_metrics` nunca encontrara una fila failed.
# Fix: convertir a Gauge labeled (`scope='cloud_verify'`). Un labeled
# Gauge SIN child no se exporta — la serie queda absent hasta que
# observamos una falla real (`.labels(scope='cloud_verify').set(...)`).
# La alerta entonces queda vacía y no dispara hasta que aparece la
# primera failure.
backup_last_verify_failed_age_seconds = Gauge(
    'cpi_backup_last_verify_failed_age_seconds',
    'Segundos transcurridos desde el último `cloud_verify` que terminó en '
    'status=failed. Labeled por `scope` para que la serie sea ABSENT '
    'hasta que se observe la primera failure real — sin esto, un Gauge '
    'unlabeled exporta 0 por default y `BackupVerifyFailed` (< 86400) '
    'dispara false-positive en greenfield. Sólo se setea cuando el '
    'refresh encuentra una fila `kind=cloud_verify status=failed`.',
    labelnames=('scope',),
    registry=REGISTRY,
)


def refresh_runtime_metrics() -> None:
    """AUDIT-51 (2026-05-18): refresca los gauges runtime no-DB antes de cada
    scrape de /metrics. Importa los módulos lazy para evitar ciclos de import
    (`ws_fanout` y `rate_limit` viven en `app.admin` y `app.services`).

    Sin esto, los gauges quedan en 0 hasta que algo los setea — útil para
    detectar overload del fanout (subscribers acumulándose, dispatcher
    drop rate) y del rate limiter (cap del LRU acercándose).
    """
    try:
        from app.admin.ws_fanout import fanout as _ws_fanout  # noqa: PLC0415
        ws_fanout_subscriber_count.set(float(_ws_fanout.subscriber_count))
        ws_fanout_tenant_count.set(float(_ws_fanout.tenant_count))
    except Exception:  # noqa: BLE001 - best-effort scrape
        pass
    try:
        # Importar de un singleton requiere acceso al limiter activo —
        # registrarlo se hace una vez en `app.main:create_app` (ver
        # `_set_active_rate_limiter`). Si no está seteado (worker, etc.),
        # el gauge queda en el último valor conocido o 0.
        limiter = _active_rate_limiter
        if limiter is not None:
            rate_limit_buckets_current.set(float(limiter.size))
    except Exception:  # noqa: BLE001
        pass


# Singleton registry for the rate limiter — set by `app.main:create_app`
# so `refresh_runtime_metrics` can pull `.size` without circular imports.
_active_rate_limiter = None


def _set_active_rate_limiter(limiter) -> None:
    global _active_rate_limiter
    _active_rate_limiter = limiter


async def refresh_backup_age_metrics(conn: 'asyncpg.Connection') -> None:
    """Recalcula los gauges de backup desde `app.backup_runs`.

    Se invoca antes de cada `render_latest()` del endpoint /metrics. Es
    barata: dos queries con LIMIT 1 sobre el índice
    `ix_backup_runs_kind_status`. Best-effort: si la DB no está
    disponible (worker arrancando, conn caída) loguea y sigue — el
    scrape devuelve los últimos valores conocidos en memoria.
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
            # BUG-176: usar `.labels(scope='cloud_verify')` para crear el child;
            # sin observación de failure, la serie queda absent y la alerta
            # `BackupVerifyFailed` no dispara falso positivo.
            backup_last_verify_failed_age_seconds.labels(scope='cloud_verify').set(
                float(failed_age)
            )
    except Exception:  # noqa: BLE001
        log.exception('metrics.refresh_backup_age_failed')


_VALID_DIRECTIONS = frozenset({'inbound', 'outbound'})
_VALID_MESSAGE_STATUSES = frozenset(
    {'accepted', 'queued', 'sent', 'delivered', 'failed', 'rejected'}
)
_VALID_LLM_STATUSES = frozenset({'success', 'error', 'rejected', 'timeout'})
_VALID_APPOINTMENT_STATUSES = frozenset(
    {'created', 'confirmed', 'cancelled', 'completed', 'no_show', 'rescheduled'}
)
_CB_STATE_VALUES = {'closed': 0, 'half_open': 1, 'open': 2}

# Bucket conocidos para `cpi_handoff_total{reason}`. Cualquier texto libre
# que envíen operadores u clientes cae a `other` para evitar explosión de
# cardinalidad en Prometheus.
_HANDOFF_REASONS = frozenset({
    'manual',
    'manual_or_policy_handoff',
    'policy',
    'risk_keyword',
    'max_turns',
    'outside_window_24h',
    'knowledge_context_insufficient',
    'llm_no_information',
    'llm_unavailable',
    'waiting_agent_handoff_pending',
    'negative_feedback',
    'complaint',
    'vip_routing',
    'urgent_triage',
    'unspecified',
})


def normalize_handoff_reason(reason: object) -> str:
    """Mapea texto libre de motivo de handoff a un enum acotado.

    Prometheus crea una serie por valor distinto de label; sin esta
    normalización el endpoint manual de handoff (`POST .../handoff`) podría
    crear series ilimitadas con cada mensaje libre que envíe el operador.
    """
    if reason is None:
        return 'unspecified'
    token = str(reason).strip().lower().replace(' ', '_')
    if not token:
        return 'unspecified'
    if token in _HANDOFF_REASONS:
        return token
    return 'other'


def _safe_tenant(tenant_id: object) -> str:
    if tenant_id is None:
        return 'unknown'
    return str(tenant_id)


def record_message(
    *,
    tenant_id: object,
    direction: str,
    channel: str,
    status: str,
) -> None:
    """Incrementa cpi_messages_total. Acepta sólo direcciones/estados conocidos."""
    if direction not in _VALID_DIRECTIONS:
        return
    if status not in _VALID_MESSAGE_STATUSES:
        return
    messages_total.labels(
        tenant_id=_safe_tenant(tenant_id),
        direction=direction,
        channel=channel or 'unknown',
        status=status,
    ).inc()


def observe_response_latency(*, tenant_id: object, tier: str, seconds: float) -> None:
    """Observa latencia de respuesta del bot. `tier` ∈ {template, local_llm, cloud_llm, handoff}."""
    if seconds < 0:
        return
    response_latency_seconds.labels(
        tenant_id=_safe_tenant(tenant_id),
        tier=tier or 'unknown',
    ).observe(seconds)


def record_llm_call(*, provider: str, status: str) -> None:
    if status not in _VALID_LLM_STATUSES:
        return
    llm_calls_total.labels(provider=provider or 'unknown', status=status).inc()


def record_appointment(*, tenant_id: object, status: str) -> None:
    if status not in _VALID_APPOINTMENT_STATUSES:
        return
    appointments_total.labels(tenant_id=_safe_tenant(tenant_id), status=status).inc()


def record_handoff(*, tenant_id: object, reason: object) -> None:
    handoff_total.labels(
        tenant_id=_safe_tenant(tenant_id),
        reason=normalize_handoff_reason(reason),
    ).inc()


def set_circuit_breaker_state(*, provider: str, state: str) -> None:
    value = _CB_STATE_VALUES.get(state)
    if value is None:
        return
    circuit_breaker_state.labels(provider=provider or 'unknown').set(value)


def set_worker_queue_depth(*, worker: str, depth: int) -> None:
    if depth < 0:
        return
    worker_queue_depth.labels(worker=worker or 'unknown').set(depth)


def record_outbound_dlq(*, tenant_id: object, error_code: object) -> None:
    """Incrementa ``cpi_outbound_dlq_total`` cuando un mensaje cae en la DLQ.

    Llamado por ``event_worker`` al marcar un envío como ``failed`` de forma
    definitiva. ``error_code`` se normaliza a cadena no vacía; cuando es
    ``None`` o ``''`` se usa ``transport_error`` para distinguir un fallo de
    red de un error de Meta con código numérico.
    """
    code = str(error_code).strip() if error_code is not None else ''
    outbound_dlq_total.labels(
        tenant_id=_safe_tenant(tenant_id),
        error_code=code or 'transport_error',
    ).inc()


_CB_STATE_LABELS = {0: 'closed', 1: 'half_open', 2: 'open'}


def _le_value(le: str) -> float:
    """Convierte el label `le` de un bucket de histograma a float (`+Inf` → inf)."""
    if le in ('+Inf', 'Inf'):
        return float('inf')
    try:
        return float(le)
    except (TypeError, ValueError):
        return float('inf')


def _histogram_quantile(buckets: list[tuple[float, float]], quantile: float) -> float | None:
    """Cuantil por interpolación lineal sobre buckets acumulativos de histograma.

    `buckets` es una lista ordenada `(upper_bound, cumulative_count)` que incluye
    el bucket `+Inf`. Reproduce de cerca el `histogram_quantile` de Prometheus,
    suficiente para un snapshot puntual (no es la SLA — esa vive en Prometheus).
    """
    if not buckets:
        return None
    total = buckets[-1][1]
    if total <= 0:
        return None
    rank = quantile * total
    prev_bound = 0.0
    prev_count = 0.0
    for upper, cum in buckets:
        if cum >= rank:
            if upper == float('inf'):
                return prev_bound or None
            if cum == prev_count:
                return upper
            ratio = (rank - prev_count) / (cum - prev_count)
            return prev_bound + (upper - prev_bound) * ratio
        if upper != float('inf'):
            prev_bound = upper
        prev_count = cum
    return prev_bound or None


def collect_health_snapshot() -> dict:
    """Materializa el registry Prometheus in-process en un snapshot estructurado.

    Alimenta la vista de Platform Owner "System Health" (UI-006.2). Lee el MISMO
    `REGISTRY` que Prometheus raspa desde `/metrics`, así que los números son
    consistentes con el pipeline de alertas de TASK-0060.

    Es un snapshot puntual: las series históricas (24h/7d/30d) requieren la query
    API de Prometheus y quedan fuera de alcance aquí (ver `docs/UI_BACKLOG.md`,
    UI-006.2). No expone PII — solo agregados e IDs de proveedor/worker.
    """
    messages: dict[tuple[str, str], float] = {}
    llm: dict[str, float] = {}
    dlq_total = 0.0
    dlq_by_code: dict[str, float] = {}
    breakers: dict[str, float] = {}
    workers: dict[str, float] = {}
    latency_buckets: dict[str, float] = {}
    latency_sum = 0.0
    latency_count = 0.0

    for metric in REGISTRY.collect():
        for sample in metric.samples:
            name = sample.name
            labels = sample.labels
            value = sample.value
            if name == 'cpi_messages_total':
                key = (labels.get('direction', 'unknown'), labels.get('status', 'unknown'))
                messages[key] = messages.get(key, 0.0) + value
            elif name == 'cpi_llm_calls_total':
                status = labels.get('status', 'unknown')
                llm[status] = llm.get(status, 0.0) + value
            elif name == 'cpi_outbound_dlq_total':
                dlq_total += value
                code = labels.get('error_code', 'unknown')
                dlq_by_code[code] = dlq_by_code.get(code, 0.0) + value
            elif name == 'cpi_circuit_breaker_state':
                breakers[labels.get('provider', 'unknown')] = value
            elif name == 'cpi_worker_queue_depth':
                workers[labels.get('worker', 'unknown')] = value
            elif name == 'cpi_response_latency_seconds_bucket':
                le = labels.get('le', '+Inf')
                latency_buckets[le] = latency_buckets.get(le, 0.0) + value
            elif name == 'cpi_response_latency_seconds_sum':
                latency_sum += value
            elif name == 'cpi_response_latency_seconds_count':
                latency_count += value

    cumulative = sorted(
        ((_le_value(le), count) for le, count in latency_buckets.items()),
        key=lambda kv: kv[0],
    )

    inbound = sum(v for (direction, _s), v in messages.items() if direction == 'inbound')
    outbound = sum(v for (direction, _s), v in messages.items() if direction == 'outbound')
    # BUG-122: `rejected` (mensajes rechazados deliberadamente — ventana
    # expirada, opt-out, validación de plantilla fallida) NO es lo mismo que
    # `failed` (error transitorio / rate-limit / 5xx). Antes los bundleabamos
    # → `outbound_error_rate` inflado, alertas falsas de `HighOutboundErrorRate`.
    # Ahora contamos `failed` solo y exponemos `rejected` aparte para visibilidad.
    outbound_failed = sum(
        v for (direction, status), v in messages.items()
        if direction == 'outbound' and status == 'failed'
    )
    outbound_rejected = sum(
        v for (direction, status), v in messages.items()
        if direction == 'outbound' and status == 'rejected'
    )

    llm_total = sum(llm.values())
    llm_success = llm.get('success', 0.0)

    return {
        'messages': {
            'inbound': int(inbound),
            'outbound': int(outbound),
            'outbound_failed': int(outbound_failed),
            # BUG-122: rejected expuesto aparte. `outbound_error_rate` ya no
            # los cuenta; el operator igual los ve para diagnóstico de opt-out
            # / templates rechazadas, sin paginar al on-call.
            'outbound_rejected': int(outbound_rejected),
            'outbound_error_rate': (outbound_failed / outbound) if outbound else 0.0,
        },
        'response_latency': {
            'p50': _histogram_quantile(cumulative, 0.50),
            'p95': _histogram_quantile(cumulative, 0.95),
            'p99': _histogram_quantile(cumulative, 0.99),
            'count': int(latency_count),
            'avg': (latency_sum / latency_count) if latency_count else None,
        },
        'llm_calls': {
            'total': int(llm_total),
            'success': int(llm_success),
            'success_rate': (llm_success / llm_total) if llm_total else None,
            'by_status': {k: int(v) for k, v in sorted(llm.items())},
        },
        'circuit_breakers': [
            {
                'provider': provider,
                'state': _CB_STATE_LABELS.get(int(value), 'unknown'),
                'state_value': int(value),
            }
            for provider, value in sorted(breakers.items())
        ],
        'workers': [
            {'worker': worker, 'queue_depth': int(value)}
            for worker, value in sorted(workers.items())
        ],
        'outbound_dlq': {
            'total': int(dlq_total),
            'by_error_code': {k: int(v) for k, v in sorted(dlq_by_code.items())},
        },
    }


def evaluate_health_alerts(snapshot: dict) -> list[dict]:
    """Deriva alertas activas puntuales desde el snapshot de salud.

    Los umbrales reproducen `infra/observability/alerts.yaml`, pero se evalúan
    contra el snapshot puntual — NO contra una ventana `rate()[5m]`. Es una
    aproximación para mostrar estado obviamente degradado en la UI; la SLA real
    de alertas vive en Prometheus + Alertmanager (TASK-0060).
    """
    alerts: list[dict] = []

    latency_p95 = snapshot['response_latency']['p95']
    if latency_p95 is not None and latency_p95 > 5.0:
        alerts.append({
            'name': 'BotResponseLatencyP95High',
            'severity': 'page',
            'summary': 'Latencia P95 del bot > 5s sostenida.',
            'runbook_url': 'docs/runbooks/postgres-down.md',
        })

    error_rate = snapshot['messages']['outbound_error_rate']
    if error_rate > 0.05:
        alerts.append({
            'name': 'HighOutboundErrorRate',
            'severity': 'page',
            'summary': 'Más del 5% de mensajes outbound están fallando.',
            'runbook_url': 'docs/runbooks/rate-limit-meta-hit.md',
        })

    for worker in snapshot['workers']:
        queue_depth = worker['queue_depth']
        if queue_depth > 1000:
            alerts.append({
                'name': 'WorkerQueueBacklog',
                'severity': 'page',
                'summary': f"Cola del worker {worker['worker']} > 1000 elementos.",
                'runbook_url': 'docs/runbooks/worker-queue-backlog.md',
            })
        elif queue_depth > 100:
            # BUG-121: alerta warning intermedia. Antes solo paginábamos al
            # cruzar 1000; el rango 101-1000 quedaba silente aunque indica
            # que el scheduler está atrasado y la SLO de delivery se va a
            # romper si no se atiende. Severidad `warning` → notificación
            # pero no page del on-call.
            alerts.append({
                'name': 'SchedulerBehind',
                'severity': 'warning',
                'summary': (
                    f"Cola del worker {worker['worker']} entre 101 y 1000 "
                    f"elementos ({int(queue_depth)}) — scheduler atrasado."
                ),
                'runbook_url': 'docs/runbooks/worker-queue-backlog.md',
            })

    for breaker in snapshot['circuit_breakers']:
        if breaker['state_value'] >= 2:
            alerts.append({
                'name': 'CircuitBreakerOpenSustained',
                'severity': 'page',
                'summary': f"Circuit breaker {breaker['provider']} OPEN.",
                'runbook_url': 'docs/runbooks/circuit-breaker-open-sustained.md',
            })

    return alerts


def render_latest() -> tuple[bytes, str]:
    """Devuelve (payload, content_type) listo para servir desde el endpoint /metrics."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


def start_metrics_http_server(port: int, addr: str = '0.0.0.0') -> None:
    """Levanta un endpoint /metrics standalone para procesos sin FastAPI.

    Los workers (event_worker, scheduler) corren en procesos separados con
    su propio `REGISTRY` en memoria; sin este servidor las métricas que
    actualizan nunca llegarían al scraper de Prometheus. Se llama una sola
    vez al arrancar cada worker.
    """
    from prometheus_client import start_http_server  # noqa: PLC0415

    start_http_server(port, addr=addr, registry=REGISTRY)


def parse_ip_allowlist(raw: str | None) -> frozenset[str]:
    """Convierte la env var `OBSERVABILITY_ALLOWED_IPS` (CSV) en un set inmutable.

    Cualquier blanco/None significa "vacío"; el handler tratará vacío como
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


# ─── Influencer module metrics — TASK-INFLU-018 ────────────────────────────


influencer_generations_total = Counter(
    'influencer_generations_total',
    'Total de generaciones encoladas/completadas en el módulo Ravit Studio.',
    ['kind', 'status', 'provider'],
)


influencer_generation_duration_seconds = Histogram(
    'influencer_generation_duration_seconds',
    'Latencia end-to-end de una generación (encolar → succeeded/failed).',
    ['kind', 'provider'],
    buckets=(0.5, 1, 2, 5, 10, 20, 30, 60, 120, 300, 600),
)


influencer_credits_balance = Gauge(
    'influencer_credits_balance',
    'Balance de créditos del tenant (actualizado en cada debit/credit).',
    ['tenant_id'],
)


influencer_posts_published_total = Counter(
    'influencer_posts_published_total',
    'Posts intentados/publicados en cada platform.',
    ['platform', 'status'],
)


influencer_provider_health = Gauge(
    'influencer_provider_health',
    'Salud del provider (1 = healthy, 0 = degraded/circuit-open).',
    ['provider', 'modality'],
)
