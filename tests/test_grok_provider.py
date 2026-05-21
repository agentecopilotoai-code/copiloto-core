"""Dynamic tests para ``GrokProvider`` — TASK-INFLU-004.

Cada modalidad se prueba con ``httpx.MockTransport`` (mismo patrón que
``tests/test_payment_provider_static.py`` y
``tests/test_unit_payment_provider_complete.py``):

- happy path → result dataclass correcto + ``provider_meta`` con
  ``model``/``request_id``/``tokens_used`` cuando aplica.
- timeout → :class:`ProviderTimeoutError`.
- 429 rate limited → :class:`ProviderRateLimited`.
- 5xx → :class:`ProviderUnavailable`.
- content rejection (400 con error.code=content_filter) →
  :class:`ProviderContentRejected`.
- ``Idempotency-Key`` presente en cada POST.
- API key se envía como ``Authorization: Bearer <key>``.
"""
from __future__ import annotations

import asyncio
import base64
from typing import Any

import httpx
import pytest

from app.ai.providers.base import (
    AudioResult,
    ImageResult,
    PersonaAnchor,
    ProviderContentRejected,
    ProviderRateLimited,
    ProviderTimeoutError,
    ProviderUnavailable,
    TextResult,
    TranscriptResult,
    VideoResult,
)
from app.ai.providers.grok import GROK_MODELS, GrokProvider


# ─── Helpers ───────────────────────────────────────────────────────────────


def _png_bytes() -> bytes:
    # PNG mágico mínimo para validar que decoding b64 produce bytes válidos.
    return b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR'


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode('ascii')


def _make_provider(handler, **kwargs) -> GrokProvider:
    transport = httpx.MockTransport(handler)
    return GrokProvider(
        api_key='test-grok-key-NEVER-LEAK',
        timeout=2.0,
        transport=transport,
        **kwargs,
    )


def _anchor() -> PersonaAnchor:
    return PersonaAnchor(
        persona_id='persona-1',
        face_embedding=tuple([0.0] * 8),
        body_traits={'build': 'athletic'},
        reference_image_urls=('https://s3/face1.jpg', 'https://s3/face2.jpg'),
        style_tokens=('cálida', 'resort wear'),
        voice_id_ref='grok-voice-clone-1',
        voice_tone='cercana',
    )


# ─── LLM ───────────────────────────────────────────────────────────────────


def test_generate_text_happy_path():
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured['path'] = request.url.path
        captured['auth'] = request.headers.get('authorization')
        captured['idem'] = request.headers.get('idempotency-key')
        captured['body'] = request.read()
        return httpx.Response(
            200,
            json={
                'id': 'chatcmpl-abc',
                'model': GROK_MODELS['llm'],
                'choices': [
                    {
                        'message': {'content': 'hola desde grok'},
                        'finish_reason': 'stop',
                    },
                ],
                'usage': {
                    'prompt_tokens': 10,
                    'completion_tokens': 5,
                    'total_tokens': 15,
                },
            },
        )

    provider = _make_provider(handler)
    result = asyncio.run(
        provider.generate_text(prompt='hola', persona_anchor=_anchor()),
    )

    assert isinstance(result, TextResult)
    assert result.text == 'hola desde grok'
    assert result.finish_reason == 'stop'
    assert result.provider_meta['model'] == GROK_MODELS['llm']
    assert result.provider_meta['request_id'] == 'chatcmpl-abc'
    assert result.provider_meta['tokens_used'] == 15
    assert result.elapsed_ms > 0

    assert captured['path'].endswith('/chat/completions')
    assert captured['auth'] == 'Bearer test-grok-key-NEVER-LEAK'
    assert captured['idem'], 'Idempotency-Key debe estar presente'


def test_generate_text_content_filter_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                'choices': [
                    {
                        'message': {'content': '[redacted]'},
                        'finish_reason': 'content_filter',
                    },
                ],
            },
        )

    provider = _make_provider(handler)
    with pytest.raises(ProviderContentRejected):
        asyncio.run(provider.generate_text(prompt='bad'))


def test_rate_limited_maps_to_typed_exception():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={'retry-after': '7'}, json={})

    provider = _make_provider(handler)
    with pytest.raises(ProviderRateLimited):
        asyncio.run(provider.generate_text(prompt='hola'))


def test_5xx_maps_to_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    provider = _make_provider(handler)
    with pytest.raises(ProviderUnavailable):
        asyncio.run(provider.generate_text(prompt='hola'))


