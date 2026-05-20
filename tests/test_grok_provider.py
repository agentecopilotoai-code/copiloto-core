"""Dynamic tests para ``GrokProvider`` — TASK-INFLU-004.

Cada modalidad se prueba con ``httpx.MockTransport`` (mismo patrón que
``tests/test_payment_provider_static.py`` y
``tests/test_unit_payment_provider_complete.py``):

- happy path → result dataclass correcto + ``provider_meta`` con
  ``model``/``request_id``/``tokens_used`` cuando aplica.
- timeout → :class:`ProviderTimeoutError`.
- 429 rate limited → :class:`ProviderRateLimited`.
- 5xx → :class:`ProviderUnavailable`.
- content rejection (400 con error.code=content_filter) →
  :class:`ProviderContentRejected`.
- ``Idempotency-Key`` presente en cada POST.
- API key se envía como ``Authorization: Bearer <key>``.
"""
from __future__ import annotations

import asyncio
import base64
from typing import Any

import httpx
import pytest

from app.services.influencer.providers.base import (
    AudioResult,
    ImageResult,
    PersonaAnchor,
    ProviderContentRejected,
    ProviderRateLimited,
    ProviderTimeoutError,
    ProviderUnavailable,
    TextResult,
    TranscriptResult,
    VideoResult,
)
from app.services.influencer.providers.grok import GROK_MODELS, GrokProvider


# ─── Helpers ───────────────────────────────────────────────────────────────


def _png_bytes() -> bytes:
    # PNG mágico mínimo para validar que decoding b64 produce bytes válidos.
    return b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode('ascii')


def _make_provider(handler, **kwargs) -> GrokProvider:
    transport = httpx.MockTransport(handler)
    return GrokProvider(
        api_key='test-grok-key-NEVER-LEAK',
        timeout=2.0,
        transport=transport,
        **kwargs,
    )


def _anchor() -> PersonaAnchor:
    return PersonaAnchor(
        persona_id='persona-1',
        face_embedding=tuple([0.0] * 8),
        body_traits={'build': 'athletic'},
        reference_image_urls=('https://s3/face1.jpg', 'https://s3/face2.jpg'),
        style_tokens=('cálida', 'resort wear'),
        voice_id_ref='grok-voice-clone-1',
        voice_tone='cercana',
    )


# ─── LLM ───────────────────────────────────────────────────────────────────


def test_generate_text_happy_path():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured['path'] = request.url.path
        captured['auth'] = request.headers.get('authorization')
        captured['idem'] = request.headers.get('idempotency-key')
        captured['body'] = request.read()
        return httpx.Response(
            200,
            json={
                'id': 'chatcmpl-abc',
                'model': GROK_MODELS['llm'],
                'choices': [
                    {
                        'message': {'content': 'hola desde grok'},
                        'finish_reason': 'stop',
                    },
                ],
                'usage': {
                    'prompt_tokens': 10,
                    'completion_tokens': 5,
                    'total_tokens': 15,
                },
            },
        )

    provider = _make_provider(handler)
    result = asyncio.run(
        provider.generate_text(prompt='hola', persona_anchor=_anchor()),
    )

    assert isinstance(result, TextResult)
    assert result.text == 'hola desde grok'
    assert result.finish_reason == 'stop'
    assert result.provider_meta['model'] == GROK_MODELS['llm']
    assert result.provider_meta['request_id'] == 'chatcmpl-abc'
    assert result.provider_meta['tokens_used'] == 15
    assert result.elapsed_ms > 0

    assert captured['path'].endswith('/chat/completions')
    assert captured['auth'] == 'Bearer test-grok-key-NEVER-LEAK'
    assert captured['idem'], 'Idempotency-Key debe estar presente'


def test_generate_text_content_filter_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                'choices': [
                    {
                        'message': {'content': '[redacted]'},
                        'finish_reason': 'content_filter',
                    },
                ],
            },
        )

    provider = _make_provider(handler)
    with pytest.raises(ProviderContentRejected):
        asyncio.run(provider.generate_text(prompt='bad'))


def test_rate_limited_maps_to_typed_exception():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={'retry-after': '7'}, json={})

    provider = _make_provider(handler)
    with pytest.raises(ProviderRateLimited):
        asyncio.run(provider.generate_text(prompt='hola'))


def test_5xx_maps_to_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    provider = _make_provider(handler)
    with pytest.raises(ProviderUnavailable):
        asyncio.run(provider.generate_text(prompt='hola'))


