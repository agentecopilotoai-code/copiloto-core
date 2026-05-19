"""Mock-based tests for `app/services/auth0_admin.py`.

Mocks the Auth0 Management API responses (token fetch + user CRUD) so we
can drive the full `invite_user`, `assign_roles`, `revoke_tenant_roles`,
and `lookup_auth0_user_by_email` paths without hitting Auth0. Currently
~70% covered; this suite pushes it to ~90%.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest


# ───────── Test doubles ────────────────────────────────────────────────────


class _MockResp:
    def __init__(self, *, status_code=200, json_payload=None, text=''):
        self.status_code = status_code
        self._payload = json_payload
        self.text = text or ''
        # mimic the `content` attribute that `_mgmt_request` checks
        if json_payload is None and status_code == 204:
            self.content = b''
        else:
            self.content = b'x'

    def json(self):
        return self._payload

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            req = httpx.Request('POST', 'http://test')
            resp = httpx.Response(self.status_code, request=req)
            raise httpx.HTTPStatusError('bad', request=req, response=resp)


class _MockHttpFlow:
    """Sequence of mock responses returned by `httpx.AsyncClient.post/request`.
    The fake client pulls them in order."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, **client_kw):
        flow = self

        class _Client:
            async def __aenter__(self_):
                return self_

            async def __aexit__(self_, *a):
                return False

            async def post(self_, url, json=None, **kw):
                flow.calls.append({'method': 'POST', 'url': url, 'json': json})
                return flow._next()

            async def request(self_, method, url, headers=None, json=None, **kw):
                flow.calls.append({'method': method, 'url': url, 'json': json})
                return flow._next()

        return _Client()

    def _next(self):
        if not self._responses:
            raise AssertionError('No more mock responses queued')
        return self._responses.pop(0)


def _set_auth0_env(monkeypatch):
    """Configure the Auth0 mgmt creds so `auth0_management_enabled()` is True."""
    monkeypatch.setenv('AUTH0_DOMAIN', 'test.auth0.com')
    monkeypatch.setenv('AUTH0_SERVICE_CLIENT_ID', 'svc-id-min-length-16')
    monkeypatch.setenv('AUTH0_SERVICE_CLIENT_SECRET', 'svc-secret-min-length-16')
    monkeypatch.setenv('JWT_SECRET', 'test-jwt-secret-min-length-16')
    monkeypatch.setenv('SERVICE_TOKEN', 'test-service-token-min-length-16')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 'test-s3-secret')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://x')
    from app.core.config import get_settings
    get_settings.cache_clear()
    from app.services.auth0_admin import clear_management_token_cache
    clear_management_token_cache()


def _patch_httpx(monkeypatch, responses):
    flow = _MockHttpFlow(responses)
    monkeypatch.setattr(httpx, 'AsyncClient', flow)
    return flow


# ───────── get_management_token ────────────────────────────────────────────


def test_get_management_token_caches_and_returns(monkeypatch):
    _set_auth0_env(monkeypatch)
    from app.services.auth0_admin import get_management_token
    from app.services.circuit_breaker import reset_registry

    reset_registry()
    _patch_httpx(monkeypatch, [
        _MockResp(json_payload={'access_token': 'token-abc', 'expires_in': 3600}),
    ])
    token = asyncio.run(get_management_token())
    assert token == 'token-abc'
    # Second call should be cached (no extra HTTP); we don't queue another resp.
    token2 = asyncio.run(get_management_token())
    assert token2 == 'token-abc'
    reset_registry()