def test_4xx_content_safety_maps_to_content_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={'error': {'code': 'content_filter_triggered', 'message': '...'}},
        )

    provider = _make_provider(handler)
    with pytest.raises(ProviderContentRejected):
        asyncio.run(provider.generate_text(prompt='hola'))


def test_4xx_error_body_as_plain_string_does_not_crash():
    """BUGFIX — xAI a veces devuelve `{"error": "string plana"}` (no
    `{"error": {"code": "..."}}`). El parser asumía siempre dict y
    crasheaba con `AttributeError: 'str' object has no attribute 'get'`.
    Ahora tolera ambos shapes y traduce a ProviderUnavailable con el
    mensaje en el detail.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={'error': 'Invalid model: grok-imagine-image'},
        )

    provider = _make_provider(handler)
    with pytest.raises(ProviderUnavailable, match='Invalid model'):
        asyncio.run(provider.generate_text(prompt='hola'))


def test_4xx_error_body_as_top_level_detail():
    """FastAPI-style `{"detail": "..."}` también se procesa."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={'detail': 'Request validation failed'},
        )

    provider = _make_provider(handler)
    with pytest.raises(ProviderUnavailable, match='Request validation failed'):
        asyncio.run(provider.generate_text(prompt='hola'))


def test_4xx_with_non_json_body_does_not_crash():
    """Si el response no es JSON (xAI puede devolver HTML/text para 4xx),
    NO crash — solo HTTP <code> en el detail.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            content=b'<html><body>Bad Request</body></html>',
            headers={'content-type': 'text/html'},
        )

    provider = _make_provider(handler)
    with pytest.raises(ProviderUnavailable, match='HTTP 400'):
        asyncio.run(provider.generate_text(prompt='hola'))


def test_extract_error_code_handles_all_shapes():
    """Unit test directo del helper — cubre los 4 paths del `isinstance`
    chain sin pasar por el handler completo.
    """
    from app.ai.providers.grok import _extract_error_code

    # Non-dict input → ''
    assert _extract_error_code('a string') == ''
    assert _extract_error_code(['a', 'list']) == ''
    assert _extract_error_code(None) == ''
    # error dict con code
    assert _extract_error_code({'error': {'code': 'X', 'message': 'm'}}) == 'X'
    # error dict sin code, con message
    assert _extract_error_code({'error': {'message': 'm only'}}) == 'm only'
    # error string plano
    assert _extract_error_code({'error': 'plain string'}) == 'plain string'
    # fallback a detail
    assert _extract_error_code({'detail': 'fastapi detail'}) == 'fastapi detail'
    # fallback a message top-level
    assert _extract_error_code({'message': 'top msg'}) == 'top msg'
    # body sin nada → ''
    assert _extract_error_code({}) == ''


def test_decode_b64_handles_invalid_input():
    """`_decode_b64` cubre 3 paths: empty → b'', valid → bytes, invalid
    → ProviderUnavailable. Defensa contra responses corruptos de xAI.
    """
    from app.ai.providers.grok import _decode_b64

    assert _decode_b64('') == b''
    assert _decode_b64('aGVsbG8=') == b'hello'
    # Padding inválido (len % 4 != 0) — base64 con `validate=False` igual
    # rechaza la longitud incorrecta y levanta binascii.Error.
    with pytest.raises(ProviderUnavailable, match='invalid base64'):
        _decode_b64('abc')


def test_post_translates_network_error_to_unavailable():
    """Errores de red (DNS/connect/etc) → ProviderUnavailable, no crash.
    Cubre la rama `except httpx.HTTPError` de `_post`.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('connection refused')

    provider = _make_provider(handler)
    with pytest.raises(ProviderUnavailable, match='connection refused'):
        asyncio.run(provider.generate_text(prompt='hola'))


def test_post_binary_translates_network_error_to_unavailable():
    """Mismo contrato para `_post_binary` (TTS)."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('boom')

    provider = _make_provider(handler)
    with pytest.raises(ProviderUnavailable):
        asyncio.run(provider.synthesize_speech(
            text='hola', persona_anchor=_anchor(),
        ))


def test_post_multipart_translates_network_error_to_unavailable():
    """Mismo contrato para `_post_multipart` (STT)."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('boom')

    provider = _make_provider(handler)
    with pytest.raises(ProviderUnavailable):
        asyncio.run(provider.transcribe(audio_bytes=b'audio'))


