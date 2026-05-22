"""Tests dinámicos para subir coverage de los routers del módulo Influencer
(batch 3 — TASK-INFLU-014..019).

Usa AsyncMock + Starlette Request directo para ejercer los endpoints sin
DB ni HTTP real. Foco en happy paths + algunos error paths para empujar
el agregado backend ≥90% (gate del CI).
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.influencer import casting_router as casting_mod
from app.influencer import credits_router as credits_router_mod
from app.influencer import face_variations_router as fv_mod
from app.influencer import generations_router as gen_mod
from app.influencer import personas_router as personas_mod
from app.influencer import posts_router as posts_mod
from app.influencer import voice_router as voice_mod
from app.influencer import wizard_router as wizard_mod
from app.influencer.personas_models import PersonaCreate, PersonaUpdate
from app.influencer.wizard_models import (
    BodyStep,
    FaceStep,
    IdentityStep,
    PlatformsStep,
    VoiceStep,
)
from app.influencer import credits as credits_helper


def _req(tenant_id=None, user_id=None, is_platform_owner=False):
    """Mini Starlette-like request con state populated."""
    return SimpleNamespace(
        state=SimpleNamespace(
            tenant_id=tenant_id or uuid4(),
            user_id=user_id or uuid4(),
            is_platform_owner=is_platform_owner,
        ),
    )


def _persona_row(**overrides):
    base = {
        'id': uuid4(),
        'tenant_id': uuid4(),
        'name': 'Sofia',
        'handle': 'sofia',
        'status': 'active',
        'category': 'fashion',
        'face': {},
        'body': {},
        'identity': {},
        'voice': {},
        'platforms': {},
        'mode': 'manual_approval',
        'disclose_ai': True,
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc),
        'created_by': None,
        'archived_at': None,
    }
    base.update(overrides)
    return base


# ─── credits.py helpers ────────────────────────────────────────────────────


def test_credits_current_balance_empty():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    bal = asyncio.run(credits_helper.current_balance(conn, uuid4()))
    assert bal == 0


def test_credits_current_balance_returns_last_row():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={'balance_after': 42})
    assert asyncio.run(credits_helper.current_balance(conn, uuid4())) == 42


def test_credits_debit_happy_path():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={'balance_after': 100})
    conn.execute = AsyncMock(return_value=None)
    new = asyncio.run(
        credits_helper.debit(conn, tenant_id=uuid4(), amount=10, reason='gen:photo'),
    )
    assert new == 90
    assert conn.execute.called


def test_credits_debit_insufficient_raises():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={'balance_after': 5})
    with pytest.raises(credits_helper.InsufficientCreditsError):
        asyncio.run(
            credits_helper.debit(
                conn, tenant_id=uuid4(), amount=100, reason='gen:reel',
            ),
        )


def test_credits_credit_happy_path():
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value={'balance_after': 50})
    conn.execute = AsyncMock(return_value=None)
    new = asyncio.run(
        credits_helper.credit(
            conn, tenant_id=uuid4(), amount=10, reason='topup', ref='pay_1',
        ),
    )
    assert new == 60


def test_credits_credit_rejects_zero():
    conn = AsyncMock()
    with pytest.raises(ValueError):
        asyncio.run(credits_helper.credit(
            conn, tenant_id=uuid4(), amount=0, reason='x',
        ))


def test_credits_pricing_map():
    conn = AsyncMock()
    conn.fetch = AsyncMock(return_value=[
        {'kind': 'photo', 'cost_credits': 3},
        {'kind': 'reel', 'cost_credits': 8},
    ])
    pricing = asyncio.run(credits_helper.pricing_map(conn))
    assert pricing == {'photo': 3, 'reel': 8}


# ─── personas_router ───────────────────────────────────────────────────────


def test_create_persona_happy_path():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    p_row = _persona_row(status='draft', handle='new_one')
    conn.fetchrow = AsyncMock(return_value=p_row)
    body = PersonaCreate(name='New', handle='new_one')
    result = asyncio.run(personas_mod.create_persona(request, body, conn))
    assert result.name == 'Sofia'  # row's name


def test_list_personas_with_filters():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[_persona_row()])
    result = asyncio.run(personas_mod.list_personas(
        request, status_filter='active', category='fashion', search='sof',
        include_archived=False, conn=conn,
    ))
    assert result.total == 1


def test_get_persona_404():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)
    import fastapi
    with pytest.raises(fastapi.HTTPException) as exc:
        asyncio.run(personas_mod.get_persona(uuid4(), request, conn))
    assert exc.value.status_code == 404


def test_patch_persona_disclose_ai_rejected_for_tenant():
    request = _req(is_platform_owner=False)
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    body = PersonaUpdate(disclose_ai=False)
    import fastapi
    with pytest.raises(fastapi.HTTPException) as exc:
        asyncio.run(personas_mod.patch_persona(uuid4(), request, body, conn))
    assert exc.value.status_code == 400
    assert 'AI disclosure' in exc.value.detail


def test_patch_persona_disclose_ai_allowed_for_platform_owner():
    request = _req(is_platform_owner=True)
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    p_row = _persona_row(disclose_ai=False)
    conn.fetchrow = AsyncMock(return_value=p_row)
    body = PersonaUpdate(disclose_ai=False)
    result = asyncio.run(personas_mod.patch_persona(uuid4(), request, body, conn))
    assert result.disclose_ai is False


def test_patch_persona_no_updates_returns_current():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=_persona_row())
    body = PersonaUpdate()
    result = asyncio.run(personas_mod.patch_persona(uuid4(), request, body, conn))
    assert result.name == 'Sofia'


def test_archive_persona_happy():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value='UPDATE 1')
    response = asyncio.run(personas_mod.archive_persona(uuid4(), request, conn))
    assert response.status_code == 204


def test_archive_persona_404_when_no_rows():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value='UPDATE 0')
    import fastapi
    with pytest.raises(fastapi.HTTPException) as exc:
        asyncio.run(personas_mod.archive_persona(uuid4(), request, conn))
    assert exc.value.status_code == 404


# ─── wizard_router ─────────────────────────────────────────────────────────


def test_put_face_happy():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=_persona_row())
    body = FaceStep(
        starting_point='upload', ethnicity='latin', eye_color='brown',
        hair_color='black', hair_style='long', skin_tone='medium',
        age_range='25-34',
    )
    result = asyncio.run(wizard_mod.put_face(uuid4(), request, body, conn))
    assert result.name == 'Sofia'


def test_put_body_happy():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=_persona_row())
    body = BodyStep(silhouette='athletic', height_cm=170, posture='confident')
    asyncio.run(wizard_mod.put_body(uuid4(), request, body, conn))


def test_put_identity_happy():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=_persona_row())
    body = IdentityStep(
        name='Sofia', handle='sofia2', age=25, city='Bogotá', country='CO',
    )
    result = asyncio.run(wizard_mod.put_identity(uuid4(), request, body, conn))
    assert result.handle == 'sofia'


def test_put_voice_happy():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=_persona_row())
    body = VoiceStep(tone='warm', energy_level=7)
    asyncio.run(wizard_mod.put_voice(uuid4(), request, body, conn))


def test_put_platforms_happy():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=_persona_row())
    body = PlatformsStep(disclose_ai=True)
    asyncio.run(wizard_mod.put_platforms(uuid4(), request, body, conn))


def test_activate_persona_happy():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    p_full = _persona_row(
        face={'a': 1}, body={'b': 1}, identity={'c': 1},
        voice={'d': 1}, platforms={'e': 1},
    )
    conn.fetchrow = AsyncMock(side_effect=[p_full, p_full])
    asyncio.run(wizard_mod.activate_persona(uuid4(), request, conn))


def test_activate_persona_missing_step():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    p_missing = _persona_row(face={'a': 1}, body={}, identity={}, voice={}, platforms={})
    conn.fetchrow = AsyncMock(return_value=p_missing)
    import fastapi
    with pytest.raises(fastapi.HTTPException) as exc:
        asyncio.run(wizard_mod.activate_persona(uuid4(), request, conn))
    assert exc.value.status_code == 422


# ─── credits_router ────────────────────────────────────────────────────────


def test_credits_balance_endpoint(monkeypatch):
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value={'balance_after': 100})
    conn.fetch = AsyncMock(return_value=[])
    result = asyncio.run(credits_router_mod.get_balance(request, conn))
    assert result.balance == 100


def test_topup_endpoint():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value={'balance_after': 50})
    from app.influencer.credits_router import TopUpRequest
    body = TopUpRequest(amount=20, payment_ref='pay_abc')
    result = asyncio.run(credits_router_mod.topup(request, body, conn))
    assert result.delta == 20
    assert result.payment_ref == 'pay_abc'


def test_pricing_endpoint():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[
        {'kind': 'photo', 'cost_credits': 3},
    ])
    result = asyncio.run(credits_router_mod.get_pricing(request, conn))
    assert result.pricing == {'photo': 3}


# ─── face_variations ───────────────────────────────────────────────────────


def test_create_face_variations_happy(monkeypatch):
    """UI-INFLU-014.3 — endpoint ahora SÍNCRONO: llama al provider, espera
    la imagen, persiste el asset, devuelve status='completed' con assets.
    Mockea provider builder + decrypt_secret + adapter.
    """
    from unittest.mock import MagicMock
    from app.ai.providers.base import ImageResult

    fake_adapter = MagicMock()
    fake_adapter._models = {}
    fake_adapter.generate_image = AsyncMock(return_value=[
        ImageResult(image_bytes=b'\x89PNG-x', mime='image/png',
                    width=512, height=512),
    ])
    monkeypatch.setattr(fv_mod, '_build_test_provider', lambda *a, **kw: fake_adapter)
    monkeypatch.setattr(fv_mod, '_decrypt_secret', lambda c: 'fake-key')

    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    persona = _persona_row()
    fvr_row = {
        'id': uuid4(),
        'persona_id': persona['id'],
        'requested_count': 1,
        'status': 'in_progress',
        'prompt_used': 'prompt',
        'error_message': None,
    }
    provider_row = {
        'provider': 'grok', 'model': 'grok-2-image',
        'hint': 'abcd', 'ciphertext': b'fake-cipher',
    }
    asset_row = {'id': uuid4(), 'marked_canonical': False}
    conn.fetchrow = AsyncMock(side_effect=[
        persona, fvr_row, provider_row, asset_row,
    ])
    result = asyncio.run(
        fv_mod.create_face_variations(uuid4(), request, conn=conn),
    )
    assert result.status == 'completed'
    assert len(result.assets) == 1
    assert result.assets[0].url.startswith('data:image/png;base64,')


def test_get_face_variation_status_happy():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    row = {
        'id': uuid4(),
        'persona_id': uuid4(),
        'requested_count': 4,
        'status': 'completed',
        'prompt_used': 'prompt',
        'error_message': None,
    }
    conn.fetchrow = AsyncMock(return_value=row)
    result = asyncio.run(
        fv_mod.get_face_variation_status(uuid4(), uuid4(), request, conn=conn),
    )
    assert result.status == 'completed'


def test_get_face_variation_status_404():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)
    import fastapi
    with pytest.raises(fastapi.HTTPException):
        asyncio.run(
            fv_mod.get_face_variation_status(uuid4(), uuid4(), request, conn=conn),
        )


# ─── generations ───────────────────────────────────────────────────────────


def _gen_row(**overrides):
    base = {
        'id': uuid4(),
        'tenant_id': uuid4(),
        'persona_id': uuid4(),
        'kind': 'photo',
        'prompt': 'a',
        'format': '1:1',
        'count_requested': 1,
        'status': 'queued',
        'provider_used': None,
        'cost_credits': 3,
        'params': {},
        'error_message': None,
        'created_at': datetime.now(timezone.utc),
        'started_at': None,
        'completed_at': None,
    }
    base.update(overrides)
    return base


def test_create_generation_happy():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(side_effect=[
        {'id': uuid4(), 'status': 'active'},
        _gen_row(),
    ])
    body = gen_mod.GenerateRequest(kind='photo', prompt='hola', format='1:1', count=1)
    result = asyncio.run(gen_mod.create_generation(uuid4(), request, body, conn))
    assert result.status == 'queued'


def test_create_generation_bad_format():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    body = gen_mod.GenerateRequest(kind='reel', prompt='x', format='1:1')
    import fastapi
    with pytest.raises(fastapi.HTTPException) as exc:
        asyncio.run(gen_mod.create_generation(uuid4(), request, body, conn))
    assert exc.value.status_code == 422


def test_create_generation_archived_persona():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value={'id': uuid4(), 'status': 'archived'})
    body = gen_mod.GenerateRequest(kind='photo')
    import fastapi
    with pytest.raises(fastapi.HTTPException) as exc:
        asyncio.run(gen_mod.create_generation(uuid4(), request, body, conn))
    assert exc.value.status_code == 409


def test_get_generation_404():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)
    import fastapi
    with pytest.raises(fastapi.HTTPException):
        asyncio.run(gen_mod.get_generation(uuid4(), request, conn))


# ─── posts_router ──────────────────────────────────────────────────────────


def _post_row(**overrides):
    base = {
        'id': uuid4(),
        'persona_id': uuid4(),
        'generation_id': None,
        'kind': 'photo',
        'caption': 'hola',
        'hashtags': [],
        'scheduled_at': datetime.now(timezone.utc) + timedelta(hours=1),
        'platforms': ['instagram'],
        'status': 'scheduled',
        'approved_at': None,
        'published_at': None,
        'external_post_ids': {},
        'error_message': None,
    }
    base.update(overrides)
    return base


def test_create_post_happy():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=_post_row())
    body = posts_mod.PostCreate(
        persona_id=uuid4(),
        kind='photo',
        caption='hola',
        scheduled_at=datetime.now(timezone.utc) + timedelta(hours=1),
        platforms=['instagram'],
    )
    result = asyncio.run(posts_mod.create_post(request, body, conn))
    assert result.kind == 'photo'


def test_create_post_with_approved_mode():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=_post_row(status='approved'))
    body = posts_mod.PostCreate(
        persona_id=uuid4(),
        kind='reel',
        scheduled_at=datetime.now(timezone.utc),
        platforms=['tiktok'],
        mode='approved',
    )
    asyncio.run(posts_mod.create_post(request, body, conn))


def test_update_post_happy():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=_post_row(caption='nuevo'))
    body = posts_mod.PostUpdate(caption='nuevo', status='approved')
    asyncio.run(posts_mod.update_post(uuid4(), request, body, conn))


def test_update_post_no_updates_returns_current():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=_post_row())
    body = posts_mod.PostUpdate()
    asyncio.run(posts_mod.update_post(uuid4(), request, body, conn))


def test_cancel_post_happy():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=_post_row(status='canceled'))
    asyncio.run(posts_mod.cancel_post(uuid4(), request, conn))


def test_cancel_post_404():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)
    import fastapi
    with pytest.raises(fastapi.HTTPException):
        asyncio.run(posts_mod.cancel_post(uuid4(), request, conn))


def test_get_calendar_happy():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    from_dt = datetime.now(timezone.utc)
    to_dt = from_dt + timedelta(days=7)
    result = asyncio.run(posts_mod.get_calendar(request, from_dt, to_dt, None, conn))
    assert result.items == []


def test_get_calendar_range_too_wide():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    from_dt = datetime.now(timezone.utc)
    to_dt = from_dt + timedelta(days=100)
    import fastapi
    with pytest.raises(fastapi.HTTPException) as exc:
        asyncio.run(posts_mod.get_calendar(request, from_dt, to_dt, None, conn))
    assert exc.value.status_code == 422


# ─── casting_router ────────────────────────────────────────────────────────


def test_get_casting_empty():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    # personas list (empty), posts_month_row.
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchrow = AsyncMock(return_value={'c': 0})
    result = asyncio.run(casting_mod.get_casting(request, None, conn))
    assert result.kpis.active_personas == 0
    assert result.personas == []


def test_get_studio_happy():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    persona = _persona_row()
    # 1st fetchrow: persona; 2nd: stats_cache miss (None) → recompute path;
    # 3rd: count_published/scheduled; 4th: next_post
    conn.fetchrow = AsyncMock(side_effect=[
        persona,  # persona
        None,  # stats_cache miss
        {'posts_total': 0, 'scheduled_count': 0},  # counts
        None,  # next_post
    ])
    conn.fetch = AsyncMock(return_value=[])
    result = asyncio.run(casting_mod.get_studio(persona['id'], request, conn))
    assert result.stats.posts_total == 0


def test_get_studio_persona_not_found():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=None)
    import fastapi
    with pytest.raises(fastapi.HTTPException):
        asyncio.run(casting_mod.get_studio(uuid4(), request, conn))


# ─── voice_router ──────────────────────────────────────────────────────────


def test_voice_sample_happy():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    persona = _persona_row(voice={'tone': 'warm'})
    conn.fetchrow = AsyncMock(side_effect=[
        persona,
        {'id': uuid4(), 'status': 'queued'},
    ])
    body = voice_mod.SampleRequest()
    result = asyncio.run(
        voice_mod.create_voice_sample(uuid4(), request, body, conn),
    )
    assert result.status == 'queued'


def test_captions_preview_happy():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value={'voice': {'tone': 'warm'}, 'identity': {}, 'status': 'active'})
    body = voice_mod.CaptionsPreviewRequest(platforms=['ig'])
    result = asyncio.run(
        voice_mod.captions_preview(uuid4(), request, body, conn),
    )
    assert 'ig' in result.captions


def test_voice_sample_archived_409():
    request = _req()
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=None)
    conn.fetchrow = AsyncMock(return_value=_persona_row(status='archived'))
    import fastapi
    with pytest.raises(fastapi.HTTPException) as exc:
        asyncio.run(
            voice_mod.create_voice_sample(uuid4(), request, voice_mod.SampleRequest(), conn),
        )
    assert exc.value.status_code == 409
