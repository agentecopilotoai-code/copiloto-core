"""Factory: ``ResolvedProvider`` → instancia concreta de ``IAProvider``.

Este módulo es el "último paso" del wire-up: cualquier consumer de IA
llama a ``dispatch()`` que resuelve el provider configurado por el
platform_owner, y para cada intento llama a un ``call_fn(resolved)``.
Ese ``call_fn`` necesita una forma uniforme de mapear el nombre del
provider a una clase de adapter + resolver el ``secret_ref`` opaco a la
API key real.

Patrón:

    >>> from copiloto_core.ai.providers.factory import make_adapter_for_provider
    >>> adapter = make_adapter_for_provider(resolved)
    >>> result = await adapter.generate_image(...)

Providers soportados (matchean ``platform_ai_providers.provider``):

    'grok'           → GrokProvider (multimodal: llm/image/video/tts/stt)
    'openai'         → OpenAIProvider (llm/image)
    'anthropic'      → AnthropicProvider (llm)
    'ollama'         → OllamaProvider (llm local, sin api_key)
    'elevenlabs'     → ElevenLabsProvider (tts)
    'local_sdxl'     → LocalSDXLProvider (image local)
    'local_whisper'  → LocalWhisperProvider (stt local)

Resolución de secrets: para providers de cloud, lee del entorno via
``resolve_secret_ref(secret_ref)``. Si el secret es requerido pero no se
puede resolver, levanta ``ProviderUnavailable`` — el dispatcher lo trata
como retryable (útil cuando la clave aún no está montada en el pod).
"""
from __future__ import annotations

from typing import Any

from copiloto_core.ai.providers.anthropic import AnthropicProvider
from copiloto_core.ai.providers.base import IAProvider, ProviderUnavailable
from copiloto_core.ai.providers.elevenlabs import ElevenLabsProvider
from copiloto_core.ai.providers.grok import GrokProvider
from copiloto_core.ai.providers.local_sdxl import LocalSDXLProvider
from copiloto_core.ai.providers.local_whisper import LocalWhisperProvider
from copiloto_core.ai.providers.ollama import OllamaProvider
from copiloto_core.ai.providers.openai import OpenAIProvider
from copiloto_core.ai.registry import ResolvedProvider
from copiloto_core.services.secret_resolver import resolve_secret_ref
from copiloto_core.services.url_safety import UrlSafetyError, check_provider_url

# Providers de cloud que requieren API key (lectura desde secret_ref).
_CLOUD_PROVIDERS: frozenset[str] = frozenset({'grok', 'openai', 'anthropic', 'elevenlabs'})


def _require_api_key(resolved: ResolvedProvider) -> str:
    """Resuelve el secret_ref → api_key real. Levanta si no se puede."""
    api_key = resolve_secret_ref(resolved.secret_ref) if resolved.secret_ref else None
    if not api_key:
        raise ProviderUnavailable(
            f'{resolved.provider}: secret_ref={resolved.secret_ref!r} '
            f'no se pudo resolver (clave no montada en el pod)',
        )
    return api_key


def _params_get(params: Any, key: str, default: Any = None) -> Any:
    """Lee ``params[key]`` defensivamente — params puede ser dict|None."""
    if isinstance(params, dict):
        return params.get(key, default)
    return default


def _safe_base_url(params: Any, provider: str) -> str | None:
    """SEC-023 (audit#4) — replica el guard SSRF al instanciar el adapter.

    El write-path (admin_routes._reject_unsafe_provider_url) lo valida
    al PATCH; este es defense-in-depth para casos donde la DB se
    pre-pobló sin validación o se corrompió. Si la URL es unsafe
    para el `provider` (e.g. private-IP para `grok` cloud) levantamos
    `ProviderUnavailable` que el dispatcher trata como retryable —
    abrirá el breaker y caerá al fallback.

    Args:
      params: `ResolvedProvider.params` dict (puede ser None/non-dict).
      provider: nombre canónico del provider — decide cloud vs local.

    Returns:
      La base_url si es safe; ``None`` si no había configurada.

    Raises:
      ProviderUnavailable: si la URL existe pero es unsafe.
    """
    base_url = _params_get(params, 'base_url')
    if not base_url:
        return None
    try:
        check_provider_url(base_url, provider=provider, field='params.base_url')
    except UrlSafetyError as exc:
        raise ProviderUnavailable(
            f'{provider}: refused unsafe base_url — {exc}',
        ) from exc
    return base_url


