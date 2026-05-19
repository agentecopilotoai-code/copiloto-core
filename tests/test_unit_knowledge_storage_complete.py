"""Completeness tests for knowledge_storage — covers _s3_client kwargs paths,
local destination-escape raise, _resolve_within OSError, and the
delete_knowledge_file rmdir loop's exception branches.
"""
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


# ── Lines 134, 139-141: _s3_client returns boto3 client with region_name ───


def test_s3_client_uses_region_name(monkeypatch):
    from app.services import knowledge_storage

    captured = {}

    def fake_client(name, **kwargs):
        captured['name'] = name
        captured.update(kwargs)
        return 'fake-client'

    monkeypatch.setattr(knowledge_storage.boto3, 'client', fake_client)
    settings = _make_settings()
    result = knowledge_storage._s3_client(
        settings,
        endpoint_url=None,  # no tenant override
        access_key_id=None,
        secret_access_key=None,
        region_name='us-east-2',
    )
    assert result == 'fake-client'
    assert captured['name'] == 's3'
    assert captured['region_name'] == 'us-east-2'
    assert captured['aws_access_key_id'] == 'AKIA'


def test_s3_client_no_region_uses_settings_credentials(monkeypatch):
    from app.services import knowledge_storage

    captured = {}
    monkeypatch.setattr(knowledge_storage.boto3, 'client',
                        lambda n, **kw: captured.update({'n': n, **kw}) or 'c')
    settings = _make_settings()
    knowledge_storage._s3_client(settings, endpoint_url=None,
                                  access_key_id=None, secret_access_key=None,
                                  region_name=None)
    assert 'region_name' not in captured
    assert captured['aws_access_key_id'] == 'AKIA'


# ── Line 172: store_knowledge_file path-escape via mocked Path.resolve ─────


def test_store_knowledge_file_invalid_path_escape(monkeypatch):
    """If destination.resolve() is not anchored within the storage root,
    raise. We force this by patching Path.resolve to return a constant path
    that bypasses the root prefix check."""
    from app.services import knowledge_storage

    with tempfile.TemporaryDirectory() as tmp:
        settings = _make_settings(knowledge_storage_local_path=tmp)

        real_resolve = Path.resolve

        def fake_resolve(self):
            # Root resolves to itself, but the destination resolves outside
            s = str(self)
            if s == tmp:
                return real_resolve(self)
            return real_resolve(Path('/outside/escaped/whatever.txt'))

        monkeypatch.setattr(Path, 'resolve', fake_resolve)
        with pytest.raises(ValueError, match='Invalid knowledge storage path'):
            knowledge_storage.store_knowledge_file(
                data=b'x', tenant_id='t', document_id='d',
                filename='evil.txt', mime_type='text/plain', settings=settings,
            )


# ── Lines 215-216: _resolve_within swallows OSError on resolve() ───────────


def test_resolve_within_returns_none_on_oserror(monkeypatch):
    from app.services import knowledge_storage

    def bad_resolve(self):
        raise OSError('cannot resolve')

    monkeypatch.setattr(Path, 'resolve', bad_resolve)
    assert knowledge_storage._resolve_within(Path('/a'), Path('/b')) is None


# ── Lines 289-290: delete_knowledge_file local — base.resolve() raises in
# the rmdir cleanup loop. We unlink successfully, then patch Path.resolve to
# raise when called on the allowed_base after the unlink.


def test_delete_local_cleanup_base_resolve_raises(monkeypatch):
    from app.services import knowledge_storage

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sub = root / 'tenants' / 't' / 'doc'
        sub.mkdir(parents=True)
        target = sub / 'f.txt'
        target.write_bytes(b'x')

        settings = _make_settings(knowledge_storage_local_path=tmp)

        # Monkeypatch resolve so the FIRST two resolutions (inside
        # _resolve_within) succeed via real implementation, and the THIRD
        # call (line 288: allowed_base.resolve()) raises.
        real_resolve = Path.resolve
        state = {'count': 0}

        def selective_resolve(self):
            state['count'] += 1
            if state['count'] == 3:
                raise OSError('cannot stat base again')
            return real_resolve(self)

        monkeypatch.setattr(Path, 'resolve', selective_resolve)
        # Should return cleanly (line 290: return)
        knowledge_storage.delete_knowledge_file(
            source_uri=f'file://{target}',
            storage_backend='local',
            object_key='tenants/t/doc/f.txt',
            settings=settings,
        )


# ── Lines 295-296: rmdir() OSError → break out of parent walk ──────────────


def test_delete_local_rmdir_breaks_on_nonempty_parent():
    from app.services import knowledge_storage

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sub = root / 'tenants' / 't' / 'doc'
        sub.mkdir(parents=True)
        target = sub / 'f.txt'
        target.write_bytes(b'x')
        # Add a sibling so the parent rmdir fails on the first iteration
        (sub / 'sibling.txt').write_bytes(b'y')

        settings = _make_settings(knowledge_storage_local_path=tmp)
        knowledge_storage.delete_knowledge_file(
            source_uri=f'file://{target}',
            storage_backend='local',
            object_key='tenants/t/doc/f.txt',
            settings=settings,
        )
        # The target is removed but the parent dir survives because of the sibling
        assert not target.exists()
        assert (sub / 'sibling.txt').exists()


# ── Lines 298-299: outer try/except OSError pass — unlink fails ────────────


def test_delete_local_unlink_failure_is_silent(monkeypatch):
    from app.services import knowledge_storage

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        sub = root / 'tenants' / 't' / 'doc'
        sub.mkdir(parents=True)
        target = sub / 'f.txt'
        target.write_bytes(b'x')
        settings = _make_settings(knowledge_storage_local_path=tmp)

        def bad_unlink(self, missing_ok=False):
            raise OSError('IO error')

        monkeypatch.setattr(Path, 'unlink', bad_unlink)
        # Must not raise
        knowledge_storage.delete_knowledge_file(
            source_uri=f'file://{target}',
            storage_backend='local',
            object_key='tenants/t/doc/f.txt',
            settings=settings,
        )
