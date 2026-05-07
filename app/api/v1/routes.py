import hashlib
import json
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status

from app.api.v1.schemas import (
    AppointmentCreate,
    ChannelCreate,
    ContactUpsert,
    ConversationCreate,
    KnowledgeDocumentCreate,
    KnowledgeDocumentUpdate,
    MessageCreate,
    PromptCreate,
    ServiceRequestCreate,
    TenantCreate,
    TenantUpdate,
)
from app.core.config import get_settings
from app.core.security import authenticate_request, require_min_role, require_platform_owner, require_service
from app.db.pool import get_db, record_to_dict
from app.services.audit import audit
from app.services.rag_indexing import build_indexing_result, vector_literal
from app.services.whatsapp import verify_signature

router = APIRouter(prefix='/v1')
public_router = APIRouter(tags=['public'])
webhook_router = APIRouter(prefix='/webhooks', tags=['public-webhooks'])
platform_admin_router = APIRouter(
    tags=['platform-admin'],
    dependencies=[Depends(authenticate_request), Depends(require_platform_owner)],
)
tenant_admin_router = APIRouter(
    tags=['tenant-admin'],
    dependencies=[Depends(authenticate_request), Depends(require_min_role('admin'))],
)
tenant_ops_router = APIRouter(
    tags=['tenant-operations'],
    dependencies=[Depends(authenticate_request), Depends(require_min_role('agent', allow_service=True))],
)
tenant_signup_router = APIRouter(
    tags=['tenant-signup'],
    dependencies=[Depends(authenticate_request), Depends(require_min_role('admin'))],
)
system_router = APIRouter(
    tags=['system'],
    dependencies=[Depends(authenticate_request), Depends(require_service)],
)


KNOWLEDGE_DOCUMENT_RESPONSE_COLUMNS = (
    'id',
    'tenant_id',
    'source_type',
    'document_type',
    'title',
    'source_uri',
    'checksum',
    'mime_type',
    'content',
    'visibility',
    'status',
    'uploaded_by_user_id',
    'metadata',
    'created_at',
    'updated_at',
)
KNOWLEDGE_DOCUMENT_WRITABLE_COLUMNS = (
    'source_type',
    'document_type',
    'title',
    'source_uri',
    'checksum',
    'mime_type',
    'content',
    'visibility',
    'status',
    'metadata',
)
KNOWLEDGE_DOCUMENT_COMPAT_DEFAULTS = {
    'document_type': 'reference',
    'content': None,
    'metadata': {},
}


async def knowledge_document_columns(conn: asyncpg.Connection) -> set[str]:
    rows = await conn.fetch(
        """
        select column_name
        from information_schema.columns
        where table_schema='app' and table_name='knowledge_documents'
        """
    )
    return {row['column_name'] for row in rows}


def knowledge_document_projection(columns: set[str]) -> str:
    projection = []
    for column in KNOWLEDGE_DOCUMENT_RESPONSE_COLUMNS:
        if column in columns:
            projection.append(column)
        elif column == 'metadata':
            projection.append("'{}'::jsonb as metadata")
        elif column in KNOWLEDGE_DOCUMENT_COMPAT_DEFAULTS:
            projection.append(f"null::text as {column}")
    return ', '.join(projection)


def normalize_knowledge_document(row: asyncpg.Record | None) -> dict | None:
    document = record_to_dict(row)
    if not document:
        return None
    for column, default in KNOWLEDGE_DOCUMENT_COMPAT_DEFAULTS.items():
        if document.get(column) is None:
            document[column] = default
    return document


def normalize_knowledge_documents(rows: list[asyncpg.Record]) -> list[dict]:
    return [normalize_knowledge_document(row) for row in rows]


def is_service_or_support(request: Request) -> bool:
    return getattr(request.state, 'actor_type', None) == 'service' or getattr(
        request.state, 'support_mode', False
    )


async def has_user_tenant_role(conn: asyncpg.Connection, request: Request, tenant_id: UUID) -> bool:
    actor_id = getattr(request.state, 'actor_id', None)
    if not actor_id:
        return False
    return bool(
        await conn.fetchval(
            """
            select exists(
              select 1
              from app.users u
              join app.user_tenant_roles utr on utr.user_id = u.id
              where u.auth_subject=$1 and utr.tenant_id=$2
            )
            """,
            actor_id,
            tenant_id,
        )
    )


