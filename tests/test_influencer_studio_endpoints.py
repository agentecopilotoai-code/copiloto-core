"""Tests para los endpoints añadidos en UI-INFLU-014.13:

  - `POST /v1/influencer/personas/{id}/face/reference` (upload-reference)
  - `GET /v1/influencer/personas/{id}/studio` ampliado (assets + face_variations)
  - `POST /v1/influencer/personas/{id}/generate` con persona en draft
    (antes solo 'active'; ahora se acepta draft/paused)
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException, UploadFile

from app.influencer import casting_router as cr
from app.influencer import face_variations_router as fvr
from app.influencer import generations_router as gr
from app.services.influencer_storage import StoredInfluencerAsset


# ── upload_reference_image ─────────────────────────────────────────────────


def _make_upload_file(content: bytes, content_type: str = 'image/png',
                     filename: str = 'ref.png') -> UploadFile:
    """Construye un UploadFile real con un BytesIO."""
    from io import BytesIO
    return UploadFile(
        filename=filename,
        file=BytesIO(content),
        headers={'content-type': content_type},
    )


def _run(coro):
    return asyncio.run(coro)


def test_upload_reference_image_persona_not_found_404(monkeypatch):
    tenant_id = uuid4()
    persona_id = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tenant_id))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)

    file = _make_upload_file(b'data', 'image/png')
    with pytest.raises(HTTPException) as exc:
        _run(fvr.upload_reference_image(
            persona_id=persona_id, request=request, file=file, conn=conn,
        ))
    assert exc.value.status_code == 404
    assert 'persona not found' in exc.value.detail


def test_upload_reference_image_unsupported_mime_415(monkeypatch):
    tenant_id = uuid4()
    persona_id = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tenant_id))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value={'id': persona_id})

    file = _make_upload_file(b'pdf-bytes', 'application/pdf', 'doc.pdf')
    with pytest.raises(HTTPException) as exc:
        _run(fvr.upload_reference_image(
            persona_id=persona_id, request=request, file=file, conn=conn,
        ))
    assert exc.value.status_code == 415
    assert 'mime' in exc.value.detail.lower()


def test_upload_reference_image_empty_file_400(monkeypatch):
    tenant_id = uuid4()
    persona_id = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tenant_id))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value={'id': persona_id})

    file = _make_upload_file(b'', 'image/png')
    with pytest.raises(HTTPException) as exc:
        _run(fvr.upload_reference_image(
            persona_id=persona_id, request=request, file=file, conn=conn,
        ))
    assert exc.value.status_code == 400
    assert 'vacío' in exc.value.detail


def test_upload_reference_image_oversize_413(monkeypatch):
    tenant_id = uuid4()
    persona_id = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tenant_id))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value={'id': persona_id})

    # 11MB > 10MB cap.
    huge = b'\x00' * (11 * 1024 * 1024)
    file = _make_upload_file(huge, 'image/png')
    with pytest.raises(HTTPException) as exc:
        _run(fvr.upload_reference_image(
            persona_id=persona_id, request=request, file=file, conn=conn,
        ))
    assert exc.value.status_code == 413


def test_upload_reference_image_happy_path(monkeypatch):
    tenant_id = uuid4()
    persona_id = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tenant_id))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value={'id': persona_id})

    fake_key = f'tenants/{tenant_id}/influencer/references/{persona_id}/0.png'
    monkeypatch.setattr(
        fvr, 'store_reference_asset',
        lambda **kw: StoredInfluencerAsset(
            storage_backend='local', bucket=None,
            object_key=fake_key,
            source_uri=f'file:///tmp/{fake_key}',
            size_bytes=len(kw['data']), mime='image/png',
        ),
    )

    async def _fake_fetch_config(conn, tid):
        return {'backend': 'local'}
    monkeypatch.setattr(
        fvr, 'fetch_tenant_knowledge_storage_config', _fake_fetch_config,
    )

    file = _make_upload_file(b'\x89PNG-fake', 'image/png')
    resp = _run(fvr.upload_reference_image(
        persona_id=persona_id, request=request, file=file, conn=conn,
    ))
    assert resp.storage_key == fake_key
    assert resp.mime == 'image/png'
    assert resp.url.startswith('/admin/api/core/v1/influencer/storage/')
    assert resp.size_bytes > 0


def test_upload_reference_image_storage_error_500(monkeypatch):
    tenant_id = uuid4()
    persona_id = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tenant_id))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value={'id': persona_id})

    def _boom(**kw):
        raise RuntimeError('disk full')
    monkeypatch.setattr(fvr, 'store_reference_asset', _boom)

    async def _fake_fetch_config(conn, tid):
        return {'backend': 'local'}
    monkeypatch.setattr(
        fvr, 'fetch_tenant_knowledge_storage_config', _fake_fetch_config,
    )

    file = _make_upload_file(b'png', 'image/png')
    with pytest.raises(HTTPException) as exc:
        _run(fvr.upload_reference_image(
            persona_id=persona_id, request=request, file=file, conn=conn,
        ))
    assert exc.value.status_code == 500
    assert 'failed to persist reference' in exc.value.detail


# ── create_generation (relaxed status) ─────────────────────────────────────


def test_create_generation_accepts_draft_status(monkeypatch):
    """UI-INFLU-014.13: antes solo 'active'; ahora draft también vale."""
    tenant_id = uuid4()
    persona_id = uuid4()
    user_id = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(
        tenant_id=tenant_id, user_id=user_id,
    ))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    # Persona en estado draft (no activo).
    persona_row = {'id': persona_id, 'status': 'draft'}
    new_gen = {
        'id': uuid4(), 'tenant_id': tenant_id, 'persona_id': persona_id,
        'kind': 'photo', 'prompt': 'test', 'format': '1:1',
        'count_requested': 1, 'status': 'queued', 'provider_used': None,
        'cost_credits': 2, 'params': {}, 'error_message': None,
        'created_at': __import__('datetime').datetime.now(),
        'started_at': None, 'completed_at': None,
    }
    conn.fetchrow = AsyncMock(side_effect=[persona_row, new_gen])

    body = gr.GenerateRequest(kind='photo', prompt='test', format='1:1', count=1)
    resp = _run(gr.create_generation(
        persona_id=persona_id, request=request, body=body, conn=conn,
    ))
    assert resp.kind == 'photo'
    assert resp.status == 'queued'


def test_create_generation_accepts_paused_status(monkeypatch):
    tenant_id = uuid4()
    persona_id = uuid4()
    user_id = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(
        tenant_id=tenant_id, user_id=user_id,
    ))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    persona_row = {'id': persona_id, 'status': 'paused'}
    new_gen = {
        'id': uuid4(), 'tenant_id': tenant_id, 'persona_id': persona_id,
        'kind': 'photo', 'prompt': 't', 'format': '1:1',
        'count_requested': 1, 'status': 'queued', 'provider_used': None,
        'cost_credits': 2, 'params': {}, 'error_message': None,
        'created_at': __import__('datetime').datetime.now(),
        'started_at': None, 'completed_at': None,
    }
    conn.fetchrow = AsyncMock(side_effect=[persona_row, new_gen])
    body = gr.GenerateRequest(kind='photo', prompt='t', format='1:1', count=1)
    resp = _run(gr.create_generation(
        persona_id=persona_id, request=request, body=body, conn=conn,
    ))
    assert resp.status == 'queued'


def test_create_generation_rejects_archived_status(monkeypatch):
    tenant_id = uuid4()
    persona_id = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(
        tenant_id=tenant_id, user_id=uuid4(),
    ))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value={'id': persona_id, 'status': 'archived'})

    body = gr.GenerateRequest(kind='photo', prompt='t', format='1:1', count=1)
    with pytest.raises(HTTPException) as exc:
        _run(gr.create_generation(
            persona_id=persona_id, request=request, body=body, conn=conn,
        ))
    assert exc.value.status_code == 409
    assert 'archived' in exc.value.detail


# ── get_studio (extended bundle) ───────────────────────────────────────────


def test_get_studio_returns_face_variations_and_assets(monkeypatch):
    """El bundle del studio ahora incluye face_variations + assets en
    cada recent_generation."""
    from datetime import datetime, timezone
    tenant_id = uuid4()
    persona_id = uuid4()
    gen_id = uuid4()
    asset_id = uuid4()
    fv_id = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tenant_id))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)

    persona_row = {
        'id': persona_id, 'name': 'Sofía', 'handle': 'sofia',
        'status': 'active', 'category': 'Lifestyle',
    }
    now = datetime.now(timezone.utc)
    gen_row = {
        'id': gen_id, 'kind': 'photo', 'status': 'succeeded',
        'prompt': 'a scene', 'format': '1:1', 'cost_credits': 2,
        'error_message': None, 'created_at': now, 'completed_at': now,
    }
    # Patch _get_or_refresh_stats para que no busque DB real.
    async def _fake_stats(conn, pid, tid):
        return {
            'posts_total': 0, 'reach_30d': 0,
            'engagement_rate': 0.0, 'scheduled_count': 0,
        }
    monkeypatch.setattr(cr, '_get_or_refresh_stats', _fake_stats)

    conn.fetchrow = AsyncMock(side_effect=[persona_row, None])  # persona + next_post
    # platforms_connected + gens + assets + face_variations
    conn.fetch = AsyncMock(side_effect=[
        [],  # platforms_connected
        [gen_row],  # generations
        [{
            'id': asset_id, 'generation_id': gen_id,
            'storage_key': f'tenants/{tenant_id}/influencer/generations/{gen_id}/0.png',
            'mime': 'image/png', 'width': 1024, 'height': 1024, 'duration_s': None,
        }],
        [{
            'id': fv_id,
            'storage_key': f'tenants/{tenant_id}/influencer/face-variations/req-1/0.png',
            'mime': 'image/png', 'marked_canonical': True,
        }],
    ])

    resp = _run(cr.get_studio(persona_id=persona_id, request=request, conn=conn))

    # persona.avatar_url derived from canonical face_variation
    assert resp.persona['avatar_url'] is not None
    assert resp.persona['category'] == 'Lifestyle'

    # face_variations populated
    assert len(resp.face_variations) == 1
    assert resp.face_variations[0].canonical is True

    # recent_generations have assets
    assert len(resp.recent_generations) == 1
    g = resp.recent_generations[0]
    assert g.kind == 'photo'
    assert g.prompt == 'a scene'
    assert g.cost_credits == 2
    assert len(g.assets) == 1
    assert g.assets[0].mime == 'image/png'
    assert g.assets[0].width == 1024


def test_get_studio_persona_not_found(monkeypatch):
    tenant_id = uuid4()
    persona_id = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tenant_id))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        _run(cr.get_studio(persona_id=persona_id, request=request, conn=conn))
    assert exc.value.status_code == 404


def test_get_studio_no_face_variations_avatar_is_none(monkeypatch):
    """Cuando el personaje no tiene face_variations todavía, avatar_url=None."""
    tenant_id = uuid4()
    persona_id = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tenant_id))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    persona_row = {
        'id': persona_id, 'name': 'X', 'handle': 'x',
        'status': 'draft', 'category': None,
    }
    async def _fake_stats(conn, pid, tid):
        return {
            'posts_total': 0, 'reach_30d': 0,
            'engagement_rate': 0.0, 'scheduled_count': 0,
        }
    monkeypatch.setattr(cr, '_get_or_refresh_stats', _fake_stats)

    conn.fetchrow = AsyncMock(side_effect=[persona_row, None])
    conn.fetch = AsyncMock(side_effect=[[], [], [], []])

    resp = _run(cr.get_studio(persona_id=persona_id, request=request, conn=conn))
    assert resp.persona['avatar_url'] is None
    assert resp.face_variations == []
    assert resp.recent_generations == []


# ── list_generations / get_generation handlers ─────────────────────────────


def test_get_generation_not_found_404():
    tenant_id = uuid4()
    gen_id = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tenant_id))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)

    with pytest.raises(HTTPException) as exc:
        _run(gr.get_generation(generation_id=gen_id, request=request, conn=conn))
    assert exc.value.status_code == 404


def test_get_generation_happy_path_returns_detail():
    from datetime import datetime
    tenant_id = uuid4()
    persona_id = uuid4()
    gen_id = uuid4()
    asset_id = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tenant_id))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    now = datetime.now()
    gen_row = {
        'id': gen_id, 'tenant_id': tenant_id, 'persona_id': persona_id,
        'kind': 'photo', 'prompt': 'p', 'format': '1:1',
        'count_requested': 1, 'status': 'succeeded', 'provider_used': 'grok',
        'cost_credits': 2, 'params': {}, 'error_message': None,
        'created_at': now, 'started_at': now, 'completed_at': now,
    }
    asset_row = {
        'id': asset_id, 'persona_id': persona_id, 'generation_id': gen_id,
        'kind': 'photo', 'storage_key': 'tenants/x/influencer/generations/g/0.png',
        'mime': 'image/png', 'width': 1024, 'height': 1024, 'duration_s': None,
        'bytes': 12345, 'marked_canonical': False,
    }
    conn.fetchrow = AsyncMock(return_value=gen_row)
    conn.fetch = AsyncMock(return_value=[asset_row])

    resp = _run(gr.get_generation(generation_id=gen_id, request=request, conn=conn))
    assert resp.generation.id == gen_id
    assert resp.generation.status == 'succeeded'
    assert len(resp.assets) == 1
    assert resp.assets[0].mime == 'image/png'


def test_list_generations_no_filters_returns_paginated_list():
    from datetime import datetime
    tenant_id = uuid4()
    persona_id = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tenant_id))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    now = datetime.now()
    gen_row = {
        'id': uuid4(), 'tenant_id': tenant_id, 'persona_id': persona_id,
        'kind': 'photo', 'prompt': 'p', 'format': '1:1',
        'count_requested': 1, 'status': 'succeeded', 'provider_used': None,
        'cost_credits': 2, 'params': {}, 'error_message': None,
        'created_at': now, 'started_at': None, 'completed_at': now,
    }
    conn.fetch = AsyncMock(return_value=[gen_row])
    conn.fetchrow = AsyncMock(return_value={'c': 1})

    resp = _run(gr.list_generations(
        persona_id=persona_id, request=request,
        kind=None, status_filter=None, limit=20, offset=0, conn=conn,
    ))
    assert resp.total == 1
    assert len(resp.items) == 1


def test_list_generations_with_kind_and_status_filter():
    """Cuando `kind` y `status` están seteados, la query agrega ambos
    WHERE clauses."""
    tenant_id = uuid4()
    persona_id = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=tenant_id))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value={'c': 0})

    resp = _run(gr.list_generations(
        persona_id=persona_id, request=request,
        kind='reel', status_filter='succeeded', limit=10, offset=5, conn=conn,
    ))
    assert resp.total == 0
    assert resp.items == []
    # Verifica que la SQL incluye los placeholders para kind + status.
    sql = conn.fetch.call_args[0][0]
    assert 'kind = $' in sql
    assert 'status = $' in sql


# ── _validate_format_for_kind direct ───────────────────────────────────────


def test_validate_format_invalid_combo_raises_422():
    with pytest.raises(HTTPException) as exc:
        gr._validate_format_for_kind('reel', '1:1')  # reel solo permite 9:16
    assert exc.value.status_code == 422


def test_validate_format_unknown_kind_raises_422():
    with pytest.raises(HTTPException) as exc:
        gr._validate_format_for_kind('unknown_kind', '1:1')
    assert exc.value.status_code == 422


def test_validate_format_valid_combo_passes():
    # No raises.
    gr._validate_format_for_kind('photo', '1:1')
    gr._validate_format_for_kind('reel', '9:16')


# ── _estimate_cost ─────────────────────────────────────────────────────────


def test_estimate_cost_by_kind():
    assert gr._estimate_cost('photo', 1) == 2
    assert gr._estimate_cost('reel', 1) == 10
    assert gr._estimate_cost('photo', 5) == 10
    assert gr._estimate_cost('reel', 3) == 30
    # kind desconocido → base default = 5.
    assert gr._estimate_cost('unknown', 1) == 5
    # count <= 0 se trata como 1.
    assert gr._estimate_cost('photo', 0) == 2


# ── create_generation: persona missing 404 ─────────────────────────────────


def test_create_generation_persona_not_found_404():
    tenant_id = uuid4()
    persona_id = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(
        tenant_id=tenant_id, user_id=uuid4(),
    ))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)

    body = gr.GenerateRequest(kind='photo', prompt='t', format='1:1', count=1)
    with pytest.raises(HTTPException) as exc:
        _run(gr.create_generation(
            persona_id=persona_id, request=request, body=body, conn=conn,
        ))
    assert exc.value.status_code == 404


def test_create_generation_invalid_format_for_kind_422():
    tenant_id = uuid4()
    persona_id = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(
        tenant_id=tenant_id, user_id=uuid4(),
    ))
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value={'id': persona_id, 'status': 'active'})

    body = gr.GenerateRequest(kind='reel', prompt='t', format='1:1', count=1)
    with pytest.raises(HTTPException) as exc:
        _run(gr.create_generation(
            persona_id=persona_id, request=request, body=body, conn=conn,
        ))
    assert exc.value.status_code == 422


# ── _require_tenant_id branches ────────────────────────────────────────────


def test_generations_require_tenant_id_no_tenant_404():
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=None))
    with pytest.raises(HTTPException) as exc:
        gr._require_tenant_id(request)
    assert exc.value.status_code == 404


def test_generations_require_tenant_id_string_coerces():
    tid = uuid4()
    request = SimpleNamespace(state=SimpleNamespace(tenant_id=str(tid)))
    assert gr._require_tenant_id(request) == tid
