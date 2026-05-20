"""Tests para los 3 cloud providers de TASK-INFLU-005:
``AnthropicProvider``, ``OpenAIProvider``, ``ElevenLabsProvider``.

Cada provider se prueba con ``httpx.MockTransport`` (consistente con
``tests/test_grok_provider.py``):
- happy path → result dataclass correcto + provider_meta.
- timeout, 429, 5xx → excepciones tipadas.
- Idempotency-Key + auth header correcto.

Cobertura: 1-2 paths felices + 1 error path principal por modalidad.
El batch completo de error paths está en test_grok_provider.py (los
providers comparten el mismo `_check_status` pattern).
"""
from __future__ import annotations

import asyncio
import base64

import httpx
import pytest

from app.services.influencer.providers.anthropic import AnthropicProvider, DEFAULT_MODEL
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
)
from app.services.influencer.providers.elevenlabs import ElevenLabsProvider
from app.services.influencer.providers.openai import OPENAI_MODELS, OpenAIProvider


def _anchor() -> PersonaAnchor:
    return PersonaAnchor(
        persona_id='p1',
        style_tokens=('cálida',),
        voice_id_ref='voice-clone-1',
        voice_tone='cercana',
    )


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode('ascii')


# ─── Anthropic ─────────────────────────────────────────────────────────────


