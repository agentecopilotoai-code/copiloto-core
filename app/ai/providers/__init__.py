"""Provider adapters de IA del core.

Cada proveedor (Grok, Anthropic, OpenAI, ElevenLabs, Ollama, SDXL local,
Whisper local) implementa una o más de las 5 interfaces abstractas
declaradas en ``base``:

    - LLMProvider   → generación de texto
    - ImageProvider → generación de imágenes
    - VideoProvider → generación de video
    - TTSProvider   → text-to-speech
    - STTProvider   → speech-to-text

Cualquier módulo opt-in que necesite IA consume estos adapters vía
``app.ai.dispatcher.dispatch()`` — el dispatcher resuelve el provider
activo via ``app.ai.registry`` y lo invoca sin conocer detalles del SDK.

Política: ningún adapter recibe ``tenant_id`` como parámetro. La config
del proveedor es global a la plataforma; el tenant nunca decide modelos.
"""
from app.ai.providers.base import (
    AudioResult,
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
    TextResult,
    TranscriptResult,
    TTSProvider,
    VideoProvider,
    VideoResult,
)

__all__ = [
    'AudioResult',
    'ImageProvider',
    'ImageResult',
    'LLMProvider',
    'PersonaAnchor',
    'ProviderContentRejected',
    'ProviderError',
    'ProviderRateLimited',
    'ProviderTimeoutError',
    'ProviderUnavailable',
    'STTProvider',
    'TextResult',
    'TTSProvider',
    'TranscriptResult',
    'VideoProvider',
    'VideoResult',
]
