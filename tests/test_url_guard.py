"""Static tests for TASK-0079: outbound URL validator (SSRF defense).

Covers BUG01 (webhook alert SSRF), BUG18 (tenant S3 endpoint SSRF + creds
leak), BUG19 (WhatsApp media URL escape + crafted media_id).
"""
from __future__ import annotations

import ipaddress

import pytest

from app.core.config import get_settings
from app.services.url_guard import (
    META_MEDIA_HOST_ALLOWLIST,
    S3_ENDPOINT_HOST_ALLOWLIST,
    UnsafeOutboundURLError,
    assert_whatsapp_media_id,
    validate_outbound_url,
)
from tests._routes_aggregator import routes_aggregated_source


@pytest.fixture(autouse=True)
def _settings_env(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://example')
    monkeypatch.setenv('JWT_SECRET', 'local-secret-with-min-length')
    monkeypatch.setenv('SERVICE_TOKEN', 'service-token-with-min-length')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 's3-secret')
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _public_resolver(host: str):  # pragma: no cover - trivial
    return [ipaddress.ip_address('93.184.216.34')]  # example.com


def _loopback_resolver(host: str):
    return [ipaddress.ip_address('127.0.0.1')]


def _metadata_resolver(host: str):
    return [ipaddress.ip_address('169.254.169.254')]


# ── Scheme + structural checks ────────────────────────────────────────────────


def test_validate_rejects_http_scheme_by_default():
    with pytest.raises(UnsafeOutboundURLError, match='scheme'):
        validate_outbound_url('http://example.com/', resolver=_public_resolver)


def test_validate_accepts_https_to_public_host():
    result = validate_outbound_url('https://example.com/path', resolver=_public_resolver)
    assert result.host == 'example.com'
    assert result.scheme == 'https'


def test_validate_rejects_empty_or_malformed_url():
    with pytest.raises(UnsafeOutboundURLError):
        validate_outbound_url('')
    with pytest.raises(UnsafeOutboundURLError):
        validate_outbound_url('not-a-url')


def test_validate_rejects_user_password_in_url():
    with pytest.raises(UnsafeOutboundURLError, match='credentials'):
        validate_outbound_url(
            'https://user:pass@example.com/',
            resolver=_public_resolver,
        )


# ── Private / metadata network blocking ──────────────────────────────────────


def test_validate_rejects_literal_loopback_ip():
    with pytest.raises(UnsafeOutboundURLError, match='blocked'):
        validate_outbound_url('https://127.0.0.1/anything', resolver=_public_resolver)


def test_validate_rejects_literal_aws_metadata_ip():
    with pytest.raises(UnsafeOutboundURLError, match='blocked'):
        validate_outbound_url('https://169.254.169.254/latest', resolver=_public_resolver)


def test_validate_rejects_localhost_hostname():
    with pytest.raises(UnsafeOutboundURLError, match='blocked'):
        validate_outbound_url('https://localhost/api', resolver=_public_resolver)


def test_validate_rejects_metadata_google_internal():
    with pytest.raises(UnsafeOutboundURLError, match='blocked'):
        validate_outbound_url(
            'https://metadata.google.internal/computeMetadata/v1/',
            resolver=_public_resolver,
        )


def test_validate_rejects_hostname_that_resolves_to_loopback():
    """DNS rebinding: attacker hostname resolves to 127.0.0.1."""
    with pytest.raises(UnsafeOutboundURLError, match='blocked network'):
        validate_outbound_url(
            'https://attacker.example/',
            resolver=_loopback_resolver,
        )


def test_validate_rejects_hostname_that_resolves_to_metadata():
    with pytest.raises(UnsafeOutboundURLError, match='blocked network'):
        validate_outbound_url(
            'https://meta.attacker.example/',
            resolver=_metadata_resolver,
        )


def test_validate_rejects_rfc1918_literal():
    for ip in ('10.0.0.5', '192.168.1.1', '172.16.0.10'):
        with pytest.raises(UnsafeOutboundURLError, match='blocked'):
            validate_outbound_url(f'https://{ip}/', resolver=_public_resolver)


def test_validate_rejects_ipv6_loopback_and_ula():
    with pytest.raises(UnsafeOutboundURLError, match='blocked'):
        validate_outbound_url('https://[::1]/', resolver=_public_resolver)
    with pytest.raises(UnsafeOutboundURLError, match='blocked'):
        validate_outbound_url('https://[fc00::1]/', resolver=_public_resolver)


# ── Host allowlist (META media CDN, S3 endpoints) ────────────────────────────