def test_get_json_translates_network_error_during_polling():
    """`_get_json` se usa SOLO para polling de video. Si la conexión cae
    en mitad del poll, levanta ProviderUnavailable. Cubre la rama
    `except httpx.HTTPError` de `_get_json`.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == 'POST':
            return httpx.Response(200, json={'request_id': 'vid-net-1'})
        raise httpx.ConnectError('poll connection dropped')

    provider = _make_provider(handler)
    with pytest.raises(ProviderUnavailable, match='poll connection dropped'):
        asyncio.run(provider.generate_video(
            prompt='x', persona_anchor=_anchor(),
            poll_interval_s=0.0, poll_max_attempts=2,
        ))


def test_post_binary_translates_timeout_to_provider_timeout_error():
    """`asyncio.TimeoutError` en `_post_binary` → ProviderTimeoutError.
    Cubre el branch del except específico de timeout.
    """
    async def slow_handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)  # excede hard_deadline=4.0s del fixture
        return httpx.Response(200, content=b'audio')

    provider = _make_provider(slow_handler)
    with pytest.raises(ProviderTimeoutError):
        asyncio.run(provider.synthesize_speech(
            text='hola', persona_anchor=_anchor(),
        ))


def test_post_multipart_translates_timeout_to_provider_timeout_error():
    """Mismo contrato para `_post_multipart` (STT)."""
    async def slow_handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)
        return httpx.Response(200, json={'text': 'never'})

    provider = _make_provider(slow_handler)
    with pytest.raises(ProviderTimeoutError):
        asyncio.run(provider.transcribe(audio_bytes=b'audio'))


def test_get_json_translates_timeout_during_polling():
    """`asyncio.TimeoutError` en el poll de video → ProviderTimeoutError."""
    async def slow_handler(request: httpx.Request) -> httpx.Response:
        if request.method == 'POST':
            return httpx.Response(200, json={'request_id': 'vid-tt-1'})
        await asyncio.sleep(10)  # poll cuelga
        return httpx.Response(200, json={'status': 'done'})

    provider = _make_provider(slow_handler)
    with pytest.raises(ProviderTimeoutError):
        asyncio.run(provider.generate_video(
            prompt='x', persona_anchor=_anchor(),
            poll_interval_s=0.0, poll_max_attempts=2,
        ))


def test_grok_provider_rejects_empty_api_key():
    """El constructor levanta ValueError si la api_key es vacía o None.
    Cubre la guarda del `__init__`.
    """
    with pytest.raises(ValueError, match='non-empty api_key'):
        GrokProvider(api_key='')
    with pytest.raises(ValueError, match='non-empty api_key'):
        GrokProvider(api_key=None)  # type: ignore[arg-type]


def test_timeout_maps_to_provider_timeout_error():
    async def slow_handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(10)  # excede el timeout=2.0 + 2s deadline
        return httpx.Response(200, json={})

    provider = _make_provider(slow_handler)
    with pytest.raises(ProviderTimeoutError):
        asyncio.run(provider.generate_text(prompt='hola'))


# ─── Image ─────────────────────────────────────────────────────────────────


def test_generate_image_happy_path():
    """xAI Imagine es OpenAI-compatible: endpoint `/v1/images/generations`,
    payload con `response_format='b64_json'`, response `{data: [{b64_json}]}`.
    El test también captura el path para garantizar que el provider golpea
    la URL correcta (regression contra el 404 del path histórico
    `/imagine/images`).
    """
    img_bytes = _png_bytes()
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        captured['path'] = request.url.path
        captured['payload'] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={
                'id': 'img-xyz',
                'model': GROK_MODELS['image'],
                'data': [
                    {
                        'b64_json': _b64(img_bytes),
                        'mime': 'image/png',
                        'width': 1024,
                        'height': 1024,
                        'seed': 42,
                    },
                ],
                'cost_units': 0.05,
            },
        )

    provider = _make_provider(handler)
    results = asyncio.run(
        provider.generate_image(prompt='girl in resort', persona_anchor=_anchor()),
    )

    # Path correcto — OpenAI-compatible en xAI.
    assert captured['path'].endswith('/images/generations')
    # Payload OpenAI-shape + extensión xAI `aspect_ratio`.
    assert captured['payload']['response_format'] == 'b64_json'
    assert captured['payload']['aspect_ratio'] == '1:1'
    assert captured['payload']['n'] == 1

    assert len(results) == 1
    img = results[0]
    assert isinstance(img, ImageResult)
    assert img.image_bytes == img_bytes
    assert img.mime == 'image/png'
    assert img.width == 1024
    assert img.height == 1024
    assert img.provider_meta['request_id'] == 'img-xyz'
    assert img.provider_meta['seed'] == 42


def test_generate_image_content_flags_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={'data': [], 'content_flags': ['nudity']},
        )

    provider = _make_provider(handler)
    with pytest.raises(ProviderContentRejected):
        asyncio.run(
            provider.generate_image(prompt='x', persona_anchor=_anchor()),
        )


def test_generate_image_respect_moderation_false_raises():
    """xAI marca imágenes filtradas por moderation con
    `respect_moderation=False` en el item. Si todas las imágenes vienen
    así, no hay output usable → ProviderContentRejected.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                'id': 'img-xyz',
                'data': [
                    {
                        'b64_json': _b64(b'irrelevant'),
                        'respect_moderation': False,
                    },
                ],
            },
        )

    provider = _make_provider(handler)
    with pytest.raises(ProviderContentRejected):
        asyncio.run(
            provider.generate_image(prompt='x', persona_anchor=_anchor()),
        )


