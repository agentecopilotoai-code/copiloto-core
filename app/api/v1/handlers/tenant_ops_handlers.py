"""Handlers extracted from routes.py for tenant_ops_router.

Original location: app/api/v1/routes.py (refactor step 3).
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import asyncpg
import httpx
import structlog
from fastapi import Depends, Header, HTTPException, Query, Request, Response, status

from app.api.v1._helpers.booking_db import (
    appointment_detail,
    ensure_resource_available,
)
from app.api.v1._helpers.normalizers import normalize_qualification_question
from app.api.v1._helpers.notifications_db import notify_operations_change
from app.api.v1._helpers.payments_db import _fetch_tenant_payment_settings
from app.api.v1._helpers.payments_pure import (
    _appointment_payment_external_ref,
    _appointment_payment_summary,
)
from app.api.v1._helpers.projections import QUALIFICATION_PROJECTION
from app.api.v1._helpers.quotes import (
    _build_quote_summary_text,
    _compute_quote_subtotal,
)
from app.api.v1._helpers.whatsapp_pure import (
    MEDIA_MESSAGE_TYPES,
    media_url_from_payload,
    validate_outbound_message_content,
)
from app.api.v1.routes import (
    current_user_id_from_request,
    ensure_tenant_access,
    ensure_tenant_role,
    tenant_id_from_request,
    tenant_ops_router,
)
from app.api.v1.schemas import (
    AppointmentCreate,
    AppointmentPaymentLinkRequest,
    AppointmentPaymentStatusUpdate,
    AppointmentUpdate,
    ContactNoteCreate,
    ContactPhoneUpdate,
    ContactTagAssign,
    ConversationStart,
    HandoffCreate,
    MessageCreate,
    QuoteCreate,
    QuotePatch,
    ResourceCreate,
    ResourceUpdate,
    ServiceRequestCreate,
    ServiceRequestPatch,
)
from app.core.config import get_settings
from app.db.pool import get_db, record_to_dict
from app.services.audit import audit
from app.services.campaign_attribution import attribute_appointment
from app.services.metrics import (
    record_appointment,
    record_handoff,
)
from app.services.notifications import (
    cancel_appointment_reminder_jobs,
    create_appointment_reminder_jobs,
    regenerate_appointment_reminder_jobs,
)
from app.services.payment_provider import (
    PaymentProviderError,
    generate_payment_link as provider_generate_payment_link,
)
from app.services.media_storage import read_media_file
from app.services.web_widget import build_lead_source
from app.services.whatsapp import (
    WhatsAppMediaTooLargeError,
    download_whatsapp_media,
    resolve_secret_ref,
)

log = structlog.get_logger()


@tenant_ops_router.get('/tenants/{tenant_id}')
async def get_tenant(tenant_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    await ensure_tenant_access(request, tenant_id, conn)
    row = await conn.fetchrow('select * from app.tenants where id=$1 and deleted_at is null', tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail='Tenant not found')
    return record_to_dict(row)


@tenant_ops_router.get('/tenants/{tenant_id}/media/{asset_id}/content')
async def get_tenant_media_content(
    tenant_id: UUID,
    asset_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    """BUG-096: proxy HTTP sobre `app.media_assets` para que el browser
    pueda renderizar el `brand_logo_url` (y cualquier otro asset
    tenant-scoped en el futuro).

    Antes el upload guardaba `stored.source_uri` (`file://` o `s3://`)
    en `tenant_settings.brand_logo_url`, y la admin shell mostraba
    imagen rota. Ahora el upload guarda la URL de este endpoint
    (`/v1/tenants/{tenant_id}/media/{asset_id}/content`) y este handler
    sirve los bytes con el `mime_type` del asset.

    Seguridad: vive en `tenant_ops_router` (agent+ MFA opcional para
    reads), valida `ensure_tenant_access` (member del tenant), y RLS
    sobre `app.media_assets` aplica con `app.tenant_id` GUC. El
    `Cache-Control: private, max-age=600` reduce hits del browser sin
    permitir caching en proxies compartidos.
    """
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    asset = await conn.fetchrow(
        """
        select kind, mime_type, source_uri, storage_backend, storage_bucket, object_key
        from app.media_assets
        where tenant_id = $1 and id = $2
        """,
        tenant_id,
        asset_id,
    )
    if not asset:
        raise HTTPException(status_code=404, detail='Media asset not found')
    try:
        content = read_media_file(
            storage_backend=asset['storage_backend'],
            object_key=asset['object_key'],
            source_uri=asset['source_uri'],
            bucket=asset['storage_bucket'],
            settings=get_settings(),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail='Media content unavailable') from exc
    return Response(
        content=content,
        media_type=asset['mime_type'] or 'application/octet-stream',
        headers={'Cache-Control': 'private, max-age=600'},
    )


@tenant_ops_router.get('/contacts/{contact_id}')
async def get_contact(
    contact_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    tenant_id = await tenant_id_from_request(request, conn)
    row = await conn.fetchrow('select * from app.contacts where tenant_id=$1 and id=$2', tenant_id, contact_id)
    if not row:
        raise HTTPException(status_code=404, detail='Contact not found')
    return record_to_dict(row)


@tenant_ops_router.patch('/contacts/{contact_id}/phone')
async def patch_contact_phone(
    contact_id: UUID,
    payload: ContactPhoneUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    """TASK-0082 / BUG22: mutate a contact's phone_e164 (and derived
    ``wa_id`` + ``phone_hash``) only through this dedicated endpoint, gated by
    role ``manager``+ and recorded in ``audit_logs``. The ``start_conversation``
    flow is now read-only with respect to identity.
    """
    tenant_id = await tenant_id_from_request(request, conn)
    await ensure_tenant_role(request, conn, tenant_id, 'manager')
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    existing = await conn.fetchrow(
        'select id, phone_e164, wa_id from app.contacts where tenant_id=$1 and id=$2',
        tenant_id,
        contact_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail='Contact not found')

    new_phone = payload.phone_e164.strip()
    new_wa_id = new_phone.lstrip('+')
    new_hash = hashlib.sha256(new_phone.encode()).digest()

    # Prevent silently colliding with another contact (another tenant row that
    # already owns this phone). If the operator wants to merge, that's a
    # separate flow; here we refuse to overwrite identity ambiguously.
    collision = await conn.fetchrow(
        'select id from app.contacts where tenant_id=$1 and phone_e164=$2 and id<>$3',
        tenant_id,
        new_phone,
        contact_id,
    )
    if collision:
        raise HTTPException(
            status_code=409,
            detail='Another contact in this tenant already has this phone_e164',
        )

    row = await conn.fetchrow(
        """
        update app.contacts
        set phone_e164=$3, wa_id=$4, phone_hash=$5, updated_at=now()
        where tenant_id=$1 and id=$2
        returning *
        """,
        tenant_id,
        contact_id,
        new_phone,
        new_wa_id,
        new_hash,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='contact.phone_changed',
        entity_type='contact',
        entity_id=str(contact_id),
        metadata={
            'previous_phone_last4': (existing['phone_e164'] or '')[-4:],
            'new_phone_last4': new_phone[-4:],
            'reason': payload.reason,
        },
    )
    return record_to_dict(row)


@tenant_ops_router.get('/contacts')
async def list_contacts(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    q: str | None = Query(default=None, max_length=160),
    tag_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    search_term = f'%{q.strip().lower()}%' if q and q.strip() else None
    rows = await conn.fetch(
        """
        select c.id, c.tenant_id, c.wa_id, c.phone_e164, c.display_name,
               c.opt_in_status, c.source, c.created_at, c.updated_at,
               (select count(*) from app.appointments a
                where a.tenant_id = c.tenant_id and a.contact_id = c.id) as appointments_count
        from app.contacts c
        where c.tenant_id = $1
          and (
                $2::text is null
                or lower(coalesce(c.display_name, '')) like $2
                or lower(coalesce(c.phone_e164, '')) like $2
                or lower(coalesce(c.wa_id, '')) like $2
              )
          and (
                $3::uuid is null
                or exists (
                  select 1 from app.contact_tag_assignments cta
                  where cta.contact_id = c.id and cta.tag_id = $3 and cta.tenant_id = c.tenant_id
                )
              )
        order by c.updated_at desc
        limit $4 offset $5
        """,
        tenant_id,
        search_term,
        tag_id,
        limit,
        offset,
    )
    contacts = [record_to_dict(row) for row in rows]
    if contacts:
        contact_ids = [contact['id'] for contact in contacts]
        tag_rows = await conn.fetch(
            """
            select cta.contact_id, t.id, t.name, t.color
            from app.contact_tag_assignments cta
            join app.contact_tags t on t.id = cta.tag_id and t.tenant_id = cta.tenant_id
            where cta.tenant_id = $1 and cta.contact_id = any($2::uuid[])
            order by t.name
            """,
            tenant_id,
            contact_ids,
        )
        tags_by_contact: dict[str, list[dict[str, Any]]] = {}
        for row in tag_rows:
            tags_by_contact.setdefault(str(row['contact_id']), []).append(
                {'id': str(row['id']), 'name': row['name'], 'color': row['color']}
            )
        for contact in contacts:
            contact['tags'] = tags_by_contact.get(str(contact['id']), [])
    return contacts


@tenant_ops_router.get('/contacts/{contact_id}/profile')
async def get_contact_profile(
    contact_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    contact = await conn.fetchrow(
        'select * from app.contacts where tenant_id=$1 and id=$2',
        tenant_id,
        contact_id,
    )
    if not contact:
        raise HTTPException(status_code=404, detail='Contact not found')
    tags = await conn.fetch(
        """
        select t.id, t.name, t.color, t.description, cta.assigned_at, cta.assigned_by
        from app.contact_tag_assignments cta
        join app.contact_tags t on t.id = cta.tag_id and t.tenant_id = cta.tenant_id
        where cta.tenant_id = $1 and cta.contact_id = $2
        order by t.name
        """,
        tenant_id,
        contact_id,
    )
    appointments = await conn.fetch(
        """
        select a.id, a.starts_at, a.ends_at, a.status, a.confirmation_status,
               a.service_code, s.name as service_name, r.name as resource_name
        from app.appointments a
        left join app.service_catalog s on s.id = a.service_id and s.tenant_id = a.tenant_id
        left join app.resources r on r.id = a.resource_id and r.tenant_id = a.tenant_id
        where a.tenant_id = $1 and a.contact_id = $2
        order by a.starts_at desc
        limit 10
        """,
        tenant_id,
        contact_id,
    )
    conversations = await conn.fetch(
        """
        select c.id, c.status, c.current_intent, c.created_at, c.updated_at,
               (select count(*) from app.messages m
                where m.tenant_id = c.tenant_id and m.conversation_id = c.id) as message_count
        from app.conversations c
        where c.tenant_id = $1 and c.contact_id = $2
          -- BUG-216 (codex P2 follow-up): excluir conversations internas
          -- del digest_worker para que el agent NO obtenga el UUID via
          -- profile y pueda abrir la conversación con los KPIs.
          and coalesce(c.metadata->>'kind', '') <> 'internal_digest'
        order by c.updated_at desc
        limit 5
        """,
        tenant_id,
        contact_id,
    )
    notes = await conn.fetch(
        """
        select n.id, n.body, n.created_by, n.created_at, n.updated_at,
               u.display_name as created_by_name
        from app.contact_notes n
        left join app.users u on u.id = n.created_by
        where n.tenant_id = $1 and n.contact_id = $2
        order by n.created_at desc
        """,
        tenant_id,
        contact_id,
    )
    stats = await conn.fetchrow(
        """
        select
          count(*) filter (where status = 'completed') as completed_appointments,
          count(*) as total_appointments,
          min(starts_at) filter (where status = 'completed') as first_visit_at,
          max(starts_at) filter (where status = 'completed') as last_visit_at
        from app.appointments
        where tenant_id = $1 and contact_id = $2
        """,
        tenant_id,
        contact_id,
    )
    feedback = await conn.fetchrow(
        """
        select avg(rating)::float as average_rating, count(*) as ratings_count
        from app.appointment_feedback
        where tenant_id = $1 and contact_id = $2
        """,
        tenant_id,
        contact_id,
    )
    qualification_questions = await conn.fetch(
        f"""
        select {QUALIFICATION_PROJECTION}
        from app.qualification_questions
        where tenant_id=$1
        order by position asc, created_at asc
        """,
        tenant_id,
    )
    contact_dict = record_to_dict(contact)
    raw_qualification = contact_dict.get('qualification') if contact_dict else None
    if isinstance(raw_qualification, str):
        try:
            raw_qualification = json.loads(raw_qualification)
        except json.JSONDecodeError:
            raw_qualification = {}
    if not isinstance(raw_qualification, dict):
        raw_qualification = {}
    contact_dict['qualification'] = raw_qualification

    # TASK-0055: surface referrer relationships on the contact profile.
    referred_by = None
    if contact_dict.get('referrer_contact_id'):
        ref_row = await conn.fetchrow(
            'select id, display_name, phone_e164 from app.contacts '
            'where tenant_id=$1 and id=$2',
            tenant_id,
            contact_dict['referrer_contact_id'],
        )
        if ref_row:
            referred_by = {
                'contact_id': str(ref_row['id']),
                'display_name': ref_row['display_name'],
                'phone_e164': ref_row['phone_e164'],
            }
    referred_contacts = await conn.fetch(
        """
        select id, display_name, phone_e164, created_at
        from app.contacts
        where tenant_id=$1 and referrer_contact_id=$2
        order by created_at desc
        limit 20
        """,
        tenant_id,
        contact_id,
    )

    return {
        'contact': contact_dict,
        'tags': [record_to_dict(row) for row in tags],
        'appointments': [record_to_dict(row) for row in appointments],
        'conversations': [record_to_dict(row) for row in conversations],
        'notes': [record_to_dict(row) for row in notes],
        'qualification_questions': [
            normalize_qualification_question(row) for row in qualification_questions
        ],
        'qualification_answers': raw_qualification,
        'stats': {
            'total_appointments': stats['total_appointments'] if stats else 0,
            'completed_appointments': stats['completed_appointments'] if stats else 0,
            'first_visit_at': stats['first_visit_at'] if stats else None,
            'last_visit_at': stats['last_visit_at'] if stats else None,
            'average_rating': feedback['average_rating'] if feedback else None,
            'ratings_count': feedback['ratings_count'] if feedback else 0,
        },
        'referrals': {
            'referred_by': referred_by,
            'referred_contacts': [
                {
                    'contact_id': str(row['id']),
                    'display_name': row['display_name'],
                    'phone_e164': row['phone_e164'],
                    'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                }
                for row in referred_contacts
            ],
        },
    }


@tenant_ops_router.get('/tenants/{tenant_id}/contact-tags')
async def list_contact_tags(
    tenant_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        """
        select t.*,
               (select count(*) from app.contact_tag_assignments cta
                where cta.tenant_id = t.tenant_id and cta.tag_id = t.id) as contacts_count
        from app.contact_tags t
        where t.tenant_id = $1
        order by t.name
        """,
        tenant_id,
    )
    return [record_to_dict(row) for row in rows]


@tenant_ops_router.post('/contacts/{contact_id}/tags', status_code=201)
async def assign_contact_tags(
    contact_id: UUID,
    payload: ContactTagAssign,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    contact = await conn.fetchrow(
        'select id from app.contacts where tenant_id=$1 and id=$2', tenant_id, contact_id
    )
    if not contact:
        raise HTTPException(status_code=404, detail='Contact not found')
    user_id = await current_user_id_from_request(request, conn)
    for tag_id in payload.tag_ids:
        owned = await conn.fetchval(
            'select id from app.contact_tags where tenant_id=$1 and id=$2', tenant_id, tag_id
        )
        if not owned:
            raise HTTPException(status_code=404, detail=f'Tag {tag_id} not found for this tenant')
        await conn.execute(
            """
            insert into app.contact_tag_assignments (tenant_id, contact_id, tag_id, assigned_by)
            values ($1, $2, $3, $4)
            on conflict (contact_id, tag_id) do nothing
            """,
            tenant_id,
            contact_id,
            tag_id,
            user_id,
        )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='contact_tag.assigned',
        entity_type='contact',
        entity_id=str(contact_id),
        metadata={'tag_ids': [str(t) for t in payload.tag_ids]},
    )
    rows = await conn.fetch(
        """
        select t.id, t.name, t.color
        from app.contact_tag_assignments cta
        join app.contact_tags t on t.id = cta.tag_id and t.tenant_id = cta.tenant_id
        where cta.tenant_id = $1 and cta.contact_id = $2
        order by t.name
        """,
        tenant_id,
        contact_id,
    )
    return [record_to_dict(row) for row in rows]


@tenant_ops_router.delete('/contacts/{contact_id}/tags/{tag_id}', status_code=204)
async def unassign_contact_tag(
    contact_id: UUID,
    tag_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    deleted = await conn.fetchval(
        """
        delete from app.contact_tag_assignments
        where tenant_id=$1 and contact_id=$2 and tag_id=$3
        returning tag_id
        """,
        tenant_id,
        contact_id,
        tag_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail='Tag assignment not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='contact_tag.unassigned',
        entity_type='contact',
        entity_id=str(contact_id),
        metadata={'tag_id': str(tag_id)},
    )
    return Response(status_code=204)


@tenant_ops_router.get('/contacts/{contact_id}/notes')
async def list_contact_notes(
    contact_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        """
        select n.id, n.tenant_id, n.contact_id, n.body, n.created_by, n.created_at, n.updated_at,
               u.display_name as created_by_name
        from app.contact_notes n
        left join app.users u on u.id = n.created_by
        where n.tenant_id = $1 and n.contact_id = $2
        order by n.created_at desc
        """,
        tenant_id,
        contact_id,
    )
    return [record_to_dict(row) for row in rows]


@tenant_ops_router.post('/contacts/{contact_id}/notes', status_code=201)
async def create_contact_note(
    contact_id: UUID,
    payload: ContactNoteCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    contact = await conn.fetchrow(
        'select id from app.contacts where tenant_id=$1 and id=$2', tenant_id, contact_id
    )
    if not contact:
        raise HTTPException(status_code=404, detail='Contact not found')
    user_id = await current_user_id_from_request(request, conn)
    row = await conn.fetchrow(
        """
        insert into app.contact_notes (tenant_id, contact_id, body, created_by)
        values ($1, $2, $3, $4)
        returning *
        """,
        tenant_id,
        contact_id,
        payload.body.strip(),
        user_id,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='contact_note.created',
        entity_type='contact_note',
        entity_id=str(row['id']),
    )
    return record_to_dict(row)


@tenant_ops_router.get('/contacts/{contact_id}/consent')
async def list_contact_consent(
    contact_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """TASK-0062: return the consent ledger for a single contact (append-only).

    The ledger is the evidence required by Ley 1581 / GDPR for derecho de
    acceso requests.  Paginated with ``limit``/``offset``; ordered newest
    first.  Returns ``{items, total, contact: {opt_in_status, opt_in_at,
    opt_out_at, consent_version}}``.
    """
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    contact_row = await conn.fetchrow(
        """
        select id, opt_in_status, opt_in_at, opt_out_at, consent_version
        from app.contacts
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        contact_id,
    )
    if contact_row is None:
        raise HTTPException(status_code=404, detail='Contact not found')
    total = await conn.fetchval(
        'select count(*) from app.consent_ledger where tenant_id=$1 and contact_id=$2',
        tenant_id,
        contact_id,
    ) or 0
    rows = await conn.fetch(
        """
        select id, event, channel, legal_basis, purpose, copy_shown,
               evidence_payload, occurred_at, ip, user_agent
        from app.consent_ledger
        where tenant_id=$1 and contact_id=$2
        order by occurred_at desc, id desc
        limit $3 offset $4
        """,
        tenant_id,
        contact_id,
        limit,
        offset,
    )
    return {
        'contact': record_to_dict(contact_row),
        'total': int(total),
        'limit': limit,
        'offset': offset,
        'items': [record_to_dict(row) for row in rows],
    }