async def ensure_tenant_access(
    request: Request, tenant_id: UUID, conn: asyncpg.Connection | None = None
) -> None:
    if is_service_or_support(request):
        return
    request_tenant_id = getattr(request.state, 'tenant_id', None)
    if request_tenant_id == tenant_id:
        return
    if conn and await has_user_tenant_role(conn, request, tenant_id):
        return
    if not request_tenant_id:
        raise HTTPException(
            status_code=400, detail='X-Tenant-Id header or tenant_id claim is required'
        )
    raise HTTPException(status_code=403, detail='Tenant scope does not match request')


async def require_tenant(request: Request) -> UUID:
    if not getattr(request.state, 'tenant_id', None):
        raise HTTPException(status_code=400, detail='X-Tenant-Id header or tenant_id claim is required')
    return request.state.tenant_id


async def tenant_id_from_request(request: Request, conn: asyncpg.Connection) -> UUID:
    tenant_id = getattr(request.state, 'tenant_id', None) or getattr(
        request.state, 'requested_tenant_id', None
    )
    if not tenant_id:
        raise HTTPException(status_code=400, detail='X-Tenant-Id header or tenant_id claim is required')
    await ensure_tenant_access(request, tenant_id, conn)
    return tenant_id


@public_router.get('/health')
async def health(conn: asyncpg.Connection = Depends(get_db)) -> dict:
    await conn.fetchval('select 1')
    return {'status': 'ok'}


def user_email_from_request(request: Request) -> str:
    email = getattr(request.state, 'email', None) or request.headers.get('X-Admin-User-Email')
    if email:
        return email
    actor_id = getattr(request.state, 'actor_id', 'unknown-user')
    stable_id = uuid5(NAMESPACE_URL, actor_id).hex
    return f'{stable_id}@auth.local'


def user_display_name_from_request(request: Request) -> str:
    return (
        getattr(request.state, 'name', None)
        or request.headers.get('X-Admin-User-Name')
        or request.headers.get('X-Admin-User-Email')
        or getattr(request.state, 'actor_id', None)
        or 'Tenant admin'
    )


@platform_admin_router.post('/tenants', status_code=status.HTTP_201_CREATED)
async def create_tenant(payload: TenantCreate, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    row = await conn.fetchrow(
        """
        insert into app.tenants (slug, legal_name, display_name, vertical_code, country_code, timezone)
        values ($1, $2, $3, $4, $5, $6)
        returning *
        """,
        payload.slug,
        payload.legal_name,
        payload.display_name,
        payload.vertical_code,
        payload.country_code,
        payload.timezone,
    )
    tenant_id = row['id']
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    await conn.execute('insert into app.tenant_settings (tenant_id) values ($1)', tenant_id)
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='tenant.created', entity_type='tenant', entity_id=str(tenant_id))
    return record_to_dict(row)


async def update_tenant_record(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    payload: TenantUpdate,
) -> asyncpg.Record:
    allowed = payload.model_dump(exclude_unset=True, exclude_none=True)
    current = await conn.fetchrow('select * from app.tenants where id=$1 and deleted_at is null', tenant_id)
    if not current:
        raise HTTPException(status_code=404, detail='Tenant not found')
    merged = dict(current)
    merged.update(allowed)
    row = await conn.fetchrow(
        """
        update app.tenants
        set slug=$2,
            legal_name=$3,
            display_name=$4,
            vertical_code=$5,
            country_code=$6,
            timezone=$7,
            updated_at=now()
        where id=$1 and deleted_at is null
        returning *
        """,
        tenant_id,
        merged['slug'],
        merged['legal_name'],
        merged['display_name'],
        merged['vertical_code'],
        merged['country_code'],
        merged['timezone'],
    )
    if not row:
        raise HTTPException(status_code=404, detail='Tenant not found')
    return row


