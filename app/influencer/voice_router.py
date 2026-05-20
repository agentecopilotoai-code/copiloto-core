"""Voice sample + captions preview — TASK-INFLU-013."""
from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.security import authenticate_request
from app.db.pool import get_db
from app.influencer import ensure_module_enabled
from app.influencer.personas_router import _set_tenant_scope

logger = logging.getLogger(__name__)


SAMPLE_DEFAULT_TEXT = (
    'Hola chicas, hoy os traigo mi look favorito del verano. '
    'Espero que os guste y me contéis qué pensáis en los comentarios.'
)

PlatformKind = Literal['ig', 'tiktok', 'story']

# Plantilla determinista del system prompt — usada por TASK-INFLU-013
# para condicionar el LLM con la voz del personaje. La función pública
# `build_caption_system_prompt` la consume; los tests verifican que
# diferentes tonos producen prompts distintos.
_SYSTEM_PROMPT_TEMPLATE = (
    'Eres una influencer virtual con la siguiente voz:\n'
    '- Tono: {tone}\n'
    '- Formalidad: {formality}\n'
    '- Energía: {energy_level}/10\n\n'
    'Escribe captions cortos, auténticos y consistentes con esta voz. '
    'No menciones que eres IA — la disclosure va por separado.'
)


def build_caption_system_prompt(voice_jsonb: dict | None) -> str:
    """Construye el system prompt para el LLM a partir del jsonb voice."""
    voice = voice_jsonb or {}
    return _SYSTEM_PROMPT_TEMPLATE.format(
        tone=voice.get('tone', 'neutral'),
        formality=voice.get('formality', 'neutral'),
        energy_level=int(voice.get('energy_level', 5) or 5),
    )


# ─── Models ────────────────────────────────────────────────────────────────


class SampleRequest(BaseModel):
    sample_text: str | None = Field(default=None, max_length=500)


class SampleResponse(BaseModel):
    generation_id: UUID
    status: str
    sample_text_used: str


class CaptionsPreviewRequest(BaseModel):
    platforms: list[PlatformKind] = Field(
        default_factory=lambda: ['ig', 'tiktok', 'story'],
        max_length=3,
    )


class CaptionsPreviewResponse(BaseModel):
    captions: dict[PlatformKind, str]
    voice_prompt_used: str


# ─── Router ────────────────────────────────────────────────────────────────


voice_router = APIRouter(
    prefix='/v1/influencer/personas/{persona_id}/voice',
    tags=['influencer-voice'],
    dependencies=[
        Depends(authenticate_request),
        Depends(ensure_module_enabled),
    ],
)


def _require_tenant_id(request: Request) -> UUID:
    tenant_id = getattr(request.state, 'tenant_id', None)
    if tenant_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'module not available')
    return tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))


@voice_router.post(
    '/sample',
    response_model=SampleResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary='Encola un voice_sample (TTS) del personaje',
)
async def create_voice_sample(
    persona_id: UUID,
    request: Request,
    body: SampleRequest = SampleRequest(),
    conn: asyncpg.Connection = Depends(get_db),
) -> SampleResponse:
    tenant_id = _require_tenant_id(request)
    user_id = getattr(request.state, 'user_id', None)
    await _set_tenant_scope(conn, tenant_id)

    persona = await conn.fetchrow(
        'select id, voice, status from influencer.personas where id = $1',
        persona_id,
    )
    if persona is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'persona not found')
    if persona['status'] == 'archived':
        raise HTTPException(
            status.HTTP_409_CONFLICT, 'cannot generate for archived persona',
        )

    text = body.sample_text or SAMPLE_DEFAULT_TEXT
    import json
    voice = persona['voice'] if isinstance(persona['voice'], dict) else {}
    params = {'voice_traits': voice, 'sample_text': text}

    # Reuse `generations` queue — kind='voice_sample', cost fijo de 1
    # crédito (estimate provisional; TASK-INFLU-016 lo conecta con la
    # tabla pricing real).
    row = await conn.fetchrow(
        '''
        insert into influencer.generations
          (tenant_id, persona_id, kind, prompt, format, count_requested,
           status, cost_credits, params, requested_by)
        values
          ($1, $2, 'voice_sample', $3, '1:1', 1, 'queued', 1, $4, $5)
        returning id, status
        ''',
        tenant_id, persona_id, text, json.dumps(params), user_id,
    )
    return SampleResponse(
        generation_id=row['id'],
        status=row['status'],
        sample_text_used=text,
    )


@voice_router.post(
    '/captions-preview',
    response_model=CaptionsPreviewResponse,
    summary='Genera captions de prueba (inline, no async)',
)
async def captions_preview(
    persona_id: UUID,
    request: Request,
    body: CaptionsPreviewRequest = CaptionsPreviewRequest(),
    conn: asyncpg.Connection = Depends(get_db),
) -> CaptionsPreviewResponse:
    tenant_id = _require_tenant_id(request)
    await _set_tenant_scope(conn, tenant_id)

    persona = await conn.fetchrow(
        'select voice, identity, status from influencer.personas where id = $1',
        persona_id,
    )
    if persona is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'persona not found')
    if persona['status'] == 'archived':
        raise HTTPException(status.HTTP_409_CONFLICT, 'persona archived')

    system_prompt = build_caption_system_prompt(persona['voice'])

    # Generación inline — en producción se llamaría al `provider_dispatcher`
    # con modality='llm' aquí. En esta tarea devolvemos placeholders
    # deterministas que demuestran la diferencia por plataforma; el
    # caller real swappea esto cuando el dispatcher esté cableado en el
    # entrypoint HTTP (sub-tarea de TASK-INFLU-018).
    base = {
        'ig': 'Ig: look del día, fresca y elegante. ¿Qué opináis? #ootd',
        'tiktok': 'TikTok: si tuviera que elegir un solo outfit este verano sería este 🌞',
        'story': 'Story: nuevo look hoy, swipe para ver más detalles ⬆️',
    }
    captions: dict[PlatformKind, str] = {
        p: base[p] for p in body.platforms if p in base
    }
    return CaptionsPreviewResponse(
        captions=captions, voice_prompt_used=system_prompt,
    )


__all__ = ['voice_router', 'SAMPLE_DEFAULT_TEXT', 'build_caption_system_prompt']
