import hashlib
import hmac
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings


def _candidate_secret_paths(secret_name: str) -> list[Path]:
    return [
        Path('/app/.secrets') / secret_name,
        Path.cwd() / '.secrets' / secret_name,
    ]


def _secret_name_from_ref(secret_ref: str | None) -> str | None:
    if not secret_ref:
        return None
    ref = secret_ref.strip()
    if not ref.startswith('secrets/'):
        return None
    secret_name = ref.removeprefix('secrets/').strip('/')
    if not secret_name or '..' in Path(secret_name).parts:
        return None
    return secret_name


def resolve_secret_ref(secret_ref: str | None) -> str | None:
    secret_name = _secret_name_from_ref(secret_ref)
    if not secret_name:
        return None
    for path in _candidate_secret_paths(secret_name):
        if path.is_file():
            return path.read_text(encoding='utf-8').strip()
    return None


def normalize_meta_app_secret(app_secret: str | None) -> str | None:
    if not app_secret:
        return None
    cleaned = app_secret.strip()
    if '|' not in cleaned:
        return cleaned
    app_id, secret = cleaned.split('|', 1)
    if app_id.strip() and secret.strip():
        return secret.strip()
    return cleaned


def secret_ref_is_configured(secret_ref: str | None) -> bool:
    return bool(resolve_secret_ref(secret_ref))


def meta_token_is_configured(token: str | None) -> bool:
    return bool(
        token
        and not token.startswith('change-me')
        and not token.startswith('local-mock')
    )


def token_ref_is_configured(token_ref: str | None) -> bool:
    return meta_token_is_configured(resolve_secret_ref(token_ref))


def verify_signature_with_secret(body: bytes, signature: str | None, app_secret: str | None) -> bool:
    normalized_secret = normalize_meta_app_secret(app_secret)
    if not signature or not normalized_secret:
        return False
    expected = 'sha256=' + hmac.new(
        normalized_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)



async def send_text_message(
    phone_number_id: str,
    to: str,
    text: str,
    delivery_mode: str = 'mock',
    token_ref: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    if delivery_mode != 'live':
        return {
            'mocked': True,
            'delivery_mode': 'mock',
            'phone_number_id': phone_number_id,
            'to': to,
            'text': text,
        }
    access_token = resolve_secret_ref(token_ref)
    if not meta_token_is_configured(access_token):
        raise RuntimeError(
            'WhatsApp delivery mode is live, but token_ref did not resolve to a real Meta access token.'
        )
    url = f'https://graph.facebook.com/{settings.meta_graph_version}/{phone_number_id}/messages'
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            url,
            headers={'Authorization': f'Bearer {access_token}'},
            json={
                'messaging_product': 'whatsapp',
                'to': to,
                'type': 'text',
                'text': {'body': text},
            },
        )
        response.raise_for_status()
        return response.json()