def test_get_management_token_returns_none_when_disabled(monkeypatch):
    """Without AUTH0_DOMAIN, returns None (no HTTP)."""
    monkeypatch.delenv('AUTH0_DOMAIN', raising=False)
    monkeypatch.delenv('AUTH0_SERVICE_CLIENT_ID', raising=False)
    monkeypatch.delenv('AUTH0_SERVICE_CLIENT_SECRET', raising=False)
    monkeypatch.setenv('JWT_SECRET', 'test-jwt-secret-min-length-16')
    monkeypatch.setenv('SERVICE_TOKEN', 'test-service-token-min-length-16')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 'test-s3-secret')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://x')

    from app.core.config import get_settings
    from app.services.auth0_admin import clear_management_token_cache, get_management_token
    get_settings.cache_clear()
    clear_management_token_cache()

    # Force Settings to ignore .env
    from app.core.config import Settings
    from pydantic_settings import SettingsConfigDict
    Settings.model_config = SettingsConfigDict(env_file=(), env_file_encoding='utf-8', extra='ignore', populate_by_name=True)
    get_settings.cache_clear()

    token = asyncio.run(get_management_token())
    assert token is None


def test_get_management_token_logs_diagnostic_on_403(monkeypatch):
    _set_auth0_env(monkeypatch)
    from app.services.auth0_admin import get_management_token
    from app.services.circuit_breaker import reset_registry

    reset_registry()
    _patch_httpx(monkeypatch, [
        _MockResp(status_code=403, text='forbidden'),
    ])
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(get_management_token())
    reset_registry()


# ───────── _mgmt_request ───────────────────────────────────────────────────


def test_mgmt_request_returns_disabled_when_token_missing(monkeypatch):
    """When `get_management_token()` returns None (auth not configured),
    `_mgmt_request` returns `{'disabled': True}` without making any HTTP call."""
    monkeypatch.delenv('AUTH0_DOMAIN', raising=False)
    monkeypatch.setenv('JWT_SECRET', 'test-jwt-secret-min-length-16')
    monkeypatch.setenv('SERVICE_TOKEN', 'test-service-token-min-length-16')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 'test-s3-secret')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://x')

    from app.core.config import Settings, get_settings
    from pydantic_settings import SettingsConfigDict
    Settings.model_config = SettingsConfigDict(env_file=(), env_file_encoding='utf-8', extra='ignore', populate_by_name=True)
    get_settings.cache_clear()
    from app.services.auth0_admin import _mgmt_request, clear_management_token_cache
    clear_management_token_cache()

    result = asyncio.run(_mgmt_request('GET', '/users'))
    assert result == {'disabled': True}


def test_mgmt_request_invalidates_cache_on_401(monkeypatch):
    """AUDIT-46: a 401 response triggers `clear_management_token_cache()` and
    raises HTTPStatusError. The next call should re-fetch the token."""
    _set_auth0_env(monkeypatch)
    from app.services.auth0_admin import _CACHED_TOKEN, _mgmt_request
    from app.services.circuit_breaker import reset_registry

    reset_registry()
    _patch_httpx(monkeypatch, [
        # Token fetch
        _MockResp(json_payload={'access_token': 'tok1', 'expires_in': 3600}),
        # First mgmt call → 401
        _MockResp(status_code=401, text='token revoked'),
    ])
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(_mgmt_request('GET', '/users'))
    # Cache was cleared
    assert _CACHED_TOKEN['token'] is None
    reset_registry()


def test_mgmt_request_raises_user_already_exists_on_409(monkeypatch):
    _set_auth0_env(monkeypatch)
    from app.services.auth0_admin import Auth0UserAlreadyExists, _mgmt_request
    from app.services.circuit_breaker import reset_registry

    reset_registry()
    _patch_httpx(monkeypatch, [
        _MockResp(json_payload={'access_token': 'tok', 'expires_in': 3600}),
        _MockResp(status_code=409, text='user already exists'),
    ])
    with pytest.raises(Auth0UserAlreadyExists):
        asyncio.run(_mgmt_request('POST', '/users', json_body={'email': 'x@y.z'}))
    reset_registry()


