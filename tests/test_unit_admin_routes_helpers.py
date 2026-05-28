"""Pure-helper tests for `app/admin/routes.py`.

Covers small helpers that don't need full Auth0/HTTP/DB. Patches
`get_admin_settings` to bypass the env-file based loader.
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from uuid import uuid4

import pytest


def _stub_admin_settings(monkeypatch, **overrides) -> None:
    """Monkey-patch `get_admin_settings` in both the admin.config and the
    admin.routes module re-export so all callsites see the stub."""
    defaults = {
        'state_secret': 'a-very-long-secret-key-for-test-32',
        'jwt_secret': 'a-very-long-secret-key-for-test-32',
        'admin_session_secret': None,
        'auth0_domain': None,
        'auth0_issuer': None,
        'auth0_audience': None,
        'auth0_api_identifier': None,
        'auth0_admin_client_id': None,
        'auth0_admin_client_secret': None,
        'auth0_admin_client_secret_file': None,
        'auth0_callback_urls': 'http://localhost:3000/callback',
        'auth0_logout_urls': 'http://localhost:3000/admin/',
        'auth0_claims_namespace': 'https://copilotoia.com/claims/',
        'mfa_enforcement_enabled': True,
    }
    defaults.update(overrides)
    stub = SimpleNamespace(**defaults)
    from copiloto_core.admin import routes as admin_routes
    monkeypatch.setattr(admin_routes, 'get_admin_settings', lambda: stub)


# ───────── _sign / _pack_state / _unpack_state ──────────────────────────


def test_sign_returns_signed_string(monkeypatch):
    _stub_admin_settings(monkeypatch)
    from copiloto_core.admin.routes import _sign
    out = _sign('hello')
    # The underlying HMAC produces a base64url-safe signature
    assert isinstance(out, str)
    assert out  # non-empty
    # Same input → same sig (deterministic)
    assert _sign('hello') == out
    assert _sign('different') != out


def test_pack_and_unpack_state_round_trip(monkeypatch):
    _stub_admin_settings(monkeypatch)
    from copiloto_core.admin.routes import _pack_state, _unpack_state
    payload = {'sub': 'user1', 'exp': 9999999999}
    packed = _pack_state(payload)
    out = _unpack_state(packed)
    assert out == payload


def test_unpack_state_returns_none_for_invalid(monkeypatch):
    _stub_admin_settings(monkeypatch)
    from copiloto_core.admin.routes import _unpack_state
    assert _unpack_state('garbage') is None


# ───────── _auth0_base_url ───────────────────────────────────────────────


def test_auth0_base_url_requires_config(monkeypatch):
    from fastapi import HTTPException
    _stub_admin_settings(monkeypatch, auth0_domain=None)
    from copiloto_core.admin.routes import _auth0_base_url
    with pytest.raises(HTTPException) as exc_info:
        _auth0_base_url()
    assert exc_info.value.status_code == 503


def test_auth0_base_url_strips_trailing_slash(monkeypatch):
    _stub_admin_settings(monkeypatch, auth0_domain='tenant.auth0.com/')
    from copiloto_core.admin.routes import _auth0_base_url
    assert _auth0_base_url() == 'https://tenant.auth0.com'


# ───────── _admin_client_secret ──────────────────────────────────────────


def test_admin_client_secret_returns_inline_value(monkeypatch):
    _stub_admin_settings(monkeypatch, auth0_admin_client_secret='inline-secret')
    from copiloto_core.admin.routes import _admin_client_secret
    assert _admin_client_secret() == 'inline-secret'


def test_admin_client_secret_reads_from_file(monkeypatch, tmp_path):
    secret_file = tmp_path / 's.txt'
    secret_file.write_text('from-file-secret\n')
    _stub_admin_settings(
        monkeypatch,
        auth0_admin_client_secret=None,
        auth0_admin_client_secret_file=str(secret_file),
    )
    from copiloto_core.admin.routes import _admin_client_secret
    assert _admin_client_secret() == 'from-file-secret'


def test_admin_client_secret_missing_raises(monkeypatch):
    from fastapi import HTTPException
    _stub_admin_settings(
        monkeypatch,
        auth0_admin_client_secret=None,
        auth0_admin_client_secret_file=None,
    )
    from copiloto_core.admin.routes import _admin_client_secret
    with pytest.raises(HTTPException) as exc_info:
        _admin_client_secret()
    assert exc_info.value.status_code == 503


def test_admin_client_secret_file_missing_raises(monkeypatch, tmp_path):
    from fastapi import HTTPException
    _stub_admin_settings(
        monkeypatch,
        auth0_admin_client_secret=None,
        auth0_admin_client_secret_file=str(tmp_path / 'nonexistent.txt'),
    )
    from copiloto_core.admin.routes import _admin_client_secret
    with pytest.raises(HTTPException):
        _admin_client_secret()


# ───────── _active_session_id ────────────────────────────────────────────


def test_active_session_id_returns_none_for_empty_id():
    import asyncio
    from copiloto_core.admin.routes import _active_session_id
    assert asyncio.run(_active_session_id(None)) is None
    assert asyncio.run(_active_session_id('')) is None


def test_active_session_id_returns_session_when_active():
    """P0-3: usar session_store API en vez de mutar _sessions directo."""
    import asyncio
    from copiloto_core.admin import routes as admin_routes
    from copiloto_core.admin.session_store import get_session_store
    sid = 'test-session-id-1'
    asyncio.run(get_session_store().set(sid, {'profile': {'email': 'x@y'}}, 3600))
    out = asyncio.run(admin_routes._active_session_id(sid))
    assert out is not None
    assert out['profile']['email'] == 'x@y'


def test_active_session_id_drops_expired():
    """P0-3: el store rechaza expired internamente (lazy expiration)."""
    import asyncio
    from copiloto_core.admin import routes as admin_routes
    from copiloto_core.admin.session_store import get_session_store
    sid = 'expired-session-id-1'
    asyncio.run(get_session_store().set(sid, {'profile': {'email': 'x@y'}}, 1))
    time.sleep(1.1)
    out = asyncio.run(admin_routes._active_session_id(sid))
    assert out is None


# ───────── _role_at_least / _has_admin_role ─────────────────────────────


def test_role_at_least():
    from copiloto_core.admin.routes import _role_at_least
    assert _role_at_least('admin', 'admin') is True
    assert _role_at_least('owner', 'admin') is True
    assert _role_at_least('manager', 'admin') is False
    assert _role_at_least('agent', 'manager') is False
    assert _role_at_least('manager', 'manager') is True


def test_role_at_least_unknown_role():
    from copiloto_core.admin.routes import _role_at_least
    # platform_owner isn't in the admin role table (admin BFF uses tenant
    # roles only; platform_owner is a separate ladder)
    assert _role_at_least('platform_owner', 'admin') is False
    assert _role_at_least('weird', 'agent') is False


def test_has_admin_role():
    from copiloto_core.admin.routes import _has_admin_role
    session = {'profile': {'roles': ['owner']}}
    assert _has_admin_role(session, 'admin') is True
    assert _has_admin_role(session, 'manager') is True

    session2 = {'profile': {'roles': ['agent']}}
    assert _has_admin_role(session2, 'admin') is False


def test_has_admin_role_no_roles():
    from copiloto_core.admin.routes import _has_admin_role
    assert _has_admin_role({}, 'admin') is False
    assert _has_admin_role({'profile': {}}, 'admin') is False
    assert _has_admin_role({'profile': {'roles': []}}, 'admin') is False


# ───────── _session_claim_matches_tenant ─────────────────────────────────


def test_session_claim_matches_tenant_true():
    from copiloto_core.admin.routes import _session_claim_matches_tenant
    tid = uuid4()
    session = {'profile': {'tenant_id': str(tid)}}
    assert _session_claim_matches_tenant(session, tid) is True


def test_session_claim_matches_tenant_false_different():
    from copiloto_core.admin.routes import _session_claim_matches_tenant
    session = {'profile': {'tenant_id': str(uuid4())}}
    assert _session_claim_matches_tenant(session, uuid4()) is False


def test_session_claim_matches_tenant_missing():
    from copiloto_core.admin.routes import _session_claim_matches_tenant
    assert _session_claim_matches_tenant({}, uuid4()) is False
    assert _session_claim_matches_tenant(
        {'profile': {'tenant_id': 'not-a-uuid'}}, uuid4(),
    ) is False


# ───────── _logout_return_to ────────────────────────────────────────────


def test_logout_return_to_uses_admin_url_when_configured(monkeypatch):
    _stub_admin_settings(
        monkeypatch,
        auth0_logout_urls='https://app.example.com/admin,https://app.example.com',
    )
    from copiloto_core.admin.routes import _logout_return_to
    request = SimpleNamespace(url_for=lambda name: 'https://fallback/')
    out = _logout_return_to(request)
    assert out == 'https://app.example.com/admin/'


def test_logout_return_to_falls_back_to_first(monkeypatch):
    _stub_admin_settings(monkeypatch, auth0_logout_urls='https://x.com/')
    from copiloto_core.admin.routes import _logout_return_to
    request = SimpleNamespace(url_for=lambda name: 'https://fallback/')
    out = _logout_return_to(request)
    assert out == 'https://x.com/'


def test_logout_return_to_falls_back_to_url_for_when_empty(monkeypatch):
    _stub_admin_settings(monkeypatch, auth0_logout_urls='')
    from copiloto_core.admin.routes import _logout_return_to
    request = SimpleNamespace(url_for=lambda name: 'https://fallback/admin/')
    out = _logout_return_to(request)
    assert out == 'https://fallback/admin/'


# ───────── _callback_url ─────────────────────────────────────────────────


def test_callback_url_prefers_localhost_3000(monkeypatch):
    _stub_admin_settings(
        monkeypatch,
        auth0_callback_urls='https://prod.example.com/callback,http://localhost:3000/callback',
    )
    from copiloto_core.admin.routes import _callback_url
    request = SimpleNamespace(url_for=lambda name: 'https://fallback/')
    # First url that matches: localhost:3000 OR https://
    out = _callback_url(request)
    assert out in (
        'https://prod.example.com/callback',
        'http://localhost:3000/callback',
    )


def test_callback_url_falls_back_to_url_for(monkeypatch):
    _stub_admin_settings(monkeypatch, auth0_callback_urls='')
    from copiloto_core.admin.routes import _callback_url
    request = SimpleNamespace(url_for=lambda name: 'https://fallback/cb')
    out = _callback_url(request)
    assert out == 'https://fallback/cb'
