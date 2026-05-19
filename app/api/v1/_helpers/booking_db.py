"""Booking/availability DB helpers extracted from app/api/v1/routes.py."""
from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID

import asyncpg
from fastapi import HTTPException

from app.api.v1._helpers.parsing import parse_json_object


async def ensure_resource_available(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    resource_id: UUID,
    starts_at: datetime,
    ends_at: datetime,
    appointment_id: UUID | None = None,
) -> None:
    if starts_at >= ends_at:
        raise HTTPException(status_code=400, detail='Appointment starts_at must be before ends_at')

    resource = await conn.fetchrow(
        """
        select id, is_active
        from app.resources
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        resource_id,
    )
    if not resource:
        raise HTTPException(status_code=404, detail='Resource not found')
    if not resource['is_active']:
        raise HTTPException(status_code=409, detail='Resource is inactive')

    conflict = await conn.fetchrow(
        """
        select id, starts_at, ends_at, status
        from app.appointments
        where tenant_id=$1
          and resource_id=$2
          and status in ('scheduled','confirmed')
          and ($5::uuid is null or id <> $5)
          and tstzrange(starts_at, ends_at, '[)') && tstzrange($3, $4, '[)')
        order by starts_at
        limit 1
        """,
        tenant_id,
        resource_id,
        starts_at,
        ends_at,
        appointment_id,
    )
    if conflict:
        raise HTTPException(
            status_code=409,
            detail={
                'message': 'Resource has a conflicting appointment',
                'conflicting_appointment_id': str(conflict['id']),
                'starts_at': conflict['starts_at'].isoformat(),
                'ends_at': conflict['ends_at'].isoformat(),
                'status': conflict['status'],
            },
        )


async def appointment_detail(conn: asyncpg.Connection, tenant_id: UUID, appointment_id: UUID):
    return await conn.fetchrow(
        """
        select a.*, r.name as resource_name, r.code as resource_code, c.display_name as contact_label, c.phone_e164
        from app.appointments a
        join app.resources r on r.id=a.resource_id and r.tenant_id=a.tenant_id
        join app.contacts c on c.id=a.contact_id and c.tenant_id=a.tenant_id
        where a.tenant_id=$1 and a.id=$2
        """,
        tenant_id,
        appointment_id,
    )


async def fetch_service_duration(
    conn: asyncpg.Connection, tenant_id: UUID, service_id: UUID | None
) -> tuple[int | None, asyncpg.Record | None]:
    """Return (duration_minutes, service_row) for the given service or (None, None)."""
    if not service_id:
        return None, None
    row = await conn.fetchrow(
        'select id, name, duration_minutes, is_active from app.service_catalog where tenant_id=$1 and id=$2',
        tenant_id,
        service_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Service not found')
    return int(row['duration_minutes']), row


async def fetch_fallback_duration(conn: asyncpg.Connection, tenant_id: UUID) -> int:
    """Return tenant_settings.service_durations.default (in minutes), or 60."""
    raw = await conn.fetchval(
        "select escalation_policy->>'service_durations' from app.tenant_settings where tenant_id=$1",
        tenant_id,
    )
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                default_minutes = parsed.get('default')
                if isinstance(default_minutes, int) and default_minutes > 0:
                    return default_minutes
        except (json.JSONDecodeError, TypeError):
            pass
    settings_row = await conn.fetchval(
        'select escalation_policy from app.tenant_settings where tenant_id=$1',
        tenant_id,
    )
    parsed = parse_json_object(settings_row, default={})
    durations = parsed.get('service_durations') if isinstance(parsed, dict) else None
    if isinstance(durations, dict):
        default_minutes = durations.get('default')
        if isinstance(default_minutes, int) and default_minutes > 0:
            return default_minutes
    return 60