# ─── Video ─────────────────────────────────────────────────────────────────


def test_generate_video_happy_path():
    """xAI Imagine video es async: POST `/v1/videos/generations` → request_id,
    luego GET `/v1/videos/{request_id}` hasta `status='done'`. La response
    final trae `video.url` (no bytes inline). Captura los paths para
    garantizar la URL correcta (regression guard contra `/imagine/videos`).
    """
    paths_hit: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths_hit.append(f'{request.method} {request.url.path}')
        if request.method == 'POST' and request.url.path.endswith('/videos/generations'):
            return httpx.Response(
                200,
                json={'request_id': 'vid-req-1'},
            )
        if request.method == 'GET' and 'vid-req-1' in request.url.path:
            # Una sola iteración del poll — status='done' directo.
            return httpx.Response(
                200,
                json={
                    'status': 'done',
                    'model': GROK_MODELS['video'],
                    'video': {
                        'url': 'https://vidgen.x.ai/test/abc.mp4',
                        'duration': 8,
                        'respect_moderation': True,
                    },
                },
            )
        return httpx.Response(404)

    provider = _make_provider(handler)
    result = asyncio.run(
        provider.generate_video(
            prompt='reel beach', persona_anchor=_anchor(),
            poll_interval_s=0.0,  # sin esperar entre polls en el test
            poll_max_attempts=3,
        ),
    )
    assert isinstance(result, VideoResult)
    # No descargamos bytes — el smoke test expone la URL al cliente.
    assert result.video_bytes == b''
    assert result.duration_s == 8.0
    assert result.provider_meta['request_id'] == 'vid-req-1'
    assert result.provider_meta['video_url'] == 'https://vidgen.x.ai/test/abc.mp4'
    # Path correcto + polling.
    assert any('POST' in p and '/videos/generations' in p for p in paths_hit)
    assert any('GET' in p and '/videos/vid-req-1' in p for p in paths_hit)


def test_generate_video_failed_status_raises():
    """status='failed' en el poll → ProviderUnavailable con el error.code."""
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == 'POST':
            return httpx.Response(200, json={'request_id': 'vid-fail-1'})
        return httpx.Response(
            200,
            json={
                'status': 'failed',
                'error': {'code': 'internal_error', 'message': 'service down'},
            },
        )

    provider = _make_provider(handler)
    with pytest.raises(ProviderUnavailable, match='internal_error'):
        asyncio.run(provider.generate_video(
            prompt='x', persona_anchor=_anchor(),
            poll_interval_s=0.0, poll_max_attempts=2,
        ))


def test_generate_video_expired_status_raises():
    """status='expired' → ProviderUnavailable. Cubre el branch del poll
    que distinge entre los 4 estados documentados (pending/done/expired/failed).
    """
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == 'POST':
            return httpx.Response(200, json={'request_id': 'vid-exp-1'})
        return httpx.Response(200, json={'status': 'expired'})

    provider = _make_provider(handler)
    with pytest.raises(ProviderUnavailable, match='expired'):
        asyncio.run(provider.generate_video(
            prompt='x', persona_anchor=_anchor(),
            poll_interval_s=0.0, poll_max_attempts=2,
        ))


