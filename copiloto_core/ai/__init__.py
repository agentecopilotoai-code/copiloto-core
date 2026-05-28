"""``copiloto_core.ai`` — Capa transversal de proveedores de IA del core.

Cualquier módulo opt-in instalado sobre el core que necesite IA
(generación de texto, imagen, video, voz, transcripción) consume estos
adapters vía ``dispatch()``. Los módulos no instancian providers
directamente — el dispatcher resuelve provider activo + circuit breaker
+ audit por cada call.

Contrato público (estable; documentado en `ARCHITECTURE.md` §6):

  - **Registry**: ``resolve_provider(conn, modality) -> ResolvedProvider``,
    ``MODALITIES``, ``_cache_invalidate`` (test-only).
  - **Dispatcher**: ``dispatch(conn, modality, call_fn, audit_conn) -> Any``,
    ``DispatchAudit``, ``CB_FAILURE_THRESHOLD/WINDOW_SECONDS/COOLDOWN_SECONDS``,
    ``_breakers_reset`` (test-only).
  - **Providers**: 5 interfaces abstractas + adapters concretos
    (Grok, Anthropic, OpenAI, ElevenLabs, Ollama, LocalSDXL, LocalWhisper).
  - **Results & Anchor**: 5 dataclasses ``*Result`` + ``PersonaAnchor``.
  - **Exceptions**: ``ProviderError`` + 4 subclases tipadas.
"""
from __future__ import annotations

from copiloto_core.ai.dispatcher import (
    CB_COOLDOWN_SECONDS,
    CB_FAILURE_THRESHOLD,
    CB_WINDOW_SECONDS,
    DispatchAudit,
    _breakers_reset,
    dispatch,
)
from copiloto_core.ai.providers.anthropic import AnthropicProvider
from copiloto_core.ai.providers.base import (
    AudioResult,
    IAProvider,
    ImageProvider,
    ImageResult,
    LLMProvider,
    PersonaAnchor,
    ProviderContentRejected,
    ProviderError,
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
from copiloto_core.ai.providers.elevenlabs import ElevenLabsProvider
from copiloto_core.ai.providers.grok import GrokProvider
from copiloto_core.ai.providers.local_sdxl import LocalSDXLProvider
from copiloto_core.ai.providers.local_whisper import LocalWhisperProvider
from copiloto_core.ai.providers.ollama import OllamaProvider
from copiloto_core.ai.providers.openai import OpenAIProvider
from copiloto_core.ai.registry import (
    MODALITIES,
    PROVIDER_CACHE_TTL_SECONDS,
    ResolvedProvider,
    _cache_invalidate,
    resolve_provider,
)


__all__ = [
    # Registry
    'MODALITIES',
    'PROVIDER_CACHE_TTL_SECONDS',
    'ResolvedProvider',
    '_cache_invalidate',
    'resolve_provider',
    # Dispatcher
    'CB_COOLDOWN_SECONDS',
    'CB_FAILURE_THRESHOLD',
    'CB_WINDOW_SECONDS',
    'DispatchAudit',
    '_breakers_reset',
    'dispatch',
    # Interfaces
    'IAProvider',
    'LLMProvider',
    'ImageProvider',
    'VideoProvider',
    'TTSProvider',
    'STTProvider',
    # Results & Anchor
    'TextResult',
    'ImageResult',
    'VideoResult',
    'AudioResult',
    'TranscriptResult',
    'PersonaAnchor',
    # Exceptions
    'ProviderError',
    'ProviderTimeoutError',
    'ProviderRateLimited',
    'ProviderContentRejected',
    'ProviderUnavailable',
    # Adapters concretos
    'AnthropicProvider',
    'ElevenLabsProvider',
    'GrokProvider',
    'LocalSDXLProvider',
    'LocalWhisperProvider',
    'OllamaProvider',
    'OpenAIProvider',
]
