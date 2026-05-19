"""Pure-helper tests for `app/services/knowledge_storage.py`."""
from __future__ import annotations

import pytest


# ───────── safe_storage_segment ─────────────────────────────────────────


def test_safe_storage_segment_sanitizes_unsafe_chars():
    from app.services.knowledge_storage import safe_storage_segment
    assert safe_storage_segment('hola mundo!') == 'hola-mundo'


def test_safe_storage_segment_truncates_long_input():
    from app.services.knowledge_storage import safe_storage_segment
    out = safe_storage_segment('x' * 500)
    assert len(out) <= 180


def test_safe_storage_segment_fallback_for_all_invalid():
    from app.services.knowledge_storage import safe_storage_segment
    assert safe_storage_segment('!@#$%') == 'file'


def test_safe_storage_segment_strips_leading_dots():
    from app.services.knowledge_storage import safe_storage_segment
    assert safe_storage_segment('  .hidden.') == 'hidden'


# ───────── normalize_object_prefix ──────────────────────────────────────


def test_normalize_object_prefix_default_when_none():
    from app.services.knowledge_storage import normalize_object_prefix
    assert normalize_object_prefix(None, 'tid-1') == 'tenants/tid-1/knowledge'


def test_normalize_object_prefix_default_when_empty():
    from app.services.knowledge_storage import normalize_object_prefix
    assert normalize_object_prefix('', 'tid-2') == 'tenants/tid-2/knowledge'


def test_normalize_object_prefix_sanitizes_parts():
    from app.services.knowledge_storage import normalize_object_prefix
    assert normalize_object_prefix('/cool/path-name/', 'tid') == 'cool/path-name'


def test_normalize_object_prefix_rejects_dot_dot():
    from app.services.knowledge_storage import normalize_object_prefix
    # Each path part is sanitized to 'file' (the SAFE_SEGMENT_RE catches '.'),
    # so '..' alone gets converted — but a single '/' input raises:
    with pytest.raises(ValueError):
        normalize_object_prefix('/', 'tid')


# ───────── knowledge_object_key ─────────────────────────────────────────


def test_knowledge_object_key_format():
    from app.services.knowledge_storage import knowledge_object_key
    out = knowledge_object_key(
        tenant_id='t1', document_id='doc-1',
        filename='hello world.txt', digest='abcdef1234567890' + 'x' * 50,
    )
    assert out.startswith('tenants/t1/knowledge/doc-1/')
    # Contains a digest prefix + safe filename
    assert 'hello-world.txt' in out


def test_knowledge_object_key_with_custom_prefix():
    from app.services.knowledge_storage import knowledge_object_key
    out = knowledge_object_key(
        tenant_id='t1', document_id='doc-1',
        filename='x.txt', digest='abc1234567890def',
        prefix='custom/path',
    )
    assert out.startswith('custom/path/doc-1/')


# ───────── is_text_upload / is_binary_extractable ───────────────────────


def test_is_text_upload_by_mime():
    from app.services.knowledge_storage import is_text_upload
    assert is_text_upload('x.bin', 'text/plain') is True
    assert is_text_upload('x.bin', 'text/markdown; charset=utf-8') is True
    assert is_text_upload('x.bin', 'application/json') is True


def test_is_text_upload_by_extension():
    from app.services.knowledge_storage import is_text_upload
    assert is_text_upload('readme.md', None) is True
    assert is_text_upload('data.csv', None) is True
    assert is_text_upload('notes.txt', None) is True
    assert is_text_upload('image.png', None) is False


def test_is_binary_extractable_by_mime():
    from app.services.knowledge_storage import is_binary_extractable
    assert is_binary_extractable('x', 'application/pdf') is True
    assert is_binary_extractable(
        'x',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    ) is True
    assert is_binary_extractable('x', 'text/plain') is False


def test_is_binary_extractable_by_extension():
    from app.services.knowledge_storage import is_binary_extractable
    assert is_binary_extractable('doc.pdf', None) is True
    assert is_binary_extractable('doc.docx', None) is True
    assert is_binary_extractable('image.png', None) is False


# ───────── extract_text_if_supported ────────────────────────────────────


def test_extract_text_if_supported_text_decode():
    from app.services.knowledge_storage import extract_text_if_supported
    out = extract_text_if_supported(b'hola\n', filename='x.txt', mime_type=None)
    assert out == 'hola'


def test_extract_text_if_supported_handles_bom():
    """UTF-8 BOM should be stripped (`utf-8-sig` decode)."""
    from app.services.knowledge_storage import extract_text_if_supported
    out = extract_text_if_supported(b'\xef\xbb\xbfhola', filename='x.txt', mime_type=None)
    assert out == 'hola'


