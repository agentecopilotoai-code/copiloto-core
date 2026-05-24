"""Tests para `serve_storage_asset` (UI-INFLU-014.7).

Cubre el endpoint `GET /v1/influencer/storage/{key:path}` que sirve
assets locales o desde S3. Validamos:
  - 401 sin actor autenticado.
  - 400 si la key no empieza con `tenants/{uuid}/`.
  - 400 si la key contiene `..`.
  - 403 si el caller no tiene membership en el tenant del path.
  - support_mode=true bypasa la validación de membership.
  - Backend local: 404 cuando el archivo no existe.
  - Backend s3: 404 cuando s3_get_asset_bytes devuelve None.
  - Backend desconocido: 500.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.influencer import face_variations_router as fvr


def _run(coro):
    return asyncio.run(coro)


def _make_request(actor_id=None, support_mode=False):
    return SimpleNamespace(state=SimpleNamespace(
        actor_id=actor_id,
        support_mode=support_mode,
    ))


# ── _extract_tenant_id_from_key ────────────────────────────────────────────


def test_extract_tenant_id_from_key_happy_path():
    tid = uuid4()
    key = f'tenants/{tid}/influencer/face-variations/req/0.png'
    assert fvr._extract_tenant_id_from_key(key) == tid


def test_extract_tenant_id_from_key_invalid_prefix():
    assert fvr._extract_tenant_id_from_key('foo/bar/baz') is None


def test_extract_tenant_id_from_key_invalid_uuid():
    assert fvr._extract_tenant_id_from_key('tenants/not-a-uuid/file.png') is None


def test_extract_tenant_id_from_key_too_short():
    assert fvr._extract_tenant_id_from_key('tenants') is None


# ── _key_belongs_to_tenant ─────────────────────────────────────────────────


def test_key_belongs_to_tenant_true():
    tid = uuid4()
    key = f'tenants/{tid}/influencer/foo'
    assert fvr._key_belongs_to_tenant(key, tid) is True


def test_key_belongs_to_tenant_false():
    tid = uuid4()
    other = uuid4()
    key = f'tenants/{other}/influencer/foo'
    assert fvr._key_belongs_to_tenant(key, tid) is False


# ── serve_storage_asset ────────────────────────────────────────────────────


def test_serve_storage_asset_no_actor_401():
    request = _make_request(actor_id=None)
    conn = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        _run(fvr.serve_storage_asset(
            object_key='tenants/00000000-0000-0000-0000-000000000000/x.png',
            request=request, conn=conn,
        ))
    assert exc.value.status_code == 401


def test_serve_storage_asset_invalid_key_400():
    actor_id = uuid4()
    request = _make_request(actor_id=actor_id)
    conn = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        _run(fvr.serve_storage_asset(
            object_key='not-tenants-prefix.png', request=request, conn=conn,
        ))
    assert exc.value.status_code == 400
    assert 'tenants/{uuid}' in exc.value.detail


def test_serve_storage_asset_path_traversal_400():
    actor_id = uuid4()
    tid = uuid4()
    request = _make_request(actor_id=actor_id)
    conn = AsyncMock()
    with pytest.raises(HTTPException) as exc:
        _run(fvr.serve_storage_asset(
            object_key=f'tenants/{tid}/../etc/passwd',
            request=request, conn=conn,
        ))
    assert exc.value.status_code == 400
    assert 'forbidden' in exc.value.detail


def test_serve_storage_asset_no_membership_403(monkeypatch):
    actor_id = uuid4()
    tid = uuid4()
    request = _make_request(actor_id=actor_id, support_mode=False)
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    # membership check returns None.
    conn.fetchrow = AsyncMock(return_value=None)
    with pytest.raises(HTTPException) as exc:
        _run(fvr.serve_storage_asset(
            object_key=f'tenants/{tid}/influencer/x.png',
            request=request, conn=conn,
        ))
    assert exc.value.status_code == 403


def test_serve_storage_asset_local_file_not_found_404(monkeypatch, tmp_path):
    actor_id = uuid4()
    tid = uuid4()
    request = _make_request(actor_id=actor_id, support_mode=True)
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value={'?column?': 1})

    # Mock fetch_tenant_knowledge_storage_config para backend=local.
    async def _fake_fetch(conn, tenant_id):
        return {'backend': 'local'}
    monkeypatch.setattr(fvr, 'fetch_tenant_knowledge_storage_config', _fake_fetch)
    # Mock get_settings → tmp_path como knowledge_storage_local_path.
    settings = SimpleNamespace(knowledge_storage_local_path=str(tmp_path))
    monkeypatch.setattr(fvr, 'get_settings', lambda: settings)

    with pytest.raises(HTTPException) as exc:
        _run(fvr.serve_storage_asset(
            object_key=f'tenants/{tid}/influencer/doesnt-exist.png',
            request=request, conn=conn,
        ))
    assert exc.value.status_code == 404


def test_serve_storage_asset_local_file_found_returns_FileResponse(
    monkeypatch, tmp_path,
):
    from fastapi.responses import FileResponse

    actor_id = uuid4()
    tid = uuid4()
    object_key = f'tenants/{tid}/influencer/file.png'

    # Crear el archivo real en disco.
    file_path = Path(tmp_path) / object_key
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b'\x89PNG-data')

    request = _make_request(actor_id=actor_id, support_mode=True)
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)

    async def _fake_fetch(conn, tenant_id):
        return {'backend': 'local'}
    monkeypatch.setattr(fvr, 'fetch_tenant_knowledge_storage_config', _fake_fetch)
    settings = SimpleNamespace(knowledge_storage_local_path=str(tmp_path))
    monkeypatch.setattr(fvr, 'get_settings', lambda: settings)

    resp = _run(fvr.serve_storage_asset(
        object_key=object_key, request=request, conn=conn,
    ))
    assert isinstance(resp, FileResponse)
    assert resp.media_type == 'image/png'


def test_serve_storage_asset_s3_not_found_404(monkeypatch):
    actor_id = uuid4()
    tid = uuid4()
    request = _make_request(actor_id=actor_id, support_mode=True)
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)

    async def _fake_fetch(conn, tenant_id):
        return {'backend': 's3', 'bucket': 'b'}
    monkeypatch.setattr(fvr, 'fetch_tenant_knowledge_storage_config', _fake_fetch)
    monkeypatch.setattr(fvr, 'get_settings', lambda: SimpleNamespace(
        knowledge_storage_local_path='/tmp',
    ))
    # s3 returns None → 404
    monkeypatch.setattr(fvr, 's3_get_asset_bytes', lambda **kw: None)

    with pytest.raises(HTTPException) as exc:
        _run(fvr.serve_storage_asset(
            object_key=f'tenants/{tid}/influencer/x.png',
            request=request, conn=conn,
        ))
    assert exc.value.status_code == 404


def test_serve_storage_asset_s3_found_returns_Response(monkeypatch):
    from fastapi.responses import Response

    actor_id = uuid4()
    tid = uuid4()
    request = _make_request(actor_id=actor_id, support_mode=True)
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)

    async def _fake_fetch(conn, tenant_id):
        return {'backend': 's3', 'bucket': 'b'}
    monkeypatch.setattr(fvr, 'fetch_tenant_knowledge_storage_config', _fake_fetch)
    monkeypatch.setattr(fvr, 'get_settings', lambda: SimpleNamespace(
        knowledge_storage_local_path='/tmp',
    ))
    monkeypatch.setattr(
        fvr, 's3_get_asset_bytes', lambda **kw: (b'image-bytes', 'image/jpeg'),
    )

    resp = _run(fvr.serve_storage_asset(
        object_key=f'tenants/{tid}/influencer/x.jpg',
        request=request, conn=conn,
    ))
    assert isinstance(resp, Response)
    assert resp.media_type == 'image/jpeg'
    assert resp.body == b'image-bytes'


def test_serve_storage_asset_unsupported_backend_500(monkeypatch):
    actor_id = uuid4()
    tid = uuid4()
    request = _make_request(actor_id=actor_id, support_mode=True)
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)

    async def _fake_fetch(conn, tenant_id):
        return {'backend': 'azure'}
    monkeypatch.setattr(fvr, 'fetch_tenant_knowledge_storage_config', _fake_fetch)
    monkeypatch.setattr(fvr, 'get_settings', lambda: SimpleNamespace(
        knowledge_storage_local_path='/tmp',
    ))

    with pytest.raises(HTTPException) as exc:
        _run(fvr.serve_storage_asset(
            object_key=f'tenants/{tid}/influencer/x.png',
            request=request, conn=conn,
        ))
    assert exc.value.status_code == 500
    assert 'unsupported storage backend' in exc.value.detail


def test_serve_storage_asset_with_membership_success(monkeypatch, tmp_path):
    """Caller sin support_mode pero CON membership en user_tenant_roles."""
    from fastapi.responses import FileResponse

    actor_id = uuid4()
    tid = uuid4()
    object_key = f'tenants/{tid}/influencer/x.png'
    file_path = Path(tmp_path) / object_key
    file_path.parent.mkdir(parents=True)
    file_path.write_bytes(b'data')

    request = _make_request(actor_id=actor_id, support_mode=False)
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    # membership returns row (truthy).
    conn.fetchrow = AsyncMock(return_value={'?column?': 1})

    async def _fake_fetch(conn, tenant_id):
        return {'backend': 'local'}
    monkeypatch.setattr(fvr, 'fetch_tenant_knowledge_storage_config', _fake_fetch)
    settings = SimpleNamespace(knowledge_storage_local_path=str(tmp_path))
    monkeypatch.setattr(fvr, 'get_settings', lambda: settings)

    resp = _run(fvr.serve_storage_asset(
        object_key=object_key, request=request, conn=conn,
    ))
    assert isinstance(resp, FileResponse)
