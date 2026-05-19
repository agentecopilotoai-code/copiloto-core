"""Handlers extracted from routes.py for tenant_catalog_router.

Original location: app/api/v1/routes.py (refactor step 3).
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import Depends, HTTPException, Query, Request

from app.api.v1._helpers.booking_db import (
    fetch_fallback_duration,
    fetch_service_duration,
)
from app.api.v1._helpers.normalizers import (
    normalize_qualification_question,
    normalize_service_catalog_row,
)
from app.api.v1._helpers.projections import (
    QUALIFICATION_PROJECTION,
    SERVICE_CATALOG_PROJECTION,
)
from app.api.v1._helpers.slots import (
    compute_free_slots,
    parse_iso_date,
    working_hours_for_date,
)
from app.api.v1.routes import (
    ensure_tenant_access,
    tenant_catalog_router,
)
from app.db.pool import get_db


@tenant_catalog_router.get(
    '/tenants/{tenant_id}/resources/{resource_id}/availability'
)
async def resource_availability(
    tenant_id: UUID,
    resource_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    date: str = Query(..., description='Target date in YYYY-MM-DD format'),
    service_id: UUID | None = Query(default=None),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    target_date = parse_iso_date(date)
    resource = await conn.fetchrow(
        'select id, name, code, capabilities, is_active from app.resources where tenant_id=$1 and id=$2',
        tenant_id,
        resource_id,
    )
    if not resource:
        raise HTTPException(status_code=404, detail='Resource not found')
    if not resource['is_active']:
        return {
            'date': date,
            'resource_id': str(resource_id),
            'service_duration_minutes': 0,
            'slots': [],
        }
    duration, service_row = await fetch_service_duration(conn, tenant_id, service_id)
    if duration is None:
        duration = await fetch_fallback_duration(conn, tenant_id)
    franjas = working_hours_for_date(resource['capabilities'], target_date)
    if not franjas:
        return {
            'date': date,
            'resource_id': str(resource_id),
            'service_duration_minutes': duration,
            'slots': [],
        }
    day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)
    day_end = day_start.replace(hour=23, minute=59, second=59)
    busy_rows = await conn.fetch(
        """
        select starts_at, ends_at
        from app.appointments
        where tenant_id=$1
          and resource_id=$2
          and status in ('scheduled','confirmed')
          and starts_at < $4
          and ends_at > $3
        """,
        tenant_id,
        resource_id,
        day_start,
        day_end,
    )
    busy_intervals: list[tuple[int, int]] = []
    for busy in busy_rows:
        starts = busy['starts_at']
        ends = busy['ends_at']
        if not isinstance(starts, datetime) or not isinstance(ends, datetime):
            continue
        starts_local = starts.astimezone(UTC).replace(tzinfo=None)
        ends_local = ends.astimezone(UTC).replace(tzinfo=None)
        same_day_start = starts_local.replace(hour=0, minute=0, second=0, microsecond=0)
        if same_day_start.date() != target_date.date():
            continue
        busy_intervals.append((
            starts_local.hour * 60 + starts_local.minute,
            ends_local.hour * 60 + ends_local.minute,
        ))
    slots = compute_free_slots(franjas, busy_intervals, duration)
    return {
        'date': date,
        'resource_id': str(resource_id),
        'resource_name': resource['name'],
        'service_id': str(service_id) if service_id else None,
        'service_name': service_row['name'] if service_row else None,
        'service_duration_minutes': duration,
        'slots': slots,
    }


@tenant_catalog_router.get('/tenants/{tenant_id}/availability')
async def tenant_availability(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    date: str = Query(..., description='Target date in YYYY-MM-DD format'),
    service_id: UUID | None = Query(default=None),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    target_date = parse_iso_date(date)
    duration, service_row = await fetch_service_duration(conn, tenant_id, service_id)
    if duration is None:
        duration = await fetch_fallback_duration(conn, tenant_id)
    resources_rows = await conn.fetch(
        """
        select id, name, code, capabilities
        from app.resources
        where tenant_id=$1 and is_active=true
        order by name asc
        """,
        tenant_id,
    )
    day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=UTC)
    day_end = day_start.replace(hour=23, minute=59, second=59)
    busy_rows = await conn.fetch(
        """
        select resource_id, starts_at, ends_at
        from app.appointments
        where tenant_id=$1
          and status in ('scheduled','confirmed')
          and starts_at < $3
          and ends_at > $2
        """,
        tenant_id,
        day_start,
        day_end,
    )
    busy_by_resource: dict[UUID, list[tuple[int, int]]] = {}
    for busy in busy_rows:
        starts = busy['starts_at']
        ends = busy['ends_at']
        if not isinstance(starts, datetime) or not isinstance(ends, datetime):
            continue
        starts_local = starts.astimezone(UTC).replace(tzinfo=None)
        ends_local = ends.astimezone(UTC).replace(tzinfo=None)
        if starts_local.date() != target_date.date():
            continue
        busy_by_resource.setdefault(busy['resource_id'], []).append((
            starts_local.hour * 60 + starts_local.minute,
            ends_local.hour * 60 + ends_local.minute,
        ))
    resources_result: list[dict[str, Any]] = []
    for resource in resources_rows:
        franjas = working_hours_for_date(resource['capabilities'], target_date)
        slots = compute_free_slots(
            franjas, busy_by_resource.get(resource['id'], []), duration
        )
        resources_result.append({
            'resource_id': str(resource['id']),
            'resource_name': resource['name'],
            'resource_code': resource['code'],
            'slots': slots,
        })
    return {
        'date': date,
        'service_id': str(service_id) if service_id else None,
        'service_name': service_row['name'] if service_row else None,
        'service_duration_minutes': duration,
        'resources': resources_result,
    }


@tenant_catalog_router.get('/tenants/{tenant_id}/services')
async def list_services(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    include_inactive: bool = Query(default=False),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        f"""
        select {SERVICE_CATALOG_PROJECTION}
        from app.service_catalog
        where tenant_id=$1
          and ($2::boolean is true or is_active is true)
        order by sort_order asc, name asc
        """,
        tenant_id,
        include_inactive,
    )
    return [normalize_service_catalog_row(row) for row in rows]


@tenant_catalog_router.get('/tenants/{tenant_id}/qualification-questions')
async def list_qualification_questions(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        f"""
        select {QUALIFICATION_PROJECTION}
        from app.qualification_questions
        where tenant_id=$1
        order by position asc, created_at asc
        """,
        tenant_id,
    )
    return [normalize_qualification_question(row) for row in rows]
