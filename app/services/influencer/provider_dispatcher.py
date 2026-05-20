"""Provider fallback chain + circuit breaker + audit — TASK-INFLU-007.

El dispatcher es el único punto desde el cual los workers de generación
invocan providers. No conoce el SDK específico — recibe un ``call_fn``
que sabe cómo hablar con el provider y devuelve un result dataclass.

Política:

1. Resuelve el provider primario via ``resolve_provider(modality)``.
2. Si la llamada lanza :class:`ProviderTimeoutError`,
   :class:`ProviderUnavailable` o :class:`ProviderRateLimited`, consulta
   ``ResolvedProvider.params['fallback_chain']`` (array ordenado de
   provider names) y reintenta con el siguiente provider del chain.
3. :class:`ProviderContentRejected` NO se reintenta (el filter rechazará
   también con el siguiente provider — error real del prompt).
4. Circuit breaker por provider: 5 fallos consecutivos en una ventana
   de 60s → provider marcado ``degraded`` por 5 min y saltado en próximos
   ``dispatch`` calls hasta que el cooldown expire.
5. Audit: cada dispatch emite una fila en ``influencer.provider_dispatch``
   con ``{modality, provider_primary, provider_used, fallback_depth,
   elapsed_ms, success, error_class}``.

Invariantes:

- El ``generation_id`` jamás cambia entre fallbacks — el tenant ve un
  solo asset producido, no sabe qué provider lo generó.
- ``cost_credits`` que paga el tenant es el del provider PRIMARIO según
  ``generation_pricing`` (TASK-INFLU-016) — no se sube si el fallback
  era más caro.
"""
from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Final

import asyncpg

from app.services.influencer.provider_registry import ResolvedProvider, resolve_provider
from app.services.influencer.providers.base import (
    ProviderContentRejected,
    ProviderError,
    ProviderRateLimited,
    ProviderTimeoutError,
    ProviderUnavailable,
)

logger = logging.getLogger(__name__)


# ─── Circuit breaker ───────────────────────────────────────────────────────


CB_FAILURE_THRESHOLD: Final[int] = 5
CB_WINDOW_SECONDS: Final[float] = 60.0
CB_COOLDOWN_SECONDS: Final[float] = 300.0  # 5 min


@dataclass
class _CircuitState:
    """Estado del breaker para un provider."""
    failures: deque = field(default_factory=lambda: deque(maxlen=CB_FAILURE_THRESHOLD))
    opened_at: float | None = None


# Module-level por worker — la "session" de un workers process. En
# producción cada worker mantiene su propio breaker (similar al cache de
# provider_registry); coordinación cross-worker se podría agregar después
# vía redis sin cambiar la interfaz.
_BREAKERS: dict[str, _CircuitState] = defaultdict(_CircuitState)


def _circuit_open(provider: str, now: float) -> bool:
    """True si el provider está en cooldown (skip en dispatch)."""
    state = _BREAKERS[provider]
    if state.opened_at is None:
        return False
    if now - state.opened_at < CB_COOLDOWN_SECONDS:
        return True
    # Cooldown expirado — reset.
    state.opened_at = None
    state.failures.clear()
    return False


def _record_failure(provider: str, now: float) -> None:
    state = _BREAKERS[provider]
    state.failures.append(now)
    # Solo abrimos si tenemos `CB_FAILURE_THRESHOLD` fallos dentro de la
    # ventana `CB_WINDOW_SECONDS`.
    if len(state.failures) < CB_FAILURE_THRESHOLD:
        return
    oldest = state.failures[0]
    if now - oldest <= CB_WINDOW_SECONDS:
        state.opened_at = now
        logger.warning(
            'circuit breaker opened for provider %s '
            '(%d failures in %.1fs, cooldown %.0fs)',
            provider, CB_FAILURE_THRESHOLD, now - oldest, CB_COOLDOWN_SECONDS,
        )


def _record_success(provider: str) -> None:
    state = _BREAKERS[provider]
    state.failures.clear()
    state.opened_at = None


def _breakers_reset() -> None:
    """Test-only. Limpia el estado de circuit breakers."""
    _BREAKERS.clear()


# ─── Audit ─────────────────────────────────────────────────────────────────


@dataclass
class DispatchAudit:
    """Snapshot de una llamada a :func:`dispatch` para auditoría."""
    modality: str
    provider_primary: str
    provider_used: str | None
    fallback_depth: int
    elapsed_ms: float
    success: bool
    error_class: str | None


async def _record_audit(conn: asyncpg.Connection | None, audit: DispatchAudit) -> None:
    """Inserta en ``influencer.provider_dispatch`` si la tabla existe.

    Si ``conn`` es ``None`` o la tabla no está creada todavía (caller
    pre-TASK-INFLU-007 schema migration), se loguea y se descarta — el
    dispatch no falla por la auditoría.
    """
    if conn is None:
        logger.info(
            'dispatch audit (conn=None): modality=%s primary=%s used=%s '
            'depth=%d elapsed_ms=%.1f success=%s err=%s',
            audit.modality, audit.provider_primary, audit.provider_used,
            audit.fallback_depth, audit.elapsed_ms, audit.success, audit.error_class,
        )
        return
    try:
        await conn.execute(
            '''
            insert into influencer.provider_dispatch
              (modality, provider_primary, provider_used, fallback_depth,
               elapsed_ms, success, error_class)
            values ($1, $2, $3, $4, $5, $6, $7)
            ''',
            audit.modality,
            audit.provider_primary,
            audit.provider_used,
            audit.fallback_depth,
            audit.elapsed_ms,
            audit.success,
            audit.error_class,
        )
    except asyncpg.PostgresError as exc:
        # No bloquear el dispatch real por un error de audit.
        logger.warning('dispatch audit insert failed: %s', exc)