@tenant_ops_router.get('/conversations')
async def list_conversations(request: Request, conn: asyncpg.Connection = Depends(get_db)):
    tenant_id = await tenant_id_from_request(request, conn)
    # BUG-043: el frontend filtra "Mis handoffs" comparando `assigned_to`
    # contra `profile.sub` (Auth0), pero `assigned_to` es `app.users.id`
    # (UUID) — nunca matcheaba. Para no obligar al FE a conocer su UUID
    # interno, computamos server-side `active_handoff_assigned_to_is_me`
    # usando `current_user_id_from_request`. El FE filtra por ese boolean.
    current_user_id = await current_user_id_from_request(request, conn)
    rows = await conn.fetch(
        """
        select c.*,
               coalesce(ct.display_name, ct.phone_e164, ct.wa_id) as contact_label,
               ct.phone_e164 as contact_phone,
               coalesce(lm.body_text, '[' || lm.message_type || ']') as latest_message_text,
               lm.message_type as latest_message_type,
               lm.direction as latest_message_direction,
               lm.created_at as latest_message_at,
               h.id as active_handoff_id,
               h.status as active_handoff_status,
               h.assigned_to as active_handoff_assigned_to
        from app.conversations c
        join app.contacts ct on ct.id = c.contact_id
        left join lateral (
          select body_text, message_type, direction, created_at
          from app.messages m
          where m.tenant_id = c.tenant_id and m.conversation_id = c.id
          order by m.created_at desc
          limit 1
        ) lm on true
        left join lateral (
          select id, status, assigned_to
          from app.handoffs ho
          where ho.tenant_id = c.tenant_id
            and ho.conversation_id = c.id
            and ho.status in ('open','accepted')
          order by ho.updated_at desc
          limit 1
        ) h on true
        where c.tenant_id=$1
          -- BUG-216 (codex MEDIUM, 2026-05-18): excluir conversations
          -- marcadas `metadata.kind = 'internal_digest'`. El digest_worker
          -- escribe los KPIs semanales (revenue, retention, top service)
          -- como messages outbound en una "conversación interna" creada
          -- ad-hoc. Sin filtro, cualquier agent del tenant (rol más bajo)
          -- podía listar conversaciones, abrir la interna, y leer
          -- analytics manager/admin-only — violando el RBAC del módulo.
          and coalesce(c.metadata->>'kind', '') <> 'internal_digest'
        order by c.updated_at desc
        limit 100
        """,
        tenant_id,
    )
    conversations = [record_to_dict(r) for r in rows]
    # BUG-043: marcar las conversaciones donde el handoff activo está
    # asignado al usuario actual. False si no hay handoff o no hay user_id
    # (token de servicio, etc.).
    for conversation in conversations:
        assigned_to = conversation.get('active_handoff_assigned_to')
        conversation['active_handoff_assigned_to_is_me'] = bool(
            current_user_id is not None
            and assigned_to is not None
            and str(assigned_to) == str(current_user_id)
        )
    if conversations:
        contact_ids = list({c['contact_id'] for c in conversations if c.get('contact_id')})
        if contact_ids:
            tag_rows = await conn.fetch(
                """
                select cta.contact_id, t.id, t.name, t.color
                from app.contact_tag_assignments cta
                join app.contact_tags t on t.id = cta.tag_id and t.tenant_id = cta.tenant_id
                where cta.tenant_id = $1 and cta.contact_id = any($2::uuid[])
                order by t.name
                """,
                tenant_id,
                contact_ids,
            )
            tags_by_contact: dict[str, list[dict[str, Any]]] = {}
            for row in tag_rows:
                tags_by_contact.setdefault(str(row['contact_id']), []).append(
                    {'id': str(row['id']), 'name': row['name'], 'color': row['color']}
                )
            for conversation in conversations:
                conversation['contact_tags'] = tags_by_contact.get(str(conversation.get('contact_id')), [])
        else:
            for conversation in conversations:
                conversation['contact_tags'] = []
    log.info(
        'operations.conversations.listed',
        tenant_id=str(tenant_id),
        count=len(conversations),
        conversation_ids=[str(item.get('id')) for item in conversations[:20]],
        actor_id=getattr(request.state, 'actor_id', None),
    )
    return conversations


