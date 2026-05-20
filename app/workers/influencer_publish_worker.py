"""``publish_worker`` — TASK-INFLU-015.

Cron cada 60s: toma posts con ``status='approved' AND scheduled_at <=
now()`` via ``FOR UPDATE SKIP LOCKED`` y publica en cada platform de
``post.platforms``.

Flujo por post:
1. Mark ``status='publishing'``.
2. Para cada platform:
   a. Resuelve token desde `platform_connections.oauth_token_ref` →
      `app.platform_secrets`.
   b. Llama API (Instagram Graph: POST /me/media → POST /me/media_publish).
   c. Guarda `external_post_ids[platform] = <id>`.
3. Aplica `apply_ai_disclosure(caption, disclose_ai)` ANTES de publicar.
4. Mark ``status='published'`` + `published_at=now()`.
5. Si falla en alguna platform: status='failed' + error_message.

Rate limits (Instagram: 200 calls/hr per user): se manejan con
exponential backoff en el publisher inyectable.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

import asyncpg

from app.influencer.posts_router import apply_ai_disclosure

logger = logging.getLogger(__name__)


PublishFn = Callable[
    [str, str, str, str, dict],  # (platform, access_token, caption, kind, params)
    Awaitable[str],  # external_post_id
]
"""Publisher inyectable. Producción usa Instagram Graph API (httpx);
tests inyectan un mock. Lanza excepción en error retryable; el worker
maneja status='failed' con el error_message."""


@dataclass
class PublishResult:
    post_id: UUID
    status: str  # 'published' | 'failed'
    external_post_ids: dict[str, str]
    error: str | None


async def claim_next_approved_post(
    conn: asyncpg.Connection,
) -> asyncpg.Record | None:
    """``FOR UPDATE SKIP LOCKED`` sobre posts approved y vencidos."""
    return await conn.fetchrow(
        '''
        select p.*, per.disclose_ai
        from influencer.posts p
        join influencer.personas per on per.id = p.persona_id
        where p.status = 'approved' and p.scheduled_at <= now()
        order by p.scheduled_at
        for update of p skip locked
        limit 1
        '''
    )


async def resolve_token(
    conn: asyncpg.Connection,
    *,
    persona_id: UUID,
    platform: str,
) -> str | None:
    """Resuelve el access_token desde platform_connections + platform_secrets.

    Devuelve None si no hay conexión activa o el secret_ref no resuelve.
    """
    row = await conn.fetchrow(
        '''
        select pc.oauth_token_ref, pc.status, ps.hint
        from influencer.platform_connections pc
        left join app.platform_secrets ps
          on ps.secret_ref = pc.oauth_token_ref
        where pc.persona_id = $1 and pc.platform = $2
          and pc.status = 'connected'
        ''',
        persona_id, platform,
    )
    if row is None or not row['oauth_token_ref']:
        return None
    # En producción `app.services.whatsapp.resolve_secret_ref` resuelve
    # secret_ref → valor real. Aquí devolvemos el secret_ref como
    # sentinela; el publisher real conoce cómo bajar el valor a partir
    # del ref.
    return row['oauth_token_ref']


async def process_one_post(
    *,
    conn: asyncpg.Connection,
    post_row: asyncpg.Record,
    publish: PublishFn,
) -> PublishResult:
    """Publica un post en todas sus platforms. ``post_row`` ya está
    bloqueado en la transacción actual."""
    post_id: UUID = post_row['id']
    persona_id: UUID = post_row['persona_id']
    disclose_ai: bool = post_row['disclose_ai']
    caption: str = apply_ai_disclosure(post_row['caption'] or '', disclose_ai)
    kind: str = post_row['kind']
    platforms: list[str] = list(post_row['platforms'])

    await conn.execute(
        'update influencer.posts set status = \'publishing\' where id = $1',
        post_id,
    )

    external_ids: dict[str, str] = {}
    last_error: str | None = None

    for platform in platforms:
        token = await resolve_token(conn, persona_id=persona_id, platform=platform)
        if not token:
            last_error = f'no active connection for {platform}'
            break
        try:
            ext_id = await publish(platform, token, caption, kind, {})
        except Exception as exc:  # noqa: BLE001
            last_error = f'{platform}: {exc!r}'
            logger.exception(
                'publish failed post=%s platform=%s', post_id, platform,
            )
            break
        external_ids[platform] = ext_id

    if last_error is None:
        await conn.execute(
            '''
            update influencer.posts
            set status = 'published',
                published_at = now(),
                external_post_ids = $1
            where id = $2
            ''',
            json.dumps(external_ids), post_id,
        )
        return PublishResult(post_id, 'published', external_ids, None)

    await conn.execute(
        '''
        update influencer.posts
        set status = 'failed',
            error_message = $1,
            external_post_ids = $2
        where id = $3
        ''',
        last_error, json.dumps(external_ids), post_id,
    )
    return PublishResult(post_id, 'failed', external_ids, last_error)


__all__ = [
    'PublishFn',
    'PublishResult',
    'apply_ai_disclosure',
    'claim_next_approved_post',
    'resolve_token',
    'process_one_post',
]