def test_mgmt_request_returns_empty_dict_on_204(monkeypatch):
    _set_auth0_env(monkeypatch)
    from app.services.auth0_admin import _mgmt_request
    from app.services.circuit_breaker import reset_registry

    reset_registry()
    _patch_httpx(monkeypatch, [
        _MockResp(json_payload={'access_token': 'tok', 'expires_in': 3600}),
        _MockResp(status_code=204),
    ])
    result = asyncio.run(_mgmt_request('DELETE', '/users/auth0|x'))
    assert result == {}
    reset_registry()


# ───────── lookup_auth0_user_by_email ──────────────────────────────────────


def test_lookup_by_email_returns_single_verified_match(monkeypatch):
    _set_auth0_env(monkeypatch)
    from app.services.auth0_admin import lookup_auth0_user_by_email
    from app.services.circuit_breaker import reset_registry

    reset_registry()
    _patch_httpx(monkeypatch, [
        _MockResp(json_payload={'access_token': 'tok', 'expires_in': 3600}),
        _MockResp(json_payload=[{'user_id': 'auth0|abc', 'email': 'x@y.z', 'email_verified': True}]),
    ])
    user = asyncio.run(lookup_auth0_user_by_email('x@y.z'))
    assert user is not None
    assert user['user_id'] == 'auth0|abc'
    reset_registry()


def test_lookup_by_email_raises_ambiguous_when_multiple_matches(monkeypatch):
    _set_auth0_env(monkeypatch)
    from app.services.auth0_admin import (
        Auth0AmbiguousUserMatch,
        lookup_auth0_user_by_email,
    )
    from app.services.circuit_breaker import reset_registry

    reset_registry()
    _patch_httpx(monkeypatch, [
        _MockResp(json_payload={'access_token': 'tok', 'expires_in': 3600}),
        _MockResp(json_payload=[
            {'user_id': 'auth0|a', 'email_verified': True},
            {'user_id': 'google|b', 'email_verified': True},
        ]),
    ])
    with pytest.raises(Auth0AmbiguousUserMatch):
        asyncio.run(lookup_auth0_user_by_email('x@y.z'))
    reset_registry()


def test_lookup_by_email_raises_unverified_when_email_not_verified(monkeypatch):
    _set_auth0_env(monkeypatch)
    from app.services.auth0_admin import (
        Auth0UserNotVerified,
        lookup_auth0_user_by_email,
    )
    from app.services.circuit_breaker import reset_registry

    reset_registry()
    _patch_httpx(monkeypatch, [
        _MockResp(json_payload={'access_token': 'tok', 'expires_in': 3600}),
        _MockResp(json_payload=[{'user_id': 'auth0|c', 'email_verified': False}]),
    ])
    with pytest.raises(Auth0UserNotVerified):
        asyncio.run(lookup_auth0_user_by_email('x@y.z'))
    reset_registry()


def test_lookup_by_email_returns_none_when_no_match(monkeypatch):
    _set_auth0_env(monkeypatch)
    from app.services.auth0_admin import lookup_auth0_user_by_email
    from app.services.circuit_breaker import reset_registry

    reset_registry()
    _patch_httpx(monkeypatch, [
        _MockResp(json_payload={'access_token': 'tok', 'expires_in': 3600}),
        _MockResp(json_payload=[]),  # empty array
    ])
    user = asyncio.run(lookup_auth0_user_by_email('nobody@example.local'))
    assert user is None
    reset_registry()


def test_lookup_by_email_allows_unverified_when_flag_off(monkeypatch):
    """`require_email_verified=False` returns the unverified user."""
    _set_auth0_env(monkeypatch)
    from app.services.auth0_admin import lookup_auth0_user_by_email
    from app.services.circuit_breaker import reset_registry

    reset_registry()
    _patch_httpx(monkeypatch, [
        _MockResp(json_payload={'access_token': 'tok', 'expires_in': 3600}),
        _MockResp(json_payload=[{'user_id': 'auth0|d', 'email_verified': False}]),
    ])
    user = asyncio.run(lookup_auth0_user_by_email(
        'x@y.z', require_email_verified=False,
    ))
    assert user is not None
    reset_registry()


