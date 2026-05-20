"""Static checks para el wizard (TASK-INFLU-009).

- 6 endpoints registrados (5 PUT + 1 POST activate).
- Cada paso tiene su Pydantic model con Literal types correctos.
- Activate verifica los 5 sub-jsonb antes de cambiar status.
- Audit tables `persona_step_updated` y `persona_activated` declaradas.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.influencer.wizard_models import (
    BodyStep,
    FaceStep,
    IdentityStep,
    PlatformAccount,
    PlatformsStep,
    VoiceStep,
)
from app.influencer.wizard_router import wizard_router

ROUTER_SRC = Path('app/influencer/wizard_router.py').read_text(encoding='utf-8')
SCHEMA_SRC = Path('infra/postgres/03-migrations.sql').read_text(encoding='utf-8')


# ─── Router ────────────────────────────────────────────────────────────────


def test_wizard_router_has_6_endpoints():
    paths = {(r.path, tuple(sorted(r.methods))) for r in wizard_router.routes}
    base = '/v1/influencer/personas/{persona_id}'
    expected = {
        (f'{base}/face', 'PUT'),
        (f'{base}/body', 'PUT'),
        (f'{base}/identity', 'PUT'),
        (f'{base}/voice', 'PUT'),
        (f'{base}/platforms', 'PUT'),
        (f'{base}/activate', 'POST'),
    }
    for endpoint, method in expected:
        assert any(p[0] == endpoint and method in p[1] for p in paths), (
            f'falta endpoint {method} {endpoint}'
        )


def test_router_uses_personas_helpers():
    """Reusa `_set_tenant_scope` y `_row_to_response` de personas_router."""
    assert '_set_tenant_scope' in ROUTER_SRC
    assert '_row_to_response' in ROUTER_SRC


def test_activate_requires_all_5_steps():
    """`_missing_steps` revisa los 5 jsonb antes de activar."""
    assert '_missing_steps' in ROUTER_SRC
    for step in ('face', 'body', 'identity', 'voice', 'platforms'):
        assert f"'{step}'" in ROUTER_SRC or f'"{step}"' in ROUTER_SRC


def test_activate_emits_audit():
    assert 'persona_activated' in ROUTER_SRC


def test_step_updates_emit_audit():
    assert 'persona_step_updated' in ROUTER_SRC


def test_identity_handles_unique_violation():
    """Cuando identity cambia el handle, debe convertir UniqueViolation en 409."""
    assert 'UniqueViolationError' in ROUTER_SRC
    assert '409' in ROUTER_SRC or 'HTTP_409_CONFLICT' in ROUTER_SRC


# ─── Pydantic models ───────────────────────────────────────────────────────


def test_face_step_rejects_invalid_eye_color():
    with pytest.raises(ValueError):
        FaceStep(
            starting_point='upload',
            ethnicity='latin',
            eye_color='purple',  # not in Literal
            hair_color='black',
            hair_style='long',
            skin_tone='medium',
            age_range='25-34',
        )


def test_face_step_variations_range():
    with pytest.raises(ValueError):
        FaceStep(
            starting_point='upload',
            ethnicity='x',
            eye_color='brown',
            hair_color='black',
            hair_style='long',
            skin_tone='medium',
            age_range='25-34',
            variations=11,  # > 10
        )


def test_body_step_height_range():
    with pytest.raises(ValueError):
        BodyStep(silhouette='athletic', height_cm=120, posture='confident')
    BodyStep(silhouette='athletic', height_cm=170, posture='confident')


def test_identity_step_normalizes_handle():
    p = IdentityStep(
        name='Sofia', handle='MY_HANDLE', age=25, city='Bogotá', country='CO',
    )
    assert p.handle == 'my_handle'


def test_identity_step_rejects_bad_handle():
    with pytest.raises(ValueError):
        IdentityStep(
            name='X', handle='ab', age=25, city='X', country='CO',
        )


def test_identity_step_age_range():
    with pytest.raises(ValueError):
        IdentityStep(
            name='X', handle='abc12', age=17, city='X', country='CO',
        )


def test_voice_step_energy_range():
    with pytest.raises(ValueError):
        VoiceStep(tone='warm', energy_level=11)
    VoiceStep(tone='warm', energy_level=8)


def test_platforms_step_limits_accounts():
    accounts = [
        PlatformAccount(platform='instagram', handle=f'user{i}')
        for i in range(11)
    ]
    with pytest.raises(ValueError):
        PlatformsStep(accounts=accounts)


def test_platforms_step_disclose_ai_defaults_true():
    p = PlatformsStep()
    assert p.disclose_ai is True


# ─── Migración SQL ─────────────────────────────────────────────────────────


def test_migration_creates_step_updated_table():
    assert 'create table if not exists influencer.persona_step_updated' in SCHEMA_SRC
    assert "step in ('face', 'body', 'identity', 'voice', 'platforms')" in SCHEMA_SRC


def test_migration_creates_activated_table():
    assert 'create table if not exists influencer.persona_activated' in SCHEMA_SRC


def test_migration_indices_for_audit_lookup():
    assert 'ix_persona_step_updated_persona_occurred' in SCHEMA_SRC
    assert 'ix_persona_activated_tenant_occurred' in SCHEMA_SRC


# ─── App mount ─────────────────────────────────────────────────────────────


def test_wizard_router_mounted_in_main():
    main_src = Path('app/main.py').read_text(encoding='utf-8')
    assert 'wizard_router' in main_src
    assert 'include_router(influencer_wizard_router)' in main_src
