"""Static tests for TASK-INFLU-003 — IAProvider abstract.

Verifica el contrato de las interfaces + dataclasses + excepciones sin
necesidad de instanciar un provider concreto. Los adapters reales
(GrokProvider, AnthropicProvider, ...) viven en TASK-INFLU-004+ y traen
sus propios tests con mocks de httpx.
"""
from __future__ import annotations

import inspect

import pytest


# ─── Excepciones tipadas ───────────────────────────────────────────────────


def test_exception_hierarchy() -> None:
    """Las 4 excepciones específicas heredan de ``ProviderError`` para
    que un ``except ProviderError`` del dispatcher las capture todas.
    """
    from app.services.influencer.providers.base import (
        ProviderContentRejected,
        ProviderError,
        ProviderRateLimited,
        ProviderTimeoutError,
        ProviderUnavailable,
    )

    for exc_class in (
        ProviderTimeoutError,
        ProviderRateLimited,
        ProviderContentRejected,
        ProviderUnavailable,
    ):
        assert issubclass(exc_class, ProviderError), exc_class
        assert issubclass(exc_class, Exception)


# ─── Result dataclasses ────────────────────────────────────────────────────


def test_result_dataclasses_are_frozen() -> None:
    """Los results deben ser inmutables — el worker los persiste tal cual
    y un mutate accidental rompería el invariante.
    """
    from app.services.influencer.providers.base import (
        AudioResult,
        ImageResult,
        TextResult,
        TranscriptResult,
        VideoResult,
    )

    for result_class in (
        TextResult,
        ImageResult,
        VideoResult,
        AudioResult,
        TranscriptResult,
    ):
        # `frozen=True` declara la metadata `__dataclass_params__.frozen`.
        params = getattr(result_class, '__dataclass_params__', None)
        assert params is not None, f'{result_class.__name__} no es dataclass'
        assert params.frozen is True, f'{result_class.__name__} debe ser frozen'


def test_result_dataclasses_carry_provider_meta_and_cost() -> None:
    """Todos los results comparten ``provider_meta``, ``cost_units``,
    ``elapsed_ms`` para auditoría y métrica Prometheus uniforme.
    """
    from app.services.influencer.providers.base import (
        AudioResult,
        ImageResult,
        TextResult,
        TranscriptResult,
        VideoResult,
    )

    for result_class in (
        TextResult,
        ImageResult,
        VideoResult,
        AudioResult,
        TranscriptResult,
    ):
        fields = set(result_class.__dataclass_fields__.keys())
        for required in ('provider_meta', 'cost_units', 'elapsed_ms'):
            assert required in fields, (
                f'{result_class.__name__} debe declarar {required}'
            )


def test_text_result_shape() -> None:
    from app.services.influencer.providers.base import TextResult

    result = TextResult(
        text='hola',
        finish_reason='stop',
        provider_meta={'model': 'grok-4.3', 'request_id': 'abc'},
        cost_units=42.0,
        elapsed_ms=123.4,
    )
    assert result.text == 'hola'
    assert result.finish_reason == 'stop'
    assert result.provider_meta['model'] == 'grok-4.3'

    # frozen → no se puede mutar.
    with pytest.raises(AttributeError):
        result.text = 'mutado'  # type: ignore[misc]


def test_image_result_shape() -> None:
    from app.services.influencer.providers.base import ImageResult

    result = ImageResult(
        image_bytes=b'\x89PNG\r\n',
        mime='image/png',
        width=1024,
        height=1024,
        provider_meta={'model': 'grok-imagine-image-quality'},
        cost_units=0.05,
        elapsed_ms=2500.0,
    )
    assert result.image_bytes.startswith(b'\x89PNG')
    assert result.width == 1024


def test_video_result_includes_duration() -> None:
    from app.services.influencer.providers.base import VideoResult

    result = VideoResult(video_bytes=b'fake-mp4', duration_s=15.0)
    assert result.duration_s == 15.0


def test_audio_result_includes_sample_rate() -> None:
    from app.services.influencer.providers.base import AudioResult

    result = AudioResult(audio_bytes=b'fake-mp3', sample_rate=24000)
    assert result.sample_rate == 24000


def test_transcript_result_includes_language_and_confidence() -> None:
    from app.services.influencer.providers.base import TranscriptResult

    result = TranscriptResult(text='hola', language='es', confidence=0.97)
    assert result.language == 'es'
    assert result.confidence == 0.97


# ─── PersonaAnchor ─────────────────────────────────────────────────────────


def test_persona_anchor_frozen_with_minimal_fields() -> None:
    """PersonaAnchor solo requiere ``persona_id``; el resto tiene defaults
    para que LLM-only adapters (que no necesitan face_embedding) puedan
    invocar generate_text sin armar el anchor completo.
    """
    from app.services.influencer.providers.base import PersonaAnchor

    anchor = PersonaAnchor(persona_id='persona-abc')
    assert anchor.persona_id == 'persona-abc'
    assert anchor.face_embedding is None
    assert anchor.reference_image_urls == ()
    assert anchor.style_tokens == ()
    assert anchor.voice_id_ref is None

    # frozen → no se puede mutar.
    with pytest.raises(AttributeError):
        anchor.persona_id = 'otro'  # type: ignore[misc]


