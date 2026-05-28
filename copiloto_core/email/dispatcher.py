"""Email dispatcher con fallback chain + audit por intento.

Espeja `copiloto_core/ai/dispatcher.py` pero simplificado:

- Sin circuit breaker (los workloads de email son baja-frecuencia
  comparado con IA; un breaker agregaría complejidad sin beneficio
  medible). Si en producción se observan tormentas de fallos, agregar
  CB después con el mismo patrón de ``_BREAKERS`` del módulo IA.
- Sin backoff entre intentos del chain. Los emails son fire-and-forget
  desde el caller; agregar latency entre attempts solo demora la
  detección del primer success.

Política:

1. ``SELECT * FROM app.email_providers WHERE is_active=true ORDER BY priority ASC``.
2. Si la lista está vacía → return ``ProviderResult(success=False,
   error='no_providers_configured')``. NO audit (no hay provider id
   contra el cual loguear).
3. Por cada provider del chain:
   a. Factory.make_email_provider(row) → instancia adapter.
   b. ``await adapter.send(msg)`` → ProviderResult.
   c. Si success → audit `sent` + return.
   d. Si ProviderUnavailable | ProviderRateLimited → audit `retried` +
      try next.
   e. Si ProviderInvalidConfig | ProviderRejected → audit `failed` +
      return (NO fallback — el error de config no se resuelve cambiando
      de provider).
4. Si todos los providers fallan con errores retryable → audit `failed` +
   return ``ProviderResult(success=False)`` con el último error.
"""
from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING

from copiloto_core.email.providers.base import (
    EmailMessage,
    ProviderInvalidConfig,
    ProviderRateLimited,
    ProviderRejected,
    ProviderResult,
    ProviderUnavailable,
)
from copiloto_core.email.providers.factory import make_email_provider

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)


