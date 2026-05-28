"""Adapter de email para Mailgun (https://mailgun.com).

Endpoint: ``POST https://api.mailgun.net/v3/{domain}/messages``
(o ``api.eu.mailgun.net`` para region=eu)
Auth: HTTP basic — ``api:<api_key>``
Docs: https://documentation.mailgun.com/en/latest/api-sending.html

Config requerida:
  - ``domain``: dominio verificado en Mailgun (e.g. 'mg.copilotoia.com').
  - ``region``: 'us' (default) o 'eu' — selecciona el endpoint regional.

Sin SDK — Mailgun acepta multipart/form-data, lo mandamos con httpx.
"""
from __future__ import annotations

import time
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from copiloto_core.email.providers.base import (
    EmailMessage,
    EmailProvider,
    ProviderInvalidConfig,
    ProviderRateLimited,
    ProviderRejected,
    ProviderResult,
    ProviderUnavailable,
)


class _MailgunConfig(BaseModel):
    """Schema esperado del `config_jsonb` de Mailgun.

    `domain` debe ser el dominio EXACTO verificado en Mailgun (no la URL,
    no el subdominio del wildcard). `region` define el cluster de la API.
    """
    model_config = ConfigDict(extra='forbid')
    domain: str = Field(min_length=3, max_length=255)
    region: Literal['us', 'eu'] = 'us'


class MailgunProvider(EmailProvider):
    """Adapter contra la API HTTP de Mailgun (multipart form)."""

    provider_type = 'mailgun'

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
            parsed = _MailgunConfig.model_validate(config or {})
        except Exception as exc:
            raise ProviderInvalidConfig(
                f'mailgun config invalid: {exc}'
            ) from exc
        if not api_key:
            raise ProviderInvalidConfig('mailgun: api_key vacío')
        if not from_address:
            raise ProviderInvalidConfig('mailgun: from_address vacío')
        self.provider_code = provider_code
        self._api_key = api_key
        self._domain = parsed.domain
        self._region = parsed.region
        self._base_url = (
            'https://api.eu.mailgun.net' if parsed.region == 'eu'
            else 'https://api.mailgun.net'
        )
        self._from_address = from_address
        self._from_name = from_name

    async def send(self, msg: EmailMessage) -> ProviderResult:
        from_field = (
            f'{self._from_name} <{self._from_address}>'
            if self._from_name else self._from_address
        )
        # Mailgun acepta multipart/form-data o application/x-www-form-urlencoded.
        # Usamos form-encoded — más simple, suficiente para el flujo sin
        # attachments. Los tags repetidos se mandan como múltiples campos
        # `o:tag` (httpx serializa una list[tuple] correctamente).
        form_data: list[tuple[str, Any]] = [
            ('from', from_field),
            ('to', msg.to_address),
            ('subject', msg.subject),
            ('text', msg.text),
            ('html', msg.html),
        ]
        if msg.tags:
            for k, v in msg.tags.items():
                form_data.append(('o:tag', f'{k}:{v}'))

        path = f'/v3/{self._domain}/messages'
        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=10.0,
            ) as client:
                resp = await client.post(
                    path,
                    auth=('api', self._api_key),
                    data=form_data,
                )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(
                f'mailgun transport error: {exc!s}'
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
                f'mailgun rate limited: {resp.text[:200]}',
                retry_after=retry_after,
            )
        if resp.status_code in (400, 422):
            raise ProviderRejected(
                f'mailgun rejected: http_{resp.status_code} {resp.text[:200]}'
            )
        if resp.status_code in (401, 403):
            raise ProviderUnavailable(
                f'mailgun auth error: http_{resp.status_code}'
            )
        if resp.status_code == 404:
            # Domain no existe → config invalid efectivamente. Lo tratamos
            # como Rejected (NOT retryable) en vez de Invalid porque el
            # adapter ya pasó la validación de shape; el error real está
            # del lado del provider, no del config jsonb.
            raise ProviderRejected(
                f'mailgun domain not found: {self._domain}'
            )
        if resp.status_code >= 500:
            raise ProviderUnavailable(
                f'mailgun server error: http_{resp.status_code} {resp.text[:200]}'
            )
        if resp.status_code >= 400:
            raise ProviderRejected(
                f'mailgun rejected: http_{resp.status_code} {resp.text[:200]}'
            )

        body = resp.json() if resp.content else {}
        # Mailgun devuelve { "id": "<...>", "message": "Queued. Thank you." }
        message_id = str(body.get('id') or '')
        return ProviderResult(
            success=True,
            message_id=message_id,
            provider_code=self.provider_code,
            latency_ms=latency_ms,
        )


__all__ = ['MailgunProvider']
