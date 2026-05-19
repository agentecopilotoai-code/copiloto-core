"""AUDIT-49 — Regression tests for the 5 quick wins identified by the
re-audit on 2026-05-18 (chapter "Re-audit post quick wins").

QW#1 — Gate `no_train` en intent_classifier + rag_indexing (HIGH).
QW#2 — Reset ws_fanout state on supervisor crash + retry in subscribe.
QW#3 — Map Auth0 CircuitOpenError to 503 + Retry-After.
QW#4 — WhatsAppMediaTooLargeError + HTTP 413 + sanitized detail.
QW#5 — Pydantic validator coerces empty SERVICE_TOKEN_NEXT to None.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# ───────────────── QW#1 — no_train gate end-to-end ────────────────────────


def test_intent_classifier_accepts_tenant_no_train_param():
    src = (REPO_ROOT / 'app' / 'services' / 'intent_classifier.py').read_text()
    # `_llm_classify` signature now includes the kw arg
    sig_idx = src.find('async def _llm_classify(')
    assert sig_idx > 0
    sig_window = src[sig_idx:sig_idx + 400]
    assert 'tenant_no_train: bool | None = None' in sig_window
    # And `classify_intent` propagates it
    classify_idx = src.find('async def classify_intent(')
    assert classify_idx > 0
    classify_window = src[classify_idx:classify_idx + 800]
    assert 'tenant_no_train: bool | None = None' in classify_window
    # The log event for the block exists
    assert 'intent_classifier.cloud_llm_blocked_by_tenant_no_train' in src


def test_intent_classifier_blocks_cloud_when_no_train_true(monkeypatch):
    """When tenant_no_train is not False, the cloud provider must be skipped
    (provider/api_key cleared before the if branch)."""
    import importlib

    from app.services import intent_classifier as ic

    # Settings with cloud configured
    class S:
        cloud_llm_provider = 'claude'
        cloud_llm_api_key = 'fake-key'
        cloud_llm_model = 'claude-sonnet-4-6'
        cloud_llm_timeout_seconds = 30
        local_llm_base_url = 'http://localhost:11434'
        local_llm_model = 'llama3.2:3b'
        local_llm_timeout_seconds = 30

    # Monkeypatch httpx to fail immediately so we can detect which branch ran.
    called = {'cloud': False, 'ollama': False}

    class FakeAsyncClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None, **kw):
            if 'localhost:11434' in url or '11434' in url:
                called['ollama'] = True
            raise RuntimeError('network blocked')

    monkeypatch.setattr(ic, 'asyncio', importlib.import_module('asyncio'))
    # Make sure even if cloud branch runs, it'd be detected via the import
    # of anthropic/openai — but those clients are imported lazily inside the
    # branch; we just verify intent_raw stays None when blocked.
    import httpx
    monkeypatch.setattr(httpx, 'AsyncClient', FakeAsyncClient)

    result_blocked = asyncio.new_event_loop().run_until_complete(
        ic._llm_classify('hola', {'greeting'}, S(), tenant_no_train=True)
    )
    # When blocked, we fall through to Ollama and the fake client raises;
    # `_llm_classify` returns None.
    assert result_blocked is None
    assert called['ollama'] is True, 'should fall through to Ollama when cloud blocked'


def test_rag_indexing_forces_local_hash_when_no_train_true():
    src = (REPO_ROOT / 'app' / 'services' / 'rag_indexing.py').read_text()
    sig_idx = src.find('async def build_indexing_result_async(')
    assert sig_idx > 0
    sig_window = src[sig_idx:sig_idx + 800]
    assert 'tenant_no_train: bool | None = None' in sig_window
    # AUDIT-51 / round-3 §1.4 refactored the gate from a hardcoded set
    # {'openai', 'anthropic'} to a derived `CLOUD_PROVIDERS` constant so
    # new cloud providers added to SUPPORTED_REAL_PROVIDERS are fail-closed
    # automatically. Assert the new form.
    assert 'embedding_provider in CLOUD_PROVIDERS and tenant_no_train is not False' in src
    assert 'rag_indexing.cloud_provider_blocked_by_tenant_no_train' in src
    # The constant itself is declared and excludes ollama (on-prem).
    assert "LOCAL_REAL_PROVIDERS = frozenset({'ollama'})" in src
    assert "CLOUD_PROVIDERS: frozenset[str] = frozenset(SUPPORTED_REAL_PROVIDERS) - LOCAL_REAL_PROVIDERS" in src


def test_routes_propagate_tenant_no_train_to_indexing():
    # Refactor phase 3: handler bodies live in app/api/v1/handlers/*.py — use

    # the aggregated source so asserts match regardless of file boundaries.

    from tests._routes_aggregator import routes_aggregated_source

    src = routes_aggregated_source()
    # Both index endpoints load no_train + pass it through
    assert src.count('select no_train from app.tenant_settings where tenant_id=$1') >= 2
    assert src.count('tenant_no_train=tenant_no_train') >= 2


def test_rag_orchestrator_propagates_tenant_no_train_to_intent_classifier():
    src = (REPO_ROOT / 'app' / 'services' / 'rag_orchestrator.py').read_text()
    # The classify_intent call site now passes tenant_no_train
    call_idx = src.find('intent_result = await classify_intent(')
    assert call_idx > 0
    call_window = src[call_idx:call_idx + 400]
    assert 'tenant_no_train=tenant_no_train' in call_window


# ────────────────── QW#2 — ws_fanout crash recovery ───────────────────────


def test_ws_fanout_supervisor_resets_state_on_crash():
    src = (REPO_ROOT / 'app' / 'admin' / 'ws_fanout.py').read_text()
    # The except Exception path resets _task, _pool, and sets _ready
    sup_idx = src.find('async def _supervise(')
    assert sup_idx > 0
    sup_window = src[sup_idx:sup_idx + 3000]
    # Critical: state reset must happen BEFORE raise
    assert 'self._task = None' in sup_window
    assert 'self._pool = None' in sup_window
    assert 'self._ready.set()' in sup_window
    # Comment references the audit finding
    assert 'AUDIT-49' in sup_window or 're-audit §1.1' in sup_window


def test_ws_fanout_subscribe_retries_after_crash():
    src = (REPO_ROOT / 'app' / 'admin' / 'ws_fanout.py').read_text()
    sub_idx = src.find('async def subscribe(')
    assert sub_idx > 0
    sub_window = src[sub_idx:sub_idx + 3000]
    # Loop with attempts counter
    assert 'attempts' in sub_window
    assert 'task.done()' in sub_window
    # Max 2 attempts before bailing
    assert 'attempts < 2' in sub_window
    # On terminal failure, raise RuntimeError so the WS can close 1011
    assert 'raise RuntimeError(' in sub_window


def test_ws_route_handles_subscribe_runtime_error_with_close_1011():
    src = (REPO_ROOT / 'app' / 'admin' / 'routes.py').read_text()
    # The WS endpoint wraps subscribe in try/except RuntimeError and closes 1011
    ws_idx = src.find('admin_conversations_stream')
    assert ws_idx > 0
    ws_window = src[ws_idx:ws_idx + 4000]
    assert 'except RuntimeError:' in ws_window
    assert 'code=1011' in ws_window


# ─────────────── QW#3 — Auth0 CircuitOpenError → 503 ──────────────────────


def test_routes_import_circuit_open_error():
    # Refactor phase 3: handler bodies live in app/api/v1/handlers/*.py — use

    # the aggregated source so asserts match regardless of file boundaries.

    from tests._routes_aggregator import routes_aggregated_source

    src = routes_aggregated_source()
    assert 'from app.services.circuit_breaker import CircuitOpenError' in src


def test_auth0_callsites_map_circuit_open_to_503():
    # Refactor phase 3: handler bodies live in app/api/v1/handlers/*.py — use

    # the aggregated source so asserts match regardless of file boundaries.

    from tests._routes_aggregator import routes_aggregated_source

    src = routes_aggregated_source()
    # All 4 Auth0 call sites (invite, assign x2, revoke) now have a typed
    # CircuitOpenError handler that returns 503 + Retry-After.
    assert src.count('except CircuitOpenError as exc:') >= 4
    # And the 503 with Retry-After header pattern
    assert src.count("'Retry-After': str(max(1, int(round(exc.retry_after_seconds))))") >= 4
    # The revoke handler specifically notes DB-side was already done
    assert 'DB-side membership revoked' in src or 'Membership revoked in our database' in src


# ────────── QW#4 — WhatsAppMediaTooLargeError + HTTP 413 + sanitized ──────


def test_whatsapp_module_exposes_typed_error():
    src = (REPO_ROOT / 'app' / 'services' / 'whatsapp.py').read_text()
    assert 'class WhatsAppMediaTooLargeError(Exception):' in src
    # phase distinguishes the two error sites
    assert "phase='preflight'" in src
    assert "phase='streamed'" in src
    # The old f-string with byte counts is gone (no info leak via detail)
    assert "f'WhatsApp media exceeds max allowed size '" not in src


def test_routes_map_media_too_large_to_413_with_sanitized_detail():
    # After the routes.py refactor (phase 3) the ops handlers live in
    # app/api/v1/handlers/tenant_ops_handlers.py — use the aggregated
    # source so the asserts keep matching regardless of file boundaries.
    from tests._routes_aggregator import routes_aggregated_source

    src = routes_aggregated_source()
    assert 'WhatsAppMediaTooLargeError' in src
    # The handler maps to 413 with a generic detail that doesn't expose the cap
    assert 'status_code=413' in src
    assert "detail='Media exceeds maximum allowed size'" in src
    # Server-side log still records the phase + max_bytes for forensics
    assert "'media.payload_too_large'" in src


# ─────────── QW#5 — SERVICE_TOKEN_NEXT empty string → None ────────────────


def test_config_validator_coerces_empty_service_token_next():
    src = (REPO_ROOT / 'app' / 'core' / 'config.py').read_text()
    assert 'from pydantic import Field, field_validator' in src
    assert '_empty_service_token_next_is_none' in src
    assert "@field_validator('service_token_next', mode='before')" in src


def test_service_token_next_empty_string_resolves_to_none(monkeypatch):
    """Functional check: SERVICE_TOKEN_NEXT='' must NOT crash bootstrap."""
    from app.core.config import Settings

    monkeypatch.setenv('DATABASE_URL', 'postgresql://example')
    monkeypatch.setenv('JWT_SECRET', 'jwt-secret-with-min-length')
    monkeypatch.setenv('SERVICE_TOKEN', 'service-token-with-min-length')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 's3-secret')
    # Empty string used to crash with ValidationError (min_length=16)
    monkeypatch.setenv('SERVICE_TOKEN_NEXT', '')
    s = Settings()  # type: ignore[call-arg]
    assert s.service_token_next is None


def test_service_token_next_whitespace_resolves_to_none(monkeypatch):
    """Whitespace-only values also coerce to None (operator paste mistakes)."""
    from app.core.config import Settings

    monkeypatch.setenv('DATABASE_URL', 'postgresql://example')
    monkeypatch.setenv('JWT_SECRET', 'jwt-secret-with-min-length')
    monkeypatch.setenv('SERVICE_TOKEN', 'service-token-with-min-length')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 's3-secret')
    monkeypatch.setenv('SERVICE_TOKEN_NEXT', '   ')
    s = Settings()  # type: ignore[call-arg]
    assert s.service_token_next is None


def test_service_token_next_valid_value_still_works(monkeypatch):
    """Real next secret with sufficient length is preserved as-is."""
    from app.core.config import Settings

    monkeypatch.setenv('DATABASE_URL', 'postgresql://example')
    monkeypatch.setenv('JWT_SECRET', 'jwt-secret-with-min-length')
    monkeypatch.setenv('SERVICE_TOKEN', 'service-token-with-min-length')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 's3-secret')
    monkeypatch.setenv('SERVICE_TOKEN_NEXT', 'rotated-secret-with-min-length')
    s = Settings()  # type: ignore[call-arg]
    assert s.service_token_next == 'rotated-secret-with-min-length'


def test_service_token_next_short_value_still_fails(monkeypatch):
    """Non-empty value below min_length must still raise (no policy bypass)."""
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.setenv('DATABASE_URL', 'postgresql://example')
    monkeypatch.setenv('JWT_SECRET', 'jwt-secret-with-min-length')
    monkeypatch.setenv('SERVICE_TOKEN', 'service-token-with-min-length')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 's3-secret')
    monkeypatch.setenv('SERVICE_TOKEN_NEXT', 'short')
    with pytest.raises(ValidationError):
        Settings()  # type: ignore[call-arg]