def test_generate_video_failed_content_moderation_raises_content_rejected():
    """status='failed' con error.code=invalid_argument + mensaje con
    'moderation' → ProviderContentRejected (no ProviderUnavailable). xAI
    documenta este patrón cuando el prompt rompe content policy.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == 'POST':
            return httpx.Response(200, json={'request_id': 'vid-cr-1'})
        return httpx.Response(
            200,
            json={
                'status': 'failed',
                'error': {
                    'code': 'invalid_argument',
                    'message': 'Prompt blocked by content moderation policy',
                },
            },
        )

    provider = _make_provider(handler)
    with pytest.raises(ProviderContentRejected, match='moderation'):
        asyncio.run(provider.generate_video(
            prompt='x', persona_anchor=_anchor(),
            poll_interval_s=0.0, poll_max_attempts=2,
        ))


def test_generate_video_pending_then_done_completes_polling():
    """Cubre el camino: 1er poll status='pending', 2do poll status='done'.
    Verifica que el loop sigue iterando hasta done — sin esto solo
    cubriríamos el caso done-en-1er-poll.
    """
    poll_count = {'n': 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == 'POST':
            return httpx.Response(200, json={'request_id': 'vid-p-1'})
        poll_count['n'] += 1
        if poll_count['n'] == 1:
            return httpx.Response(200, json={'status': 'pending'})
        return httpx.Response(
            200,
            json={
                'status': 'done',
                'video': {'url': 'https://vid/x.mp4', 'duration': 5,
                          'respect_moderation': True},
            },
        )

    provider = _make_provider(handler)
    result = asyncio.run(provider.generate_video(
        prompt='x', persona_anchor=_anchor(),
        poll_interval_s=0.0, poll_max_attempts=3,
    ))
    assert result.provider_meta['video_url'] == 'https://vid/x.mp4'
    assert poll_count['n'] == 2


def test_generate_video_timeout_when_polling_exhausts_attempts():
    """Si el poll nunca llega a done en `poll_max_attempts`, levanta
    ProviderTimeoutError con el tiempo total mencionado en el detail.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == 'POST':
            return httpx.Response(200, json={'request_id': 'vid-t-1'})
        return httpx.Response(200, json={'status': 'pending'})

    provider = _make_provider(handler)
    with pytest.raises(ProviderTimeoutError, match='still pending'):
        asyncio.run(provider.generate_video(
            prompt='x', persona_anchor=_anchor(),
            poll_interval_s=0.0, poll_max_attempts=2,
        ))


def test_generate_video_missing_request_id_raises():
    """xAI MUST devolver `request_id` en el POST. Si no viene, no podemos
    pollear → ProviderUnavailable explícito en lugar de TypeError luego.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})  # sin request_id

    provider = _make_provider(handler)
    with pytest.raises(ProviderUnavailable, match='missing request_id'):
        asyncio.run(provider.generate_video(
            prompt='x', persona_anchor=_anchor(),
            poll_interval_s=0.0, poll_max_attempts=1,
        ))


def test_generate_video_done_without_url_raises():
    """xAI debería devolver `video.url` cuando status='done'. Si no viene,
    no hay output usable → ProviderUnavailable.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == 'POST':
            return httpx.Response(200, json={'request_id': 'vid-nu-1'})
        return httpx.Response(200, json={'status': 'done', 'video': {}})

    provider = _make_provider(handler)
    with pytest.raises(ProviderUnavailable, match='done without url'):
        asyncio.run(provider.generate_video(
            prompt='x', persona_anchor=_anchor(),
            poll_interval_s=0.0, poll_max_attempts=2,
        ))


