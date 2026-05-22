"""Tests para ``app.ai.providers.factory.make_adapter_for_provider``.

Cubre el "último paso" del wire-up provider config → adapter instance,
que antes estaba stubeado con ``NotImplementedError`` en el worker.

Estrategia: monkey-patch ``resolve_secret_ref`` para devolver una key
falsa (no leemos del filesystem) y verificamos:
- Cada provider name conocido se mapea a la clase concreta esperada.
- Providers de cloud sin secret resoluble → ``ProviderUnavailable``.
- Providers locales (ollama, local_sdxl, local_whisper) NO consultan
  ``secret_ref``.
- ``resolved.model`` se propaga al constructor (vía ``models`` dict o
  ``model`` string según la firma del adapter).
- Provider name desconocido → ``ValueError``.
"""
from __future__ import annotations

import pytest

from app.ai.providers import factory
from app.ai.providers.anthropic import AnthropicProvider
from app.ai.providers.base import ProviderUnavailable
from app.ai.providers.elevenlabs import ElevenLabsProvider
from app.ai.providers.grok import GrokProvider
from app.ai.providers.local_sdxl import LocalSDXLProvider
from app.ai.providers.local_whisper import LocalWhisperProvider
from app.ai.providers.ollama import OllamaProvider
from app.ai.providers.openai import OpenAIProvider
from app.ai.registry import ResolvedProvider


def _resolved(
    provider: str,
    modality: str = 'image',
    secret_ref: str | None = 'secrets/test-key',
    model: str | None = None,
    params: dict | None = None,
) -> ResolvedProvider:
    return ResolvedProvider(
        modality=modality,
        provider=provider,
        secret_ref=secret_ref,
        model=model,
        params=params or {},
        source='db',
    )


@pytest.fixture
def fake_secret(monkeypatch):
    """Sustituye resolve_secret_ref para devolver una key falsa estable."""
    monkeypatch.setattr(
        factory, 'resolve_secret_ref', lambda ref: 'fake-key-NEVER-LEAK' if ref else None,
    )


# ─── Cloud providers (require API key) ─────────────────────────────────────


def test_grok_provider_instantiated(fake_secret):
    adapter = factory.make_adapter_for_provider(_resolved('grok'))
    assert isinstance(adapter, GrokProvider)


def test_openai_provider_instantiated(fake_secret):
    adapter = factory.make_adapter_for_provider(_resolved('openai'))
    assert isinstance(adapter, OpenAIProvider)


def test_anthropic_provider_instantiated(fake_secret):
    adapter = factory.make_adapter_for_provider(_resolved('anthropic', modality='llm'))
    assert isinstance(adapter, AnthropicProvider)


def test_elevenlabs_provider_instantiated(fake_secret):
    adapter = factory.make_adapter_for_provider(_resolved('elevenlabs', modality='tts'))
    assert isinstance(adapter, ElevenLabsProvider)


def test_cloud_provider_without_resolvable_secret_raises_unavailable(monkeypatch):
    # resolve_secret_ref devuelve None → factory debe levantar ProviderUnavailable.
    monkeypatch.setattr(factory, 'resolve_secret_ref', lambda ref: None)
    with pytest.raises(ProviderUnavailable) as exc:
        factory.make_adapter_for_provider(_resolved('grok'))
    assert 'grok' in str(exc.value)
    assert 'secret_ref' in str(exc.value)


def test_cloud_provider_with_none_secret_ref_raises(monkeypatch):
    # secret_ref=None debe levantar antes de intentar resolver.
    monkeypatch.setattr(factory, 'resolve_secret_ref', lambda ref: 'should-not-be-called')
    with pytest.raises(ProviderUnavailable):
        factory.make_adapter_for_provider(_resolved('openai', secret_ref=None))


# ─── Local providers (no API key) ──────────────────────────────────────────


def test_ollama_provider_instantiated_without_secret():
    # Sin monkeypatch — ollama no debe tocar resolve_secret_ref.
    adapter = factory.make_adapter_for_provider(
        _resolved('ollama', modality='llm', secret_ref=None),
    )
    assert isinstance(adapter, OllamaProvider)


def test_local_sdxl_provider_instantiated_without_secret():
    adapter = factory.make_adapter_for_provider(
        _resolved('local_sdxl', secret_ref=None),
    )
    assert isinstance(adapter, LocalSDXLProvider)


def test_local_whisper_provider_instantiated_without_secret():
    adapter = factory.make_adapter_for_provider(
        _resolved('local_whisper', modality='stt', secret_ref=None),
    )
    assert isinstance(adapter, LocalWhisperProvider)


# ─── Model + params propagation ────────────────────────────────────────────


def test_grok_with_explicit_model_maps_to_modality(fake_secret):
    """`resolved.model='grok-2-image'` debe llegar al adapter via models dict."""
    adapter = factory.make_adapter_for_provider(
        _resolved('grok', modality='image', model='grok-2-image-custom'),
    )
    assert isinstance(adapter, GrokProvider)
    # GrokProvider expone models en _models (private), pero el contrato
    # público es que el modelo se use en la próxima llamada. Verificamos
    # vía el atributo interno por simplicidad del test.
    assert adapter._models.get('image') == 'grok-2-image-custom'


