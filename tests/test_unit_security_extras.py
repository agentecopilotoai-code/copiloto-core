"""Pure-helper tests for `app/core/security.py`.

Covers the helpers that don't need a full request lifecycle:
_service_token_match, _claim, _coerce_bool, _extract_mfa_verified,
_normalize_auth0_domain, _auth0_issuer, _select_jwk, _has_role,
has_jwt_role, _derive_session_id, clear_jwks_cache.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from types import SimpleNamespace


# ───────── _service_token_match ──────────────────────────────────────────


def test_service_token_match_empty_token():
    from app.core.security import _service_token_match
    settings = SimpleNamespace(service_token='abc', service_token_next='def')
    assert _service_token_match('', settings) is False


def test_service_token_match_current():
    from app.core.security import _service_token_match
    settings = SimpleNamespace(service_token='token-current', service_token_next=None)
    assert _service_token_match('token-current', settings) is True


def test_service_token_match_next_during_rotation():
    from app.core.security import _service_token_match
    settings = SimpleNamespace(
        service_token='token-current', service_token_next='token-next',
    )
    assert _service_token_match('token-next', settings) is True


def test_service_token_match_wrong_token():
    from app.core.security import _service_token_match
    settings = SimpleNamespace(service_token='abc', service_token_next='def')
    assert _service_token_match('wrong', settings) is False


def test_service_token_match_both_unset():
    from app.core.security import _service_token_match
    settings = SimpleNamespace(service_token=None, service_token_next=None)
    assert _service_token_match('anything', settings) is False


# ───────── _claim ────────────────────────────────────────────────────────


def test_claim_namespaced_with_trailing_slash():
    from app.core.security import _claim
    payload = {'https://api.copilotoia.com/tenant_id': 'tid-1'}
    assert _claim(payload, 'https://api.copilotoia.com/', 'tenant_id') == 'tid-1'


def test_claim_namespaced_no_trailing_slash():
    from app.core.security import _claim
    payload = {'https://api.copilotoia.com/tenant_id': 'tid-2'}
    assert _claim(payload, 'https://api.copilotoia.com', 'tenant_id') == 'tid-2'


def test_claim_fallback_to_bare_name():
    from app.core.security import _claim
    payload = {'tenant_id': 'tid-3'}
    assert _claim(payload, 'https://api.copilotoia.com/', 'tenant_id') == 'tid-3'


def test_claim_missing_returns_none():
    from app.core.security import _claim
    assert _claim({}, 'ns', 'tenant_id') is None


# ───────── _coerce_bool ──────────────────────────────────────────────────


def test_coerce_bool_native():
    from app.core.security import _coerce_bool
    assert _coerce_bool(True) is True
    assert _coerce_bool(False) is False


def test_coerce_bool_strings():
    from app.core.security import _coerce_bool
    assert _coerce_bool('true') is True
    assert _coerce_bool('TRUE') is True
    assert _coerce_bool('1') is True
    assert _coerce_bool('yes') is True
    assert _coerce_bool('on') is True
    assert _coerce_bool('false') is False
    assert _coerce_bool('0') is False
    assert _coerce_bool('') is False


def test_coerce_bool_other():
    from app.core.security import _coerce_bool
    assert _coerce_bool(1) is True
    assert _coerce_bool(0) is False
    assert _coerce_bool(None) is False
    assert _coerce_bool([]) is False


# ───────── _extract_mfa_verified ─────────────────────────────────────────


def test_extract_mfa_verified_custom_claim():
    from app.core.security import _extract_mfa_verified
    assert _extract_mfa_verified({'mfa_verified': True}) is True
    assert _extract_mfa_verified({'mfa_verified': 'true'}) is True


def test_extract_mfa_verified_namespaced_claim():
    from app.core.security import _extract_mfa_verified
    payload = {'https://api.copilotoia.com/mfa_verified': True}
    assert _extract_mfa_verified(payload, 'https://api.copilotoia.com/') is True


def test_extract_mfa_verified_from_amr():
    from app.core.security import _extract_mfa_verified
    assert _extract_mfa_verified({'amr': ['mfa']}) is True
    assert _extract_mfa_verified({'amr': 'mfa'}) is True
    assert _extract_mfa_verified({'amr': ['pwd']}) is False


def test_extract_mfa_verified_missing():
    from app.core.security import _extract_mfa_verified
    assert _extract_mfa_verified({}) is False
    assert _extract_mfa_verified({'amr': None}) is False


# ───────── _verify_mfa_attestation_header (M63) ───────────────────────

def _build_mfa_assertion(jwt_secret, actor_id, *, ts_ms=None):
    """Helper test — replica lo que hace el BFF para firmar el aserto."""
    import hashlib
    import hmac as _hmac
    import time as _time
    ts_ms = ts_ms if ts_ms is not None else int(_time.time() * 1000)
    payload = f'mfa-verified:{actor_id}:{ts_ms}'
    sig = _hmac.new(jwt_secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return {
        'x-auth-mfa-verified': '1',
        'x-auth-mfa-actor': actor_id,
        'x-auth-mfa-timestamp': str(ts_ms),
        'x-auth-mfa-signature': sig,
    }


def _fake_request(headers):
    from types import SimpleNamespace
    return SimpleNamespace(headers={k.lower(): v for k, v in headers.items()})


def test_mfa_attestation_valid_returns_true(monkeypatch):
    from app.core import security
    monkeypatch.setattr(security, 'get_settings',
                        lambda: type('S', (), {'jwt_secret': 'x' * 32})())
    headers = _build_mfa_assertion('x' * 32, 'auth0|abc')
    req = _fake_request(headers)
    assert security._verify_mfa_attestation_header(req, 'auth0|abc') is True


def test_mfa_attestation_actor_mismatch_returns_false(monkeypatch):
    """Defense: header dice 'auth0|other' pero JWT sub es 'auth0|abc'."""
    from app.core import security
    monkeypatch.setattr(security, 'get_settings',
                        lambda: type('S', (), {'jwt_secret': 'x' * 32})())
    headers = _build_mfa_assertion('x' * 32, 'auth0|other')
    req = _fake_request(headers)
    assert security._verify_mfa_attestation_header(req, 'auth0|abc') is False


def test_mfa_attestation_bad_signature_returns_false(monkeypatch):
    """Spoof: header con signature inválida (firmada con otra key)."""
    from app.core import security
    monkeypatch.setattr(security, 'get_settings',
                        lambda: type('S', (), {'jwt_secret': 'x' * 32})())
    # Atacker firma con otra key
    headers = _build_mfa_assertion('attacker-secret-key', 'auth0|abc')
    req = _fake_request(headers)
    assert security._verify_mfa_attestation_header(req, 'auth0|abc') is False


def test_mfa_attestation_stale_timestamp_returns_false(monkeypatch):
    """Replay: assertion firmada hace 5 minutos."""
    from app.core import security
    monkeypatch.setattr(security, 'get_settings',
                        lambda: type('S', (), {'jwt_secret': 'x' * 32})())
    import time
    old_ts_ms = int(time.time() * 1000) - 5 * 60 * 1000  # hace 5min
    headers = _build_mfa_assertion('x' * 32, 'auth0|abc', ts_ms=old_ts_ms)
    req = _fake_request(headers)
    assert security._verify_mfa_attestation_header(req, 'auth0|abc') is False


def test_mfa_attestation_missing_headers_returns_false(monkeypatch):
    from app.core import security
    monkeypatch.setattr(security, 'get_settings',
                        lambda: type('S', (), {'jwt_secret': 'x' * 32})())
    # Ninguno de los headers
    req = _fake_request({})
    assert security._verify_mfa_attestation_header(req, 'auth0|abc') is False
    # Falta signature
    headers = _build_mfa_assertion('x' * 32, 'auth0|abc')
    del headers['x-auth-mfa-signature']
    req = _fake_request(headers)
    assert security._verify_mfa_attestation_header(req, 'auth0|abc') is False


def test_mfa_attestation_invalid_timestamp_returns_false(monkeypatch):
    from app.core import security
    monkeypatch.setattr(security, 'get_settings',
                        lambda: type('S', (), {'jwt_secret': 'x' * 32})())
    headers = _build_mfa_assertion('x' * 32, 'auth0|abc')
    headers['x-auth-mfa-timestamp'] = 'not-a-number'
    req = _fake_request(headers)
    assert security._verify_mfa_attestation_header(req, 'auth0|abc') is False


def test_mfa_attestation_no_jwt_sub_returns_false(monkeypatch):
    from app.core import security
    monkeypatch.setattr(security, 'get_settings',
                        lambda: type('S', (), {'jwt_secret': 'x' * 32})())
    headers = _build_mfa_assertion('x' * 32, 'auth0|abc')
    req = _fake_request(headers)
    # jwt_sub = None significa request anónima sin JWT — no debe ascender mfa.
    assert security._verify_mfa_attestation_header(req, None) is False


# ───────── _normalize_auth0_domain / _auth0_issuer / _normalize_issuer ──


def test_normalize_auth0_domain_strips_scheme():
    from app.core.security import _normalize_auth0_domain
    assert _normalize_auth0_domain('https://tenant.auth0.com/') == 'tenant.auth0.com'
    assert _normalize_auth0_domain('http://tenant.auth0.com') == 'tenant.auth0.com'
    assert _normalize_auth0_domain('tenant.auth0.com') == 'tenant.auth0.com'


def test_auth0_issuer_default_from_domain():
    from app.core.security import _auth0_issuer
    assert _auth0_issuer('tenant.auth0.com') == 'https://tenant.auth0.com/'


def test_auth0_issuer_with_configured_overrides_domain():
    from app.core.security import _auth0_issuer
    assert _auth0_issuer(
        'tenant.auth0.com', configured_issuer='https://custom-issuer.com'
    ) == 'https://custom-issuer.com/'


def test_normalize_issuer_adds_trailing_slash():
    from app.core.security import _normalize_issuer
    assert _normalize_issuer('https://x.com') == 'https://x.com/'
    assert _normalize_issuer('https://x.com/') == 'https://x.com/'


# ───────── _select_jwk ───────────────────────────────────────────────────


def test_select_jwk_single_key_without_kid():
    from app.core.security import _select_jwk
    jwks = {'keys': [{'kty': 'RSA', 'kid': 'k1'}]}
    assert _select_jwk(jwks, None) == {'kty': 'RSA', 'kid': 'k1'}


def test_select_jwk_finds_by_kid():
    from app.core.security import _select_jwk
    jwks = {'keys': [
        {'kty': 'RSA', 'kid': 'k1'},
        {'kty': 'RSA', 'kid': 'k2'},
    ]}
    assert _select_jwk(jwks, 'k2') == {'kty': 'RSA', 'kid': 'k2'}


def test_select_jwk_unknown_kid_returns_none():
    """M-001: ahora devuelve None — el resolver caller decide si refrescar
    el JWKS (rotation handling) antes de levantar 401."""
    from app.core.security import _select_jwk
    jwks = {'keys': [{'kty': 'RSA', 'kid': 'k1'}]}
    assert _select_jwk(jwks, 'unknown') is None


def test_select_jwk_missing_keys_returns_none():
    from app.core.security import _select_jwk
    assert _select_jwk({}, 'k1') is None


# ───────── _has_role / has_jwt_role ─────────────────────────────────────


def test_has_role_meets_minimum():
    from app.core.security import _has_role
    assert _has_role(['admin'], 'admin') is True
    assert _has_role(['owner'], 'admin') is True
    assert _has_role(['platform_owner'], 'admin') is True
    assert _has_role(['agent'], 'admin') is False
    assert _has_role([], 'admin') is False


def test_has_role_supports_multiple_roles():
    from app.core.security import _has_role
    assert _has_role(['viewer', 'manager'], 'admin') is False
    assert _has_role(['viewer', 'owner'], 'admin') is True


def test_has_role_unknown_role_treated_as_zero():
    from app.core.security import _has_role
    assert _has_role(['support'], 'admin') is False  # BUG-133: support removed


def test_has_jwt_role_is_public_wrapper():
    from app.core.security import has_jwt_role
    assert has_jwt_role(['admin'], 'manager') is True
    assert has_jwt_role(['agent'], 'admin') is False


# ───────── _session_has_privileged_role ──────────────────────────────────


def test_session_has_privileged_role():
    from app.core.security import _session_has_privileged_role
    assert _session_has_privileged_role(['admin']) is True
    assert _session_has_privileged_role(['owner']) is True
    assert _session_has_privileged_role(['platform_owner']) is True
    assert _session_has_privileged_role(['viewer', 'agent']) is False
    assert _session_has_privileged_role([]) is False


# ───────── _derive_session_id ────────────────────────────────────────────


def test_derive_session_id_from_jti():
    from app.core.security import _derive_session_id
    assert _derive_session_id({'jti': 'unique-id-1'}) == 'unique-id-1'


def test_derive_session_id_fallback_to_iat_hash():
    from app.core.security import _derive_session_id
    sid = _derive_session_id({'sub': 'user1', 'iat': 1700000000})
    assert sid is not None
    assert sid.startswith('iat-')
    assert len(sid) == 36  # 'iat-' + 32 hex chars


def test_derive_session_id_returns_none_when_missing_parts():
    from app.core.security import _derive_session_id
    assert _derive_session_id({}) is None
    assert _derive_session_id({'sub': 'u'}) is None
    assert _derive_session_id({'iat': 0}) is None


def test_derive_session_id_deterministic_iat_hash():
    from app.core.security import _derive_session_id
    a = _derive_session_id({'sub': 'u', 'iat': 1700000000})
    b = _derive_session_id({'sub': 'u', 'iat': 1700000000})
    assert a == b


# ───────── clear_jwks_cache ──────────────────────────────────────────────


def test_clear_jwks_cache_resets_cache():
    from app.core.security import _jwks_cache, clear_jwks_cache
    _jwks_cache['fake'] = (999.0, {'keys': []})
    assert 'fake' in _jwks_cache
    clear_jwks_cache()
    assert 'fake' not in _jwks_cache


# ───────── _decode_local_token ──────────────────────────────────────────


def test_decode_local_token_invalid_raises():
    from app.core.security import _decode_local_token
    settings = SimpleNamespace(
        jwt_secret='secret-value-that-is-long-enough',
        jwt_audience='api',
        jwt_issuer='copilotoia',
    )
    with pytest.raises(HTTPException):
        _decode_local_token('not.a.jwt', settings)


def test_decode_local_token_valid_returns_payload():
    from time import time
    from jose import jwt
    from app.core.security import _decode_local_token
    settings = SimpleNamespace(
        jwt_secret='secret-value-that-is-long-enough',
        jwt_audience='api',
        jwt_issuer='copilotoia',
    )
    now = int(time())
    token = jwt.encode(
        {'sub': 'user1', 'aud': 'api', 'iss': 'copilotoia',
         'iat': now, 'exp': now + 3600},
        settings.jwt_secret, algorithm='HS256',
    )
    payload = _decode_local_token(token, settings)
    assert payload['sub'] == 'user1'


# ───────── _decode_auth0_token guard rails ──────────────────────────────


def test_decode_auth0_token_requires_config():
    import asyncio
    from app.core.security import _decode_auth0_token
    settings = SimpleNamespace(auth0_domain='', auth0_audience='')

    async def _go():
        return await _decode_auth0_token('any.token.here', settings)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_go())
    assert 'Auth0 is not configured' in str(exc_info.value.detail)


def test_decode_auth0_token_rejects_malformed():
    import asyncio
    from app.core.security import _decode_auth0_token
    settings = SimpleNamespace(
        auth0_domain='tenant.auth0.com',
        auth0_audience='api',
        auth0_jwks_cache_ttl_seconds=300,
        auth0_issuer=None,
    )

    async def _go():
        return await _decode_auth0_token('not.a.real.token', settings)

    with pytest.raises(HTTPException):
        asyncio.run(_go())


def test_decode_auth0_token_rejects_hs256_alg():
    """RS256 is required for Auth0 path."""
    import asyncio
    from jose import jwt
    from app.core.security import _decode_auth0_token
    settings = SimpleNamespace(
        auth0_domain='tenant.auth0.com',
        auth0_audience='api',
        auth0_jwks_cache_ttl_seconds=300,
        auth0_issuer=None,
    )
    # HS256-signed token (with header.alg = 'HS256')
    token = jwt.encode({'sub': 'x'}, 'secret', algorithm='HS256')

    async def _go():
        return await _decode_auth0_token(token, settings)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_go())
    assert 'algorithm' in str(exc_info.value.detail).lower() \
        or exc_info.value.status_code == 401
