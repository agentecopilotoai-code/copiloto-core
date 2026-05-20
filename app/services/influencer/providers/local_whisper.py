"""``LocalWhisperProvider`` — STT local vía faster-whisper-server (TASK-INFLU-006).

Asume un servicio HTTP local (faster-whisper-server o whisper.cpp server)
en ``http://localhost:9001`` con un endpoint OpenAI-compatible
``/v1/audio/transcriptions``. CPU/GPU autodetect en el server-side; el
adapter solo hace el call.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Final

import httpx

from app.services.influencer.providers.base import (
    ProviderTimeoutError,
    ProviderUnavailable,
    STTProvider,
    TranscriptResult,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL: Final[str] = 'http://localhost:9001'
DEFAULT_MODEL: Final[str] = 'large-v3'


class LocalWhisperProvider(STTProvider):
    provider_name = 'local_whisper'

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
                resp = await asyncio.wait_for(client.get('/health'), timeout=2.0)
            except (asyncio.TimeoutError, httpx.HTTPError):
                return False
        return resp.status_code in (200, 404)

    async def transcribe(
        self,
        *,
        audio_bytes: bytes,
        mime: str = 'audio/mpeg',
        language: str | None = None,
    ) -> TranscriptResult:
        files: dict = {
            'file': ('audio.mp3', audio_bytes, mime),
            'model': (None, self._model),
        }
        if language:
            files['language'] = (None, language)

        t0 = time.monotonic()
        async with self._client() as client:
            try:
                resp = await asyncio.wait_for(
                    client.post('/v1/audio/transcriptions', files=files),
                    timeout=self._hard_deadline,
                )
            except asyncio.TimeoutError as exc:
                raise ProviderTimeoutError(
                    f'local_whisper exceeded {self._hard_deadline:.1f}s',
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(f'local_whisper: {exc}') from exc

        if resp.status_code >= 400:
            raise ProviderUnavailable(f'local_whisper HTTP {resp.status_code}')

        elapsed_ms = (time.monotonic() - t0) * 1000.0
        body = resp.json()
        return TranscriptResult(
            text=(body.get('text') or '').strip(),
            language=body.get('language') or language,
            confidence=body.get('confidence'),
            provider_meta={
                'model': self._model,
                'audio_seconds': body.get('duration'),
            },
            cost_units=float(body.get('duration') or 0) / 3600.0,
            elapsed_ms=elapsed_ms,
        )


__all__ = ['LocalWhisperProvider', 'DEFAULT_BASE_URL', 'DEFAULT_MODEL']
