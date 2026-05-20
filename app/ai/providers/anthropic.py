"""``AnthropicProvider`` — adapter Claude API para LLM (TASK-INFLU-005).

Cloud fallback de Grok para generación de texto (captions, descripciones
de identidad). Usa la API REST de Anthropic directamente vía httpx —
mismo patrón que `grok.py` para consistencia (transport inyectable,
hard_deadline, excepciones tipadas).
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any, Final

import httpx

from app.ai.providers.base import (
    LLMProvider,
    PersonaAnchor,
    ProviderContentRejected,
    ProviderRateLimited,
    ProviderTimeoutError,
    ProviderUnavailable,
    TextResult,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL: Final[str] = 'https://api.anthropic.com/v1'
ANTHROPIC_API_VERSION: Final[str] = '2023-06-01'
DEFAULT_MODEL: Final[str] = 'claude-sonnet-4-6'


class AnthropicProvider(LLMProvider):
    provider_name = 'anthropic'

    def __init__(
        self,
        *,
        api_key: str,
        timeout: float = 60.0,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError('AnthropicProvider requires a non-empty api_key')
        self._api_key = api_key
        self._timeout = float(timeout)
        self._hard_deadline = self._timeout + 2.0
        self._base_url = base_url.rstrip('/')
        self._model = model
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(self._timeout, connect=5.0),
            transport=self._transport,
            headers={
                'x-api-key': self._api_key,
                'anthropic-version': ANTHROPIC_API_VERSION,
                'content-type': 'application/json',
            },
        )

    async def health_check(self) -> bool:
        async with self._client() as client:
            try:
                resp = await asyncio.wait_for(client.get('/health'), timeout=2.0)
            except (asyncio.TimeoutError, httpx.HTTPError):
                return False
        return resp.status_code in (200, 404)  # /health no documented; tolerate 404

    async def generate_text(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
        persona_anchor: PersonaAnchor | None = None,
    ) -> TextResult:
        sys_prompt = system or ''
        if persona_anchor is not None:
            tone = persona_anchor.voice_tone or ''
            style = ', '.join(persona_anchor.style_tokens or ())
            if tone or style:
                sys_prompt = f'{sys_prompt}\n\nVoz: {tone}. Estilo: {style}.'.strip()

        payload: dict[str, Any] = {
            'model': self._model,
            'max_tokens': int(max_tokens),
            'temperature': float(temperature),
            'messages': [{'role': 'user', 'content': prompt}],
        }
        if sys_prompt:
            payload['system'] = sys_prompt

        idem = f'inf-{uuid.uuid4().hex}'
        t0 = time.monotonic()
        async with self._client() as client:
            try:
                resp = await asyncio.wait_for(
                    client.post(
                        '/messages',
                        json=payload,
                        headers={'Idempotency-Key': idem},
                    ),
                    timeout=self._hard_deadline,
                )
            except asyncio.TimeoutError as exc:
                raise ProviderTimeoutError(
                    f'anthropic /messages exceeded {self._hard_deadline:.1f}s',
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(f'anthropic /messages: {exc}') from exc
        elapsed_ms = (time.monotonic() - t0) * 1000.0

        if resp.status_code == 429:
            raise ProviderRateLimited('anthropic /messages 429')
        if resp.status_code in {400, 422}:
            try:
                body = resp.json()
            except ValueError:
                body = {}
            etype = ((body.get('error') or {}).get('type') or '').lower()
            if 'content' in etype or 'safety' in etype:
                raise ProviderContentRejected(f'anthropic: {etype}')
            raise ProviderUnavailable(f'anthropic 400: {etype}')
        if resp.status_code >= 400:
            raise ProviderUnavailable(f'anthropic /messages HTTP {resp.status_code}')

        try:
            body = resp.json()
        except ValueError as exc:
            raise ProviderUnavailable('anthropic non-json response') from exc

        # Anthropic returns content as a list of blocks.
        parts = body.get('content') or []
        text = ''.join(
            p.get('text', '') for p in parts if isinstance(p, dict) and p.get('type') == 'text'
        ).strip()
        finish_reason = body.get('stop_reason')
        usage = body.get('usage') or {}
        return TextResult(
            text=text,
            finish_reason=finish_reason,
            provider_meta={
                'model': body.get('model') or self._model,
                'request_id': body.get('id'),
                'tokens_used': (usage.get('input_tokens') or 0) + (usage.get('output_tokens') or 0),
                'input_tokens': usage.get('input_tokens'),
                'output_tokens': usage.get('output_tokens'),
            },
            cost_units=float((usage.get('input_tokens') or 0) + (usage.get('output_tokens') or 0)),
            elapsed_ms=elapsed_ms,
        )


__all__ = ['AnthropicProvider', 'DEFAULT_BASE_URL', 'DEFAULT_MODEL']
