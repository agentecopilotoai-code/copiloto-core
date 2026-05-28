"""M45 — cobertura completa de `copiloto_core.ai.providers.factory` (antes 0%)."""
from __future__ import annotations

import pytest

from copiloto_core.ai.providers.anthropic import AnthropicProvider
from copiloto_core.ai.providers.base import ProviderUnavailable
from copiloto_core.ai.providers.elevenlabs import ElevenLabsProvider
from copiloto_core.ai.providers.factory import (
    _CLOUD_PROVIDERS,
    _params_get,
    _require_api_key,
    make_adapter_for_provider,
)
from copiloto_core.ai.providers.grok import GrokProvider
from copiloto_core.ai.providers.local_sdxl import LocalSDXLProvider
from copiloto_core.ai.providers.local_whisper import LocalWhisperProvider
from copiloto_core.ai.providers.ollama import OllamaProvider
from copiloto_core.ai.providers.openai import OpenAIProvider
from copiloto_core.ai.registry import ResolvedProvider


# ─── Fixtures ──────────────────────────────────────────────────────────────


def _resolved(provider, modality='llm', secret_ref='env:FOO', model=None, params=None):
    return ResolvedProvider(
        modality=modality,
        provider=provider,
        secret_ref=secret_ref,
        model=model,
        params=params or {},
        source='db',
    )


@pytest.fixture
def patched_secret(monkeypatch):
    """Hace que `resolve_secret_ref()` devuelva una key dummy para los
    providers de cloud. Pasa `monkeypatch.setattr` al SITE donde el factory
    importa la función."""
    from copiloto_core.ai.providers import factory as fmod

    monkeypatch.setattr(fmod, 'resolve_secret_ref', lambda ref: 'sk-test-1234567890')
    return fmod


# ─── _params_get ──────────────────────────────────────────────────────────


def test_params_get_dict():
    assert _params_get({'a': 1}, 'a') == 1


def test_params_get_dict_default():
    assert _params_get({'a': 1}, 'b', default=42) == 42


def test_params_get_none():
    assert _params_get(None, 'a', default='X') == 'X'


def test_params_get_non_dict():
    assert _params_get('not a dict', 'a', default='X') == 'X'


# ─── _require_api_key ─────────────────────────────────────────────────────


def test_require_api_key_resolved(patched_secret):
    r = _resolved('grok')
    assert _require_api_key(r) == 'sk-test-1234567890'


def test_require_api_key_unresolved_raises(monkeypatch):
    from copiloto_core.ai.providers import factory as fmod

    monkeypatch.setattr(fmod, 'resolve_secret_ref', lambda ref: None)
    r = _resolved('grok')
    with pytest.raises(ProviderUnavailable) as exc:
        _require_api_key(r)
    assert 'grok' in str(exc.value)
    assert 'env:FOO' in str(exc.value)


def test_require_api_key_no_secret_ref_raises(monkeypatch):
    from copiloto_core.ai.providers import factory as fmod

    monkeypatch.setattr(fmod, 'resolve_secret_ref', lambda ref: 'whatever')
    r = _resolved('grok', secret_ref=None)
    with pytest.raises(ProviderUnavailable):
        _require_api_key(r)


# ─── _CLOUD_PROVIDERS constant ────────────────────────────────────────────


def test_cloud_providers_constant():
    assert _CLOUD_PROVIDERS == frozenset({'grok', 'openai', 'anthropic', 'elevenlabs'})


# ─── make_adapter_for_provider — cada branch ──────────────────────────────


def test_make_grok_minimal(patched_secret):
    r = _resolved('grok')
    adapter = make_adapter_for_provider(r)
    assert isinstance(adapter, GrokProvider)


def test_make_grok_with_params_and_model(patched_secret):
    r = _resolved(
        'grok',
        model='grok-4.3',
        params={'base_url': 'https://x.ai', 'timeout': '30', 'models': {'llm': 'grok-3'}},
    )
    adapter = make_adapter_for_provider(r)
    assert isinstance(adapter, GrokProvider)


def test_make_grok_model_param_falls_to_modality_map(patched_secret):
    r = _resolved('grok', modality='image', model='grok-imagine')
    adapter = make_adapter_for_provider(r)
    assert isinstance(adapter, GrokProvider)


