"""Adapter de email para SendGrid (https://sendgrid.com).

Endpoint: ``POST https://api.sendgrid.com/v3/mail/send``
Auth: ``Authorization: Bearer <api_key>``
Docs: https://www.twilio.com/docs/sendgrid/api-reference/mail-send/mail-send

Implementación nota: el SDK oficial ``sendgrid==6.11.0`` está pineado en
``pyproject.toml`` para que esté disponible cuando alguien quiera usar el
``SendGridAPIClient`` directo o sus helpers (``Mail``, ``Email``, ...).
Acá usamos httpx async para mantener consistencia con Resend/Mailgun
(reutilizamos el connection pool global; el SDK oficial es sync y forzaría
``run_in_executor`` por cada envío — sub-óptimo).
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


class _SendGridConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')


class SendGridProvider(EmailProvider):
    """Adapter contra la API REST de SendGrid (v3)."""

    provider_type = 'sendgrid'
    _base_url = 'https://api.sendgrid.com'

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
            _SendGridConfig.model_validate(config or {})
        except Exception as exc:
            raise ProviderInvalidConfig(
                f'sendgrid config invalid: {exc}'
            ) from exc
        if not api_key:
            raise ProviderInvalidConfig('sendgrid: api_key vacío')
        if not from_address:
            raise ProviderInvalidConfig('sendgrid: from_address vacío')
        self.provider_code = provider_code
        self._api_key = api_key
        self._from_address = from_address
        self._from_name = from_name

    async def send(self, msg: EmailMessage) -> ProviderResult:
        # Payload v3 — multi-personalization (acá solo uno). `content` lleva
        # el text/plain primero y luego text/html (la spec sugiere ordenar
        # de menor a mayor riqueza).
        payload: dict[str, Any] = {
            'personalizations': [
                {
                    'to': [{'email': msg.to_address}],
                    'subject': msg.subject,
                },
            ],
            'from': {
                'email': self._from_address,
                **({'name': self._from_name} if self._from_name else {}),
            },
            'content': [
                {'type': 'text/plain', 'value': msg.text},
                {'type': 'text/html', 'value': msg.html},
            ],
        }
        if msg.tags:
            # SendGrid expone tags como `categories` (max 10, strings); el
            # dict de tags lo aplanamos a `key:value` para preservar info.
            payload['categories'] = [
                f'{k}:{v}' for k, v in list(msg.tags.items())[:10]
            ]

        t0 = time.monotonic()
        try:
            # Client one-off para sendgrid — sin singleton dedicado porque no
            # es el primary path; cuando se promueva a primary, agregar
            # `get_sendgrid_client` en `services/http_clients.py`.
            async with httpx.AsyncClient(
                base_url=self._base_url, timeout=10.0,
            ) as client:
                resp = await client.post(
                    '/v3/mail/send',
                    headers={
                        'authorization': f'Bearer {self._api_key}',
                        'content-type': 'application/json',
                    },
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise ProviderUnavailable(
                f'sendgrid transport error: {exc!s}'
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
                f'sendgrid rate limited: {resp.text[:200]}',
                retry_after=retry_after,
            )
        if resp.status_code in (400, 422):
            raise ProviderRejected(
                f'sendgrid rejected: http_{resp.status_code} {resp.text[:200]}'
            )
        if resp.status_code in (401, 403):
            raise ProviderUnavailable(
                f'sendgrid auth error: http_{resp.status_code}'
            )
        if resp.status_code >= 500:
            raise ProviderUnavailable(
                f'sendgrid server error: http_{resp.status_code} {resp.text[:200]}'
            )
        if resp.status_code >= 400:
            raise ProviderRejected(
                f'sendgrid rejected: http_{resp.status_code} {resp.text[:200]}'
            )

        # SendGrid devuelve 202 Accepted con body vacío. El message_id viene
        # en el header `x-message-id` (mayúscula/minúscula irrelevante con
        # httpx). Lo guardamos para correlar con webhooks de events.
        message_id = resp.headers.get('x-message-id', '')
        return ProviderResult(
            success=True,
            message_id=message_id,
            provider_code=self.provider_code,
            latency_ms=latency_ms,
        )


__all__ = ['SendGridProvider']
