"""Tests para `copiloto_core.auth.devices.verify_device_hmac` (Fase 7)."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from copiloto_core.auth.devices import (
    DeviceIdentity,
    HEADER_DEVICE_ID,
    HEADER_DEVICE_SIGNATURE,
    verify_device_hmac,
)


def _make_request(*, headers: dict | None = None, body: bytes = b''):
    """Mock minimal de fastapi.Request."""

    class _Req:
        def __init__(self):
            self.headers = headers or {}
            self._body = body

        async def body(self):
            return self._body

    return _Req()


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()


# ─── happy path ──────────────────────────────────────────────────────────


def test_valid_signature_returns_identity():
    secret = 'top-secret-xyz'
    body = b'{"sensor":1,"value":42}'
    sig = _sign(secret, body)

    async def lookup(did: str) -> str | None:
        assert did == 'device-001'
        return secret

    verifier = verify_device_hmac(lookup)
    req = _make_request(
        headers={
            HEADER_DEVICE_ID: 'device-001',
            HEADER_DEVICE_SIGNATURE: sig,
        },
        body=body,
    )
    identity = asyncio.run(verifier(req))
    assert isinstance(identity, DeviceIdentity)
    assert identity.device_id == 'device-001'


def test_signature_uppercase_hex_accepted():
    """compare_digest debe ser case-insensitive: aceptamos uppercase."""
    secret = 's'
    body = b'x'
    sig = _sign(secret, body).upper()

    async def lookup(did: str) -> str | None:
        return secret

    verifier = verify_device_hmac(lookup)
    req = _make_request(
        headers={HEADER_DEVICE_ID: 'd', HEADER_DEVICE_SIGNATURE: sig},
        body=body,
    )
    identity = asyncio.run(verifier(req))
    assert identity.device_id == 'd'


# ─── missing headers ─────────────────────────────────────────────────────


def test_missing_device_id_raises_401():
    verifier = verify_device_hmac(AsyncMock(return_value='s'))
    req = _make_request(headers={HEADER_DEVICE_SIGNATURE: 'abc'}, body=b'')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(verifier(req))
    assert exc.value.status_code == 401
    assert exc.value.detail['error'] == 'device_id_missing'


def test_missing_signature_raises_401():
    verifier = verify_device_hmac(AsyncMock(return_value='s'))
    req = _make_request(headers={HEADER_DEVICE_ID: 'd'}, body=b'')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(verifier(req))
    assert exc.value.status_code == 401
    assert exc.value.detail['error'] == 'signature_missing'


# ─── invalid identity / signature ────────────────────────────────────────


def test_unknown_device_id_raises_401_generic():
    """Anti-enumeration: device unknown da mismo error que invalid sig."""
    async def lookup(did: str) -> str | None:
        return None  # device no existe

    verifier = verify_device_hmac(lookup)
    req = _make_request(
        headers={HEADER_DEVICE_ID: 'd', HEADER_DEVICE_SIGNATURE: 'aaaa'},
        body=b'',
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(verifier(req))
    assert exc.value.status_code == 401
    assert exc.value.detail['error'] == 'device_unauthorized'


def test_invalid_signature_raises_401_same_error():
    """Mismo error que device unknown — anti-enumeration."""
    async def lookup(did: str) -> str | None:
        return 'real-secret'

    verifier = verify_device_hmac(lookup)
    req = _make_request(
        headers={HEADER_DEVICE_ID: 'd', HEADER_DEVICE_SIGNATURE: 'cafe' * 16},
        body=b'something',
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(verifier(req))
    assert exc.value.status_code == 401
    assert exc.value.detail['error'] == 'device_unauthorized'


def test_signature_with_wrong_body_fails():
    secret = 's'
    sig = _sign(secret, b'original body')

    async def lookup(did: str) -> str | None:
        return secret

    verifier = verify_device_hmac(lookup)
    req = _make_request(
        headers={HEADER_DEVICE_ID: 'd', HEADER_DEVICE_SIGNATURE: sig},
        body=b'tampered body',
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(verifier(req))
    assert exc.value.status_code == 401
    assert exc.value.detail['error'] == 'device_unauthorized'


# ─── custom header names ─────────────────────────────────────────────────


def test_custom_header_names():
    secret = 'k'
    body = b'p'
    sig = _sign(secret, body)

    async def lookup(did: str) -> str | None:
        return secret

    verifier = verify_device_hmac(
        lookup,
        header_device_id='X-My-Device',
        header_signature='X-My-Sig',
    )
    req = _make_request(
        headers={'X-My-Device': 'abc', 'X-My-Sig': sig},
        body=body,
    )
    identity = asyncio.run(verifier(req))
    assert identity.device_id == 'abc'


def test_custom_headers_missing_use_custom_message():
    verifier = verify_device_hmac(
        AsyncMock(return_value='s'),
        header_device_id='X-My-Device',
    )
    req = _make_request(headers={'X-Device-Signature': 'a'}, body=b'')
    with pytest.raises(HTTPException) as exc:
        asyncio.run(verifier(req))
    assert 'X-My-Device' in exc.value.detail['message']
