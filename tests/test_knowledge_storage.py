from pathlib import Path
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.services.knowledge_storage import (
    delete_knowledge_file,
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


def test_delete_knowledge_file_removes_files_inside_tenant_prefix(tmp_path):
    tenant_id = str(uuid4())
    tenant_prefix = f'tenants/{tenant_id}/knowledge'
    target = tmp_path / tenant_prefix / 'doc-1' / 'file.txt'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('payload')

    delete_knowledge_file(
        source_uri=f'file://{target}',
        storage_backend='local',
        object_key=f'{tenant_prefix}/doc-1/file.txt',
        settings=make_settings(tmp_path),
        tenant_prefix=tenant_prefix,
    )

    assert not target.exists()


def test_delete_knowledge_file_refuses_absolute_source_uri_outside_storage_root(tmp_path):
    secret_dir = tmp_path.parent / 'secrets'
    secret_dir.mkdir(parents=True, exist_ok=True)
    secret_file = secret_dir / 'tenant-key.pem'
    secret_file.write_text('SENSITIVE')

    delete_knowledge_file(
        source_uri=f'file://{secret_file}',
        storage_backend='local',
        object_key=None,
        settings=make_settings(tmp_path),
        tenant_prefix=f'tenants/{uuid4()}/knowledge',
    )

    assert secret_file.exists(), 'file outside storage root must not be deleted'


def test_delete_knowledge_file_refuses_object_key_traversal(tmp_path):
    tenant_id = str(uuid4())
    tenant_prefix = f'tenants/{tenant_id}/knowledge'

    other_tenant_file = tmp_path / 'tenants' / 'victim-tenant' / 'knowledge' / 'doc' / 'private.txt'
    other_tenant_file.parent.mkdir(parents=True, exist_ok=True)
    other_tenant_file.write_text('victim data')

    delete_knowledge_file(
        source_uri='',
        storage_backend='local',
        object_key=f'{tenant_prefix}/../../victim-tenant/knowledge/doc/private.txt',
        settings=make_settings(tmp_path),
        tenant_prefix=tenant_prefix,
    )

    assert other_tenant_file.exists(), 'traversal out of tenant prefix must not delete other tenant files'


def test_delete_knowledge_file_refuses_object_key_outside_tenant_prefix(tmp_path):
    tenant_id = str(uuid4())
    tenant_prefix = f'tenants/{tenant_id}/knowledge'

    other_file = tmp_path / 'tenants' / 'other' / 'knowledge' / 'a.txt'
    other_file.parent.mkdir(parents=True, exist_ok=True)
    other_file.write_text('x')

    delete_knowledge_file(
        source_uri='',
        storage_backend='local',
        object_key='tenants/other/knowledge/a.txt',
        settings=make_settings(tmp_path),
        tenant_prefix=tenant_prefix,
    )

    assert other_file.exists()


def test_delete_knowledge_file_s3_refuses_bucket_mismatch(tmp_path, monkeypatch):
    calls = []

    class FakeClient:
        def delete_object(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(
        'app.services.knowledge_storage._s3_client', lambda *a, **kw: FakeClient()
    )

    delete_knowledge_file(
        source_uri='',
        storage_backend='s3',
        object_key='tenants/victim/knowledge/file',
        bucket='attacker-supplied-bucket',
        settings=make_settings(tmp_path),
        tenant_prefix='tenants/victim/knowledge',
        expected_bucket='configured-tenant-bucket',
    )

    assert calls == []


def test_delete_knowledge_file_s3_refuses_key_outside_tenant_prefix(tmp_path, monkeypatch):
    calls = []

    class FakeClient:
        def delete_object(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(
        'app.services.knowledge_storage._s3_client', lambda *a, **kw: FakeClient()
    )

    delete_knowledge_file(
        source_uri='',
        storage_backend='s3',
        object_key='tenants/other-tenant/knowledge/file',
        bucket='configured-tenant-bucket',
        settings=make_settings(tmp_path),
        tenant_prefix='tenants/this-tenant/knowledge',
        expected_bucket='configured-tenant-bucket',
    )

    assert calls == []


def test_delete_knowledge_file_s3_deletes_when_within_tenant_prefix(tmp_path, monkeypatch):
    calls = []

    class FakeClient:
        def delete_object(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(
        'app.services.knowledge_storage._s3_client', lambda *a, **kw: FakeClient()
    )

    delete_knowledge_file(
        source_uri='',
        storage_backend='s3',
        object_key='tenants/this-tenant/knowledge/doc/file',
        bucket='configured-tenant-bucket',
        settings=make_settings(tmp_path),
        tenant_prefix='tenants/this-tenant/knowledge',
        expected_bucket='configured-tenant-bucket',
    )

    assert calls == [
        {'Bucket': 'configured-tenant-bucket', 'Key': 'tenants/this-tenant/knowledge/doc/file'}
    ]


@pytest.mark.parametrize('bad_prefix', ['/', '//', '', '.', '..', '/./', '/../'])
def test_delete_knowledge_file_s3_refuses_root_like_tenant_prefix(tmp_path, monkeypatch, bad_prefix):
    """A tenant_prefix that normalizes to empty must NOT degrade to 'no containment';
    otherwise an admin that stored prefix='/' could delete arbitrary objects
    (including other tenants') in the shared bucket."""
    calls = []

    class FakeClient:
        def delete_object(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setattr(
        'app.services.knowledge_storage._s3_client', lambda *a, **kw: FakeClient()
    )

    delete_knowledge_file(
        source_uri='',
        storage_backend='s3',
        object_key='tenants/other-tenant/knowledge/secret',
        bucket='shared-bucket',
        settings=make_settings(tmp_path),
        tenant_prefix=bad_prefix,
        expected_bucket='shared-bucket',
    )

    assert calls == []


@pytest.mark.parametrize('bad_prefix', ['/', '//', '', '.', '..'])
def test_delete_knowledge_file_local_refuses_root_like_tenant_prefix(tmp_path, bad_prefix):
    other_tenant_file = tmp_path / 'tenants' / 'victim-tenant' / 'knowledge' / 'doc' / 'private.txt'
    other_tenant_file.parent.mkdir(parents=True, exist_ok=True)
    other_tenant_file.write_text('victim data')

    delete_knowledge_file(
        source_uri='',
        storage_backend='local',
        object_key='tenants/victim-tenant/knowledge/doc/private.txt',
        settings=make_settings(tmp_path),
        tenant_prefix=bad_prefix,
    )

    assert other_tenant_file.exists(), (
        'empty / root-like tenant_prefix must not degrade containment'
    )


def test_normalize_object_prefix_rejects_root_like_values():
    tenant_id = str(uuid4())
    for bad in ('/', '//', '///'):
        with pytest.raises(ValueError):
            normalize_object_prefix(bad, tenant_id)
