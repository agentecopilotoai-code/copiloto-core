"""``generation_worker`` — TASK-INFLU-012.

Consume `influencer.generations` con `status='queued'` (y
`face_variation_requests`), llama al ``provider_dispatcher``, persiste
los assets en storage (S3 o local stub) e inserta filas en
`influencer.assets`. Maneja safety filters: si el provider rechaza,
marca `status='failed'` + `error_message='content_rejected'`.

Patrón de queue: ``select ... for update skip locked`` para que múltiples
workers en paralelo no procesen el mismo job.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import asyncpg

from app.ai.dispatcher import dispatch
from app.ai.providers.factory import make_adapter_for_provider
from app.ai.registry import ResolvedProvider
from app.ai.providers.base import (
    AudioResult,
    ImageProvider,
    ImageResult,
    LLMProvider,
    PersonaAnchor,
    ProviderContentRejected,
    ProviderError,
    TTSProvider,
    TextResult,
    VideoProvider,
    VideoResult,
)

logger = logging.getLogger(__name__)


# ─── Storage interface (S3 stub) ───────────────────────────────────────────


StorageUploader = Callable[[str, bytes, str], Awaitable[str]]
"""Función ``(key, bytes, mime) -> stored_url``. Por defecto se inyecta
un noop que devuelve un placeholder; producción se inyecta un cliente S3
real. Mantenemos esto inyectable para que el worker sea testeable sin
boto3 / minio."""


async def _noop_uploader(key: str, data: bytes, mime: str) -> str:
    """Storage stub — devuelve un key estable sin subir nada.

    Producción inyecta `s3_uploader` que persiste en MinIO/S3 con
    `cache-control: private, max-age=3600` y `content-type` correcto.
    """
    return f's3://stub/{key}'


# ─── Kind → modality + result extraction ───────────────────────────────────


_KIND_TO_MODALITY: dict[str, str] = {
    'photo': 'image',
    'carousel': 'image',
    'story': 'image',
    'ad': 'image',
    'face_variation': 'image',
    'reel': 'video',
    'voice_sample': 'tts',
}


def _build_persona_anchor(persona_row: asyncpg.Record) -> PersonaAnchor:
    """Arma el PersonaAnchor desde la fila completa de personas."""
    face = persona_row['face'] if isinstance(persona_row['face'], dict) else {}
    body = persona_row['body'] if isinstance(persona_row['body'], dict) else {}
    voice = persona_row['voice'] if isinstance(persona_row['voice'], dict) else {}
    return PersonaAnchor(
        persona_id=str(persona_row['id']),
        face_embedding=tuple(face.get('face_embedding') or ()) or None,
        body_traits=body,
        reference_image_urls=tuple(face.get('reference_image_urls') or ()),
        style_tokens=tuple(face.get('style_tokens') or ())
            or tuple(body.get('style_tokens') or ()),
        voice_id_ref=voice.get('voice_id_ref'),
        voice_tone=voice.get('tone'),
    )


def _extract_asset_bytes(result: Any) -> tuple[bytes, str, dict[str, Any]]:
    """Devuelve `(payload_bytes, mime, meta_dims)` del result dataclass."""
    if isinstance(result, ImageResult):
        return result.image_bytes, result.mime, {
            'width': result.width, 'height': result.height,
        }
    if isinstance(result, VideoResult):
        return result.video_bytes, result.mime, {
            'width': result.width, 'height': result.height,
            'duration_s': result.duration_s,
        }
    if isinstance(result, AudioResult):
        return result.audio_bytes, result.mime, {
            'duration_s': result.duration_s,
        }
    if isinstance(result, TextResult):
        return result.text.encode('utf-8'), 'text/plain', {}
    raise ValueError(f'unknown result type: {type(result)!r}')


# ─── Worker core ───────────────────────────────────────────────────────────


@dataclass
class WorkerResult:
    generation_id: UUID
    status: str
    error: str | None
    assets_created: int


async def claim_next_generation(
    conn: asyncpg.Connection,
) -> asyncpg.Record | None:
    """Toma un job pendiente vía ``FOR UPDATE SKIP LOCKED``.

    Devuelve la fila (con bloqueo en la transacción actual) o None si
    no hay nada en cola. Caller debe estar dentro de una transacción.
    """
    return await conn.fetchrow(
        '''
        select * from influencer.generations
        where status = 'queued'
        order by created_at
        for update skip locked
        limit 1
        '''
    )


async def process_one_generation(
    *,
    conn: asyncpg.Connection,
    generation_row: asyncpg.Record,
    storage_upload: StorageUploader | None = None,
) -> WorkerResult:
    """Procesa una generación end-to-end.

    Asume que ``generation_row`` ya está bloqueado en la transacción
    actual (`select ... for update`). Esta función:
    1. Marca `status='running'`.
    2. Carga la persona + arma PersonaAnchor.
    3. Llama al dispatcher con la modalidad correcta.
    4. Sube los bytes a storage (vía `storage_upload` o noop).
    5. Inserta filas en `influencer.assets`.
    6. Marca `status='succeeded'` (o `'failed'` con error_message).

    Returns:
        WorkerResult con el outcome.
    """
    gen_id: UUID = generation_row['id']
    persona_id: UUID = generation_row['persona_id']
    tenant_id: UUID = generation_row['tenant_id']
    kind: str = generation_row['kind']
    uploader: StorageUploader = storage_upload or _noop_uploader

    modality = _KIND_TO_MODALITY.get(kind)
    if modality is None:
        await _mark_failed(conn, gen_id, f'unknown kind: {kind}')
        return WorkerResult(gen_id, 'failed', f'unknown kind: {kind}', 0)

    await conn.execute(
        '''
        update influencer.generations
        set status = 'running', started_at = now()
        where id = $1
        ''',
        gen_id,
    )

    persona = await conn.fetchrow(
        'select * from influencer.personas where id = $1',
        persona_id,
    )
    if persona is None:
        await _mark_failed(conn, gen_id, 'persona disappeared')
        return WorkerResult(gen_id, 'failed', 'persona disappeared', 0)

    anchor = _build_persona_anchor(persona)
    prompt: str = generation_row['prompt'] or ''
    fmt: str = generation_row['format']
    count: int = generation_row['count_requested']

    async def call_fn(provider: ResolvedProvider) -> Any:
        """Instancia adapter via factory y llama el método correcto.

        El dispatcher invoca este closure por cada intento (primary +
        fallbacks). Cada llamada construye una instancia fresca del
        adapter — los adapters son stateless (httpx.AsyncClient lo crea
        cada `_post`), así que no hay costo de recrear.

        Mapping modality → método:
            llm   → generate_text
            image → generate_image (devuelve list, el worker itera)
            video → generate_video
            tts   → synthesize_speech

        STT no llega a este worker (no está en _KIND_TO_MODALITY) —
        se procesa en otro flow (mensajes de voz inbound).
        """
        adapter = make_adapter_for_provider(provider)

        if modality == 'image':
            if not isinstance(adapter, ImageProvider):
                raise ProviderError(
                    f'{provider.provider} no implementa ImageProvider '
                    f'(modality={modality})',
                )
            return await adapter.generate_image(
                prompt=prompt,
                persona_anchor=anchor,
                count=count,
                format=fmt,
                safety_mode=True,
            )

        if modality == 'video':
            if not isinstance(adapter, VideoProvider):
                raise ProviderError(
                    f'{provider.provider} no implementa VideoProvider '
                    f'(modality={modality})',
                )
            return await adapter.generate_video(
                prompt=prompt,
                persona_anchor=anchor,
                format=fmt,
                safety_mode=True,
            )

        if modality == 'tts':
            if not isinstance(adapter, TTSProvider):
                raise ProviderError(
                    f'{provider.provider} no implementa TTSProvider '
                    f'(modality={modality})',
                )
            return await adapter.synthesize_speech(
                text=prompt,
                persona_anchor=anchor,
            )

        if modality == 'llm':
            if not isinstance(adapter, LLMProvider):
                raise ProviderError(
                    f'{provider.provider} no implementa LLMProvider '
                    f'(modality={modality})',
                )
            return await adapter.generate_text(
                prompt=prompt,
                persona_anchor=anchor,
            )

        raise ProviderError(f'modality no soportada en el worker: {modality}')

    try:
        results = await dispatch(
            conn=conn,
            modality=modality,
            call_fn=call_fn,
            audit_conn=conn,
        )
    except ProviderContentRejected as exc:
        await _mark_failed(conn, gen_id, f'content_rejected: {exc}')
        return WorkerResult(gen_id, 'failed', 'content_rejected', 0)
    except ProviderError as exc:
        await _mark_failed(conn, gen_id, f'provider_error: {exc}')
        return WorkerResult(gen_id, 'failed', 'provider_error', 0)
    except Exception as exc:  # noqa: BLE001 — log + mark failed
        logger.exception('worker unexpected error gen_id=%s', gen_id)
        await _mark_failed(conn, gen_id, f'unexpected: {exc!r}')
        return WorkerResult(gen_id, 'failed', 'unexpected', 0)

    # `results` puede ser una lista (image, count>1) o un dataclass (video/audio).
    items = results if isinstance(results, list) else [results]
    assets_created = 0
    for idx, item in enumerate(items):
        payload, mime, dims = _extract_asset_bytes(item)
        storage_key = (
            f'tenants/{tenant_id}/influencer/personas/{persona_id}/'
            f'generations/{gen_id}/{idx}'
        )
        await uploader(storage_key, payload, mime)
        await conn.execute(
            '''
            insert into influencer.assets
              (tenant_id, persona_id, generation_id, kind, storage_key,
               mime, width, height, duration_s, bytes)
            values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ''',
            tenant_id, persona_id, gen_id, kind, storage_key, mime,
            dims.get('width'), dims.get('height'), dims.get('duration_s'),
            len(payload),
        )
        assets_created += 1

    await conn.execute(
        '''
        update influencer.generations
        set status = 'succeeded', completed_at = now()
        where id = $1
        ''',
        gen_id,
    )
    return WorkerResult(gen_id, 'succeeded', None, assets_created)


async def _mark_failed(
    conn: asyncpg.Connection, gen_id: UUID, error: str,
) -> None:
    await conn.execute(
        '''
        update influencer.generations
        set status = 'failed', error_message = $1, completed_at = now()
        where id = $2
        ''',
        error, gen_id,
    )


# ─── Worker para face_variation_requests (UI-INFLU-014.1) ──────────────────
# La tabla `influencer.face_variation_requests` es separada de
# `influencer.generations` (decisión histórica de TASK-INFLU-010 para
# permitir variaciones rápidas en el wizard sin afectar el catálogo de
# generaciones). Este worker procesa SOLO esa cola y persiste assets con
# `kind='face_variation'` + FK `face_variation_request_id`.


async def claim_next_face_variation_request(
    conn: asyncpg.Connection,
) -> asyncpg.Record | None:
    """Toma un request pendiente de face_variation_requests con SKIP LOCKED."""
    return await conn.fetchrow(
        '''
        select * from influencer.face_variation_requests
        where status = 'queued'
        order by requested_at
        for update skip locked
        limit 1
        '''
    )


async def process_one_face_variation_request(
    *,
    conn: asyncpg.Connection,
    request_row: asyncpg.Record,
    storage_upload: StorageUploader | None = None,
) -> WorkerResult:
    """Procesa un face_variation_request end-to-end (image modality).

    Mismo patrón que ``process_one_generation`` pero:
    - lee de ``face_variation_requests`` (no de ``generations``)
    - usa el ``prompt_used`` ya construido por el endpoint POST
    - persiste assets con ``kind='face_variation'`` +
      ``face_variation_request_id`` para que el frontend pueda hacer GET
      del status y obtener las URLs.
    """
    req_id: UUID = request_row['id']
    persona_id: UUID = request_row['persona_id']
    tenant_id: UUID = request_row['tenant_id']
    count: int = request_row['requested_count']
    prompt: str = request_row['prompt_used'] or ''
    uploader: StorageUploader = storage_upload or _noop_uploader

    await conn.execute(
        '''
        update influencer.face_variation_requests
        set status = 'in_progress', started_at = now()
        where id = $1
        ''',
        req_id,
    )

    persona = await conn.fetchrow(
        'select * from influencer.personas where id = $1',
        persona_id,
    )
    if persona is None:
        await _mark_fvr_failed(conn, req_id, 'persona disappeared')
        return WorkerResult(req_id, 'failed', 'persona disappeared', 0)

    anchor = _build_persona_anchor(persona)

    async def call_fn(provider: ResolvedProvider) -> Any:
        adapter = make_adapter_for_provider(provider)
        if not isinstance(adapter, ImageProvider):
            raise ProviderError(
                f'{provider.provider} no implementa ImageProvider para '
                f'face_variation (modality=image)',
            )
        return await adapter.generate_image(
            prompt=prompt,
            persona_anchor=anchor,
            count=count,
            format='1:1',
            safety_mode=True,
        )

    try:
        results = await dispatch(
            conn=conn, modality='image', call_fn=call_fn, audit_conn=conn,
        )
    except ProviderContentRejected as exc:
        await _mark_fvr_failed(conn, req_id, f'content_rejected: {exc}')
        return WorkerResult(req_id, 'failed', 'content_rejected', 0)
    except ProviderError as exc:
        await _mark_fvr_failed(conn, req_id, f'provider_error: {exc}')
        return WorkerResult(req_id, 'failed', 'provider_error', 0)
    except Exception as exc:  # noqa: BLE001
        logger.exception('face_variation worker unexpected req_id=%s', req_id)
        await _mark_fvr_failed(conn, req_id, f'unexpected: {exc!r}')
        return WorkerResult(req_id, 'failed', 'unexpected', 0)

    items = results if isinstance(results, list) else [results]
    assets_created = 0
    for idx, item in enumerate(items):
        payload, mime, dims = _extract_asset_bytes(item)
        storage_key = (
            f'tenants/{tenant_id}/influencer/personas/{persona_id}/'
            f'face_variations/{req_id}/{idx}'
        )
        await uploader(storage_key, payload, mime)
        await conn.execute(
            '''
            insert into influencer.assets
              (tenant_id, persona_id, face_variation_request_id, kind,
               storage_key, mime, width, height, bytes)
            values ($1, $2, $3, 'face_variation', $4, $5, $6, $7, $8)
            ''',
            tenant_id, persona_id, req_id, storage_key, mime,
            dims.get('width'), dims.get('height'), len(payload),
        )
        assets_created += 1

    await conn.execute(
        '''
        update influencer.face_variation_requests
        set status = 'completed', completed_at = now()
        where id = $1
        ''',
        req_id,
    )
    return WorkerResult(req_id, 'succeeded', None, assets_created)


async def _mark_fvr_failed(
    conn: asyncpg.Connection, req_id: UUID, error: str,
) -> None:
    await conn.execute(
        '''
        update influencer.face_variation_requests
        set status = 'failed', error_message = $1, completed_at = now()
        where id = $2
        ''',
        error, req_id,
    )


__all__ = [
    'StorageUploader',
    'WorkerResult',
    '_KIND_TO_MODALITY',
    '_build_persona_anchor',
    '_extract_asset_bytes',
    '_noop_uploader',
    'claim_next_generation',
    'claim_next_face_variation_request',
    'process_one_generation',
    'process_one_face_variation_request',
]