class EmailDispatcher:
    """Punto único de envío de email del core.

    Es stateless — instanciar uno por proceso (o ad-hoc) no agrega costo.
    Recibe `conn` en cada `send()` porque las conexiones a la DB son
    transaction-per-request y no queremos guardarlas en estado.

    Args:
      fallback_from_address: sender global que aplica si la fila de provider
        no tiene `from_address_override`. Si None, lee de Settings al call.
      fallback_from_name: idem para nombre.
    """

    def __init__(
        self,
        *,
        fallback_from_address: str | None = None,
        fallback_from_name: str | None = None,
    ) -> None:
        self._explicit_from_address = fallback_from_address
        self._explicit_from_name = fallback_from_name

    def _resolve_sender(self) -> tuple[str, str]:
        """Lee del Settings si no se inyectó explícito. Lazy para que tests
        que monkeypatchen `get_settings` después de instanciar funcionen."""
        from copiloto_core.core.config import get_settings  # noqa: PLC0415
        s = get_settings()
        addr = self._explicit_from_address or s.email_from_address
        name = self._explicit_from_name or s.email_from_name
        return addr, name

    async def send(
        self,
        conn: 'asyncpg.Connection',
        msg: EmailMessage,
        *,
        support_mode: bool = True,
    ) -> ProviderResult:
        """Envía `msg` recorriendo `app.email_providers` por prioridad.

        Args:
          conn: connection asyncpg. El método setea `app.support_mode`
            si `support_mode=True` (default) para bypassear RLS — los
            providers son recurso global. Si el caller ya está bajo
            `support_mode` (e.g. dentro de un handler platform_admin),
            puede pasar False para no anidar settings.
          msg: `EmailMessage` a enviar.

        Returns:
          ProviderResult con `success` + `provider_code` del provider que
          aceptó (o `error` si todos fallaron). NUNCA levanta excepción
          al caller — los errores se devuelven como `success=False`.
        """
        rows = await self._fetch_active_providers(conn, support_mode=support_mode)
        if not rows:
            logger.warning(
                'email.dispatcher.no_providers_configured to=%s', _redact(msg.to_address),
            )
            return ProviderResult(
                success=False,
                error='no_providers_configured',
            )

        from_address, from_name = self._resolve_sender()
        last_error: str | None = None

        for row in rows:
            provider_code = row.get('code') or ''
            provider_id = row.get('id')
            try:
                adapter = make_email_provider(
                    row,
                    fallback_from_address=from_address,
                    fallback_from_name=from_name,
                )
            except (ProviderInvalidConfig, ValueError) as exc:
                # Config rota → NOT retryable; el siguiente provider del
                # chain probablemente esté igual de bien configurado, pero
                # este es un error de plataforma que el operador debe
                # arreglar. Lo logueamos y propagamos error.
                last_error = f'{type(exc).__name__}: {exc}'
                logger.error(
                    'email.dispatcher.invalid_config code=%s error=%s',
                    provider_code, last_error,
                )
                await self._audit_attempt(
                    conn, provider_id=provider_id, msg=msg,
                    status='failed', error_message=last_error,
                    latency_ms=0.0, support_mode=support_mode,
                )
                return ProviderResult(
                    success=False,
                    provider_code=provider_code,
                    error=last_error,
                )

            t0 = time.monotonic()
            try:
                result = await adapter.send(msg)
            except (ProviderUnavailable, ProviderRateLimited) as exc:
                # Retryable — audit como `retried` y seguir con el next.
                latency_ms = (time.monotonic() - t0) * 1000.0
                last_error = f'{type(exc).__name__}: {exc}'
                logger.info(
                    'email.dispatcher.attempt_retryable code=%s error=%s',
                    provider_code, last_error,
                )
                await self._audit_attempt(
                    conn, provider_id=provider_id, msg=msg,
                    status='retried', error_message=last_error,
                    latency_ms=latency_ms, support_mode=support_mode,
                )
                continue
            except (ProviderInvalidConfig, ProviderRejected) as exc:
                # NOT retryable — el fallback no resolvería. Stop chain.
                latency_ms = (time.monotonic() - t0) * 1000.0
                last_error = f'{type(exc).__name__}: {exc}'
                logger.warning(
                    'email.dispatcher.attempt_terminal code=%s error=%s',
                    provider_code, last_error,
                )
                await self._audit_attempt(
                    conn, provider_id=provider_id, msg=msg,
                    status='failed', error_message=last_error,
                    latency_ms=latency_ms, support_mode=support_mode,
                )
                return ProviderResult(
                    success=False,
                    provider_code=provider_code,
                    latency_ms=latency_ms,
                    error=last_error,
                )

            # Path feliz.
            await self._audit_attempt(
                conn, provider_id=provider_id, msg=msg,
                status='sent', error_message=None,
                latency_ms=result.latency_ms, support_mode=support_mode,
            )
            logger.info(
                'email.dispatcher.sent code=%s to=%s message_id=%s',
                provider_code, _redact(msg.to_address), result.message_id,
            )
            return result

        # Chain agotado sin éxito — todos los attempts eran retryable.
        logger.warning(
            'email.dispatcher.chain_exhausted to=%s last_error=%s',
            _redact(msg.to_address), last_error,
        )
        return ProviderResult(
            success=False,
            error=last_error or 'all_providers_failed',
        )

    # ─── Internals ────────────────────────────────────────────────────────

    async def _fetch_active_providers(
        self,
        conn: 'asyncpg.Connection',
        *,
        support_mode: bool,
    ) -> list[dict]:
        """Devuelve filas activas ORDER BY priority ASC."""
        async with conn.transaction():
            if support_mode:
                await conn.execute(
                    "select set_config('app.support_mode', 'true', true)"
                )
            rows = await conn.fetch(
                '''
                select id, code, provider_type, name, config_jsonb,
                       api_key_ciphertext, from_address_override,
                       from_name_override, is_active, priority
                from app.email_providers
                where is_active = true
                order by priority asc, created_at asc
                '''
            )
        return [dict(r) for r in rows]

    async def _audit_attempt(
        self,
        conn: 'asyncpg.Connection',
        *,
        provider_id,
        msg: EmailMessage,
        status: str,
        error_message: str | None,
        latency_ms: float,
        support_mode: bool,
    ) -> None:
        """Insert best-effort en `app.email_dispatch_log`. Nunca rompe el
        dispatch si la inserción falla — solo loguea.

        Trunca `error_message` a 2 KiB para no inflar la tabla si un
        provider devuelve un HTML largo en el body de error.
        """
        try:
            async with conn.transaction():
                if support_mode:
                    await conn.execute(
                        "select set_config('app.support_mode', 'true', true)"
                    )
                await conn.execute(
                    '''
                    insert into app.email_dispatch_log
                      (email_provider_id, to_address, subject, status,
                       error_message, latency_ms, dispatched_at)
                    values ($1, $2, $3, $4, $5, $6, now())
                    ''',
                    provider_id,
                    msg.to_address,
                    msg.subject[:500],
                    status,
                    (error_message or '')[:2048] or None,
                    int(latency_ms),
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                'email.dispatcher.audit_failed status=%s error=%s',
                status, exc,
            )


def _redact(addr: str) -> str:
    """`a***@d.com` para logs PII-safe."""
    if not addr or '@' not in addr:
        return '[invalid]'
    local, _, domain = addr.partition('@')
    if len(local) <= 2:
        masked = '*' * len(local)
    else:
        masked = local[0] + '*' * (len(local) - 2) + local[-1]
    return f'{masked}@{domain}'


# ``json`` import-only por si los adapters necesitan el helper más adelante.
_ = json


__all__ = ['EmailDispatcher']
