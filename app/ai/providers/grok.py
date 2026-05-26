"""``GrokProvider`` — adapter xAI Grok del core.

Implementa las 5 interfaces de IA del core (LLM/Image/Video/TTS/STT)
contra la API REST de xAI. Modelos cableados según el pricing público:

- LLM: ``grok-4.3`` (1M ctx).
- Image quality: ``grok-imagine-image-quality``.
- Image fast: ``grok-imagine-image``.
- Video: ``grok-imagine-video``.
- TTS / STT: endpoints ``Text to Speech`` / ``Speech to Text`` Grok.

Diseño:

- ``httpx.AsyncClient`` (no SDK oficial — el SDK xAI no es estable y este
  adapter usa la API REST documentada).
- ``asyncio.wait_for`` con ``hard_deadline = timeout + 2s`` como defensa
  contra SDKs que ignoran el timeout nativo.
- ``transport`` inyectable para tests (``httpx.MockTransport``).
- API key resuelta via ``app.services.secret_resolver.resolve_secret_ref``
  (o inyectada en el constructor para tests). Nunca se loguea en claro.

Seguridad:

- ``Authorization: Bearer <key>`` se envía solo en requests, nunca a
  logs. ``provider_meta`` incluye ``model``, ``request_id``,
  ``tokens_used`` cuando el provider los expone — sin la API key.
- Si ``safety_mode=True`` (default), el adapter prefija el prompt con
  ``[SAFE-FOR-WORK, BRAND-SAFE]`` y verifica ``content_flags`` antes
  de retornar. Si el provider rechaza, lanza
  :class:`ProviderContentRejected`.
- ``Idempotency-Key`` en todos los POSTs para safety con retries del
  dispatcher (TASK-INFLU-007).
"""
from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import time
import uuid
from typing import Any, Final

import httpx

from app.ai.providers.base import (
    AudioResult,
    ImageProvider,
    ImageResult,
    LLMProvider,
    PersonaAnchor,
    ProviderContentRejected,
    ProviderRateLimited,
    ProviderTimeoutError,
    ProviderUnavailable,
    STTProvider,
    TTSProvider,
    TextResult,
    TranscriptResult,
    VideoProvider,
    VideoResult,
)

logger = logging.getLogger(__name__)


# ─── Modelos cableados (TASK-INFLU-004) ────────────────────────────────────


DEFAULT_BASE_URL: Final[str] = 'https://api.x.ai/v1'

# Modelos por modalidad — sincronizado con el pricing de xAI. Pueden ser
# overrideados con ``params['model']`` desde ``platform_ai_providers``.
GROK_MODELS: Final[dict[str, str]] = {
    'llm': 'grok-4.3',
    'image': 'grok-imagine-image-quality',
    'image_fast': 'grok-imagine-image',
    'video': 'grok-imagine-video',
    'tts': 'grok-tts-1',
    'stt': 'grok-stt-1',
}

# Prefijo aplicado cuando ``safety_mode=True``. Grok respeta hints en el
# prompt; los ``content_flags`` de la respuesta confirman si el filter
# disparó.
SAFETY_PREFIX: Final[str] = '[SAFE-FOR-WORK, BRAND-SAFE] '


# ─── GrokProvider ──────────────────────────────────────────────────────────


