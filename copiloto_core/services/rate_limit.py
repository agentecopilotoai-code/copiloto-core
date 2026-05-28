"""Rate limiting con token bucket en memoria.

Diseñado para FastAPI: el middleware se registra en `copiloto_core.main.create_app()` y
aplica un bucket por IP (y por tenant_id cuando viene en el path).

Para webhooks de Meta usamos un cap más permisivo porque Meta hace retries
agresivos y queremos absorber bursts legítimos sin devolver 429.

El bucket en memoria es válido para una sola instancia; si se escala
horizontalmente hay que mover el estado a Redis.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field

import structlog

from copiloto_core.core.config import get_settings

log = structlog.get_logger()

WEBHOOK_PREFIX = '/webhooks/'
# Extrae tenant_id del path si viene presente.
_TENANT_PATH_RE = re.compile(
    r'/(?:v1|webhooks)/(?:tenants/)?'
    r'(?P<tenant>[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})'
)


@dataclass
class TokenBucket:
    capacity: float
    refill_per_second: float
    tokens: float = field(default=0.0)
    last_refill: float = field(default_factory=time.monotonic)

    def __post_init__(self) -> None:
        if self.tokens == 0.0:
            self.tokens = float(self.capacity)

    def consume(self, amount: float = 1.0) -> tuple[bool, float]:
        """Intenta consumir tokens. Devuelve (allowed, retry_after_seconds)."""
        now = time.monotonic()
        elapsed = max(0.0, now - self.last_refill)
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
        self.last_refill = now
        if self.tokens >= amount:
            self.tokens -= amount
            return True, 0.0
        deficit = amount - self.tokens
        retry_after = deficit / self.refill_per_second if self.refill_per_second > 0 else 60.0
        return False, retry_after


class RateLimiter:
    """Registry de buckets por clave + factory por scope (webhook vs default).

    AUDIT-46 (speed quick win #2, 2026-05-18): buckets ahora viven en un
    ``OrderedDict`` con cap (``max_entries``) y expiración por inactividad
    (``ttl_seconds``). Sin esto, el dict crecía sin tope: cada IP nueva (o
    rotación de NAT/IPv6 dirigida) creaba un bucket que NUNCA se liberaba.
    BUG-219 cerró el spoofing trivial via XFF; el crecimiento ilimitado por
    fuentes legítimas seguía abierto. El cap es defensa-en-profundidad
    (límite duro de memoria) y el TTL recupera memoria de tráfico
    transitorio. Política de eviction:
      1. Si una key expiró por ``ttl_seconds`` (no se usa hace TTL+), se
         purga al próximo ``check()``.
      2. Si tras insertar excedemos ``max_entries``, hacemos LRU pop
         (``OrderedDict.popitem(last=False)``) hasta volver al cap.
    """

    def __init__(
        self,
        *,
        default_per_minute: int,
        webhook_per_minute: int,
        max_entries: int = 10_000,
        ttl_seconds: int = 900,
    ) -> None:
        if default_per_minute <= 0:
            raise ValueError('default_per_minute must be > 0')
        if webhook_per_minute <= 0:
            raise ValueError('webhook_per_minute must be > 0')
        if max_entries <= 0:
            raise ValueError('max_entries must be > 0')
        if ttl_seconds <= 0:
            raise ValueError('ttl_seconds must be > 0')
        self.default_per_minute = default_per_minute
        self.webhook_per_minute = webhook_per_minute
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        # OrderedDict para LRU: la key más-recientemente-usada va al final
        # (move_to_end), la menos-recientemente-usada al inicio (popitem(last=False)).
        self._buckets: 'OrderedDict[str, TokenBucket]' = OrderedDict()
        self._lock = asyncio.Lock()

    def build_bucket(self, *, scope: str) -> TokenBucket:
        if scope == 'webhook':
            return TokenBucket(
                capacity=float(self.webhook_per_minute),
                refill_per_second=self.webhook_per_minute / 60.0,
            )
        return TokenBucket(
            capacity=float(self.default_per_minute),
            refill_per_second=self.default_per_minute / 60.0,
        )

    @property
    def size(self) -> int:
        return len(self._buckets)

    def _is_expired(self, bucket: TokenBucket, now: float) -> bool:
        return (now - bucket.last_refill) > self.ttl_seconds

    async def check(self, key: str, *, scope: str) -> tuple[bool, float]:
        # AUDIT-51: counter Prometheus de evictions por causa (ttl/cap).
        # Lazy import para evitar ciclo con `copiloto_core.services.metrics` (que
        # importa `copiloto_core.admin.ws_fanout` que NO importa rate_limit).
        try:
            from copiloto_core.services.metrics import rate_limit_buckets_evicted_total  # noqa: PLC0415
        except Exception:  # noqa: BLE001
            rate_limit_buckets_evicted_total = None  # noqa: N806
        async with self._lock:
            now = time.monotonic()
            bucket = self._buckets.get(key)
            if bucket is not None and self._is_expired(bucket, now):
                # Key fría: descartar y crear nueva (estado lleno).
                del self._buckets[key]
                bucket = None
                if rate_limit_buckets_evicted_total is not None:
                    rate_limit_buckets_evicted_total.labels(reason='ttl').inc()
            if bucket is None:
                bucket = self.build_bucket(scope=scope)
                self._buckets[key] = bucket
            else:
                # Touch para LRU (mueve al final).
                self._buckets.move_to_end(key)
            # Cap defensivo (post-insert): pop oldest hasta cumplir.
            while len(self._buckets) > self.max_entries:
                self._buckets.popitem(last=False)
                if rate_limit_buckets_evicted_total is not None:
                    rate_limit_buckets_evicted_total.labels(reason='cap').inc()
            return bucket.consume(1.0)


def classify_scope(path: str) -> str:
    if path.startswith(WEBHOOK_PREFIX):
        return 'webhook'
    return 'default'


def build_rate_limit_key(*, client_ip: str, path: str) -> str:
    """Construye la clave del bucket: ip + tenant_id si está en el path."""
    match = _TENANT_PATH_RE.search(path)
    if match:
        return f'{client_ip}:{match.group("tenant")}'
    return f'{client_ip}:-'


def extract_client_ip(request) -> str:
    """Extract client IP — ignores X-Forwarded-For when not from a trusted proxy.

    BUG-219 (codex MEDIUM, 2026-05-18): la versión anterior leía X-Forwarded-For
    UNCONDICIONALLY como source-of-truth para el rate limit key. Un atacante
    podía rotar el header en cada request (`X-Forwarded-For: 1.2.3.4` →
    `1.2.3.5` → ...) y cada valor forjado producía una key distinta —
    cada request abría un nuevo bucket con burst limit full. Bypass total
    del rate limiter contra endpoints públicos (webhooks, etc.).

    Además: el `_buckets` dict no tenía eviction; el atacante podía
    saturar memoria del worker con millones de fake-IP buckets.

    Fix: solo aceptar XFF cuando settings.trust_proxy_forwarded_for esté
    seteado (deploy-time toggle requiriendo que el operador confirme que
    hay un reverse proxy delante que SOBREESCRIBE el header). En caso
    contrario, usar SIEMPRE el peer IP de la conexión TCP (no spoofable).
    """
    # Defensive: si `get_settings()` falla (test env sin envvars completos),
    # fail-safe a `trust_xff=False` — el peor caso es bucket más generoso,
    # NO bypass del rate limit.
    try:
        settings = get_settings()
        trust_xff = bool(getattr(settings, 'trust_proxy_forwarded_for', False))
    except Exception:  # noqa: BLE001
        trust_xff = False
    if trust_xff:
        forwarded = request.headers.get('x-forwarded-for')
        if forwarded:
            first = forwarded.split(',')[0].strip()
            if first:
                return first
    client = request.client
    if client and client.host:
        return client.host
    return 'unknown'


def build_rate_limit_middleware(limiter: RateLimiter):
    """Factory que retorna el middleware listo para `@api.middleware('http')`."""
    from fastapi import Response  # noqa: PLC0415

    async def rate_limit_middleware(request, call_next):
        path = request.url.path
        scope = classify_scope(path)
        client_ip = extract_client_ip(request)
        key = build_rate_limit_key(client_ip=client_ip, path=path)
        allowed, retry_after = await limiter.check(key, scope=scope)
        if not allowed:
            retry_seconds = max(1, int(round(retry_after)))
            log.warning(
                'rate_limit.blocked',
                rate_limited=True,
                client_ip=client_ip,
                path=path,
                scope=scope,
                retry_after_seconds=retry_seconds,
            )
            return Response(
                status_code=429,
                content='{"detail":"Too Many Requests"}',
                media_type='application/json',
                headers={'Retry-After': str(retry_seconds)},
            )
        return await call_next(request)

    return rate_limit_middleware
