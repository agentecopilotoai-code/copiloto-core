"""``OllamaProvider`` — LLM local vía Ollama HTTP API (TASK-INFLU-006).

Opción off-cloud para tenants regulados. Default host
``http://localhost:11434``. Modelo por defecto ``llama3.1:8b``.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Final

import httpx

from app.ai.providers.base import (
    LLMProvider,
    PersonaAnchor,
    ProviderTimeoutError,
    ProviderUnavailable,
    TextResult,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL: Final[str] = 'http://localhost:11434'
DEFAULT_MODEL: Final[str] = 'llama3.1:8b'


class OllamaProvider(LLMProvider):
    provider_name = 'ollama'

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip('/')
        self._model = model
        self._timeout = float(timeout)
        self._hard_deadline = self._timeout + 2.0
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(self._timeout, connect=2.0),
            transport=self._transport,
        )

    async def health_check(self) -> bool:
        async with self._client() as client:
            try:
                resp = await asyncio.wait_for(client.get('/api/tags'), timeout=2.0)
            except (asyncio.TimeoutError, httpx.HTTPError):
                return False
        return resp.status_code == 200

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

        payload = {
            'model': self._model,
            'prompt': prompt,
            'system': sys_prompt or None,
            'stream': False,
            'options': {
                'num_predict': int(max_tokens),
                'temperature': float(temperature),
            },
        }

        t0 = time.monotonic()
        async with self._client() as client:
            try:
                resp = await asyncio.wait_for(
                    client.post('/api/generate', json=payload),
                    timeout=self._hard_deadline,
                )
            except asyncio.TimeoutError as exc:
                raise ProviderTimeoutError(
                    f'ollama /api/generate exceeded {self._hard_deadline:.1f}s',
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(f'ollama /api/generate: {exc}') from exc

        if resp.status_code >= 400:
            raise ProviderUnavailable(f'ollama HTTP {resp.status_code}')
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        body = resp.json()
        return TextResult(
            text=(body.get('response') or '').strip(),
            finish_reason='stop' if body.get('done') else 'length',
            provider_meta={
                'model': body.get('model') or self._model,
                'eval_count': body.get('eval_count'),
                'total_duration_ns': body.get('total_duration'),
            },
            cost_units=float(body.get('eval_count') or 0),
            elapsed_ms=elapsed_ms,
        )


__all__ = ['OllamaProvider', 'DEFAULT_BASE_URL', 'DEFAULT_MODEL']
