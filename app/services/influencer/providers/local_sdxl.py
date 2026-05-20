"""``LocalSDXLProvider`` — Stable Diffusion XL local (TASK-INFLU-006).

Adapter sobre AUTOMATIC1111 WebUI (default :7860) o ComfyUI con un
endpoint REST compatible. Soporta IP-Adapter para persona consistency
vía ``PersonaAnchor.reference_image_urls``.
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import time
from typing import Final

import httpx

from app.services.influencer.providers.base import (
    ImageProvider,
    ImageResult,
    PersonaAnchor,
    ProviderContentRejected,
    ProviderTimeoutError,
    ProviderUnavailable,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL: Final[str] = 'http://localhost:7860'
DEFAULT_MODEL: Final[str] = 'sd_xl_base_1.0'


class LocalSDXLProvider(ImageProvider):
    provider_name = 'local_sdxl'

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip('/')
        self._model = model
        self._timeout = float(timeout)
        self._hard_deadline = self._timeout + 2.0
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(self._timeout, connect=2.0),
            transport=self._transport,
        )

    async def health_check(self) -> bool:
        async with self._client() as client:
            try:
                resp = await asyncio.wait_for(
                    client.get('/sdapi/v1/options'),
                    timeout=2.0,
                )
            except (asyncio.TimeoutError, httpx.HTTPError):
                return False
        return resp.status_code == 200

    async def generate_image(
        self,
        *,
        prompt: str,
        persona_anchor: PersonaAnchor,
        count: int = 1,
        format: str = '1:1',
        safety_mode: bool = True,
        reference_image_url: str | None = None,
    ) -> list[ImageResult]:
        width, height = _format_to_wh(format)
        safety_prefix = '[SAFE-FOR-WORK, BRAND-SAFE] ' if safety_mode else ''
        full_prompt = safety_prefix + prompt
        if persona_anchor.style_tokens:
            full_prompt += f', {", ".join(persona_anchor.style_tokens)}'

        payload = {
            'prompt': full_prompt,
            'negative_prompt': 'nsfw, lowres, blurry, deformed',
            'batch_size': max(1, int(count)),
            'width': width,
            'height': height,
            'steps': 30,
            'cfg_scale': 7.0,
            'sampler_name': 'DPM++ 2M Karras',
            # IP-Adapter via alwayson_scripts si reference disponible
            'alwayson_scripts': _build_ipadapter_args(persona_anchor, reference_image_url),
        }

        t0 = time.monotonic()
        async with self._client() as client:
            try:
                resp = await asyncio.wait_for(
                    client.post('/sdapi/v1/txt2img', json=payload),
                    timeout=self._hard_deadline,
                )
            except asyncio.TimeoutError as exc:
                raise ProviderTimeoutError(
                    f'local_sdxl exceeded {self._hard_deadline:.1f}s',
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(f'local_sdxl: {exc}') from exc

        if resp.status_code >= 400:
            try:
                body = resp.json()
            except ValueError:
                body = {}
            detail = (body.get('detail') or '').lower()
            if 'nsfw' in detail or 'safety' in detail:
                raise ProviderContentRejected(f'local_sdxl: {detail}')
            raise ProviderUnavailable(f'local_sdxl HTTP {resp.status_code}')

        elapsed_ms = (time.monotonic() - t0) * 1000.0
        body = resp.json()
        images_b64 = body.get('images') or []
        results: list[ImageResult] = []
        for b64 in images_b64:
            results.append(
                ImageResult(
                    image_bytes=_decode_b64(b64),
                    mime='image/png',
                    width=width,
                    height=height,
                    provider_meta={
                        'model': self._model,
                        'sampler': payload['sampler_name'],
                        'steps': payload['steps'],
                    },
                    elapsed_ms=elapsed_ms,
                ),
            )
        return results


def _format_to_wh(fmt: str) -> tuple[int, int]:
    return {
        '1:1': (1024, 1024),
        '9:16': (768, 1344),
        '16:9': (1344, 768),
        '4:5': (896, 1120),
    }.get(fmt, (1024, 1024))


def _build_ipadapter_args(
    anchor: PersonaAnchor,
    extra_ref: str | None,
) -> dict:
    refs = list(anchor.reference_image_urls or ())
    if extra_ref:
        refs.append(extra_ref)
    if not refs:
        return {}
    return {
        'IP-Adapter': {
            'args': [
                {
                    'enabled': True,
                    'reference_images': refs,
                    'weight': 0.7,
                },
            ],
        },
    }


def _decode_b64(data: str) -> bytes:
    if not data:
        return b''
    try:
        return base64.b64decode(data, validate=False)
    except (ValueError, binascii.Error) as exc:
        raise ProviderUnavailable(f'local_sdxl invalid b64: {exc}') from exc


__all__ = ['LocalSDXLProvider', 'DEFAULT_BASE_URL', 'DEFAULT_MODEL']
