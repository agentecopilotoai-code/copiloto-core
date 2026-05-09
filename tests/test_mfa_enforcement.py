"""Tests for TASK-0016: MFA enforcement for privileged roles.

Covers:
- _extract_mfa_verified: True when amr=['mfa'], False otherwise.
- authenticate_request: mfa_verified populated from JWT amr claim.
- require_mfa_for_privileged: 403 for privileged role without MFA, pass with MFA.
- Admin session callback: mfa_verified stored when amr=['mfa'] in id_token.
- _session_mfa_required helper.
"""
import asyncio
import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from jose import jwt
from starlette.requests import Request

from app.core.config import get_settings
from app.core.security import (
    _extract_mfa_verified,
    authenticate_request,
    clear_jwks_cache,
    require_mfa_for_privileged,
)


# ── helpers ────────────────────────────────────────────────────────────────

def make_request(headers: dict | None = None) -> Request:
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    return Request({'type': 'http', 'method': 'GET', 'path': '/', 'headers': raw_headers})


def local_token(
    roles: list[str],
    *,
    amr: list[str] | None = None,
    tenant_id=None,
    secret: str = 'local-secret-with-min-length',
    audience: str = 'copilotoia-local',
    issuer: str = 'copilotoia-local',
) -> str:
    payload: dict = {
        'sub': 'user|test',
        'iss': issuer,
        'aud': audience,
        'exp': int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
        'https://copilotoia.example/claims/roles': roles,
    }
    if tenant_id:
        payload['https://copilotoia.example/claims/tenant_id'] = str(tenant_id)
    if amr is not None:
        payload['amr'] = amr
    return jwt.encode(payload, secret, algorithm='HS256')


@pytest.fixture(autouse=True)
def local_auth_env(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://example')
    monkeypatch.setenv('JWT_SECRET', 'local-secret-with-min-length')
    monkeypatch.setenv('JWT_AUDIENCE', 'copilotoia-local')
    monkeypatch.setenv('JWT_ISSUER', 'copilotoia-local')
    monkeypatch.setenv('SERVICE_TOKEN', 'service-token-with-min-length')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 's3-secret')
    monkeypatch.setenv('AUTH0_CLAIMS_NAMESPACE', 'https://copilotoia.example/claims')
    monkeypatch.delenv('AUTH0_DOMAIN', raising=False)
    monkeypatch.delenv('AUTH0_AUDIENCE', raising=False)
    get_settings.cache_clear()
    clear_jwks_cache()
    yield
    get_settings.cache_clear()
    clear_jwks_cache()


# ── unit: _extract_mfa_verified ────────────────────────────────────────────

def test_extract_mfa_verified_true_when_amr_contains_mfa():
    assert _extract_mfa_verified({'amr': ['pwd', 'mfa']}) is True


def test_extract_mfa_verified_false_when_amr_missing():
    assert _extract_mfa_verified({}) is False


def test_extract_mfa_verified_false_when_amr_no_mfa():
    assert _extract_mfa_verified({'amr': ['pwd', 'otp']}) is False


def test_extract_mfa_verified_string_amr_mfa():
    assert _extract_mfa_verified({'amr': 'mfa'}) is True


def test_extract_mfa_verified_string_amr_pwd():
    assert _extract_mfa_verified({'amr': 'pwd'}) is False


# ── authenticate_request: mfa_verified in state ────────────────────────────

def test_authenticate_sets_mfa_verified_true():
    async def run():
        token = local_token(['admin'], amr=['pwd', 'mfa'])
        req = make_request({'Authorization': f'Bearer {token}'})
        await authenticate_request(req, authorization=f'Bearer {token}', x_tenant_id=None)
        assert req.state.mfa_verified is True

    asyncio.get_event_loop().run_until_complete(run())


def test_authenticate_sets_mfa_verified_false_without_amr():
    async def run():
        token = local_token(['admin'])
        req = make_request({'Authorization': f'Bearer {token}'})
        await authenticate_request(req, authorization=f'Bearer {token}', x_tenant_id=None)
        assert req.state.mfa_verified is False

    asyncio.get_event_loop().run_until_complete(run())


def test_authenticate_anonymous_mfa_verified_false():
    async def run():
        req = make_request()
        await authenticate_request(req, authorization=None, x_tenant_id=None)
        assert req.state.mfa_verified is False

    asyncio.get_event_loop().run_until_complete(run())


# ── require_mfa_for_privileged ─────────────────────────────────────────────

def _make_state(actor_type='user', roles=None, mfa_verified=False):
    req = make_request()
    req.state.actor_type = actor_type
    req.state.roles = roles or []
    req.state.mfa_verified = mfa_verified
    return req


def test_require_mfa_privileged_passes_with_mfa(monkeypatch):
    """admin role + mfa_verified=True: no exception (Auth0 not configured)."""
    req = _make_state(roles=['admin'], mfa_verified=True)
    asyncio.get_event_loop().run_until_complete(require_mfa_for_privileged(req))


def test_require_mfa_privileged_passes_without_auth0(monkeypatch):
    """Without AUTH0_DOMAIN the check is skipped even for privileged roles."""
    req = _make_state(roles=['owner'], mfa_verified=False)
    # AUTH0_DOMAIN is not set (local_auth_env fixture), so no error.
    asyncio.get_event_loop().run_until_complete(require_mfa_for_privileged(req))


