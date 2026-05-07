import hashlib
import hmac
import os
from pathlib import Path
from typing import Any

import httpx

from app.core.config import get_settings


def verify_signature(body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    settings = get_settings()
    expected = 'sha256=' + hmac.new(
        settings.whatsapp_app_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def meta_token_is_configured(token: str | None) -> bool:
    return bool(
        token
        and not token.startswith('change-me')
        and not token.startswith('local-mock')
    )


def _candidate_secret_paths(secret_name: str) -> list[Path]:
    return [
        Path('/app/.secrets') / secret_name,
        Path.cwd() / '.secrets' / secret_name,
    ]


def resolve_secret_ref(secret_ref: str | None, fallback_env: str | None = None) -> str | None:
    if secret_ref:
        ref = secret_ref.strip()
        if ref.startswith('env:'):
            return os.getenv(ref.removeprefix('env:').strip())
        if ref.startswith('secrets/'):
            secret_name = ref.removeprefix('secrets/').strip('/')
            if not secret_name or '..' in Path(secret_name).parts:
                return None
            for path in _candidate_secret_paths(secret_name):
                if path.is_file():
                    return path.read_text(encoding='utf-8').strip()
            if secret_name == 'meta_access_token' and fallback_env:
                return os.getenv(fallback_env)
            return None
    return os.getenv(fallback_env) if fallback_env else None


def token_ref_is_configured(token_ref: str | None) -> bool:
    return meta_token_is_configured(resolve_secret_ref(token_ref, 'META_ACCESS_TOKEN'))


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
    access_token = resolve_secret_ref(token_ref, 'META_ACCESS_TOKEN')
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
