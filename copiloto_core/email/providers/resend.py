"""Adapter de email para Resend (https://resend.com).

Endpoint: ``POST https://api.resend.com/emails``
Auth: ``Authorization: Bearer <api_key>``
Docs: https://resend.com/docs/api-reference/emails/send-email

Reusa el singleton ``copiloto_core.services.http_clients.get_resend_client()``
para no repetir el TCP+TLS handshake en cada envío.
"""
from __future__ import annotations

import time
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict

from copiloto_core.email.providers.base import (
    EmailMessage,
    EmailProvider,
    ProviderInvalidConfig,
    ProviderRateLimited,
    ProviderRejected,
    ProviderResult,
    ProviderUnavailable,
)


class _ResendConfig(BaseModel):
    """Resend no necesita nada más que la api_key (sí cifrada aparte).

    `extra='forbid'` para detectar typos en la config al instanciar.
    """
    model_config = ConfigDict(extra='forbid')


class ResendProvider(EmailProvider):
    """Implementación contra la API HTTP de Resend.

    Args:
      provider_code: el ``code`` único de la fila DB (audit / logs).
      api_key: la API key plaintext (ya descifrada del ciphertext).
      config: dict (parseado de `config_jsonb`). Para Resend debe ser ``{}``.
      from_address: sender efectivo (override del provider o fallback global).
      from_name: nombre humano del sender (puede ser vacío).
    """

    provider_type = 'resend'

    def __init__(
        self,
        *,
        provider_code: str,
        api_key: str,
        config: dict,
        from_address: str,
        from_name: str,
    ) -> None:
        try:
            _ResendConfig.model_validate(config or {})
        except Exception as exc:  # pydantic.ValidationError → re-raise tipada
            raise ProviderInvalidConfig(
                f'resend config invalid: {exc}'
            ) from exc
        if not api_key:
            raise ProviderInvalidConfig('resend: api_key vacío')
        if not from_address:
            raise ProviderInvalidConfig('resend: from_address vacío')
        self.provider_code = provider_code
        self._api_key = api_key
        self._from_address = from_address
        self._from_name = from_name

    async def send(self, msg: EmailMessage) -> ProviderResult:
        from_field = (
            f'{self._from_name} <{self._from_address}>'
            if self._from_name else self._from_address
        )
        payload: dict[str, Any] = {
            'from': from_field,
            'to': [msg.to_address],
            'subject': msg.subject,
            'html': msg.html,
            'text': msg.text,
        }
        if msg.tags:
            payload['tags'] = [
                {'name': k, 'value': v} for k, v in msg.tags.items()
            ]

        # Singleton client (TLS handshake reuse — PERF-001).
        from copiloto_core.services.http_clients import get_resend_client  # noqa: PLC0415

        t0 = time.monotonic()
        try:
            client = await get_resend_client()
            resp = await client.post(
                '/emails',
                headers={
                    'authorization': f'Bearer {self._api_key}',
                    'content-type': 'application/json',
                },
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(
                f'resend transport error: {exc!s}'
            ) from exc

        latency_ms = (time.monotonic() - t0) * 1000.0

        if resp.status_code == 429:
            retry_after_raw = resp.headers.get('retry-after')
            retry_after: float | None = None
            if retry_after_raw:
                try:
                    retry_after = float(retry_after_raw)
                except ValueError:
                    retry_after = None
            raise ProviderRateLimited(
                f'resend rate limited: {resp.text[:200]}',
                retry_after=retry_after,
            )
        if resp.status_code in (400, 422):
            # Body inválido: dirección mal formada, dominio no verificado.
            # NOT retryable.
            raise ProviderRejected(
                f'resend rejected: http_{resp.status_code} {resp.text[:200]}'
            )
        if resp.status_code in (401, 403):
            # Key inválida o sin permisos. Retryable (otro provider sí podría).
            raise ProviderUnavailable(
                f'resend auth error: http_{resp.status_code}'
            )
        if resp.status_code >= 500:
            raise ProviderUnavailable(
                f'resend server error: http_{resp.status_code} {resp.text[:200]}'
            )
        if resp.status_code >= 400:
            # Otro 4xx no clasificado → tratar como rejected (no retryable).
            raise ProviderRejected(
                f'resend rejected: http_{resp.status_code} {resp.text[:200]}'
            )

        body = resp.json() if resp.content else {}
        message_id = str(body.get('id') or '')
        return ProviderResult(
            success=True,
            message_id=message_id,
            provider_code=self.provider_code,
            latency_ms=latency_ms,
        )


__all__ = ['ResendProvider']
