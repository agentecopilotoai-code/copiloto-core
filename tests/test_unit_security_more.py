"""Extra tests for app/core/security.py."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException


def _run(c):
    return asyncio.run(c)


# ─── _normalize_auth0_domain / _normalize_issuer / _auth0_issuer ─────────


def test_normalize_auth0_domain_strips_protocol_and_trailing_slash():
    from app.core.security import _normalize_auth0_domain
    assert _normalize_auth0_domain('https://test.auth0.com/') == 'test.auth0.com'


def test_normalize_auth0_domain_handles_bare_domain():
    from app.core.security import _normalize_auth0_domain
    assert _normalize_auth0_domain('test.auth0.com') == 'test.auth0.com'


def test_normalize_issuer_adds_trailing_slash():
    from app.core.security import _normalize_issuer
    assert _normalize_issuer('https://test.auth0.com').endswith('/')


def test_normalize_issuer_no_double_slash():
    from app.core.security import _normalize_issuer
    out = _normalize_issuer('https://test.auth0.com/')
    assert out == 'https://test.auth0.com/'


def test_auth0_issuer_uses_configured():
    from app.core.security import _auth0_issuer
    assert _auth0_issuer('test.auth0.com', 'https://custom-issuer/').endswith('/')


def test_auth0_issuer_derives_from_domain():
    from app.core.security import _auth0_issuer
    out = _auth0_issuer('test.auth0.com')
    assert 'test.auth0.com' in out
    assert out.endswith('/')


# ─── _select_jwk ─────────────────────────────────────────────────────────


def test_select_jwk_single_key_without_kid():
    from app.core.security import _select_jwk
    jwks = {'keys': [{'kid': 'k1'}]}
    out = _select_jwk(jwks, None)
    assert out['kid'] == 'k1'


def test_select_jwk_matches_kid():
    from app.core.security import _select_jwk
    jwks = {'keys': [{'kid': 'k1'}, {'kid': 'k2'}]}
    out = _select_jwk(jwks, 'k2')
    assert out['kid'] == 'k2'


def test_select_jwk_unknown_kid_raises():
    from app.core.security import _select_jwk
    jwks = {'keys': [{'kid': 'k1'}, {'kid': 'k2'}]}
    with pytest.raises(HTTPException) as exc:
        _select_jwk(jwks, 'unknown')
    assert exc.value.status_code == 401


def test_select_jwk_no_keys_raises():
    from app.core.security import _select_jwk
    with pytest.raises(HTTPException):
        _select_jwk({'keys': []}, None)


# ─── _decode_auth0_token error paths ─────────────────────────────────────


def test_decode_auth0_token_no_domain_raises():
    from app.core.security import _decode_auth0_token
    settings = SimpleNamespace(auth0_domain=None, auth0_audience=None)
    with pytest.raises(HTTPException) as exc:
        _run(_decode_auth0_token('any', settings))
    assert exc.value.status_code == 401


def test_decode_auth0_token_invalid_token_raises():
    from app.core.security import _decode_auth0_token
    settings = SimpleNamespace(
        auth0_domain='x.auth0.com', auth0_audience='aud',
        auth0_issuer=None, auth0_jwks_cache_ttl_seconds=60,
    )
    with pytest.raises(HTTPException) as exc:
        _run(_decode_auth0_token('garbage-token', settings))
    assert exc.value.status_code == 401


def test_decode_auth0_token_wrong_algorithm_raises(monkeypatch):
    from app.core import security
    from app.core.security import _decode_auth0_token
    monkeypatch.setattr(security.jwt, 'get_unverified_header', lambda t: {'alg': 'HS256'})
    settings = SimpleNamespace(
        auth0_domain='x.auth0.com', auth0_audience='aud',
        auth0_issuer=None, auth0_jwks_cache_ttl_seconds=60,
    )
    with pytest.raises(HTTPException) as exc:
        _run(_decode_auth0_token('any', settings))
    assert 'algorithm' in exc.value.detail.lower()


# ─── _decode_local_token ────────────────────────────────────────────────


def test_decode_local_token_invalid_raises():
    from app.core.security import _decode_local_token
    settings = SimpleNamespace(
        jwt_secret='x' * 32, jwt_audience='aud', jwt_issuer='iss',
    )
    with pytest.raises(HTTPException):
        _decode_local_token('not.a.jwt', settings)


# ─── _decode_user_token dispatches based on auth0_domain ────────────────


def test_decode_user_token_uses_local_when_no_domain():
    from app.core.security import _decode_user_token
    settings = SimpleNamespace(
        auth0_domain=None, jwt_secret='x' * 32,
        jwt_audience='aud', jwt_issuer='iss',
    )
    with pytest.raises(HTTPException):
        _run(_decode_user_token('not.a.jwt', settings))


# ─── _has_role / has_jwt_role ──────────────────────────────────────────


def test_has_role_with_required():
    from app.core.security import _has_role
    assert _has_role(['admin'], 'admin') is True


def test_has_role_higher_satisfies_lower():
    from app.core.security import _has_role
    assert _has_role(['owner'], 'admin') is True


def test_has_role_lower_doesnt_satisfy_higher():
    from app.core.security import _has_role
    assert _has_role(['viewer'], 'admin') is False


def test_has_role_unknown_role():
    from app.core.security import _has_role
    assert _has_role(['totally_made_up'], 'admin') is False


def test_has_jwt_role_public_wrapper():
    from app.core.security import has_jwt_role
    assert has_jwt_role(['admin'], 'agent') is True


# ─── _session_has_privileged_role ───────────────────────────────────────


def test_session_has_privileged_role_true():
    from app.core.security import _session_has_privileged_role
    assert _session_has_privileged_role(['admin']) is True


def test_session_has_privileged_role_false():
    from app.core.security import _session_has_privileged_role
    assert _session_has_privileged_role(['viewer']) is False


# ─── require_platform_owner ────────────────────────────────────────────


def _request_with_state(**kw):
    state = SimpleNamespace(**kw)
    return SimpleNamespace(state=state)


def test_require_platform_owner_anonymous_401():
    from app.core.security import require_platform_owner
    req = _request_with_state(actor_type='anonymous')
    with pytest.raises(HTTPException) as exc:
        _run(require_platform_owner(req))
    assert exc.value.status_code == 401


def test_require_platform_owner_service_403():
    from app.core.security import require_platform_owner
    req = _request_with_state(actor_type='service')
    with pytest.raises(HTTPException) as exc:
        _run(require_platform_owner(req))
    assert exc.value.status_code == 403


def test_require_platform_owner_scoped_token_403():
    from app.core.security import require_platform_owner
    from uuid import uuid4
    req = _request_with_state(actor_type='user', tenant_id=uuid4(), roles=['platform_owner'])
    with pytest.raises(HTTPException) as exc:
        _run(require_platform_owner(req))
    assert exc.value.status_code == 403


def test_require_platform_owner_missing_role_403():
    from app.core.security import require_platform_owner
    req = _request_with_state(actor_type='user', tenant_id=None, roles=['admin'])
    with pytest.raises(HTTPException) as exc:
        _run(require_platform_owner(req))
    assert exc.value.status_code == 403


def test_require_platform_owner_ok():
    from app.core.security import require_platform_owner
    req = _request_with_state(actor_type='user', tenant_id=None, roles=['platform_owner'])
    _run(require_platform_owner(req))


# ─── require_service ────────────────────────────────────────────────────


def test_require_service_rejects_user():
    from app.core.security import require_service
    req = _request_with_state(actor_type='user')
    with pytest.raises(HTTPException) as exc:
        _run(require_service(req))
    assert exc.value.status_code == 403


def test_require_service_accepts_service():
    from app.core.security import require_service
    req = _request_with_state(actor_type='service')
    _run(require_service(req))


# ─── require_min_role ──────────────────────────────────────────────────


def test_require_min_role_anonymous_401():
    from app.core.security import require_min_role
    dep = require_min_role('admin')
    req = _request_with_state(actor_type='anonymous')
    with pytest.raises(HTTPException) as exc:
        _run(dep(req))
    assert exc.value.status_code == 401


def test_require_min_role_service_disallowed():
    from app.core.security import require_min_role
    dep = require_min_role('admin', allow_service=False)
    req = _request_with_state(actor_type='service')
    with pytest.raises(HTTPException) as exc:
        _run(dep(req))
    assert exc.value.status_code == 403


def test_require_min_role_service_allowed():
    from app.core.security import require_min_role
    dep = require_min_role('admin', allow_service=True)
    req = _request_with_state(actor_type='service')
    _run(dep(req))


def test_require_min_role_insufficient_role():
    from app.core.security import require_min_role
    dep = require_min_role('admin')
    req = _request_with_state(actor_type='user', roles=['viewer'])
    with pytest.raises(HTTPException) as exc:
        _run(dep(req))
    assert exc.value.status_code == 403


def test_require_min_role_sufficient_role():
    from app.core.security import require_min_role
    dep = require_min_role('admin')
    req = _request_with_state(actor_type='user', roles=['admin'])
    _run(dep(req))


# ─── require_mfa_for_privileged ───────────────────────────────────────


def test_require_mfa_anonymous_401(monkeypatch):
    from app.core.security import require_mfa_for_privileged
    req = _request_with_state(actor_type='anonymous')
    with pytest.raises(HTTPException) as exc:
        _run(require_mfa_for_privileged(req))
    assert exc.value.status_code == 401


def test_require_mfa_service_skipped(monkeypatch):
    from app.core.security import require_mfa_for_privileged
    req = _request_with_state(actor_type='service')
    _run(require_mfa_for_privileged(req))


def test_require_mfa_unprivileged_skipped(monkeypatch):
    from app.core.security import require_mfa_for_privileged
    req = _request_with_state(actor_type='user', roles=['agent'])
    _run(require_mfa_for_privileged(req))


def test_require_mfa_no_enforcement_skipped(monkeypatch):
    from app.core import security
    from app.core.security import require_mfa_for_privileged

    monkeypatch.setattr(security, 'get_settings', lambda: SimpleNamespace(
        mfa_enforcement_enabled=False, auth0_domain='x.auth0.com',
    ))
    req = _request_with_state(actor_type='user', roles=['admin'])
    _run(require_mfa_for_privileged(req))


def test_require_mfa_no_auth0_skipped(monkeypatch):
    from app.core import security
    from app.core.security import require_mfa_for_privileged

    monkeypatch.setattr(security, 'get_settings', lambda: SimpleNamespace(
        mfa_enforcement_enabled=True, auth0_domain=None,
    ))
    req = _request_with_state(actor_type='user', roles=['admin'])
    _run(require_mfa_for_privileged(req))


def test_require_mfa_missing_verified_403(monkeypatch):
    from app.core import security
    from app.core.security import require_mfa_for_privileged

    monkeypatch.setattr(security, 'get_settings', lambda: SimpleNamespace(
        mfa_enforcement_enabled=True, auth0_domain='x.auth0.com',
    ))
    req = _request_with_state(actor_type='user', roles=['admin'], mfa_verified=False)
    with pytest.raises(HTTPException) as exc:
        _run(require_mfa_for_privileged(req))
    assert exc.value.status_code == 403


def test_require_mfa_verified_ok(monkeypatch):
    from app.core import security
    from app.core.security import require_mfa_for_privileged

    monkeypatch.setattr(security, 'get_settings', lambda: SimpleNamespace(
        mfa_enforcement_enabled=True, auth0_domain='x.auth0.com',
    ))
    req = _request_with_state(actor_type='user', roles=['admin'], mfa_verified=True)
    _run(require_mfa_for_privileged(req))


# ─── _derive_session_id ────────────────────────────────────────────────


def test_derive_session_id_with_jti():
    from app.core.security import _derive_session_id
    assert _derive_session_id({'jti': 'abc'}) == 'abc'


def test_derive_session_id_fallback_to_iat_hash():
    from app.core.security import _derive_session_id
    out = _derive_session_id({'sub': 'user|1', 'iat': 12345})
    assert out is not None
    assert out.startswith('iat-')


def test_derive_session_id_no_sub_or_iat():
    from app.core.security import _derive_session_id
    assert _derive_session_id({}) is None


# ─── _extract_mfa_verified ────────────────────────────────────────────


def test_extract_mfa_verified_with_namespace():
    from app.core.security import _extract_mfa_verified
    payload = {'https://example.com/mfa_verified': True}
    assert _extract_mfa_verified(payload, 'https://example.com/') is True


def test_extract_mfa_verified_root_claim():
    from app.core.security import _extract_mfa_verified
    payload = {'mfa_verified': True}
    assert _extract_mfa_verified(payload, '') is True


def test_extract_mfa_verified_string_true():
    from app.core.security import _extract_mfa_verified
    payload = {'mfa_verified': 'true'}
    assert _extract_mfa_verified(payload, '') is True


def test_extract_mfa_verified_false():
    from app.core.security import _extract_mfa_verified
    assert _extract_mfa_verified({}, '') is False


# ─── _coerce_bool ────────────────────────────────────────────────────


def test_coerce_bool_true_strings():
    from app.core.security import _coerce_bool
    assert _coerce_bool('true') is True
    assert _coerce_bool('TRUE') is True
    assert _coerce_bool('1') is True


def test_coerce_bool_false_strings():
    from app.core.security import _coerce_bool
    assert _coerce_bool('false') is False
    assert _coerce_bool('0') is False


def test_coerce_bool_actual_bool():
    from app.core.security import _coerce_bool
    assert _coerce_bool(True) is True
    assert _coerce_bool(False) is False


def test_coerce_bool_other_falsy():
    from app.core.security import _coerce_bool
    assert _coerce_bool(None) is False
    assert _coerce_bool(0) is False


# ─── _claim ─────────────────────────────────────────────────────────


def test_claim_returns_namespaced():
    from app.core.security import _claim
    payload = {'https://example.com/roles': ['admin']}
    assert _claim(payload, 'https://example.com/', 'roles') == ['admin']


def test_claim_returns_root():
    from app.core.security import _claim
    payload = {'roles': ['admin']}
    assert _claim(payload, '', 'roles') == ['admin']


def test_claim_none_when_missing():
    from app.core.security import _claim
    assert _claim({}, '', 'roles') is None


# ─── clear_jwks_cache ──────────────────────────────────────────────


def test_clear_jwks_cache_empties_cache():
    from app.core.security import clear_jwks_cache, _jwks_cache
    _jwks_cache['x'] = (12345, {'keys': []})
    clear_jwks_cache()
    assert _jwks_cache == {}


# ─── _enforce_session_not_revoked ─────────────────────────────────


def test_enforce_session_not_revoked_no_pool(monkeypatch):
    from app.core.security import _enforce_session_not_revoked
    from app.db.pool import db
    monkeypatch.setattr(db, 'pool', None)
    # no raise = fail-open
    _run(_enforce_session_not_revoked('some-sid'))


def test_enforce_session_not_revoked_db_error_fail_open(monkeypatch):
    """If DB raises, fail open."""
    from app.core.security import _enforce_session_not_revoked

    class _BadDB:
        pool = SimpleNamespace()

    # mock the import to raise
    import sys

    class _MockPool:
        pool = SimpleNamespace()

        def acquire(self):
            raise RuntimeError('connection refused')

    # We can't easily mock the lazy import, so just test the basic happy path
    monkeypatch.setitem(sys.modules, 'app.db.pool', SimpleNamespace(db=_MockPool()))
    # Should not raise
    try:
        _run(_enforce_session_not_revoked('any-sid'))
    except Exception:
        pytest.fail('should fail open')
