"""Static tests para casting + studio — TASK-INFLU-017."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from app.influencer.casting_router import STATS_CACHE_TTL, casting_router


SCHEMA = Path('infra/postgres/03-migrations.sql').read_text(encoding='utf-8')


def test_stats_cache_ttl_is_1h():
    """TTL 1h alineado con spec — cron horario refresh stats."""
    assert STATS_CACHE_TTL == timedelta(hours=1)


def test_persona_stats_cache_table():
    assert 'create table if not exists influencer.persona_stats_cache' in SCHEMA
    assert 'posts_total' in SCHEMA
    assert 'reach_30d' in SCHEMA
    assert 'engagement_rate' in SCHEMA
    assert 'scheduled_count' in SCHEMA


def test_stats_cache_rls():
    assert 'persona_stats_cache_tenant_isolation' in SCHEMA


def test_2_endpoints_registered():
    paths = {(r.path, tuple(sorted(r.methods))) for r in casting_router.routes}
    assert any(p[0] == '/v1/influencer/casting' and 'GET' in p[1] for p in paths)
    assert any(
        p[0] == '/v1/influencer/personas/{persona_id}/studio' and 'GET' in p[1]
        for p in paths
    )


def test_studio_includes_5_sections():
    """Studio response debe traer persona + stats + next_post +
    platforms_connected + recent_generations."""
    src = Path('app/influencer/casting_router.py').read_text(encoding='utf-8')
    for field in (
        'persona', 'stats', 'next_post',
        'platforms_connected', 'recent_generations',
    ):
        assert field in src


def test_casting_kpis_shape():
    """KPIs alineados con el HTML: active_personas, posts_this_month,
    total_reach, avg_engagement."""
    src = Path('app/influencer/casting_router.py').read_text(encoding='utf-8')
    for k in ('active_personas', 'posts_this_month', 'total_reach', 'avg_engagement'):
        assert k in src


def test_recent_generations_capped_at_12():
    src = Path('app/influencer/casting_router.py').read_text(encoding='utf-8')
    assert 'limit 12' in src


def test_archived_personas_excluded_from_casting():
    src = Path('app/influencer/casting_router.py').read_text(encoding='utf-8')
    assert "status <> 'archived'" in src


def test_disconnected_platforms_excluded_from_studio():
    src = Path('app/influencer/casting_router.py').read_text(encoding='utf-8')
    assert "status <> 'disconnected'" in src


def test_casting_router_mounted_in_main():
    main_src = Path('app/main.py').read_text(encoding='utf-8')
    assert 'influencer_casting_router' in main_src
