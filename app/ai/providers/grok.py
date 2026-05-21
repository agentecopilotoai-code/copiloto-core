"""``GrokProvider`` — adapter xAI Grok para el módulo Influencer.

Implementa las 5 interfaces de TASK-INFLU-003 (LLM/Image/Video/TTS/STT)
contra la API REST de xAI. Modelos cableados según el pricing compartido
por el usuario (TASK-INFLU-004):

- LLM: ``grok-4.3`` (1M ctx).
- Image quality: ``grok-imagine-image-quality``.
- Image fast: ``grok-imagine-image``.
- Video: ``grok-imagine-video``.
- TTS / STT: endpoints ``Text to Speech`` / ``Speech to Text`` Grok.

Diseño:

- ``httpx.AsyncClient`` (no SDK oficial — el SDK xAI no es estable a
  fecha de TASK-INFLU-004 y este adapter usa la API REST documentada).
- ``asyncio.wait_for`` con ``hard_deadline = timeout + 2s`` (mismo
  patrón de ``app/chatbot/intent_classifier.py``) — defensa contra
  SDKs que ignoran el timeout nativo.
- ``transport`` inyectable para tests (``httpx.MockTransport``); mismo
  patrón que ``tests/test_payment_provider_static.py``.
- API key resuelta via ``app.services.whatsapp.resolve_secret_ref`` (o
  inyectada en el constructor para tests). Nunca se loguea en claro.

Seguridad:

- ``Authorization: Bearer <key>`` se envía solo en requests, nunca a
  logs. ``provider_meta`` incluye ``model``, ``request_id``,
  ``tokens_used`` cuando el provider los expone — sin la API key.
- Si ``safety_mode=True`` (default), el adapter prefija el prompt con
  ``[SAFE-FOR-WORK, BRAND-SAFE]`` y verifica ``content_flags`` antes
  de retornar. Si el provider rechaza, lanza
  :class:`ProviderContentRejected`.
- ``Idempotency-Key`` en todos los POSTs para safety con retries del
  dispatcher (TASK-INFLU-007).
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import time
import uuid
from typing import Any, Final

import httpx

from app.ai.providers.base import (
    AudioResult,
    ImageProvider,
    ImageResult,
    LLMProvider,
    PersonaAnchor,
    ProviderContentRejected,
    ProviderRateLimited,
    ProviderTimeoutError,
    ProviderUnavailable,
    STTProvider,
    TTSProvider,
    TextResult,
    TranscriptResult,
    VideoProvider,
    VideoResult,
)

logger = logging.getLogger(__name__)


# ─── Modelos cableados (TASK-INFLU-004) ────────────────────────────────────


DEFAULT_BASE_URL: Final[str] = 'https://api.x.ai/v1'

# Modelos por modalidad — sincronizado con el pricing de xAI. Pueden ser
# overrideados con ``params['model']`` desde ``platform_ai_providers``.
GROK_MODELS: Final[dict[str, str]] = {
    'llm': 'grok-4.3',
    'image': 'grok-imagine-image-quality',
    'image_fast': 'grok-imagine-image',
    'video': 'grok-imagine-video',
    'tts': 'grok-tts-1',
    'stt': 'grok-stt-1',
}

# Prefijo aplicado cuando ``safety_mode=True``. Grok respeta hints en el
# prompt; los ``content_flags`` de la respuesta confirman si el filter
# disparó.
SAFETY_PREFIX: Final[str] = '[SAFE-FOR-WORK, BRAND-SAFE] '


# ─── GrokProvider ──────────────────────────────────────────────────────────


class GrokProvider(LLMProvider, ImageProvider, VideoProvider, TTSProvider, STTProvider):
    """Adapter xAI Grok — implementa las 5 interfaces."""

    provider_name = 'grok'  # match con ``platform_ai_providers.provider``.

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
            raise ValueError('GrokProvider requires a non-empty api_key')
        self._api_key = api_key
        self._timeout = float(timeout)
        self._hard_deadline = self._timeout + 2.0
        self._base_url = base_url.rstrip('/')
        self._models = {**GROK_MODELS, **(models or {})}
        self._transport = transport

    # ── HTTP plumbing ─────────────────────────────────────────────────────

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(self._timeout, connect=5.0),
            transport=self._transport,
            headers={
                'Authorization': f'Bearer {self._api_key}',
                'User-Agent': 'copilotoia-influencer/1.0',
            },
        )

    async def _post(self, path: str, payload: dict[str, Any]) -> tuple[dict, dict]:
        """POST con hard deadline + error translation.

        Returns ``(json_body, response_headers)`` o levanta una de las
        excepciones tipadas de ``base.py``.
        """
        idem_key = f'inf-{uuid.uuid4().hex}'
        async with self._client() as client:
            try:
                resp = await asyncio.wait_for(
                    client.post(
                        path,
                        json=payload,
                        headers={'Idempotency-Key': idem_key},
                    ),
                    timeout=self._hard_deadline,
                )
            except asyncio.TimeoutError as exc:
                raise ProviderTimeoutError(
                    f'grok {path} exceeded {self._hard_deadline:.1f}s',
                ) from exc
            except httpx.HTTPError as exc:
                # Network / DNS / connect errors — provider está caído.
                raise ProviderUnavailable(f'grok {path}: {exc}') from exc

        return _translate_response(resp, path)

    # ── IAProvider ────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """GET ``/health`` (xAI lo expone). Returns True si 200."""
        async with self._client() as client:
            try:
                resp = await asyncio.wait_for(
                    client.get('/health'),
                    timeout=2.0,
                )
            except (asyncio.TimeoutError, httpx.HTTPError):
                return False
        return resp.status_code == 200

    # ── LLMProvider ───────────────────────────────────────────────────────

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
                sys_prompt = (
                    f'{sys_prompt}\n\nVoz: {tone}. Estilo: {style}.'.strip()
                )

        payload: dict[str, Any] = {
            'model': self._models['llm'],
            'messages': _build_messages(prompt, sys_prompt),
            'max_tokens': max_tokens,
            'temperature': temperature,
        }

        t0 = time.monotonic()
        body, _ = await self._post('/chat/completions', payload)
        elapsed_ms = (time.monotonic() - t0) * 1000.0

        choice = (body.get('choices') or [{}])[0]
        message = choice.get('message') or {}
        text = (message.get('content') or '').strip()
        finish_reason = choice.get('finish_reason')
        if finish_reason == 'content_filter':
            raise ProviderContentRejected('grok flagged the response (content_filter)')

        usage = body.get('usage') or {}
        return TextResult(
            text=text,
            finish_reason=finish_reason,
            provider_meta={
                'model': body.get('model') or self._models['llm'],
                'request_id': body.get('id'),
                'tokens_used': usage.get('total_tokens'),
                'prompt_tokens': usage.get('prompt_tokens'),
                'completion_tokens': usage.get('completion_tokens'),
            },
            cost_units=float(usage.get('total_tokens') or 0),
            elapsed_ms=elapsed_ms,
        )

    # ── ImageProvider ─────────────────────────────────────────────────────

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
        """Genera imágenes via la API REST de xAI Imagine.

        xAI expone un endpoint OpenAI-compatible: `POST /v1/images/generations`.
        El payload base es OpenAI-shape (`model`, `prompt`, `n`,
        `response_format`); `aspect_ratio` es una extensión propia de xAI
        documentada en `docs/xGrok/Imagine Overview`. Soporta opcionalmente
        `image_url` / `image_urls` para edits con reference images.

        Response shape: `{data: [{url, b64_json?}, ...]}`. Pedimos
        `response_format='b64_json'` para obtener los bytes inline (URLs
        son temporales y exigirían un fetch extra).
        """
        full_prompt = (SAFETY_PREFIX if safety_mode else '') + prompt
        refs: list[str] = list(persona_anchor.reference_image_urls or ())
        if reference_image_url:
            refs.append(reference_image_url)

        payload: dict[str, Any] = {
            'model': self._models['image'],
            'prompt': full_prompt,
            'n': max(1, int(count)),
            'response_format': 'b64_json',
        }
        # `aspect_ratio` es opcional en xAI; default 'auto'. Solo enviamos
        # si el caller pidió algo distinto del wildcard.
        if format and format != 'auto':
            payload['aspect_ratio'] = format
        # Reference images: el doc menciona `image_url` (1 ref, para edits
        # de una sola imagen) y `image_urls` (hasta 3 para multi-edit).
        if refs:
            if len(refs) == 1:
                payload['image_url'] = refs[0]
            else:
                payload['image_urls'] = refs[:3]

        t0 = time.monotonic()
        body, _ = await self._post('/images/generations', payload)
        elapsed_ms = (time.monotonic() - t0) * 1000.0

        # xAI puede devolver content moderation en el item, no en root.
        # Si todos los items vienen marcados como respect_moderation=False,
        # tratamos como rejection (el cliente no puede usar la imagen).
        data = body.get('data') or []
        if not data and body.get('content_flags'):
            raise ProviderContentRejected(
                f'grok rejected image generation: {body["content_flags"]}',
            )
        all_filtered = data and all(
            item.get('respect_moderation') is False for item in data
        )
        if all_filtered:
            raise ProviderContentRejected(
                'grok content_moderation rejected all generated images',
            )

        results: list[ImageResult] = []
        for item in data:
            # OpenAI shape: `b64_json`. Algunos endpoints xAI también
            # devuelven `b64_image` — aceptamos ambos por defensa.
            img_b64 = item.get('b64_json') or item.get('b64_image') or ''
            results.append(
                ImageResult(
                    image_bytes=_decode_b64(img_b64),
                    mime=item.get('mime') or 'image/jpeg',
                    width=int(item.get('width') or 0),
                    height=int(item.get('height') or 0),
                    provider_meta={
                        'model': body.get('model') or self._models['image'],
                        'request_id': body.get('id'),
                        'seed': item.get('seed'),
                    },
                    cost_units=float(body.get('cost_units') or 0) / max(1, len(data)),
                    elapsed_ms=elapsed_ms,
                ),
            )
        return results

    # ── VideoProvider ─────────────────────────────────────────────────────

    async def generate_video(
        self,
        *,
        prompt: str,
        persona_anchor: PersonaAnchor,
        duration_s: float = 15.0,
        format: str = '9:16',
        safety_mode: bool = True,
        audio_url: str | None = None,
    ) -> VideoResult:
        full_prompt = (SAFETY_PREFIX if safety_mode else '') + prompt

        payload: dict[str, Any] = {
            'model': self._models['video'],
            'prompt': full_prompt,
            'duration_s': float(duration_s),
            'aspect_ratio': format,
            'reference_image_urls': list(persona_anchor.reference_image_urls or ()),
            'style_tokens': list(persona_anchor.style_tokens or ()),
            'audio_url': audio_url,
            'safety_mode': bool(safety_mode),
        }

        t0 = time.monotonic()
        body, _ = await self._post('/imagine/videos', payload)
        elapsed_ms = (time.monotonic() - t0) * 1000.0

        if body.get('content_flags'):
            raise ProviderContentRejected(
                f'grok rejected video generation: {body["content_flags"]}',
            )

        return VideoResult(
            video_bytes=_decode_b64(body.get('b64_video') or ''),
            mime=body.get('mime') or 'video/mp4',
            width=int(body.get('width') or 0),
            height=int(body.get('height') or 0),
            duration_s=float(body.get('duration_s') or duration_s),
            provider_meta={
                'model': body.get('model') or self._models['video'],
                'request_id': body.get('id'),
            },
            cost_units=float(body.get('cost_units') or 0),
            elapsed_ms=elapsed_ms,
        )

    # ── TTSProvider ───────────────────────────────────────────────────────

    async def synthesize_speech(
        self,
        *,
        text: str,
        persona_anchor: PersonaAnchor,
        language: str = 'es',
        sample_rate: int = 24000,
    ) -> AudioResult:
        payload: dict[str, Any] = {
            'model': self._models['tts'],
            'text': text,
            'language': language,
            'sample_rate': int(sample_rate),
            'voice_ref': persona_anchor.voice_id_ref,
            'voice_tone': persona_anchor.voice_tone,
        }

        t0 = time.monotonic()
        body, _ = await self._post('/tts', payload)
        elapsed_ms = (time.monotonic() - t0) * 1000.0

        return AudioResult(
            audio_bytes=_decode_b64(body.get('b64_audio') or ''),
            mime=body.get('mime') or 'audio/mpeg',
            duration_s=float(body.get('duration_s') or 0.0),
            sample_rate=int(body.get('sample_rate') or sample_rate),
            provider_meta={
                'model': body.get('model') or self._models['tts'],
                'request_id': body.get('id'),
                'chars_used': body.get('chars_used') or len(text),
            },
            cost_units=float(body.get('chars_used') or len(text)),
            elapsed_ms=elapsed_ms,
        )

    # ── STTProvider ───────────────────────────────────────────────────────

    async def transcribe(
        self,
        *,
        audio_bytes: bytes,
        mime: str = 'audio/mpeg',
        language: str | None = None,
    ) -> TranscriptResult:
        payload: dict[str, Any] = {
            'model': self._models['stt'],
            'audio_b64': base64.b64encode(audio_bytes).decode('ascii'),
            'mime': mime,
            'language': language,
        }

        t0 = time.monotonic()
        body, _ = await self._post('/stt', payload)
        elapsed_ms = (time.monotonic() - t0) * 1000.0

        return TranscriptResult(
            text=(body.get('text') or '').strip(),
            language=body.get('language'),
            confidence=body.get('confidence'),
            provider_meta={
                'model': body.get('model') or self._models['stt'],
                'request_id': body.get('id'),
                'audio_seconds': body.get('audio_seconds'),
            },
            cost_units=float(body.get('audio_seconds') or 0.0) / 3600.0,
            elapsed_ms=elapsed_ms,
        )


# ─── Helpers ───────────────────────────────────────────────────────────────


def _build_messages(prompt: str, system: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({'role': 'system', 'content': system})
    messages.append({'role': 'user', 'content': prompt})
    return messages


def _decode_b64(data: str) -> bytes:
    if not data:
        return b''
    try:
        return base64.b64decode(data, validate=False)
    except (ValueError, binascii.Error) as exc:
        raise ProviderUnavailable(f'grok returned invalid base64: {exc}') from exc


def _translate_response(resp: httpx.Response, path: str) -> tuple[dict, dict]:
    """Mapea status codes a excepciones tipadas o devuelve ``(body, headers)``."""
    if resp.status_code == 429:
        retry_after = resp.headers.get('retry-after')
        raise ProviderRateLimited(
            f'grok {path} rate-limited (retry-after={retry_after})',
        )
    if resp.status_code in {400, 422}:
        # 400/422 con marker de content filter → content_rejected;
        # otros 4xx genéricos → unavailable.
        try:
            body = resp.json()
        except ValueError:
            body = {}
        err = (body.get('error') or {}).get('code') or ''
        if 'content' in err.lower() or 'safety' in err.lower():
            raise ProviderContentRejected(f'grok {path}: {err}')
        raise ProviderUnavailable(f'grok {path}: HTTP {resp.status_code} {err}')
    if resp.status_code >= 500:
        raise ProviderUnavailable(f'grok {path}: HTTP {resp.status_code}')
    if resp.status_code >= 400:
        raise ProviderUnavailable(f'grok {path}: HTTP {resp.status_code}')

    try:
        return resp.json(), dict(resp.headers)
    except ValueError as exc:
        raise ProviderUnavailable(f'grok {path}: non-json response') from exc


__all__ = ['GrokProvider', 'GROK_MODELS', 'DEFAULT_BASE_URL', 'SAFETY_PREFIX']
