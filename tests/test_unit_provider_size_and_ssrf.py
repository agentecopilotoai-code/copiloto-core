"""Tests para SEC-022 (bytes cap response) y SEC-023 (URL safety en factory).

SEC-022: el dispatcher delega a `_translate_response_status` /
`_check_status` que ahora validan `Content-Length`. Cualquier provider
hostil/buggy con body > 256MB es rechazado pre-lectura.

SEC-023: el factory de adapters valida `params.base_url` contra
`app.services.url_safety.check_provider_url` — defense-in-depth del
write-path que ya valida al PATCH.
"""
from __future__ import annotations

import pytest

from app.ai.providers.base import (
    PROVIDER_RESPONSE_MAX_BYTES,
    ProviderUnavailable,
    assert_response_within_size_limit,
)
from app.services.url_safety import (
    UrlSafetyError,
    check_provider_url,
)


# ─── SEC-022: assert_response_within_size_limit ───────────────────────────


def test_size_limit_passes_when_no_content_length():
    # Sin header → no bloquea (caller debe complementar con stream-cap).
    assert_response_within_size_limit(None, provider='grok', path='/v1/x')


def test_size_limit_passes_when_under_cap():
    assert_response_within_size_limit(
        str(100 * 1024 * 1024),  # 100 MB
        provider='grok', path='/v1/x',
    )


def test_size_limit_blocks_when_over_cap():
    with pytest.raises(ProviderUnavailable, match='too large'):
        assert_response_within_size_limit(
            str(PROVIDER_RESPONSE_MAX_BYTES + 1),
            provider='grok', path='/v1/x',
        )


def test_size_limit_blocks_with_int_arg():
    with pytest.raises(ProviderUnavailable):
        assert_response_within_size_limit(
            PROVIDER_RESPONSE_MAX_BYTES * 2,
            provider='openai', path='/chat',
        )


def test_size_limit_ignores_garbage_header():
    # Header "abc" no es parseable — no bloquea.
    assert_response_within_size_limit(
        'not-a-number', provider='anthropic', path='/messages',
    )


def test_size_limit_respects_custom_cap():
    with pytest.raises(ProviderUnavailable):
        assert_response_within_size_limit(
            '1024',
            provider='x', path='/y',
            cap_bytes=512,
        )


# ─── SEC-023: check_provider_url ──────────────────────────────────────────


def test_url_safety_accepts_https_public_for_cloud():
    check_provider_url('https://api.x.ai/v1', provider='grok')
    check_provider_url('https://api.openai.com/v1', provider='openai')


def test_url_safety_rejects_http_for_cloud():
    with pytest.raises(UrlSafetyError, match='scheme'):
        check_provider_url('http://api.x.ai/v1', provider='grok')


def test_url_safety_rejects_localhost_for_cloud():
    with pytest.raises(UrlSafetyError, match='localhost'):
        check_provider_url('https://localhost:8080', provider='grok')


def test_url_safety_rejects_dot_internal_for_cloud():
    with pytest.raises(UrlSafetyError, match='internal'):
        check_provider_url('https://foo.internal', provider='openai')


def test_url_safety_rejects_dot_local_for_cloud():
    with pytest.raises(UrlSafetyError, match='local'):
        check_provider_url('https://router.local', provider='anthropic')


def test_url_safety_rejects_aws_metadata_ip_for_cloud():
    with pytest.raises(UrlSafetyError, match='link-local|169.254'):
        check_provider_url('https://169.254.169.254/latest/meta-data', provider='grok')


def test_url_safety_rejects_rfc1918_for_cloud():
    with pytest.raises(UrlSafetyError, match='private|10.0'):
        check_provider_url('https://10.0.0.1/api', provider='openai')
    with pytest.raises(UrlSafetyError):
        check_provider_url('https://192.168.1.1/api', provider='openai')
    with pytest.raises(UrlSafetyError):
        check_provider_url('https://172.16.0.5/api', provider='openai')


def test_url_safety_rejects_loopback_for_cloud():
    with pytest.raises(UrlSafetyError):
        check_provider_url('https://127.0.0.1', provider='grok')


def test_url_safety_rejects_missing_host():
    with pytest.raises(UrlSafetyError, match='hostname missing'):
        check_provider_url('https://', provider='grok')