def test_extract_text_if_supported_returns_none_for_binary():
    from app.services.knowledge_storage import extract_text_if_supported
    out = extract_text_if_supported(b'\x00\x01', filename='image.png', mime_type='image/png')
    assert out is None


# ───────── validate_knowledge_upload ────────────────────────────────────


def test_validate_knowledge_upload_rejects_empty_filename():
    from app.core.config import Settings
    from app.services.knowledge_storage import validate_knowledge_upload
    settings = Settings.model_construct(
        knowledge_file_max_bytes=1_000_000,
        knowledge_allowed_mime_types_set={'text/plain'},
    )
    with pytest.raises(ValueError, match='filename'):
        validate_knowledge_upload(b'data', filename='', mime_type='text/plain', settings=settings)


def test_validate_knowledge_upload_rejects_empty_data():
    from app.core.config import Settings
    from app.services.knowledge_storage import validate_knowledge_upload
    settings = Settings.model_construct(
        knowledge_file_max_bytes=1_000_000,
        knowledge_allowed_mime_types_set={'text/plain'},
    )
    with pytest.raises(ValueError, match='empty'):
        validate_knowledge_upload(b'', filename='x.txt', mime_type='text/plain', settings=settings)


def test_validate_knowledge_upload_rejects_oversized():
    from app.core.config import Settings
    from app.services.knowledge_storage import validate_knowledge_upload
    settings = Settings.model_construct(
        knowledge_file_max_bytes=10,
        knowledge_allowed_mime_types_set={'text/plain'},
    )
    with pytest.raises(ValueError, match='exceeds'):
        validate_knowledge_upload(b'x' * 100, filename='x.txt', mime_type='text/plain', settings=settings)


def test_validate_knowledge_upload_rejects_bad_mime():
    from app.core.config import Settings
    from app.services.knowledge_storage import validate_knowledge_upload
    settings = Settings.model_construct(
        knowledge_file_max_bytes=1_000_000,
        knowledge_allowed_mime_types_set={'text/plain'},
    )
    with pytest.raises(ValueError, match='MIME'):
        validate_knowledge_upload(
            b'x', filename='x.exe', mime_type='application/x-msdownload', settings=settings,
        )


def test_validate_knowledge_upload_accepts_valid():
    from app.core.config import Settings
    from app.services.knowledge_storage import validate_knowledge_upload
    settings = Settings.model_construct(
        knowledge_file_max_bytes=1_000_000,
        knowledge_allowed_mime_types_set={'text/plain', 'text/markdown'},
    )
    # No raise = pass
    validate_knowledge_upload(
        b'hola', filename='x.txt', mime_type='text/plain', settings=settings,
    )


def test_validate_knowledge_upload_strips_mime_params():
    from app.core.config import Settings
    from app.services.knowledge_storage import validate_knowledge_upload
    settings = Settings.model_construct(
        knowledge_file_max_bytes=1_000_000,
        knowledge_allowed_mime_types_set={'text/plain'},
    )
    # 'text/plain; charset=utf-8' should be normalized to 'text/plain'
    validate_knowledge_upload(
        b'hola', filename='x.txt',
        mime_type='text/plain; charset=utf-8', settings=settings,
    )


# ───────── _s3_client guards ──────────────────────────────────────────


def test_s3_client_tenant_endpoint_rejects_unsafe_host():
    """An endpoint whose host is not in the S3 allowlist is rejected."""
    from app.core.config import Settings
    from app.services.knowledge_storage import _s3_client
    settings = Settings.model_construct(
        s3_endpoint_url=None, s3_access_key_id='AKIA', s3_secret_access_key='sk',
    )
    # Unknown host → blocked by S3_ENDPOINT_HOST_ALLOWLIST
    with pytest.raises(ValueError, match='rejected'):
        _s3_client(
            settings, endpoint_url='https://example.com',
            access_key_id=None, secret_access_key=None,
        )


def test_s3_client_tenant_endpoint_rejects_unsafe_url():
    from app.core.config import Settings
    from app.services.knowledge_storage import _s3_client
    settings = Settings.model_construct(
        s3_endpoint_url=None, s3_access_key_id='AKIA', s3_secret_access_key='sk',
    )
    with pytest.raises(ValueError, match='rejected'):
        _s3_client(
            settings,
            endpoint_url='http://127.0.0.1:9000',  # loopback
            access_key_id='AKIA',
            secret_access_key='sk',
        )
