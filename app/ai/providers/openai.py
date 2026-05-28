"""``OpenAIProvider`` — adapter OpenAI (TASK-INFLU-005).

LLM (gpt-4o-mini) + Image (DALL-E 3) + TTS (tts-1-hd) + STT (whisper-1).
Cloud fallback de Grok cubriendo 4 de las 5 modalidades — video no
ofrecido por OpenAI a fecha de TASK-INFLU-005, así que el dispatcher
debe ir directo a Grok / SDXL local para video.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import time
import uuid
from typing import Final

import httpx

from app.ai.providers.base import (
    AudioResult,
    ImageProvider,
    ImageResult,
    LLMProvider,
    PersistentHttpxClient,
    PersonaAnchor,
    ProviderContentRejected,
    ProviderRateLimited,
    ProviderTimeoutError,
    ProviderUnavailable,
    STTProvider,
    TTSProvider,
    TextResult,
    TranscriptResult,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL: Final[str] = 'https://api.openai.com/v1'
OPENAI_MODELS: Final[dict[str, str]] = {
    'llm': 'gpt-4o-mini',
    'image': 'dall-e-3',
    'tts': 'tts-1-hd',
    'stt': 'whisper-1',
}


class OpenAIProvider(LLMProvider, ImageProvider, TTSProvider, STTProvider):
    provider_name = 'openai'

    def __init__(
        self,
        *,
        api_key: str,
        timeout: float = 60.0,
        base_url: str = DEFAULT_BASE_URL,
        models: dict[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError('OpenAIProvider requires a non-empty api_key')
        self._api_key = api_key
        self._timeout = float(timeout)
        self._hard_deadline = self._timeout + 2.0
        self._base_url = base_url.rstrip('/')
        self._models = {**OPENAI_MODELS, **(models or {})}
        self._transport = transport
        # PERF-021 (audit#4) — singleton lazy-init, ver `app.ai.providers.base.
        # PersistentHttpxClient` para el rationale.
        self._http_client: httpx.AsyncClient | None = None

    def _client(self) -> PersistentHttpxClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self._base_url,
                timeout=httpx.Timeout(self._timeout, connect=5.0),
                transport=self._transport,
                headers={'Authorization': f'Bearer {self._api_key}'},
                limits=httpx.Limits(
                    max_keepalive_connections=10,
                    max_connections=20,
                    keepalive_expiry=30.0,
                ),
            )
        return PersistentHttpxClient(self._http_client)

    async def aclose(self) -> None:
        """Cleanup del client singleton (shutdown del worker)."""
        if self._http_client is not None:
            try:
                await self._http_client.aclose()
            except Exception:  # noqa: BLE001
                pass
            self._http_client = None

    async def _post(
        self,
        path: str,
        *,
        json_body: dict | None = None,
        binary: bool = False,
    ) -> httpx.Response:
        idem = f'inf-{uuid.uuid4().hex}'
        async with self._client() as client:
            try:
                resp = await asyncio.wait_for(
                    client.post(
                        path,
                        json=json_body,
                        headers={'Idempotency-Key': idem},
                    ),
                    timeout=self._hard_deadline,
                )
            except asyncio.TimeoutError as exc:
                raise ProviderTimeoutError(
                    f'openai {path} exceeded {self._hard_deadline:.1f}s',
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(f'openai {path}: {exc}') from exc
        _check_status(resp, path)
        return resp

    async def health_check(self) -> bool:
        async with self._client() as client:
            try:
                resp = await asyncio.wait_for(client.get('/models'), timeout=2.0)
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

        messages: list[dict] = []
        if sys_prompt:
            messages.append({'role': 'system', 'content': sys_prompt})
        messages.append({'role': 'user', 'content': prompt})

        t0 = time.monotonic()
        resp = await self._post(
            '/chat/completions',
            json_body={
                'model': self._models['llm'],
                'messages': messages,
                'max_tokens': int(max_tokens),
                'temperature': float(temperature),
            },
        )
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        body = resp.json()
        choice = (body.get('choices') or [{}])[0]
        finish_reason = choice.get('finish_reason')
        if finish_reason == 'content_filter':
            raise ProviderContentRejected('openai content_filter')
        usage = body.get('usage') or {}
        return TextResult(
            text=((choice.get('message') or {}).get('content') or '').strip(),
            finish_reason=finish_reason,
            provider_meta={
                'model': body.get('model') or self._models['llm'],
                'request_id': body.get('id'),
                'tokens_used': usage.get('total_tokens'),
            },
            cost_units=float(usage.get('total_tokens') or 0),
            elapsed_ms=elapsed_ms,
        )

    async def generate_image(
        self,
        *,
        prompt: str,
        persona_anchor: PersonaAnchor,
        count: int = 1,
        format: str = '1:1',
        safety_mode: bool = True,
        reference_image_url: str | None = None,
    ) -> list[ImageResult]:
        # DALL-E 3 size hint: 1024x1024 / 1024x1792 / 1792x1024
        size = _format_to_dalle_size(format)
        full_prompt = prompt
        if persona_anchor.style_tokens:
            full_prompt = f'{prompt}. Estilo: {", ".join(persona_anchor.style_tokens)}'

        t0 = time.monotonic()
        resp = await self._post(
            '/images/generations',
            json_body={
                'model': self._models['image'],
                'prompt': full_prompt,
                'n': max(1, int(count)),
                'size': size,
                'response_format': 'b64_json',
            },
        )
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        body = resp.json()
        results: list[ImageResult] = []
        data = body.get('data') or []
        for item in data:
            results.append(
                ImageResult(
                    image_bytes=_decode_b64(item.get('b64_json') or ''),
                    mime='image/png',
                    width=int(size.split('x')[0]),
                    height=int(size.split('x')[1]),
                    provider_meta={
                        'model': self._models['image'],
                        'revised_prompt': item.get('revised_prompt'),
                    },
                    elapsed_ms=elapsed_ms,
                ),
            )
        return results

    async def synthesize_speech(
        self,
        *,
        text: str,
        persona_anchor: PersonaAnchor,
        language: str = 'es',
        sample_rate: int = 24000,
    ) -> AudioResult:
        # OpenAI TTS returns binary mp3 directly (no JSON envelope).
        idem = f'inf-{uuid.uuid4().hex}'
        t0 = time.monotonic()
        async with self._client() as client:
            try:
                resp = await asyncio.wait_for(
                    client.post(
                        '/audio/speech',
                        json={
                            'model': self._models['tts'],
                            'input': text,
                            'voice': persona_anchor.voice_id_ref or 'alloy',
                            'response_format': 'mp3',
                        },
                        headers={'Idempotency-Key': idem},
                    ),
                    timeout=self._hard_deadline,
                )
            except asyncio.TimeoutError as exc:
                raise ProviderTimeoutError('openai /audio/speech timeout') from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(f'openai /audio/speech: {exc}') from exc
        _check_status(resp, '/audio/speech')
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        audio_bytes = resp.content
        return AudioResult(
            audio_bytes=audio_bytes,
            mime='audio/mpeg',
            duration_s=0.0,  # OpenAI no devuelve duración
            sample_rate=sample_rate,
            provider_meta={'model': self._models['tts'], 'chars_used': len(text)},
            cost_units=float(len(text)),
            elapsed_ms=elapsed_ms,
        )

    async def transcribe(
        self,
        *,
        audio_bytes: bytes,
        mime: str = 'audio/mpeg',
        language: str | None = None,
    ) -> TranscriptResult:
        # multipart/form-data — usar files=
        idem = f'inf-{uuid.uuid4().hex}'
        files = {
            'file': ('audio.mp3', audio_bytes, mime),
            'model': (None, self._models['stt']),
        }
        if language:
            files['language'] = (None, language)

        t0 = time.monotonic()
        async with self._client() as client:
            try:
                resp = await asyncio.wait_for(
                    client.post(
                        '/audio/transcriptions',
                        files=files,
                        headers={'Idempotency-Key': idem},
                    ),
                    timeout=self._hard_deadline,
                )
            except asyncio.TimeoutError as exc:
                raise ProviderTimeoutError('openai /audio/transcriptions timeout') from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(f'openai /audio/transcriptions: {exc}') from exc
        _check_status(resp, '/audio/transcriptions')
        elapsed_ms = (time.monotonic() - t0) * 1000.0
        body = resp.json()
        return TranscriptResult(
            text=(body.get('text') or '').strip(),
            language=body.get('language') or language,
            confidence=None,
            provider_meta={'model': self._models['stt']},
            elapsed_ms=elapsed_ms,
        )


# ─── Helpers ───────────────────────────────────────────────────────────────


def _check_status(resp: httpx.Response, path: str) -> None:
    if resp.status_code == 429:
        retry_after_raw = resp.headers.get('retry-after')
        # Reusamos el parser del módulo grok para mantener semántica única
        # (RFC 9110, sanity-cap 300s).
        from app.ai.providers.grok import _parse_retry_after  # noqa: PLC0415

        raise ProviderRateLimited(
            f'openai {path} 429 (retry-after={retry_after_raw})',
            retry_after=_parse_retry_after(retry_after_raw),
        )
    if resp.status_code in {400, 422}:
        try:
            body = resp.json()
        except ValueError:
            body = {}
        err = ((body.get('error') or {}).get('code') or '').lower()
        if 'content_policy' in err or 'safety' in err or 'moderation' in err:
            raise ProviderContentRejected(f'openai {path}: {err}')
        raise ProviderUnavailable(f'openai {path} HTTP 400: {err}')
    if resp.status_code >= 400:
        raise ProviderUnavailable(f'openai {path} HTTP {resp.status_code}')


def _format_to_dalle_size(fmt: str) -> str:
    # Mapping the requested format spec to DALL-E 3 supported sizes.
    return {
        '1:1': '1024x1024',
        '9:16': '1024x1792',
        '16:9': '1792x1024',
        '4:5': '1024x1024',  # closest aspect supported by DALL-E 3
    }.get(fmt, '1024x1024')


def _decode_b64(data: str) -> bytes:
    if not data:
        return b''
    try:
        return base64.b64decode(data, validate=False)
    except (ValueError, binascii.Error) as exc:
        raise ProviderUnavailable(f'openai invalid b64: {exc}') from exc


__all__ = ['OpenAIProvider', 'OPENAI_MODELS', 'DEFAULT_BASE_URL']