@tenant_ops_router.get('/conversations/complaints')
async def list_complaint_conversations(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    limit: int = Query(default=50, ge=1, le=200),
):
    """TASK-0045: list conversations escalated due to negative feedback.

    Returns conversations with an open ``handoffs`` row whose
    ``reason='negative_feedback'``, joined with the latest
    ``appointment_feedback`` row (rating + comment) for the contact so the
    agent sees the complaint without opening the conversation.
    """
    tenant_id = await tenant_id_from_request(request, conn)
    rows = await conn.fetch(
        """
        select c.id, c.status, c.contact_id, c.handoff_required,
               c.current_intent, c.updated_at, c.created_at,
               coalesce(ct.display_name, ct.phone_e164, ct.wa_id) as contact_label,
               ct.phone_e164 as contact_phone,
               h.id as handoff_id, h.reason as handoff_reason,
               h.created_at as handoff_created_at,
               fb.rating as feedback_rating,
               fb.comment as feedback_comment,
               fb.created_at as feedback_created_at,
               fb.appointment_id as feedback_appointment_id
        from app.handoffs h
        join app.conversations c
          on c.tenant_id = h.tenant_id and c.id = h.conversation_id
        join app.contacts ct
          on ct.tenant_id = c.tenant_id and ct.id = c.contact_id
        left join lateral (
          select rating, comment, created_at, appointment_id
          from app.appointment_feedback af
          where af.tenant_id = c.tenant_id and af.contact_id = c.contact_id
          order by af.created_at desc
          limit 1
        ) fb on true
        where h.tenant_id = $1
          and h.reason = 'negative_feedback'
          and h.status in ('open', 'accepted')
        order by h.created_at desc
        limit $2
        """,
        tenant_id,
        limit,
    )
    complaints = [record_to_dict(r) for r in rows]
    log.info(
        'operations.complaints.listed',
        tenant_id=str(tenant_id),
        count=len(complaints),
    )
    return complaints


@tenant_ops_router.post('/conversations/start', status_code=status.HTTP_201_CREATED)
async def start_conversation(
    payload: ConversationStart,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias='Idempotency-Key'),
):
    await ensure_tenant_access(request, payload.tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(payload.tenant_id))
    user_id = await current_user_id_from_request(request, conn)
    channel = await conn.fetchrow(
        """
        select id
        from app.tenant_channels
        where tenant_id=$1 and provider='whatsapp_cloud_api' and status in ('active','provisioning')
        order by case when status='active' then 0 else 1 end, updated_at desc
        limit 1
        """,
        payload.tenant_id,
    )
    if not channel:
        log.warning(
            'operations.conversation.start_missing_channel',
            tenant_id=str(payload.tenant_id),
            actor_id=request.state.actor_id,
        )
        raise HTTPException(status_code=409, detail='Configured WhatsApp channel is required to start a conversation')
    log.info(
        'operations.conversation.start_requested',
        tenant_id=str(payload.tenant_id),
        channel_id=str(channel['id']),
        phone_last4=payload.phone_e164[-4:] if payload.phone_e164 else None,
        contact_id=str(payload.contact_id) if payload.contact_id else None,
        actor_id=request.state.actor_id,
    )

    # TASK-0082 / BUG22: pick the contact by ID first, then by phone — and
    # NEVER mutate an existing contact's phone_e164/wa_id from this endpoint.
    # The previous upsert path overwrote phone_e164 on conflict, which let an
    # agent redirect outbound traffic to an attacker's phone; phone changes
    # now go through PATCH /contacts/{id}/phone (manager+, audited).
    if payload.contact_id is None and not (payload.phone_e164 or '').strip():
        raise HTTPException(
            status_code=422,
            detail='Either contact_id or phone_e164 is required to start a conversation',
        )
    if payload.contact_id is not None:
        contact = await conn.fetchrow(
            'select * from app.contacts where tenant_id=$1 and id=$2',
            payload.tenant_id,
            payload.contact_id,
        )
        if not contact:
            raise HTTPException(status_code=404, detail='Contact not found in this tenant')
    else:
        phone_e164 = payload.phone_e164.strip()
        phone_hash = hashlib.sha256(phone_e164.encode()).digest()
        contact = await conn.fetchrow(
            'select * from app.contacts where tenant_id=$1 and phone_e164=$2',
            payload.tenant_id,
            phone_e164,
        )
        if not contact:
            wa_id = phone_e164.lstrip('+')
            contact = await conn.fetchrow(
                """
                insert into app.contacts (tenant_id, wa_id, phone_e164, phone_hash, display_name, source, metadata, lead_source)
                values ($1, $2, $3, $4, $5, 'operations_desk', $6::jsonb, $7::jsonb)
                returning *
                """,
                payload.tenant_id,
                wa_id,
                phone_e164,
                phone_hash,
                payload.display_name,
                json.dumps(payload.metadata or {}),
                json.dumps(build_lead_source(channel='whatsapp')),
            )
    conversation = await conn.fetchrow(
        """
        select *
        from app.conversations
        where tenant_id=$1
          and contact_id=$2
          and status not in ('resolved','closed','archived')
        order by updated_at desc
        limit 1
        """,
        payload.tenant_id,
        contact['id'],
    )
    reused_conversation = bool(conversation)
    if conversation:
        conversation = await conn.fetchrow(
            """
            update app.conversations
            set current_owner_user_id=$3,
                status='waiting_user',
                handoff_required=false,
                current_intent=coalesce($4, current_intent)
            where tenant_id=$1 and id=$2
            returning *
            """,
            payload.tenant_id,
            conversation['id'],
            user_id,
            payload.current_intent,
        )
    else:
        conversation = await conn.fetchrow(
            """
            insert into app.conversations (
              tenant_id, contact_id, channel_id, status, opened_by, current_owner_user_id, current_intent
            )
            values ($1, $2, $3, 'waiting_user', 'agent', $4, $5)
            returning *
            """,
            payload.tenant_id,
            contact['id'],
            channel['id'],
            user_id,
            payload.current_intent,
        )

    initial_body_text = (payload.initial_message or '').strip() or None
    initial_message_payload: dict[str, Any] = {}
    if payload.initial_media_url:
        initial_message_payload['media_url'] = payload.initial_media_url.strip()
    if payload.initial_message_type in {'image', 'video'} and initial_body_text:
        initial_message_payload['caption'] = initial_body_text
    validate_outbound_message_content(
        payload.initial_message_type,
        initial_body_text,
        payload.initial_media_id,
        media_url_from_payload(initial_message_payload),
    )
    message = await conn.fetchrow(
        """
        insert into app.messages (
          tenant_id, conversation_id, direction, sender_actor_type, sender_actor_id,
          body_text, message_type, media_id, mime_type, payload, status
        )
        values ($1, $2, 'outbound', 'agent', $3, $4, $5, $6, $7, $8::jsonb, 'queued')
        returning *
        """,
        payload.tenant_id,
        conversation['id'],
        str(user_id) if user_id else request.state.actor_id,
        initial_body_text,
        payload.initial_message_type,
        payload.initial_media_id.strip() if payload.initial_media_id else None,
        payload.initial_mime_type,
        json.dumps(initial_message_payload),
    )
    key = idempotency_key or str(message['id'])
    await conn.execute(
        "insert into app.domain_events (tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload) values ($1,'message',$2,'message.queued',$3,$4::jsonb) on conflict do nothing",
        payload.tenant_id,
        message['id'],
        key,
        json.dumps({'conversation_id': str(conversation['id']), 'started_by_agent': True}),
    )
    await audit(
        conn,
        tenant_id=payload.tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='conversation.started_by_agent',
        entity_type='conversation',
        entity_id=str(conversation['id']),
        metadata={'contact_id': str(contact['id']), 'message_id': str(message['id']), 'reused': reused_conversation},
    )
    await audit(conn, tenant_id=payload.tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='message.queued', entity_type='message', entity_id=str(message['id']))
    await notify_operations_change(
        conn,
        payload.tenant_id,
        'conversation.changed',
        conversation_id=conversation['id'],
        message_id=message['id'],
    )
    response = record_to_dict(conversation)
    response['contact_label'] = contact['display_name'] or contact['phone_e164'] or contact['wa_id']
    response['contact_phone'] = contact['phone_e164']
    response['contact'] = record_to_dict(contact)
    response['initial_message'] = record_to_dict(message)
    response['messages'] = [response['initial_message']]
    response['handoffs'] = []
    response['reused_conversation'] = reused_conversation
    log.info(
        'operations.conversation.started',
        tenant_id=str(payload.tenant_id),
        conversation_id=str(conversation['id']),
        contact_id=str(contact['id']),
        channel_id=str(channel['id']),
        message_id=str(message['id']),
        reused=reused_conversation,
        actor_id=request.state.actor_id,
    )
    return response


