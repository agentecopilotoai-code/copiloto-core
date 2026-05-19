"""Tenant membership DB helpers extracted from app/api/v1/routes.py."""
from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import HTTPException

from app.db.pool import record_to_dict


_TENANT_MEMBER_ROLES = ('owner', 'admin', 'manager', 'agent', 'viewer')


async def _tenant_owner_count(conn: asyncpg.Connection, tenant_id: UUID) -> int:
    return int(
        await conn.fetchval(
            'select count(*) from app.user_tenant_roles where tenant_id=$1 and role=$2',
            tenant_id,
            'owner',
        )
    )


async def _tenant_member_payload(
    conn: asyncpg.Connection, tenant_id: UUID, user_id: UUID
) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        select u.id as user_id, u.auth_subject, u.email, u.display_name,
               u.status, u.last_login_at, u.created_at,
               array_agg(utr.role order by
                   case utr.role
                       when 'owner' then 1
                       when 'admin' then 2
                       when 'manager' then 3
                       when 'agent' then 4
                       when 'viewer' then 5
                       else 6
                   end
               ) as roles,
               bool_or(utr.is_default) as is_default_role
        from app.users u
        join app.user_tenant_roles utr on utr.user_id = u.id
        where u.id=$1 and utr.tenant_id=$2
        group by u.id
        """,
        user_id,
        tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Member not found')
    payload = record_to_dict(row)
    payload['roles'] = list(payload.get('roles') or [])
    return payload