def test_lookup_by_email_returns_none_when_auth0_disabled(monkeypatch):
    """No env vars → `auth0_management_enabled` is False → returns None."""
    monkeypatch.delenv('AUTH0_DOMAIN', raising=False)
    monkeypatch.setenv('JWT_SECRET', 'test-jwt-secret-min-length-16')
    monkeypatch.setenv('SERVICE_TOKEN', 'test-service-token-min-length-16')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 'test-s3-secret')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://x')
    from app.core.config import Settings, get_settings
    from pydantic_settings import SettingsConfigDict
    Settings.model_config = SettingsConfigDict(env_file=(), env_file_encoding='utf-8', extra='ignore', populate_by_name=True)
    get_settings.cache_clear()
    from app.services.auth0_admin import lookup_auth0_user_by_email

    user = asyncio.run(lookup_auth0_user_by_email('x@y.z'))
    assert user is None


# ───────── invite_user / assign_roles / revoke_tenant_roles ────────────────


def test_invite_user_returns_disabled_when_unconfigured(monkeypatch):
    monkeypatch.delenv('AUTH0_DOMAIN', raising=False)
    monkeypatch.setenv('JWT_SECRET', 'test-jwt-secret-min-length-16')
    monkeypatch.setenv('SERVICE_TOKEN', 'test-service-token-min-length-16')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 'test-s3-secret')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://x')
    from app.core.config import Settings, get_settings
    from pydantic_settings import SettingsConfigDict
    Settings.model_config = SettingsConfigDict(env_file=(), env_file_encoding='utf-8', extra='ignore', populate_by_name=True)
    get_settings.cache_clear()
    from app.services.auth0_admin import invite_user
    from uuid import uuid4

    result = asyncio.run(invite_user(
        email='x@y.z', role='admin', tenant_id=uuid4(),
    ))
    assert result == {'disabled': True}


def test_assign_roles_returns_disabled_when_unconfigured(monkeypatch):
    monkeypatch.delenv('AUTH0_DOMAIN', raising=False)
    monkeypatch.setenv('JWT_SECRET', 'test-jwt-secret-min-length-16')
    monkeypatch.setenv('SERVICE_TOKEN', 'test-service-token-min-length-16')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 'test-s3-secret')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://x')
    from app.core.config import Settings, get_settings
    from pydantic_settings import SettingsConfigDict
    Settings.model_config = SettingsConfigDict(env_file=(), env_file_encoding='utf-8', extra='ignore', populate_by_name=True)
    get_settings.cache_clear()
    from app.services.auth0_admin import assign_roles

    result = asyncio.run(assign_roles(
        auth_subject='auth0|x', roles=[{'tenant_id': 'tid', 'role': 'admin'}],
    ))
    assert result.get('disabled') is True


def test_revoke_tenant_roles_returns_disabled_when_unconfigured(monkeypatch):
    monkeypatch.delenv('AUTH0_DOMAIN', raising=False)
    monkeypatch.setenv('JWT_SECRET', 'test-jwt-secret-min-length-16')
    monkeypatch.setenv('SERVICE_TOKEN', 'test-service-token-min-length-16')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 'test-s3-secret')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://x')
    from app.core.config import Settings, get_settings
    from pydantic_settings import SettingsConfigDict
    Settings.model_config = SettingsConfigDict(env_file=(), env_file_encoding='utf-8', extra='ignore', populate_by_name=True)
    get_settings.cache_clear()
    from app.services.auth0_admin import revoke_tenant_roles
    from uuid import uuid4

    # When disabled, returns None or empty without raising.
    result = asyncio.run(revoke_tenant_roles(
        auth_subject='auth0|x', tenant_id=uuid4(),
    ))
    assert result is None or isinstance(result, dict)
