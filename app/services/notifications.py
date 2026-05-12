"""Appointment notifications: confirmation, reminders and post-cita follow-ups.

Responsibilities
----------------
- Read ``tenant_settings.notification_settings`` (with safe defaults) and decide
  which reminder jobs to create when an appointment is scheduled, rescheduled
  or cancelled.
- Build the variable map (cliente, servicio, fecha, hora, profesional,
  dirección, link de Maps, instrucciones de preparación) that will be injected
  into the approved WhatsApp template at delivery time.
- Cancel pending jobs when the appointment is moved or cancelled.
"""
from __future__ import annotations

import json
from datetime import timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

import structlog

if TYPE_CHECKING:
    import asyncpg

log = structlog.get_logger()


DEFAULT_NOTIFICATION_SETTINGS: dict[str, Any] = {
    # TASK-0035: confirmation + reminders
    'confirmation_enabled': True,
    'reminder_24h_enabled': True,
    'reminder_1h_enabled': False,
    'include_location_link': True,
    'location_address': '',
    'location_maps_url': '',
    'include_preparation_notes': True,
    # TASK-0036: active confirmation
    'no_show_confirmation_enabled': True,
    'confirmation_reminder_hours': 4,
    # TASK-0036: post-cita
    'post_instructions_enabled': True,
    'post_instructions_delay_minutes': 30,
    'post_feedback_enabled': True,
    'post_feedback_delay_hours': 2,
    'post_rebooking_enabled': False,
    'post_rebooking_delay_days': 30,
    'post_rebooking_message': '',
    # TASK-0044: auto-rebooking when the client declines the active confirmation
    'auto_rebook_on_decline': True,
}

# Locale used for templates; tenants who need extra locales can register them
# in app.whatsapp_templates with the same purpose and the scheduler will pick
# whichever is approved.
DEFAULT_TEMPLATE_LOCALE = 'es'

# Purposes that fire on creation/scheduling
PURPOSES_ON_CREATE = (
    'appointment_confirmation',
    'appointment_reminder_24h',
    'appointment_reminder_1h',
    'no_show_confirmation_request',
)

# Purposes scheduled relative to ends_at
PURPOSES_POST_APPOINTMENT = (
    'post_appointment_instructions',
    'post_appointment_feedback',
    'post_appointment_rebooking',
)

ALL_NOTIFICATION_PURPOSES = PURPOSES_ON_CREATE + PURPOSES_POST_APPOINTMENT


def _coerce_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
    return value if isinstance(value, dict) else {}


def normalize_notification_settings(value: Any) -> dict[str, Any]:
    """Merge the stored notification_settings with the defaults."""
    parsed = _coerce_dict(value)
    merged = {**DEFAULT_NOTIFICATION_SETTINGS, **parsed}
    return merged


async def fetch_notification_settings(
    conn: asyncpg.Connection, tenant_id: UUID
) -> dict[str, Any]:
    raw = await conn.fetchval(
        'select notification_settings from app.tenant_settings where tenant_id=$1',
        tenant_id,
    )
    return normalize_notification_settings(raw)


def _format_local(dt) -> tuple[str, str]:
    """Return (date_str, time_str) in DD/MM/YYYY and HH:MM."""
    return dt.strftime('%d/%m/%Y'), dt.strftime('%H:%M')


def build_variables(
    *,
    contact_name: str | None,
    service_name: str | None,
    resource_name: str | None,
    starts_at,
    address: str | None,
    maps_url: str | None,
    preparation_notes: str | None,
    include_location: bool,
    include_preparation: bool,
) -> dict[str, str]:
    """Variables exposed to the template body. Stable order ``1..N``."""
    date_str, time_str = _format_local(starts_at)
    variables: dict[str, str] = {
        '1': contact_name or 'cliente',
        '2': service_name or 'tu cita',
        '3': date_str,
        '4': time_str,
        '5': resource_name or '',
    }
    if include_location and address:
        variables['6'] = address
        if maps_url:
            variables['7'] = maps_url
    if include_preparation and preparation_notes:
        slot = str(max(int(k) for k in variables) + 1)
        variables[slot] = preparation_notes
    return variables


