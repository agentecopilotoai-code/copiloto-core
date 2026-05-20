"""OAuth flow Instagram para `platform_connections` — TASK-INFLU-014.

Solo Instagram en esta tarea. Otras plataformas (TikTok/YouTube/...)
quedan como sub-tareas separadas.

Seguridad:
- State firmado HMAC-SHA256 con `settings.jwt_secret` (anti-CSRF).
  El state se construye con el persona_id + nonce aleatorio + timestamp;
  TTL 10 min.
- Tokens nunca en logs; persisten en `app.platform_secrets` opaco. Solo
  el `secret_ref` se guarda en `platform_connections`.
- El callback NO acepta state expirado ni con HMAC inválido (403).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets as _secrets
import time
from typing import Final
from uuid import UUID

logger = logging.getLogger(__name__)


STATE_TTL_SECONDS: Final[int] = 600  # 10 min


def build_oauth_state(*, persona_id: UUID, secret: str) -> str:
    """Construye un state firmado HMAC-SHA256.

    Formato: ``<persona_id>:<nonce>:<ts>:<hmac>`` donde el hmac firma
    los 3 primeros campos concatenados con `:`.
    """
    nonce = _secrets.token_urlsafe(16)
    ts = str(int(time.time()))
    payload = f'{persona_id}:{nonce}:{ts}'
    mac = hmac.new(
        secret.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256,
    ).hexdigest()
    return f'{payload}:{mac}'


def verify_oauth_state(
    *, state: str, secret: str, expected_persona_id: UUID | None = None,
) -> UUID:
    """Verifica un state recibido en el callback.

    Returns: el persona_id codificado en el state.
    Raises: ``ValueError`` si el HMAC no matchea, el state está expirado,
            o (si se pasa) el persona_id no coincide.
    """
    parts = state.split(':')
    if len(parts) != 4:
        raise ValueError('malformed state')
    persona_id_s, nonce, ts_s, mac_got = parts
    payload = f'{persona_id_s}:{nonce}:{ts_s}'
    mac_expected = hmac.new(
        secret.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(mac_got, mac_expected):
        raise ValueError('state HMAC mismatch')

    try:
        ts = int(ts_s)
    except ValueError as exc:
        raise ValueError('state timestamp not int') from exc
    now = int(time.time())
    if now - ts > STATE_TTL_SECONDS:
        raise ValueError(f'state expired ({now - ts}s > {STATE_TTL_SECONDS}s)')

    try:
        persona_id = UUID(persona_id_s)
    except ValueError as exc:
        raise ValueError('state persona_id not UUID') from exc

    if expected_persona_id is not None and persona_id != expected_persona_id:
        raise ValueError('state persona_id mismatch')

    return persona_id


# ─── Meta OAuth URL builders (Instagram Basic Display) ─────────────────────


INSTAGRAM_AUTHORIZE_URL: Final[str] = 'https://api.instagram.com/oauth/authorize'
INSTAGRAM_TOKEN_URL: Final[str] = 'https://api.instagram.com/oauth/access_token'
INSTAGRAM_LONG_LIVED_TOKEN_URL: Final[str] = (
    'https://graph.instagram.com/access_token'
)
INSTAGRAM_REFRESH_URL: Final[str] = 'https://graph.instagram.com/refresh_access_token'

DEFAULT_SCOPES: Final[tuple[str, ...]] = (
    'user_profile',
    'user_media',
    'instagram_basic',
    'instagram_content_publish',
)


def build_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    scopes: tuple[str, ...] = DEFAULT_SCOPES,
) -> str:
    """Construye la URL de autorización de Meta a la que se redirige
    el usuario para que apruebe el OAuth scope."""
    from urllib.parse import urlencode
    params = {
        'client_id': client_id,
        'redirect_uri': redirect_uri,
        'scope': ','.join(scopes),
        'response_type': 'code',
        'state': state,
    }
    return f'{INSTAGRAM_AUTHORIZE_URL}?{urlencode(params)}'


__all__ = [
    'STATE_TTL_SECONDS',
    'INSTAGRAM_AUTHORIZE_URL',
    'INSTAGRAM_TOKEN_URL',
    'INSTAGRAM_LONG_LIVED_TOKEN_URL',
    'INSTAGRAM_REFRESH_URL',
    'DEFAULT_SCOPES',
    'build_oauth_state',
    'verify_oauth_state',
    'build_authorize_url',
]
