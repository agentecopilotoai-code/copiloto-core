"""Casting home + studio detail — read endpoints con stats. TASK-INFLU-017."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from app.core.security import authenticate_request
from app.db.pool import get_db
from app.influencer import ensure_module_enabled
from app.influencer.face_variations_router import _storage_key_to_url
from app.influencer.personas_router import _set_tenant_scope


STATS_CACHE_TTL = timedelta(hours=1)


# ─── Models ────────────────────────────────────────────────────────────────


class CastingKpis(BaseModel):
    active_personas: int
    posts_this_month: int
    total_reach: int
    avg_engagement: float


class PersonaCard(BaseModel):
    id: UUID
    name: str
    handle: str
    status: str
    category: str | None = None
    posts_total: int
    reach_30d: int
    engagement_rate: float
    # UI-INFLU-014.8: URL de la última variación generada (face_variation
    # más reciente) o canonical si existe. Null para drafts sin variaciones.
    avatar_url: str | None = None


class CastingResponse(BaseModel):
    kpis: CastingKpis
    personas: list[PersonaCard]


class StudioStats(BaseModel):
    posts_total: int
    reach_30d: int
    engagement_rate: float
    scheduled_count: int


class NextPost(BaseModel):
    id: UUID
    scheduled_at: datetime
    kind: str
    platforms: list[str]


class PlatformConn(BaseModel):
    platform: str
    external_handle: str | None
    status: str


class GenerationAssetLite(BaseModel):
    """Subset de `AssetResponse` con la URL ya resuelta para el frontend."""
    id: UUID
    storage_key: str
    url: str
    mime: str
    width: int | None = None
    height: int | None = None
    duration_s: float | None = None


class GenerationLite(BaseModel):
    id: UUID
    kind: str
    status: str
    prompt: str | None = None
    format: str | None = None
    cost_credits: int | None = None
    error_message: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    # UI-INFLU-014.13 — assets del job (vacío mientras status='queued').
    # El frontend renderiza el thumbnail desde aquí.
    assets: list[GenerationAssetLite] = Field(default_factory=list)


class FaceVariationLite(BaseModel):
    """Cada variación de cara del personaje, con URL renderizable."""
    id: UUID
    url: str
    thumbnail_url: str
    canonical: bool = False
    mime: str | None = None


class StudioResponse(BaseModel):
    persona: dict[str, Any]  # PersonaResponse-shaped, dict for brevity
    stats: StudioStats
    next_post: NextPost | None = None
    platforms_connected: list[PlatformConn] = Field(default_factory=list)
    recent_generations: list[GenerationLite] = Field(default_factory=list)
    # UI-INFLU-014.13 — variaciones de cara para el persona switcher
    # (avatar + thumbnails) en el header del studio.
    face_variations: list[FaceVariationLite] = Field(default_factory=list)


# ─── Router ────────────────────────────────────────────────────────────────


casting_router = APIRouter(
    prefix='/v1/influencer',
    tags=['influencer-casting'],
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


async def _get_or_refresh_stats(
    conn: asyncpg.Connection,
    persona_id: UUID,
    tenant_id: UUID,
) -> dict:
    """Lee `persona_stats_cache`; si está expirado o no existe, devuelve
    el row con `posts_total=0,...` (stub). El refresh real vía IG
    Insights se hace en un cron horario en producción (TASK-INFLU-018).
    """
    row = await conn.fetchrow(
        '''
        select posts_total, reach_30d, engagement_rate, scheduled_count, computed_at
        from influencer.persona_stats_cache
        where persona_id = $1
        ''',
        persona_id,
    )
    if row is not None:
        age = datetime.now(timezone.utc) - row['computed_at']
        if age <= STATS_CACHE_TTL:
            return {
                'posts_total': row['posts_total'],
                'reach_30d': row['reach_30d'],
                'engagement_rate': row['engagement_rate'],
                'scheduled_count': row['scheduled_count'],
            }

    # Cache miss o expirado — calcula stats básicas en línea (counts
    # baratos sobre posts) y persistencia para próximas lecturas. reach
    # / engagement reales vienen del cron de TASK-INFLU-018.
    counts = await conn.fetchrow(
        '''
        select
          count(*) filter (where status = 'published') as posts_total,
          count(*) filter (where status in ('scheduled', 'approved')) as scheduled_count
        from influencer.posts where persona_id = $1
        ''',
        persona_id,
    )
    stats = {
        'posts_total': int(counts['posts_total'] or 0),
        'reach_30d': int(row['reach_30d']) if row else 0,
        'engagement_rate': float(row['engagement_rate']) if row else 0.0,
        'scheduled_count': int(counts['scheduled_count'] or 0),
    }
    await conn.execute(
        '''
        insert into influencer.persona_stats_cache
          (persona_id, tenant_id, posts_total, reach_30d,
           engagement_rate, scheduled_count, computed_at)
        values ($1, $2, $3, $4, $5, $6, now())
        on conflict (persona_id) do update set
          posts_total = excluded.posts_total,
          scheduled_count = excluded.scheduled_count,
          computed_at = now()
        ''',
        persona_id, tenant_id, stats['posts_total'], stats['reach_30d'],
        stats['engagement_rate'], stats['scheduled_count'],
    )
    return stats


# ─── Endpoints ─────────────────────────────────────────────────────────────


@casting_router.get(
    '/casting',
    response_model=CastingResponse,
    summary='Home del casting: KPIs globales + lista de personas con stats',
)
async def get_casting(
    request: Request,
    category: str | None = Query(default=None, max_length=64),
    conn: asyncpg.Connection = Depends(get_db),
) -> CastingResponse:
    tenant_id = _require_tenant_id(request)
    await _set_tenant_scope(conn, tenant_id)

    # UI-INFLU-014.8: filtrar `tenant_id` EXPLÍCITAMENTE en el WHERE.
    # Sin esto, cuando el caller tiene `support_mode=true` (platform_owner),
    # la RLS `tenant_id = current OR support_mode='true'` permitía leer
    # personas de OTROS tenants (drafts viejos quedaban en el casting de
    # cualquier tenant que el platform_owner visitaba con support_mode).
    where_p = ['tenant_id = $1', "status <> 'archived'"]
    params: list = [tenant_id]
    if category:
        params.append(category)
        where_p.append(f'category = ${len(params)}')

    personas_rows = await conn.fetch(
        f'''
        select id, name, handle, status, category
        from influencer.personas
        where {' and '.join(where_p)}
        order by created_at desc
        ''',
        *params,
    )

    cards: list[PersonaCard] = []
    for p in personas_rows:
        stats = await _get_or_refresh_stats(conn, p['id'], tenant_id)
        # UI-INFLU-014.8: avatar = canonical primero, sino la última
        # face_variation generada. Usa el mismo proxy endpoint que el
        # wizard preview.
        avatar_row = await conn.fetchrow(
            '''
            select storage_key
            from influencer.assets
            where persona_id = $1 and kind = 'face_variation'
            order by marked_canonical desc, created_at desc
            limit 1
            ''',
            p['id'],
        )
        avatar_url = None
        if avatar_row:
            avatar_url = _storage_key_to_url(avatar_row['storage_key'])
        cards.append(
            PersonaCard(
                id=p['id'],
                name=p['name'],
                handle=p['handle'],
                status=p['status'],
                category=p['category'],
                posts_total=stats['posts_total'],
                reach_30d=stats['reach_30d'],
                engagement_rate=stats['engagement_rate'],
                avatar_url=avatar_url,
            ),
        )

    # KPIs globales
    active = sum(1 for c in cards if c.status == 'active')
    month_start = datetime.now(timezone.utc).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0,
    )
    posts_month_row = await conn.fetchrow(
        '''
        select count(*) as c from influencer.posts
        where status = 'published' and published_at >= $1
        ''',
        month_start,
    )
    total_reach = sum(c.reach_30d for c in cards)
    avg_eng = (
        sum(c.engagement_rate for c in cards) / len(cards)
        if cards else 0.0
    )

    return CastingResponse(
        kpis=CastingKpis(
            active_personas=active,
            posts_this_month=int(posts_month_row['c']) if posts_month_row else 0,
            total_reach=total_reach,
            avg_engagement=avg_eng,
        ),
        personas=cards,
    )


@casting_router.get(
    '/personas/{persona_id}/studio',
    response_model=StudioResponse,
    summary='Bundle del estudio del personaje (persona + stats + conexiones)',
)
async def get_studio(
    persona_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> StudioResponse:
    tenant_id = _require_tenant_id(request)
    await _set_tenant_scope(conn, tenant_id)

    persona = await conn.fetchrow(
        'select * from influencer.personas where id = $1',
        persona_id,
    )
    if persona is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'persona not found')

    stats = await _get_or_refresh_stats(conn, persona_id, tenant_id)

    next_post = await conn.fetchrow(
        '''
        select id, scheduled_at, kind, platforms
        from influencer.posts
        where persona_id = $1 and status in ('scheduled', 'approved')
          and scheduled_at >= now()
        order by scheduled_at
        limit 1
        ''',
        persona_id,
    )

    conns = await conn.fetch(
        '''
        select platform, external_handle, status
        from influencer.platform_connections
        where persona_id = $1 and status <> 'disconnected'
        order by platform
        ''',
        persona_id,
    )

    gens = await conn.fetch(
        '''
        select id, kind, status, prompt, format, cost_credits,
               error_message, created_at, completed_at
        from influencer.generations
        where persona_id = $1
        order by created_at desc
        limit 12
        ''',
        persona_id,
    )

    # UI-INFLU-014.13 — assets de cada generación. Una sola query
    # batch (`generation_id = ANY($1)`) en lugar de N queries.
    gen_ids = [g['id'] for g in gens]
    assets_rows: list[asyncpg.Record] = []
    if gen_ids:
        assets_rows = await conn.fetch(
            '''
            select id, generation_id, storage_key, mime, width, height, duration_s
            from influencer.assets
            where generation_id = ANY($1::uuid[])
            order by created_at
            ''',
            gen_ids,
        )
    assets_by_gen: dict[UUID, list[GenerationAssetLite]] = {}
    for a in assets_rows:
        assets_by_gen.setdefault(a['generation_id'], []).append(
            GenerationAssetLite(
                id=a['id'],
                storage_key=a['storage_key'],
                url=_storage_key_to_url(a['storage_key']),
                mime=a['mime'],
                width=a['width'],
                height=a['height'],
                duration_s=a['duration_s'],
            ),
        )

    # UI-INFLU-014.13 — face_variations + avatar canonical para el
    # persona switcher del studio. Devolvemos hasta 12; el frontend
    # muestra las primeras 5 + un "+".
    face_var_rows = await conn.fetch(
        '''
        select id, storage_key, mime, marked_canonical
        from influencer.assets
        where persona_id = $1 and kind = 'face_variation'
        order by marked_canonical desc, created_at desc
        limit 12
        ''',
        persona_id,
    )
    face_variations = [
        FaceVariationLite(
            id=fv['id'],
            url=_storage_key_to_url(fv['storage_key']),
            thumbnail_url=_storage_key_to_url(fv['storage_key']),
            canonical=fv['marked_canonical'],
            mime=fv['mime'],
        )
        for fv in face_var_rows
    ]
    avatar_url = face_variations[0].url if face_variations else None

    return StudioResponse(
        persona={
            'id': str(persona['id']),
            'name': persona['name'],
            'handle': persona['handle'],
            'status': persona['status'],
            'category': persona.get('category') if isinstance(persona, dict) else persona['category'],
            'avatar_url': avatar_url,
        },
        stats=StudioStats(**stats),
        next_post=(
            NextPost(
                id=next_post['id'],
                scheduled_at=next_post['scheduled_at'],
                kind=next_post['kind'],
                platforms=list(next_post['platforms']),
            )
            if next_post else None
        ),
        platforms_connected=[
            PlatformConn(
                platform=c['platform'],
                external_handle=c['external_handle'],
                status=c['status'],
            )
            for c in conns
        ],
        face_variations=face_variations,
        recent_generations=[
            GenerationLite(
                id=g['id'],
                kind=g['kind'],
                status=g['status'],
                prompt=g['prompt'],
                format=g['format'],
                cost_credits=g['cost_credits'],
                error_message=g['error_message'],
                created_at=g['created_at'],
                completed_at=g['completed_at'],
                assets=assets_by_gen.get(g['id'], []),
            )
            for g in gens
        ],
    )


__all__ = ['casting_router', 'STATS_CACHE_TTL']
