import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jose import jwt
from jose.utils import base64url_encode
from starlette.requests import Request

from app.core.config import get_settings
from app.core.security import authenticate_request, clear_jwks_cache, require_platform_owner


def make_request() -> Request:
    return Request({'type': 'http', 'method': 'GET', 'path': '/', 'headers': []})


@pytest.fixture(autouse=True)
def settings_env(monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://example')
    monkeypatch.setenv('JWT_SECRET', 'local-secret-with-min-length')
    monkeypatch.setenv('SERVICE_TOKEN', 'service-token-with-min-length')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 's3-secret')
    monkeypatch.delenv('AUTH0_DOMAIN', raising=False)
    monkeypatch.delenv('AUTH0_AUDIENCE', raising=False)
    get_settings.cache_clear()
    clear_jwks_cache()
    yield
    get_settings.cache_clear()
    clear_jwks_cache()


def rsa_jwk(private_key, kid: str) -> dict:
    public_numbers = private_key.public_key().public_numbers()
    return {
        'kty': 'RSA',
        'use': 'sig',
        'kid': kid,
        'alg': 'RS256',
        'n': base64url_encode(public_numbers.n.to_bytes(256, 'big')).decode(),
        'e': base64url_encode(public_numbers.e.to_bytes(3, 'big')).decode(),
    }


def rsa_private_key_pem(private_key) -> bytes:
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def test_auth0_rs256_token_sets_tenant_roles_and_support_mode(monkeypatch):
    async def run_test():
        tenant_id = uuid4()
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        namespace = 'https://copilotoia.example/claims'
        monkeypatch.setenv('AUTH0_DOMAIN', 'tenant.us.auth0.com')
        monkeypatch.setenv('AUTH0_AUDIENCE', 'https://api.copilotoia.example')
        monkeypatch.setenv('AUTH0_CLAIMS_NAMESPACE', namespace)
        get_settings.cache_clear()

        async def fake_fetch_auth0_jwks(domain: str, ttl_seconds: int) -> dict:
            assert domain == 'tenant.us.auth0.com'
            assert ttl_seconds == 300
            return {'keys': [rsa_jwk(private_key, 'kid-1')]}

        monkeypatch.setattr('app.core.security._fetch_auth0_jwks', fake_fetch_auth0_jwks)
        token = jwt.encode(
            {
                'iss': 'https://tenant.us.auth0.com/',
                'aud': 'https://api.copilotoia.example',
                'sub': 'auth0|user-1',
                'exp': datetime.now(UTC) + timedelta(minutes=5),
                f'{namespace}/tenant_id': str(tenant_id),
                f'{namespace}/roles': ['admin', 'agent'],
                f'{namespace}/support_mode': False,
            },
            rsa_private_key_pem(private_key),
            algorithm='RS256',
            headers={'kid': 'kid-1'},
        )

        request = make_request()
        await authenticate_request(request, authorization=f'Bearer {token}', x_tenant_id=None)

        assert request.state.actor_type == 'user'
        assert request.state.actor_id == 'auth0|user-1'
        assert request.state.tenant_id == tenant_id
        assert request.state.roles == ['admin', 'agent']
        assert request.state.support_mode is False

    asyncio.run(run_test())


def test_auth0_rejects_token_signed_with_unknown_key(monkeypatch):
    async def run_test():
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        monkeypatch.setenv('AUTH0_DOMAIN', 'tenant.us.auth0.com')
        monkeypatch.setenv('AUTH0_AUDIENCE', 'https://api.copilotoia.example')
        get_settings.cache_clear()

        async def fake_fetch_auth0_jwks(domain: str, ttl_seconds: int) -> dict:
            return {'keys': [rsa_jwk(private_key, 'expected-kid')]}

        monkeypatch.setattr('app.core.security._fetch_auth0_jwks', fake_fetch_auth0_jwks)
        token = jwt.encode(
            {
                'iss': 'https://tenant.us.auth0.com/',
                'aud': 'https://api.copilotoia.example',
                'sub': 'auth0|user-1',
                'exp': datetime.now(UTC) + timedelta(minutes=5),
            },
            rsa_private_key_pem(private_key),
            algorithm='RS256',
            headers={'kid': 'different-kid'},
        )

        with pytest.raises(HTTPException) as exc_info:
            await authenticate_request(make_request(), authorization=f'Bearer {token}', x_tenant_id=None)

        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == 'Unknown token key id'

    asyncio.run(run_test())


def test_authenticate_rejects_x_tenant_id_when_jwt_has_no_tenant_claim():
    async def run_test():
        token = jwt.encode(
            {
                'iss': 'copilotoia-local',
                'aud': 'copilotoia-panel',
                'sub': 'auth0|platform-user',
                'exp': datetime.now(UTC) + timedelta(minutes=5),
                'roles': ['admin'],
            },
            'local-secret-with-min-length',
            algorithm='HS256',
        )

        with pytest.raises(HTTPException) as exc_info:
            await authenticate_request(
                make_request(), authorization=f'Bearer {token}', x_tenant_id=uuid4()
            )

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == 'X-Tenant-Id requires a tenant-scoped token or support_mode'

    asyncio.run(run_test())


def test_service_token_still_authenticates_internal_workloads():
    async def run_test():
        request = make_request()

        await authenticate_request(
            request, authorization='Bearer service-token-with-min-length', x_tenant_id=None
        )

        assert request.state.actor_type == 'service'
        assert request.state.support_mode is True

    asyncio.run(run_test())


def test_platform_owner_rejects_tenant_scoped_owner_token():
    async def run_test():
        request = make_request()
        request.state.actor_type = 'user'
        request.state.tenant_id = uuid4()
        request.state.roles = ['owner']

        with pytest.raises(HTTPException) as exc_info:
            await require_platform_owner(request)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == 'Platform administration requires an unscoped token'

    asyncio.run(run_test())


def test_platform_owner_accepts_unscoped_owner_token():
    async def run_test():
        request = make_request()
        request.state.actor_type = 'user'
        request.state.tenant_id = None
        request.state.roles = ['owner']

        await require_platform_owner(request)

    asyncio.run(run_test())


def test_platform_owner_rejects_service_token():
    async def run_test():
        request = make_request()
        request.state.actor_type = 'service'
        request.state.tenant_id = None
        request.state.roles = []

        with pytest.raises(HTTPException) as exc_info:
            await require_platform_owner(request)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == 'Platform user required'

    asyncio.run(run_test())


def test_platform_owner_rejects_support_role_without_owner():
    async def run_test():
        request = make_request()
        request.state.actor_type = 'user'
        request.state.tenant_id = None
        request.state.roles = ['support']

        with pytest.raises(HTTPException) as exc_info:
            await require_platform_owner(request)

        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == 'owner role is required'

    asyncio.run(run_test())
