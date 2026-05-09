from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.services.knowledge_storage import (
    extract_text_if_supported,
    normalize_object_prefix,
    safe_storage_segment,
    store_knowledge_file,
)


def make_settings(tmp_path: Path, **overrides):
    values = {
        'database_url': 'postgresql://copiloto_app:secret@postgres:5432/copilotoia',
        'jwt_secret': 'x' * 16,
        'service_token': 'y' * 16,
        's3_secret_access_key': 'z' * 16,
        'knowledge_storage_local_path': str(tmp_path),
    }
    values.update(overrides)
    return Settings(**values)


def test_local_knowledge_storage_persists_under_tenant_scoped_key(tmp_path):
    tenant_id = uuid4()
    document_id = uuid4()
    stored = store_knowledge_file(
        data=b'# FAQ\nGarantia: 30 dias',
        tenant_id=str(tenant_id),
        document_id=str(document_id),
        filename='faq inicial.md',
        mime_type='text/markdown',
        settings=make_settings(tmp_path),
    )

    path = Path(stored.source_uri.removeprefix('file://'))
    assert path.exists()
    assert str(tenant_id) in stored.object_key
    assert str(document_id) in stored.object_key
    assert stored.checksum.startswith('sha256:')
    assert stored.extracted_text == '# FAQ\nGarantia: 30 dias'


def test_knowledge_storage_rejects_disallowed_mime(tmp_path):
    with pytest.raises(ValueError, match='not allowed'):
        store_knowledge_file(
            data=b'<script>alert(1)</script>',
            tenant_id=str(uuid4()),
            document_id=str(uuid4()),
            filename='payload.html',
            mime_type='text/html',
            settings=make_settings(tmp_path),
        )


def test_knowledge_storage_enforces_size_limit(tmp_path):
    with pytest.raises(ValueError, match='exceeds'):
        store_knowledge_file(
            data=b'abcdef',
            tenant_id=str(uuid4()),
            document_id=str(uuid4()),
            filename='big.txt',
            mime_type='text/plain',
            settings=make_settings(tmp_path, knowledge_file_max_bytes=3),
        )


def test_pdf_is_stored_without_runtime_binary_parsing():
    assert extract_text_if_supported(b'%PDF-1.7', filename='manual.pdf', mime_type='application/pdf') is None


def test_safe_storage_segment_removes_path_traversal_characters():
    assert '..' not in safe_storage_segment('../../secret file.md')
    assert '/' not in safe_storage_segment('../../secret file.md')


def test_local_knowledge_storage_accepts_tenant_prefix(tmp_path):
    tenant_id = uuid4()
    stored = store_knowledge_file(
        data=b'FAQ storage tenant',
        tenant_id=str(tenant_id),
        document_id=str(uuid4()),
        filename='faq.txt',
        mime_type='text/plain',
        settings=make_settings(tmp_path),
        prefix=f'knowledge/{tenant_id}',
    )

    assert stored.object_key.startswith(f'knowledge/{tenant_id}/')
    assert Path(stored.source_uri.removeprefix('file://')).exists()


def test_object_prefix_defaults_to_tenant_scoped_knowledge_path():
    tenant_id = str(uuid4())

    assert normalize_object_prefix(None, tenant_id) == f'tenants/{tenant_id}/knowledge'
    assert normalize_object_prefix('/custom//tenant//knowledge/', tenant_id) == 'custom/tenant/knowledge'