def test_validate_accepts_meta_cdn_wildcard():
    result = validate_outbound_url(
        'https://scontent.fbcdn.net/v/foo',
        host_allowlist=META_MEDIA_HOST_ALLOWLIST,
        resolver=_public_resolver,
    )
    assert result.host == 'scontent.fbcdn.net'


def test_validate_rejects_host_outside_allowlist():
    with pytest.raises(UnsafeOutboundURLError, match='allowlist'):
        validate_outbound_url(
            'https://evil.example/',
            host_allowlist=META_MEDIA_HOST_ALLOWLIST,
            resolver=_public_resolver,
        )


def test_validate_accepts_aws_s3_virtual_hosted_style():
    result = validate_outbound_url(
        'https://my-bucket.s3.us-east-1.amazonaws.com/key',
        host_allowlist=S3_ENDPOINT_HOST_ALLOWLIST,
        resolver=_public_resolver,
    )
    assert result.host.endswith('amazonaws.com')


def test_validate_rejects_arbitrary_s3_compatible_host():
    with pytest.raises(UnsafeOutboundURLError, match='allowlist'):
        validate_outbound_url(
            'https://minio.attacker.example/',
            host_allowlist=S3_ENDPOINT_HOST_ALLOWLIST,
            resolver=_public_resolver,
        )


# ── Local dev override ──────────────────────────────────────────────────────


def test_validate_allows_local_minio_only_when_dev_flag_and_env_local(monkeypatch):
    from app.services import url_guard as guard_module

    monkeypatch.setattr(guard_module, '_is_local_dev_env', lambda: True)

    result = validate_outbound_url(
        'http://minio:9000/bucket',
        allowed_schemes=('https',),
        allow_http_for_local_dev=True,
        resolver=_loopback_resolver,
    )
    assert result.host == 'minio'


def test_validate_rejects_local_minio_when_dev_flag_but_env_prod(monkeypatch):
    from app.services import url_guard as guard_module

    monkeypatch.setattr(guard_module, '_is_local_dev_env', lambda: False)

    with pytest.raises(UnsafeOutboundURLError):
        validate_outbound_url(
            'http://minio:9000/bucket',
            allowed_schemes=('https',),
            allow_http_for_local_dev=True,
            resolver=_loopback_resolver,
        )


# ── WhatsApp media_id regex ──────────────────────────────────────────────────


def test_media_id_accepts_numeric_meta_id():
    assert assert_whatsapp_media_id('123456789012345') == '123456789012345'


def test_media_id_rejects_path_traversal():
    with pytest.raises(UnsafeOutboundURLError):
        assert_whatsapp_media_id('../foo')


def test_media_id_rejects_query_string_injection():
    with pytest.raises(UnsafeOutboundURLError):
        assert_whatsapp_media_id('123?token=stolen')


def test_media_id_rejects_letters_or_dashes():
    with pytest.raises(UnsafeOutboundURLError):
        assert_whatsapp_media_id('abc123')
    with pytest.raises(UnsafeOutboundURLError):
        assert_whatsapp_media_id('123-456')


def test_media_id_rejects_non_string():
    with pytest.raises(UnsafeOutboundURLError):
        assert_whatsapp_media_id(12345)  # type: ignore[arg-type]


# ── BUG01: alert webhook URL validated at write + send ───────────────────────


def test_normalize_alert_channels_strict_rejects_loopback_webhook(monkeypatch):
    from app.services import operator_alerts

    with pytest.raises(UnsafeOutboundURLError):
        operator_alerts.normalize_alert_channels(
            {'webhook_url': 'http://127.0.0.1:6379/cmd'},
            strict=True,
        )


def test_normalize_alert_channels_lenient_preserves_url_for_send_time_check():
    """Lenient (dispatch) path is shape-only; the actual SSRF gate lives in
    ``_send_webhook_channel`` so the URL survives normalization here and is
    dropped at send time."""
    from app.services import operator_alerts

    result = operator_alerts.normalize_alert_channels(
        {'webhook_url': 'http://127.0.0.1:6379/'},
        strict=False,
    )
    assert result['webhook_url'] == 'http://127.0.0.1:6379/'


def test_send_webhook_channel_drops_legacy_loopback_url():
    """Defense-in-depth: even if a stale DB row has a bad URL, the sender refuses."""
    import asyncio

    from app.services import operator_alerts

    class Spy:
        def __init__(self):
            self.called = False

        async def post(self, *_a, **_kw):  # pragma: no cover - should not run
            self.called = True
            raise AssertionError('webhook should have been blocked')

    spy = Spy()
    asyncio.run(
        operator_alerts._send_webhook_channel(
            tenant_id='00000000-0000-0000-0000-000000000000',
            url='http://127.0.0.1:6379/',
            payload={'k': 'v'},
            http_client=spy,
        )
    )
    assert spy.called is False


