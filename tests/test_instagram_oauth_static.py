"""Static tests para Instagram OAuth + platform_connections — TASK-INFLU-014."""
from __future__ import annotations

import time
from pathlib import Path
from uuid import uuid4

import pytest

from app.influencer.instagram_oauth import (
    DEFAULT_SCOPES,
    INSTAGRAM_AUTHORIZE_URL,
    STATE_TTL_SECONDS,
    build_authorize_url,
    build_oauth_state,
    verify_oauth_state,
)
from app.influencer.instagram_router import instagram_router


SCHEMA = Path('infra/postgres/03-migrations.sql').read_text(encoding='utf-8')
ROUTER_SRC = Path('app/influencer/instagram_router.py').read_text(encoding='utf-8')


# ─── Migración SQL ─────────────────────────────────────────────────────────


def test_migration_platform_connections_table():
    assert 'create table if not exists influencer.platform_connections' in SCHEMA
    assert "platform in ('instagram', 'tiktok', 'youtube'" in SCHEMA
    assert "status in ('connected', 'expired', 'disconnected', 'pending')" in SCHEMA


def test_migration_tokens_via_secret_ref():
    """Los tokens NO están en claro — son referencias a `platform_secrets`."""
    assert 'oauth_token_ref text null references app.platform_secrets' in SCHEMA
    assert 'refresh_token_ref text null references app.platform_secrets' in SCHEMA


def test_migration_unique_active_connection_per_platform():
    """Un personaje no puede tener 2 conexiones activas a la misma platform."""
    assert 'ux_platform_connections_persona_platform' in SCHEMA
    assert "where status <> 'disconnected'" in SCHEMA


def test_migration_rls_enabled():
    assert 'enable row level security' in SCHEMA
    assert 'platform_connections_tenant_isolation' in SCHEMA


# ─── State HMAC ────────────────────────────────────────────────────────────


def test_state_signs_and_verifies():
    pid = uuid4()
    state = build_oauth_state(persona_id=pid, secret='topsecret')
    decoded = verify_oauth_state(state=state, secret='topsecret', expected_persona_id=pid)
    assert decoded == pid


def test_state_hmac_mismatch_rejected():
    pid = uuid4()
    state = build_oauth_state(persona_id=pid, secret='real-secret')
    with pytest.raises(ValueError, match='HMAC'):
        verify_oauth_state(state=state, secret='wrong-secret')


def test_state_rejects_mismatched_persona():
    pid = uuid4()
    other = uuid4()
    state = build_oauth_state(persona_id=pid, secret='s')
    with pytest.raises(ValueError, match='persona_id'):
        verify_oauth_state(state=state, secret='s', expected_persona_id=other)


def test_state_rejects_expired(monkeypatch):
    pid = uuid4()
    # Construye un state con timestamp ya viejo.
    real_time = time.time()
    monkeypatch.setattr(
        'app.influencer.instagram_oauth.time.time',
        lambda: real_time - STATE_TTL_SECONDS - 60,
    )
    state = build_oauth_state(persona_id=pid, secret='s')
    monkeypatch.undo()
    with pytest.raises(ValueError, match='expired'):
        verify_oauth_state(state=state, secret='s')


def test_state_malformed_rejected():
    with pytest.raises(ValueError):
        verify_oauth_state(state='not-valid', secret='s')


# ─── Authorize URL ─────────────────────────────────────────────────────────


def test_build_authorize_url_includes_required_params():
    url = build_authorize_url(
        client_id='abc123', redirect_uri='https://app/cb', state='S',
    )
    assert url.startswith(INSTAGRAM_AUTHORIZE_URL)
    assert 'client_id=abc123' in url
    assert 'response_type=code' in url
    assert 'state=S' in url
    assert 'scope=' in url


def test_default_scopes_include_publish():
    """`instagram_content_publish` es necesario para que el publish_worker
    de TASK-INFLU-015 pueda postear."""
    assert 'instagram_content_publish' in DEFAULT_SCOPES


# ─── Router shape ──────────────────────────────────────────────────────────


def test_router_has_3_endpoints():
    paths = {(r.path, tuple(sorted(r.methods))) for r in instagram_router.routes}
    base = '/v1/influencer/personas/{persona_id}/platforms/instagram'
    assert any(p[0] == f'{base}/oauth/start' and 'GET' in p[1] for p in paths)
    assert any(p[0] == f'{base}/oauth/callback' and 'GET' in p[1] for p in paths)
    assert any(p[0] == f'{base}/disconnect' and 'POST' in p[1] for p in paths)


def test_disconnect_requires_mfa():
    assert 'require_mfa_for_privileged' in ROUTER_SRC
    delete_idx = ROUTER_SRC.find('@instagram_router.post')
    assert delete_idx != -1
    block = ROUTER_SRC[delete_idx:delete_idx + 800]
    assert 'require_mfa_for_privileged' in block


def test_callback_verifies_state():
    """El callback DEBE llamar a verify_oauth_state con expected_persona_id."""
    assert 'verify_oauth_state' in ROUTER_SRC
    assert 'expected_persona_id=persona_id' in ROUTER_SRC


def test_token_persisted_as_secret_ref():
    """El token va a `app.platform_secrets`, no en logs ni en claro."""
    assert 'platform_secrets' in ROUTER_SRC
    assert 'secret_ref' in ROUTER_SRC


def test_router_mounted_in_main():
    main_src = Path('app/main.py').read_text(encoding='utf-8')
    assert 'instagram_router' in main_src
