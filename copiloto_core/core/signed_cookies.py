"""HMAC-signed payload helpers for HTTP-only cookies.

Originally implemented inline in `app/admin/routes.py` for the OAuth state
cookie (`_pack_state` / `_unpack_state` / `_sign`). BUG-008 introduced a
second consumer (`/v1/me/support-mode/{tenant_id}` cookie for opt-in
support mode) so we extracted the primitive here. Both consumers share the
same wire format:

    <base64url(json_payload)>.<base64url(hmac_sha256(secret, base64url(json)))>

The signature uses `hmac.compare_digest` (constant time) so signature
forgery attempts can't time-side-channel the secret. The payload is
opaque JSON — callers must validate the fields they care about (`exp`,
`sub`, scope, etc.) after `unpack_signed_payload` returns the dict.

Use `pack_signed_payload(secret, data)` when emitting; pair with
`unpack_signed_payload(secret, cookie_value)` when reading. The latter
returns `None` for any tampered or malformed input — never raises.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any


def _b64url(data: bytes) -> str:
    """Base64-URL encode without padding (RFC 4648 §5 with `=` stripped)."""
    return base64.urlsafe_b64encode(data).decode('ascii').rstrip('=')


def _sign(secret: str, value: str) -> str:
    """HMAC-SHA256 of `value` under `secret`, base64url-encoded."""
    digest = hmac.new(
        secret.encode('utf-8'),
        value.encode('utf-8'),
        hashlib.sha256,
    ).digest()
    return _b64url(digest)


def pack_signed_payload(secret: str, payload: dict[str, Any]) -> str:
    """Serialize `payload` as a signed cookie value.

    JSON encoding is canonical (no extra whitespace) so the same dict
    always produces the same bytes — required for the signature to match
    on decode.
    """
    raw = _b64url(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
    return f'{raw}.{_sign(secret, raw)}'


def unpack_signed_payload(secret: str, value: str) -> dict[str, Any] | None:
    """Verify the HMAC and decode the payload. Returns `None` on any
    tampering, bad format, or invalid JSON. NEVER raises — caller checks
    for None and rejects the request.
    """
    if not value or '.' not in value:
        return None
    raw, separator, signature = value.partition('.')
    if not separator or not hmac.compare_digest(_sign(secret, raw), signature):
        return None
    padding = '=' * (-len(raw) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(raw + padding))
    except (ValueError, json.JSONDecodeError):
        # Defensive — `_sign` already validated the HMAC so a properly
        # signed value should always decode, but a buggy producer could
        # ship malformed JSON. Treat as "tampered" (None) rather than 500.
        return None
