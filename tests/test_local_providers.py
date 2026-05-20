"""Tests para los 3 providers locales (TASK-INFLU-006):
``OllamaProvider``, ``LocalSDXLProvider``, ``LocalWhisperProvider``.

Mismo patrón que tests/test_cloud_providers.py — httpx.MockTransport,
happy path + 1 error por provider.
"""
from __future__ import annotations

import asyncio
import base64

import httpx
import pytest

from app.services.influencer.providers.base import (
    ImageResult,
    PersonaAnchor,
    ProviderContentRejected,
    ProviderTimeoutError,
    ProviderUnavailable,
    TextResult,
    TranscriptResult,
)
from app.services.influencer.providers.local_sdxl import LocalSDXLProvider
from app.services.influencer.providers.local_whisper import LocalWhisperProvider
from app.services.influencer.providers.ollama import OllamaProvider


def _anchor() -> PersonaAnchor:
    return PersonaAnchor(
        persona_id='p1',
        reference_image_urls=('https://s3/face.jpg',),
        style_tokens=('resort wear',),
        voice_tone='cercana',
    )


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode('ascii')


# ─── Ollama ────────────────────────────────────────────────────────────────


def test_ollama_generate_text_happy_path():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == '/api/generate'
        return httpx.Response(
            200,
            json={
                'model': 'llama3.1:8b',
                'response': 'hola desde ollama',
                'done': True,
                'eval_count': 25,
                'total_duration': 1_500_000_000,
            },
        )

    provider = OllamaProvider(timeout=2.0, transport=httpx.MockTransport(handler))
    result = asyncio.run(provider.generate_text(prompt='hola', persona_anchor=_anchor()))
    assert isinstance(result, TextResult)
    assert result.text == 'hola desde ollama'
    assert result.finish_reason == 'stop'
    assert result.provider_meta['eval_count'] == 25


def test_ollama_health_check_tags_endpoint():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == '/api/tags'
        return httpx.Response(200, json={'models': []})

    provider = OllamaProvider(timeout=2.0, transport=httpx.MockTransport(handler))
    assert asyncio.run(provider.health_check()) is True


def test_ollama_unavailable_on_5xx():
    def handler(_):
        return httpx.Response(503, json={})

    provider = OllamaProvider(timeout=1.0, transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderUnavailable):
        asyncio.run(provider.generate_text(prompt='x'))


def test_ollama_timeout():
    async def slow(_):
        await asyncio.sleep(10)
        return httpx.Response(200, json={})

    provider = OllamaProvider(timeout=1.0, transport=httpx.MockTransport(slow))
    with pytest.raises(ProviderTimeoutError):
        asyncio.run(provider.generate_text(prompt='x'))


# ─── LocalSDXL ─────────────────────────────────────────────────────────────


def test_local_sdxl_generate_image_happy_path():
    img = b'\x89PNG\r\n\x1a\n'

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == '/sdapi/v1/txt2img'
        body = request.read().decode()
        # IP-Adapter debería estar en payload porque persona_anchor tiene refs
        assert 'IP-Adapter' in body
        return httpx.Response(200, json={'images': [_b64(img)]})

    provider = LocalSDXLProvider(timeout=2.0, transport=httpx.MockTransport(handler))
    results = asyncio.run(
        provider.generate_image(prompt='girl', persona_anchor=_anchor()),
    )
    assert len(results) == 1
    assert isinstance(results[0], ImageResult)
    assert results[0].image_bytes == img
    assert results[0].provider_meta['steps'] == 30


def test_local_sdxl_nsfw_rejected():
    def handler(_):
        return httpx.Response(400, json={'detail': 'nsfw content detected'})

    provider = LocalSDXLProvider(timeout=1.0, transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderContentRejected):
        asyncio.run(
            provider.generate_image(prompt='x', persona_anchor=_anchor()),
        )


def test_local_sdxl_no_ipadapter_without_refs():
    """Si la persona no tiene reference_image_urls, NO se inyecta IP-Adapter."""
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        assert 'IP-Adapter' not in body
        return httpx.Response(200, json={'images': []})

    provider = LocalSDXLProvider(timeout=2.0, transport=httpx.MockTransport(handler))
    anchor = PersonaAnchor(persona_id='p', reference_image_urls=())
    asyncio.run(provider.generate_image(prompt='x', persona_anchor=anchor))


# ─── LocalWhisper ──────────────────────────────────────────────────────────


def test_local_whisper_transcribe_happy_path():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == '/v1/audio/transcriptions'
        return httpx.Response(
            200,
            json={
                'text': 'hola, ¿cómo estás?',
                'language': 'es',
                'confidence': 0.95,
                'duration': 4.2,
            },
        )

    provider = LocalWhisperProvider(timeout=2.0, transport=httpx.MockTransport(handler))
    result = asyncio.run(provider.transcribe(audio_bytes=b'fake-mp3', language='es'))
    assert isinstance(result, TranscriptResult)
    assert result.text == 'hola, ¿cómo estás?'
    assert result.language == 'es'
    assert result.confidence == 0.95


def test_local_whisper_unavailable_on_connection_error():
    def handler(_):
        raise httpx.ConnectError('connection refused')

    provider = LocalWhisperProvider(timeout=1.0, transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderUnavailable):
        asyncio.run(provider.transcribe(audio_bytes=b'x'))
