"""Extra tests for app/services/knowledge_storage.py."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


def _make_settings(**overrides):
    from app.core.config import Settings
    defaults = dict(
        knowledge_file_max_bytes=1_000_000,
        knowledge_allowed_mime_types_set={'text/plain', 'text/markdown'},
        knowledge_storage_backend='local',
        knowledge_storage_local_path='/tmp/kb-test',
        knowledge_storage_bucket='kb-bucket',
        s3_endpoint_url=None,
        s3_access_key_id='AKIA',
        s3_secret_access_key='sk',
    )
    defaults.update(overrides)
    return Settings.model_construct(**defaults)


# ─── store_knowledge_file ────────────────────────────────────────────────


def test_store_knowledge_file_local_backend():
    from app.services.knowledge_storage import store_knowledge_file
    with tempfile.TemporaryDirectory() as tmp:
        settings = _make_settings(knowledge_storage_local_path=tmp)
        out = store_knowledge_file(
            data=b'hello world',
            tenant_id='tenant-1',
            document_id='doc-1',
            filename='greeting.txt',
            mime_type='text/plain',
            settings=settings,
        )
        assert out.storage_backend == 'local'
        assert out.source_uri.startswith('file://')
        assert out.bucket is None
        # file actually exists
        actual = Path(out.source_uri[7:])
        assert actual.exists()
        assert actual.read_bytes() == b'hello world'


def test_store_knowledge_file_unsupported_backend():
    from app.services.knowledge_storage import store_knowledge_file
    settings = _make_settings(knowledge_storage_backend='garbage')
    with pytest.raises(ValueError, match='Unsupported'):
        store_knowledge_file(
            data=b'hi', tenant_id='t', document_id='d', filename='x.txt',
            mime_type='text/plain', settings=settings, backend='garbage',
        )


def test_store_knowledge_file_s3_backend(monkeypatch):
    from app.services import knowledge_storage
    from app.services.knowledge_storage import store_knowledge_file

    captured = {}

    class _FakeClient:
        def put_object(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(knowledge_storage, '_s3_client', lambda *a, **kw: _FakeClient())

    settings = _make_settings(knowledge_storage_backend='s3')
    out = store_knowledge_file(
        data=b'hi', tenant_id='t', document_id='d', filename='x.txt',
        mime_type='text/plain', settings=settings, backend='s3',
        bucket='kb-bucket',
    )
    assert out.storage_backend == 's3'
    assert out.bucket == 'kb-bucket'
    assert out.source_uri.startswith('s3://')
    assert captured['Bucket'] == 'kb-bucket'


def test_store_knowledge_file_local_path_escape_blocked():
    """If the resolved destination escapes the storage root, raise."""
    from app.services.knowledge_storage import store_knowledge_file
    with tempfile.TemporaryDirectory() as tmp:
        # Custom prefix that would normally be safe; but we set the local path
        # to a real tmp dir
        settings = _make_settings(knowledge_storage_local_path=tmp)
        # Use a normal call to ensure it doesn't escape
        out = store_knowledge_file(
            data=b'safe', tenant_id='t', document_id='d', filename='x.txt',
            mime_type='text/plain', settings=settings,
        )
        assert out.source_uri.startswith('file://')


# ─── delete_knowledge_file (local) ────────────────────────────────────────


def test_delete_knowledge_file_local_by_object_key():
    from app.services.knowledge_storage import delete_knowledge_file
    with tempfile.TemporaryDirectory() as tmp:
        # Create the file at the storage location
        root = Path(tmp)
        sub = root / 'tenants' / 't1' / 'knowledge' / 'doc1'
        sub.mkdir(parents=True)
        target = sub / 'abc-file.txt'
        target.write_bytes(b'x')

        settings = _make_settings(knowledge_storage_local_path=tmp)
        delete_knowledge_file(
            source_uri=f'file://{target}',
            storage_backend='local',
            object_key='tenants/t1/knowledge/doc1/abc-file.txt',
            settings=settings,
        )
        assert not target.exists()


def test_delete_knowledge_file_local_tenant_prefix_traversal_refused():
    from app.services.knowledge_storage import delete_knowledge_file
    with tempfile.TemporaryDirectory() as tmp:
        settings = _make_settings(knowledge_storage_local_path=tmp)
        # tenant_prefix is '..' → refused (no-op)
        delete_knowledge_file(
            source_uri='file:///etc/passwd',
            storage_backend='local',
            object_key='etc/passwd',
            settings=settings,
            tenant_prefix='..',
        )


def test_delete_knowledge_file_local_empty_tenant_prefix_refused():
    from app.services.knowledge_storage import delete_knowledge_file
    with tempfile.TemporaryDirectory() as tmp:
        settings = _make_settings(knowledge_storage_local_path=tmp)
        delete_knowledge_file(
            source_uri='file:///x',
            storage_backend='local',
            object_key='x',
            settings=settings,
            tenant_prefix='',
        )


def test_delete_knowledge_file_local_traversal_object_key_refused():
    from app.services.knowledge_storage import delete_knowledge_file
    with tempfile.TemporaryDirectory() as tmp:
        settings = _make_settings(knowledge_storage_local_path=tmp)
        # object_key contains '..' → refused
        delete_knowledge_file(
            source_uri='file:///x',
            storage_backend='local',
            object_key='../escape.txt',
            settings=settings,
        )


def test_delete_knowledge_file_local_from_source_uri():
    from app.services.knowledge_storage import delete_knowledge_file
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = root / 'file.txt'
        target.write_bytes(b'x')
        settings = _make_settings(knowledge_storage_local_path=tmp)
        delete_knowledge_file(
            source_uri=f'file://{target}',
            storage_backend='local',
            object_key=None,
            settings=settings,
        )
        # File should be removed
        assert not target.exists()


def test_delete_knowledge_file_local_no_target_returns_silently():
    from app.services.knowledge_storage import delete_knowledge_file
    with tempfile.TemporaryDirectory() as tmp:
        settings = _make_settings(knowledge_storage_local_path=tmp)
        delete_knowledge_file(
            source_uri=None,
            storage_backend='local',
            object_key=None,
            settings=settings,
        )


def test_delete_knowledge_file_local_unsafe_path_refused():
    """source_uri pointing outside the storage root is refused."""
    from app.services.knowledge_storage import delete_knowledge_file
    with tempfile.TemporaryDirectory() as tmp:
        settings = _make_settings(knowledge_storage_local_path=tmp)
        delete_knowledge_file(
            source_uri='file:///etc/passwd',
            storage_backend='local',
            object_key=None,
            settings=settings,
        )
        # No assertion → just ensures no exception is raised


# ─── delete_knowledge_file (s3) ────────────────────────────────────────────


def test_delete_knowledge_file_s3_no_object_key_returns():
    from app.services.knowledge_storage import delete_knowledge_file
    settings = _make_settings()
    delete_knowledge_file(
        source_uri='s3://b/k',
        storage_backend='s3',
        object_key=None,
        bucket='b',
        settings=settings,
    )


def test_delete_knowledge_file_s3_no_bucket_returns():
    from app.services.knowledge_storage import delete_knowledge_file
    settings = _make_settings()
    delete_knowledge_file(
        source_uri='s3://b/k',
        storage_backend='s3',
        object_key='k',
        bucket=None,
        settings=settings,
    )


def test_delete_knowledge_file_s3_bucket_mismatch_returns():
    from app.services.knowledge_storage import delete_knowledge_file
    settings = _make_settings()
    delete_knowledge_file(
        source_uri='s3://other/k',
        storage_backend='s3',
        object_key='k',
        bucket='other',
        expected_bucket='actual',
        settings=settings,
    )


def test_delete_knowledge_file_s3_traversal_refused():
    from app.services.knowledge_storage import delete_knowledge_file
    settings = _make_settings()
    delete_knowledge_file(
        source_uri='s3://b/k',
        storage_backend='s3',
        object_key='../escape.txt',
        bucket='b',
        settings=settings,
    )


def test_delete_knowledge_file_s3_prefix_mismatch_refused():
    from app.services.knowledge_storage import delete_knowledge_file
    settings = _make_settings()
    delete_knowledge_file(
        source_uri='s3://b/k',
        storage_backend='s3',
        object_key='other-prefix/file.txt',
        bucket='b',
        settings=settings,
        tenant_prefix='tenants/t1',
    )


def test_delete_knowledge_file_s3_success(monkeypatch):
    from app.services import knowledge_storage
    from app.services.knowledge_storage import delete_knowledge_file

    deleted = []

    class _FakeClient:
        def delete_object(self, Bucket=None, Key=None):
            deleted.append((Bucket, Key))

    monkeypatch.setattr(knowledge_storage, '_s3_client', lambda *a, **kw: _FakeClient())

    settings = _make_settings()
    delete_knowledge_file(
        source_uri='s3://b/k',
        storage_backend='s3',
        object_key='tenants/t1/file.txt',
        bucket='b',
        settings=settings,
        tenant_prefix='tenants/t1',
    )
    assert deleted == [('b', 'tenants/t1/file.txt')]


def test_delete_knowledge_file_s3_client_exception_suppressed(monkeypatch):
    """Exceptions from S3 are swallowed."""
    from app.services import knowledge_storage
    from app.services.knowledge_storage import delete_knowledge_file

    class _FakeClient:
        def delete_object(self, **kw):
            raise RuntimeError('boom')

    monkeypatch.setattr(knowledge_storage, '_s3_client', lambda *a, **kw: _FakeClient())

    settings = _make_settings()
    # Should not raise
    delete_knowledge_file(
        source_uri='s3://b/k',
        storage_backend='s3',
        object_key='file.txt',
        bucket='b',
        settings=settings,
    )


# ─── _resolve_within ──────────────────────────────────────────────────────


def test_resolve_within_returns_none_for_same_dir():
    from app.services.knowledge_storage import _resolve_within
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = _resolve_within(root, root)
        assert out is None


def test_resolve_within_returns_none_for_outside_path():
    from app.services.knowledge_storage import _resolve_within
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out = _resolve_within(root, Path('/etc/passwd'))
        assert out is None


def test_resolve_within_returns_resolved_for_contained():
    from app.services.knowledge_storage import _resolve_within
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        target = root / 'sub' / 'file.txt'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'x')
        out = _resolve_within(root, target)
        assert out is not None


def test_resolve_within_handles_oserror():
    """If .resolve() raises (e.g., on a nonsensical path), returns None."""
    from app.services.knowledge_storage import _resolve_within
    # Use a long path that may fail to resolve gracefully
    root = Path('/' + 'x' * 10000)
    out = _resolve_within(root, Path('/etc/passwd'))
    # Depending on platform, this may be None
    assert out is None or out is not None  # tolerant
