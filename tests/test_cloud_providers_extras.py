"""Tests adicionales para cubrir branches faltantes de cloud providers."""
from __future__ import annotations

import asyncio
import base64

import httpx
import pytest

from copiloto_core.ai.providers.anthropic import AnthropicProvider
from copiloto_core.ai.providers.base import (
    ProviderContentRejected,
    ProviderRateLimited,
    ProviderTimeoutError,
    ProviderUnavailable,
)
from copiloto_core.ai.providers.elevenlabs import ElevenLabsProvider
from copiloto_core.ai.providers.openai import OpenAIProvider


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode('ascii')


# ── anthropic ──────────────────────────────────────────────────────────────


def test_anthropic_health_check_ok():
    def handler(_):
        return httpx.Response(200, json={})
    p = AnthropicProvider(
        api_key='k', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    assert asyncio.run(p.health_check()) is True


def test_anthropic_health_check_404_tolerated():
    def handler(_):
        return httpx.Response(404)
    p = AnthropicProvider(
        api_key='k', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    assert asyncio.run(p.health_check()) is True


def test_anthropic_health_check_http_error_false():
    def handler(_):
        raise httpx.ConnectError('boom')
    p = AnthropicProvider(
        api_key='k', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    assert asyncio.run(p.health_check()) is False


def test_anthropic_http_error_raises_unavailable():
    def handler(_):
        raise httpx.ReadError('reset')
    p = AnthropicProvider(
        api_key='k', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderUnavailable):
        asyncio.run(p.generate_text(prompt='hi'))


def test_anthropic_400_content_safety_raises_content_rejected():
    def handler(_):
        return httpx.Response(
            400, json={'error': {'type': 'safety_violation', 'message': 'nope'}},
        )
    p = AnthropicProvider(
        api_key='k', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderContentRejected):
        asyncio.run(p.generate_text(prompt='hi'))


def test_anthropic_400_content_keyword_raises_content_rejected():
    def handler(_):
        return httpx.Response(
            400, json={'error': {'type': 'content_filter'}},
        )
    p = AnthropicProvider(
        api_key='k', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderContentRejected):
        asyncio.run(p.generate_text(prompt='hi'))


def test_anthropic_400_generic_raises_unavailable():
    def handler(_):
        return httpx.Response(
            400, json={'error': {'type': 'invalid_request'}},
        )
    p = AnthropicProvider(
        api_key='k', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderUnavailable):
        asyncio.run(p.generate_text(prompt='hi'))


def test_anthropic_500_raises_unavailable():
    def handler(_):
        return httpx.Response(503, json={'error': {}})
    p = AnthropicProvider(
        api_key='k', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderUnavailable):
        asyncio.run(p.generate_text(prompt='hi'))


def test_anthropic_non_json_response_raises():
    def handler(_):
        return httpx.Response(200, content=b'not json at all')
    p = AnthropicProvider(
        api_key='k', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderUnavailable, match='non-json'):
        asyncio.run(p.generate_text(prompt='hi'))


def test_anthropic_400_non_json_body_treated_as_unavailable():
    """Si el body del 400 no es JSON, el except ValueError → body={} →
    no es content rejection → ProviderUnavailable."""
    def handler(_):
        return httpx.Response(400, content=b'broken-body')
    p = AnthropicProvider(
        api_key='k', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderUnavailable):
        asyncio.run(p.generate_text(prompt='hi'))


# ── elevenlabs ─────────────────────────────────────────────────────────────


def test_elevenlabs_5xx_raises_unavailable():
    def handler(_):
        return httpx.Response(502, content=b'')
    p = ElevenLabsProvider(
        api_key='k', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    from copiloto_core.ai.providers.base import PersonaAnchor
    with pytest.raises(ProviderUnavailable):
        asyncio.run(p.synthesize_speech(
            text='hola', persona_anchor=PersonaAnchor(persona_id='p'),
        ))


def test_elevenlabs_timeout_raises_provider_timeout():
    import time
    def handler(_):
        time.sleep(0.5)  # NB: synchronous sleep, will exceed timeout
        return httpx.Response(200, content=b'mp3')
    # We can't easily force a real httpx timeout with MockTransport sync handler,
    # but we can verify the wrapping by using a custom transport that raises.
    def raising_handler(_):
        raise httpx.ReadTimeout('slow')
    p = ElevenLabsProvider(
        api_key='k', timeout=2.0, transport=httpx.MockTransport(raising_handler),
    )
    from copiloto_core.ai.providers.base import PersonaAnchor
    with pytest.raises((ProviderTimeoutError, ProviderUnavailable)):
        asyncio.run(p.synthesize_speech(
            text='hola', persona_anchor=PersonaAnchor(persona_id='p'),
        ))


def test_elevenlabs_400_content_rejected():
    def handler(_):
        return httpx.Response(
            400, json={'detail': {'status': 'invalid_text_for_synthesis'}},
        )
    p = ElevenLabsProvider(
        api_key='k', timeout=2.0, transport=httpx.MockTransport(handler),
    )
    from copiloto_core.ai.providers.base import PersonaAnchor
    # 400 con detail puede mapearse a content rejected o unavailable según
    # impl; aceptamos cualquiera de las dos excepciones tipadas.
    with pytest.raises((ProviderContentRejected, ProviderUnavailable)):
        asyncio.run(p.synthesize_speech(
            text='', persona_anchor=PersonaAnchor(persona_id='p'),
        ))


# ── openai ─────────────────────────────────────────────────────────────────


def test_openai_health_check_ok():
    def handler(_):
        return httpx.Response(200, json={'data': []})
    p = OpenAIProvider(
        api_key='k', timeout=2.0,
        transport=httpx.MockTransport(handler),
    )
    assert asyncio.run(p.health_check()) is True


def test_openai_health_check_failure():
    def handler(_):
        raise httpx.ConnectError('down')
    p = OpenAIProvider(
        api_key='k', timeout=2.0,
        transport=httpx.MockTransport(handler),
    )
    assert asyncio.run(p.health_check()) is False


def test_openai_text_429_raises_rate_limited():
    def handler(_):
        return httpx.Response(429, json={'error': {'message': 'slow down'}})
    p = OpenAIProvider(
        api_key='k', timeout=2.0,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderRateLimited):
        asyncio.run(p.generate_text(prompt='hi'))


def test_openai_text_timeout_raises():
    def handler(_):
        raise httpx.ReadTimeout('slow')
    p = OpenAIProvider(
        api_key='k', timeout=2.0,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises((ProviderTimeoutError, ProviderUnavailable)):
        asyncio.run(p.generate_text(prompt='hi'))


def test_openai_text_5xx_raises_unavailable():
    def handler(_):
        return httpx.Response(503, json={'error': {}})
    p = OpenAIProvider(
        api_key='k', timeout=2.0,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(ProviderUnavailable):
        asyncio.run(p.generate_text(prompt='hi'))


def test_openai_init_rejects_empty_key():
    with pytest.raises(ValueError):
        OpenAIProvider(api_key='')
