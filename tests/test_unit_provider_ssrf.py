"""Tests para SEC-019 (audit #2) — anti-SSRF en provider params."""
from __future__ import annotations

import pytest
from fastapi import HTTPException


def test_reject_unsafe_url_http_scheme():
    from copiloto_core.platform_admin.admin_routes import _reject_unsafe_provider_url
    with pytest.raises(HTTPException) as exc:
        _reject_unsafe_provider_url('http://api.x.ai', field='params.base_url')
    assert exc.value.status_code == 422
    assert 'scheme' in str(exc.value.detail).lower()


def test_reject_unsafe_url_aws_metadata_ip():
    """AWS metadata service — el clásico SSRF target."""
    from copiloto_core.platform_admin.admin_routes import _reject_unsafe_provider_url
    with pytest.raises(HTTPException) as exc:
        _reject_unsafe_provider_url(
            'https://169.254.169.254/latest/meta-data/iam/security-credentials/',
            field='params.base_url',
        )
    assert exc.value.status_code == 422
    assert 'link-local' in str(exc.value.detail).lower() or '169.254' in str(exc.value.detail)


def test_reject_unsafe_url_loopback_ip():
    from copiloto_core.platform_admin.admin_routes import _reject_unsafe_provider_url
    with pytest.raises(HTTPException) as exc:
        _reject_unsafe_provider_url('https://127.0.0.1:8080', field='x')
    assert exc.value.status_code == 422


def test_reject_unsafe_url_rfc1918_private():
    from copiloto_core.platform_admin.admin_routes import _reject_unsafe_provider_url
    for ip in ('10.0.0.1', '172.16.0.1', '192.168.1.1'):
        with pytest.raises(HTTPException) as exc:
            _reject_unsafe_provider_url(f'https://{ip}/api', field='x')
        assert exc.value.status_code == 422


def test_reject_unsafe_url_localhost_hostname():
    from copiloto_core.platform_admin.admin_routes import _reject_unsafe_provider_url
    with pytest.raises(HTTPException) as exc:
        _reject_unsafe_provider_url('https://localhost/api', field='x')
    assert exc.value.status_code == 422


def test_reject_unsafe_url_internal_tld():
    from copiloto_core.platform_admin.admin_routes import _reject_unsafe_provider_url
    with pytest.raises(HTTPException) as exc:
        _reject_unsafe_provider_url('https://foo.internal/api', field='x')
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException):
        _reject_unsafe_provider_url('https://bar.local/api', field='x')


def test_accepts_public_provider_url():
    """Las URLs reales de providers (api.x.ai, etc.) deben pasar."""
    from copiloto_core.platform_admin.admin_routes import _reject_unsafe_provider_url
    # No raise.
    _reject_unsafe_provider_url('https://api.x.ai/v1', field='x')
    _reject_unsafe_provider_url('https://api.openai.com', field='x')
    _reject_unsafe_provider_url('https://api.anthropic.com/v1', field='x')


def test_params_validator_blocks_base_url_ssrf():
    from copiloto_core.platform_admin.admin_routes import PlatformAIProviderUpdate

    with pytest.raises(HTTPException) as exc:
        PlatformAIProviderUpdate(
            provider='grok',
            params={'base_url': 'http://169.254.169.254'},
        )
    assert exc.value.status_code == 422


def test_params_validator_accepts_safe_base_url():
    from copiloto_core.platform_admin.admin_routes import PlatformAIProviderUpdate
    p = PlatformAIProviderUpdate(
        provider='grok',
        params={'base_url': 'https://api.x.ai/v1', 'temperature': 0.5},
    )
    assert p.params is not None
    assert p.params['base_url'] == 'https://api.x.ai/v1'


def test_params_validator_ignores_none():
    from copiloto_core.platform_admin.admin_routes import PlatformAIProviderUpdate
    p = PlatformAIProviderUpdate(provider='grok', params=None)
    assert p.params is None