class GrokProvider(LLMProvider, ImageProvider, VideoProvider, TTSProvider, STTProvider):
    """Adapter xAI Grok — implementa las 5 interfaces."""

    provider_name = 'grok'  # match con ``platform_ai_providers.provider``.

    def __init__(
        self,
        *,
        api_key: str,
        timeout: float = 60.0,
        base_url: str = DEFAULT_BASE_URL,
        models: dict[str, str] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError('GrokProvider requires a non-empty api_key')
        self._api_key = api_key
        self._timeout = float(timeout)
        self._hard_deadline = self._timeout + 2.0
        self._base_url = base_url.rstrip('/')
        self._models = {**GROK_MODELS, **(models or {})}
        self._transport = transport

    # ── HTTP plumbing ─────────────────────────────────────────────────────

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(self._timeout, connect=5.0),
            transport=self._transport,
            headers={
                'Authorization': f'Bearer {self._api_key}',
                'User-Agent': 'copiloto-core/1.0',
            },
        )

    async def _post(self, path: str, payload: dict[str, Any]) -> tuple[dict, dict]:
        """POST con hard deadline + error translation.

        Returns ``(json_body, response_headers)`` o levanta una de las
        excepciones tipadas de ``base.py``.
        """
        idem_key = f'inf-{uuid.uuid4().hex}'
        async with self._client() as client:
            try:
                resp = await asyncio.wait_for(
                    client.post(
                        path,
                        json=payload,
                        headers={'Idempotency-Key': idem_key},
                    ),
                    timeout=self._hard_deadline,
                )
            except asyncio.TimeoutError as exc:
                raise ProviderTimeoutError(
                    f'grok {path} exceeded {self._hard_deadline:.1f}s',
                ) from exc
            except httpx.HTTPError as exc:
                # Network / DNS / connect errors — provider está caído.
                raise ProviderUnavailable(f'grok {path}: {exc}') from exc

        return _translate_response(resp, path)

    async def _post_binary(self, path: str, payload: dict[str, Any]) -> tuple[bytes, dict]:
        """POST JSON con response binario (e.g. `/audio/speech` devuelve mp3).

        El response NO es JSON — devolvemos bytes crudos. Status codes se
        mapean con el mismo `_translate_response_status` que el POST normal,
        pero saltando el JSON parse del body.
        """
        idem_key = f'inf-{uuid.uuid4().hex}'
        async with self._client() as client:
            try:
                resp = await asyncio.wait_for(
                    client.post(
                        path,
                        json=payload,
                        headers={'Idempotency-Key': idem_key},
                    ),
                    timeout=self._hard_deadline,
                )
            except asyncio.TimeoutError as exc:
                raise ProviderTimeoutError(
                    f'grok {path} exceeded {self._hard_deadline:.1f}s',
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(f'grok {path}: {exc}') from exc

        _translate_response_status(resp, path)
        return resp.content, dict(resp.headers)

    async def _post_multipart(
        self,
        path: str,
        *,
        files: dict[str, tuple[str, bytes, str]],
        data: dict[str, str],
    ) -> tuple[dict, dict]:
        """POST multipart/form-data → JSON response. Usado por STT
        (`/audio/transcriptions`) que exige multipart con el archivo.
        """
        idem_key = f'inf-{uuid.uuid4().hex}'
        async with self._client() as client:
            try:
                resp = await asyncio.wait_for(
                    client.post(
                        path,
                        files=files,
                        data=data,
                        headers={'Idempotency-Key': idem_key},
                    ),
                    timeout=self._hard_deadline,
                )
            except asyncio.TimeoutError as exc:
                raise ProviderTimeoutError(
                    f'grok {path} exceeded {self._hard_deadline:.1f}s',
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(f'grok {path}: {exc}') from exc

        return _translate_response(resp, path)

    async def _get_json(self, path: str) -> dict:
        """GET con response JSON. Usado para el polling de videos
        (`GET /videos/{request_id}`). Sin Idempotency-Key — los GET son
        naturalmente idempotentes.
        """
        async with self._client() as client:
            try:
                resp = await asyncio.wait_for(
                    client.get(path),
                    timeout=self._hard_deadline,
                )
            except asyncio.TimeoutError as exc:
                raise ProviderTimeoutError(
                    f'grok {path} exceeded {self._hard_deadline:.1f}s',
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderUnavailable(f'grok {path}: {exc}') from exc

        body, _ = _translate_response(resp, path)
        return body

    # `_download` (descarga de URL externa) se removió cuando `generate_video`
    # dejó de bajar los bytes inline (el smoke test usa la URL temporal de xAI
    # directamente). Si en el futuro un caller necesita bytes — para subir a
    # S3, p.ej. — se puede re-introducir o usar httpx ad-hoc desde el caller.

    # ── IAProvider ────────────────────────────────────────────────────────

    async def health_check(self) -> bool:
        """GET ``/health`` (xAI lo expone). Returns True si 200."""
        async with self._client() as client:
            try:
                resp = await asyncio.wait_for(
                    client.get('/health'),
                    timeout=2.0,
                )
            except (asyncio.TimeoutError, httpx.HTTPError):
                return False
        return resp.status_code == 200

    # ── LLMProvider ───────────────────────────────────────────────────────

    async def generate_text(
        self,
        *,
        prompt: str,
        system: str | None = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
        persona_anchor: PersonaAnchor | None = None,
    ) -> TextResult:
        sys_prompt = system or ''
        if persona_anchor is not None:
            tone = persona_anchor.voice_tone or ''
            style = ', '.join(persona_anchor.style_tokens or ())
            if tone or style:
                sys_prompt = (
                    f'{sys_prompt}\n\nVoz: {tone}. Estilo: {style}.'.strip()
                )

        payload: dict[str, Any] = {
            'model': self._models['llm'],
            'messages': _build_messages(prompt, sys_prompt),
            'max_tokens': max_tokens,
            'temperature': temperature,
        }

        t0 = time.monotonic()
        body, _ = await self._post('/chat/completions', payload)
        elapsed_ms = (time.monotonic() - t0) * 1000.0

        choice = (body.get('choices') or [{}])[0]
        message = choice.get('message') or {}
        text = (message.get('content') or '').strip()
        finish_reason = choice.get('finish_reason')
        if finish_reason == 'content_filter':
            raise ProviderContentRejected('grok flagged the response (content_filter)')

        usage = body.get('usage') or {}
        return TextResult(
            text=text,
            finish_reason=finish_reason,
            provider_meta={
                'model': body.get('model') or self._models['llm'],
                'request_id': body.get('id'),
                'tokens_used': usage.get('total_tokens'),
                'prompt_tokens': usage.get('prompt_tokens'),
                'completion_tokens': usage.get('completion_tokens'),
            },
            cost_units=float(usage.get('total_tokens') or 0),
            elapsed_ms=elapsed_ms,
        )

    # ── ImageProvider ─────────────────────────────────────────────────────

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
        """Genera imágenes via la API REST de xAI Imagine.

        xAI expone un endpoint OpenAI-compatible: `POST /v1/images/generations`.
        El payload base es OpenAI-shape (`model`, `prompt`, `n`,
        `response_format`); `aspect_ratio` es una extensión propia de xAI
        documentada en `docs/xGrok/Imagine Overview`. Soporta opcionalmente
        `image_url` / `image_urls` para edits con reference images.

        Response shape: `{data: [{url, b64_json?}, ...]}`. Pedimos
        `response_format='b64_json'` para obtener los bytes inline (URLs
        son temporales y exigirían un fetch extra).
        """
        full_prompt = (SAFETY_PREFIX if safety_mode else '') + prompt
        refs: list[str] = list(persona_anchor.reference_image_urls or ())
        if reference_image_url:
            refs.append(reference_image_url)

        payload: dict[str, Any] = {
            'model': self._models['image'],
            'prompt': full_prompt,
            'n': max(1, int(count)),
            'response_format': 'b64_json',
        }
        # `aspect_ratio` es opcional en xAI; default 'auto'. Solo enviamos
        # si el caller pidió algo distinto del wildcard.
        if format and format != 'auto':
            payload['aspect_ratio'] = format
        # Reference images: el doc menciona `image_url` (1 ref, para edits
        # de una sola imagen) y `image_urls` (hasta 3 para multi-edit).
        if refs:
            if len(refs) == 1:
                payload['image_url'] = refs[0]
            else:
                payload['image_urls'] = refs[:3]

        t0 = time.monotonic()
        body, _ = await self._post('/images/generations', payload)
        elapsed_ms = (time.monotonic() - t0) * 1000.0

        # xAI puede devolver content moderation en el item, no en root.
        # Si todos los items vienen marcados como respect_moderation=False,
        # tratamos como rejection (el cliente no puede usar la imagen).
        data = body.get('data') or []
        if not data and body.get('content_flags'):
            raise ProviderContentRejected(
                f'grok rejected image generation: {body["content_flags"]}',
            )
        all_filtered = data and all(
            item.get('respect_moderation') is False for item in data
        )
        if all_filtered:
            raise ProviderContentRejected(
                'grok content_moderation rejected all generated images',
            )

        results: list[ImageResult] = []
        for item in data:
            # OpenAI shape: `b64_json`. Algunos endpoints xAI también
            # devuelven `b64_image` — aceptamos ambos por defensa.
            img_b64 = item.get('b64_json') or item.get('b64_image') or ''
            results.append(
                ImageResult(
                    image_bytes=_decode_b64(img_b64),
                    mime=item.get('mime') or 'image/jpeg',
                    width=int(item.get('width') or 0),
                    height=int(item.get('height') or 0),
                    provider_meta={
                        'model': body.get('model') or self._models['image'],
                        'request_id': body.get('id'),
                        'seed': item.get('seed'),
                    },
                    cost_units=float(body.get('cost_units') or 0) / max(1, len(data)),
                    elapsed_ms=elapsed_ms,
                ),
            )
        return results

    # ── VideoProvider ─────────────────────────────────────────────────────

    async def generate_video(
        self,
        *,
        prompt: str,
        persona_anchor: PersonaAnchor,
        duration_s: float = 15.0,
        format: str = '9:16',
        safety_mode: bool = True,
        audio_url: str | None = None,
        poll_interval_s: float = 5.0,
        poll_max_attempts: int = 120,
    ) -> VideoResult:
        """Genera video via xAI Imagine — async start + poll + download.

        xAI documenta el flujo en `docs/xGrok/Video Generation`:

          1. POST `/v1/videos/generations` body `{model, prompt, ...}`
             → `{request_id}`.
          2. GET `/v1/videos/{request_id}` repetido hasta
             `status in ('done', 'expired', 'failed')`.
          3. Cuando `status='done'`, la response trae
             `video: {url, duration, respect_moderation}`. La URL es
             temporal; descargamos los bytes inmediatamente para que el
             caller no tenga que hacer un segundo HTTP fetch.

        Persona anchoring se mantiene como input, pero solo se manda lo
        que xAI acepta (`reference_image_urls` para reference-to-video,
        opcional). Los style_tokens viajan dentro del prompt vía
        SAFETY_PREFIX si está activo el modo seguro.
        """
        full_prompt = (SAFETY_PREFIX if safety_mode else '') + prompt
        refs = list(persona_anchor.reference_image_urls or ())

        payload: dict[str, Any] = {
            'model': self._models['video'],
            'prompt': full_prompt,
            'duration': max(1, int(duration_s)),
            'aspect_ratio': format,
        }
        if refs:
            payload['reference_image_urls'] = refs[:7]
        if audio_url:
            payload['audio_url'] = audio_url

        t0 = time.monotonic()
        body, _ = await self._post('/videos/generations', payload)

        request_id = body.get('request_id') or body.get('id')
        if not request_id:
            raise ProviderUnavailable(
                'grok /videos/generations: missing request_id in response',
            )

        # Poll hasta done/expired/failed. xAI dice que videos toman
        # típicamente "varios minutos"; usamos 120 intentos * 5s = 10 min
        # como techo. El hard_deadline general (timeout * 2) no aplica al
        # polling — cada GET es individual.
        done_body: dict | None = None
        for _ in range(max(1, poll_max_attempts)):
            await asyncio.sleep(poll_interval_s)
            poll_body = await self._get_json(f'/videos/{request_id}')
            status_str = poll_body.get('status') or 'pending'
            if status_str == 'done':
                done_body = poll_body
                break
            if status_str == 'expired':
                raise ProviderUnavailable(
                    f'grok video {request_id}: request expired'
                )
            if status_str == 'failed':
                err = poll_body.get('error') or {}
                code = err.get('code') or 'unknown'
                msg = err.get('message') or 'video generation failed'
                if code == 'invalid_argument' and (
                    'content' in msg.lower() or 'moderation' in msg.lower()
                ):
                    raise ProviderContentRejected(f'grok video: {msg}')
                raise ProviderUnavailable(f'grok video [{code}]: {msg}')
            # status='pending' → seguir polling

        if done_body is None:
            raise ProviderTimeoutError(
                f'grok video {request_id}: still pending after '
                f'{poll_max_attempts * poll_interval_s:.0f}s'
            )

        video = done_body.get('video') or {}
        video_url = video.get('url')
        if not video_url:
            raise ProviderUnavailable(f'grok video {request_id}: done without url')

        if video.get('respect_moderation') is False:
            raise ProviderContentRejected('grok video: content_moderation rejected')

        # NO descargamos los bytes — la URL de xAI es temporal pero válida
        # mientras dura el smoke test, y los videos pueden pesar megabytes
        # (no queremos inline-base64 en el JSON del response). Callers que
        # necesiten bytes pueden hacer `_download(provider_meta['video_url'])`
        # explícitamente. Para el smoke test, el frontend usa
        # `<video src={url}>` directo y stream-friendly.
        elapsed_ms = (time.monotonic() - t0) * 1000.0

        return VideoResult(
            video_bytes=b'',
            mime='video/mp4',
            width=int(video.get('width') or 0),
            height=int(video.get('height') or 0),
            duration_s=float(video.get('duration') or duration_s),
            provider_meta={
                'model': done_body.get('model') or self._models['video'],
                'request_id': request_id,
                'video_url': video_url,
            },
            cost_units=float(video.get('duration') or duration_s),
            elapsed_ms=elapsed_ms,
        )

    # ── TTSProvider ───────────────────────────────────────────────────────

    async def synthesize_speech(
        self,
        *,
        text: str,
        persona_anchor: PersonaAnchor,
        language: str = 'es',
        sample_rate: int = 24000,
    ) -> AudioResult:
        """Sintetiza voz via xAI — endpoint OpenAI-compatible.

        POST `/v1/audio/speech` body `{model, input, voice, response_format}`.
        Response: bytes binarios del audio (Content-Type según
        `response_format`, default mp3). NO es JSON — usamos
        `_post_binary` que no intenta parsear.

        Voces de xAI documentadas en `docs/xGrok/Voice Agent API`:
        `eve` (default), `ara`, `rex`, `sal`, `leo`, o un voice_id custom
        creado vía Custom Voices API. Si `persona_anchor.voice_id_ref`
        viene set, lo usamos como override; si no, defaulteamos a `eve`.
        """
        voice = persona_anchor.voice_id_ref or _map_voice_tone(
            persona_anchor.voice_tone,
        ) or 'eve'

        payload: dict[str, Any] = {
            'model': self._models['tts'],
            'input': text,
            'voice': voice,
            'response_format': 'mp3',
        }

        t0 = time.monotonic()
        audio_bytes, headers = await self._post_binary('/audio/speech', payload)
        elapsed_ms = (time.monotonic() - t0) * 1000.0

        return AudioResult(
            audio_bytes=audio_bytes,
            mime=headers.get('content-type') or 'audio/mpeg',
            duration_s=0.0,  # OpenAI-compat response no incluye duración
            sample_rate=sample_rate,
            provider_meta={
                'model': self._models['tts'],
                'voice': voice,
                'chars_used': len(text),
            },
            cost_units=float(len(text)),
            elapsed_ms=elapsed_ms,
        )

    # ── STTProvider ───────────────────────────────────────────────────────

    async def transcribe(
        self,
        *,
        audio_bytes: bytes,
        mime: str = 'audio/mpeg',
        language: str | None = None,
    ) -> TranscriptResult:
        """Transcribe audio via xAI — endpoint OpenAI-compatible.

        POST `/v1/audio/transcriptions` con multipart/form-data:
          - `file`: bytes del audio (con filename + content-type)
          - `model`: nombre del modelo STT (ej. `grok-voice-latest`)
          - `language`: opcional, ISO code (sino autodetect)
          - `response_format`: `json` para que el response sea
            `{text, language?}` parseable.
        """
        ext = _ext_for_mime(mime)
        files = {
            'file': (f'audio.{ext}', audio_bytes, mime),
        }
        form: dict[str, str] = {
            'model': self._models['stt'],
            'response_format': 'json',
        }
        if language:
            form['language'] = language

        t0 = time.monotonic()
        body, _ = await self._post_multipart(
            '/audio/transcriptions', files=files, data=form,
        )
        elapsed_ms = (time.monotonic() - t0) * 1000.0

        return TranscriptResult(
            text=(body.get('text') or '').strip(),
            language=body.get('language') or language,
            confidence=body.get('confidence'),
            provider_meta={
                'model': self._models['stt'],
                'duration_s': body.get('duration'),
            },
            cost_units=float(body.get('duration') or 0.0) / 3600.0,
            elapsed_ms=elapsed_ms,
        )


# ─── Helpers ───────────────────────────────────────────────────────────────


def _build_messages(prompt: str, system: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({'role': 'system', 'content': system})
    messages.append({'role': 'user', 'content': prompt})
    return messages


def _decode_b64(data: str) -> bytes:
    if not data:
        return b''
    try:
        return base64.b64decode(data, validate=False)
    except (ValueError, binascii.Error) as exc:
        raise ProviderUnavailable(f'grok returned invalid base64: {exc}') from exc


def _translate_response_status(resp: httpx.Response, path: str) -> None:
    """Mapea status codes >= 400 a excepciones tipadas. Levanta o regresa
    silenciosamente. Compartido entre `_translate_response` (JSON),
    `_post_binary` (bytes) y `_post_multipart`.
    """
    if resp.status_code == 429:
        retry_after = resp.headers.get('retry-after')
        raise ProviderRateLimited(
            f'grok {path} rate-limited (retry-after={retry_after})',
        )
    if resp.status_code in {400, 422}:
        # 400/422 con marker de content filter → content_rejected;
        # otros 4xx genéricos → unavailable.
        try:
            body = resp.json()
        except ValueError:
            body = {}
        err = _extract_error_code(body)
        if err and ('content' in err.lower() or 'safety' in err.lower()):
            raise ProviderContentRejected(f'grok {path}: {err}')
        raise ProviderUnavailable(f'grok {path}: HTTP {resp.status_code} {err}'.rstrip())
    if resp.status_code >= 400:
        raise ProviderUnavailable(f'grok {path}: HTTP {resp.status_code}')


def _extract_error_code(body: Any) -> str:
    """Best-effort: extrae código/mensaje de error de un body JSON 4xx.

    xAI no garantiza un shape único para errores. Vimos en producción:

      - OpenAI-shape:     ``{"error": {"code": "...", "message": "..."}}``
      - String plano:     ``{"error": "Invalid request"}``
      - Detail estilo FastAPI: ``{"detail": "..."}`` o ``{"message": "..."}``

    Sin esta defensa, el caller crasheaba con
    ``AttributeError: 'str' object has no attribute 'get'`` cuando xAI
    enviaba el segundo shape.
    """
    if not isinstance(body, dict):
        return ''
    err = body.get('error')
    if isinstance(err, dict):
        return str(err.get('code') or err.get('message') or '')
    if isinstance(err, str):
        return err
    # Fallbacks comunes — xAI/FastAPI/etc.
    detail = body.get('detail') or body.get('message')
    return str(detail) if detail else ''


def _translate_response(resp: httpx.Response, path: str) -> tuple[dict, dict]:
    """Mapea status codes a excepciones tipadas o devuelve ``(body, headers)``."""
    _translate_response_status(resp, path)
    try:
        return resp.json(), dict(resp.headers)
    except ValueError as exc:
        raise ProviderUnavailable(f'grok {path}: non-json response') from exc


# Mapa heurístico voice_tone (texto libre) → voice id de xAI documentado.
# Si el operador setea `voice_tone='cálida'` queremos elegir una voz coherente.
_VOICE_TONE_MAP: Final[dict[str, str]] = {
    'cálida': 'ara',
    'calida': 'ara',
    'amigable': 'ara',
    'cercana': 'eve',
    'energética': 'eve',
    'energetica': 'eve',
    'profesional': 'rex',
    'autoritativa': 'leo',
    'autoritaria': 'leo',
    'neutral': 'sal',
    'balanceada': 'sal',
}


def _map_voice_tone(tone: str | None) -> str | None:
    """Mapea un texto libre de tono a un voice id de xAI. Devuelve None si
    no hay match — el caller cae al default `eve`."""
    if not tone:
        return None
    return _VOICE_TONE_MAP.get(tone.strip().lower())


# MIME → extensión. xAI (y OpenAI) usan el `filename` del multipart como
# hint del codec; sin extension correcta el endpoint puede devolver 400.
_MIME_EXT_MAP: Final[dict[str, str]] = {
    'audio/mpeg': 'mp3',
    'audio/mp3': 'mp3',
    'audio/wav': 'wav',
    'audio/x-wav': 'wav',
    'audio/wave': 'wav',
    'audio/webm': 'webm',
    'audio/ogg': 'ogg',
    'audio/flac': 'flac',
    'audio/m4a': 'm4a',
    'audio/mp4': 'm4a',
}


def _ext_for_mime(mime: str) -> str:
    return _MIME_EXT_MAP.get(mime.lower().split(';')[0].strip(), 'mp3')


__all__ = ['GrokProvider', 'GROK_MODELS', 'DEFAULT_BASE_URL', 'SAFETY_PREFIX']