def test_persona_anchor_full_shape() -> None:
    from app.services.influencer.providers.base import PersonaAnchor

    anchor = PersonaAnchor(
        persona_id='persona-abc',
        face_embedding=(0.1, 0.2, 0.3),
        body_traits={'silhouette': 'athletic', 'height_cm': 172},
        reference_image_urls=('s3://x/1.jpg', 's3://x/2.jpg'),
        style_tokens=('cálida', 'resort wear'),
        voice_id_ref='eleven-abc-123',
        voice_tone='cálida',
    )
    assert len(anchor.reference_image_urls) == 2
    assert 'cálida' in anchor.style_tokens


# ─── Interfaces abstractas ──────────────────────────────────────────────────


def test_iaprovider_is_abstract() -> None:
    """IAProvider no se puede instanciar directamente — los métodos
    abstractos fuerzan a los adapters a implementarlos.
    """
    from app.services.influencer.providers.base import IAProvider

    with pytest.raises(TypeError):
        IAProvider()  # type: ignore[abstract]


def test_llm_provider_signature() -> None:
    from app.services.influencer.providers.base import LLMProvider

    method = LLMProvider.generate_text
    assert inspect.iscoroutinefunction(method)
    params = inspect.signature(method).parameters
    # Argumentos keyword-only (forzados con `*,` en la firma).
    for arg in ('prompt', 'system', 'max_tokens', 'temperature', 'persona_anchor'):
        assert arg in params, f'LLMProvider.generate_text falta {arg}'


def test_image_provider_signature_requires_persona_anchor() -> None:
    """ImageProvider.generate_image hace ``persona_anchor`` obligatorio
    (sin default) para garantizar consistencia entre generaciones del
    mismo personaje. Si alguien lo deja default a None se rompe el
    invariante de producto.
    """
    from app.services.influencer.providers.base import ImageProvider

    method = ImageProvider.generate_image
    assert inspect.iscoroutinefunction(method)
    params = inspect.signature(method).parameters
    assert 'persona_anchor' in params

    persona_param = params['persona_anchor']
    assert persona_param.default is inspect.Parameter.empty, (
        'persona_anchor NO debe tener default — siempre requerido'
    )


def test_video_provider_signature_requires_persona_anchor() -> None:
    """Mismo invariante que ImageProvider — sin persona_anchor el video
    no mantendría consistencia visual del personaje.
    """
    from app.services.influencer.providers.base import VideoProvider

    method = VideoProvider.generate_video
    assert inspect.iscoroutinefunction(method)
    params = inspect.signature(method).parameters
    assert params['persona_anchor'].default is inspect.Parameter.empty


def test_tts_provider_signature() -> None:
    from app.services.influencer.providers.base import TTSProvider

    method = TTSProvider.synthesize_speech
    assert inspect.iscoroutinefunction(method)
    params = inspect.signature(method).parameters
    for arg in ('text', 'persona_anchor', 'language', 'sample_rate'):
        assert arg in params


def test_stt_provider_signature() -> None:
    from app.services.influencer.providers.base import STTProvider

    method = STTProvider.transcribe
    assert inspect.iscoroutinefunction(method)
    params = inspect.signature(method).parameters
    for arg in ('audio_bytes', 'mime', 'language'):
        assert arg in params


def test_all_providers_have_provider_name_and_health_check() -> None:
    """Cada interfaz hereda de IAProvider, así que tiene ``provider_name``
    (property abstracta) y ``health_check`` (async abstracta). Verifica
    que el AST de cada interfaz declara ambas explícitamente.
    """
    from app.services.influencer.providers.base import (
        IAProvider,
        ImageProvider,
        LLMProvider,
        STTProvider,
        TTSProvider,
        VideoProvider,
    )

    for iface in (LLMProvider, ImageProvider, VideoProvider, TTSProvider, STTProvider):
        assert issubclass(iface, IAProvider), iface
        # Métodos heredados del base + el suyo propio.
        members = dict(inspect.getmembers(iface))
        assert 'provider_name' in members
        assert 'health_check' in members


def test_safety_mode_defaults_to_true() -> None:
    """Image/Video providers: ``safety_mode`` default True. Un adapter que
    instale default False sería un riesgo de seguridad — el invariante
    es "safety on by default, opt-out explícito".
    """
    from app.services.influencer.providers.base import ImageProvider, VideoProvider

    for cls, method_name in (
        (ImageProvider, 'generate_image'),
        (VideoProvider, 'generate_video'),
    ):
        params = inspect.signature(getattr(cls, method_name)).parameters
        assert params['safety_mode'].default is True, (
            f'{cls.__name__}.{method_name}.safety_mode debe default True'
        )


def test_package_exports() -> None:
    """`app.services.influencer.providers` exporta los nombres canónicos
    para que los adapters concretos puedan hacer
    ``from ... import LLMProvider`` sin profundizar al módulo `.base`.
    """
    from app.services.influencer import providers

    expected = {
        'LLMProvider', 'ImageProvider', 'VideoProvider', 'TTSProvider', 'STTProvider',
        'TextResult', 'ImageResult', 'VideoResult', 'AudioResult', 'TranscriptResult',
        'PersonaAnchor',
        'ProviderError', 'ProviderTimeoutError', 'ProviderRateLimited',
        'ProviderContentRejected', 'ProviderUnavailable',
    }
    actual = set(providers.__all__)
    missing = expected - actual
    assert not missing, f'faltan exports: {missing}'
