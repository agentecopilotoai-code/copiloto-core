"""TASK-0060 — Métricas Prometheus para observabilidad operativa.

Expone los counters/histograms/gauges que necesita Prometheus para construir
dashboards y disparar alertas. Nada de PII (sin `phone_e164`, sin contenidos
de mensajes); solo IDs y agregados.

Las funciones `record_*` son la API pública del módulo: el resto del código
las llama con los parámetros del dominio y este archivo decide cómo se
materializan en métricas.
"""

from __future__ import annotations

from typing import Iterable

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

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


_VALID_DIRECTIONS = frozenset({'inbound', 'outbound'})
_VALID_MESSAGE_STATUSES = frozenset(
    {'accepted', 'queued', 'sent', 'delivered', 'failed', 'rejected'}
)
_VALID_LLM_STATUSES = frozenset({'success', 'error', 'rejected', 'timeout'})
_VALID_APPOINTMENT_STATUSES = frozenset(
    {'created', 'confirmed', 'cancelled', 'completed', 'no_show', 'rescheduled'}
)
_CB_STATE_VALUES = {'closed': 0, 'half_open': 1, 'open': 2}


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


def record_handoff(*, tenant_id: object, reason: str) -> None:
    handoff_total.labels(
        tenant_id=_safe_tenant(tenant_id),
        reason=reason or 'unspecified',
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


def render_latest() -> tuple[bytes, str]:
    """Devuelve (payload, content_type) listo para servir desde el endpoint /metrics."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


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