def test_generate_video_respect_moderation_false_raises():
    """status='done' pero `video.respect_moderation=False` (xAI marca el
    output como filtrado post-generación) → ProviderContentRejected.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == 'POST':
            return httpx.Response(200, json={'request_id': 'vid-rm-1'})
        return httpx.Response(
            200,
            json={
                'status': 'done',
                'video': {
                    'url': 'https://vid/x.mp4',
                    'duration': 5,
                    'respect_moderation': False,
                },
            },
        )

    provider = _make_provider(handler)
    with pytest.raises(ProviderContentRejected, match='content_moderation'):
        asyncio.run(provider.generate_video(
            prompt='x', persona_anchor=_anchor(),
            poll_interval_s=0.0, poll_max_attempts=2,
        ))


# ─── TTS ───────────────────────────────────────────────────────────────────


def test_synthesize_speech_happy_path():
    """xAI TTS via `/v1/audio/speech` (OpenAI-compat) devuelve audio binario,
    no JSON. Verifica path + content-type del response llega como `mime`.
    """
    audio = b'\xff\xfb\x90\x44' * 100  # mp3 frame magic + padding
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        captured['path'] = request.url.path
        captured['payload'] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            content=audio,
            headers={'content-type': 'audio/mpeg'},
        )

    provider = _make_provider(handler)
    result = asyncio.run(
        provider.synthesize_speech(text='hola mundo', persona_anchor=_anchor()),
    )
    assert isinstance(result, AudioResult)
    assert result.audio_bytes == audio
    assert result.mime == 'audio/mpeg'
    # Path correcto — OpenAI-compatible.
    assert captured['path'].endswith('/audio/speech')
    # Payload OpenAI-shape: model + input + voice + response_format.
    assert captured['payload']['model'] == GROK_MODELS['tts']
    assert captured['payload']['input'] == 'hola mundo'
    assert captured['payload']['response_format'] == 'mp3'
    # `_anchor()` setea `voice_id_ref='grok-voice-clone-1'` → override del
    # tono. xAI documenta Custom Voices API que devuelve voice_ids opacos;
    # el operador puede mandarlos como override directo.
    assert captured['payload']['voice'] == 'grok-voice-clone-1'


def test_synthesize_speech_voice_tone_maps_to_builtin_voice():
    """Sin voice_id_ref, el handler mapea `voice_tone` (texto libre) a una
    voz built-in de xAI: 'eve'/'ara'/'rex'/'sal'/'leo'.
    """
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        captured['payload'] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            content=b'mp3-bytes',
            headers={'content-type': 'audio/mpeg'},
        )

    persona = PersonaAnchor(
        persona_id='p1',
        voice_tone='cálida',  # debería mapear a 'ara' (warm/friendly)
    )
    provider = _make_provider(handler)
    asyncio.run(
        provider.synthesize_speech(text='hola', persona_anchor=persona),
    )
    assert captured['payload']['voice'] == 'ara'


def test_synthesize_speech_defaults_to_eve_when_no_tone():
    """Sin voice_id_ref y sin voice_tone, default es 'eve'."""
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        import json
        captured['payload'] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            content=b'mp3-bytes',
            headers={'content-type': 'audio/mpeg'},
        )

    persona = PersonaAnchor(persona_id='p1')
    provider = _make_provider(handler)
    asyncio.run(
        provider.synthesize_speech(text='hola', persona_anchor=persona),
    )
    assert captured['payload']['voice'] == 'eve'


# ─── STT ───────────────────────────────────────────────────────────────────


def test_transcribe_happy_path():
    """xAI STT via `/v1/audio/transcriptions` (OpenAI-compat) usa multipart
    con el archivo + model. Response: JSON con `text`.
    """
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured['path'] = request.url.path
        captured['content_type'] = request.headers.get('content-type', '')
        captured['body_sample'] = request.content[:200]
        return httpx.Response(
            200,
            json={
                'text': 'hola, ¿cómo estás?',
                'language': 'es',
                'duration': 3.6,
            },
        )

    provider = _make_provider(handler)
    result = asyncio.run(
        provider.transcribe(audio_bytes=b'audio-payload', language='es'),
    )
    assert isinstance(result, TranscriptResult)
    assert result.text == 'hola, ¿cómo estás?'
    assert result.language == 'es'
    # Path correcto.
    assert captured['path'].endswith('/audio/transcriptions')
    # Content-Type multipart (no application/json).
    assert captured['content_type'].startswith('multipart/form-data'), (
        f"esperado multipart, vino: {captured['content_type']}"
    )
    # El body multipart incluye el modelo + el archivo.
    assert GROK_MODELS['stt'].encode() in captured['body_sample'] or b'model' in captured['body_sample']


# ─── Health check ──────────────────────────────────────────────────────────


def test_health_check_returns_true_on_200():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={'status': 'ok'})

    provider = _make_provider(handler)
    assert asyncio.run(provider.health_check()) is True


def test_health_check_returns_false_on_5xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={})

    provider = _make_provider(handler)
    assert asyncio.run(provider.health_check()) is False
