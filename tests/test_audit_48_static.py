"""AUDIT-48 — Static regression tests for the security batch (2026-05-18).

Covers:
  * BUG-42: tenant_settings.no_train gates the cloud LLM tier-3 in
    rag_orchestrator (security #1 from the audit).
  * Meta webhook freshness check via `is_meta_message_fresh` + audit drops
    in both WhatsApp and Messenger handlers (security #2).
  * Dual-secret service_token in `app/core/security.py` (security #3).
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


# ────────────── Security #1 / BUG-42 — Cloud LLM no_train gate ────────────


def test_orchestrator_loads_no_train_from_tenant_settings():
    src = (REPO_ROOT / 'app' / 'services' / 'rag_orchestrator.py').read_text()
    # The select column was added
    assert 'ts.no_train, ts.pii_policy' in src
    # The bool gets coerced (fail-closed if missing → True)
    assert 'tenant_no_train: bool | None' in src
    # Both call sites receive the param
    assert 'tenant_no_train=tenant_no_train' in src
    # And the helper exists
    assert 'def _tenant_allows_cloud_llm' in src


def test_resolve_answer_blocks_cloud_llm_when_no_train():
    """Both cloud-LLM call sites are wrapped by `_tenant_allows_cloud_llm`."""
    src = (REPO_ROOT / 'app' / 'services' / 'rag_orchestrator.py').read_text()
    # The 3 cloud LLM call sites should all be guarded.
    # We assert the guard appears at least 3 times (the explicit 3 cloud sites).
    assert src.count('_tenant_allows_cloud_llm(tenant_no_train)') >= 3
    # And the structured log event for the block
    assert 'cloud_llm.blocked_by_tenant_no_train' in src
    assert 'cascade.cloud_llm_blocked_by_tenant_no_train' in src
    assert 'cascade.cloud_llm_conv_blocked_by_tenant_no_train' in src


def test_tenant_allows_cloud_llm_fail_closed_on_none():
    """`None` (settings_row missing the column) → False (block cloud)."""
    from app.services.rag_orchestrator import _tenant_allows_cloud_llm
    assert _tenant_allows_cloud_llm(None) is False
    assert _tenant_allows_cloud_llm(True) is False
    assert _tenant_allows_cloud_llm(False) is True


# ──────────── Security #2 — Meta webhook freshness check ──────────────────


def test_is_meta_message_fresh_basic():
    from app.services.whatsapp import is_meta_message_fresh

    now_ts = 1_700_000_000
    # Disabled when max_age <= 0
    assert is_meta_message_fresh({'timestamp': '0'}, now_ts=now_ts, max_age_seconds=0) is True
    # Missing timestamp → fail-closed
    assert is_meta_message_fresh({}, now_ts=now_ts, max_age_seconds=60) is False
    assert is_meta_message_fresh({'timestamp': None}, now_ts=now_ts, max_age_seconds=60) is False
    # Garbage timestamp → fail-closed
    assert is_meta_message_fresh({'timestamp': 'not-a-number'}, now_ts=now_ts, max_age_seconds=60) is False
    # Zero / negative → fail-closed
    assert is_meta_message_fresh({'timestamp': '0'}, now_ts=now_ts, max_age_seconds=60) is False
    # Fresh: within window
    assert is_meta_message_fresh(
        {'timestamp': str(now_ts - 100)}, now_ts=now_ts, max_age_seconds=200
    ) is True
    # Stale: past window
    assert is_meta_message_fresh(
        {'timestamp': str(now_ts - 1000)}, now_ts=now_ts, max_age_seconds=200
    ) is False
    # Future >1h → reject (corrupt or huge clock skew)
    assert is_meta_message_fresh(
        {'timestamp': str(now_ts + 7200)}, now_ts=now_ts, max_age_seconds=999_999_999
    ) is False
    # Slightly future <1h → accept (small skew)
    assert is_meta_message_fresh(
        {'timestamp': str(now_ts + 300)}, now_ts=now_ts, max_age_seconds=60
    ) is True


def test_whatsapp_webhook_uses_freshness_check():
    # After the routes.py refactor (phase 3) the webhook handlers live in
    # app/api/v1/handlers/webhook_handlers.py — use the aggregated source so
    # the asserts keep matching regardless of file boundaries.
    from tests._routes_aggregator import routes_aggregated_source

    src = routes_aggregated_source()
    assert 'from app.services.whatsapp import (' in src
    assert 'is_meta_message_fresh,' in src
    # The handler invokes it with the configured max age
    assert 'is_meta_message_fresh(message, now_ts=' in src
    # And audit-drops the stale message
    assert "action='webhook.whatsapp_message_stale'" in src


def test_messenger_webhook_uses_freshness_check():
    from tests._routes_aggregator import routes_aggregated_source

    src = routes_aggregated_source()
    # The messenger loop guards on event.timestamp
    assert "action='webhook.messenger_event_stale'" in src
    assert "action='webhook.messenger_event_missing_timestamp'" in src
    # Reuses the new setting
    assert 'webhook_meta_max_message_age_seconds' in src


def test_config_exposes_freshness_setting():
    src = (REPO_ROOT / 'app' / 'core' / 'config.py').read_text()
    assert 'webhook_meta_max_message_age_seconds: int = Field(' in src
    # Default = 7 days (7 * 24 * 3600 = 604800)
    assert 'default=7 * 24 * 3600' in src


# ──────────── Security #3 — Dual-secret service_token ─────────────────────


def test_security_uses_dual_service_token_helper():
    src = (REPO_ROOT / 'app' / 'core' / 'security.py').read_text()
    assert 'def _service_token_match(' in src
    assert '_service_token_match(token, settings)' in src
    # And no longer does the plain `==` check
    assert 'token == settings.service_token' not in src
    # The helper is constant-time (hmac.compare_digest)
    assert 'hmac.compare_digest' in src


def test_service_token_match_accepts_both_secrets(monkeypatch):
    from app.core.security import _service_token_match

    class FakeSettings:
        service_token = 'current-secret-xxxxxxxxxxx'
        service_token_next = 'rotated-secret-yyyyyyyyyyy'

    settings = FakeSettings()
    assert _service_token_match('current-secret-xxxxxxxxxxx', settings) is True
    assert _service_token_match('rotated-secret-yyyyyyyyyyy', settings) is True
    assert _service_token_match('attacker-guess', settings) is False
    assert _service_token_match('', settings) is False


def test_service_token_match_falls_back_when_next_is_none():
    from app.core.security import _service_token_match

    class FakeSettings:
        service_token = 'current-secret-xxxxxxxxxxx'
        service_token_next = None

    settings = FakeSettings()
    assert _service_token_match('current-secret-xxxxxxxxxxx', settings) is True
    assert _service_token_match('any-other-value', settings) is False


def test_config_exposes_service_token_next():
    src = (REPO_ROOT / 'app' / 'core' / 'config.py').read_text()
    assert 'service_token_next: str | None = Field(default=None, min_length=16)' in src
