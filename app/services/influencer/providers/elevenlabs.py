"""``ElevenLabsProvider`` — adapter ElevenLabs TTS (TASK-INFLU-005).

Voice cloning premium: cada persona puede tener un `voice_id`
ElevenLabs si el platform_owner habilita este provider. La API devuelve
audio binario directo (no JSON envelope).
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Final

import httpx

from app.services.influencer.providers.base import (
    AudioResult,
    PersonaAnchor,
    ProviderContentRejected,
    ProviderRateLimited,
    ProviderTimeoutError,
    ProviderUnavailable,
    TTSProvider,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL: Final[str] = 'https://api.elevenlabs.io/v1'
DEFAULT_MODEL: Final[str] = 'eleven_multilingual_v2'
DEFAULT_VOICE_ID: Final[str] = '21m00Tcm4TlvDq8ikWAM'  # ElevenLabs "Rachel" stock


class ElevenLabsProvider(TTSProvider):
    provider_name = 'elevenlabs'

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
            raise ValueError('ElevenLabsProvider requires a non-empty api_key')
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
            headers={'xi-api-key': self._api_key},
        )

    async def health_check(self) -> bool:
        async with self._client() as client:
            try:
                resp = await asyncio.wait_for(client.get('/voices'), timeout=2.0)
            except (asyncio.TimeoutError, httpx.HTTPError):
                return False
        return resp.status_code == 200

    async def synthesize_speech(
        self,
        *,
        text: str,
        persona_anchor: PersonaAnchor,
        language: str = 'es',
        sample_rate: int = 24000,
    ) -> AudioResult:
        voice_id = persona_anchor.voice_id_ref or DEFAULT_VOICE_ID
        idem = f'inf-{uuid.uuid4().hex}'

        t0 = time.monotonic()
        async with self._client() as client:
            try:
                resp = await asyncio.wait_for(
                    client.post(
                        f'/text-to-speech/{voice_id}',
                        json={
                            'text': text,
                            'model_id': self._model,
                            'voice_settings': {
                                'stability': 0.5,
                                'similarity_boost': 0.75,
                            },
                        },
                        headers={'Idempotency-Key': idem},
                    ),
                    timeout=self._hard_deadline,
                )
            except asyncio.TimeoutError as exc:
                raise ProviderTimeoutError('elevenlabs TTS timeout') from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(f'elevenlabs TTS: {exc}') from exc

        if resp.status_code == 429:
            raise ProviderRateLimited('elevenlabs 429')
        if resp.status_code in {400, 422}:
            try:
                body = resp.json()
            except ValueError:
                body = {}
            detail = str((body.get('detail') or '')).lower()
            if 'content' in detail or 'safety' in detail:
                raise ProviderContentRejected(f'elevenlabs: {detail}')
            raise ProviderUnavailable(f'elevenlabs HTTP 400: {detail}')
        if resp.status_code >= 400:
            raise ProviderUnavailable(f'elevenlabs HTTP {resp.status_code}')

        elapsed_ms = (time.monotonic() - t0) * 1000.0
        audio_bytes = resp.content
        return AudioResult(
            audio_bytes=audio_bytes,
            mime='audio/mpeg',
            duration_s=0.0,  # ElevenLabs no devuelve duración en headers
            sample_rate=sample_rate,
            provider_meta={
                'model': self._model,
                'voice_id': voice_id,
                'chars_used': len(text),
            },
            cost_units=float(len(text)),
            elapsed_ms=elapsed_ms,
        )


__all__ = ['ElevenLabsProvider', 'DEFAULT_BASE_URL', 'DEFAULT_MODEL']
