"""Cover remaining gaps in app/services/media_storage.py to ≥95%."""
from __future__ import annotations


import pytest


def test_store_media_file_local_path_escape_raises(monkeypatch, tmp_path):
    """Line 112-113: if resolved destination escapes the root, raise ValueError."""
    from app.core.config import Settings
    from app.services.media_storage import store_media_file
    settings = Settings.model_construct(
        knowledge_storage_backend='local',
        knowledge_storage_local_path=str(tmp_path),
    )

    # Monkeypatch media_object_key to return a path that escapes root via .. segments
    from app.services import media_storage
    monkeypatch.setattr(
        media_storage, 'media_object_key',
        lambda **kw: f'../../escape/{kw["filename"]}',
    )

    with pytest.raises(ValueError, match='Invalid media storage path'):
        store_media_file(
            data=b'X', tenant_id='t1', asset_id='a1', kind='image',
            filename='hack.png', mime_type='image/png', settings=settings,
        )


def test_store_media_file_s3_uploads(monkeypatch):
    """Lines 125-137: S3 backend goes through _s3_client + put_object."""
    from app.core.config import Settings
    from app.services import knowledge_storage
    from app.services.media_storage import store_media_file

    uploads = []

    class _FakeS3:
        def put_object(self, **kw):
            uploads.append(kw)

    monkeypatch.setattr(knowledge_storage, '_s3_client', lambda settings: _FakeS3())
    settings = Settings.model_construct(
        knowledge_storage_backend='s3',
        knowledge_storage_local_path='/tmp',
        knowledge_storage_bucket='my-bucket',
    )

    out = store_media_file(
        data=b'PNG-BYTES', tenant_id='t1', asset_id='a1', kind='image',
        filename='photo.png', mime_type='image/png', settings=settings,
    )
    assert out.storage_backend == 's3'
    assert out.bucket  # whatever the configured bucket is
    assert out.source_uri.startswith('s3://')
    assert len(uploads) == 1
    assert uploads[0]['Body'] == b'PNG-BYTES'


def test_delete_media_file_local_oserror_swallowed(monkeypatch, tmp_path):
    """Lines 205-206: OSError on unlink is swallowed silently."""
    from app.core.config import Settings
    from app.services.media_storage import delete_media_file
    settings = Settings.model_construct()

    # Monkey-patch Path.unlink to raise OSError
    from app.services import media_storage

    class _BrokenPath:
        def __init__(self, *a, **kw):
            pass
        def unlink(self, *a, **kw):
            raise OSError('permission denied')

    # Override Path import in the media_storage module
    monkeypatch.setattr(media_storage, 'Path', _BrokenPath)

    # No raise — error is swallowed
    delete_media_file(
        storage_backend='local', object_key='x',
        source_uri='file:///broken/path.bin',
        bucket=None, settings=settings,
    )
