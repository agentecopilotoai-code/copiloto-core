"""M45.3 — completar cobertura de lines remanentes que no caen en otros suites.

Cubre:
  - app.core.signed_cookies.unpack_signed_payload — invalid JSON branch.
  - app.services.rate_limit.build_rate_limit_middleware — 429 path.
  - app.api.v1.schemas — TENANT_SLUG_PATTERN exporta, _validate_iana_timezone
    con valores raros.
  - app.api.v1.handlers.tenant_signup_handlers — branch sin tz custom.
"""
from __future__ import annotations

import asyncio
import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


# ─── signed_cookies.unpack_signed_payload edge cases ──────────────────────


def test_unpack_signed_payload_empty():
    from app.core.signed_cookies import unpack_signed_payload
    assert unpack_signed_payload('secret', '') is None


def test_unpack_signed_payload_no_separator():
    from app.core.signed_cookies import unpack_signed_payload
    assert unpack_signed_payload('secret', 'noseparator') is None


def test_unpack_signed_payload_invalid_signature():
    from app.core.signed_cookies import unpack_signed_payload
    # raw = base64 valid JSON, signature deliberately wrong
    raw = base64.urlsafe_b64encode(json.dumps({'x': 1}).encode()).decode().rstrip('=')
    assert unpack_signed_payload('secret', f'{raw}.deadbeef') is None


def test_unpack_signed_payload_malformed_json_after_valid_signature():
    """Buggy producer signs garbage bytes — unpack returns None (no 500)."""
    from app.core.signed_cookies import _sign, unpack_signed_payload
    # raw = base64 of non-JSON bytes
    raw = base64.urlsafe_b64encode(b'not json @@@').decode().rstrip('=')
    sig = _sign('secret', raw)
    assert unpack_signed_payload('secret', f'{raw}.{sig}') is None


def test_unpack_signed_payload_happy():
    from app.core.signed_cookies import pack_signed_payload, unpack_signed_payload
    packed = pack_signed_payload('secret', {'k': 'v', 'n': 42})
    out = unpack_signed_payload('secret', packed)
    assert out == {'k': 'v', 'n': 42}


# ─── rate_limit.build_rate_limit_middleware — 429 path ────────────────────


def test_rate_limit_middleware_429():
    from app.services.rate_limit import RateLimiter, build_rate_limit_middleware

    limiter = RateLimiter(default_per_minute=1, webhook_per_minute=10)
    # Force `check` to return (False, 5.0) → 429 con Retry-After.
    limiter.check = AsyncMock(return_value=(False, 5.0))
    mw = build_rate_limit_middleware(limiter)

    req = SimpleNamespace(
        url=SimpleNamespace(path='/v1/health'),
        headers={'x-forwarded-for': '1.2.3.4'},
        client=SimpleNamespace(host='1.2.3.4'),
    )

    async def call_next(r):
        raise AssertionError('should not call next when limited')

    resp = asyncio.run(mw(req, call_next))
    assert resp.status_code == 429
    assert resp.headers['Retry-After'] == '5'


def test_rate_limit_middleware_allowed_passes_through():
    from app.services.rate_limit import RateLimiter, build_rate_limit_middleware

    limiter = RateLimiter(default_per_minute=60, webhook_per_minute=600)
    limiter.check = AsyncMock(return_value=(True, 0))
    mw = build_rate_limit_middleware(limiter)

    sentinel = object()

    async def call_next(r):
        return sentinel

    req = SimpleNamespace(
        url=SimpleNamespace(path='/v1/health'),
        headers={},
        client=SimpleNamespace(host='1.2.3.4'),
    )
    out = asyncio.run(mw(req, call_next))
    assert out is sentinel


def test_rate_limit_middleware_retry_after_min_1():
    """Si retry_after viene <1s, lo ajustamos a 1 para que el header tenga sentido."""
    from app.services.rate_limit import RateLimiter, build_rate_limit_middleware

    limiter = RateLimiter(default_per_minute=60, webhook_per_minute=600)
    limiter.check = AsyncMock(return_value=(False, 0.3))
    mw = build_rate_limit_middleware(limiter)
    req = SimpleNamespace(
        url=SimpleNamespace(path='/v1/health'),
        headers={},
        client=SimpleNamespace(host='1.2.3.4'),
    )

    async def call_next(r):
        return None

    resp = asyncio.run(mw(req, call_next))
    assert resp.headers['Retry-After'] == '1'


