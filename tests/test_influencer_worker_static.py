"""Static tests para ``generation_worker`` — TASK-INFLU-012."""
from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from app.ai.providers.base import (
    AudioResult,
    ImageResult,
    TextResult,
    VideoResult,
)
from app.workers import influencer_generation_worker as worker
from app.workers.influencer_generation_worker import (
    _KIND_TO_MODALITY,
    _build_persona_anchor,
    _extract_asset_bytes,
    _noop_uploader,
)


SRC = Path('app/workers/influencer_generation_worker.py').read_text(encoding='utf-8')


def test_kind_to_modality_mapping():
    """photo/carousel/story/ad/face_variation → image; reel → video; voice → tts."""
    for k in ('photo', 'carousel', 'story', 'ad', 'face_variation'):
        assert _KIND_TO_MODALITY[k] == 'image'
    assert _KIND_TO_MODALITY['reel'] == 'video'
    assert _KIND_TO_MODALITY['voice_sample'] == 'tts'


def test_uses_for_update_skip_locked():
    """Pattern de queue obligatorio (multi-worker safe)."""
    assert 'for update skip locked' in SRC.lower()


def test_content_rejected_marks_failed():
    """ProviderContentRejected → status='failed', error 'content_rejected'."""
    assert 'ProviderContentRejected' in SRC
    assert "'failed'" in SRC
    assert 'content_rejected' in SRC


def test_dispatch_uses_provider_dispatcher():
    """El worker invoca `dispatch()` (TASK-INFLU-007), no providers directos."""
    assert 'from app.ai.dispatcher import dispatch' in SRC
    assert 'await dispatch(' in SRC


def test_storage_key_format():
    """Asset storage key incluye tenant + persona + generation hierarchy."""
    assert 'tenants/{tenant_id}/influencer/personas/{persona_id}/' in SRC


def test_build_persona_anchor_from_persona_row():
    row = {
        'id': uuid4(),
        'face': {
            'reference_image_urls': ['https://s3/face1.jpg'],
            'style_tokens': ['cálida'],
        },
        'body': {'build': 'athletic'},
        'voice': {'voice_id_ref': 'voice-1', 'tone': 'warm'},
    }
    anchor = _build_persona_anchor(row)
    assert anchor.reference_image_urls == ('https://s3/face1.jpg',)
    assert anchor.style_tokens == ('cálida',)
    assert anchor.voice_id_ref == 'voice-1'
    assert anchor.voice_tone == 'warm'


def test_build_persona_anchor_handles_empty_jsonb():
    """Si face/body/voice son {} (paso wizard sin completar), no explota."""
    row = {'id': uuid4(), 'face': {}, 'body': {}, 'voice': {}}
    anchor = _build_persona_anchor(row)
    assert anchor.reference_image_urls == ()
    assert anchor.voice_id_ref is None


def test_extract_asset_bytes_image():
    result = ImageResult(image_bytes=b'png', mime='image/png', width=1024, height=1024)
    payload, mime, dims = _extract_asset_bytes(result)
    assert payload == b'png'
    assert mime == 'image/png'
    assert dims == {'width': 1024, 'height': 1024}


def test_extract_asset_bytes_video():
    result = VideoResult(
        video_bytes=b'mp4', mime='video/mp4', width=1080, height=1920, duration_s=15.0,
    )
    payload, mime, dims = _extract_asset_bytes(result)
    assert mime == 'video/mp4'
    assert dims['duration_s'] == 15.0


def test_extract_asset_bytes_audio():
    result = AudioResult(audio_bytes=b'mp3', mime='audio/mpeg', duration_s=3.2)
    payload, mime, dims = _extract_asset_bytes(result)
    assert mime == 'audio/mpeg'
    assert dims == {'duration_s': 3.2}


def test_extract_asset_bytes_text():
    result = TextResult(text='hola', finish_reason='stop')
    payload, mime, dims = _extract_asset_bytes(result)
    assert payload == b'hola'
    assert mime == 'text/plain'


def test_extract_asset_bytes_unknown_raises():
    with pytest.raises(ValueError):
        _extract_asset_bytes(object())


def test_noop_uploader_returns_stub_key():
    url = asyncio.run(_noop_uploader('k/1', b'x', 'image/png'))
    assert 's3://stub/' in url


def test_storage_uploader_is_injectable():
    """`process_one_generation` acepta storage_upload param para tests."""
    import inspect
    sig = inspect.signature(worker.process_one_generation)
    assert 'storage_upload' in sig.parameters