def _scheduled_jobs_for_create(
    settings: dict[str, Any],
    starts_at,
) -> list[dict[str, Any]]:
    """Return the list of jobs to create when an appointment is scheduled."""
    jobs: list[dict[str, Any]] = []
    if settings['confirmation_enabled']:
        jobs.append({'purpose': 'appointment_confirmation', 'scheduled_for': starts_at - timedelta(seconds=0), 'immediate': True})
    if settings['reminder_24h_enabled']:
        jobs.append({'purpose': 'appointment_reminder_24h', 'scheduled_for': starts_at - timedelta(hours=24)})
    if settings['reminder_1h_enabled']:
        jobs.append({'purpose': 'appointment_reminder_1h', 'scheduled_for': starts_at - timedelta(hours=1)})
    if settings['no_show_confirmation_enabled']:
        hours_before = int(settings['confirmation_reminder_hours'])
        if hours_before > 0:
            jobs.append({
                'purpose': 'no_show_confirmation_request',
                'scheduled_for': starts_at - timedelta(hours=hours_before),
            })
    return jobs


def _scheduled_jobs_post_appointment(
    settings: dict[str, Any],
    ends_at,
) -> list[dict[str, Any]]:
    jobs: list[dict[str, Any]] = []
    if settings['post_instructions_enabled']:
        jobs.append({
            'purpose': 'post_appointment_instructions',
            'scheduled_for': ends_at + timedelta(minutes=int(settings['post_instructions_delay_minutes'])),
        })
    if settings['post_feedback_enabled']:
        jobs.append({
            'purpose': 'post_appointment_feedback',
            'scheduled_for': ends_at + timedelta(hours=int(settings['post_feedback_delay_hours'])),
        })
    if settings['post_rebooking_enabled']:
        jobs.append({
            'purpose': 'post_appointment_rebooking',
            'scheduled_for': ends_at + timedelta(days=int(settings['post_rebooking_delay_days'])),
        })
    return jobs


async def _appointment_context(
    conn: asyncpg.Connection, tenant_id: UUID, appointment_id: UUID
) -> dict[str, Any] | None:
    """Resolve service/resource/branch/contact/conversation/channel for the appointment."""
    row = await conn.fetchrow(
        """
        select a.id, a.starts_at, a.ends_at, a.conversation_id,
               a.service_id, a.resource_id, a.contact_id, a.branch_id,
               c.display_name as contact_name,
               cv.channel_id as channel_id,
               sc.name as service_name,
               sc.preparation_notes as preparation_notes,
               r.name as resource_name,
               b.address as branch_address,
               b.maps_url as branch_maps_url,
               b.phone_e164 as branch_phone,
               b.name as branch_name
        from app.appointments a
        left join app.contacts c on c.id=a.contact_id and c.tenant_id=a.tenant_id
        left join app.conversations cv on cv.id=a.conversation_id and cv.tenant_id=a.tenant_id
        left join app.service_catalog sc on sc.id=a.service_id and sc.tenant_id=a.tenant_id
        left join app.resources r on r.id=a.resource_id and r.tenant_id=a.tenant_id
        left join app.branches b on b.id=a.branch_id and b.tenant_id=a.tenant_id
        where a.tenant_id=$1 and a.id=$2
        """,
        tenant_id,
        appointment_id,
    )
    if not row:
        return None
    channel_id = row['channel_id']
    if channel_id is None:
        channel_id = await conn.fetchval(
            "select id from app.tenant_channels where tenant_id=$1 and provider='whatsapp_cloud_api' limit 1",
            tenant_id,
        )
    return {
        'id': row['id'],
        'starts_at': row['starts_at'],
        'ends_at': row['ends_at'],
        'conversation_id': row['conversation_id'],
        'service_id': row['service_id'],
        'resource_id': row['resource_id'],
        'contact_id': row['contact_id'],
        'contact_name': row['contact_name'],
        'channel_id': channel_id,
        'service_name': row['service_name'],
        'preparation_notes': row['preparation_notes'],
        'resource_name': row['resource_name'],
        'branch_id': row['branch_id'],
        'branch_address': row['branch_address'],
        'branch_maps_url': row['branch_maps_url'],
        'branch_phone': row['branch_phone'],
        'branch_name': row['branch_name'],
    }


