"""Rate limiting con token bucket en memoria.

Diseñado para FastAPI: el middleware se registra en `app.main.create_app()` y
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
from dataclasses import dataclass, field

import structlog

log = structlog.get_logger()

WEBHOOK_META_PREFIX = '/webhooks/whatsapp'
# Extrae tenant_id del path del webhook si viene presente.
_TENANT_PATH_RE = re.compile(
    r'/(?:v1|webhooks/whatsapp)/(?:tenants/)?'
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
    """Registry de buckets por clave + factory por scope (webhook vs default)."""

    def __init__(
        self,
        *,
        default_per_minute: int,
        webhook_per_minute: int,
    ) -> None:
        if default_per_minute <= 0:
            raise ValueError('default_per_minute must be > 0')
        if webhook_per_minute <= 0:
            raise ValueError('webhook_per_minute must be > 0')
        self.default_per_minute = default_per_minute
        self.webhook_per_minute = webhook_per_minute
        self._buckets: dict[str, TokenBucket] = {}
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

    async def check(self, key: str, *, scope: str) -> tuple[bool, float]:
        async with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = self.build_bucket(scope=scope)
                self._buckets[key] = bucket
            return bucket.consume(1.0)


def classify_scope(path: str) -> str:
    if path.startswith(WEBHOOK_META_PREFIX):
        return 'webhook'
    return 'default'


def build_rate_limit_key(*, client_ip: str, path: str) -> str:
    """Construye la clave del bucket: ip + tenant_id si está en el path."""
    match = _TENANT_PATH_RE.search(path)
    if match:
        return f'{client_ip}:{match.group("tenant")}'
    return f'{client_ip}:-'


def extract_client_ip(request) -> str:
    """Extrae IP del cliente respetando X-Forwarded-For si viene del proxy."""
    forwarded = request.headers.get('x-forwarded-for')
    if forwarded:
        # Toma el primer hop (cliente original).
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
