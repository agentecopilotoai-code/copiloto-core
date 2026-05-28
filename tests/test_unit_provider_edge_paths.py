"""M45.4 — cubre branches faltantes en local_sdxl/local_whisper/openai
helpers que no requieren mock httpx complejo.
"""
from __future__ import annotations

import base64
import binascii

import pytest


# ─── local_sdxl helpers ───────────────────────────────────────────────────


def test_format_to_wh_known_aspects():
    from copiloto_core.ai.providers.local_sdxl import _format_to_wh
    assert _format_to_wh('1:1') == (1024, 1024)
    assert _format_to_wh('9:16') == (768, 1344)
    assert _format_to_wh('16:9') == (1344, 768)
    assert _format_to_wh('4:5') == (896, 1120)
    # unknown → default 1:1
    assert _format_to_wh('weird') == (1024, 1024)


def test_build_ipadapter_args_empty():
    from copiloto_core.ai.providers.base import PersonaAnchor
    from copiloto_core.ai.providers.local_sdxl import _build_ipadapter_args
    anchor = PersonaAnchor(persona_id='p')
    assert _build_ipadapter_args(anchor, None) == {}


def test_build_ipadapter_args_with_refs():
    from copiloto_core.ai.providers.base import PersonaAnchor
    from copiloto_core.ai.providers.local_sdxl import _build_ipadapter_args
    anchor = PersonaAnchor(
        persona_id='p',
        reference_image_urls=('https://x/a.png',),
    )
    out = _build_ipadapter_args(anchor, 'https://y/b.png')
    assert 'IP-Adapter' in out
    refs = out['IP-Adapter']['args'][0]['reference_images']
    assert 'https://x/a.png' in refs
    assert 'https://y/b.png' in refs


def test_build_ipadapter_args_only_extra_ref():
    from copiloto_core.ai.providers.base import PersonaAnchor
    from copiloto_core.ai.providers.local_sdxl import _build_ipadapter_args
    anchor = PersonaAnchor(persona_id='p')
    out = _build_ipadapter_args(anchor, 'https://z/c.png')
    assert out['IP-Adapter']['args'][0]['reference_images'] == ['https://z/c.png']


def test_decode_b64_empty():
    from copiloto_core.ai.providers.local_sdxl import _decode_b64
    assert _decode_b64('') == b''
    assert _decode_b64(None) == b''


def test_decode_b64_valid():
    from copiloto_core.ai.providers.local_sdxl import _decode_b64
    data = b'hello world'
    encoded = base64.b64encode(data).decode()
    assert _decode_b64(encoded) == data


def test_decode_b64_invalid_raises():
    from copiloto_core.ai.providers.base import ProviderUnavailable
    from copiloto_core.ai.providers.local_sdxl import _decode_b64
    # b64decode(validate=False) tolera basura; necesitamos algo que sí rompa.
    # Pasamos un objeto incompatible → TypeError no es atrapado, así que
    # mejor probamos un input cuya longitud no es múltiplo de 4 + sin padding:
    # Force a real binascii.Error → "Invalid base64-encoded string" via
    # incorrect padding length.
    with pytest.raises((ProviderUnavailable, ValueError, binascii.Error)):
        _decode_b64('YWJj=garbage')


# ─── openai helpers / model defaults ──────────────────────────────────────


def test_openai_models_defaults():
    from copiloto_core.ai.providers.openai import OPENAI_MODELS
    assert OPENAI_MODELS['llm']
    assert OPENAI_MODELS['image']


def test_openai_provider_constructor_with_custom_models():
    from copiloto_core.ai.providers.openai import OpenAIProvider
    p = OpenAIProvider(api_key='sk-x', models={'llm': 'gpt-x'})
    assert p._models['llm'] == 'gpt-x'


def test_openai_provider_default_models():
    from copiloto_core.ai.providers.openai import OpenAIProvider, OPENAI_MODELS
    p = OpenAIProvider(api_key='sk-x')
    assert p._models['llm'] == OPENAI_MODELS['llm']


def test_format_to_dalle_size_branches():
    from copiloto_core.ai.providers.openai import _format_to_dalle_size
    assert _format_to_dalle_size('1:1') == '1024x1024'
    assert _format_to_dalle_size('9:16') == '1024x1792'
    assert _format_to_dalle_size('16:9') == '1792x1024'
    # unknown → default 1024x1024
    assert _format_to_dalle_size('weird') == '1024x1024'


# ─── local_whisper helpers ────────────────────────────────────────────────


def test_local_whisper_constructor_defaults():
    from copiloto_core.ai.providers.local_whisper import LocalWhisperProvider
    p = LocalWhisperProvider()
    assert p._base_url
    assert p._timeout > 0


def test_local_whisper_constructor_custom():
    from copiloto_core.ai.providers.local_whisper import LocalWhisperProvider
    p = LocalWhisperProvider(base_url='http://x:9000', timeout=60.0)
    assert p._base_url == 'http://x:9000'
    assert p._timeout == 60.0