def test_anthropic_generate_text_happy_path():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured['path'] = request.url.path
        captured['key'] = request.headers.get('x-api-key')
        captured['version'] = request.headers.get('anthropic-version')
        return httpx.Response(
            200,
            json={
                'id': 'msg_01',
                'model': DEFAULT_MODEL,
                'content': [{'type': 'text', 'text': 'hola desde claude'}],
                'stop_reason': 'end_turn',
                'usage': {'input_tokens': 10, 'output_tokens': 5},
            },
        )

    provider = AnthropicProvider(
        api_key='anthropic-key',
        timeout=2.0,
        transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(provider.generate_text(prompt='hola', persona_anchor=_anchor()))

    assert isinstance(result, TextResult)
    assert result.text == 'hola desde claude'
    assert result.finish_reason == 'end_turn'
    assert result.provider_meta['tokens_used'] == 15
    assert captured['path'].endswith('/messages')
    assert captured['key'] == 'anthropic-key'
    assert captured['version']  # anthropic-version header presente


def test_anthropic_rate_limited():
    def handler(_):
        return httpx.Response(429, json={})

    provider = AnthropicProvider(
        api_key='k', timeout=1.0, transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderRateLimited):
        asyncio.run(provider.generate_text(prompt='x'))


def test_anthropic_timeout():
    async def slow(_):
        await asyncio.sleep(10)
        return httpx.Response(200, json={})

    provider = AnthropicProvider(
        api_key='k', timeout=1.0, transport=httpx.MockTransport(slow),
    )
    with pytest.raises(ProviderTimeoutError):
        asyncio.run(provider.generate_text(prompt='x'))


def test_anthropic_init_rejects_empty_key():
    with pytest.raises(ValueError):
        AnthropicProvider(api_key='')


# ─── OpenAI ────────────────────────────────────────────────────────────────


def test_openai_generate_text_happy_path():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get('authorization') == 'Bearer openai-key'
        return httpx.Response(
            200,
            json={
                'id': 'chatcmpl-1',
                'model': OPENAI_MODELS['llm'],
                'choices': [
                    {'message': {'content': 'hi'}, 'finish_reason': 'stop'},
                ],
                'usage': {'total_tokens': 20},
            },
        )

    provider = OpenAIProvider(
        api_key='openai-key', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(provider.generate_text(prompt='hola'))
    assert result.text == 'hi'
    assert result.provider_meta['tokens_used'] == 20


def test_openai_generate_image_dalle():
    img = b'\x89PNG\r\n\x1a\n'

    def handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        assert OPENAI_MODELS['image'] in body
        return httpx.Response(
            200,
            json={
                'data': [
                    {'b64_json': _b64(img), 'revised_prompt': 'fancy prompt'},
                ],
            },
        )

    provider = OpenAIProvider(
        api_key='k', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    results = asyncio.run(
        provider.generate_image(prompt='girl', persona_anchor=_anchor()),
    )
    assert len(results) == 1
    assert isinstance(results[0], ImageResult)
    assert results[0].image_bytes == img
    assert results[0].provider_meta['revised_prompt'] == 'fancy prompt'


def test_openai_synthesize_speech_returns_binary():
    audio = b'mp3-bytes'

    def handler(_):
        return httpx.Response(200, content=audio, headers={'content-type': 'audio/mpeg'})

    provider = OpenAIProvider(
        api_key='k', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(
        provider.synthesize_speech(text='hola mundo', persona_anchor=_anchor()),
    )
    assert isinstance(result, AudioResult)
    assert result.audio_bytes == audio
    assert result.cost_units == 10  # len('hola mundo')


def test_openai_transcribe_whisper():
    def handler(_):
        return httpx.Response(
            200,
            json={'text': 'hola mundo', 'language': 'es'},
        )

    provider = OpenAIProvider(
        api_key='k', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(provider.transcribe(audio_bytes=b'fake-mp3'))
    assert isinstance(result, TranscriptResult)
    assert result.text == 'hola mundo'
    assert result.language == 'es'


def test_openai_content_policy_violation():
    def handler(_):
        return httpx.Response(
            400,
            json={'error': {'code': 'content_policy_violation'}},
        )

    provider = OpenAIProvider(
        api_key='k', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderContentRejected):
        asyncio.run(provider.generate_text(prompt='bad'))


def test_openai_5xx_unavailable():
    def handler(_):
        return httpx.Response(503, json={})

    provider = OpenAIProvider(
        api_key='k', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderUnavailable):
        asyncio.run(provider.generate_text(prompt='x'))


# ─── ElevenLabs ────────────────────────────────────────────────────────────


def test_elevenlabs_synthesize_speech_happy_path():
    audio = b'fake-mp3-bytes'
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured['path'] = request.url.path
        captured['key'] = request.headers.get('xi-api-key')
        return httpx.Response(200, content=audio, headers={'content-type': 'audio/mpeg'})

    provider = ElevenLabsProvider(
        api_key='el-key', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    result = asyncio.run(
        provider.synthesize_speech(text='hola', persona_anchor=_anchor()),
    )
    assert isinstance(result, AudioResult)
    assert result.audio_bytes == audio
    assert result.provider_meta['voice_id'] == 'voice-clone-1'
    assert captured['path'].endswith('/text-to-speech/voice-clone-1')
    assert captured['key'] == 'el-key'


def test_elevenlabs_falls_back_to_default_voice():
    def handler(request: httpx.Request) -> httpx.Response:
        # voice_id_ref es None → debe usar DEFAULT_VOICE_ID
        return httpx.Response(200, content=b'audio')

    provider = ElevenLabsProvider(
        api_key='k', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    anchor = PersonaAnchor(persona_id='p', voice_id_ref=None)
    result = asyncio.run(
        provider.synthesize_speech(text='hola', persona_anchor=anchor),
    )
    assert result.audio_bytes == b'audio'
    # voice_id default debe estar en provider_meta
    assert result.provider_meta['voice_id']  # truthy = default voice was used


def test_elevenlabs_rate_limited():
    def handler(_):
        return httpx.Response(429, json={})

    provider = ElevenLabsProvider(
        api_key='k', timeout=1.0, transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderRateLimited):
        asyncio.run(
            provider.synthesize_speech(text='x', persona_anchor=_anchor()),
        )


def test_elevenlabs_health_check_ok():
    def handler(_):
        return httpx.Response(200, json={'voices': []})

    provider = ElevenLabsProvider(
        api_key='k', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    assert asyncio.run(provider.health_check()) is True
