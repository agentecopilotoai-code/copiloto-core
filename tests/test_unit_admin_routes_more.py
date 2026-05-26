"""Unit tests for app/admin/routes.py — BFF helpers."""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest


def _run(c):
    return asyncio.run(c)


# ─── _active_session_id ─────────────────────────────────────────────────


def test_active_session_id_none_input():
    from app.admin.routes import _active_session_id
    assert _active_session_id(None) is None
    assert _active_session_id('') is None


def test_active_session_id_unknown_session():
    from app.admin.routes import _active_session_id, _sessions
    _sessions.clear()
    assert _active_session_id('nonexistent') is None


def test_active_session_id_expired_session():
    from app.admin.routes import _active_session_id, _sessions
    _sessions.clear()
    sid = 'expired-sid'
    _sessions[sid] = {'expires_at': time.time() - 1, 'profile': {}}
    assert _active_session_id(sid) is None
    # Should be removed
    assert sid not in _sessions


def test_active_session_id_valid_session():
    from app.admin.routes import _active_session_id, _sessions
    _sessions.clear()
    sid = 'valid-sid'
    _sessions[sid] = {'expires_at': time.time() + 60, 'profile': {'sub': 'u|1'}}
    out = _active_session_id(sid)
    assert out is not None
    assert out['profile']['sub'] == 'u|1'


# ─── _role_at_least / _has_admin_role ───────────────────────────────────


def test_role_at_least_equal_passes():
    from app.admin.routes import _role_at_least
    assert _role_at_least('admin', 'admin') is True


def test_role_at_least_higher_passes():
    from app.admin.routes import _role_at_least
    assert _role_at_least('owner', 'admin') is True


def test_role_at_least_lower_fails():
    from app.admin.routes import _role_at_least
    assert _role_at_least('viewer', 'admin') is False


def test_role_at_least_unknown_role_zero():
    from app.admin.routes import _role_at_least
    assert _role_at_least('nonexistent_role', 'admin') is False


def test_has_admin_role_yes():
    from app.admin.routes import _has_admin_role
    session = {'profile': {'roles': ['admin']}}
    assert _has_admin_role(session, 'admin') is True


def test_has_admin_role_no():
    from app.admin.routes import _has_admin_role
    session = {'profile': {'roles': ['agent']}}
    assert _has_admin_role(session, 'admin') is False


def test_has_admin_role_no_roles_key():
    from app.admin.routes import _has_admin_role
    session = {'profile': {}}
    assert _has_admin_role(session, 'agent') is False


def test_has_admin_role_no_profile():
    from app.admin.routes import _has_admin_role
    assert _has_admin_role({}, 'agent') is False


# ─── _session_claim_matches_tenant ──────────────────────────────────────


def test_session_claim_matches_tenant_valid():
    from app.admin.routes import _session_claim_matches_tenant
    tid = uuid4()
    session = {'profile': {'tenant_id': str(tid)}}
    assert _session_claim_matches_tenant(session, tid) is True


def test_session_claim_matches_tenant_mismatch():
    from app.admin.routes import _session_claim_matches_tenant
    session = {'profile': {'tenant_id': str(uuid4())}}
    assert _session_claim_matches_tenant(session, uuid4()) is False


def test_session_claim_matches_tenant_invalid_uuid():
    from app.admin.routes import _session_claim_matches_tenant
    session = {'profile': {'tenant_id': 'not-a-uuid'}}
    assert _session_claim_matches_tenant(session, uuid4()) is False


def test_session_claim_matches_tenant_none_claim():
    from app.admin.routes import _session_claim_matches_tenant
    session = {'profile': {}}
    assert _session_claim_matches_tenant(session, uuid4()) is False


# ─── _session_can_stream_tenant ─────────────────────────────────────────


def test_session_can_stream_support_mode_with_agent_role():
    """A2: el support_mode shortcut SOLO aplica si la cookie firmada
    matchea el tenant_id. El claim cacheado solo NO basta."""
    from app.admin.routes import _session_can_stream_tenant
    session = {'profile': {'support_mode': True, 'roles': ['agent']}}
    tenant_id = uuid4()
    # Sin cookie tid → cae al DB-check.
    from app.db.pool import db
    original_pool = db.pool
    db.pool = None
    try:
        out = _run(_session_can_stream_tenant(session, tenant_id))
        assert out is False, 'sin cookie matching debe ir al DB-check'
        # Con cookie matching → shortcut aplica.
        out = _run(_session_can_stream_tenant(
            session, tenant_id, support_cookie_tid=str(tenant_id),
        ))
        assert out is True
    finally:
        db.pool = original_pool


