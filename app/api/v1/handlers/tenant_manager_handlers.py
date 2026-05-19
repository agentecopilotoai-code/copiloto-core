"""Handlers extracted from routes.py for tenant_manager_router.

Original location: app/api/v1/routes.py (refactor step 3).
"""
from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import Depends, HTTPException, Request, Response, status

from app.api.v1._helpers.normalizers import _digest_subscription_to_dict
from app.api.v1._helpers.validators import _validate_digest_recipients
from app.api.v1.routes import (
    ensure_tenant_access,
    tenant_manager_router,
)
from app.api.v1.schemas import DigestSubscriptionCreate, DigestSubscriptionUpdate
from app.db.pool import get_db
from app.services.audit import audit


@tenant_manager_router.get('/tenants/{tenant_id}/digest/subscriptions')
async def list_digest_subscriptions(
    tenant_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        """
        select id, recipient_email, recipient_whatsapp, cadence, enabled,
               last_sent_at, created_at, updated_at
        from app.digest_subscriptions
        where tenant_id=$1
        order by cadence, created_at
        """,
        tenant_id,
    )
    return {
        'tenant_id': str(tenant_id),
        'subscriptions': [_digest_subscription_to_dict(row) for row in rows],
    }


# BUG-036: en tenant_manager_router (manager+).
@tenant_manager_router.post(
    '/tenants/{tenant_id}/digest/subscriptions', status_code=status.HTTP_201_CREATED
)
async def create_digest_subscription(
    tenant_id: UUID,
    payload: DigestSubscriptionCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    _validate_digest_recipients(payload.recipient_email, payload.recipient_whatsapp)
    row = await conn.fetchrow(
        """
        insert into app.digest_subscriptions
          (tenant_id, recipient_email, recipient_whatsapp, cadence, enabled)
        values ($1, nullif($2, ''), nullif($3, ''), $4, $5)
        returning id, recipient_email, recipient_whatsapp, cadence, enabled,
                  last_sent_at, created_at, updated_at
        """,
        tenant_id,
        (payload.recipient_email or '').strip(),
        (payload.recipient_whatsapp or '').strip(),
        payload.cadence,
        payload.enabled,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='digest.subscription_created',
        entity_type='digest_subscription',
        entity_id=str(row['id']),
    )
    return _digest_subscription_to_dict(row)


# BUG-036: en tenant_manager_router (manager+).
@tenant_manager_router.patch(
    '/tenants/{tenant_id}/digest/subscriptions/{subscription_id}'
)
async def update_digest_subscription(
    tenant_id: UUID,
    subscription_id: UUID,
    payload: DigestSubscriptionUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    current = await conn.fetchrow(
        """
        select id, recipient_email, recipient_whatsapp, cadence, enabled
        from app.digest_subscriptions
        where tenant_id=$1 and id=$2
        """,
        tenant_id, subscription_id,
    )
    if current is None:
        raise HTTPException(status_code=404, detail='subscription_not_found')
    new_email = payload.recipient_email if payload.recipient_email is not None else current['recipient_email']
    new_whatsapp = payload.recipient_whatsapp if payload.recipient_whatsapp is not None else current['recipient_whatsapp']
    _validate_digest_recipients(new_email, new_whatsapp)
    new_cadence = payload.cadence or current['cadence']
    new_enabled = current['enabled'] if payload.enabled is None else payload.enabled
    row = await conn.fetchrow(
        """
        update app.digest_subscriptions
        set recipient_email = nullif($3, ''),
            recipient_whatsapp = nullif($4, ''),
            cadence = $5,
            enabled = $6,
            updated_at = now()
        where tenant_id=$1 and id=$2
        returning id, recipient_email, recipient_whatsapp, cadence, enabled,
                  last_sent_at, created_at, updated_at
        """,
        tenant_id,
        subscription_id,
        (new_email or '').strip(),
        (new_whatsapp or '').strip(),
        new_cadence,
        new_enabled,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='digest.subscription_updated',
        entity_type='digest_subscription',
        entity_id=str(subscription_id),
    )
    return _digest_subscription_to_dict(row)


# BUG-036: en tenant_manager_router (manager+).
@tenant_manager_router.delete(
    '/tenants/{tenant_id}/digest/subscriptions/{subscription_id}',
    status_code=204,
)
async def delete_digest_subscription(
    tenant_id: UUID,
    subscription_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    result = await conn.execute(
        'delete from app.digest_subscriptions where tenant_id=$1 and id=$2',
        tenant_id, subscription_id,
    )
    if result.endswith(' 0'):
        raise HTTPException(status_code=404, detail='subscription_not_found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='digest.subscription_deleted',
        entity_type='digest_subscription',
        entity_id=str(subscription_id),
    )
    return Response(status_code=204)
