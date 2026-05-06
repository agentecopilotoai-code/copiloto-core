import hashlib
import hmac
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


async def send_text_message(phone_number_id: str, to: str, text: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.meta_access_token or settings.meta_access_token.startswith('change-me'):
        return {'mocked': True, 'phone_number_id': phone_number_id, 'to': to, 'text': text}
    url = f'https://graph.facebook.com/{settings.meta_graph_version}/{phone_number_id}/messages'
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            url,
            headers={'Authorization': f'Bearer {settings.meta_access_token}'},
            json={
                'messaging_product': 'whatsapp',
                'to': to,
                'type': 'text',
                'text': {'body': text},
            },
        )
        response.raise_for_status()
        return response.json()
