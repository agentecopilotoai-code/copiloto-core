"""``POST /generate`` + lookup de generations + assets — TASK-INFLU-011.

Los workers (TASK-INFLU-012) consumen las filas con
``status='queued'``, llaman al `provider_dispatcher`, y persisten los
resultados en `influencer.assets`. El cliente ve el status via GET o
WebSocket (TASK-INFLU-018).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.security import authenticate_request
from app.db.pool import get_db
from app.influencer import ensure_module_enabled
from app.influencer.personas_router import _set_tenant_scope

logger = logging.getLogger(__name__)


# ─── Models ────────────────────────────────────────────────────────────────


GenerationKind = Literal[
    'photo', 'reel', 'carousel', 'story', 'ad',
    'face_variation', 'voice_sample',
]
GenerationStatus = Literal['queued', 'running', 'succeeded', 'failed', 'canceled']
GenerationFormat = Literal['1:1', '4:5', '9:16', '16:9']


# Formatos permitidos por `kind`. reel/story son verticales 9:16.
# ad puede ser horizontal o cuadrado (uso en feed o stories).
_KIND_FORMAT_RULES: dict[str, set[str]] = {
    'photo': {'1:1', '4:5', '9:16', '16:9'},
    'reel': {'9:16'},
    'carousel': {'1:1', '4:5'},
    'story': {'9:16'},
    'ad': {'1:1', '4:5', '9:16', '16:9'},
    'face_variation': {'1:1', '4:5'},
    'voice_sample': {'1:1'},  # audio — no aplica pero requiere algo válido
}


class GenerateRequest(BaseModel):
    kind: GenerationKind
    prompt: str = Field(default='', max_length=1000)
    format: GenerationFormat = '1:1'
    count: int = Field(default=1, ge=1, le=10)
    params: dict[str, Any] = Field(default_factory=dict)


class GenerationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    persona_id: UUID
    kind: GenerationKind
    prompt: str
    format: str
    count_requested: int
    status: GenerationStatus
    provider_used: str | None = None
    cost_credits: int
    params: dict[str, Any]
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class AssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    persona_id: UUID
    generation_id: UUID | None
    kind: str
    storage_key: str
    mime: str
    width: int | None = None
    height: int | None = None
    duration_s: float | None = None
    bytes: int | None = None
    marked_canonical: bool


class GenerationDetailResponse(BaseModel):
    generation: GenerationResponse
    assets: list[AssetResponse]


class GenerationsList(BaseModel):
    items: list[GenerationResponse]
    total: int


# ─── Routers ───────────────────────────────────────────────────────────────


generate_router = APIRouter(
    prefix='/v1/influencer/personas/{persona_id}',
    tags=['influencer-generate'],
    dependencies=[
        Depends(authenticate_request),
        Depends(ensure_module_enabled),
    ],
)

generations_router = APIRouter(
    prefix='/v1/influencer',
    tags=['influencer-generations'],
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


def _validate_format_for_kind(kind: str, fmt: str) -> None:
    allowed = _KIND_FORMAT_RULES.get(kind, set())
    if fmt not in allowed:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f'format {fmt!r} not valid for kind={kind!r}; allowed: {sorted(allowed)}',
        )


def _row_to_generation(row: asyncpg.Record) -> GenerationResponse:
    return GenerationResponse(
        id=row['id'],
        tenant_id=row['tenant_id'],
        persona_id=row['persona_id'],
        kind=row['kind'],
        prompt=row['prompt'],
        format=row['format'],
        count_requested=row['count_requested'],
        status=row['status'],
        provider_used=row['provider_used'],
        cost_credits=row['cost_credits'],
        params=row['params'] if isinstance(row['params'], dict) else {},
        error_message=row['error_message'],
        created_at=row['created_at'],
        started_at=row['started_at'],
        completed_at=row['completed_at'],
    )


def _row_to_asset(row: asyncpg.Record) -> AssetResponse:
    return AssetResponse(
        id=row['id'],
        persona_id=row['persona_id'],
        generation_id=row['generation_id'],
        kind=row['kind'],
        storage_key=row['storage_key'],
        mime=row['mime'],
        width=row['width'],
        height=row['height'],
        duration_s=row['duration_s'],
        bytes=row['bytes'],
        marked_canonical=row['marked_canonical'],
    )


# ─── POST /generate ────────────────────────────────────────────────────────


@generate_router.post(
    '/generate',
    response_model=GenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary='Encola una generación (foto/reel/carousel/story/ad/voice)',
)
async def create_generation(
    persona_id: UUID,
    request: Request,
    body: GenerateRequest,
    conn: asyncpg.Connection = Depends(get_db),
) -> GenerationResponse:
    tenant_id = _require_tenant_id(request)
    user_id = getattr(request.state, 'user_id', None)
    await _set_tenant_scope(conn, tenant_id)

    _validate_format_for_kind(body.kind, body.format)

    persona = await conn.fetchrow(
        'select id, status from influencer.personas where id = $1', persona_id,
    )
    if persona is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'persona not found')
    if persona['status'] == 'archived':
        raise HTTPException(
            status.HTTP_409_CONFLICT, 'cannot generate for archived persona',
        )
    if persona['status'] != 'active':
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f'persona is in status={persona["status"]!r}, must be active',
        )

    # cost_credits provisional — TASK-INFLU-016 lo conecta con
    # generation_pricing real. Por ahora se calcula con un map sencillo.
    cost = _estimate_cost(body.kind, body.count)

    import json
    row = await conn.fetchrow(
        '''
        insert into influencer.generations
          (tenant_id, persona_id, kind, prompt, format, count_requested,
           status, cost_credits, params, requested_by)
        values
          ($1, $2, $3, $4, $5, $6, 'queued', $7, $8, $9)
        returning *
        ''',
        tenant_id, persona_id, body.kind, body.prompt, body.format,
        body.count, cost, json.dumps(body.params), user_id,
    )
    logger.info(
        'generation queued tenant=%s persona=%s kind=%s cost=%d id=%s',
        tenant_id, persona_id, body.kind, cost, row['id'],
    )
    return _row_to_generation(row)


def _estimate_cost(kind: str, count: int) -> int:
    """Cost estimate provisional. TASK-INFLU-016 lo conecta con la
    tabla `generation_pricing` real (por provider + kind)."""
    base = {
        'photo': 2,
        'reel': 10,
        'carousel': 5,
        'story': 3,
        'ad': 8,
        'face_variation': 1,
        'voice_sample': 1,
    }.get(kind, 5)
    return base * max(1, count)


# ─── GET lookup ────────────────────────────────────────────────────────────


@generations_router.get(
    '/generations/{generation_id}',
    response_model=GenerationDetailResponse,
    summary='Estado + assets de una generación',
)
async def get_generation(
    generation_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> GenerationDetailResponse:
    tenant_id = _require_tenant_id(request)
    await _set_tenant_scope(conn, tenant_id)

    gen = await conn.fetchrow(
        'select * from influencer.generations where id = $1', generation_id,
    )
    if gen is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'generation not found')

    assets = await conn.fetch(
        'select * from influencer.assets where generation_id = $1 order by created_at',
        generation_id,
    )
    return GenerationDetailResponse(
        generation=_row_to_generation(gen),
        assets=[_row_to_asset(a) for a in assets],
    )


@generate_router.get(
    '/generations',
    response_model=GenerationsList,
    summary='Generaciones de un personaje (paginado)',
)
async def list_generations(
    persona_id: UUID,
    request: Request,
    kind: GenerationKind | None = None,
    status_filter: GenerationStatus | None = Query(default=None, alias='status'),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    conn: asyncpg.Connection = Depends(get_db),
) -> GenerationsList:
    tenant_id = _require_tenant_id(request)
    await _set_tenant_scope(conn, tenant_id)

    where = ['persona_id = $1']
    params: list = [persona_id]
    if kind:
        params.append(kind)
        where.append(f'kind = ${len(params)}')
    if status_filter:
        params.append(status_filter)
        where.append(f'status = ${len(params)}')
    params.extend([limit, offset])

    sql = (
        f'select * from influencer.generations '
        f'where {" and ".join(where)} '
        f'order by created_at desc '
        f'limit ${len(params) - 1} offset ${len(params)}'
    )
    rows = await conn.fetch(sql, *params)
    total_row = await conn.fetchrow(
        f'select count(*) as c from influencer.generations where {" and ".join(where[:-0] or ["persona_id = $1"])}',
        *params[: len(params) - 2],
    )
    return GenerationsList(
        items=[_row_to_generation(r) for r in rows],
        total=int(total_row['c']) if total_row else 0,
    )


__all__ = [
    'generate_router',
    'generations_router',
    '_KIND_FORMAT_RULES',
    '_estimate_cost',
]
