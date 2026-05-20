"""Static tests para observabilidad — TASK-INFLU-018."""
from __future__ import annotations

from pathlib import Path

from app.services.metrics import (
    influencer_credits_balance,
    influencer_generation_duration_seconds,
    influencer_generations_total,
    influencer_posts_published_total,
    influencer_provider_health,
)


ALERTS = Path('infra/observability/alerts/influencer.yml').read_text(encoding='utf-8')
RUNBOOK_STUCK = Path('docs/runbooks/influencer-generation-stuck.md').read_text(encoding='utf-8')
RUNBOOK_IG = Path('docs/runbooks/influencer-instagram-publish-failure.md').read_text(encoding='utf-8')
PERSONAS_ROUTER = Path('app/influencer/personas_router.py').read_text(encoding='utf-8')


# ─── Métricas registradas ──────────────────────────────────────────────────


def test_generations_total_has_kind_status_provider_labels():
    """Verifica label names esperados por las alertas."""
    labels = influencer_generations_total._labelnames
    assert tuple(labels) == ('kind', 'status', 'provider')


def test_duration_histogram_has_kind_provider_labels():
    labels = influencer_generation_duration_seconds._labelnames
    assert 'kind' in labels and 'provider' in labels


def test_credits_balance_gauge_by_tenant():
    assert 'tenant_id' in influencer_credits_balance._labelnames


def test_posts_published_counter_by_platform_status():
    labels = influencer_posts_published_total._labelnames
    assert 'platform' in labels and 'status' in labels


def test_provider_health_gauge_by_provider_modality():
    labels = influencer_provider_health._labelnames
    assert 'provider' in labels and 'modality' in labels


# ─── Alertas Prometheus ────────────────────────────────────────────────────


def test_alert_influencer_provider_down():
    assert 'InfluencerProviderDown' in ALERTS
    assert 'influencer_provider_health == 0' in ALERTS


def test_alert_generation_p95():
    assert 'InfluencerGenerationP95High' in ALERTS
    assert 'influencer_generation_duration_seconds_bucket' in ALERTS


def test_alert_publish_failures():
    assert 'InfluencerPublishFailures' in ALERTS
    assert 'influencer_posts_published_total{status="failed"}' in ALERTS


def test_alerts_reference_runbook_urls():
    """Cada alerta debe llevar al runbook correspondiente."""
    assert 'docs/runbooks/influencer-generation-stuck.md' in ALERTS
    assert 'docs/runbooks/influencer-instagram-publish-failure.md' in ALERTS


# ─── Runbooks ──────────────────────────────────────────────────────────────


def test_runbook_stuck_covers_circuit_breaker_and_content_rejection():
    assert 'circuit breaker' in RUNBOOK_STUCK.lower()
    assert 'content_rejected' in RUNBOOK_STUCK
    assert 'refund' in RUNBOOK_STUCK.lower()


def test_runbook_ig_covers_expired_tokens_and_rate_limits():
    assert 'expir' in RUNBOOK_IG.lower()
    assert 'rate' in RUNBOOK_IG.lower()
    assert 'community guidelines' in RUNBOOK_IG.lower() or 'content' in RUNBOOK_IG.lower()


# ─── Disclose AI enforcer ──────────────────────────────────────────────────


def test_disclose_ai_enforcer_in_patch_persona():
    """Patch persona debe rechazar disclose_ai=False salvo platform_owner."""
    assert 'disclose_ai' in PERSONAS_ROUTER
    # Debe verificar is_platform_owner antes de permitir disable.
    assert 'is_platform_owner' in PERSONAS_ROUTER
    assert 'AI disclosure is required' in PERSONAS_ROUTER