# ─── dispatch() ────────────────────────────────────────────────────────────


CallFn = Callable[[ResolvedProvider], Awaitable[Any]]
"""Type alias: el caller pasa una función que recibe el ResolvedProvider
y devuelve el result de la modalidad (TextResult, ImageResult, etc).

Ejemplo de uso desde un worker::

    async def call(provider: ResolvedProvider) -> TextResult:
        adapter = make_adapter(provider)  # factory que mapea name → instancia
        return await adapter.generate_text(prompt=prompt, ...)

    result = await dispatch(
        conn=conn, modality='llm', call_fn=call,
    )
"""


async def dispatch(
    *,
    conn: asyncpg.Connection,
    modality: str,
    call_fn: CallFn,
    audit_conn: asyncpg.Connection | None = None,
) -> Any:
    """Ejecuta ``call_fn`` contra el provider primario; si falla con un
    error retryable, recorre el ``fallback_chain`` configurado.

    Args:
        conn: connection para leer ``platform_ai_providers``.
        modality: una de :data:`MODALITIES`.
        call_fn: corutina que recibe el ResolvedProvider y devuelve el
            result. La implementación es responsable de instanciar el
            adapter correcto y resolver el ``secret_ref``.
        audit_conn: si se provee, se inserta una fila en
            ``influencer.provider_dispatch``. Puede ser la misma `conn`.

    Raises:
        ProviderContentRejected: si el primer provider rechaza por
            content/safety (no se reintenta).
        ProviderUnavailable: si TODOS los providers (primario +
            fallback chain) fallaron.
    """
    primary = await resolve_provider(conn, modality)
    chain: list[str] = [primary.provider, *_get_fallback_chain(primary)]

    t_total = time.monotonic()
    last_error: ProviderError | None = None
    error_class: str | None = None
    provider_used: str | None = None
    depth = 0

    for i, provider_name in enumerate(chain):
        now = time.monotonic()
        if _circuit_open(provider_name, now):
            logger.info(
                'dispatch skipping %s (circuit open) — modality=%s depth=%d',
                provider_name, modality, i,
            )
            continue

        resolved = primary if i == 0 else _shadow_resolve(primary, provider_name)
        try:
            result = await call_fn(resolved)
        except ProviderContentRejected:
            # No fallback — content filter rechazaría también con el siguiente.
            _record_success(provider_name)  # el provider funcionó, el prompt es el problema
            await _record_audit(audit_conn, DispatchAudit(
                modality=modality,
                provider_primary=primary.provider,
                provider_used=provider_name,
                fallback_depth=i,
                elapsed_ms=(time.monotonic() - t_total) * 1000.0,
                success=False,
                error_class='ProviderContentRejected',
            ))
            raise
        except (ProviderTimeoutError, ProviderUnavailable, ProviderRateLimited) as exc:
            _record_failure(provider_name, now)
            last_error = exc
            error_class = type(exc).__name__
            logger.info(
                'dispatch fallback: %s failed (%s) — modality=%s next=%s',
                provider_name, error_class, modality,
                chain[i + 1] if i + 1 < len(chain) else 'NONE',
            )
            continue
        else:
            _record_success(provider_name)
            provider_used = provider_name
            depth = i
            await _record_audit(audit_conn, DispatchAudit(
                modality=modality,
                provider_primary=primary.provider,
                provider_used=provider_used,
                fallback_depth=depth,
                elapsed_ms=(time.monotonic() - t_total) * 1000.0,
                success=True,
                error_class=None,
            ))
            return result

    # Si llegamos aquí, todos los providers del chain fallaron.
    await _record_audit(audit_conn, DispatchAudit(
        modality=modality,
        provider_primary=primary.provider,
        provider_used=None,
        fallback_depth=len(chain),
        elapsed_ms=(time.monotonic() - t_total) * 1000.0,
        success=False,
        error_class=error_class or 'ProviderUnavailable',
    ))
    raise ProviderUnavailable(
        f'all providers failed for modality={modality} chain={chain} '
        f'last_error={last_error!r}',
    )


def _get_fallback_chain(primary: ResolvedProvider) -> list[str]:
    """Extrae ``params['fallback_chain']`` con defensa para forma inválida."""
    raw = primary.params.get('fallback_chain') if isinstance(primary.params, dict) else None
    if not isinstance(raw, list):
        return []
    return [str(name) for name in raw if isinstance(name, str) and name]


def _shadow_resolve(primary: ResolvedProvider, provider_name: str) -> ResolvedProvider:
    """Construye un ResolvedProvider sombra para un fallback name.

    El registry no tiene 5 filas por modalidad — solo una. Para los
    fallbacks, el caller debe poder distinguir el `provider_name` y
    resolver el secret_ref correspondiente (TASK-INFLU-016 lo formaliza
    con una tabla `fallback_secrets`). Aquí solo retornamos un wrapper
    con el name; el `call_fn` se encarga del resto.
    """
    return ResolvedProvider(
        modality=primary.modality,
        provider=provider_name,
        secret_ref=None,  # caller resuelve via env/separate table
        model=primary.params.get(f'{provider_name}_model') if isinstance(primary.params, dict) else None,
        params=primary.params if isinstance(primary.params, dict) else {},
        source=primary.source,
    )


__all__ = [
    'CB_FAILURE_THRESHOLD',
    'CB_WINDOW_SECONDS',
    'CB_COOLDOWN_SECONDS',
    'DispatchAudit',
    'dispatch',
    '_breakers_reset',
]