async def _insert_reminder_job(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    appointment_id: UUID,
    channel_id: UUID | None,
    purpose: str,
    scheduled_for,
    variables: dict[str, str],
    locale: str = DEFAULT_TEMPLATE_LOCALE,
) -> UUID:
    row = await conn.fetchrow(
        """
        insert into app.reminder_jobs (
          tenant_id, target_type, target_id, channel_id,
          template_name, template_locale, payload, scheduled_for
        )
        values ($1, 'appointment', $2, $3, $4, $5, $6::jsonb, $7)
        returning id
        """,
        tenant_id,
        appointment_id,
        channel_id,
        purpose,
        locale,
        json.dumps({
            'purpose': purpose,
            'appointment_id': str(appointment_id),
            'variables': variables,
        }),
        scheduled_for,
    )
    return row['id']


async def create_appointment_reminder_jobs(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    appointment_id: UUID,
) -> dict[str, Any]:
    """Create the reminder_jobs for an appointment based on tenant settings."""
    settings = await fetch_notification_settings(conn, tenant_id)
    context = await _appointment_context(conn, tenant_id, appointment_id)
    if not context:
        return {'created': 0, 'skipped': 'appointment_not_found'}
    starts_at = context['starts_at']
    ends_at = context['ends_at']
    # TASK-0050: appointments tied to a branch use that branch's address/maps;
    # appointments without a branch fall back to the tenant-wide defaults.
    if context.get('branch_id'):
        address = context.get('branch_address') or None
        maps_url = context.get('branch_maps_url') or None
    else:
        address = settings.get('location_address') or None
        maps_url = settings.get('location_maps_url') or None
    variables = build_variables(
        contact_name=context['contact_name'],
        service_name=context['service_name'],
        resource_name=context['resource_name'],
        starts_at=starts_at,
        address=address,
        maps_url=maps_url,
        preparation_notes=context.get('preparation_notes'),
        include_location=bool(settings.get('include_location_link')),
        include_preparation=bool(settings.get('include_preparation_notes')),
    )
    pending_jobs = _scheduled_jobs_for_create(settings, starts_at)
    pending_jobs += _scheduled_jobs_post_appointment(settings, ends_at)
    created_ids: list[UUID] = []
    for job in pending_jobs:
        job_id = await _insert_reminder_job(
            conn,
            tenant_id=tenant_id,
            appointment_id=appointment_id,
            channel_id=context['channel_id'],
            purpose=job['purpose'],
            scheduled_for=job['scheduled_for'],
            variables=variables,
        )
        created_ids.append(job_id)
    log.info(
        'notifications.jobs_created',
        tenant_id=str(tenant_id),
        appointment_id=str(appointment_id),
        count=len(created_ids),
        purposes=[job['purpose'] for job in pending_jobs],
    )
    return {'created': len(created_ids), 'purposes': [job['purpose'] for job in pending_jobs]}


async def cancel_appointment_reminder_jobs(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    appointment_id: UUID,
) -> int:
    """Mark all pending/processing reminder jobs for the appointment as cancelled."""
    result = await conn.fetch(
        """
        update app.reminder_jobs
        set status='cancelled', updated_at=now()
        where tenant_id=$1
          and target_type='appointment'
          and target_id=$2
          and status in ('pending','processing')
        returning id
        """,
        tenant_id,
        appointment_id,
    )
    log.info(
        'notifications.jobs_cancelled',
        tenant_id=str(tenant_id),
        appointment_id=str(appointment_id),
        count=len(result),
    )
    return len(result)


async def regenerate_appointment_reminder_jobs(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    appointment_id: UUID,
) -> dict[str, Any]:
    await cancel_appointment_reminder_jobs(conn, tenant_id, appointment_id)
    return await create_appointment_reminder_jobs(conn, tenant_id, appointment_id)
