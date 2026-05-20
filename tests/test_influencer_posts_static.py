"""Static tests para posts + publish_worker — TASK-INFLU-015."""
from __future__ import annotations

from pathlib import Path

from app.influencer.posts_router import (
    AI_DISCLOSURE_SUFFIX,
    apply_ai_disclosure,
    posts_router,
)
from app.workers.influencer_publish_worker import apply_ai_disclosure as worker_disclose


SCHEMA = Path('infra/postgres/03-migrations.sql').read_text(encoding='utf-8')
WORKER_SRC = Path('app/workers/influencer_publish_worker.py').read_text(encoding='utf-8')


# ─── Migración ─────────────────────────────────────────────────────────────


def test_posts_table_with_check_constraints():
    assert 'create table if not exists influencer.posts' in SCHEMA
    assert "kind in ('photo', 'reel', 'carousel', 'story', 'ad')" in SCHEMA
    assert (
        "status in ('scheduled', 'approved', 'publishing',\n"
        "                                       'published', 'failed', 'canceled')"
    ) in SCHEMA
    assert 'cardinality(platforms) > 0' in SCHEMA


def test_indices_queue_and_calendar():
    assert 'ix_posts_publish_queue' in SCHEMA
    assert "where status = 'approved'" in SCHEMA
    assert 'ix_posts_persona_scheduled' in SCHEMA
    assert 'ix_posts_tenant_status_scheduled' in SCHEMA


def test_rls_enabled():
    fragment = SCHEMA[SCHEMA.find('influencer.posts'):]
    assert 'enable row level security' in fragment
    assert 'posts_tenant_isolation' in fragment


# ─── Router ────────────────────────────────────────────────────────────────


def test_4_endpoints_registered():
    paths = {(r.path, tuple(sorted(r.methods))) for r in posts_router.routes}
    assert any(p[0] == '/v1/influencer/posts' and 'POST' in p[1] for p in paths)
    assert any(p[0] == '/v1/influencer/posts/{post_id}' and 'PATCH' in p[1] for p in paths)
    assert any(p[0] == '/v1/influencer/posts/{post_id}/cancel' and 'POST' in p[1] for p in paths)
    assert any(p[0] == '/v1/influencer/calendar' and 'GET' in p[1] for p in paths)


def test_router_mounted_in_main():
    assert 'influencer_posts_router' in Path('app/main.py').read_text(encoding='utf-8')


# ─── AI disclosure ─────────────────────────────────────────────────────────


def test_disclose_ai_prepends_hashtags():
    out = apply_ai_disclosure('look del día', disclose_ai=True)
    assert '#AI' in out
    assert '#generadoConIA' in out
    assert out.startswith('look del día')


def test_disclose_ai_idempotent():
    """No agrega los hashtags 2 veces si ya están."""
    first = apply_ai_disclosure('hola #AI', disclose_ai=True)
    second = apply_ai_disclosure(first, disclose_ai=True)
    assert first == second


def test_disclose_ai_skipped_when_false():
    out = apply_ai_disclosure('look', disclose_ai=False)
    assert '#AI' not in out


def test_worker_imports_same_disclosure_fn():
    """El worker reusa exactamente la misma función → consistencia."""
    assert worker_disclose is apply_ai_disclosure


# ─── Worker ────────────────────────────────────────────────────────────────


def test_worker_uses_for_update_skip_locked():
    assert 'for update of p skip locked' in WORKER_SRC.lower() or \
           'for update skip locked' in WORKER_SRC.lower()


def test_worker_only_picks_approved_due():
    """Solo posts con status='approved' AND scheduled_at <= now()."""
    assert "status = 'approved'" in WORKER_SRC
    assert 'scheduled_at <= now()' in WORKER_SRC


def test_worker_writes_external_post_ids():
    assert 'external_post_ids' in WORKER_SRC
    # publish() devuelve external_post_id por platform.
    assert 'external_ids[platform]' in WORKER_SRC


def test_worker_resolves_token_from_platform_connections():
    """El token debe venir de platform_connections.oauth_token_ref →
    app.platform_secrets, no hardcoded."""
    assert 'platform_connections' in WORKER_SRC
    assert 'oauth_token_ref' in WORKER_SRC


def test_disclose_ai_suffix_constant():
    assert '#AI' in AI_DISCLOSURE_SUFFIX
    assert '#generadoConIA' in AI_DISCLOSURE_SUFFIX