def test_4xx_content_safety_maps_to_content_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={'error': {'code': 'content_filter_triggered', 'message': '...'}},
        )

    provider = _make_provider(handler)
    with pytest.raises(ProviderContentRejected):
        asyncio.run(provider.generate_text(prompt='hola'))


def test_timeout_maps_to_provider_timeout_error():
    async def slow_handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)  # excede el timeout=2.0 + 2s deadline
        return httpx.Response(200, json={})

    provider = _make_provider(slow_handler)
    with pytest.raises(ProviderTimeoutError):
        asyncio.run(provider.generate_text(prompt='hola'))


# ─── Image ─────────────────────────────────────────────────────────────────


def test_generate_image_happy_path():
    img_bytes = _png_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                'id': 'img-xyz',
                'model': GROK_MODELS['image'],
                'data': [
                    {
                        'b64_image': _b64(img_bytes),
                        'mime': 'image/png',
                        'width': 1024,
                        'height': 1024,
                        'seed': 42,
                    },
                ],
                'cost_units': 0.05,
            },
        )

    provider = _make_provider(handler)
    results = asyncio.run(
        provider.generate_image(prompt='girl in resort', persona_anchor=_anchor()),
    )

    assert len(results) == 1
    img = results[0]
    assert isinstance(img, ImageResult)
    assert img.image_bytes == img_bytes
    assert img.mime == 'image/png'
    assert img.width == 1024
    assert img.height == 1024
    assert img.provider_meta['request_id'] == 'img-xyz'
    assert img.provider_meta['seed'] == 42


def test_generate_image_content_flags_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={'data': [], 'content_flags': ['nudity']},
        )

    provider = _make_provider(handler)
    with pytest.raises(ProviderContentRejected):
        asyncio.run(
            provider.generate_image(prompt='x', persona_anchor=_anchor()),
        )


# ─── Video ─────────────────────────────────────────────────────────────────


def test_generate_video_happy_path():
    vid_bytes = b'\x00\x00\x00\x18ftypisom'  # mp4 magic

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                'id': 'vid-1',
                'model': GROK_MODELS['video'],
                'b64_video': _b64(vid_bytes),
                'mime': 'video/mp4',
                'width': 1080,
                'height': 1920,
                'duration_s': 15.0,
                'cost_units': 0.75,
            },
        )

    provider = _make_provider(handler)
    result = asyncio.run(
        provider.generate_video(prompt='reel beach', persona_anchor=_anchor()),
    )
    assert isinstance(result, VideoResult)
    assert result.video_bytes == vid_bytes
    assert result.duration_s == 15.0
    assert result.provider_meta['request_id'] == 'vid-1'


# ─── TTS ───────────────────────────────────────────────────────────────────


def test_synthesize_speech_happy_path():
    audio = b'\xff\xfb\x90\x44'  # mp3 frame magic

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                'id': 'tts-1',
                'model': GROK_MODELS['tts'],
                'b64_audio': _b64(audio),
                'mime': 'audio/mpeg',
                'duration_s': 3.2,
                'sample_rate': 24000,
                'chars_used': 50,
            },
        )

    provider = _make_provider(handler)
    result = asyncio.run(
        provider.synthesize_speech(text='hola mundo', persona_anchor=_anchor()),
    )
    assert isinstance(result, AudioResult)
    assert result.audio_bytes == audio
    assert result.sample_rate == 24000
    assert result.cost_units == 50


# ─── STT ───────────────────────────────────────────────────────────────────


def test_transcribe_happy_path():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                'id': 'stt-1',
                'model': GROK_MODELS['stt'],
                'text': 'hola, ¿cómo estás?',
                'language': 'es',
                'confidence': 0.92,
                'audio_seconds': 3.6,
            },
        )

    provider = _make_provider(handler)
    result = asyncio.run(
        provider.transcribe(audio_bytes=b'audio-payload'),
    )
    assert isinstance(result, TranscriptResult)
    assert result.text == 'hola, ¿cómo estás?'
    assert result.language == 'es'
    assert result.confidence == 0.92


# ─── Health check ──────────────────────────────────────────────────────────


def test_health_check_returns_true_on_200():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={'status': 'ok'})

    provider = _make_provider(handler)
    assert asyncio.run(provider.health_check()) is True


def test_health_check_returns_false_on_5xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    provider = _make_provider(handler)
    assert asyncio.run(provider.health_check()) is False