def make_adapter_for_provider(resolved: ResolvedProvider) -> IAProvider:
    """Instancia el adapter concreto para el ``ResolvedProvider`` dado.

    No es async — los constructores de los adapters son síncronos. La
    única operación I/O es ``resolve_secret_ref()`` que lee del
    filesystem (mounted volume con la key).

    Para providers locales (ollama, local_sdxl, local_whisper) no se
    consulta el secret_ref — leen ``params['base_url']`` o el default.

    Args:
        resolved: snapshot de ``platform_ai_providers`` resuelto por
            ``copiloto_core.ai.registry.resolve_provider()``.

    Returns:
        Instancia concreta del adapter, lista para llamar
        ``generate_text/image/video/synthesize_speech/transcribe`` según
        la modalidad.

    Raises:
        ProviderUnavailable: si el provider requiere api_key y no se
            puede resolver el secret_ref. Esto es retryable según
            ``dispatch()``.
        ValueError: si el provider name no está en el catálogo (config
            corrupta en DB — no debería pasar si los CHECK constraints
            están bien).
    """
    name = (resolved.provider or '').strip().lower()
    params = resolved.params or {}

    if name == 'grok':
        kwargs: dict[str, Any] = {'api_key': _require_api_key(resolved)}
        if (base_url := _safe_base_url(params, name)):
            kwargs['base_url'] = base_url
        if (timeout := _params_get(params, 'timeout')):
            kwargs['timeout'] = float(timeout)
        # Grok acepta dict {modality: model} para overrides; si solo viene
        # `model` en ResolvedProvider, mapearlo al modality del resolved.
        models = _params_get(params, 'models')
        if isinstance(models, dict):
            kwargs['models'] = models
        elif resolved.model:
            kwargs['models'] = {resolved.modality: resolved.model}
        return GrokProvider(**kwargs)

    if name == 'openai':
        kwargs = {'api_key': _require_api_key(resolved)}
        if (base_url := _safe_base_url(params, name)):
            kwargs['base_url'] = base_url
        if (timeout := _params_get(params, 'timeout')):
            kwargs['timeout'] = float(timeout)
        models = _params_get(params, 'models')
        if isinstance(models, dict):
            kwargs['models'] = models
        elif resolved.model:
            kwargs['models'] = {resolved.modality: resolved.model}
        return OpenAIProvider(**kwargs)

    if name == 'anthropic':
        kwargs = {'api_key': _require_api_key(resolved)}
        if (base_url := _safe_base_url(params, name)):
            kwargs['base_url'] = base_url
        if (timeout := _params_get(params, 'timeout')):
            kwargs['timeout'] = float(timeout)
        if resolved.model:
            kwargs['model'] = resolved.model
        return AnthropicProvider(**kwargs)

    if name == 'elevenlabs':
        kwargs = {'api_key': _require_api_key(resolved)}
        if (base_url := _safe_base_url(params, name)):
            kwargs['base_url'] = base_url
        if (timeout := _params_get(params, 'timeout')):
            kwargs['timeout'] = float(timeout)
        if resolved.model:
            kwargs['model'] = resolved.model
        return ElevenLabsProvider(**kwargs)

    if name == 'ollama':
        kwargs = {}
        if (base_url := _safe_base_url(params, name)):
            kwargs['base_url'] = base_url
        if (timeout := _params_get(params, 'timeout')):
            kwargs['timeout'] = float(timeout)
        if resolved.model:
            kwargs['model'] = resolved.model
        return OllamaProvider(**kwargs)

    if name == 'local_sdxl':
        kwargs = {}
        if (base_url := _safe_base_url(params, name)):
            kwargs['base_url'] = base_url
        if (timeout := _params_get(params, 'timeout')):
            kwargs['timeout'] = float(timeout)
        if resolved.model:
            kwargs['model'] = resolved.model
        return LocalSDXLProvider(**kwargs)

    if name == 'local_whisper':
        kwargs = {}
        if (base_url := _safe_base_url(params, name)):
            kwargs['base_url'] = base_url
        if (timeout := _params_get(params, 'timeout')):
            kwargs['timeout'] = float(timeout)
        if resolved.model:
            kwargs['model'] = resolved.model
        return LocalWhisperProvider(**kwargs)

    raise ValueError(
        f'unknown provider {name!r} (modality={resolved.modality}); '
        f'expected one of: grok, openai, anthropic, elevenlabs, '
        f'ollama, local_sdxl, local_whisper',
    )


__all__ = ['make_adapter_for_provider']
