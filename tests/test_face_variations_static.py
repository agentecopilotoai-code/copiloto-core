"""Static checks para TASK-INFLU-010 — face variations async."""
from __future__ import annotations

from pathlib import Path

from app.influencer.face_variations_router import (
    _build_prompt,
    face_variations_router,
)


ROUTER_SRC = Path('app/influencer/face_variations_router.py').read_text(encoding='utf-8')
SCHEMA_SRC = Path('infra/postgres/03-migrations.sql').read_text(encoding='utf-8')


def test_post_returns_202():
    """El endpoint POST declara status_code=202 (async accept)."""
    for route in face_variations_router.routes:
        if route.path.endswith('/variations') and 'POST' in route.methods:
            assert route.status_code == 202
            return
    raise AssertionError('POST /variations no encontrado')


def test_get_status_endpoint_registered():
    paths = {r.path for r in face_variations_router.routes}
    assert '/v1/influencer/personas/{persona_id}/face/variations/{variation_request_id}' in paths


def test_prompt_includes_face_traits():
    face = {
        'ethnicity': 'latin', 'eye_color': 'brown', 'hair_color': 'black',
        'hair_style': 'long', 'skin_tone': 'medium', 'age_range': '25-34',
    }
    prompt = _build_prompt(face)
    assert 'latin' in prompt
    assert 'brown' in prompt and 'eyes' in prompt
    assert 'black' in prompt and 'long' in prompt
    assert 'medium' in prompt
    assert '25-34' in prompt
    assert 'consistent identity' in prompt


def test_prompt_handles_empty_face():
    """Si face={} (paso 1 sin completar), devolver prompt genérico."""
    prompt = _build_prompt({})
    assert prompt
    assert 'portrait headshot' in prompt


def test_migration_creates_face_variation_requests():
    assert 'create table if not exists influencer.face_variation_requests' in SCHEMA_SRC
    assert "status in ('queued', 'in_progress', 'completed', 'failed')" in SCHEMA_SRC


def test_migration_count_range_check():
    assert 'requested_count between 1 and 10' in SCHEMA_SRC


def test_migration_index_for_worker_queue():
    """Index sobre status='queued' o 'in_progress' para que el worker
    picke jobs rápido."""
    assert 'ix_face_variation_requests_queued' in SCHEMA_SRC
    assert "status in ('queued', 'in_progress')" in SCHEMA_SRC


def test_migration_rls_enabled():
    # Buscar la sección específica de face_variation_requests
    fvr_idx = SCHEMA_SRC.find('influencer.face_variation_requests')
    assert fvr_idx > 0
    section = SCHEMA_SRC[fvr_idx:fvr_idx + 2000]
    assert 'enable row level security' in section
    assert 'fvr_tenant_isolation' in section


def test_router_mounted_in_main():
    main_src = Path('app/main.py').read_text(encoding='utf-8')
    assert 'face_variations_router' in main_src
    assert 'include_router(influencer_face_variations_router)' in main_src
