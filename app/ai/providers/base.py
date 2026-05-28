"""Interfaces abstractas + dataclasses para los proveedores IA del core.

Cada adapter concreto (Grok, Anthropic, OpenAI, ElevenLabs, Ollama, SDXL,
Whisper) implementa una o más de estas interfaces. El dispatcher selecciona
el adapter activo via ``app.ai.registry.resolve_provider`` y delega la
llamada sin conocer el SDK específico — eso permite cambiar provider a
nivel platform sin tocar el código de los módulos opt-in.

Diseño:

- **Interfaces async**: todas las operaciones son corutinas. Los adapters
  cloud usan ``httpx.AsyncClient`` o el SDK async oficial; los locales
  (Ollama/SDXL/Whisper) usan ``httpx`` async contra el endpoint local. El
  hot path (worker de generación) NO bloquea el event loop nunca.
- **Result dataclasses frozen**: cada operación devuelve un objeto inmutable
  con bytes + meta + cost — el worker del módulo opt-in persiste eso tal
  cual en sus propias tablas (e.g. assets + credit_ledger).
- **PersonaAnchor**: encapsula los rasgos visuales/voz del personaje
  (face_embedding, body_traits, reference URLs) para que los adapters
  de imagen/video mantengan consistencia entre generaciones del mismo
  personaje. No es opcional para image/video — sin él la cara cambia
  entre prompts y rompe la promesa de producto (un personaje consistente).
- **Excepciones tipadas**: el dispatcher (TASK-INFLU-007) distingue
  ``ProviderTimeoutError`` (retry con fallback chain) vs
  ``ProviderContentRejected`` (no retry, marcar generation failed con
  refund) vs ``ProviderRateLimited`` (backoff + fallback) vs
  ``ProviderUnavailable`` (circuit breaker).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx


# ─── PersistentHttpxClient (PERF-021 audit#4) ─────────────────────────────


class PersistentHttpxClient:
    """Wrapper que expone `httpx.AsyncClient` vía protocolo
    async-context-manager **sin cerrarlo al salir**.

    Existe porque el call-pattern legado de los providers IA era::

        async with self._client() as c:
            ...

    y eso destruía la `AsyncClient` (handshake TCP+TLS) en cada call.
    Refactor PERF-021 (audit#4) convirtió `_client()` a un singleton
    lazy-init, pero todos los call-sites siguen usando `async with`.
    Este wrapper hace ese patrón un no-op (preserva la conn pool) sin
    tocar 14+ call-sites en 7 providers.

    El cleanup real vive en `Provider.aclose()` (al shutdown del worker).
    """

    __slots__ = ('_client',)

    def __init__(self, client: 'httpx.AsyncClient') -> None:
        self._client = client

    async def __aenter__(self) -> 'httpx.AsyncClient':
        return self._client

    async def __aexit__(self, *exc: object) -> None:
        # No-op a propósito — el client singleton sobrevive a este context.
        return None


# ─── Excepciones tipadas ───────────────────────────────────────────────────


class ProviderError(Exception):
    """Base de las excepciones del subsistema de providers."""


class ProviderTimeoutError(ProviderError):
    """El provider tardó más que el deadline duro (``asyncio.wait_for``).

    El dispatcher debe reintentar con el siguiente provider del
    ``fallback_chain`` configurado en ``platform_ai_providers.params``.
    """


class ProviderRateLimited(ProviderError):
    """El provider devolvió 429 / cuota excedida.

    El dispatcher hace backoff exponencial y, si el chain tiene fallback,
    intenta con el siguiente proveedor. El cost_credits del generation
    NO se debita hasta el éxito.

    Attributes:
      retry_after: segundos sugeridos por el provider (header
        ``Retry-After``). Si está presente, el dispatcher debe esperar
        AL MENOS ese tiempo antes del próximo intento contra el MISMO
        provider, y antes de switchear al fallback (PERF-022 audit#4).
        ``None`` si el provider no proporcionó el hint.
    """

    def __init__(self, message: str, *, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after: float | None = retry_after


class ProviderContentRejected(ProviderError):
    """El provider rechazó el prompt o el resultado por safety filter.

    NO se reintenta — el filter probablemente va a rechazar también con
    el siguiente provider del chain. El worker marca la generation
    ``status='failed'`` con ``error='content_rejected'`` y reembolsa los
    créditos al ledger del tenant.
    """


class ProviderUnavailable(ProviderError):
    """El provider está caído (5xx persistente, network unreachable, key
    inválida). El dispatcher abre el circuit breaker por 5 min y
    redirige al siguiente del chain.
    """


# ─── Result dataclasses ────────────────────────────────────────────────────


@dataclass(frozen=True)
class _ProviderResultBase:
    """Campos comunes a todos los results — auditoría + costos.

    - ``provider_meta``: snapshot del provider response útil para audit
      (model, request_id, tokens_used, finish_reason...). NUNCA incluye
      la API key ni el prompt completo — solo metadata operativa.
    - ``cost_units``: cantidad de "units" cobradas por el provider (tokens
      LLM, USD para image generation, segundos de video/audio). El cálculo
      a créditos del tenant lo hace el worker, no el provider.
    - ``elapsed_ms``: para el histogram de Prometheus + alertas.
    """
    provider_meta: dict = field(default_factory=dict)
    cost_units: float = 0.0
    elapsed_ms: float = 0.0


@dataclass(frozen=True)
class TextResult(_ProviderResultBase):
    """Resultado de :meth:`LLMProvider.generate_text`."""
    text: str = ''
    # `finish_reason` viene del SDK del provider (e.g. 'stop', 'length',
    # 'content_filter'). El worker decide si el caption es válido.
    finish_reason: str | None = None


@dataclass(frozen=True)
class ImageResult(_ProviderResultBase):
    """Resultado de :meth:`ImageProvider.generate_image` (una sola imagen).

    El método devuelve una lista — el worker arma el batch a partir de
    ``count`` y persiste cada una en S3 con su propio asset row.
    """
    image_bytes: bytes = b''
    mime: str = 'image/jpeg'
    width: int = 0
    height: int = 0


@dataclass(frozen=True)
class VideoResult(_ProviderResultBase):
    """Resultado de :meth:`VideoProvider.generate_video`."""
    video_bytes: bytes = b''
    mime: str = 'video/mp4'
    width: int = 0
    height: int = 0
    duration_s: float = 0.0


@dataclass(frozen=True)
class AudioResult(_ProviderResultBase):
    """Resultado de :meth:`TTSProvider.synthesize_speech`."""
    audio_bytes: bytes = b''
    mime: str = 'audio/mpeg'
    duration_s: float = 0.0
    sample_rate: int = 0


@dataclass(frozen=True)
class TranscriptResult(_ProviderResultBase):
    """Resultado de :meth:`STTProvider.transcribe`."""
    text: str = ''
    language: str | None = None
    # Confianza promedio del transcript (0..1). None si el provider no la
    # expone.
    confidence: float | None = None


# ─── PersonaAnchor ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PersonaAnchor:
    """Encapsulación de los rasgos del personaje para mantener consistencia
    cross-generation.

    Para image/video providers: ``reference_image_urls`` (1-4 fotos
    canónicas del personaje desde S3) + ``face_embedding`` (vector 512-d
    derivado de la canonical face) + ``style_tokens`` (chips del wizard:
    "cálida", "resort wear", etc.) son el input que el SDK pasa al modelo
    (e.g. IP-Adapter para SDXL, reference images para Grok Imagine).

    Para TTS: ``voice_id_ref`` apunta al voice clone del provider (e.g.
    ElevenLabs voice_id, Grok voice ref). El worker resuelve el ref
    consultando la persona row si está disponible.

    Para LLM: solo ``voice_tone`` y ``style_tokens`` aplican — guían el
    system prompt del caption generator para que mantenga la voz del
    personaje.
    """
    persona_id: str
    # Visual anchoring (image/video)
    face_embedding: tuple[float, ...] | None = None
    body_traits: dict = field(default_factory=dict)
    reference_image_urls: tuple[str, ...] = field(default_factory=tuple)
    style_tokens: tuple[str, ...] = field(default_factory=tuple)
    # Voice anchoring (TTS)
    voice_id_ref: str | None = None
    voice_tone: str | None = None  # 'cálida', 'cercana', etc.


# ─── Interfaces abstractas ──────────────────────────────────────────────────


class IAProvider(ABC):
    """Base abstracta — métodos comunes a todos los providers.

    Concrete adapters override ``provider_name`` con su identificador (e.g.
    'grok', 'anthropic'). El ``health_check`` es invocado por el dispatcher
    + la métrica Prometheus ``ai_provider_health{provider, modality}``
    para detectar caídas.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Identificador único del proveedor (snake_case, matchea valor
        en ``app.platform_ai_providers.provider``)."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Probe rápido (≤ 2s) que valida que el provider está alcanzable.

        Para cloud: HEAD/OPTIONS al endpoint del SDK con la API key.
        Para local (Ollama/SDXL/Whisper): GET al endpoint local.
        Returns True si OK, False si degraded — el dispatcher decide si
        marca circuit breaker.
        """


class LLMProvider(IAProvider):
    """Generación de texto: captions, descripciones, decisiones."""

    @abstractmethod
    async def generate_text(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
        persona_anchor: PersonaAnchor | None = None,
    ) -> TextResult:
        """Genera texto a partir del prompt.

        ``persona_anchor`` es opcional para LLM — se usa para inyectar el
        ``voice_tone`` y ``style_tokens`` al system prompt cuando el worker
        está generando captions en la voz de un personaje específico.
        """


class ImageProvider(IAProvider):
    """Generación de imagen — fotos, escenas, anuncios visuales."""

    @abstractmethod
    async def generate_image(
        self,
        *,
        prompt: str,
        persona_anchor: PersonaAnchor,
        count: int = 1,
        format: str = '1:1',
        safety_mode: bool = True,
        reference_image_url: str | None = None,
    ) -> list[ImageResult]:
        """Genera ``count`` imágenes (típicamente 1-10) consistentes con la
        cara y cuerpo del ``persona_anchor``.

        ``persona_anchor`` NO es opcional — sin él la cara cambia entre
        generaciones del mismo personaje. ``format`` mapea a ratio
        (``1:1``, ``4:5``, ``9:16``, ``16:9``).

        ``safety_mode=True`` (default) instruye al provider a aplicar
        sus filters de SFW + brand safety; ``False`` solo está permitido
        para platform_owners en ciertos tipos de contenido y NUNCA
        bypasa los enforcers de TASK-INFLU-018 (etiqueta IA visible).
        """


class VideoProvider(IAProvider):
    """Generación de video — reels, historias, anuncios."""

    @abstractmethod
    async def generate_video(
        self,
        *,
        prompt: str,
        persona_anchor: PersonaAnchor,
        duration_s: float = 15.0,
        format: str = '9:16',
        safety_mode: bool = True,
        audio_url: str | None = None,
    ) -> VideoResult:
        """Genera un video corto consistente con el ``persona_anchor``.

        ``duration_s`` típicamente 15s (reel) o 60s (anuncio). ``audio_url``
        opcionalmente apunta a un asset TTS pre-generado que el provider
        sincroniza con el video — útil para narración del personaje.
        """


class TTSProvider(IAProvider):
    """Text-to-speech — voz del personaje."""

    @abstractmethod
    async def synthesize_speech(
        self,
        *,
        text: str,
        persona_anchor: PersonaAnchor,
        language: str = 'es',
        sample_rate: int = 24000,
    ) -> AudioResult:
        """Sintetiza ``text`` en la voz del personaje (vía
        ``persona_anchor.voice_id_ref`` para providers con voice cloning,
        e.g. ElevenLabs; o vía ``persona_anchor.voice_tone`` para
        providers genéricos como Grok TTS).
        """


class STTProvider(IAProvider):
    """Speech-to-text — transcripción de audio inputs."""

    @abstractmethod
    async def transcribe(
        self,
        *,
        audio_bytes: bytes,
        mime: str = 'audio/mpeg',
        language: str | None = None,
    ) -> TranscriptResult:
        """Transcribe ``audio_bytes`` a texto.

        ``language`` opcionalmente fuerza el idioma (e.g. 'es'); si es
        None, el provider auto-detecta.
        """


__all__ = [
    # Excepciones
    'PersistentHttpxClient',
    'ProviderError',
    'ProviderTimeoutError',
    'ProviderRateLimited',
    'ProviderContentRejected',
    'ProviderUnavailable',
    # Result dataclasses
    'TextResult',
    'ImageResult',
    'VideoResult',
    'AudioResult',
    'TranscriptResult',
    'PersonaAnchor',
    # Interfaces
    'IAProvider',
    'LLMProvider',
    'ImageProvider',
    'VideoProvider',
    'TTSProvider',
    'STTProvider',
]
