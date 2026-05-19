"""AUDIT-51 — Regression tests for the 5 quick wins identified by the
round-3 audit on 2026-05-18 (chapter "Re-audit round 3 (post AUDIT-49)").

QW#1 — Propagate `tenant_no_train` en `/intents/evaluate` (MEDIUM §1.1).
QW#2 — Audit metadata with diff (changed_keys + previous/new) en
        `patch_settings` (MEDIUM §1.2). Includes input validation for
        `no_train` payload field (LOW §1.3).
QW#3 — Refactor gate cloud-provider a `CLOUD_PROVIDERS` constante
        (LOW §1.4).
QW#4 — Prometheus gauges + counters para ws_fanout + rate_limit
        (round-2 §1.3 + §1.10 MEDIUM).
QW#5 — Reorder WhatsApp handler: freshness pre-scan ANTES del INSERT
        a `webhook_events_raw` (round-2 §1.8 MEDIUM).
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


# ──────────────── QW#1 — /intents/evaluate propaga no_train ──────────────


def test_evaluate_intent_loads_no_train_and_propagates_to_classify():
    src = (REPO_ROOT / 'app' / 'api' / 'v1' / 'routes.py').read_text()
    ep_idx = src.find('async def evaluate_intent_retrieval(')
    assert ep_idx > 0
    ep_window = src[ep_idx:ep_idx + 3500]
    # Loads `no_train` from tenant_settings
    assert 'select no_train from app.tenant_settings where tenant_id=$1' in ep_window
    # Fail-closed: missing row → True (blocks cloud)
    assert "tenant_no_train: bool | None" in ep_window
    # Passes it to classify_intent
    assert 'tenant_no_train=tenant_no_train' in ep_window


# ────────────── QW#2 — patch_settings audit metadata diff ─────────────────


def test_patch_settings_validates_no_train_is_bool():
    src = (REPO_ROOT / 'app' / 'api' / 'v1' / 'routes.py').read_text()
    ep_idx = src.find('async def patch_settings(')
    assert ep_idx > 0
    ep_window = src[ep_idx:ep_idx + 6000]
    # Strict type check on no_train
    assert "isinstance(allowed['no_train'], bool)" in ep_window
    assert 'no_train must be a boolean' in ep_window


def test_patch_settings_audit_includes_changed_keys_diff():
    src = (REPO_ROOT / 'app' / 'api' / 'v1' / 'routes.py').read_text()
    ep_idx = src.find('async def patch_settings(')
    assert ep_idx > 0
    # AUDIT-51 / HTTP-E2E follow-up: the function grew when jsonb hashing
    # was reworked (asyncpg returns jsonb as str, so the `isinstance(str)`
    # branch was inlining raw JSON values — now we whitelist jsonb-known keys
    # to always hash). Bumped window from 8000 to 12000 chars.
    ep_window = src[ep_idx:ep_idx + 12000]
    # The audit call passes metadata with diff
    assert 'audit_meta' in ep_window
    assert "audit_meta['changed_keys'] = changed_keys" in ep_window
    assert "metadata=audit_meta" in ep_window
    # Privacy-sensitive keys are captured with previous/new (or hash for jsonb)
    assert "privacy_sensitive_keys = ('no_train', 'pii_policy', 'escalation_policy', 'locale')" in ep_window
    # Hash truncation for jsonb diffs (no raw value leak)
    assert "_previous_hash" in ep_window
    assert "_new_hash" in ep_window


# ───────────── QW#3 — CLOUD_PROVIDERS constant + gate refactor ────────────


def test_rag_indexing_exposes_cloud_providers_constant():
    src = (REPO_ROOT / 'app' / 'services' / 'rag_indexing.py').read_text()
    assert 'LOCAL_REAL_PROVIDERS = frozenset({\'ollama\'})' in src
    assert "CLOUD_PROVIDERS: frozenset[str] = frozenset(SUPPORTED_REAL_PROVIDERS) - LOCAL_REAL_PROVIDERS" in src


def test_rag_indexing_gate_uses_cloud_providers_constant():
    src = (REPO_ROOT / 'app' / 'services' / 'rag_indexing.py').read_text()
    # Old hardcoded set is gone from the gate condition
    assert "embedding_provider in {'openai', 'anthropic'} and tenant_no_train is not False" not in src
    # New gate uses the constant
    assert 'embedding_provider in CLOUD_PROVIDERS and tenant_no_train is not False' in src


def test_cloud_providers_set_excludes_ollama():
    """Functional check: ollama is the on-prem provider and must NOT be in
    the cloud set. Any future cloud provider added to SUPPORTED_REAL_PROVIDERS
    is automatically gated by `no_train`."""
    from app.services.rag_indexing import CLOUD_PROVIDERS, SUPPORTED_REAL_PROVIDERS

    assert 'ollama' not in CLOUD_PROVIDERS
    assert 'openai' in CLOUD_PROVIDERS
    assert 'anthropic' in CLOUD_PROVIDERS
    # Anything in SUPPORTED_REAL_PROVIDERS that isn't ollama is in CLOUD_PROVIDERS
    expected = set(SUPPORTED_REAL_PROVIDERS) - {'ollama'}
    assert CLOUD_PROVIDERS == expected


# ──────────── QW#4 — Prometheus gauges/counters expuestos ────────────────


def test_metrics_exports_ws_fanout_gauges_and_counters():
    src = (REPO_ROOT / 'app' / 'services' / 'metrics.py').read_text()
    assert 'cpi_ws_fanout_subscriber_count' in src
    assert 'cpi_ws_fanout_tenant_count' in src
    assert 'cpi_ws_fanout_dropped_total' in src
    assert 'cpi_ws_fanout_supervisor_crashes_total' in src


def test_metrics_exports_rate_limit_gauges_and_counters():
    src = (REPO_ROOT / 'app' / 'services' / 'metrics.py').read_text()
    assert 'cpi_rate_limit_buckets_current' in src
    assert 'cpi_rate_limit_buckets_evicted_total' in src
    # Eviction reason label distinguishes ttl vs cap
    assert "labelnames=('reason',)" in src


def test_metrics_module_exposes_refresh_runtime_metrics():
    src = (REPO_ROOT / 'app' / 'services' / 'metrics.py').read_text()
    assert 'def refresh_runtime_metrics()' in src
    # Wired into the /metrics endpoint
    main = (REPO_ROOT / 'app' / 'main.py').read_text()
    assert 'refresh_runtime_metrics()' in main
    assert '_set_active_rate_limiter(limiter)' in main


def test_rate_limit_increments_eviction_counters():
    src = (REPO_ROOT / 'app' / 'services' / 'rate_limit.py').read_text()
    # Both eviction paths (TTL + cap) increment with the proper reason label
    assert "rate_limit_buckets_evicted_total.labels(reason='ttl').inc()" in src
    assert "rate_limit_buckets_evicted_total.labels(reason='cap').inc()" in src


def test_ws_fanout_increments_drop_and_crash_counters():
    src = (REPO_ROOT / 'app' / 'admin' / 'ws_fanout.py').read_text()
    assert "ws_fanout_dropped_total.labels(reason='invalid_json').inc()" in src
    assert "ws_fanout_dropped_total.labels(reason='queue_full').inc()" in src
    assert 'ws_fanout_supervisor_crashes_total.inc()' in src


# ────────── QW#5 — WhatsApp pre-scan freshness before raw INSERT ─────────


def test_whatsapp_handler_freshness_prescan_before_raw_insert():
    src = (REPO_ROOT / 'app' / 'api' / 'v1' / 'routes.py').read_text()
    ep_idx = src.find('async def receive_whatsapp_webhook(')
    assert ep_idx > 0
    ep_window = src[ep_idx:ep_idx + 8000]
    # Pre-scan loop variables present
    assert '_has_fresh_message' in ep_window
    assert '_total_messages' in ep_window
    # The pre-scan happens BEFORE the INSERT
    prescan_idx = ep_window.find('_has_fresh_message = False')
    insert_idx = ep_window.find('insert into app.webhook_events_raw')
    assert prescan_idx > 0 and insert_idx > 0
    assert prescan_idx < insert_idx, (
        'Freshness pre-scan must run BEFORE the webhook_events_raw INSERT '
        '(AUDIT-51 / round-3 §1.8): stale replays should not pollute the '
        'raw table.'
    )


def test_whatsapp_handler_skips_when_all_messages_stale():
    src = (REPO_ROOT / 'app' / 'api' / 'v1' / 'routes.py').read_text()
    ep_idx = src.find('async def receive_whatsapp_webhook(')
    assert ep_idx > 0
    ep_window = src[ep_idx:ep_idx + 8000]
    # Audit event + early return
    assert "action='webhook.whatsapp_payload_all_messages_stale'" in ep_window
    assert "return {'status': 'rejected', 'reason': 'all_messages_stale'}" in ep_window


def test_whatsapp_handler_does_not_skip_status_update_payloads():
    """Status updates (no `messages[]`) MUST NOT be filtered by the freshness
    pre-scan — they don't carry per-message timestamps and Meta handles dedup."""
    src = (REPO_ROOT / 'app' / 'api' / 'v1' / 'routes.py').read_text()
    ep_idx = src.find('async def receive_whatsapp_webhook(')
    assert ep_idx > 0
    ep_window = src[ep_idx:ep_idx + 8000]
    # The gate condition is `if _total_messages > 0 and not _has_fresh_message`
    # — status-only payloads have `_total_messages == 0` and slip through.
    assert 'if _total_messages > 0 and not _has_fresh_message' in ep_window
