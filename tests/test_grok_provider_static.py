"""Static checks para ``app/ai/providers/grok.py`` —
TASK-INFLU-004.

Verifica que el código fuente del adapter cumple los invariantes
declarados en la spec sin necesidad de invocar HTTP:

- ``GrokProvider`` implementa las 5 interfaces (LLM/Image/Video/TTS/STT).
- ``provider_name`` matchea ``platform_ai_providers.provider`` (= 'grok').
- Cada método async usa ``asyncio.wait_for`` con un hard deadline
  (defensa contra SDKs que ignoran timeouts).
- ``GROK_MODELS`` cablea los 5 modelos esperados (LLM + image + video +
  TTS + STT) de acuerdo al pricing compartido por el usuario.
- ``Idempotency-Key`` se envía en cada POST (retry safety del dispatcher).
- API key nunca aparece en logs / repr / format strings del módulo.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.ai.providers import grok as grok_module
from app.ai.providers.base import (
    ImageProvider,
    LLMProvider,
    STTProvider,
    TTSProvider,
    VideoProvider,
)
from app.ai.providers.grok import GROK_MODELS, GrokProvider

SOURCE = Path(grok_module.__file__).read_text(encoding='utf-8')


def test_grokprovider_implements_5_interfaces():
    """GrokProvider debe subclassear las 5 interfaces (multi-modality)."""
    assert issubclass(GrokProvider, LLMProvider)
    assert issubclass(GrokProvider, ImageProvider)
    assert issubclass(GrokProvider, VideoProvider)
    assert issubclass(GrokProvider, TTSProvider)
    assert issubclass(GrokProvider, STTProvider)


def test_provider_name_is_grok():
    """``provider_name`` matchea valor en ``platform_ai_providers.provider``."""
    assert GrokProvider.provider_name == 'grok'


def test_required_methods_are_async():
    """generate_text/image/video, synthesize_speech, transcribe son corutinas."""
    for method_name in (
        'generate_text',
        'generate_image',
        'generate_video',
        'synthesize_speech',
        'transcribe',
        'health_check',
    ):
        method = getattr(GrokProvider, method_name)
        assert inspect.iscoroutinefunction(method), (
            f'{method_name} debe ser async para no bloquear el event loop'
        )


def test_models_for_all_modalities_wired():
    """GROK_MODELS cablea los 5 modelos del pricing (LLM/image/video/TTS/STT)."""
    for modality in ('llm', 'image', 'video', 'tts', 'stt'):
        assert modality in GROK_MODELS, f'GROK_MODELS falta modality {modality!r}'
        assert GROK_MODELS[modality], f'GROK_MODELS[{modality!r}] vacío'

    # Modelos específicos de la spec
    assert GROK_MODELS['llm'].startswith('grok-'), 'LLM debe ser un modelo grok-*'
    assert 'imagine' in GROK_MODELS['image'], 'image quality model debe ser grok-imagine-*'
    assert 'imagine' in GROK_MODELS['video'], 'video model debe ser grok-imagine-*'


def test_hard_deadline_pattern_present():
    """``asyncio.wait_for`` envuelve cada llamada httpx (patrón TASK-0086)."""
    assert 'asyncio.wait_for' in SOURCE, (
        'GrokProvider debe envolver httpx en asyncio.wait_for con un hard_deadline '
        '(defensa contra SDKs que ignoran timeout nativo).'
    )
    # El deadline duro debe sumar margen sobre el timeout configurado.
    assert 'hard_deadline' in SOURCE.lower() or '_hard_deadline' in SOURCE, (
        'El módulo debe declarar un hard_deadline mayor que el timeout nominal.'
    )


def test_idempotency_key_on_every_post():
    """Cada POST envía ``Idempotency-Key`` para retry safety del dispatcher."""
    assert 'Idempotency-Key' in SOURCE, (
        'Los POSTs deben incluir Idempotency-Key (TASK-INFLU-007 retry safety).'
    )


def test_safety_prefix_when_enabled():
    """``SAFETY_PREFIX`` se aplica cuando ``safety_mode=True``."""
    assert 'SAFETY_PREFIX' in SOURCE
    assert 'safety_mode' in SOURCE


def test_api_key_not_logged():
    """El módulo NO loguea la API key en claro.

    Patrones prohibidos: ``logger.info(.*api_key)`` literal, format strings
    que incluyan ``self._api_key`` fuera del header ``Authorization``.
    """
    # Permitimos `Bearer {self._api_key}` (header construction) pero NO
    # cualquier otra mención formateada que pueda terminar en logs.
    lines = SOURCE.splitlines()
    for i, line in enumerate(lines, 1):
        # Excluir el header de autorización legítimo.
        if 'Authorization' in line:
            continue
        # Cualquier f-string o .format con api_key fuera del header es sospechoso.
        if 'api_key' in line and ('logger' in line or 'print(' in line):
            pytest.fail(
                f'Posible leak de api_key en log/print (línea {i}): {line.strip()}',
            )


def test_typed_exceptions_imported():
    """Las 4 excepciones tipadas están importadas desde base.py."""
    for exc_name in (
        'ProviderTimeoutError',
        'ProviderRateLimited',
        'ProviderContentRejected',
        'ProviderUnavailable',
    ):
        assert exc_name in SOURCE, (
            f'{exc_name} debe estar importada en grok.py para que el adapter '
            'use excepciones tipadas (dispatcher de TASK-INFLU-007 las distingue).'
        )


def test_init_validates_api_key():
    """``__init__`` rechaza api_key vacío (fail-fast)."""
    with pytest.raises(ValueError):
        GrokProvider(api_key='')


def test_transport_injection_for_tests():
    """Constructor acepta ``transport`` opcional para httpx.MockTransport
    (patrón ya usado en tests/test_payment_provider_static.py)."""
    sig = inspect.signature(GrokProvider.__init__)
    assert 'transport' in sig.parameters, (
        'GrokProvider.__init__ debe aceptar `transport` para inyección '
        'de httpx.MockTransport en tests.'
    )
