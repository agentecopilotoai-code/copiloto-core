"""Provider adapters del módulo Influencer / Ravit Studio.

Cada proveedor (Grok, Anthropic, OpenAI, ElevenLabs, Ollama, SDXL local,
Whisper local) implementa una o más de las 5 interfaces abstractas
declaradas en ``base``:

    - LLMProvider   → generación de texto (captions, descripciones, decisiones)
    - ImageProvider → generación de imágenes (fotos, escenas, anuncios visuales)
    - VideoProvider → generación de video (reels, historias, anuncios)
    - TTSProvider   → text-to-speech (voz del personaje)
    - STTProvider   → speech-to-text (transcripción de audio inputs)

La interfaz es la fuente de verdad — los adapters concretos (TASK-INFLU-004+)
implementan estos métodos. El dispatcher de TASK-INFLU-007 resuelve el
provider activo via ``app.services.influencer.provider_registry`` y lo invoca
sin conocer detalles del SDK específico.

Política D3: ningún adapter recibe ``tenant_id`` como parámetro. La config
del proveedor es global a la plataforma; el tenant nunca decide modelos.
"""
from app.services.influencer.providers.base import (
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
