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


MEDIA_MESSAGE_TYPES = {'image', 'audio', 'video'}
SUPPORTED_OUTBOUND_MESSAGE_TYPES = {'text', *MEDIA_MESSAGE_TYPES}


def build_whatsapp_message_payload(
    to: str,
    message_type: str,
    text: str | None = None,
    media_id: str | None = None,
    media_url: str | None = None,
    caption: str | None = None,
) -> dict[str, Any]:
    normalized_type = message_type if message_type in SUPPORTED_OUTBOUND_MESSAGE_TYPES else 'text'
    payload: dict[str, Any] = {
        'messaging_product': 'whatsapp',
        'to': to,
        'type': normalized_type,
    }
    if normalized_type == 'text':
        payload['text'] = {'body': (text or '').strip()}
        return payload

    media_object: dict[str, str] = {}
    if media_id:
        media_object['id'] = media_id.strip()
    elif media_url:
        media_object['link'] = media_url.strip()
    else:
        raise ValueError(f'Outbound WhatsApp {normalized_type} messages require media_id or media_url')

    if normalized_type in {'image', 'video'} and (caption or text):
        media_object['caption'] = (caption or text or '').strip()
    payload[normalized_type] = media_object
    return payload


async def send_whatsapp_message(
    phone_number_id: str,
    to: str,
    message_type: str,
    text: str | None = None,
    delivery_mode: str = 'mock',
    token_ref: str | None = None,
    media_id: str | None = None,
    media_url: str | None = None,
    caption: str | None = None,
) -> dict[str, Any]:
    message_payload = build_whatsapp_message_payload(
        to=to,
        message_type=message_type,
        text=text,
        media_id=media_id,
        media_url=media_url,
        caption=caption,
    )
    settings = get_settings()
    if delivery_mode != 'live':
        return {
            'mocked': True,
            'delivery_mode': 'mock',
            'phone_number_id': phone_number_id,
            'to': to,
            'text': text,
            'message_type': message_payload['type'],
            'message': message_payload,
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
            json=message_payload,
        )
        response.raise_for_status()
        return response.json()


async def send_text_message(
    phone_number_id: str,
    to: str,
    text: str,
    delivery_mode: str = 'mock',
    token_ref: str | None = None,
) -> dict[str, Any]:
    return await send_whatsapp_message(
        phone_number_id=phone_number_id,
        to=to,
        message_type='text',
        text=text,
        delivery_mode=delivery_mode,
        token_ref=token_ref,
    )


async def get_whatsapp_media_info(
    media_id: str,
    token_ref: str | None,
) -> dict[str, Any]:
    settings = get_settings()
    access_token = resolve_secret_ref(token_ref)

    if not meta_token_is_configured(access_token):
        raise RuntimeError(
            'WhatsApp media download requires a real Meta access token.'
        )

    url = f'https://graph.facebook.com/{settings.meta_graph_version}/{media_id}'

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        response = await client.get(
            url,
            headers={'Authorization': f'Bearer {access_token}'},
        )
        response.raise_for_status()
        return response.json()


async def download_whatsapp_media(
    media_id: str,
    token_ref: str | None,
) -> tuple[bytes, str]:
    media_info = await get_whatsapp_media_info(
        media_id=media_id,
        token_ref=token_ref,
    )

    media_url = media_info.get('url')
    if not media_url:
        raise RuntimeError('Meta did not return a media download URL.')

    access_token = resolve_secret_ref(token_ref)

    if not meta_token_is_configured(access_token):
        raise RuntimeError(
            'WhatsApp media download requires a real Meta access token.'
        )

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(
            media_url,
            headers={'Authorization': f'Bearer {access_token}'},
        )
        response.raise_for_status()

        content_type = (
            response.headers.get('content-type')
            or media_info.get('mime_type')
            or 'application/octet-stream'
        )

        return response.content, content_type
