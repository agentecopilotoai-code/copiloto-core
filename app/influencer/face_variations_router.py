"""Generación async de variaciones de cara — TASK-INFLU-010.

Endpoint POST que encola un request; un worker (TASK-INFLU-012) lo
procesa con el `provider_dispatcher`. Cliente refresca con GET o
WebSocket (TASK-INFLU-018 monta el bus de eventos).
"""
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


face_variations_router = APIRouter(
    prefix='/v1/influencer/personas/{persona_id}/face',
    tags=['influencer-face-variations'],
    dependencies=[
        Depends(authenticate_request),
        Depends(ensure_module_enabled),
    ],
)


# ─── Models ────────────────────────────────────────────────────────────────


class VariationRequest(BaseModel):
    count: int = Field(default=4, ge=1, le=10)


class VariationRequestResponse(BaseModel):
    id: UUID
    persona_id: UUID
    requested_count: int
    status: Literal['queued', 'in_progress', 'completed', 'failed']
    prompt_used: str | None = None
    error_message: str | None = None


def _require_tenant_id(request: Request) -> UUID:
    tenant_id = getattr(request.state, 'tenant_id', None)
    if tenant_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'module not available')
    return tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))


def _build_prompt(face: dict) -> str:
    """Construye un prompt determinista a partir del jsonb face del paso 1.

    El image provider (Grok / OpenAI / SDXL local) recibe este prompt;
    el persona_anchor + reference_image_urls va aparte vía
    PersonaAnchor.
    """
    if not isinstance(face, dict) or not face:
        return 'portrait headshot, neutral background, professional photography'
    parts = [
        'portrait headshot',
        face.get('ethnicity', ''),
        f"{face.get('eye_color', '')} eyes",
        f"{face.get('hair_color', '')} {face.get('hair_style', '')} hair",
        f"skin tone {face.get('skin_tone', '')}",
        f"age range {face.get('age_range', '')}",
        'consistent identity, professional photography, neutral background',
    ]
    return ', '.join(p.strip() for p in parts if p.strip())


# ─── Endpoints ─────────────────────────────────────────────────────────────


@face_variations_router.post(
    '/variations',
    response_model=VariationRequestResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary='Encola N variaciones de cara (async)',
)
async def create_face_variations(
    persona_id: UUID,
    request: Request,
    body: VariationRequest = VariationRequest(),
    conn: asyncpg.Connection = Depends(get_db),
) -> VariationRequestResponse:
    tenant_id = _require_tenant_id(request)
    user_id = getattr(request.state, 'user_id', None)
    await _set_tenant_scope(conn, tenant_id)

    # Lee el face del persona para construir el prompt.
    persona = await conn.fetchrow(
        'select id, face, status from influencer.personas where id = $1',
        persona_id,
    )
    if persona is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'persona not found')
    if persona['status'] == 'archived':
        raise HTTPException(
            status.HTTP_409_CONFLICT, 'cannot generate for archived persona',
        )

    prompt = _build_prompt(persona['face'] or {})
    row = await conn.fetchrow(
        '''
        insert into influencer.face_variation_requests
          (tenant_id, persona_id, requested_count, status, prompt_used, requested_by)
        values ($1, $2, $3, 'queued', $4, $5)
        returning *
        ''',
        tenant_id, persona_id, body.count, prompt, user_id,
    )
    logger.info(
        'face_variation queued tenant=%s persona=%s count=%d req_id=%s',
        tenant_id, persona_id, body.count, row['id'],
    )
    return VariationRequestResponse(
        id=row['id'],
        persona_id=row['persona_id'],
        requested_count=row['requested_count'],
        status=row['status'],
        prompt_used=row['prompt_used'],
        error_message=row['error_message'],
    )


@face_variations_router.get(
    '/variations/{variation_request_id}',
    response_model=VariationRequestResponse,
    summary='Estado de un request de variaciones',
)
async def get_face_variation_status(
    persona_id: UUID,
    variation_request_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> VariationRequestResponse:
    tenant_id = _require_tenant_id(request)
    await _set_tenant_scope(conn, tenant_id)
    row = await conn.fetchrow(
        '''
        select * from influencer.face_variation_requests
        where id = $1 and persona_id = $2
        ''',
        variation_request_id, persona_id,
    )
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'variation request not found')
    return VariationRequestResponse(
        id=row['id'],
        persona_id=row['persona_id'],
        requested_count=row['requested_count'],
        status=row['status'],
        prompt_used=row['prompt_used'],
        error_message=row['error_message'],
    )


__all__ = ['face_variations_router', '_build_prompt']
