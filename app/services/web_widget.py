"""Helpers for the embedded web widget channel (TASK-0039).

The web widget is authenticated by two short-lived tokens:

* ``widget_token`` — opaque secret stored in
  ``.secrets/tenants/{tenant_id}/widget_token``. The site embeds the public
  ``widget.js`` which calls ``/v1/web/chat/start`` with the tenant slug and
  the widget token. The token is provisioned by the tenant admin via the
  Admin Panel and rotated on demand.
* ``session_token`` — short-lived JWT (HS256 with ``SECRET_KEY``) returned
  by ``/v1/web/chat/start``. It carries ``tenant_id``/``conversation_id``
  /``contact_id`` and expires in 24h. Subsequent calls to
  ``/v1/web/chat/{conversation_id}/messages`` validate this token.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from jose import JWTError, jwt


WEB_SESSION_TOKEN_TTL_HOURS = 24
WEB_SESSION_TOKEN_AUDIENCE = 'copilotoia-web-widget'


def generate_widget_token() -> str:
    """Return a high-entropy widget token (URL-safe, ~43 chars)."""
    return secrets.token_urlsafe(32)


def constant_time_equals(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    return hmac.compare_digest(left.encode('utf-8'), right.encode('utf-8'))


def issue_session_token(
    *,
    secret_key: str,
    tenant_id: UUID,
    conversation_id: UUID,
    contact_id: UUID,
    issuer: str,
    ttl_hours: int = WEB_SESSION_TOKEN_TTL_HOURS,
) -> tuple[str, datetime]:
    """Sign a JWT for the widget session. Returns (token, expires_at)."""
    now = datetime.now(UTC)
    exp = now + timedelta(hours=ttl_hours)
    payload: dict[str, Any] = {
        'iss': issuer,
        'aud': WEB_SESSION_TOKEN_AUDIENCE,
        'iat': int(now.timestamp()),
        'exp': int(exp.timestamp()),
        'tenant_id': str(tenant_id),
        'conversation_id': str(conversation_id),
        'contact_id': str(contact_id),
        'kind': 'web_session',
    }
    token = jwt.encode(payload, secret_key, algorithm='HS256')
    return token, exp


def decode_session_token(token: str, *, secret_key: str, issuer: str) -> dict[str, Any]:
    """Validate a session token and return its payload. Raises ValueError on failure."""
    try:
        payload = jwt.decode(
            token,
            secret_key,
            algorithms=['HS256'],
            audience=WEB_SESSION_TOKEN_AUDIENCE,
            issuer=issuer,
        )
    except JWTError as exc:  # noqa: BLE001 — translate to ValueError for callers
        raise ValueError(f'Invalid session token: {exc}') from exc
    if payload.get('kind') != 'web_session':
        raise ValueError('Token is not a web session token')
    return payload


def origin_is_allowed(origin: str | None, allowed_origins: list[str] | None) -> bool:
    """Return True if the request Origin matches the configured allow-list.

    An empty allow-list is treated as "any origin" — convenient for local dev
    or single-page sites that don't reliably set Origin. Production tenants
    should populate ``allowed_origins`` from the Admin Panel.
    """
    if not allowed_origins:
        return True
    if not origin:
        return False
    origin = origin.rstrip('/')
    for candidate in allowed_origins:
        candidate = (candidate or '').strip().rstrip('/')
        if not candidate:
            continue
        if candidate == '*' or candidate == origin:
            return True
    return False


def hash_phone(phone_e164: str) -> bytes:
    """Replicate the SHA-256 phone hash used by the WhatsApp ingestion path."""
    return hashlib.sha256(phone_e164.encode('utf-8')).digest()


def synthesize_web_identity(conversation_seed: str) -> tuple[str, str]:
    """Generate (wa_id, phone_e164) placeholders for a web-only contact.

    Web contacts may not provide a real phone number, but the contacts table
    requires non-null ``wa_id`` and ``phone_e164`` (both tenant-unique). We
    derive a deterministic placeholder from a per-conversation seed so the
    pair is stable for the lifetime of the lead.
    """
    digest = hashlib.sha256(conversation_seed.encode('utf-8')).hexdigest()[:24]
    return f'web:{digest}', f'web:{digest}'


def build_lead_source(
    *,
    channel: str = 'web',
    utm_source: str | None = None,
    utm_medium: str | None = None,
    utm_campaign: str | None = None,
    referrer: str | None = None,
    first_contact_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        'channel': channel,
        'utm_source': utm_source,
        'utm_medium': utm_medium,
        'utm_campaign': utm_campaign,
        'referrer': referrer,
        'first_contact_at': (first_contact_at or datetime.now(UTC)).isoformat(),
    }
