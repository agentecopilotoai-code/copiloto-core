"""Static checks para TASK-INFLU-011 — generations + assets."""
from __future__ import annotations

from pathlib import Path

import pytest

from app.influencer.generations_router import (
    _KIND_FORMAT_RULES,
    _estimate_cost,
    generate_router,
    generations_router,
)


SCHEMA = Path('infra/postgres/03-migrations.sql').read_text(encoding='utf-8')


def test_generations_table_with_check_constraints():
    assert 'create table if not exists influencer.generations' in SCHEMA
    assert (
        "kind in ('photo', 'reel', 'carousel', 'story', 'ad',\n"
        "                                     'face_variation', 'voice_sample')"
    ) in SCHEMA
    assert "status in ('queued', 'running', 'succeeded', 'failed', 'canceled')" in SCHEMA
    assert 'count_requested between 1 and 10' in SCHEMA


def test_assets_table_with_storage_key():
    assert 'create table if not exists influencer.assets' in SCHEMA
    assert 'storage_key' in SCHEMA
    assert 'marked_canonical' in SCHEMA


def test_indices_for_worker_queue_and_listing():
    assert 'ix_generations_persona_status_created' in SCHEMA
    assert 'ix_generations_queue' in SCHEMA
    assert "status in ('queued', 'running')" in SCHEMA
    assert 'ix_assets_persona_kind_created' in SCHEMA
    assert 'ix_assets_generation' in SCHEMA


def test_rls_on_both_tables():
    assert 'enable row level security' in SCHEMA
    assert 'generations_tenant_isolation' in SCHEMA
    assert 'assets_tenant_isolation' in SCHEMA


def test_post_generate_returns_202():
    for route in generate_router.routes:
        if route.path.endswith('/generate') and 'POST' in route.methods:
            assert route.status_code == 202
            return
    raise AssertionError('POST /generate no encontrado')


def test_get_generation_detail_route():
    paths = {r.path for r in generations_router.routes}
    assert '/v1/influencer/generations/{generation_id}' in paths


def test_list_generations_route_under_persona():
    paths = {r.path for r in generate_router.routes}
    assert '/v1/influencer/personas/{persona_id}/generations' in paths


def test_kind_format_rules_reel_only_vertical():
    assert _KIND_FORMAT_RULES['reel'] == {'9:16'}
    assert _KIND_FORMAT_RULES['story'] == {'9:16'}


def test_kind_format_rules_carousel_square_or_4x5():
    assert _KIND_FORMAT_RULES['carousel'] == {'1:1', '4:5'}


def test_kind_format_rules_photo_any_aspect():
    assert _KIND_FORMAT_RULES['photo'] == {'1:1', '4:5', '9:16', '16:9'}


def test_estimate_cost_reel_more_expensive_than_photo():
    assert _estimate_cost('reel', 1) > _estimate_cost('photo', 1)


def test_estimate_cost_scales_with_count():
    assert _estimate_cost('photo', 4) == 4 * _estimate_cost('photo', 1)


def test_routers_mounted_in_main():
    main_src = Path('app/main.py').read_text(encoding='utf-8')
    assert 'influencer_generate_router' in main_src
    assert 'influencer_generations_router' in main_src


def test_validate_format_for_kind_raises_on_mismatch():
    from app.influencer.generations_router import _validate_format_for_kind
    with pytest.raises(Exception):
        _validate_format_for_kind('reel', '1:1')  # reel solo 9:16
    # OK case: reel + 9:16 no debe lanzar
    _validate_format_for_kind('reel', '9:16')