@tenant_ops_router.get('/conversations/{conversation_id}')
async def get_conversation(
    conversation_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    tenant_id = await tenant_id_from_request(request, conn)
    # BUG-221 (codex MEDIUM, 2026-05-18): el retry loop con `asyncio.sleep(0.1)`
    # mantenía la conn de la pool (`max_size=10`) durante hasta 400ms.
    # Atacante con UUIDs random saturaba la pool. Fix: 1 sola query, 404
    # inmediato. El race que el legacy cubría se maneja client-side.
    #
    # BUG-216 (codex P2 follow-up): excluir conversations internas del
    # digest_worker para que un agent que conozca el UUID via
    # /contacts/{id}/profile NO pueda abrir la conversación con los KPIs.
    row = await conn.fetchrow(
        """
        select c.*,
               coalesce(ct.display_name, ct.phone_e164, ct.wa_id) as contact_label,
               ct.phone_e164 as contact_phone
        from app.conversations c
        join app.contacts ct on ct.id = c.contact_id
        where c.tenant_id=$1 and c.id=$2
          and coalesce(c.metadata->>'kind', '') <> 'internal_digest'
        """,
        tenant_id,
        conversation_id,
    )
    if not row:
        # SEC-010 fix — el bloque diagnóstico ANTES corría siempre y logueaba
        # `actual_tenant_id` + `actual_status` aún cuando el conversation_id
        # pedido pertenecía a OTRO tenant. Eso filtraba metadata cross-tenant
        # a logs operacionales (alguien con acceso a `docker logs` o al log
        # aggregator podía descubrir qué conversaciones existen en otros
        # tenants y su estado, simplemente probando UUIDs random vía
        # `/v1/tenants/<su-tenant>/conversations/<uuid-random>`).
        #
        # Ahora el bloque está gated por `debug_cross_tenant_diagnostics`
        # (env `DEBUG_CROSS_TENANT_DIAGNOSTICS=1`, default false). Sin el
        # flag, solo logueamos los identificadores del caller (su tenant
        # + el conversation_id que pidió + actor) — info que ELLOS ya
        # conocen. El leak cierra.
        #
        # Para investigar un 404 sospechoso, operadores enable el flag
        # transitoriamente (procedimiento en runbook).
        settings = get_settings()
        if settings.debug_cross_tenant_diagnostics:
            diagnostic = await conn.fetchrow(
                """
                select
                  exists(select 1 from app.conversations where id=$1) as exists_any_tenant,
                  exists(select 1 from app.conversations where tenant_id=$2 and id=$1) as exists_for_tenant,
                  (select tenant_id::text from app.conversations where id=$1 limit 1) as actual_tenant_id,
                  (select status from app.conversations where id=$1 limit 1) as actual_status
                """,
                conversation_id,
                tenant_id,
            )
            log.warning(
                'operations.conversation.detail_not_found',
                tenant_id=str(tenant_id),
                conversation_id=str(conversation_id),
                actor_id=getattr(request.state, 'actor_id', None),
                exists_any_tenant=bool(diagnostic and diagnostic['exists_any_tenant']),
                exists_for_tenant=bool(diagnostic and diagnostic['exists_for_tenant']),
                actual_tenant_id=diagnostic['actual_tenant_id'] if diagnostic else None,
                actual_status=diagnostic['actual_status'] if diagnostic else None,
                diagnostic_flag='DEBUG_CROSS_TENANT_DIAGNOSTICS',
            )
        else:
            # Log mínimo: solo info que el caller YA conoce (su tenant_id, su
            # conversation_id pedido, su actor_id). Cero info cross-tenant.
            log.info(
                'operations.conversation.detail_not_found',
                tenant_id=str(tenant_id),
                conversation_id=str(conversation_id),
                actor_id=getattr(request.state, 'actor_id', None),
            )
        raise HTTPException(status_code=404, detail='Conversation not found')
    log.info(
        'operations.conversation.detail_found',
        tenant_id=str(tenant_id),
        conversation_id=str(conversation_id),
        status=row['status'],
        contact_id=str(row['contact_id']),
        actor_id=getattr(request.state, 'actor_id', None),
    )
    messages = await conn.fetch(
        'select * from app.messages where tenant_id=$1 and conversation_id=$2 order by created_at',
        tenant_id,
        conversation_id,
    )
    handoffs = await conn.fetch(
        'select * from app.handoffs where tenant_id=$1 and conversation_id=$2 order by updated_at desc',
        tenant_id,
        conversation_id,
    )
    data = record_to_dict(row)
    data['messages'] = [record_to_dict(m) for m in messages]
    data['handoffs'] = [record_to_dict(h) for h in handoffs]
    tag_rows = await conn.fetch(
        """
        select t.id, t.name, t.color
        from app.contact_tag_assignments cta
        join app.contact_tags t on t.id = cta.tag_id and t.tenant_id = cta.tenant_id
        where cta.tenant_id = $1 and cta.contact_id = $2
        order by t.name
        """,
        tenant_id,
        row['contact_id'],
    )
    data['contact_tags'] = [
        {'id': str(r['id']), 'name': r['name'], 'color': r['color']} for r in tag_rows
    ]
    return data


@tenant_ops_router.get('/conversations/{conversation_id}/messages/{message_id}/media')
async def get_conversation_message_media(
    conversation_id: UUID,
    message_id: UUID,
    request: Request,
    tenant_id: UUID = Query(...),
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    message = await conn.fetchrow(
        """
        select m.id,
               m.tenant_id,
               m.conversation_id,
               m.message_type,
               m.media_id,
               m.mime_type,
               c.channel_id
        from app.messages m
        join app.conversations c
          on c.tenant_id = m.tenant_id
         and c.id = m.conversation_id
        where m.tenant_id = $1
          and m.conversation_id = $2
          and m.id = $3
        """,
        tenant_id,
        conversation_id,
        message_id,
    )

    if not message:
        raise HTTPException(status_code=404, detail='Message media not found')

    if message['message_type'] not in MEDIA_MESSAGE_TYPES:
        raise HTTPException(status_code=400, detail='Message is not a media message')

    if not message['media_id']:
        raise HTTPException(status_code=404, detail='Message has no WhatsApp media_id')

    channel = await conn.fetchrow(
        """
        select token_ref
        from app.tenant_channels
        where tenant_id = $1
          and id = $2
          and provider = 'whatsapp_cloud_api'
          and status = 'active'
        """,
        tenant_id,
        message['channel_id'],
    )

    if not channel:
        raise HTTPException(status_code=404, detail='WhatsApp channel not found')

    try:
        content, content_type = await download_whatsapp_media(
            media_id=str(message['media_id']),
            token_ref=channel['token_ref'],
        )

        return Response(
            content=content,
            media_type=content_type or message['mime_type'] or 'application/octet-stream',
            headers={
                'Cache-Control': 'private, max-age=300',
            },
        )

    except WhatsAppMediaTooLargeError as error:
        # AUDIT-49 / re-audit §1.5 (2026-05-18): typed exception → HTTP 413
        # con detail saneado (no expone el cap interno al cliente). El
        # `phase` (`preflight` o `streamed`) queda solo en logs server-side
        # para forensia operativa.
        log.warning(
            'media.payload_too_large',
            phase=error.phase,
            tenant_id=str(tenant_id),
            message_id=str(message_id),
            max_bytes=get_settings().knowledge_file_max_bytes,
        )
        raise HTTPException(
            status_code=413,
            detail='Media exceeds maximum allowed size',
        ) from error

    except httpx.HTTPStatusError as error:
        raise HTTPException(
            status_code=error.response.status_code,
            detail=error.response.text,
        ) from error

    except RuntimeError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error


@tenant_ops_router.post('/conversations/{conversation_id}/messages', status_code=202)
async def create_message(conversation_id: UUID, payload: MessageCreate, request: Request, conn: asyncpg.Connection = Depends(get_db), idempotency_key: str | None = Header(default=None, alias='Idempotency-Key')):
    await ensure_tenant_access(request, payload.tenant_id, conn)

    await conn.execute("select set_config('app.tenant_id', $1, true)", str(payload.tenant_id))
    conversation = await conn.fetchrow(
        'select id, status from app.conversations where tenant_id=$1 and id=$2',
        payload.tenant_id,
        conversation_id,
    )
    if not conversation:
        raise HTTPException(status_code=404, detail='Conversation not found for tenant')

    message_payload = dict(payload.payload)
    if payload.message_type in {'image', 'video'} and payload.body_text and 'caption' not in message_payload:
        message_payload['caption'] = payload.body_text.strip()
    validate_outbound_message_content(
        payload.message_type,
        payload.body_text,
        payload.media_id,
        media_url_from_payload(message_payload),
    )
    row = await conn.fetchrow(
        """
        insert into app.messages (
          tenant_id, conversation_id, direction, sender_actor_type, body_text,
          message_type, media_id, mime_type, payload, status
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, 'queued') returning *
        """,
        payload.tenant_id,
        conversation_id,
        payload.direction,
        payload.sender_actor_type,
        payload.body_text.strip() if payload.body_text else None,
        payload.message_type,
        payload.media_id.strip() if payload.media_id else None,
        payload.mime_type,
        json.dumps(message_payload),
    )
    key = idempotency_key or str(row['id'])
    await conn.execute(
        "insert into app.domain_events (tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload) values ($1,'message',$2,'message.queued',$3,$4::jsonb) on conflict do nothing",
        payload.tenant_id,
        row['id'],
        key,
        json.dumps({'conversation_id': str(conversation_id)}),
    )
    # BUG-020: NO flipear status a 'waiting_user' si hay un agente humano
    # trabajando activamente la conversación. Antes este UPDATE era
    # incondicional: si el agente humano enviaba un mensaje vía este
    # endpoint, el status pasaba de 'human_active' a 'waiting_user', y la
    # próxima respuesta del usuario entraba al orchestrator que evaluaba
    # `continue_bot` (porque su check solo skipea con status='human_active'
    # o 'waiting_agent'). El bot le pisaba la respuesta al agente humano,
    # rompiendo el handoff que el cliente había pedido.
    # Fix: chequear si hay un handoff con status='accepted' y agente
    # asignado. Si lo hay, dejar el status como 'human_active' (el agente
    # sigue activo, el bot debe seguir silenciado). Sino, mantener el
    # comportamiento original (flipear a 'waiting_user').
    active_human_handoff = await conn.fetchval(
        """
        select id from app.handoffs
        where tenant_id=$1 and conversation_id=$2
          and status='accepted' and assigned_to is not null
        limit 1
        """,
        payload.tenant_id,
        conversation_id,
    )
    if active_human_handoff:
        # Agente humano sigue activo. Mantener 'human_active' (que el
        # orchestrator ya skipea con el check de línea ~250).
        await conn.execute(
            "update app.conversations set status='human_active' where tenant_id=$1 and id=$2",
            payload.tenant_id,
            conversation_id,
        )
    else:
        # Sin handoff humano activo → flow normal del bot (waiting_user).
        await conn.execute(
            "update app.conversations set status='waiting_user' where tenant_id=$1 and id=$2",
            payload.tenant_id,
            conversation_id,
        )
    await audit(conn, tenant_id=payload.tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='message.queued', entity_type='message', entity_id=str(row['id']))
    await notify_operations_change(
        conn,
        payload.tenant_id,
        'conversation.changed',
        conversation_id=conversation_id,
        message_id=row['id'],
    )
    return record_to_dict(row)


@tenant_ops_router.post('/conversations/{conversation_id}/handoff', status_code=202)
async def create_handoff(
    conversation_id: UUID,
    request: Request,
    # BUG-157: antes aceptábamos `payload: dict` raw — cualquier reason
    # (sin límite) llegaba a la columna `handoffs.reason text` y a la
    # métrica Prometheus `cpi_handoff_total{reason}`. Aunque
    # `normalize_handoff_reason` bucketea a `other`, el body raw permitía
    # strings gigantes (DOS). `HandoffCreate` acota a max_length=80.
    payload: HandoffCreate,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    conversation = await conn.fetchrow(
        'select id from app.conversations where tenant_id=$1 and id=$2', tenant_id, conversation_id
    )
    if not conversation:
        raise HTTPException(status_code=404, detail='Conversation not found')
    row = await conn.fetchrow(
        """
        insert into app.handoffs (tenant_id, conversation_id, reason, assigned_to)
        values ($1, $2, $3, null) returning *
        """,
        tenant_id,
        conversation_id,
        payload.reason or 'manual_or_policy_handoff',
    )
    await conn.execute("update app.conversations set status='human_required', handoff_required=true where tenant_id=$1 and id=$2", tenant_id, conversation_id)
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='handoff.created', entity_type='handoff', entity_id=str(row['id']))
    record_handoff(tenant_id=tenant_id, reason=str(row['reason'] or 'manual'))
    return record_to_dict(row)


@tenant_ops_router.post('/conversations/{conversation_id}/handoff/accept', status_code=202)
async def accept_handoff(
    conversation_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    tenant_id = await tenant_id_from_request(request, conn)
    user_id = await current_user_id_from_request(request, conn)
    handoff = await conn.fetchrow(
        """
        update app.handoffs
        set status='accepted', assigned_to=$3, updated_at=now()
        where id = (
          select id
          from app.handoffs
          where tenant_id=$1 and conversation_id=$2 and status='open'
          order by updated_at desc
          limit 1
        )
        returning *
        """,
        tenant_id,
        conversation_id,
        user_id,
    )
    if not handoff:
        raise HTTPException(status_code=404, detail='Open handoff not found')
    await conn.execute(
        """
        update app.conversations
        set status='human_active', handoff_required=false, current_owner_user_id=$3
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        conversation_id,
        user_id,
    )
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='handoff.accepted', entity_type='handoff', entity_id=str(handoff['id']))
    return record_to_dict(handoff)


@tenant_ops_router.post('/conversations/{conversation_id}/release', status_code=202)
async def release_conversation(
    conversation_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    tenant_id = await tenant_id_from_request(request, conn)
    row = await conn.fetchrow(
        """
        update app.conversations
        set status='open', handoff_required=false, current_owner_user_id=null
        where tenant_id=$1 and id=$2
        returning *
        """,
        tenant_id,
        conversation_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Conversation not found')
    await conn.execute(
        """
        update app.handoffs
        set status='resolved', updated_at=now()
        where tenant_id=$1 and conversation_id=$2 and status in ('open','accepted')
        """,
        tenant_id,
        conversation_id,
    )
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='conversation.released', entity_type='conversation', entity_id=str(conversation_id))
    return record_to_dict(row)


@tenant_ops_router.get('/branches')
async def list_branches(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    is_active: bool | None = Query(default=None),
):
    tenant_id = await tenant_id_from_request(request, conn)
    rows = await conn.fetch(
        """
        select *
        from app.branches
        where tenant_id=$1
          and ($2::boolean is null or is_active=$2)
        order by sort_order asc, name asc
        limit 250
        """,
        tenant_id,
        is_active,
    )
    return [record_to_dict(row) for row in rows]


@tenant_ops_router.get('/packages')
async def list_treatment_packages(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    is_active: bool | None = Query(default=None),
):
    tenant_id = await tenant_id_from_request(request, conn)
    rows = await conn.fetch(
        """
        select *
        from app.treatment_packages
        where tenant_id=$1
          and ($2::boolean is null or is_active=$2)
        order by sort_order asc, name asc
        limit 250
        """,
        tenant_id,
        is_active,
    )
    return [record_to_dict(row) for row in rows]


@tenant_ops_router.get('/contacts/{contact_id}/packages')
async def list_contact_packages(
    contact_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    status_filter: str | None = Query(default=None, alias='status'),
):
    tenant_id = await tenant_id_from_request(request, conn)
    rows = await conn.fetch(
        """
        select cp.*, tp.name as package_name, tp.includes_service_ids
        from app.contact_packages cp
        join app.treatment_packages tp
          on tp.id=cp.package_id and tp.tenant_id=cp.tenant_id
        where cp.tenant_id=$1
          and cp.contact_id=$2
          and ($3::text is null or cp.status=$3)
        order by cp.purchased_at desc
        limit 250
        """,
        tenant_id,
        contact_id,
        status_filter,
    )
    return [record_to_dict(row) for row in rows]


@tenant_ops_router.get('/subscription-plans')
async def list_subscription_plans(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    status_filter: str | None = Query(default=None, alias='status'),
):
    tenant_id = await tenant_id_from_request(request, conn)
    rows = await conn.fetch(
        """
        select *
        from app.subscription_plans
        where tenant_id=$1
          and ($2::text is null or status=$2)
        order by status asc, name asc
        limit 250
        """,
        tenant_id,
        status_filter,
    )
    return [record_to_dict(row) for row in rows]


@tenant_ops_router.get('/subscriptions')
async def list_contact_subscriptions(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    status_filter: str | None = Query(default=None, alias='status'),
    plan_id: UUID | None = Query(default=None),
    contact_id: UUID | None = Query(default=None),
):
    tenant_id = await tenant_id_from_request(request, conn)
    rows = await conn.fetch(
        """
        select cs.*, sp.name as plan_name, sp.billing_period as plan_billing_period,
               sp.price_amount as plan_price_amount, sp.currency as plan_currency,
               c.display_name as contact_display_name, c.phone_e164 as contact_phone_e164
        from app.contact_subscriptions cs
        join app.subscription_plans sp on sp.id=cs.plan_id and sp.tenant_id=cs.tenant_id
        join app.contacts c on c.id=cs.contact_id and c.tenant_id=cs.tenant_id
        where cs.tenant_id=$1
          and ($2::text is null or cs.status=$2)
          and ($3::uuid is null or cs.plan_id=$3)
          and ($4::uuid is null or cs.contact_id=$4)
        order by cs.started_at desc
        limit 250
        """,
        tenant_id,
        status_filter,
        plan_id,
        contact_id,
    )
    return [record_to_dict(row) for row in rows]


@tenant_ops_router.get('/resources')
async def list_resources(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    resource_type: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
    branch_id: UUID | None = Query(default=None),
):
    tenant_id = await tenant_id_from_request(request, conn)
    rows = await conn.fetch(
        """
        select *
        from app.resources
        where tenant_id=$1
          and ($2::text is null or resource_type=$2)
          and ($3::boolean is null or is_active=$3)
          and ($4::uuid is null or branch_id=$4)
        order by is_active desc, resource_type, name
        limit 250
        """,
        tenant_id,
        resource_type,
        is_active,
        branch_id,
    )
    return [record_to_dict(row) for row in rows]


@tenant_ops_router.post('/resources', status_code=201)
async def create_resource(payload: ResourceCreate, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    await ensure_tenant_access(request, payload.tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(payload.tenant_id))
    vertical_code = (payload.vertical_code or '').strip()
    if not vertical_code:
        vertical_code = (
            await conn.fetchval('select vertical_code from app.tenants where id=$1', payload.tenant_id)
            or 'general'
        )
    try:
        row = await conn.fetchrow(
            """
            insert into app.resources (
                tenant_id, vertical_code, resource_type, code, name, capabilities,
                bio, photo_media_asset_id, specialty, license_number, years_of_experience,
                public_profile, branch_id, is_active
            )
            values ($1,$2,$3,$4,$5,$6::jsonb,$7,$8,$9,$10,$11,$12,$13,$14)
            returning *
            """,
            payload.tenant_id,
            vertical_code,
            payload.resource_type,
            payload.code,
            payload.name,
            json.dumps(payload.capabilities),
            payload.bio,
            payload.photo_media_asset_id,
            payload.specialty,
            payload.license_number,
            payload.years_of_experience,
            payload.public_profile,
            payload.branch_id,
            payload.is_active,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail='Resource code already exists for tenant') from exc
    except asyncpg.ForeignKeyViolationError as exc:
        raise HTTPException(status_code=400, detail='photo_media_asset_id or branch_id not found for tenant') from exc
    await audit(conn, tenant_id=payload.tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='resource.created', entity_type='resource', entity_id=str(row['id']))
    return record_to_dict(row)


@tenant_ops_router.patch('/resources/{resource_id}')
async def update_resource(resource_id: UUID, payload: ResourceUpdate, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    tenant_id = await tenant_id_from_request(request, conn)
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        row = await conn.fetchrow('select * from app.resources where tenant_id=$1 and id=$2', tenant_id, resource_id)
        if not row:
            raise HTTPException(status_code=404, detail='Resource not found')
        return record_to_dict(row)
    profile_fields = {
        'bio',
        'photo_media_asset_id',
        'specialty',
        'license_number',
        'years_of_experience',
        'public_profile',
    }
    profile_changed = bool(profile_fields & update_data.keys())
    try:
        row = await conn.fetchrow(
            """
            update app.resources
            set vertical_code=coalesce($3, vertical_code),
                resource_type=coalesce($4, resource_type),
                code=coalesce($5, code),
                name=coalesce($6, name),
                capabilities=coalesce($7::jsonb, capabilities),
                bio=case when $14::boolean then $8 else bio end,
                photo_media_asset_id=case when $15::boolean then $9 else photo_media_asset_id end,
                specialty=case when $16::boolean then $10 else specialty end,
                license_number=case when $17::boolean then $11 else license_number end,
                years_of_experience=case when $18::boolean then $12 else years_of_experience end,
                public_profile=coalesce($13, public_profile),
                branch_id=case when $20::boolean then $21 else branch_id end,
                is_active=coalesce($19, is_active)
            where tenant_id=$1 and id=$2
            returning *
            """,
            tenant_id,
            resource_id,
            update_data.get('vertical_code'),
            update_data.get('resource_type'),
            update_data.get('code'),
            update_data.get('name'),
            json.dumps(update_data['capabilities']) if 'capabilities' in update_data else None,
            update_data.get('bio'),
            update_data.get('photo_media_asset_id'),
            update_data.get('specialty'),
            update_data.get('license_number'),
            update_data.get('years_of_experience'),
            update_data.get('public_profile'),
            'bio' in update_data,
            'photo_media_asset_id' in update_data,
            'specialty' in update_data,
            'license_number' in update_data,
            'years_of_experience' in update_data,
            update_data.get('is_active'),
            'branch_id' in update_data,
            update_data.get('branch_id'),
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail='Resource code already exists for tenant') from exc
    except asyncpg.ForeignKeyViolationError as exc:
        raise HTTPException(status_code=400, detail='photo_media_asset_id or branch_id not found for tenant') from exc
    if not row:
        raise HTTPException(status_code=404, detail='Resource not found')
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='resource.updated', entity_type='resource', entity_id=str(resource_id))
    if profile_changed:
        await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='resource.profile_updated', entity_type='resource', entity_id=str(resource_id))
    return record_to_dict(row)


@tenant_ops_router.delete('/resources/{resource_id}', status_code=204)
async def deactivate_resource(resource_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    tenant_id = await tenant_id_from_request(request, conn)
    row = await conn.fetchrow(
        """
        update app.resources
        set is_active=false
        where tenant_id=$1 and id=$2
        returning id
        """,
        tenant_id,
        resource_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Resource not found')
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='resource.deactivated', entity_type='resource', entity_id=str(resource_id))
    return Response(status_code=204)


@tenant_ops_router.post('/service-requests', status_code=201)
async def create_service_request(payload: ServiceRequestCreate, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    await ensure_tenant_access(request, payload.tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(payload.tenant_id))
    row = await conn.fetchrow(
        """
        insert into app.service_requests (tenant_id, contact_id, conversation_id, vertical_code, service_type, problem_summary, urgency, intake)
        values ($1,$2,$3,$4,$5,$6,$7,$8::jsonb) returning *
        """,
        payload.tenant_id, payload.contact_id, payload.conversation_id, payload.vertical_code, payload.service_type, payload.problem_summary, payload.urgency, json.dumps(payload.intake),
    )
    return record_to_dict(row)


@tenant_ops_router.get('/service-requests')
async def list_service_requests(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    contact_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias='status'),
    vertical_code: str | None = Query(default=None),
):
    tenant_id = await tenant_id_from_request(request, conn)
    rows = await conn.fetch(
        """
        select sr.*, c.display_name as contact_label, c.phone_e164
        from app.service_requests sr
        join app.contacts c on c.id = sr.contact_id and c.tenant_id = sr.tenant_id
        where sr.tenant_id = $1
          and ($2::uuid is null or sr.contact_id = $2)
          and ($3::text is null or sr.status = $3)
          and ($4::text is null or sr.vertical_code = $4)
        order by sr.created_at desc
        limit 250
        """,
        tenant_id,
        contact_id,
        status_filter,
        vertical_code,
    )
    return [record_to_dict(row) for row in rows]


@tenant_ops_router.get('/service-requests/{request_id}')
async def get_service_request(request_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    tenant_id = await tenant_id_from_request(request, conn)
    row = await conn.fetchrow(
        """
        select sr.*, c.display_name as contact_label, c.phone_e164
        from app.service_requests sr
        join app.contacts c on c.id = sr.contact_id and c.tenant_id = sr.tenant_id
        where sr.tenant_id = $1 and sr.id = $2
        """,
        tenant_id,
        request_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Service request not found')
    return record_to_dict(row)


@tenant_ops_router.patch('/service-requests/{request_id}')
async def patch_service_request(
    request_id: UUID,
    payload: ServiceRequestPatch,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    update_data = payload.model_dump(exclude_unset=True)
    intake_patch = update_data.pop('intake', None)
    row = await conn.fetchrow(
        """
        update app.service_requests
        set status = coalesce($3, status),
            assigned_resource_id = coalesce($4, assigned_resource_id),
            problem_summary = coalesce($5, problem_summary),
            urgency = coalesce($6, urgency),
            preferred_date = coalesce($7::date, preferred_date),
            preferred_slot = coalesce($8, preferred_slot),
            intake = case when $9::jsonb is not null then intake || $9::jsonb else intake end
        where tenant_id = $1 and id = $2
        returning *
        """,
        tenant_id,
        request_id,
        update_data.get('status'),
        update_data.get('assigned_resource_id'),
        update_data.get('problem_summary'),
        update_data.get('urgency'),
        update_data.get('preferred_date'),
        update_data.get('preferred_slot'),
        json.dumps(intake_patch) if intake_patch is not None else None,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Service request not found')
    return record_to_dict(row)


@tenant_ops_router.post('/service-requests/{request_id}/quotes', status_code=201)
async def create_quote(
    request_id: UUID,
    payload: QuoteCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    sr = await conn.fetchrow('select id from app.service_requests where tenant_id=$1 and id=$2', tenant_id, request_id)
    if not sr:
        raise HTTPException(status_code=404, detail='Service request not found')
    items = [item.model_dump() for item in payload.line_items]
    subtotal = _compute_quote_subtotal(items)
    grand_total = subtotal - payload.discount_total + payload.tax_total
    try:
        row = await conn.fetchrow(
            """
            insert into app.quotes
              (tenant_id, service_request_id, currency, subtotal, discount_total, tax_total, grand_total, line_items, valid_until)
            values ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9)
            returning *
            """,
            tenant_id,
            request_id,
            payload.currency,
            subtotal,
            payload.discount_total,
            payload.tax_total,
            grand_total,
            json.dumps(items),
            payload.valid_until,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail='A quote already exists for this service request') from exc
    await conn.execute(
        "update app.service_requests set status='quoted' where tenant_id=$1 and id=$2 and status not in ('scheduled','resolved','cancelled')",
        tenant_id, request_id,
    )
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='quote.created', entity_type='quote', entity_id=str(row['id']))
    return record_to_dict(row)


@tenant_ops_router.get('/service-requests/{request_id}/quote')
async def get_quote_for_service_request(request_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    tenant_id = await tenant_id_from_request(request, conn)
    row = await conn.fetchrow(
        'select * from app.quotes where tenant_id=$1 and service_request_id=$2',
        tenant_id, request_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Quote not found')
    return record_to_dict(row)


@tenant_ops_router.patch('/quotes/{quote_id}')
async def patch_quote(
    quote_id: UUID,
    payload: QuotePatch,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    existing = await conn.fetchrow('select * from app.quotes where tenant_id=$1 and id=$2', tenant_id, quote_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Quote not found')
    update_data = payload.model_dump(exclude_unset=True)
    items = [item.model_dump() for item in payload.line_items] if payload.line_items is not None else None
    next_items = items if items is not None else (existing['line_items'] if isinstance(existing['line_items'], list) else json.loads(existing['line_items']))
    next_discount = update_data.get('discount_total', existing['discount_total'])
    next_tax = update_data.get('tax_total', existing['tax_total'])
    subtotal = _compute_quote_subtotal(next_items)
    grand_total = subtotal - next_discount + next_tax
    row = await conn.fetchrow(
        """
        update app.quotes
        set line_items     = coalesce($3::jsonb, line_items),
            currency       = coalesce($4, currency),
            discount_total = $5,
            tax_total      = $6,
            subtotal       = $7,
            grand_total    = $8,
            status         = coalesce($9, status),
            valid_until    = coalesce($10, valid_until)
        where tenant_id=$1 and id=$2
        returning *
        """,
        tenant_id,
        quote_id,
        json.dumps(items) if items is not None else None,
        update_data.get('currency'),
        next_discount,
        next_tax,
        subtotal,
        grand_total,
        update_data.get('status'),
        update_data.get('valid_until'),
    )
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='quote.updated', entity_type='quote', entity_id=str(quote_id))
    return record_to_dict(row)


@tenant_ops_router.post('/quotes/{quote_id}/send', status_code=202)
async def send_quote(
    quote_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    quote = await conn.fetchrow('select * from app.quotes where tenant_id=$1 and id=$2', tenant_id, quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail='Quote not found')
    sr = await conn.fetchrow('select * from app.service_requests where tenant_id=$1 and id=$2', tenant_id, quote['service_request_id'])
    if not sr['conversation_id']:
        raise HTTPException(status_code=422, detail='Service request has no associated conversation')
    conversation = await conn.fetchrow('select * from app.conversations where tenant_id=$1 and id=$2', tenant_id, sr['conversation_id'])
    if not conversation:
        raise HTTPException(status_code=422, detail='Conversation not found')
    body_text = _build_quote_summary_text(sr, quote)
    message = await conn.fetchrow(
        """
        insert into app.messages
          (tenant_id, conversation_id, direction, sender_actor_type, sender_actor_id, body_text, message_type, payload, status)
        values ($1,$2,'outbound','agent',$3,$4,'text','{}','queued')
        returning *
        """,
        tenant_id,
        conversation['id'],
        request.state.actor_id,
        body_text,
    )
    idempotency_key = f"quote-send-{quote_id}"
    await conn.execute(
        "insert into app.domain_events (tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload) values ($1,'message',$2,'message.queued',$3,$4::jsonb) on conflict do nothing",
        tenant_id,
        message['id'],
        idempotency_key,
        json.dumps({'conversation_id': str(conversation['id']), 'quote_id': str(quote_id)}),
    )
    await conn.execute(
        "update app.quotes set status='sent' where tenant_id=$1 and id=$2 and status='draft'",
        tenant_id, quote_id,
    )
    await conn.execute(
        "update app.service_requests set status='quoted' where tenant_id=$1 and id=$2 and status='open'",
        tenant_id, sr['id'],
    )
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='quote.sent', entity_type='quote', entity_id=str(quote_id))
    await notify_operations_change(conn, tenant_id, 'conversation.changed', conversation_id=conversation['id'], message_id=message['id'])
    return {'quote_id': str(quote_id), 'message_id': str(message['id'])}


@tenant_ops_router.get('/appointments')
async def list_appointments(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    resource_id: UUID | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias='status'),
    branch_id: UUID | None = Query(default=None),
    from_date: date | None = Query(default=None, description='Lower bound (inclusive) on starts_at, ISO date.'),
    to_date: date | None = Query(default=None, description='Upper bound (exclusive next day) on starts_at, ISO date.'),
):
    """BUG-044: agregados `from_date` / `to_date` para filtrar server-side.

    Antes el endpoint devolvía las 250 más recientes sin filtro por fecha;
    el frontend (`useTodayAppointmentsData`) filtraba por día en cliente,
    pero para tenants con >250 citas, el día actual podía caer fuera del
    slice y el panel mostraba "no hay citas hoy" cuando sí las había.

    BUG-180 (codex P2 sobre BUG-044): el cliente envía `from_date`/`to_date`
    como `YYYY-MM-DD` local del tenant (de `todayISO()` en
    `useTodayAppointmentsData`). El SQL antes hacía `a.starts_at >= $5::date`,
    que Postgres evaluaba en la TZ de sesión (UTC). Para `America/Bogota`
    (UTC-5), una cita local `2026-05-14 22:00` se guarda como
    `2026-05-15 03:00 UTC` — el comparador la excluía del filtro
    `from=2026-05-14&to=2026-05-14`. Fix: comparar `(a.starts_at AT TIME
    ZONE t.timezone)::date` contra los bounds, leyendo `t.timezone` del
    join con `app.tenants` (column existente, `timestamptz` aware).
    """
    tenant_id = await tenant_id_from_request(request, conn)
    rows = await conn.fetch(
        """
        select a.*, r.name as resource_name, r.code as resource_code, c.display_name as contact_label, c.phone_e164
        from app.appointments a
        join app.resources r on r.id=a.resource_id and r.tenant_id=a.tenant_id
        join app.contacts c on c.id=a.contact_id and c.tenant_id=a.tenant_id
        join app.tenants t on t.id=a.tenant_id
        where a.tenant_id=$1
          and ($2::uuid is null or a.resource_id=$2)
          and ($3::text is null or a.status=$3)
          and ($4::uuid is null or a.branch_id=$4)
          and ($5::date is null or (a.starts_at at time zone t.timezone)::date >= $5::date)
          and ($6::date is null or (a.starts_at at time zone t.timezone)::date <= $6::date)
        order by a.starts_at desc
        limit 250
        """,
        tenant_id,
        resource_id,
        status_filter,
        branch_id,
        from_date,
        to_date,
    )
    return [record_to_dict(row) for row in rows]


@tenant_ops_router.post('/appointments', status_code=201)
async def create_appointment(payload: AppointmentCreate, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    await ensure_tenant_access(request, payload.tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(payload.tenant_id))
    await ensure_resource_available(conn, tenant_id=payload.tenant_id, resource_id=payload.resource_id, starts_at=payload.starts_at, ends_at=payload.ends_at)
    closing_user_id = await current_user_id_from_request(request, conn)
    appointment_metadata: dict[str, Any] = {}
    if closing_user_id is not None:
        appointment_metadata['closed_by_user_id'] = str(closing_user_id)
        appointment_metadata['closed_at'] = datetime.now(UTC).isoformat()
    try:
        row = await conn.fetchrow(
            """
            insert into app.appointments (tenant_id, contact_id, conversation_id, service_request_id, service_id, resource_id, service_code, starts_at, ends_at, notes, metadata)
            values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11::jsonb) returning *
            """,
            payload.tenant_id, payload.contact_id, payload.conversation_id, payload.service_request_id, payload.service_id, payload.resource_id, payload.service_code, payload.starts_at, payload.ends_at, payload.notes, json.dumps(appointment_metadata),
        )
    except asyncpg.ExclusionViolationError as exc:
        raise HTTPException(status_code=409, detail='Resource has a conflicting appointment') from exc
    if payload.service_request_id:
        await conn.execute(
            """
            update app.service_requests
            set status='scheduled', assigned_resource_id=$3
            where tenant_id=$1 and id=$2
            """,
            payload.tenant_id,
            payload.service_request_id,
            payload.resource_id,
        )
    try:
        await create_appointment_reminder_jobs(conn, payload.tenant_id, row['id'])
    except Exception:
        log.exception(
            'appointment.notifications_failed',
            tenant_id=str(payload.tenant_id),
            appointment_id=str(row['id']),
        )
    try:
        await attribute_appointment(
            conn,
            tenant_id=payload.tenant_id,
            appointment_id=row['id'],
            contact_id=payload.contact_id,
        )
    except Exception:
        log.exception(
            'appointment.attribution_failed',
            tenant_id=str(payload.tenant_id),
            appointment_id=str(row['id']),
        )
    await audit(conn, tenant_id=payload.tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='appointment.created', entity_type='appointment', entity_id=str(row['id']))
    record_appointment(tenant_id=payload.tenant_id, status='created')
    return record_to_dict(row)


@tenant_ops_router.patch('/appointments/{appointment_id}')
async def update_appointment(appointment_id: UUID, payload: AppointmentUpdate, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    tenant_id = await tenant_id_from_request(request, conn)
    existing = await conn.fetchrow('select * from app.appointments where tenant_id=$1 and id=$2', tenant_id, appointment_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Appointment not found')
    update_data = payload.model_dump(exclude_unset=True)
    next_resource_id = update_data.get('resource_id') or existing['resource_id']
    next_starts_at = update_data.get('starts_at') or existing['starts_at']
    next_ends_at = update_data.get('ends_at') or existing['ends_at']
    next_status = update_data.get('status') or existing['status']
    if next_status in ('scheduled', 'confirmed'):
        await ensure_resource_available(conn, tenant_id=tenant_id, resource_id=next_resource_id, starts_at=next_starts_at, ends_at=next_ends_at, appointment_id=appointment_id)
    else:
        if next_starts_at >= next_ends_at:
            raise HTTPException(status_code=400, detail='Appointment starts_at must be before ends_at')
        if 'resource_id' in update_data:
            resource = await conn.fetchrow(
                'select id from app.resources where tenant_id=$1 and id=$2',
                tenant_id,
                next_resource_id,
            )
            if not resource:
                raise HTTPException(status_code=404, detail='Resource not found')
    closing_user_id = await current_user_id_from_request(request, conn)
    existing_metadata = existing['metadata']
    if isinstance(existing_metadata, str):
        existing_metadata = json.loads(existing_metadata) if existing_metadata else {}
    elif existing_metadata is None:
        existing_metadata = {}
    metadata_patch: dict[str, Any] = {}
    if (
        closing_user_id is not None
        and next_status in {'confirmed', 'completed'}
        and existing['status'] != next_status
        and not existing_metadata.get('closed_by_user_id')
    ):
        metadata_patch['closed_by_user_id'] = str(closing_user_id)
        metadata_patch['closed_at'] = datetime.now(UTC).isoformat()
    try:
        row = await conn.fetchrow(
            """
            update app.appointments
            set resource_id=$3,
                service_code=coalesce($4, service_code),
                starts_at=$5,
                ends_at=$6,
                status=$7,
                confirmation_status=coalesce($8, confirmation_status),
                notes=coalesce($9, notes),
                metadata=metadata || $10::jsonb
            where tenant_id=$1 and id=$2
            returning *
            """,
            tenant_id,
            appointment_id,
            next_resource_id,
            update_data.get('service_code'),
            next_starts_at,
            next_ends_at,
            next_status,
            update_data.get('confirmation_status'),
            update_data.get('notes'),
            json.dumps(metadata_patch),
        )
    except asyncpg.ExclusionViolationError as exc:
        raise HTTPException(status_code=409, detail='Resource has a conflicting appointment') from exc
    action = 'appointment.cancelled' if next_status == 'cancelled' else 'appointment.updated'
    if next_status in {'cancelled', 'completed', 'no_show', 'confirmed'}:
        record_appointment(tenant_id=tenant_id, status=next_status)
    try:
        if next_status == 'cancelled':
            await cancel_appointment_reminder_jobs(conn, tenant_id, appointment_id)
        elif (
            'starts_at' in update_data
            or 'ends_at' in update_data
            or 'resource_id' in update_data
        ):
            await regenerate_appointment_reminder_jobs(conn, tenant_id, appointment_id)
    except Exception:
        log.exception(
            'appointment.notifications_failed',
            tenant_id=str(tenant_id),
            appointment_id=str(appointment_id),
        )
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action=action, entity_type='appointment', entity_id=str(appointment_id))
    return record_to_dict(row)


@tenant_ops_router.post('/appointments/{appointment_id}/cancel', status_code=202)
async def cancel_appointment(appointment_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    tenant_id = await tenant_id_from_request(request, conn)
    row = await conn.fetchrow(
        """
        update app.appointments
        set status='cancelled'
        where tenant_id=$1 and id=$2 and status <> 'cancelled'
        returning *
        """,
        tenant_id,
        appointment_id,
    )
    if not row:
        exists = await conn.fetchrow('select id from app.appointments where tenant_id=$1 and id=$2', tenant_id, appointment_id)
        if not exists:
            raise HTTPException(status_code=404, detail='Appointment not found')
        row = await appointment_detail(conn, tenant_id, appointment_id)
    else:
        try:
            await cancel_appointment_reminder_jobs(conn, tenant_id, appointment_id)
        except Exception:
            log.exception(
                'appointment.notifications_failed',
                tenant_id=str(tenant_id),
                appointment_id=str(appointment_id),
            )
        await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='appointment.cancelled', entity_type='appointment', entity_id=str(appointment_id))
        record_appointment(tenant_id=tenant_id, status='cancelled')
    return record_to_dict(row)


@tenant_ops_router.get('/appointments/{appointment_id}/feedback')
async def list_appointment_feedback(
    appointment_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    appointment = await conn.fetchrow(
        'select id from app.appointments where tenant_id=$1 and id=$2',
        tenant_id,
        appointment_id,
    )
    if not appointment:
        raise HTTPException(status_code=404, detail='Appointment not found')
    rows = await conn.fetch(
        """
        select id, tenant_id, appointment_id, contact_id, rating, comment, created_at
        from app.appointment_feedback
        where tenant_id=$1 and appointment_id=$2
        order by created_at desc
        """,
        tenant_id,
        appointment_id,
    )
    return [record_to_dict(row) for row in rows]


@tenant_ops_router.post('/appointments/{appointment_id}/feedback', status_code=201)
async def create_appointment_feedback(
    appointment_id: UUID,
    payload: dict,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    rating = payload.get('rating') if isinstance(payload, dict) else None
    if not isinstance(rating, int) or rating < 1 or rating > 5:
        raise HTTPException(status_code=400, detail='rating must be an integer 1-5')
    appointment = await conn.fetchrow(
        'select id, contact_id from app.appointments where tenant_id=$1 and id=$2',
        tenant_id,
        appointment_id,
    )
    if not appointment:
        raise HTTPException(status_code=404, detail='Appointment not found')
    row = await conn.fetchrow(
        """
        insert into app.appointment_feedback (tenant_id, appointment_id, contact_id, rating, comment)
        values ($1, $2, $3, $4, $5)
        returning id, tenant_id, appointment_id, contact_id, rating, comment, created_at
        """,
        tenant_id,
        appointment_id,
        appointment['contact_id'],
        rating,
        (payload.get('comment') if isinstance(payload, dict) else None),
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='appointment.feedback_recorded',
        entity_type='appointment_feedback',
        entity_id=str(row['id']),
        metadata={'rating': rating, 'appointment_id': str(appointment_id)},
    )
    return record_to_dict(row)


@tenant_ops_router.post('/appointments/{appointment_id}/payment-link')
async def create_appointment_payment_link(
    appointment_id: UUID,
    payload: AppointmentPaymentLinkRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    appointment = await conn.fetchrow(
        'select * from app.appointments where tenant_id=$1 and id=$2',
        tenant_id,
        appointment_id,
    )
    if not appointment:
        raise HTTPException(status_code=404, detail='Appointment not found')
    payment_settings = await _fetch_tenant_payment_settings(conn, tenant_id)
    if payment_settings['provider'] == 'none':
        raise HTTPException(status_code=422, detail='Tenant has no payment provider configured')
    api_key = resolve_secret_ref(payment_settings.get('api_key_ref'))
    if not api_key:
        raise HTTPException(status_code=422, detail='Payment provider API key is not configured')
    amount = payload.amount if payload.amount is not None else appointment['payment_amount']
    if amount is None:
        amount = payment_settings.get('default_amount')
    if amount is None or float(amount) <= 0:
        raise HTTPException(status_code=400, detail='Amount is required to generate a payment link')
    currency = (payload.currency or appointment['payment_currency'] or payment_settings['currency']).upper()
    description = (
        payload.description
        or appointment['service_code']
        or 'Servicio'
    )[:200]
    external_ref = _appointment_payment_external_ref(tenant_id, appointment_id)
    try:
        link = await provider_generate_payment_link(
            provider=payment_settings['provider'],
            api_key=api_key,
            amount=amount,
            currency=currency,
            description=description,
            external_ref=external_ref,
        )
    except PaymentProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    row = await conn.fetchrow(
        """
        update app.appointments
        set payment_status='pending',
            payment_amount=$3,
            payment_currency=$4,
            payment_link=$5,
            payment_provider=$6,
            payment_provider_reference=$7,
            payment_link_generated_at=now()
        where tenant_id=$1 and id=$2
        returning *
        """,
        tenant_id,
        appointment_id,
        amount,
        currency,
        link.url,
        payment_settings['provider'],
        link.provider_reference,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='appointment.payment_link_generated',
        entity_type='appointment',
        entity_id=str(appointment_id),
        metadata={'provider': payment_settings['provider'], 'amount': str(amount), 'currency': currency},
    )
    return _appointment_payment_summary(row)


@tenant_ops_router.post('/appointments/{appointment_id}/send-payment', status_code=202)
async def send_appointment_payment_link(
    appointment_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    appointment = await conn.fetchrow(
        """
        select a.*, c.display_name as contact_name
        from app.appointments a
        join app.contacts c on c.tenant_id=a.tenant_id and c.id=a.contact_id
        where a.tenant_id=$1 and a.id=$2
        """,
        tenant_id,
        appointment_id,
    )
    if not appointment:
        raise HTTPException(status_code=404, detail='Appointment not found')
    if not appointment['payment_link']:
        raise HTTPException(status_code=422, detail='Generate a payment link before sending it')
    conversation_id = appointment['conversation_id']
    if not conversation_id:
        conversation = await conn.fetchrow(
            """
            select id from app.conversations
            where tenant_id=$1 and contact_id=$2 and status not in ('archived')
            order by updated_at desc
            limit 1
            """,
            tenant_id,
            appointment['contact_id'],
        )
        if not conversation:
            raise HTTPException(status_code=422, detail='Contact has no open conversation to receive the payment link')
        conversation_id = conversation['id']
    amount = appointment['payment_amount']
    currency = appointment['payment_currency'] or 'COP'
    contact_name = appointment['contact_name'] or 'Hola'
    body_text = (
        f'Hola {contact_name}, te compartimos el link para pagar tu cita '
        f'({amount} {currency}):\n{appointment["payment_link"]}'
    )
    message = await conn.fetchrow(
        """
        insert into app.messages
          (tenant_id, conversation_id, direction, sender_actor_type, sender_actor_id, body_text, message_type, payload, status)
        values ($1,$2,'outbound','agent',$3,$4,'text','{}','queued')
        returning *
        """,
        tenant_id,
        conversation_id,
        request.state.actor_id,
        body_text,
    )
    idempotency_key = f'payment-link-{appointment_id}-{message["id"]}'
    await conn.execute(
        "insert into app.domain_events (tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload) values ($1,'message',$2,'message.queued',$3,$4::jsonb) on conflict do nothing",
        tenant_id,
        message['id'],
        idempotency_key,
        json.dumps({
            'conversation_id': str(conversation_id),
            'appointment_id': str(appointment_id),
            'payment_link': appointment['payment_link'],
        }),
    )
    row = await conn.fetchrow(
        """
        update app.appointments
        set payment_status=case when payment_status in ('paid','refunded') then payment_status else 'link_sent' end,
            payment_link_sent_at=now()
        where tenant_id=$1 and id=$2
        returning *
        """,
        tenant_id,
        appointment_id,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='appointment.payment_link_sent',
        entity_type='appointment',
        entity_id=str(appointment_id),
        metadata={'message_id': str(message['id'])},
    )
    await notify_operations_change(
        conn,
        tenant_id,
        'conversation.changed',
        conversation_id=conversation_id,
        message_id=message['id'],
    )
    summary = _appointment_payment_summary(row)
    summary['message_id'] = str(message['id'])
    return summary


@tenant_ops_router.patch('/appointments/{appointment_id}/payment-status')
async def patch_appointment_payment_status(
    appointment_id: UUID,
    payload: AppointmentPaymentStatusUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    existing = await conn.fetchrow(
        'select id from app.appointments where tenant_id=$1 and id=$2',
        tenant_id,
        appointment_id,
    )
    if not existing:
        raise HTTPException(status_code=404, detail='Appointment not found')
    row = await conn.fetchrow(
        """
        update app.appointments
        set payment_status=$3,
            payment_amount=coalesce($4, payment_amount),
            payment_currency=coalesce($5, payment_currency),
            payment_paid_at=case when $3='paid' then now() else payment_paid_at end
        where tenant_id=$1 and id=$2
        returning *
        """,
        tenant_id,
        appointment_id,
        payload.payment_status,
        payload.payment_amount,
        payload.payment_currency.upper() if payload.payment_currency else None,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='appointment.payment_status_updated',
        entity_type='appointment',
        entity_id=str(appointment_id),
        metadata={'payment_status': payload.payment_status},
    )
    return _appointment_payment_summary(row)


@tenant_ops_router.get('/tenants/{tenant_id}/outbound/dlq')
async def list_outbound_dlq(
    tenant_id: UUID,
    request: Request,
    since: datetime | None = Query(default=None),
    until: datetime | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    error_code: str | None = Query(default=None),
    conn: asyncpg.Connection = Depends(get_db),
):
    from app.services.outbound_dlq import list_dlq

    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    return await list_dlq(
        conn,
        tenant_id=tenant_id,
        since=since,
        until=until,
        limit=limit,
        error_code=error_code,
    )


@tenant_ops_router.post('/tenants/{tenant_id}/outbound/dlq/{message_id}/retry')
async def retry_outbound_dlq_message(
    tenant_id: UUID,
    message_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    from app.services.outbound_dlq import requeue_message

    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    result = await requeue_message(
        conn,
        tenant_id=tenant_id,
        message_id=message_id,
        requested_by=getattr(request.state, 'actor_id', None),
    )
    if result.get('reason') == 'not_found':
        raise HTTPException(status_code=404, detail='Outbound message not found in this tenant')
    if not result.get('requeued'):
        raise HTTPException(status_code=409, detail=result.get('reason') or 'cannot_requeue')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='outbound.dlq.retried',
        entity_type='message',
        entity_id=str(message_id),
    )
    return result