def test_session_can_stream_support_cookie_different_tenant():
    """Cookie matching tenant A NO autoriza WS para tenant B."""
    from app.admin.routes import _session_can_stream_tenant
    session = {'profile': {'support_mode': True, 'roles': ['agent']}}
    from app.db.pool import db
    original_pool = db.pool
    db.pool = None
    try:
        out = _run(_session_can_stream_tenant(
            session, uuid4(), support_cookie_tid=str(uuid4()),
        ))
        assert out is False
    finally:
        db.pool = original_pool


def test_session_can_stream_support_mode_without_role():
    from app.admin.routes import _session_can_stream_tenant
    session = {'profile': {'support_mode': True, 'roles': []}}
    # Falls through to DB check, which we mock via no pool
    from app.db.pool import db
    original_pool = db.pool
    db.pool = None
    try:
        out = _run(_session_can_stream_tenant(session, uuid4()))
        assert out is False
    finally:
        db.pool = original_pool


def test_session_can_stream_no_sub():
    from app.admin.routes import _session_can_stream_tenant
    session = {'profile': {}}
    out = _run(_session_can_stream_tenant(session, uuid4()))
    assert out is False


def test_session_can_stream_no_pool():
    from app.admin.routes import _session_can_stream_tenant
    from app.db.pool import db
    session = {'profile': {'sub': 'u|1'}}
    original_pool = db.pool
    db.pool = None
    try:
        out = _run(_session_can_stream_tenant(session, uuid4()))
        assert out is False
    finally:
        db.pool = original_pool


# ─── _sign / _pack_state / _unpack_state ────────────────────────────────


def test_pack_and_unpack_state_roundtrip():
    from app.admin.routes import _pack_state, _unpack_state
    payload = {'state': 'abc', 'foo': 1}
    packed = _pack_state(payload)
    out = _unpack_state(packed)
    assert out['state'] == 'abc'
    assert out['foo'] == 1


def test_unpack_state_invalid_returns_none():
    from app.admin.routes import _unpack_state
    assert _unpack_state('tampered.value.x') is None


def test_sign_returns_signed():
    from app.admin.routes import _sign
    out = _sign('hello')
    # The signed value should differ from input
    assert out != 'hello'


# ─── _namespaced_claim ──────────────────────────────────────────────────


def test_namespaced_claim_with_value():
    from app.admin.routes import _namespaced_claim
    from app.admin.config import get_admin_settings
    settings = get_admin_settings()
    ns = settings.auth0_claims_namespace.rstrip('/')
    claims = {f'{ns}/roles': ['admin']}
    assert _namespaced_claim(claims, 'roles') == ['admin']


def test_namespaced_claim_default():
    from app.admin.routes import _namespaced_claim
    out = _namespaced_claim({}, 'missing', default='fallback')
    assert out == 'fallback'


# ─── _core_api_url ──────────────────────────────────────────────────────


def test_core_api_url_basic():
    from app.admin.routes import _core_api_url
    out = _core_api_url('/v1/users')
    assert out.endswith('/v1/users')


def test_core_api_url_strips_leading_slash():
    from app.admin.routes import _core_api_url
    out = _core_api_url('v1/users')
    assert '/v1/users' in out


def test_core_api_url_with_query():
    from app.admin.routes import _core_api_url
    out = _core_api_url('/v1/users', query='page=1&size=10')
    assert '?page=1&size=10' in out


# ─── _core_api_headers ──────────────────────────────────────────────────


def test_core_api_headers_basic():
    from app.admin.routes import _core_api_headers
    request = SimpleNamespace(
        headers={'accept': 'application/json', 'content-type': 'application/json',
                 'x-tenant-id': str(uuid4()), 'idempotency-key': 'idem-1'},
        cookies={},
    )
    session = {'access_token': 'tok', 'profile': {'email': 'x@y.com', 'name': 'X', 'sub': 'u|1'}}
    out = _core_api_headers(request, session, has_body=True)
    assert out['authorization'] == 'Bearer tok'
    assert out['accept'] == 'application/json'
    assert out['content-type'] == 'application/json'
    assert out['x-tenant-id']
    assert out['idempotency-key'] == 'idem-1'
    assert out['x-admin-user-email'] == 'x@y.com'
    assert out['x-admin-user-name'] == 'X'
    # M42 — `x-admin-identity` (HMAC signed) se removió: nunca tuvo verifier
    # backend que lo consultara, era dead defense-in-depth.
    assert 'x-admin-identity' not in out


