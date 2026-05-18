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
SUPPORTED_OUTBOUND_MESSAGE_TYPES = {'text', 'interactive', 'template', *MEDIA_MESSAGE_TYPES}

MAX_INTERACTIVE_BUTTONS = 3
MAX_INTERACTIVE_LIST_ROWS = 10


def build_interactive_button_payload(
    body_text: str,
    buttons: list[dict[str, str]],
    header_text: str | None = None,
    footer_text: str | None = None,
) -> dict[str, Any]:
    if not body_text or not body_text.strip():
        raise ValueError('Interactive button messages require body_text')
    if not buttons:
        raise ValueError('Interactive button messages require at least one button')
    if len(buttons) > MAX_INTERACTIVE_BUTTONS:
        raise ValueError(
            f'WhatsApp interactive button messages allow up to {MAX_INTERACTIVE_BUTTONS} buttons'
        )
    reply_buttons: list[dict[str, Any]] = []
    for index, button in enumerate(buttons):
        button_id = (button.get('id') or '').strip()
        title = (button.get('title') or '').strip()
        if not button_id or not title:
            raise ValueError('Each interactive button requires non-empty id and title')
        if len(title) > 20:
            raise ValueError('Interactive button titles must be 20 characters or fewer')
        reply_buttons.append({
            'type': 'reply',
            'reply': {'id': button_id, 'title': title},
        })
        if index >= MAX_INTERACTIVE_BUTTONS - 1:
            break
    interactive: dict[str, Any] = {
        'type': 'button',
        'body': {'text': body_text.strip()},
        'action': {'buttons': reply_buttons},
    }
    if header_text and header_text.strip():
        interactive['header'] = {'type': 'text', 'text': header_text.strip()}
    if footer_text and footer_text.strip():
        interactive['footer'] = {'text': footer_text.strip()}
    return interactive


def build_interactive_list_payload(
    body_text: str,
    button_label: str,
    sections: list[dict[str, Any]],
    header_text: str | None = None,
    footer_text: str | None = None,
) -> dict[str, Any]:
    if not body_text or not body_text.strip():
        raise ValueError('Interactive list messages require body_text')
    if not button_label or not button_label.strip():
        raise ValueError('Interactive list messages require a button_label')
    if not sections:
        raise ValueError('Interactive list messages require at least one section')
    normalized_sections: list[dict[str, Any]] = []
    total_rows = 0
    for section in sections:
        rows = section.get('rows') or []
        if not rows:
            raise ValueError('Each interactive list section requires at least one row')
        normalized_rows = []
        for row in rows:
            row_id = (row.get('id') or '').strip()
            title = (row.get('title') or '').strip()
            if not row_id or not title:
                raise ValueError('Each interactive list row requires non-empty id and title')
            normalized_row: dict[str, str] = {'id': row_id, 'title': title}
            description = (row.get('description') or '').strip()
            if description:
                normalized_row['description'] = description
            normalized_rows.append(normalized_row)
            total_rows += 1
            if total_rows >= MAX_INTERACTIVE_LIST_ROWS:
                break
        section_payload: dict[str, Any] = {'rows': normalized_rows}
        section_title = (section.get('title') or '').strip()
        if section_title:
            section_payload['title'] = section_title
        normalized_sections.append(section_payload)
        if total_rows >= MAX_INTERACTIVE_LIST_ROWS:
            break
    if total_rows > MAX_INTERACTIVE_LIST_ROWS:
        raise ValueError(
            f'WhatsApp interactive list messages allow up to {MAX_INTERACTIVE_LIST_ROWS} rows'
        )
    interactive: dict[str, Any] = {
        'type': 'list',
        'body': {'text': body_text.strip()},
        'action': {
            'button': button_label.strip(),
            'sections': normalized_sections,
        },
    }
    if header_text and header_text.strip():
        interactive['header'] = {'type': 'text', 'text': header_text.strip()}
    if footer_text and footer_text.strip():
        interactive['footer'] = {'text': footer_text.strip()}
    return interactive


