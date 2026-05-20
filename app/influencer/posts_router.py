"""Posts + calendar endpoints — TASK-INFLU-015."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from app.core.security import authenticate_request
from app.db.pool import get_db
from app.influencer import ensure_module_enabled
from app.influencer.personas_router import _set_tenant_scope

logger = logging.getLogger(__name__)


PostKind = Literal['photo', 'reel', 'carousel', 'story', 'ad']
PostStatus = Literal['scheduled', 'approved', 'publishing', 'published', 'failed', 'canceled']
PostMode = Literal['draft', 'scheduled', 'approved']


AI_DISCLOSURE_SUFFIX = '\n\n#AI #generadoConIA'


def apply_ai_disclosure(caption: str, disclose_ai: bool) -> str:
    """Si la persona tiene `disclose_ai=True`, prepende los hashtags de
    disclosure al caption antes de publicar. Idempotente."""
    if not disclose_ai:
        return caption
    if '#AI' in caption or '#generadoConIA' in caption:
        return caption
    return caption + AI_DISCLOSURE_SUFFIX


# ─── Models ────────────────────────────────────────────────────────────────


class PostCreate(BaseModel):
    persona_id: UUID
    generation_id: UUID | None = None
    kind: PostKind
    caption: str = Field(default='', max_length=2200)
    hashtags: list[str] = Field(default_factory=list, max_length=30)
    scheduled_at: datetime
    platforms: list[str] = Field(..., min_length=1, max_length=6)
    mode: PostMode = 'scheduled'


class PostUpdate(BaseModel):
    caption: str | None = Field(default=None, max_length=2200)
    hashtags: list[str] | None = None
    scheduled_at: datetime | None = None
    status: Literal['scheduled', 'approved', 'canceled'] | None = None


class PostResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    persona_id: UUID
    generation_id: UUID | None
    kind: PostKind
    caption: str
    hashtags: list[str]
    scheduled_at: datetime
    platforms: list[str]
    status: PostStatus
    approved_at: datetime | None = None
    published_at: datetime | None = None
    external_post_ids: dict
    error_message: str | None = None


class CalendarItem(BaseModel):
    id: UUID
    persona_id: UUID
    scheduled_at: datetime
    kind: PostKind
    status: PostStatus
    platforms: list[str]


class CalendarResponse(BaseModel):
    items: list[CalendarItem]
    range_from: datetime
    range_to: datetime


# ─── Router ────────────────────────────────────────────────────────────────


posts_router = APIRouter(
    prefix='/v1/influencer',
    tags=['influencer-posts'],
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


def _row_to_post(row: asyncpg.Record) -> PostResponse:
    return PostResponse(
        id=row['id'],
        persona_id=row['persona_id'],
        generation_id=row['generation_id'],
        kind=row['kind'],
        caption=row['caption'],
        hashtags=list(row['hashtags']),
        scheduled_at=row['scheduled_at'],
        platforms=list(row['platforms']),
        status=row['status'],
        approved_at=row['approved_at'],
        published_at=row['published_at'],
        external_post_ids=row['external_post_ids'] if isinstance(row['external_post_ids'], dict) else {},
        error_message=row['error_message'],
    )


@posts_router.post(
    '/posts',
    response_model=PostResponse,
    status_code=status.HTTP_201_CREATED,
    summary='Crea un post para una persona',
)
async def create_post(
    request: Request,
    body: PostCreate,
    conn: asyncpg.Connection = Depends(get_db),
) -> PostResponse:
    tenant_id = _require_tenant_id(request)
    user_id = getattr(request.state, 'user_id', None)
    await _set_tenant_scope(conn, tenant_id)

    # Si mode='approved', se setea status='approved' + approved_at.
    initial_status = 'approved' if body.mode == 'approved' else 'scheduled'
    approved_at = datetime.utcnow() if body.mode == 'approved' else None
    approved_by = user_id if body.mode == 'approved' else None

    row = await conn.fetchrow(
        '''
        insert into influencer.posts
          (tenant_id, persona_id, generation_id, kind, caption, hashtags,
           scheduled_at, platforms, status, approved_by, approved_at)
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
        returning *
        ''',
        tenant_id, body.persona_id, body.generation_id, body.kind,
        body.caption, body.hashtags, body.scheduled_at,
        body.platforms, initial_status, approved_by, approved_at,
    )
    return _row_to_post(row)


@posts_router.patch(
    '/posts/{post_id}',
    response_model=PostResponse,
    summary='Update parcial / aprobar / reprogramar / cancelar',
)
async def update_post(
    post_id: UUID,
    request: Request,
    body: PostUpdate,
    conn: asyncpg.Connection = Depends(get_db),
) -> PostResponse:
    tenant_id = _require_tenant_id(request)
    user_id = getattr(request.state, 'user_id', None)
    await _set_tenant_scope(conn, tenant_id)

    updates = body.model_dump(exclude_unset=True)
    if not updates:
        row = await conn.fetchrow(
            'select * from influencer.posts where id = $1', post_id,
        )
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, 'post not found')
        return _row_to_post(row)

    set_clauses: list[str] = []
    params: list = []
    for col, val in updates.items():
        params.append(val)
        set_clauses.append(f'{col} = ${len(params)}')
        if col == 'status' and val == 'approved':
            params.append(datetime.utcnow())
            set_clauses.append(f'approved_at = ${len(params)}')
            params.append(user_id)
            set_clauses.append(f'approved_by = ${len(params)}')
    params.append(post_id)
    sql = (
        f'update influencer.posts set {", ".join(set_clauses)} '
        f'where id = ${len(params)} returning *'
    )
    row = await conn.fetchrow(sql, *params)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'post not found')
    return _row_to_post(row)


@posts_router.post(
    '/posts/{post_id}/cancel',
    response_model=PostResponse,
    summary='Cancela el post (no publica)',
)
async def cancel_post(
    post_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> PostResponse:
    tenant_id = _require_tenant_id(request)
    await _set_tenant_scope(conn, tenant_id)
    row = await conn.fetchrow(
        '''
        update influencer.posts
        set status = 'canceled'
        where id = $1 and status in ('scheduled', 'approved')
        returning *
        ''',
        post_id,
    )
    if row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            'post not found or not in cancelable state',
        )
    return _row_to_post(row)


@posts_router.get(
    '/calendar',
    response_model=CalendarResponse,
    summary='Vista de calendario (rango de fechas)',
)
async def get_calendar(
    request: Request,
    from_dt: datetime = Query(..., alias='from'),
    to_dt: datetime = Query(..., alias='to'),
    persona_id: UUID | None = Query(default=None),
    conn: asyncpg.Connection = Depends(get_db),
) -> CalendarResponse:
    tenant_id = _require_tenant_id(request)
    await _set_tenant_scope(conn, tenant_id)

    if (to_dt - from_dt).days > 90:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            'date range > 90 days not allowed (use pagination)',
        )

    where = [
        'tenant_id = $1',
        'scheduled_at >= $2',
        'scheduled_at < $3',
    ]
    params: list = [tenant_id, from_dt, to_dt]
    if persona_id:
        params.append(persona_id)
        where.append(f'persona_id = ${len(params)}')

    sql = (
        f'select id, persona_id, scheduled_at, kind, status, platforms '
        f'from influencer.posts where {" and ".join(where)} '
        'order by scheduled_at'
    )
    rows = await conn.fetch(sql, *params)
    items = [
        CalendarItem(
            id=r['id'],
            persona_id=r['persona_id'],
            scheduled_at=r['scheduled_at'],
            kind=r['kind'],
            status=r['status'],
            platforms=list(r['platforms']),
        )
        for r in rows
    ]
    return CalendarResponse(items=items, range_from=from_dt, range_to=to_dt)


__all__ = ['posts_router', 'apply_ai_disclosure', 'AI_DISCLOSURE_SUFFIX']