def test_make_openai(patched_secret):
    r = _resolved(
        'openai',
        model='gpt-4o-mini',
        params={'base_url': 'https://api.openai.com/v1', 'timeout': '15'},
    )
    adapter = make_adapter_for_provider(r)
    assert isinstance(adapter, OpenAIProvider)


def test_make_openai_with_models_dict(patched_secret):
    r = _resolved(
        'openai', params={'models': {'llm': 'gpt-4o', 'image': 'dall-e-3'}}
    )
    adapter = make_adapter_for_provider(r)
    assert isinstance(adapter, OpenAIProvider)


def test_make_anthropic(patched_secret):
    r = _resolved(
        'anthropic',
        model='claude-3-5-sonnet',
        params={'base_url': 'https://api.anthropic.com', 'timeout': '20'},
    )
    adapter = make_adapter_for_provider(r)
    assert isinstance(adapter, AnthropicProvider)


def test_make_anthropic_minimal(patched_secret):
    r = _resolved('anthropic')
    adapter = make_adapter_for_provider(r)
    assert isinstance(adapter, AnthropicProvider)


def test_make_elevenlabs(patched_secret):
    r = _resolved(
        'elevenlabs',
        modality='tts',
        model='eleven_multilingual_v2',
        params={'base_url': 'https://api.elevenlabs.io/v1', 'timeout': '25'},
    )
    adapter = make_adapter_for_provider(r)
    assert isinstance(adapter, ElevenLabsProvider)


def test_make_elevenlabs_minimal(patched_secret):
    r = _resolved('elevenlabs', modality='tts')
    adapter = make_adapter_for_provider(r)
    assert isinstance(adapter, ElevenLabsProvider)


def test_make_ollama_no_api_key():
    # Ollama no usa secret_ref → no se invoca resolve_secret_ref.
    r = _resolved('ollama', secret_ref=None, model='llama3', params={'base_url': 'http://x:11434', 'timeout': '60'})
    adapter = make_adapter_for_provider(r)
    assert isinstance(adapter, OllamaProvider)


def test_make_ollama_minimal():
    r = _resolved('ollama', secret_ref=None)
    adapter = make_adapter_for_provider(r)
    assert isinstance(adapter, OllamaProvider)


def test_make_local_sdxl():
    r = _resolved(
        'local_sdxl',
        modality='image',
        secret_ref=None,
        model='sdxl-1.0',
        params={'base_url': 'http://localhost:7860', 'timeout': '120'},
    )
    adapter = make_adapter_for_provider(r)
    assert isinstance(adapter, LocalSDXLProvider)


def test_make_local_sdxl_minimal():
    r = _resolved('local_sdxl', modality='image', secret_ref=None)
    adapter = make_adapter_for_provider(r)
    assert isinstance(adapter, LocalSDXLProvider)


def test_make_local_whisper():
    r = _resolved(
        'local_whisper',
        modality='stt',
        secret_ref=None,
        model='whisper-large-v3',
        params={'base_url': 'http://localhost:9000', 'timeout': '90'},
    )
    adapter = make_adapter_for_provider(r)
    assert isinstance(adapter, LocalWhisperProvider)


def test_make_local_whisper_minimal():
    r = _resolved('local_whisper', modality='stt', secret_ref=None)
    adapter = make_adapter_for_provider(r)
    assert isinstance(adapter, LocalWhisperProvider)


def test_make_unknown_provider_raises():
    r = _resolved('not_a_real_provider', secret_ref=None)
    with pytest.raises(ValueError) as exc:
        make_adapter_for_provider(r)
    assert 'not_a_real_provider' in str(exc.value)


def test_make_handles_uppercase_and_whitespace(patched_secret):
    # Factory normaliza con .strip().lower().
    r = _resolved('  GROK  ')
    adapter = make_adapter_for_provider(r)
    assert isinstance(adapter, GrokProvider)


def test_make_empty_provider_name_raises():
    r = _resolved('', secret_ref=None)
    with pytest.raises(ValueError):
        make_adapter_for_provider(r)


def test_make_none_provider_raises():
    # ResolvedProvider is a frozen dataclass, can't have None for str field,
    # but factory uses (resolved.provider or '').strip().lower(). Test the
    # empty string branch (None coerces).
    r = ResolvedProvider(
        modality='llm', provider='', secret_ref=None,
        model=None, params={}, source='unset',
    )
    with pytest.raises(ValueError):
        make_adapter_for_provider(r)