def test_url_safety_allows_localhost_for_local_provider():
    # Ollama / SDXL / Whisper son LOCAL_PROVIDERS — permiten localhost.
    check_provider_url('http://localhost:11434', provider='ollama')
    check_provider_url('http://localhost:7860', provider='local_sdxl')
    check_provider_url('http://localhost:9001', provider='local_whisper')


def test_url_safety_allows_private_ip_for_local_provider():
    # Un sdxl-server detrás de tu firewall en 10.0.x.x es legítimo.
    check_provider_url('http://10.0.0.10:7860', provider='local_sdxl')


def test_url_safety_explicit_strict_overrides_provider():
    # Forzar strict=True a un local provider lo trata como cloud.
    with pytest.raises(UrlSafetyError):
        check_provider_url(
            'http://localhost:11434', provider='ollama', strict=True,
        )


def test_url_safety_explicit_lax_overrides_provider():
    # Forzar strict=False a un cloud provider lo permite (no recomendado).
    check_provider_url(
        'http://localhost:9999', provider='grok', strict=False,
    )


# ─── SEC-023: factory rejects unsafe base_url ─────────────────────────────


def test_factory_rejects_unsafe_base_url_for_grok(monkeypatch):
    from app.ai.providers.factory import make_adapter_for_provider
    from app.ai.registry import ResolvedProvider

    # Mock secret_resolver para que api_key esté presente.
    monkeypatch.setattr(
        'app.ai.providers.factory.resolve_secret_ref',
        lambda ref: 'xai-test-key',
    )
    resolved = ResolvedProvider(
        modality='llm', provider='grok',
        secret_ref='env/XAI_API_KEY', model='grok-2',
        params={'base_url': 'http://169.254.169.254/v1'},  # AWS metadata
        source='db',
    )
    with pytest.raises(ProviderUnavailable, match='unsafe base_url'):
        make_adapter_for_provider(resolved)


def test_factory_rejects_localhost_for_openai(monkeypatch):
    from app.ai.providers.factory import make_adapter_for_provider
    from app.ai.registry import ResolvedProvider

    monkeypatch.setattr(
        'app.ai.providers.factory.resolve_secret_ref',
        lambda ref: 'sk-test',
    )
    resolved = ResolvedProvider(
        modality='llm', provider='openai',
        secret_ref='env/OPENAI_API_KEY', model='gpt-4o-mini',
        params={'base_url': 'https://localhost:8080'},
        source='db',
    )
    with pytest.raises(ProviderUnavailable, match='localhost'):
        make_adapter_for_provider(resolved)


def test_factory_accepts_valid_https_for_cloud(monkeypatch):
    from app.ai.providers.factory import make_adapter_for_provider
    from app.ai.providers.openai import OpenAIProvider
    from app.ai.registry import ResolvedProvider

    monkeypatch.setattr(
        'app.ai.providers.factory.resolve_secret_ref',
        lambda ref: 'sk-test',
    )
    resolved = ResolvedProvider(
        modality='llm', provider='openai',
        secret_ref='env/OPENAI_API_KEY', model='gpt-4o-mini',
        params={'base_url': 'https://api.openai.com/v1'},
        source='db',
    )
    adapter = make_adapter_for_provider(resolved)
    assert isinstance(adapter, OpenAIProvider)


def test_factory_accepts_localhost_for_ollama():
    from app.ai.providers.factory import make_adapter_for_provider
    from app.ai.providers.ollama import OllamaProvider
    from app.ai.registry import ResolvedProvider

    resolved = ResolvedProvider(
        modality='llm', provider='ollama',
        secret_ref=None, model='llama3.1:8b',
        params={'base_url': 'http://localhost:11434'},
        source='db',
    )
    adapter = make_adapter_for_provider(resolved)
    assert isinstance(adapter, OllamaProvider)


def test_factory_no_base_url_is_ok(monkeypatch):
    """Sin `base_url` configurada, el provider usa default — no validate."""
    from app.ai.providers.factory import make_adapter_for_provider
    from app.ai.providers.grok import GrokProvider
    from app.ai.registry import ResolvedProvider

    monkeypatch.setattr(
        'app.ai.providers.factory.resolve_secret_ref',
        lambda ref: 'xai-test',
    )
    resolved = ResolvedProvider(
        modality='llm', provider='grok',
        secret_ref='env/XAI_API_KEY', model='grok-2',
        params={}, source='db',
    )
    adapter = make_adapter_for_provider(resolved)
    assert isinstance(adapter, GrokProvider)