# ─── tenant_signup_handlers: locale fallback path ─────────────────────────


def test_tenant_signup_locale_fallback(monkeypatch):
    """Si `profile_for(country_code)` levanta KeyError/AttributeError,
    cae al default `America/Bogota`."""
    from app.api.v1.handlers import tenant_signup_handlers as tsh
    from app.api.v1.schemas import TenantCreate
    from uuid import uuid4

    # locale_service.profile_for levanta KeyError
    monkeypatch.setattr(
        tsh.locale_service, 'profile_for',
        lambda code: (_ for _ in ()).throw(KeyError(code)),
    )

    uid = uuid4()
    tid = uuid4()

    class C:
        def __init__(self):
            self.calls = []

        async def fetchval(self, sql, *args):
            return None  # no existing membership

        async def fetchrow(self, sql, *args):
            self.calls.append((sql, args))
            if 'insert into app.tenants' in sql:
                # tz argument should be 'America/Bogota' (default fallback)
                assert args[-1] == 'America/Bogota'
                return {
                    'id': tid, 'slug': 'acme', 'legal_name': 'X',
                    'display_name': 'X', 'vertical_code': 'tech',
                    'business_type_label': None, 'country_code': 'CO',
                    'timezone': 'America/Bogota', 'status': 'trial',
                    'created_at': None, 'updated_at': None,
                }
            if 'app.users' in sql:
                return {'id': uid}
            return None

        async def execute(self, sql, *args):
            return 'OK'

    req = SimpleNamespace(state=SimpleNamespace(
        actor_id='auth0|u1', email='u@x.co', name='U',
    ))
    payload = TenantCreate(
        slug='acme', legal_name='X', display_name='X',
        vertical_code='tech', country_code='CO',
    )
    result = asyncio.run(tsh.create_own_tenant(payload, req, C()))
    assert result['slug'] == 'acme'


# ─── schemas — TENANT_SLUG_PATTERN export check ───────────────────────────


def test_tenant_slug_pattern_export():
    from app.api.v1.schemas import TENANT_SLUG_PATTERN
    import re
    pat = re.compile(TENANT_SLUG_PATTERN)
    assert pat.match('acme')
    assert pat.match('acme-co')
    assert not pat.match('Acme')      # uppercase
    assert not pat.match('-acme')     # leading dash
    assert not pat.match('acme-')     # trailing dash
    # 'a' technically matches the optional group (which is 0-61 chars).
    # The min-length=2 is enforced via Pydantic Field, not the regex alone.
    assert pat.match('ab')


def test_validate_iana_timezone_branches():
    from app.api.v1.schemas import _validate_iana_timezone
    assert _validate_iana_timezone(None) is None
    assert _validate_iana_timezone('') == ''
    assert _validate_iana_timezone('America/Bogota') == 'America/Bogota'
    with pytest.raises(ValueError):
        _validate_iana_timezone('Not/A/Zone')
    with pytest.raises(ValueError):
        # Non-string input
        _validate_iana_timezone(123)


# ─── service_token_next coercion ──────────────────────────────────────────


def test_empty_service_token_next_normalized_to_none():
    from app.core.config import Settings
    s = Settings(
        database_url='postgresql://x:x@localhost/x',
        jwt_secret='x' * 32,
        service_token='y' * 32,
        s3_secret_access_key='z' * 32,
        service_token_next='   ',
    )
    assert s.service_token_next is None


def test_service_token_next_keeps_value():
    from app.core.config import Settings
    s = Settings(
        database_url='postgresql://x:x@localhost/x',
        jwt_secret='x' * 32,
        service_token='y' * 32,
        s3_secret_access_key='z' * 32,
        service_token_next='valid-rotation-secret-16+',
    )
    assert s.service_token_next == 'valid-rotation-secret-16+'