def build_template_message_payload(
    template_name: str,
    locale: str,
    variables: dict[str, Any] | None = None,
    components: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Construye el bloque ``template`` que va dentro de un mensaje WhatsApp.

    ``variables`` mapea ``"1"`` → ``"valor"`` para el body por simplicidad y se
    convierte en un único component ``body`` con parámetros ordenados. Si se
    quieren componentes más complejos (header con imagen, botones, etc.), se
    puede pasar ``components`` directamente respetando el shape de Meta.
    """
    if not template_name:
        raise ValueError('template_name is required')
    template_block: dict[str, Any] = {
        'name': template_name,
        'language': {'code': locale or 'es'},
    }
    if components:
        template_block['components'] = components
    elif variables:
        ordered_keys = sorted(variables.keys(), key=lambda k: int(k) if str(k).isdigit() else 0)
        parameters = [
            {'type': 'text', 'text': str(variables[key])} for key in ordered_keys
        ]
        template_block['components'] = [{'type': 'body', 'parameters': parameters}]
    return template_block


def build_whatsapp_message_payload(
    to: str,
    message_type: str,
    text: str | None = None,
    media_id: str | None = None,
    media_url: str | None = None,
    caption: str | None = None,
    interactive_payload: dict[str, Any] | None = None,
    template_payload: dict[str, Any] | None = None,
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

    if normalized_type == 'interactive':
        if not isinstance(interactive_payload, dict) or not interactive_payload:
            raise ValueError(
                'Outbound WhatsApp interactive messages require an interactive_payload dict'
            )
        payload['interactive'] = interactive_payload
        return payload

    if normalized_type == 'template':
        if not isinstance(template_payload, dict) or not template_payload:
            raise ValueError(
                'Outbound WhatsApp template messages require a template_payload dict'
            )
        payload['template'] = template_payload
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


def parse_interactive_reply(message: dict[str, Any]) -> dict[str, Any] | None:
    """Extract id/title/type from an inbound interactive WhatsApp message.

    Returns None if the message is not interactive or lacks the expected shape.
    """
    if not isinstance(message, dict):
        return None
    interactive = message.get('interactive')
    if not isinstance(interactive, dict):
        return None
    reply_type = interactive.get('type')
    if reply_type == 'button_reply':
        reply = interactive.get('button_reply')
    elif reply_type == 'list_reply':
        reply = interactive.get('list_reply')
    else:
        return None
    if not isinstance(reply, dict):
        return None
    reply_id = reply.get('id')
    title = reply.get('title')
    if not isinstance(reply_id, str) or not isinstance(title, str):
        return None
    parsed: dict[str, Any] = {
        'interactive_type': reply_type,
        'interactive_id': reply_id,
        'interactive_title': title,
    }
    description = reply.get('description')
    if isinstance(description, str) and description:
        parsed['interactive_description'] = description
    return parsed


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
    interactive_payload: dict[str, Any] | None = None,
    template_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    message_payload = build_whatsapp_message_payload(
        to=to,
        message_type=message_type,
        text=text,
        media_id=media_id,
        media_url=media_url,
        caption=caption,
        interactive_payload=interactive_payload,
        template_payload=template_payload,
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


async def send_interactive_buttons(
    phone_number_id: str,
    to: str,
    body_text: str,
    buttons: list[dict[str, str]],
    *,
    header_text: str | None = None,
    footer_text: str | None = None,
    delivery_mode: str = 'mock',
    token_ref: str | None = None,
) -> dict[str, Any]:
    interactive_payload = build_interactive_button_payload(
        body_text=body_text,
        buttons=buttons,
        header_text=header_text,
        footer_text=footer_text,
    )
    return await send_whatsapp_message(
        phone_number_id=phone_number_id,
        to=to,
        message_type='interactive',
        text=body_text,
        delivery_mode=delivery_mode,
        token_ref=token_ref,
        interactive_payload=interactive_payload,
    )


async def send_whatsapp_template(
    phone_number_id: str,
    to: str,
    template_name: str,
    *,
    locale: str = 'es',
    variables: dict[str, Any] | None = None,
    components: list[dict[str, Any]] | None = None,
    delivery_mode: str = 'mock',
    token_ref: str | None = None,
) -> dict[str, Any]:
    template_payload = build_template_message_payload(
        template_name=template_name,
        locale=locale,
        variables=variables,
        components=components,
    )
    return await send_whatsapp_message(
        phone_number_id=phone_number_id,
        to=to,
        message_type='template',
        delivery_mode=delivery_mode,
        token_ref=token_ref,
        template_payload=template_payload,
    )


async def send_interactive_list(
    phone_number_id: str,
    to: str,
    body_text: str,
    button_label: str,
    sections: list[dict[str, Any]],
    *,
    header_text: str | None = None,
    footer_text: str | None = None,
    delivery_mode: str = 'mock',
    token_ref: str | None = None,
) -> dict[str, Any]:
    interactive_payload = build_interactive_list_payload(
        body_text=body_text,
        button_label=button_label,
        sections=sections,
        header_text=header_text,
        footer_text=footer_text,
    )
    return await send_whatsapp_message(
        phone_number_id=phone_number_id,
        to=to,
        message_type='interactive',
        text=body_text,
        delivery_mode=delivery_mode,
        token_ref=token_ref,
        interactive_payload=interactive_payload,
    )


def template_components_for_meta(components: dict[str, Any] | list | None) -> list[dict[str, Any]]:
    """Normalize a tenant-side ``components`` jsonb into Meta's array shape.

    Supports two input shapes:
    - ``{"header": {"type": "text", "text": "Hola"}, "body": {"text": "..."}, "footer": ..., "buttons": [...]}``
    - A list already in Meta's shape — returned unchanged after sanitization.
    """
    if isinstance(components, list):
        return [item for item in components if isinstance(item, dict)]
    if not isinstance(components, dict):
        return []
    out: list[dict[str, Any]] = []
    header = components.get('header')
    if isinstance(header, dict) and header.get('text'):
        out.append({
            'type': 'HEADER',
            'format': (header.get('format') or 'TEXT').upper(),
            'text': str(header['text']),
        })
    body = components.get('body')
    if isinstance(body, dict) and body.get('text'):
        out.append({'type': 'BODY', 'text': str(body['text'])})
    footer = components.get('footer')
    if isinstance(footer, dict) and footer.get('text'):
        out.append({'type': 'FOOTER', 'text': str(footer['text'])})
    buttons = components.get('buttons')
    if isinstance(buttons, list) and buttons:
        normalized_buttons = [
            {
                'type': (button.get('type') or 'QUICK_REPLY').upper(),
                'text': str(button.get('text') or '').strip(),
            }
            for button in buttons
            if isinstance(button, dict) and button.get('text')
        ]
        if normalized_buttons:
            out.append({'type': 'BUTTONS', 'buttons': normalized_buttons})
    return out


async def submit_template_to_meta(
    waba_id: str,
    token_ref: str | None,
    *,
    name: str,
    locale: str,
    category: str,
    components: dict[str, Any] | list,
) -> dict[str, Any]:
    """POST a template to the Meta Graph API for review."""
    access_token = resolve_secret_ref(token_ref)
    if not meta_token_is_configured(access_token):
        raise RuntimeError(
            'WhatsApp template submission requires a real Meta access token.'
        )
    settings = get_settings()
    url = f'https://graph.facebook.com/{settings.meta_graph_version}/{waba_id}/message_templates'
    payload = {
        'name': name,
        'language': locale or 'es',
        'category': (category or 'utility').upper(),
        'components': template_components_for_meta(components),
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            url,
            headers={'Authorization': f'Bearer {access_token}'},
            json=payload,
        )
        response.raise_for_status()
        return response.json()


async def fetch_templates_from_meta(
    waba_id: str,
    token_ref: str | None,
) -> list[dict[str, Any]]:
    access_token = resolve_secret_ref(token_ref)
    if not meta_token_is_configured(access_token):
        raise RuntimeError(
            'WhatsApp template sync requires a real Meta access token.'
        )
    settings = get_settings()
    url = f'https://graph.facebook.com/{settings.meta_graph_version}/{waba_id}/message_templates'
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            url,
            headers={'Authorization': f'Bearer {access_token}'},
            params={'limit': 200},
        )
        response.raise_for_status()
        data = response.json()
    items = data.get('data') if isinstance(data, dict) else None
    return items if isinstance(items, list) else []


async def delete_template_from_meta(
    waba_id: str,
    token_ref: str | None,
    *,
    template_name: str,
) -> None:
    access_token = resolve_secret_ref(token_ref)
    if not meta_token_is_configured(access_token):
        raise RuntimeError(
            'WhatsApp template deletion requires a real Meta access token.'
        )
    settings = get_settings()
    url = f'https://graph.facebook.com/{settings.meta_graph_version}/{waba_id}/message_templates'
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.delete(
            url,
            headers={'Authorization': f'Bearer {access_token}'},
            params={'name': template_name},
        )
        response.raise_for_status()


async def get_whatsapp_media_info(
    media_id: str,
    token_ref: str | None,
) -> dict[str, Any]:
    from urllib.parse import quote  # noqa: PLC0415

    from app.services.url_guard import (  # noqa: PLC0415
        META_MEDIA_HOST_ALLOWLIST,
        UnsafeOutboundURLError,
        assert_whatsapp_media_id,
        validate_outbound_url,
    )

    settings = get_settings()
    access_token = resolve_secret_ref(token_ref)

    if not meta_token_is_configured(access_token):
        raise RuntimeError(
            'WhatsApp media download requires a real Meta access token.'
        )

    # BUG19: validate the media_id before interpolating it into the Graph URL.
    # Meta IDs are pure numeric; anything else is a crafted payload trying to
    # escape the URL path (e.g. ``../foo`` or ``123?token=...``).
    safe_media_id = quote(assert_whatsapp_media_id(media_id), safe='')

    url = f'https://graph.facebook.com/{settings.meta_graph_version}/{safe_media_id}'

    # The Graph URL is platform-controlled but we validate it anyway so the
    # follow-redirects=False / host-allowlist guard is applied consistently.
    try:
        validated_graph = validate_outbound_url(
            url,
            host_allowlist=META_MEDIA_HOST_ALLOWLIST,
        )
    except UnsafeOutboundURLError as exc:
        raise RuntimeError(f'Graph URL failed validation: {exc}') from exc

    async with httpx.AsyncClient(timeout=15, follow_redirects=False) as client:
        response = await client.get(
            validated_graph.canonical,
            headers={'Authorization': f'Bearer {access_token}'},
        )
        response.raise_for_status()
        return response.json()


async def download_whatsapp_media(
    media_id: str,
    token_ref: str | None,
) -> tuple[bytes, str]:
    from app.services.url_guard import (  # noqa: PLC0415
        META_MEDIA_HOST_ALLOWLIST,
        UnsafeOutboundURLError,
        validate_outbound_url,
    )

    media_info = await get_whatsapp_media_info(
        media_id=media_id,
        token_ref=token_ref,
    )

    media_url = media_info.get('url')
    if not media_url:
        raise RuntimeError('Meta did not return a media download URL.')

    # BUG19 defense: even though the URL came from the Graph response, treat it
    # as untrusted (the upstream API could be compromised or DNS-poisoned).
    # Without this gate the bearer token is leaked to whichever host Graph
    # decides to return.
    try:
        validated_media = validate_outbound_url(
            media_url,
            host_allowlist=META_MEDIA_HOST_ALLOWLIST,
        )
    except UnsafeOutboundURLError as exc:
        raise RuntimeError(f'Meta media URL failed validation: {exc}') from exc

    access_token = resolve_secret_ref(token_ref)

    if not meta_token_is_configured(access_token):
        raise RuntimeError(
            'WhatsApp media download requires a real Meta access token.'
        )

    # AUDIT-47 / BUG-49 (2026-05-18): antes hacíamos `response.content` que
    # buffereaba el archivo entero a memoria sin tope. Un adversario que
    # respondiera con un payload de 5GB (o un upstream malicioso al que Meta
    # redirigiera) podía colapsar la memoria del worker. Ahora streameamos en
    # chunks y enforce un size cap (`knowledge_file_max_bytes`, default 10MB)
    # — el mismo cap que usamos para uploads de knowledge, así garantizamos
    # consistencia. Si el upstream excede el cap, abortamos sin leer el resto.
    settings = get_settings()
    max_bytes = settings.knowledge_file_max_bytes

    # Si Content-Length viene y excede el cap, rechazar antes de leer.
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        async with client.stream(
            'GET',
            validated_media.canonical,
            headers={'Authorization': f'Bearer {access_token}'},
        ) as response:
            response.raise_for_status()
            content_length_header = response.headers.get('content-length')
            if content_length_header:
                try:
                    content_length = int(content_length_header)
                except ValueError:
                    content_length = None
                if content_length is not None and content_length > max_bytes:
                    raise RuntimeError(
                        f'WhatsApp media exceeds max allowed size '
                        f'({content_length} > {max_bytes} bytes)'
                    )

            content_type = (
                response.headers.get('content-type')
                or media_info.get('mime_type')
                or 'application/octet-stream'
            )

            buffer = bytearray()
            async for chunk in response.aiter_bytes():
                buffer.extend(chunk)
                if len(buffer) > max_bytes:
                    raise RuntimeError(
                        f'WhatsApp media exceeds max allowed size '
                        f'(>{max_bytes} bytes streamed before stop)'
                    )

            return bytes(buffer), content_type
