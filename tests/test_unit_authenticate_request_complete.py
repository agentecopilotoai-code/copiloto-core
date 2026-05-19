"""Cover authenticate_request happy paths + edge cases in `app/core/security.py`."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from jose import jwt


_SECRET = 'test-secret-key-min-length-16-extra'


def _stub_settings(monkeypatch, **overrides):
    """Replace get_settings to return a stub WITHOUT auth0_domain → forces HS256 path."""
    from app.core import security
    defaults = {
        'jwt_secret': _SECRET,
        'jwt_audience': 'api',
        'jwt_issuer': 'copilotoia',
        'auth0_domain': None,
        'auth0_audience': None,
        'auth0_issuer': None,
        'auth0_claims_namespace': 'https://copilotoia.com/claims/',
        'auth0_jwks_cache_ttl_seconds': 300,
        'mfa_enforcement_enabled': True,
        'service_token': 'test-service-token-min-length-16',
        'service_token_next': None,
    }
    defaults.update(overrides)
    stub = SimpleNamespace(**defaults)
    monkeypatch.setattr(security, 'get_settings', lambda: stub)
    return stub


def _signed_token(claims: dict, secret: str = _SECRET, audience='api', issuer='copilotoia'):
    base = {'aud': audience, 'iss': issuer, **claims}
    return jwt.encode(base, secret, algorithm='HS256')


def _req():
    """Build a minimal Request-like object."""
    return SimpleNamespace(
        state=SimpleNamespace(),
        headers={},
        cookies={},
    )


def test_authenticate_request_service_token_authenticates(monkeypatch):
    """Bearer with service_token → actor_type=service, support_mode=True."""
    from app.core.security import authenticate_request
    _stub_settings(monkeypatch)

    request = _req()

    async def _go():
        await authenticate_request(
            request,
            authorization='Bearer test-service-token-min-length-16',
            x_tenant_id=None,
        )

    asyncio.run(_go())
    assert request.state.actor_type == 'service'
    assert request.state.support_mode is True
    assert request.state.support_mode_source == 'service'


def test_authenticate_request_local_hs256_token_authenticates(monkeypatch):
    """Bearer with locally-signed HS256 token → actor_type=user."""
    from app.core.security import authenticate_request
    _stub_settings(monkeypatch)
    token = _signed_token(
        {'sub': 'user1', 'exp': int((datetime.now(UTC) + timedelta(hours=1)).timestamp())},
    )

    request = _req()

    async def _go():
        await authenticate_request(
            request, authorization=f'Bearer {token}', x_tenant_id=None,
        )

    asyncio.run(_go())
    assert request.state.actor_type == 'user'
    assert request.state.actor_id == 'user1'


def test_authenticate_request_expired_token_raises_401(monkeypatch):
    from app.core.security import authenticate_request
    _stub_settings(monkeypatch)
    token = _signed_token(
        {'sub': 'user1', 'exp': int((datetime.now(UTC) - timedelta(hours=1)).timestamp())},
    )

    request = _req()

    async def _go():
        await authenticate_request(
            request, authorization=f'Bearer {token}', x_tenant_id=None,
        )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_go())
    assert exc_info.value.status_code == 401


def test_authenticate_request_invalid_tenant_claim_raises_401(monkeypatch):
    from app.core.security import authenticate_request
    _stub_settings(monkeypatch)
    token = _signed_token(
        {
            'sub': 'user1',
            'https://copilotoia.com/claims/tenant_id': 'not-a-uuid',
            'exp': int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        },
    )

    request = _req()

    async def _go():
        await authenticate_request(
            request, authorization=f'Bearer {token}', x_tenant_id=None,
        )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_go())
    assert exc_info.value.status_code == 401


def test_authenticate_request_tenant_scope_mismatch_raises_403(monkeypatch):
    from app.core.security import authenticate_request
    _stub_settings(monkeypatch)
    tid1 = uuid4()
    tid2 = uuid4()
    token = _signed_token(
        {
            'sub': 'user1',
            'https://copilotoia.com/claims/tenant_id': str(tid1),
            'https://copilotoia.com/claims/roles': ['admin'],
            'exp': int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        },
    )

    request = _req()

    async def _go():
        await authenticate_request(
            request, authorization=f'Bearer {token}', x_tenant_id=tid2,
        )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(_go())
    assert exc_info.value.status_code == 403


def test_authenticate_request_roles_string_normalized(monkeypatch):
    from app.core.security import authenticate_request
    _stub_settings(monkeypatch)
    token = _signed_token(
        {
            'sub': 'user1',
            'https://copilotoia.com/claims/roles': 'admin',
            'exp': int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        },
    )

    request = _req()

    async def _go():
        await authenticate_request(
            request, authorization=f'Bearer {token}', x_tenant_id=None,
        )

    asyncio.run(_go())
    assert request.state.roles == ['admin']


def test_authenticate_request_with_support_mode_claim(monkeypatch):
    from app.core.security import authenticate_request
    _stub_settings(monkeypatch)
    tid = uuid4()
    token = _signed_token(
        {
            'sub': 'user1',
            'https://copilotoia.com/claims/tenant_id': str(tid),
            'https://copilotoia.com/claims/support_mode': True,
            'https://copilotoia.com/claims/roles': ['admin'],
            'exp': int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        },
    )

    request = _req()

    async def _go():
        await authenticate_request(
            request, authorization=f'Bearer {token}', x_tenant_id=None,
        )

    asyncio.run(_go())
    assert request.state.support_mode is True
    assert request.state.support_mode_source == 'jwt'


def test_authenticate_request_with_cookie_support_mode(monkeypatch):
    """Signed cookie + X-Tenant-Id match → support_mode=True (BUG-008)."""
    from app.core.security import authenticate_request, SUPPORT_MODE_COOKIE_NAME
    from app.core.signed_cookies import pack_signed_payload
    _stub_settings(monkeypatch)
    tid = uuid4()
    token = _signed_token(
        {
            'sub': 'user1',
            'https://copilotoia.com/claims/tenant_id': str(tid),
            'https://copilotoia.com/claims/roles': ['platform_owner'],
            'exp': int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        },
    )

    cookie_value = pack_signed_payload(
        _SECRET,
        {
            'tid': str(tid),
            'sub': 'user1',
            'exp': int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        },
    )

    request = _req()
    request.cookies = {SUPPORT_MODE_COOKIE_NAME: cookie_value}

    async def _go():
        await authenticate_request(
            request, authorization=f'Bearer {token}', x_tenant_id=tid,
        )

    asyncio.run(_go())
    assert request.state.support_mode is True
    assert request.state.support_mode_source == 'cookie'