def test_anthropic_with_explicit_model(fake_secret):
    adapter = factory.make_adapter_for_provider(
        _resolved('anthropic', modality='llm', model='claude-sonnet-4-5'),
    )
    assert isinstance(adapter, AnthropicProvider)


def test_params_base_url_propagates(fake_secret):
    """Si `params` trae `base_url`, debe pasarse al constructor."""
    adapter = factory.make_adapter_for_provider(
        _resolved('grok', params={'base_url': 'https://test.x.ai/v1'}),
    )
    assert adapter._base_url == 'https://test.x.ai/v1'


def test_params_timeout_propagates(fake_secret):
    adapter = factory.make_adapter_for_provider(
        _resolved('grok', params={'timeout': 30.0}),
    )
    assert adapter._timeout == 30.0


# ─── Error paths ───────────────────────────────────────────────────────────


def test_unknown_provider_raises_value_error(fake_secret):
    with pytest.raises(ValueError) as exc:
        factory.make_adapter_for_provider(_resolved('made-up-provider'))
    assert 'made-up-provider' in str(exc.value)
    # El mensaje debe listar los providers válidos.
    assert 'grok' in str(exc.value)
    assert 'openai' in str(exc.value)


def test_empty_provider_name_raises(fake_secret):
    with pytest.raises(ValueError):
        factory.make_adapter_for_provider(_resolved(''))


def test_provider_name_case_insensitive(fake_secret):
    """`provider='GROK'` debe normalizarse a lowercase."""
    adapter = factory.make_adapter_for_provider(_resolved('GROK'))
    assert isinstance(adapter, GrokProvider)


# ─── params/model override por provider (cobertura branches) ───────────────
# Cada provider tiene 2-3 branches `if (base_url|timeout|model)` que solo
# se ejercitan cuando esos params vienen presentes. Los tests anteriores
# solo ejercían el camino default (sin overrides). Estos parametrizan
# los 7 providers para subir coverage del factory.


@pytest.mark.parametrize(
    'provider_name,expected_cls,needs_secret',
    [
        ('grok', GrokProvider, True),
        ('openai', OpenAIProvider, True),
        ('anthropic', AnthropicProvider, True),
        ('elevenlabs', ElevenLabsProvider, True),
        ('ollama', OllamaProvider, False),
        ('local_sdxl', LocalSDXLProvider, False),
        ('local_whisper', LocalWhisperProvider, False),
    ],
)
def test_each_provider_accepts_base_url_and_timeout_override(
    fake_secret, provider_name, expected_cls, needs_secret,
):
    """Ejerce el branch `if (base_url := ...)` + `if (timeout := ...)` de
    cada provider. Sin esto, factory.py queda con ~80% coverage."""
    secret = 'secrets/test-key' if needs_secret else None
    adapter = factory.make_adapter_for_provider(_resolved(
        provider_name,
        modality='llm',
        secret_ref=secret,
        params={'base_url': 'https://custom.local/v1', 'timeout': 45.0},
    ))
    assert isinstance(adapter, expected_cls)
    assert adapter._base_url == 'https://custom.local/v1'
    assert adapter._timeout == 45.0


@pytest.mark.parametrize(
    'provider_name,expected_cls,needs_secret',
    [
        ('anthropic', AnthropicProvider, True),
        ('elevenlabs', ElevenLabsProvider, True),
        ('ollama', OllamaProvider, False),
        ('local_sdxl', LocalSDXLProvider, False),
        ('local_whisper', LocalWhisperProvider, False),
    ],
)
def test_providers_with_simple_model_string(
    fake_secret, provider_name, expected_cls, needs_secret,
):
    """Estos 5 adapters toman `model: str` (no dict). Verifica que
    `resolved.model` se propaga al constructor."""
    secret = 'secrets/test-key' if needs_secret else None
    adapter = factory.make_adapter_for_provider(_resolved(
        provider_name,
        modality='llm',
        secret_ref=secret,
        model='custom-model-v1',
    ))
    assert isinstance(adapter, expected_cls)
    # Atributo interno _model — el contrato público es que el modelo se
    # use en la próxima llamada; verificamos vía atributo por simplicidad.
    assert adapter._model == 'custom-model-v1'


@pytest.mark.parametrize('provider_name', ['grok', 'openai'])
def test_multimodal_providers_accept_models_dict_in_params(fake_secret, provider_name):
    """Grok y OpenAI toman `models: dict[modality, model_name]`. El
    factory debe aceptar el dict desde `params['models']` (rama
    `isinstance(models, dict)`)."""
    adapter = factory.make_adapter_for_provider(_resolved(
        provider_name,
        modality='image',
        params={'models': {'image': 'custom-img', 'video': 'custom-vid'}},
    ))
    assert adapter._models.get('image') == 'custom-img'
    assert adapter._models.get('video') == 'custom-vid'


def test_openai_with_model_string_maps_to_modality(fake_secret):
    """OpenAI: si viene `resolved.model` sin `params.models`, se mapea al
    modality del resolved (rama `elif resolved.model`)."""
    adapter = factory.make_adapter_for_provider(_resolved(
        'openai', modality='image', model='dall-e-3',
    ))
    assert adapter._models.get('image') == 'dall-e-3'