def test_core_api_headers_no_body_no_content_type():
    from app.admin.routes import _core_api_headers
    request = SimpleNamespace(headers={}, cookies={})
    session = {'access_token': 'tok', 'profile': {}}
    out = _core_api_headers(request, session, has_body=False)
    assert 'content-type' not in out


def test_core_api_headers_forwards_support_mode_cookie():
    from app.admin.routes import _core_api_headers
    request = SimpleNamespace(headers={}, cookies={'copilotoia_support_mode': 'signed-value'})
    session = {'access_token': 'tok', 'profile': {}}
    out = _core_api_headers(request, session, has_body=False)
    assert 'copilotoia_support_mode=signed-value' in out['cookie']


def test_core_api_headers_no_email_no_identity():
    """If no sub+email in profile, no x-admin-identity header."""
    from app.admin.routes import _core_api_headers
    request = SimpleNamespace(headers={}, cookies={})
    session = {'access_token': 'tok', 'profile': {}}
    out = _core_api_headers(request, session, has_body=False)
    assert 'x-admin-identity' not in out


# ─── _auth0_base_url / _admin_client_secret ─────────────────────────────


def test_auth0_base_url_returns_url(monkeypatch):
    from app.admin import routes
    from app.admin.routes import _auth0_base_url
    fake_settings = SimpleNamespace(auth0_domain='test.auth0.com')
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    out = _auth0_base_url()
    assert out == 'https://test.auth0.com'


def test_auth0_base_url_strips_trailing_slash(monkeypatch):
    from app.admin import routes
    from app.admin.routes import _auth0_base_url
    fake_settings = SimpleNamespace(auth0_domain='test.auth0.com/')
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    out = _auth0_base_url()
    assert out == 'https://test.auth0.com'


def test_auth0_base_url_no_domain_raises(monkeypatch):
    from fastapi import HTTPException
    from app.admin import routes
    from app.admin.routes import _auth0_base_url
    fake_settings = SimpleNamespace(auth0_domain=None)
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    with pytest.raises(HTTPException) as exc:
        _auth0_base_url()
    assert exc.value.status_code == 503


