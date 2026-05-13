"""Circuit breaker para llamadas a proveedores externos (cloud LLM, pagos).

Estados:
    closed     — flujo normal; cuenta fallos consecutivos.
    open       — el proveedor está caído; `call()` levanta `CircuitOpenError`
                  inmediatamente sin invocar el callable subyacente.
    half_open  — pasó el cooldown; permite UNA llamada de prueba. Si tiene
                  éxito vuelve a `closed`; si falla regresa a `open`.

El registro global `get_breaker(name)` evita instanciar uno nuevo por request
y se comparte entre el orquestador, el cloud_llm_answer y el payment_provider.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, TypeVar

import structlog

from app.services.metrics import set_circuit_breaker_state

log = structlog.get_logger()

T = TypeVar('T')

CLOSED = 'closed'
OPEN = 'open'
HALF_OPEN = 'half_open'


class CircuitOpenError(RuntimeError):
    """Levantada cuando el circuito está abierto y no se intenta la llamada."""

    def __init__(self, name: str, retry_after_seconds: float) -> None:
        super().__init__(
            f'Circuit breaker {name!r} is open; retry after {retry_after_seconds:.1f}s'
        )
        self.name = name
        self.retry_after_seconds = retry_after_seconds


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 5
    cooldown_seconds: float = 30.0
    _state: str = field(default=CLOSED)
    _consecutive_failures: int = 0
    _opened_at: float | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False, repr=False)

    @property
    def state(self) -> str:
        if self._state == OPEN and self._cooldown_elapsed():
            return HALF_OPEN
        return self._state

    @property
    def consecutive_failures(self) -> int:
        return self._consecutive_failures

    def _cooldown_elapsed(self) -> bool:
        if self._opened_at is None:
            return False
        return (time.monotonic() - self._opened_at) >= self.cooldown_seconds

    def _retry_after(self) -> float:
        if self._opened_at is None:
            return 0.0
        elapsed = time.monotonic() - self._opened_at
        return max(0.0, self.cooldown_seconds - elapsed)

    def _trip(self) -> None:
        self._state = OPEN
        self._opened_at = time.monotonic()
        set_circuit_breaker_state(provider=self.name, state=OPEN)
        log.warning(
            'circuit_breaker.opened',
            circuit_open=True,
            name=self.name,
            consecutive_failures=self._consecutive_failures,
            cooldown_seconds=self.cooldown_seconds,
        )

    def _reset(self) -> None:
        if self._state != CLOSED:
            log.info(
                'circuit_breaker.closed',
                circuit_open=False,
                name=self.name,
            )
        self._state = CLOSED
        self._consecutive_failures = 0
        self._opened_at = None
        set_circuit_breaker_state(provider=self.name, state=CLOSED)

    def record_success(self) -> None:
        self._reset()

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= self.failure_threshold:
            self._trip()

    async def call(self, func: Callable[..., Awaitable[T]], *args, **kwargs) -> T:
        """Ejecuta `func` bajo la protección del circuito.

        Si el circuito está `open` y el cooldown no expiró → `CircuitOpenError`.
        Si está `half_open` → permite la llamada y, según resultado, lo
        cierra o lo vuelve a abrir.
        """
        async with self._lock:
            current = self.state
            if current == OPEN:
                retry = self._retry_after()
                log.warning(
                    'circuit_breaker.rejected',
                    circuit_open=True,
                    name=self.name,
                    retry_after_seconds=round(retry, 2),
                )
                raise CircuitOpenError(self.name, retry)
            if current == HALF_OPEN:
                # Promueve el estado interno para que llamadas paralelas
                # vean `half_open` y no intenten otra prueba.
                self._state = HALF_OPEN
                set_circuit_breaker_state(provider=self.name, state=HALF_OPEN)
                log.info(
                    'circuit_breaker.half_open_probe',
                    name=self.name,
                )

        try:
            result = await func(*args, **kwargs)
        except Exception:
            async with self._lock:
                self.record_failure()
            raise
        async with self._lock:
            self.record_success()
        return result


_REGISTRY: dict[str, CircuitBreaker] = {}
_REGISTRY_LOCK = asyncio.Lock()


def get_breaker(
    name: str,
    *,
    failure_threshold: int = 5,
    cooldown_seconds: float = 30.0,
) -> CircuitBreaker:
    """Devuelve (o crea) un breaker registrado por nombre.

    La primera llamada con un `name` define los parámetros; llamadas
    posteriores con el mismo nombre devuelven la misma instancia y
    los parámetros nuevos se ignoran.
    """
    breaker = _REGISTRY.get(name)
    if breaker is None:
        breaker = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            cooldown_seconds=cooldown_seconds,
        )
        _REGISTRY[name] = breaker
    return breaker


def reset_registry() -> None:
    """Limpia el registro global. Sólo para tests."""
    _REGISTRY.clear()