def test_patch_settings_blocks_loopback_webhook_at_source_handler():
    """The PATCH handler must call normalize_alert_channels(strict=True)."""

    source = routes_aggregated_source()
    start = source.index("async def patch_settings(")
    end = source.index("@tenant_admin_router", start + 1)
    block = source[start:end]
    assert 'normalize_alert_channels' in block
    assert "strict=True" in block
    assert 'complaint_alert_channels' in block


# ── BUG18: S3 endpoint rejected at PATCH handler + _s3_client ────────────────


def test_s3_client_rejects_tenant_endpoint_without_tenant_creds():
    from app.core.config import get_settings
    from app.services import knowledge_storage

    settings = get_settings()

    with pytest.raises(ValueError, match='requires tenant-supplied'):
        knowledge_storage._s3_client(
            settings,
            endpoint_url='https://s3.us-east-1.amazonaws.com',
            access_key_id=None,
            secret_access_key=None,
        )


def test_s3_client_rejects_loopback_endpoint():
    from app.core.config import get_settings
    from app.services import knowledge_storage

    settings = get_settings()

    with pytest.raises(ValueError, match='rejected'):
        knowledge_storage._s3_client(
            settings,
            endpoint_url='http://127.0.0.1:9000',
            access_key_id='AKIA',
            secret_access_key='secret',
        )


def test_s3_client_rejects_endpoint_outside_allowlist():
    from app.core.config import get_settings
    from app.services import knowledge_storage

    settings = get_settings()

    with pytest.raises(ValueError, match='rejected'):
        knowledge_storage._s3_client(
            settings,
            endpoint_url='https://attacker.example.com',
            access_key_id='AKIA',
            secret_access_key='secret',
        )


def test_patch_knowledge_storage_validates_endpoint_at_source_handler():

    source = routes_aggregated_source()
    start = source.index('async def patch_knowledge_storage_settings(')
    end = source.index('@tenant_admin_router', start + 1)
    block = source[start:end]
    assert 'S3_ENDPOINT_HOST_ALLOWLIST' in block
    assert 'validate_outbound_url' in block
    assert 'requires tenant-supplied' in block


# ── BUG19: WhatsApp media inbound + Graph payload validation ─────────────────


def test_validate_outbound_message_content_rejects_crafted_media_id():
    from fastapi import HTTPException

    from app.api.v1.routes import validate_outbound_message_content

    with pytest.raises(HTTPException) as exc_info:
        validate_outbound_message_content(
            message_type='image',
            body_text=None,
            media_id='../foo',
            media_url=None,
        )
    assert exc_info.value.status_code == 422
    assert 'media_id' in exc_info.value.detail


def test_validate_outbound_message_content_accepts_numeric_media_id():
    from app.api.v1.routes import validate_outbound_message_content

    # Should not raise
    validate_outbound_message_content(
        message_type='image',
        body_text=None,
        media_id='1234567890',
        media_url=None,
    )


def test_meta_media_allowlist_blocks_non_meta_host():
    with pytest.raises(UnsafeOutboundURLError, match='allowlist'):
        validate_outbound_url(
            'https://attacker.com/file.jpg',
            host_allowlist=META_MEDIA_HOST_ALLOWLIST,
            resolver=_public_resolver,
        )


def test_meta_media_allowlist_accepts_lookaside_and_fbcdn():
    for url in (
        'https://lookaside.fbsbx.com/whatsapp_business/attachments/?mid=1',
        'https://scontent-mia.fbcdn.net/v/foo',
    ):
        result = validate_outbound_url(
            url,
            host_allowlist=META_MEDIA_HOST_ALLOWLIST,
            resolver=_public_resolver,
        )
        assert 'fb' in result.host or result.host.endswith('fbcdn.net')


def test_download_media_source_uses_url_guard_and_no_redirects():
    """The download path must call validate_outbound_url with the META allowlist
    and disable redirect following — the test inspects source to keep the
    suite zero-network."""
    from pathlib import Path

    source = Path('app/services/whatsapp.py').read_text()
    block_start = source.index('async def download_whatsapp_media(')
    block = source[block_start:block_start + 3000]
    assert 'validate_outbound_url' in block
    assert 'META_MEDIA_HOST_ALLOWLIST' in block
    assert 'follow_redirects=False' in block


def test_get_media_info_source_quotes_media_id_and_validates_graph_host():
    from pathlib import Path

    source = Path('app/services/whatsapp.py').read_text()
    block_start = source.index('async def get_whatsapp_media_info(')
    block = source[block_start:block_start + 3000]
    assert 'assert_whatsapp_media_id' in block
    assert 'quote(' in block
    assert "safe=''" in block
    assert 'follow_redirects=False' in block