def test_admin_client_secret_from_env(monkeypatch):
    from app.admin import routes
    from app.admin.routes import _admin_client_secret
    fake_settings = SimpleNamespace(
        auth0_admin_client_secret='direct-secret',
        auth0_admin_client_secret_file=None,
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    assert _admin_client_secret() == 'direct-secret'


def test_admin_client_secret_from_file(monkeypatch, tmp_path):
    from app.admin import routes
    from app.admin.routes import _admin_client_secret
    f = tmp_path / 'secret.txt'
    f.write_text('file-secret\n')
    fake_settings = SimpleNamespace(
        auth0_admin_client_secret=None,
        auth0_admin_client_secret_file=str(f),
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    assert _admin_client_secret() == 'file-secret'


def test_admin_client_secret_not_configured(monkeypatch):
    from fastapi import HTTPException
    from app.admin import routes
    from app.admin.routes import _admin_client_secret
    fake_settings = SimpleNamespace(
        auth0_admin_client_secret=None,
        auth0_admin_client_secret_file=None,
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    with pytest.raises(HTTPException) as exc:
        _admin_client_secret()
    assert exc.value.status_code == 503


# ─── _callback_url ──────────────────────────────────────────────────────


def test_callback_url_picks_https_first(monkeypatch):
    from app.admin import routes
    from app.admin.routes import _callback_url
    fake_settings = SimpleNamespace(
        auth0_callback_urls='https://x.com/cb,http://localhost:3000/cb',
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    # Build a minimal request stub
    request = SimpleNamespace(url_for=lambda name: 'http://default/cb')
    out = _callback_url(request)
    assert out == 'https://x.com/cb'


def test_callback_url_localhost_allowed():
    from app.admin.routes import _callback_url
    request = SimpleNamespace(url_for=lambda name: 'http://default/cb')
    out = _callback_url(request)
    # The real settings might have an http://localhost:3000/ value
    # Just verify it returns something
    assert out


# ─── _logout_return_to ──────────────────────────────────────────────────


def test_logout_return_to_returns_admin_normalized(monkeypatch):
    from app.admin import routes
    from app.admin.routes import _logout_return_to
    fake_settings = SimpleNamespace(
        auth0_logout_urls='https://x.com/admin',
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    request = SimpleNamespace(url_for=lambda name: 'http://default/admin')
    out = _logout_return_to(request)
    assert out == 'https://x.com/admin/'


def test_logout_return_to_fallback_first_url(monkeypatch):
    from app.admin import routes
    from app.admin.routes import _logout_return_to
    fake_settings = SimpleNamespace(
        auth0_logout_urls='https://x.com/somewhere',
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    request = SimpleNamespace(url_for=lambda name: 'http://default/admin')
    out = _logout_return_to(request)
    assert out == 'https://x.com/somewhere'


def test_logout_return_to_empty_url_list(monkeypatch):
    from app.admin import routes
    from app.admin.routes import _logout_return_to
    fake_settings = SimpleNamespace(auth0_logout_urls='')
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    request = SimpleNamespace(url_for=lambda name: 'http://default/admin')
    out = _logout_return_to(request)
    assert out == 'http://default/admin'


# ─── _active_session ────────────────────────────────────────────────────


def test_active_session_no_cookie():
    from app.admin.routes import _active_session
    request = SimpleNamespace(cookies={})
    out = _active_session(request)
    assert out is None


def test_active_session_with_cookie():
    from app.admin.routes import _active_session, _sessions, SESSION_COOKIE
    _sessions.clear()
    sid = 'live-sid'
    _sessions[sid] = {'expires_at': time.time() + 100, 'profile': {}}
    request = SimpleNamespace(cookies={SESSION_COOKIE: sid})
    out = _active_session(request)
    assert out is not None


# ─── _dist_file ─────────────────────────────────────────────────────────


def test_dist_file_path_traversal_blocked():
    """Path traversal attempt should raise 503."""
    from fastapi import HTTPException
    from app.admin.routes import _dist_file
    with pytest.raises(HTTPException) as exc:
        _dist_file('../../../etc/passwd')
    assert exc.value.status_code == 503


def test_dist_file_nonexistent_raises():
    from fastapi import HTTPException
    from app.admin.routes import _dist_file
    with pytest.raises(HTTPException):
        _dist_file('definitely-does-not-exist-asdf.html')


# ─── M47 — _debug helper ───────────────────────────────────────────────────


def test_debug_helper_noop_when_disabled(monkeypatch, capsys):
    """Cuando BFF_DEBUG=0 (default), `_debug()` no imprime nada."""
    from app.admin import routes as ar
    monkeypatch.setattr(ar, '_BFF_DEBUG', False)
    ar._debug('test_stage', foo='bar')
    out = capsys.readouterr().out
    assert out == ''


def test_debug_helper_prints_when_enabled(monkeypatch, capsys):
    """Cuando BFF_DEBUG=1, imprime una línea con stage + key=val."""
    from app.admin import routes as ar
    monkeypatch.setattr(ar, '_BFF_DEBUG', True)
    ar._debug('test_stage', foo='bar', count=42)
    out = capsys.readouterr().out
    assert '[BFF-DEBUG]' in out
    assert 'test_stage' in out
    assert 'foo=bar' in out
    assert 'count=42' in out


def test_debug_helper_redacts_sensitive_keys(monkeypatch, capsys):
    """Cualquier key con 'secret', 'token', 'code', 'state', 'sid', 'cookie'
    en el nombre se trunca a 8 chars para no leakear credenciales."""
    from app.admin import routes as ar
    monkeypatch.setattr(ar, '_BFF_DEBUG', True)
    ar._debug(
        'test',
        sid='abcdefghijklmnop123456',
        secret='super-secret-value-xyz',
        access_token='very-long-token-string',
        ok_field='public-value-not-redacted',
    )
    out = capsys.readouterr().out
    assert 'sid=abcdefgh…' in out
    assert 'secret=super-se…' in out
    assert 'access_token=very-lon…' in out
    # Non-sensitive passthrough
    assert 'ok_field=public-value-not-redacted' in out


def test_debug_helper_handles_none(monkeypatch, capsys):
    """None se muestra como ∅ para distinguir de string vacío."""
    from app.admin import routes as ar
    monkeypatch.setattr(ar, '_BFF_DEBUG', True)
    ar._debug('test', value=None)
    out = capsys.readouterr().out
    assert 'value=∅' in out