@tenant_signup_router.get('/me/tenants')
async def list_my_tenants(request: Request, conn: asyncpg.Connection = Depends(get_db)):
    actor_id = getattr(request.state, 'actor_id', None)
    if not actor_id:
        raise HTTPException(status_code=401, detail='Authentication required')
    rows = await conn.fetch(
        """
        select t.id, t.slug, t.legal_name, t.display_name, t.vertical_code, t.country_code, t.timezone, t.status, utr.role, utr.is_default
        from app.users u
        join app.user_tenant_roles utr on utr.user_id = u.id
        join app.tenants t on t.id = utr.tenant_id
        where u.auth_subject=$1 and t.deleted_at is null
        order by utr.is_default desc, utr.created_at asc
        """,
        actor_id,
    )
    return [record_to_dict(row) for row in rows]


@tenant_signup_router.post('/tenant-signup', status_code=status.HTTP_201_CREATED)
async def create_own_tenant(
    payload: TenantCreate, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    actor_id = getattr(request.state, 'actor_id', None)
    if not actor_id:
        raise HTTPException(status_code=401, detail='Authentication required')
    existing_tenant_id = await conn.fetchval(
        """
        select utr.tenant_id
        from app.users u
        join app.user_tenant_roles utr on utr.user_id = u.id
        where u.auth_subject=$1
        order by utr.created_at asc
        limit 1
        """,
        actor_id,
    )
    if existing_tenant_id:
        row = await update_tenant_record(conn, existing_tenant_id, TenantUpdate(**payload.model_dump()))
        await audit(
            conn,
            tenant_id=existing_tenant_id,
            actor_type=request.state.actor_type,
            actor_id=request.state.actor_id,
            action='tenant.self_service_updated',
            entity_type='tenant',
            entity_id=str(existing_tenant_id),
        )
        response = record_to_dict(row)
        response['user_role'] = 'owner'
        return response

    row = await conn.fetchrow(
        """
        insert into app.tenants (slug, legal_name, display_name, vertical_code, country_code, timezone)
        values ($1, $2, $3, $4, $5, $6)
        returning *
        """,
        payload.slug,
        payload.legal_name,
        payload.display_name,
        payload.vertical_code,
        payload.country_code,
        payload.timezone,
    )
    tenant_id = row['id']
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    await conn.execute('insert into app.tenant_settings (tenant_id) values ($1)', tenant_id)
    user_row = await conn.fetchrow(
        """
        insert into app.users (auth_subject, email, display_name, last_login_at)
        values ($1, $2, $3, now())
        on conflict (auth_subject) do update set
          email=excluded.email,
          display_name=excluded.display_name,
          last_login_at=now(),
          updated_at=now()
        returning id
        """,
        actor_id,
        user_email_from_request(request),
        user_display_name_from_request(request),
    )
    await conn.execute(
        """
        insert into app.user_tenant_roles (user_id, tenant_id, role, is_default)
        values ($1, $2, 'owner', true)
        on conflict (user_id, tenant_id, role) do update set is_default=true
        """,
        user_row['id'],
        tenant_id,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant.self_service_created',
        entity_type='tenant',
        entity_id=str(tenant_id),
    )
    response = record_to_dict(row)
    response['user_role'] = 'owner'
    return response


@tenant_ops_router.get('/tenants/{tenant_id}')
async def get_tenant(tenant_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    await ensure_tenant_access(request, tenant_id, conn)
    row = await conn.fetchrow('select * from app.tenants where id=$1 and deleted_at is null', tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail='Tenant not found')
    return record_to_dict(row)


@tenant_admin_router.patch('/tenants/{tenant_id}')
async def patch_tenant(
    tenant_id: UUID,
    payload: TenantUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await update_tenant_record(conn, tenant_id, payload)
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant.updated',
        entity_type='tenant',
        entity_id=str(tenant_id),
    )
    return record_to_dict(row)


@tenant_admin_router.get('/tenants/{tenant_id}/settings')
async def get_tenant_settings(
    tenant_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow('select * from app.tenant_settings where tenant_id=$1', tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail='Settings not found')
    return record_to_dict(row)


@tenant_admin_router.patch('/tenants/{tenant_id}/settings')
async def patch_settings(tenant_id: UUID, payload: dict, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    allowed = {k: payload[k] for k in ('locale', 'business_hours', 'escalation_policy', 'pii_policy', 'no_train', 'max_bot_turns') if k in payload}
    current = await conn.fetchrow('select * from app.tenant_settings where tenant_id=$1', tenant_id)
    if not current:
        raise HTTPException(status_code=404, detail='Settings not found')
    merged = dict(current)
    merged.update(allowed)
    row = await conn.fetchrow(
        """
        update app.tenant_settings
        set locale=$2, business_hours=$3::jsonb, escalation_policy=$4::jsonb, pii_policy=$5::jsonb,
            no_train=$6, max_bot_turns=$7
        where tenant_id=$1 returning *
        """,
        tenant_id,
        merged['locale'],
        json.dumps(merged['business_hours']),
        json.dumps(merged['escalation_policy']),
        json.dumps(merged['pii_policy']),
        merged['no_train'],
        merged['max_bot_turns'],
    )
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='tenant_settings.updated', entity_type='tenant_settings', entity_id=str(tenant_id))
    return record_to_dict(row)


@tenant_admin_router.post('/tenants/{tenant_id}/channels/whatsapp', status_code=201)
async def create_channel(tenant_id: UUID, payload: ChannelCreate, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow(
        """
        insert into app.tenant_channels (tenant_id, provider, business_id, waba_id, phone_number_id, token_ref, app_secret_ref, status)
        values ($1, 'whatsapp_cloud_api', $2, $3, $4, $5, $6, 'active')
        on conflict (tenant_id, provider) do update set
          business_id=excluded.business_id, waba_id=excluded.waba_id, phone_number_id=excluded.phone_number_id,
          token_ref=excluded.token_ref, app_secret_ref=excluded.app_secret_ref, status='active'
        returning *
        """,
        tenant_id,
        payload.business_id,
        payload.waba_id,
        payload.phone_number_id,
        payload.token_ref,
        payload.app_secret_ref,
    )
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='channel.upserted', entity_type='tenant_channel', entity_id=str(row['id']))
    return record_to_dict(row)


@tenant_admin_router.get('/tenants/{tenant_id}/channels/whatsapp/health')
async def channel_health(tenant_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow(
        """
        select id, tenant_id, provider, business_id, waba_id, phone_number_id, token_ref,
               app_secret_ref, quality_rating, messaging_limit_tier, account_mode, status,
               created_at, updated_at
        from app.tenant_channels
        where tenant_id=$1 and provider='whatsapp_cloud_api'
        """,
        tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='WhatsApp channel not found')

    channel = record_to_dict(row)
    checks = {
        'business_id': bool(channel.get('business_id')),
        'waba_id': bool(channel.get('waba_id')),
        'phone_number_id': bool(channel.get('phone_number_id')),
        'token_ref': bool(channel.get('token_ref')),
        'app_secret_ref': bool(channel.get('app_secret_ref')),
        'channel_active': channel.get('status') == 'active',
    }
    health_status = 'healthy' if all(checks.values()) else 'degraded'
    return {
        'status': health_status,
        'channel': channel,
        'checks': checks,
        'upstream': 'not_checked_in_local_core',
    }


@system_router.post('/contacts/upsert')
async def upsert_contact(payload: ContactUpsert, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    await ensure_tenant_access(request, payload.tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(payload.tenant_id))
    phone_hash = hashlib.sha256(payload.phone_e164.encode()).digest()
    row = await conn.fetchrow(
        """
        insert into app.contacts (tenant_id, wa_id, phone_e164, phone_hash, display_name, opt_in_status, metadata)
        values ($1, $2, $3, $4, $5, $6, $7::jsonb)
        on conflict (tenant_id, wa_id) do update set
          phone_e164=excluded.phone_e164, phone_hash=excluded.phone_hash, display_name=excluded.display_name,
          opt_in_status=excluded.opt_in_status, metadata=app.contacts.metadata || excluded.metadata
        returning *
        """,
        payload.tenant_id,
        payload.wa_id,
        payload.phone_e164,
        phone_hash,
        payload.display_name,
        payload.opt_in_status,
        json.dumps(payload.metadata),
    )
    await audit(conn, tenant_id=payload.tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='contact.upserted', entity_type='contact', entity_id=str(row['id']))
    return record_to_dict(row)


@tenant_ops_router.get('/contacts/{contact_id}')
async def get_contact(
    contact_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    tenant_id = await tenant_id_from_request(request, conn)
    row = await conn.fetchrow('select * from app.contacts where tenant_id=$1 and id=$2', tenant_id, contact_id)
    if not row:
        raise HTTPException(status_code=404, detail='Contact not found')
    return record_to_dict(row)


@system_router.post('/conversations', status_code=201)
async def create_conversation(payload: ConversationCreate, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    await ensure_tenant_access(request, payload.tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(payload.tenant_id))
    row = await conn.fetchrow(
        """
        insert into app.conversations (tenant_id, contact_id, channel_id, opened_by, current_intent)
        values ($1, $2, $3, $4, $5) returning *
        """,
        payload.tenant_id,
        payload.contact_id,
        payload.channel_id,
        payload.opened_by,
        payload.current_intent,
    )
    return record_to_dict(row)


@tenant_ops_router.get('/conversations')
async def list_conversations(request: Request, conn: asyncpg.Connection = Depends(get_db)):
    tenant_id = await tenant_id_from_request(request, conn)
    rows = await conn.fetch('select * from app.conversations where tenant_id=$1 order by updated_at desc limit 100', tenant_id)
    return [dict(r) for r in rows]


@tenant_ops_router.get('/conversations/{conversation_id}')
async def get_conversation(
    conversation_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    tenant_id = await tenant_id_from_request(request, conn)
    row = await conn.fetchrow('select * from app.conversations where tenant_id=$1 and id=$2', tenant_id, conversation_id)
    if not row:
        raise HTTPException(status_code=404, detail='Conversation not found')
    messages = await conn.fetch('select * from app.messages where tenant_id=$1 and conversation_id=$2 order by created_at', tenant_id, conversation_id)
    data = dict(row)
    data['messages'] = [dict(m) for m in messages]
    return data


@tenant_ops_router.post('/conversations/{conversation_id}/messages', status_code=202)
async def create_message(conversation_id: UUID, payload: MessageCreate, request: Request, conn: asyncpg.Connection = Depends(get_db), idempotency_key: str | None = Header(default=None, alias='Idempotency-Key')):
    await ensure_tenant_access(request, payload.tenant_id, conn)

    await conn.execute("select set_config('app.tenant_id', $1, true)", str(payload.tenant_id))
    conversation = await conn.fetchrow(
        'select id from app.conversations where tenant_id=$1 and id=$2',
        payload.tenant_id,
        conversation_id,
    )
    if not conversation:
        raise HTTPException(status_code=404, detail='Conversation not found for tenant')

    row = await conn.fetchrow(
        """
        insert into app.messages (tenant_id, conversation_id, direction, sender_actor_type, body_text, message_type, payload, status)
        values ($1, $2, $3, $4, $5, $6, $7::jsonb, 'queued') returning *
        """,
        payload.tenant_id,
        conversation_id,
        payload.direction,
        payload.sender_actor_type,
        payload.body_text,
        payload.message_type,
        json.dumps(payload.payload),
    )
    key = idempotency_key or str(row['id'])
    await conn.execute(
        "insert into app.domain_events (tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload) values ($1,'message',$2,'message.queued',$3,$4::jsonb) on conflict do nothing",
        payload.tenant_id,
        row['id'],
        key,
        json.dumps({'conversation_id': str(conversation_id)}),
    )
    await audit(conn, tenant_id=payload.tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='message.queued', entity_type='message', entity_id=str(row['id']))
    return record_to_dict(row)


@tenant_ops_router.post('/conversations/{conversation_id}/handoff', status_code=202)
async def create_handoff(
    conversation_id: UUID,
    request: Request,
    payload: dict,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    row = await conn.fetchrow(
        """
        insert into app.handoffs (tenant_id, conversation_id, reason, assigned_to)
        values ($1, $2, $3, null) returning *
        """,
        tenant_id,
        conversation_id,
        payload.get('reason', 'manual_or_policy_handoff'),
    )
    await conn.execute("update app.conversations set status='human_required', handoff_required=true where tenant_id=$1 and id=$2", tenant_id, conversation_id)
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='handoff.created', entity_type='handoff', entity_id=str(row['id']))
    return record_to_dict(row)


@tenant_ops_router.post('/conversations/{conversation_id}/release', status_code=202)
async def release_conversation(
    conversation_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    tenant_id = await tenant_id_from_request(request, conn)
    row = await conn.fetchrow("update app.conversations set status='open', handoff_required=false where tenant_id=$1 and id=$2 returning *", tenant_id, conversation_id)
    if not row:
        raise HTTPException(status_code=404, detail='Conversation not found')
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='conversation.released', entity_type='conversation', entity_id=str(conversation_id))
    return record_to_dict(row)


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


@tenant_ops_router.patch('/service-requests/{request_id}')
async def patch_service_request(
    request_id: UUID,
    payload: dict,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    row = await conn.fetchrow("update app.service_requests set status=coalesce($3,status), intake=intake || $4::jsonb where tenant_id=$1 and id=$2 returning *", tenant_id, request_id, payload.get('status'), json.dumps(payload.get('intake', {})))
    if not row:
        raise HTTPException(status_code=404, detail='Service request not found')
    return record_to_dict(row)


@tenant_ops_router.post('/appointments', status_code=201)
async def create_appointment(payload: AppointmentCreate, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    await ensure_tenant_access(request, payload.tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(payload.tenant_id))
    row = await conn.fetchrow(
        """
        insert into app.appointments (tenant_id, contact_id, conversation_id, service_request_id, resource_id, service_code, starts_at, ends_at, notes)
        values ($1,$2,$3,$4,$5,$6,$7,$8,$9) returning *
        """,
        payload.tenant_id, payload.contact_id, payload.conversation_id, payload.service_request_id, payload.resource_id, payload.service_code, payload.starts_at, payload.ends_at, payload.notes,
    )
    return record_to_dict(row)


@tenant_admin_router.get('/knowledge/documents')
async def list_knowledge_documents(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    status_filter: str | None = Query(default=None, alias='status'),
    visibility: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
):
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    columns = await knowledge_document_columns(conn)
    rows = await conn.fetch(
        f"""
        select {knowledge_document_projection(columns)}
        from app.knowledge_documents
        where tenant_id=$1
          and ($2::text is null or status=$2)
          and ($3::text is null or visibility=$3)
          and ($4::text is null or source_type=$4)
        order by updated_at desc, created_at desc
        limit 250
        """,
        tenant_id,
        status_filter,
        visibility,
        source_type,
    )
    return normalize_knowledge_documents(rows)


@tenant_admin_router.post('/knowledge/documents', status_code=201)
async def create_knowledge_document(
    payload: KnowledgeDocumentCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, payload.tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(payload.tenant_id))
    if payload.status == 'active':
        raise HTTPException(status_code=400, detail='Use the indexing endpoint to activate documents')
    columns = await knowledge_document_columns(conn)
    payload_values = payload.model_dump()
    insert_columns = ['tenant_id'] + [
        column for column in KNOWLEDGE_DOCUMENT_WRITABLE_COLUMNS if column in columns
    ]
    values = []
    for column in insert_columns:
        if column == 'tenant_id':
            values.append(payload.tenant_id)
        elif column == 'metadata':
            values.append(json.dumps(payload_values[column]))
        else:
            values.append(payload_values[column])

    placeholders = [
        f'${index}::jsonb' if column == 'metadata' else f'${index}'
        for index, column in enumerate(insert_columns, start=1)
    ]
    row = await conn.fetchrow(
        f"""
        insert into app.knowledge_documents ({', '.join(insert_columns)})
        values ({', '.join(placeholders)})
        returning {knowledge_document_projection(columns)}
        """,
        *values,
    )
    await audit(
        conn,
        tenant_id=payload.tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='knowledge_document.created',
        entity_type='knowledge_document',
        entity_id=str(row['id']),
    )
    return normalize_knowledge_document(row)


@tenant_admin_router.get('/knowledge/documents/{document_id}')
async def get_knowledge_document(
    document_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    columns = await knowledge_document_columns(conn)
    row = await conn.fetchrow(
        f"""
        select {knowledge_document_projection(columns)}
        from app.knowledge_documents
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        document_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Knowledge document not found')
    return normalize_knowledge_document(row)


@tenant_admin_router.patch('/knowledge/documents/{document_id}')
async def patch_knowledge_document(
    document_id: UUID,
    payload: KnowledgeDocumentUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    columns = await knowledge_document_columns(conn)
    current = await conn.fetchrow(
        f"""
        select {knowledge_document_projection(columns)}
        from app.knowledge_documents
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        document_id,
    )
    if not current:
        raise HTTPException(status_code=404, detail='Knowledge document not found')

    allowed = {
        column: value
        for column, value in payload.model_dump(exclude_unset=True).items()
        if column in columns and column in KNOWLEDGE_DOCUMENT_WRITABLE_COLUMNS
    }
    if not allowed:
        return normalize_knowledge_document(current)
    if allowed.get('status') == 'active':
        has_chunks = await conn.fetchval(
            'select exists(select 1 from app.knowledge_chunks where tenant_id=$1 and document_id=$2)',
            tenant_id,
            document_id,
        )
        if not has_chunks:
            raise HTTPException(status_code=400, detail='Use the indexing endpoint to activate documents')

    assignments = []
    values = [tenant_id, document_id]
    for column, value in allowed.items():
        values.append(json.dumps(value) if column == 'metadata' else value)
        placeholder = f'${len(values)}::jsonb' if column == 'metadata' else f'${len(values)}'
        assignments.append(f'{column}={placeholder}')

    row = await conn.fetchrow(
        f"""
        update app.knowledge_documents
        set {', '.join(assignments)}
        where tenant_id=$1 and id=$2
        returning {knowledge_document_projection(columns)}
        """,
        *values,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='knowledge_document.updated',
        entity_type='knowledge_document',
        entity_id=str(document_id),
    )
    return normalize_knowledge_document(row)



@tenant_admin_router.post('/knowledge/documents/{document_id}/index')
async def index_knowledge_document(
    document_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    columns = await knowledge_document_columns(conn)
    document = await conn.fetchrow(
        f"""
        select {knowledge_document_projection(columns)}
        from app.knowledge_documents
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        document_id,
    )
    if not document:
        raise HTTPException(status_code=404, detail='Knowledge document not found')

    settings = get_settings()
    try:
        result = build_indexing_result(
            normalize_knowledge_document(document),
            max_tokens=settings.rag_chunk_max_tokens,
            overlap_tokens=settings.rag_chunk_overlap_tokens,
            embedding_dimensions=settings.rag_embedding_dimensions,
            embedding_provider=settings.rag_embedding_provider,
            embedding_model=settings.rag_embedding_model,
        )
    except ValueError as exc:
        await conn.execute(
            """
            update app.knowledge_documents
            set status='failed', metadata=metadata || $3::jsonb
            where tenant_id=$1 and id=$2
            """,
            tenant_id,
            document_id,
            json.dumps({'indexing_error': str(exc)}),
        )
        await audit(
            conn,
            tenant_id=tenant_id,
            actor_type=request.state.actor_type,
            actor_id=request.state.actor_id,
            action='knowledge_document.index_failed',
            entity_type='knowledge_document',
            entity_id=str(document_id),
            metadata={'error': str(exc)},
        )
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    indexing_started_at = datetime.now(UTC).isoformat()
    async with conn.transaction():
        await conn.execute(
            """
            update app.knowledge_documents
            set status='indexing', metadata=metadata || $3::jsonb
            where tenant_id=$1 and id=$2
            """,
            tenant_id,
            document_id,
            json.dumps(
                {
                    'last_indexing_started_at': indexing_started_at,
                    'embedding_provider': result.embedding_provider,
                    'embedding_model': result.embedding_model,
                    'embedding_dimensions': result.embedding_dimensions,
                }
            ),
        )
        await conn.execute(
            'delete from app.knowledge_chunks where tenant_id=$1 and document_id=$2',
            tenant_id,
            document_id,
        )
        for chunk in result.chunks:
            await conn.execute(
                """
                insert into app.knowledge_chunks (
                  tenant_id, document_id, chunk_index, section_path, chunk_text,
                  token_count, embedding, metadata
                )
                values ($1,$2,$3,$4,$5,$6,$7::vector,$8::jsonb)
                """,
                tenant_id,
                document_id,
                chunk.chunk_index,
                chunk.section_path,
                chunk.chunk_text,
                chunk.token_count,
                vector_literal(chunk.embedding),
                json.dumps(chunk.metadata),
            )
        indexing_completed_at = datetime.now(UTC).isoformat()
        row = await conn.fetchrow(
            f"""
            update app.knowledge_documents
            set status='active', metadata=metadata || $3::jsonb
            where tenant_id=$1 and id=$2
            returning {knowledge_document_projection(columns)}
            """,
            tenant_id,
            document_id,
            json.dumps(
                {
                    'chunk_count': len(result.chunks),
                    'sanitized_warning_count': result.sanitized_warning_count,
                    'last_indexing_completed_at': indexing_completed_at,
                }
            ),
        )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='knowledge_document.indexed',
        entity_type='knowledge_document',
        entity_id=str(document_id),
        metadata={
            'chunk_count': len(result.chunks),
            'sanitized_warning_count': result.sanitized_warning_count,
            'embedding_provider': result.embedding_provider,
            'embedding_model': result.embedding_model,
        },
    )
    response = normalize_knowledge_document(row)
    response['indexing'] = {
        'chunk_count': len(result.chunks),
        'sanitized_warning_count': result.sanitized_warning_count,
        'embedding_provider': result.embedding_provider,
        'embedding_model': result.embedding_model,
        'embedding_dimensions': result.embedding_dimensions,
    }
    return response


@tenant_admin_router.delete('/knowledge/documents/{document_id}', status_code=204)
async def delete_knowledge_document(
    document_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    result = await conn.execute(
        'delete from app.knowledge_documents where tenant_id=$1 and id=$2', tenant_id, document_id
    )
    if result == 'DELETE 0':
        raise HTTPException(status_code=404, detail='Knowledge document not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='knowledge_document.deleted',
        entity_type='knowledge_document',
        entity_id=str(document_id),
    )
    return Response(status_code=204)


@tenant_admin_router.post('/prompts', status_code=201)
async def create_prompt(payload: PromptCreate, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    if payload.tenant_id:
        await ensure_tenant_access(request, payload.tenant_id, conn)
    row = await conn.fetchrow("insert into app.prompt_templates (tenant_id, vertical_code, prompt_type, name, version, content, variables, checksum) values ($1,$2,$3,$4,$5,$6,$7::jsonb, encode(sha256($6::bytea),'hex')) returning *", payload.tenant_id, payload.vertical_code, payload.prompt_type, payload.name, payload.version, payload.content, json.dumps(payload.variables))
    return record_to_dict(row)


@tenant_admin_router.get('/audit-logs')
async def list_audit_logs(request: Request, conn: asyncpg.Connection = Depends(get_db)):
    tenant_id = await tenant_id_from_request(request, conn)
    rows = await conn.fetch('select * from app.audit_logs where tenant_id=$1 order by created_at desc limit 100', tenant_id)
    return [dict(r) for r in rows]


@webhook_router.get('/whatsapp')
async def verify_whatsapp_webhook(
    hub_mode: str | None = Query(default=None, alias='hub.mode'),
    hub_verify_token: str | None = Query(default=None, alias='hub.verify_token'),
    hub_challenge: str | None = Query(default=None, alias='hub.challenge'),
):
    settings = get_settings()
    if hub_mode == 'subscribe' and hub_verify_token == settings.whatsapp_verify_token:
        return Response(content=hub_challenge or '', media_type='text/plain')
    raise HTTPException(status_code=403, detail='Invalid verify token')


@webhook_router.post('/whatsapp', status_code=202)
async def receive_whatsapp_webhook(request: Request, conn: asyncpg.Connection = Depends(get_db), x_hub_signature_256: str | None = Header(default=None, alias='X-Hub-Signature-256')):
    body = await request.body()
    if not verify_signature(body, x_hub_signature_256):
        raise HTTPException(status_code=401, detail='Invalid webhook signature')
    payload = json.loads(body or b'{}')
    sha = hashlib.sha256(body).hexdigest()
    await conn.fetchrow(
        """
        insert into app.webhook_events_raw (provider, event_type, headers, payload, payload_sha256)
        values ('whatsapp_cloud_api', $1, $2::jsonb, $3::jsonb, $4)
        on conflict (payload_sha256) do nothing returning *
        """,
        payload.get('object', 'unknown'),
        json.dumps(dict(request.headers)),
        json.dumps(payload),
        sha,
    )
    return {'accepted': True, 'payload_sha256': sha}


router.include_router(public_router)
router.include_router(webhook_router)
router.include_router(platform_admin_router)
router.include_router(tenant_signup_router)
router.include_router(tenant_admin_router)
router.include_router(tenant_ops_router)
router.include_router(system_router)
