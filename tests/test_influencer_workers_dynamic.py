"""Dynamic tests para los workers de generación + publicación.

Cubre las paths más usadas con AsyncMock para no requerir DB real ni
HTTP — el objetivo es subir cobertura del worker code que se ejercita
solo en runtime."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4


from app.ai.providers.base import (
    ImageResult,
    ProviderContentRejected,
)
from app.workers import influencer_generation_worker as gen_worker
from app.workers import influencer_publish_worker as pub_worker


# ─── generation_worker.process_one_generation ──────────────────────────────


def _gen_row(**overrides):
    row = {
        'id': uuid4(),
        'persona_id': uuid4(),
        'tenant_id': uuid4(),
        'kind': 'photo',
        'prompt': 'a girl',
        'format': '1:1',
        'count_requested': 1,
    }
    row.update(overrides)
    return row


def _persona_row():
    return {
        'id': uuid4(),
        'face': {'reference_image_urls': ['https://s3/face.jpg']},
        'body': {},
        'voice': {},
    }


def test_process_one_generation_unknown_kind_marks_failed():
    conn = AsyncMock()
    row = _gen_row(kind='unknown_kind')
    result = asyncio.run(gen_worker.process_one_generation(
        conn=conn, generation_row=row,
    ))
    assert result.status == 'failed'
    assert 'unknown kind' in (result.error or '')
    # Mark failed call:
    assert conn.execute.called


def test_process_one_generation_persona_missing():
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)  # persona disappeared
    row = _gen_row()
    result = asyncio.run(gen_worker.process_one_generation(
        conn=conn, generation_row=row,
    ))
    assert result.status == 'failed'
    assert 'persona disappeared' in (result.error or '')


def test_process_one_generation_content_rejected_marks_failed(monkeypatch):
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=_persona_row())

    async def fake_dispatch(**kwargs):
        raise ProviderContentRejected('nsfw flagged')

    monkeypatch.setattr(
        'app.workers.influencer_generation_worker.dispatch', fake_dispatch,
    )
    row = _gen_row()
    result = asyncio.run(gen_worker.process_one_generation(
        conn=conn, generation_row=row,
    ))
    assert result.status == 'failed'
    assert result.error == 'content_rejected'


def test_process_one_generation_unexpected_error(monkeypatch):
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=_persona_row())

    async def boom(**kwargs):
        raise RuntimeError('oops')

    monkeypatch.setattr(
        'app.workers.influencer_generation_worker.dispatch', boom,
    )
    result = asyncio.run(gen_worker.process_one_generation(
        conn=conn, generation_row=_gen_row(),
    ))
    assert result.status == 'failed'
    assert result.error == 'unexpected'


def test_process_one_generation_success_image_path(monkeypatch):
    captured_uploads: list[tuple[str, bytes, str]] = []

    async def fake_uploader(key, data, mime):
        captured_uploads.append((key, data, mime))
        return f's3://test/{key}'

    async def fake_dispatch(**kwargs):
        return [
            ImageResult(image_bytes=b'\x89PNG', mime='image/png', width=1024, height=1024),
        ]

    monkeypatch.setattr(
        'app.workers.influencer_generation_worker.dispatch', fake_dispatch,
    )

    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=_persona_row())

    result = asyncio.run(gen_worker.process_one_generation(
        conn=conn,
        generation_row=_gen_row(),
        storage_upload=fake_uploader,
    ))
    assert result.status == 'succeeded'
    assert result.assets_created == 1
    assert len(captured_uploads) == 1
    assert captured_uploads[0][2] == 'image/png'


def test_claim_next_generation_returns_record():
    conn = AsyncMock()
    expected = _gen_row()
    conn.fetchrow = AsyncMock(return_value=expected)
    result = asyncio.run(gen_worker.claim_next_generation(conn))
    assert result is expected


# ─── publish_worker.process_one_post ──────────────────────────────────────


def _post_row(**overrides):
    row = {
        'id': uuid4(),
        'persona_id': uuid4(),
        'tenant_id': uuid4(),
        'caption': 'hola mundo',
        'kind': 'photo',
        'platforms': ['instagram'],
        'disclose_ai': True,
    }
    row.update(overrides)
    return row


def test_publish_no_active_connection_marks_failed(monkeypatch):
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    # resolve_token returns None when no active connection
    monkeypatch.setattr(
        'app.workers.influencer_publish_worker.resolve_token',
        AsyncMock(return_value=None),
    )

    async def publish(*args, **kwargs):
        raise AssertionError('should not call publish without token')

    result = asyncio.run(pub_worker.process_one_post(
        conn=conn, post_row=_post_row(), publish=publish,
    ))
    assert result.status == 'failed'
    assert 'no active connection' in (result.error or '')


def test_publish_happy_path_marks_published(monkeypatch):
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    monkeypatch.setattr(
        'app.workers.influencer_publish_worker.resolve_token',
        AsyncMock(return_value='secret-ref-1'),
    )

    captured: list = []

    async def publish(platform, token, caption, kind, params):
        captured.append((platform, token, caption, kind))
        return f'ext-{platform}-1'

    result = asyncio.run(pub_worker.process_one_post(
        conn=conn, post_row=_post_row(), publish=publish,
    ))
    assert result.status == 'published'
    assert result.external_post_ids == {'instagram': 'ext-instagram-1'}
    assert captured[0][0] == 'instagram'
    # AI disclosure prepended since disclose_ai=True
    assert '#AI' in captured[0][2]


def test_publish_failure_in_one_platform_breaks(monkeypatch):
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    monkeypatch.setattr(
        'app.workers.influencer_publish_worker.resolve_token',
        AsyncMock(return_value='secret-ref-1'),
    )

    async def publish(platform, *args, **kwargs):
        if platform == 'tiktok':
            raise RuntimeError('tiktok rate limited')
        return 'ext-1'

    result = asyncio.run(pub_worker.process_one_post(
        conn=conn,
        post_row=_post_row(platforms=['instagram', 'tiktok']),
        publish=publish,
    ))
    assert result.status == 'failed'
    assert 'tiktok' in (result.error or '')
    # Instagram succeeded antes del fail; debe estar en external_post_ids
    assert 'instagram' in result.external_post_ids


def test_claim_next_approved_post_returns_record():
    conn = AsyncMock()
    expected = _post_row()
    conn.fetchrow = AsyncMock(return_value=expected)
    result = asyncio.run(pub_worker.claim_next_approved_post(conn))
    assert result is expected


def test_resolve_token_returns_secret_ref():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(
        return_value={'oauth_token_ref': 'ref-1', 'status': 'connected', 'hint': 'abcd'},
    )
    result = asyncio.run(
        pub_worker.resolve_token(conn, persona_id=uuid4(), platform='instagram'),
    )
    assert result == 'ref-1'


def test_resolve_token_returns_none_without_connection():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    result = asyncio.run(
        pub_worker.resolve_token(conn, persona_id=uuid4(), platform='instagram'),
    )
    assert result is None