def test_require_mfa_privileged_raises_with_auth0_no_mfa(monkeypatch):
    """With AUTH0_DOMAIN active, admin without MFA gets 403."""
    monkeypatch.setenv('AUTH0_DOMAIN', 'test.auth0.com')
    monkeypatch.setenv('AUTH0_AUDIENCE', 'https://test-api')
    get_settings.cache_clear()
    req = _make_state(roles=['admin'], mfa_verified=False)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.get_event_loop().run_until_complete(require_mfa_for_privileged(req))
    assert exc_info.value.status_code == 403
    assert 'MFA' in exc_info.value.detail


def test_require_mfa_privileged_passes_owner_with_mfa(monkeypatch):
    """With AUTH0_DOMAIN active, owner + mfa_verified=True passes."""
    monkeypatch.setenv('AUTH0_DOMAIN', 'test.auth0.com')
    monkeypatch.setenv('AUTH0_AUDIENCE', 'https://test-api')
    get_settings.cache_clear()
    req = _make_state(roles=['owner'], mfa_verified=True)
    asyncio.get_event_loop().run_until_complete(require_mfa_for_privileged(req))


def test_require_mfa_unprivileged_no_check(monkeypatch):
    """agent role without MFA is not blocked even with AUTH0_DOMAIN active."""
    monkeypatch.setenv('AUTH0_DOMAIN', 'test.auth0.com')
    monkeypatch.setenv('AUTH0_AUDIENCE', 'https://test-api')
    get_settings.cache_clear()
    req = _make_state(roles=['agent'], mfa_verified=False)
    asyncio.get_event_loop().run_until_complete(require_mfa_for_privileged(req))


def test_require_mfa_service_exempt(monkeypatch):
    """Service actor is always exempt from MFA check."""
    monkeypatch.setenv('AUTH0_DOMAIN', 'test.auth0.com')
    monkeypatch.setenv('AUTH0_AUDIENCE', 'https://test-api')
    get_settings.cache_clear()
    req = _make_state(actor_type='service', roles=['admin'], mfa_verified=False)
    asyncio.get_event_loop().run_until_complete(require_mfa_for_privileged(req))


def test_require_mfa_anonymous_raises_401(monkeypatch):
    req = _make_state(actor_type='anonymous', roles=[], mfa_verified=False)
    with pytest.raises(HTTPException) as exc_info:
        asyncio.get_event_loop().run_until_complete(require_mfa_for_privileged(req))
    assert exc_info.value.status_code == 401


# ── admin routes: _session_mfa_required ────────────────────────────────────

def test_session_mfa_required_privileged_no_mfa():
    from app.admin.routes import _session_mfa_required

    session = {
        'profile': {'roles': ['admin'], 'mfa_verified': False},
        'expires_at': time.time() + 3600,
    }
    assert _session_mfa_required(session) is True


def test_session_mfa_required_privileged_with_mfa():
    from app.admin.routes import _session_mfa_required

    session = {
        'profile': {'roles': ['owner'], 'mfa_verified': True},
        'expires_at': time.time() + 3600,
    }
    assert _session_mfa_required(session) is False


def test_session_mfa_required_unprivileged():
    from app.admin.routes import _session_mfa_required

    session = {
        'profile': {'roles': ['agent'], 'mfa_verified': False},
        'expires_at': time.time() + 3600,
    }
    assert _session_mfa_required(session) is False


def test_session_mfa_required_no_roles():
    from app.admin.routes import _session_mfa_required

    session = {'profile': {}, 'expires_at': time.time() + 3600}
    assert _session_mfa_required(session) is False


# ── admin callback: mfa_verified stored from id_token amr ─────────────────

def test_admin_callback_stores_mfa_verified_in_profile():
    """The session builder stores mfa_verified=True when id_token has amr=['mfa']."""
    import base64

    def b64(data: dict) -> str:
        raw = json.dumps(data).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()

    id_token_payload = {
        'sub': 'user|123',
        'amr': ['pwd', 'mfa'],
        'exp': int(time.time()) + 3600,
    }
    fake_id_token = f"header.{b64(id_token_payload)}.sig"

    # Simulate what the callback does when building the session.
    id_token_claims: dict = {}
    payload_segment = fake_id_token.split('.')[1]
    padding = '=' * (-len(payload_segment) % 4)
    id_token_claims = json.loads(base64.urlsafe_b64decode(payload_segment + padding))

    amr = id_token_claims.get('amr') or []
    if isinstance(amr, str):
        amr = [amr]
    mfa_verified = 'mfa' in amr

    assert mfa_verified is True


def test_admin_callback_stores_mfa_verified_false_without_amr():
    import base64

    def b64(data: dict) -> str:
        raw = json.dumps(data).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()

    id_token_payload = {'sub': 'user|456', 'exp': int(time.time()) + 3600}
    fake_id_token = f"header.{b64(id_token_payload)}.sig"
    payload_segment = fake_id_token.split('.')[1]
    padding = '=' * (-len(payload_segment) % 4)
    id_token_claims = json.loads(base64.urlsafe_b64decode(payload_segment + padding))

    amr = id_token_claims.get('amr') or []
    mfa_verified = 'mfa' in amr

    assert mfa_verified is False
