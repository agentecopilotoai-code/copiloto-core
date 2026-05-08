import asyncio
import hashlib
import hmac
import json
from pathlib import Path
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

import httpx
import asyncpg
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status

from app.api.v1.schemas import (
    AppointmentCreate,
    AppointmentUpdate,
    ChannelCreate,
    ContactUpsert,
    ConversationCreate,
    ConversationStart,
    IntentEvaluateRequest,
    KnowledgeDocumentCreate,
    KnowledgeDocumentUpdate,
    MessageCreate,
    PromptCreate,
    QuoteCreate,
    QuotePatch,
    ResourceCreate,
    ResourceUpdate,
    ServiceRequestCreate,
    ServiceRequestPatch,
    TenantCreate,
    TenantUpdate,
)
from app.core.config import get_settings
from app.core.security import authenticate_request, require_min_role, require_platform_owner, require_service
from app.db.pool import get_db, record_to_dict
from app.services.audit import audit
from app.services.rag_indexing import build_indexing_result, vector_literal
from app.services.rag_retrieval import build_grounded_answer, rank_chunks, retrieval_match_to_dict
from app.services.whatsapp import (
    download_whatsapp_media,
    normalize_meta_app_secret,
    resolve_secret_ref,
    secret_ref_is_configured,
    token_ref_is_configured,
    verify_signature_with_secret,
)

log = structlog.get_logger()


def tenant_secret_ref(tenant_id: UUID, secret_name: str) -> str:
    return f'secrets/tenants/{tenant_id}/{secret_name}'


def write_tenant_secret(secret_ref: str, value: str) -> None:
    relative_name = secret_ref.removeprefix('secrets/').strip('/')
    if not relative_name or '..' in Path(relative_name).parts:
        raise HTTPException(status_code=400, detail='Invalid tenant secret ref')
    path = Path('/app/.secrets') / relative_name
    if not path.parent.exists() and not Path('/app/.secrets').exists():
        path = Path.cwd() / '.secrets' / relative_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.strip(), encoding='utf-8')
    path.chmod(0o600)


def verify_token_hash(verify_token: str) -> bytes:
    return hashlib.sha256(verify_token.encode('utf-8')).digest()


def whatsapp_phone_number_id_from_payload(payload: dict[str, Any]) -> str | None:
    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            value = change.get('value', {})
            metadata = value.get('metadata', {})
            phone_number_id = metadata.get('phone_number_id')
            if phone_number_id:
                return str(phone_number_id)
    return None


async def notify_operations_change(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    event: str,
    *,
    conversation_id: UUID | str | None = None,
    message_id: UUID | str | None = None,
) -> None:
    payload = {
        'type': event,
        'tenant_id': str(tenant_id),
        'conversation_id': str(conversation_id) if conversation_id else None,
        'message_id': str(message_id) if message_id else None,
        'occurred_at': datetime.now(UTC).isoformat(),
    }
    await conn.execute("select pg_notify('tenant_operations_events', $1)", json.dumps(payload))




MEDIA_MESSAGE_TYPES = {'image', 'audio', 'video'}
SUPPORTED_AGENT_MESSAGE_TYPES = {'text', *MEDIA_MESSAGE_TYPES}


def media_url_from_payload(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get('media_url') or payload.get('link')
    return value.strip() if isinstance(value, str) and value.strip() else None


def validate_outbound_message_content(
    message_type: str,
    body_text: str | None,
    media_id: str | None = None,
    media_url: str | None = None,
) -> None:
    if message_type not in SUPPORTED_AGENT_MESSAGE_TYPES:
        raise HTTPException(status_code=400, detail='Only text, image, audio, and video outbound WhatsApp messages are supported')
    if message_type == 'text' and not (body_text or '').strip():
        raise HTTPException(status_code=400, detail='Text messages require body_text')
    if message_type in MEDIA_MESSAGE_TYPES and not ((media_id or '').strip() or (media_url or '').strip()):
        raise HTTPException(status_code=400, detail=f'{message_type} messages require media_id or payload.media_url')

async def upsert_whatsapp_contact(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    wa_id: str,
    phone_e164: str,
    phone_hash: bytes,
    display_name: str | None,
    metadata: dict[str, Any],
    source: str | None = 'whatsapp_cloud_api',
):
    existing = await conn.fetchrow(
        """
        select *
        from app.contacts
        where tenant_id=$1 and (wa_id=$2 or phone_e164=$3)
        order by case when wa_id=$2 then 0 else 1 end, updated_at desc
        limit 1
        """,
        tenant_id,
        wa_id,
        phone_e164,
    )
    if existing:
        return await conn.fetchrow(
            """
            update app.contacts
            set wa_id=$2,
                phone_e164=$3,
                phone_hash=$4,
                display_name=coalesce($5, display_name),
                source=coalesce($6, source),
                metadata=metadata || $7::jsonb,
                updated_at=now()
            where tenant_id=$1 and id=$8
            returning *
            """,
            tenant_id,
            wa_id,
            phone_e164,
            phone_hash,
            display_name,
            source,
            json.dumps(metadata),
            existing['id'],
        )
    return await conn.fetchrow(
        """
        insert into app.contacts (tenant_id, wa_id, phone_e164, phone_hash, display_name, source, metadata)
        values ($1, $2, $3, $4, $5, $6, $7::jsonb)
        returning *
        """,
        tenant_id,
        wa_id,
        phone_e164,
        phone_hash,
        display_name,
        source,
        json.dumps(metadata),
    )


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


def metadata_extracted_text(value: Any) -> str | None:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if not isinstance(value, dict):
        return None
    extracted_text = value.get('extracted_text')
    return extracted_text if isinstance(extracted_text, str) else None


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
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
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


async def current_user_id_from_request(request: Request, conn: asyncpg.Connection) -> UUID | None:
    actor_id = getattr(request.state, 'actor_id', None)
    if not actor_id or getattr(request.state, 'actor_type', None) != 'user':
        return None
    row = await conn.fetchrow(
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
    return row['id']


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

    token_ref = tenant_secret_ref(tenant_id, 'meta_access_token')
    app_secret_ref = tenant_secret_ref(tenant_id, 'whatsapp_app_secret')
    verify_token_ref = tenant_secret_ref(tenant_id, 'whatsapp_verify_token')

    if payload.meta_access_token:
        write_tenant_secret(token_ref, payload.meta_access_token)
    elif not token_ref_is_configured(token_ref):
        raise HTTPException(
            status_code=400,
            detail='Meta access token is required for this tenant secret',
        )

    if payload.app_secret:
        write_tenant_secret(app_secret_ref, normalize_meta_app_secret(payload.app_secret) or payload.app_secret)
    elif not secret_ref_is_configured(app_secret_ref):
        raise HTTPException(
            status_code=400,
            detail='WhatsApp app secret is required for this tenant secret',
        )

    if payload.verify_token:
        write_tenant_secret(verify_token_ref, payload.verify_token)
    elif not secret_ref_is_configured(verify_token_ref):
        raise HTTPException(
            status_code=400,
            detail='WhatsApp verify token is required for this tenant secret',
        )

    verify_token = resolve_secret_ref(verify_token_ref)

    row = await conn.fetchrow(
        """
        insert into app.tenant_channels (
          tenant_id, provider, business_id, waba_id, phone_number_id, token_ref, app_secret_ref,
          verify_token_hash, account_mode, status
        )
        values ($1, 'whatsapp_cloud_api', $2, $3, $4, $5, $6, $7, $8, 'active')
        on conflict (tenant_id, provider) do update set
          business_id=excluded.business_id, waba_id=excluded.waba_id, phone_number_id=excluded.phone_number_id,
          token_ref=excluded.token_ref, app_secret_ref=excluded.app_secret_ref,
          verify_token_hash=excluded.verify_token_hash,
          account_mode=excluded.account_mode, status='active'
        returning *
        """,
        tenant_id,
        payload.business_id,
        payload.waba_id,
        payload.phone_number_id,
        token_ref,
        app_secret_ref,
        verify_token_hash(verify_token) if verify_token else None,
        payload.account_mode,
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
               app_secret_ref, verify_token_hash, quality_rating, messaging_limit_tier, account_mode, status,
               created_at, updated_at
        from app.tenant_channels
        where tenant_id=$1 and provider='whatsapp_cloud_api'
        """,
        tenant_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='WhatsApp channel not found')

    channel = record_to_dict(row)
    delivery_mode = channel.get('account_mode') or 'mock'
    token_ready = token_ref_is_configured(channel.get('token_ref'))
    app_secret_ready = secret_ref_is_configured(channel.get('app_secret_ref'))
    verify_token_ready = secret_ref_is_configured(tenant_secret_ref(channel['tenant_id'], 'whatsapp_verify_token'))
    delivery_ready = delivery_mode != 'live' or token_ready
    checks = {
        'business_id': bool(channel.get('business_id')),
        'waba_id': bool(channel.get('waba_id')),
        'phone_number_id': bool(channel.get('phone_number_id')),
        'token_ref': bool(channel.get('token_ref')),
        'app_secret_ref': bool(channel.get('app_secret_ref')),
        'app_secret_configured': app_secret_ready,
        'verify_token_configured': verify_token_ready,
        'channel_active': channel.get('status') == 'active',
        'delivery_mode': delivery_mode,
        'meta_access_token_configured': token_ready,
        'delivery_ready': delivery_ready,
    }
    health_status = 'healthy' if all(
        value for key, value in checks.items() if key != 'delivery_mode'
    ) else 'degraded'
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
        order by c.updated_at desc
        limit 100
        """,
        tenant_id,
    )
    conversations = [record_to_dict(r) for r in rows]
    log.info(
        'operations.conversations.listed',
        tenant_id=str(tenant_id),
        count=len(conversations),
        conversation_ids=[str(item.get('id')) for item in conversations[:20]],
        actor_id=getattr(request.state, 'actor_id', None),
    )
    return conversations


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
        actor_id=request.state.actor_id,
    )

    phone_e164 = payload.phone_e164.strip()
    wa_id = (payload.wa_id or phone_e164).strip().lstrip('+')
    phone_hash = hashlib.sha256(phone_e164.encode()).digest()
    contact = await upsert_whatsapp_contact(
        conn,
        tenant_id=payload.tenant_id,
        wa_id=wa_id,
        phone_e164=phone_e164,
        phone_hash=phone_hash,
        display_name=payload.display_name,
        metadata=payload.metadata,
        source='operations_desk',
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
    row = None
    for attempt in range(5):
        row = await conn.fetchrow(
            """
            select c.*,
                   coalesce(ct.display_name, ct.phone_e164, ct.wa_id) as contact_label,
                   ct.phone_e164 as contact_phone
            from app.conversations c
            join app.contacts ct on ct.id = c.contact_id
            where c.tenant_id=$1 and c.id=$2
            """,
            tenant_id,
            conversation_id,
        )
        if row or attempt == 4:
            break
        await asyncio.sleep(0.1)
    if not row:
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
    payload: dict,
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
        payload.get('reason', 'manual_or_policy_handoff'),
    )
    await conn.execute("update app.conversations set status='human_required', handoff_required=true where tenant_id=$1 and id=$2", tenant_id, conversation_id)
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='handoff.created', entity_type='handoff', entity_id=str(row['id']))
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


@tenant_ops_router.get('/resources')
async def list_resources(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    resource_type: str | None = Query(default=None),
    is_active: bool | None = Query(default=None),
):
    tenant_id = await tenant_id_from_request(request, conn)
    rows = await conn.fetch(
        """
        select *
        from app.resources
        where tenant_id=$1
          and ($2::text is null or resource_type=$2)
          and ($3::boolean is null or is_active=$3)
        order by is_active desc, resource_type, name
        limit 250
        """,
        tenant_id,
        resource_type,
        is_active,
    )
    return [record_to_dict(row) for row in rows]


@tenant_ops_router.post('/resources', status_code=201)
async def create_resource(payload: ResourceCreate, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    await ensure_tenant_access(request, payload.tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(payload.tenant_id))
    try:
        row = await conn.fetchrow(
            """
            insert into app.resources (tenant_id, vertical_code, resource_type, code, name, capabilities, is_active)
            values ($1,$2,$3,$4,$5,$6::jsonb,$7)
            returning *
            """,
            payload.tenant_id,
            payload.vertical_code,
            payload.resource_type,
            payload.code,
            payload.name,
            json.dumps(payload.capabilities),
            payload.is_active,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail='Resource code already exists for tenant') from exc
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
    try:
        row = await conn.fetchrow(
            """
            update app.resources
            set vertical_code=coalesce($3, vertical_code),
                resource_type=coalesce($4, resource_type),
                code=coalesce($5, code),
                name=coalesce($6, name),
                capabilities=coalesce($7::jsonb, capabilities),
                is_active=coalesce($8, is_active)
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
            update_data.get('is_active'),
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail='Resource code already exists for tenant') from exc
    if not row:
        raise HTTPException(status_code=404, detail='Resource not found')
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='resource.updated', entity_type='resource', entity_id=str(resource_id))
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


def _compute_quote_subtotal(line_items: list) -> float:
    return sum(item['qty'] * item['unit_price'] for item in line_items)


def _build_quote_summary_text(sr: Any, quote: Any) -> str:
    items = quote['line_items'] if isinstance(quote['line_items'], list) else json.loads(quote['line_items'])
    lines = [f"- {it['description']}: {it['qty']} x {it['unit_price']:,.0f} = {it['qty'] * it['unit_price']:,.0f}" for it in items]
    items_block = '\n'.join(lines) if lines else '(sin ítems)'
    valid_str = ''
    if quote['valid_until']:
        valid_str = f"\nVálida hasta: {quote['valid_until'].strftime('%Y-%m-%d %H:%M')}"
    return (
        f"*Cotización orientativa*\n"
        f"Servicio: {sr['service_type']}\n\n"
        f"{items_block}\n\n"
        f"Subtotal: {quote['subtotal']:,.0f} {quote['currency']}\n"
        f"Descuento: {quote['discount_total']:,.0f}\n"
        f"Impuestos: {quote['tax_total']:,.0f}\n"
        f"*Total: {quote['grand_total']:,.0f} {quote['currency']}*"
        f"{valid_str}"
    )


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
):
    tenant_id = await tenant_id_from_request(request, conn)
    rows = await conn.fetch(
        """
        select a.*, r.name as resource_name, r.code as resource_code, c.display_name as contact_label, c.phone_e164
        from app.appointments a
        join app.resources r on r.id=a.resource_id and r.tenant_id=a.tenant_id
        join app.contacts c on c.id=a.contact_id and c.tenant_id=a.tenant_id
        where a.tenant_id=$1
          and ($2::uuid is null or a.resource_id=$2)
          and ($3::text is null or a.status=$3)
        order by a.starts_at desc
        limit 250
        """,
        tenant_id,
        resource_id,
        status_filter,
    )
    return [record_to_dict(row) for row in rows]


@tenant_ops_router.post('/appointments', status_code=201)
async def create_appointment(payload: AppointmentCreate, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    await ensure_tenant_access(request, payload.tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(payload.tenant_id))
    await ensure_resource_available(conn, tenant_id=payload.tenant_id, resource_id=payload.resource_id, starts_at=payload.starts_at, ends_at=payload.ends_at)
    try:
        row = await conn.fetchrow(
            """
            insert into app.appointments (tenant_id, contact_id, conversation_id, service_request_id, resource_id, service_code, starts_at, ends_at, notes)
            values ($1,$2,$3,$4,$5,$6,$7,$8,$9) returning *
            """,
            payload.tenant_id, payload.contact_id, payload.conversation_id, payload.service_request_id, payload.resource_id, payload.service_code, payload.starts_at, payload.ends_at, payload.notes,
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
    await audit(conn, tenant_id=payload.tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='appointment.created', entity_type='appointment', entity_id=str(row['id']))
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
                notes=coalesce($9, notes)
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
        )
    except asyncpg.ExclusionViolationError as exc:
        raise HTTPException(status_code=409, detail='Resource has a conflicting appointment') from exc
    action = 'appointment.cancelled' if next_status == 'cancelled' else 'appointment.updated'
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
        await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='appointment.cancelled', entity_type='appointment', entity_id=str(appointment_id))
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


@tenant_admin_router.post('/intents/evaluate')
async def evaluate_intent_retrieval(
    payload: IntentEvaluateRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        """
        select kc.id,
               kc.document_id,
               kd.title as document_title,
               kd.source_uri,
               kd.source_type,
               kd.document_type,
               kd.visibility,
               kc.chunk_index,
               kc.section_path,
               kc.chunk_text,
               kc.token_count,
               kc.metadata
        from app.knowledge_chunks kc
        join app.knowledge_documents kd on kd.id = kc.document_id and kd.tenant_id = kc.tenant_id
        where kc.tenant_id=$1
          and kd.status='active'
        order by kd.updated_at desc, kc.chunk_index asc
        """,
        tenant_id,
    )
    matches = rank_chunks(
        payload.question,
        [record_to_dict(row) for row in rows],
        max_chunks=payload.max_chunks,
    )
    answer = build_grounded_answer(payload.question, matches, min_score=payload.min_score)
    response = {
        'tenant_id': str(tenant_id),
        'question': payload.question,
        **answer,
        'chunks': [retrieval_match_to_dict(match) for match in matches],
        'retrieval': {
            'candidate_chunk_count': len(rows),
            'returned_chunk_count': len(matches),
            'min_score': payload.min_score,
        },
    }
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='intent.evaluated',
        entity_type='intent_evaluation',
        entity_id=None,
        metadata={
            'status': response['status'],
            'sufficient_context': response['sufficient_context'],
            'returned_chunk_count': len(matches),
            'top_score': matches[0].score if matches else None,
        },
    )
    return response


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
    current_document = normalize_knowledge_document(current)

    allowed = {
        column: value
        for column, value in payload.model_dump(exclude_unset=True).items()
        if column in columns and column in KNOWLEDGE_DOCUMENT_WRITABLE_COLUMNS
    }
    if not allowed:
        return current_document

    content_changed = 'content' in allowed and allowed.get('content') != current_document.get('content')
    extracted_text_changed = (
        'metadata' in allowed
        and metadata_extracted_text(allowed.get('metadata'))
        != metadata_extracted_text(current_document.get('metadata'))
    )
    invalidates_chunks = content_changed or extracted_text_changed
    if invalidates_chunks:
        allowed['status'] = 'draft'
    elif allowed.get('status') == 'active':
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

    async with conn.transaction():
        row = await conn.fetchrow(
            f"""
            update app.knowledge_documents
            set {', '.join(assignments)}
            where tenant_id=$1 and id=$2
            returning {knowledge_document_projection(columns)}
            """,
            *values,
        )
        if invalidates_chunks:
            await conn.execute(
                'delete from app.knowledge_chunks where tenant_id=$1 and document_id=$2',
                tenant_id,
                document_id,
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
    conn: asyncpg.Connection = Depends(get_db),
):
    if hub_mode != 'subscribe' or not hub_verify_token:
        raise HTTPException(status_code=403, detail='Invalid verify token')
    rows = await conn.fetch(
        """
        select tenant_id
        from app.tenant_channels
        where provider='whatsapp_cloud_api'
          and status='active'
        """,
    )
    for row in rows:
        verify_token = resolve_secret_ref(tenant_secret_ref(row['tenant_id'], 'whatsapp_verify_token'))
        if verify_token and hmac.compare_digest(verify_token, hub_verify_token):
            return Response(content=hub_challenge or '', media_type='text/plain')
    raise HTTPException(status_code=403, detail='Invalid verify token')


@webhook_router.post('/whatsapp', status_code=202)
async def receive_whatsapp_webhook(request: Request, conn: asyncpg.Connection = Depends(get_db), x_hub_signature_256: str | None = Header(default=None, alias='X-Hub-Signature-256')):
    body = await request.body()
    try:
        payload = json.loads(body or b'{}')
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail='Invalid webhook payload') from exc

    phone_number_id = whatsapp_phone_number_id_from_payload(payload)
    if not phone_number_id:
        raise HTTPException(status_code=404, detail='WhatsApp channel not found')

    channel = await conn.fetchrow(
        """
        select id, tenant_id, app_secret_ref
        from app.tenant_channels
        where provider='whatsapp_cloud_api'
          and phone_number_id=$1
          and status='active'
        """,
        phone_number_id,
    )
    if not channel:
        raise HTTPException(status_code=404, detail='WhatsApp channel not found')

    app_secret = resolve_secret_ref(channel['app_secret_ref'])
    if not verify_signature_with_secret(body, x_hub_signature_256, app_secret):
        raise HTTPException(status_code=401, detail='Invalid webhook signature')

    await conn.execute("select set_config('app.tenant_id', $1, true)", str(channel['tenant_id']))
    sha = hashlib.sha256(body).hexdigest()
    await conn.fetchrow(
        """
        insert into app.webhook_events_raw (tenant_id, provider, event_type, headers, payload, payload_sha256)
        values ($1, 'whatsapp_cloud_api', $2, $3::jsonb, $4::jsonb, $5)
        on conflict (payload_sha256) do nothing returning *
        """,
        channel['tenant_id'],
        payload.get('object', 'unknown'),
        json.dumps(dict(request.headers)),
        json.dumps(payload),
        sha,
    )

    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            value = change.get('value', {})
            contacts_by_wa_id = {
                str(contact.get('wa_id')): contact
                for contact in value.get('contacts', [])
                if contact.get('wa_id')
            }
            for message in value.get('messages', []):
                wa_id = str(message.get('from') or '').strip()
                external_message_id = str(message.get('id') or '').strip()
                if not wa_id or not external_message_id:
                    continue

                contact_payload = contacts_by_wa_id.get(wa_id, {})
                display_name = contact_payload.get('profile', {}).get('name')
                phone_e164 = f'+{wa_id}' if not wa_id.startswith('+') else wa_id
                phone_hash = hashlib.sha256(phone_e164.encode()).digest()
                contact = await upsert_whatsapp_contact(
                    conn,
                    tenant_id=channel['tenant_id'],
                    wa_id=wa_id,
                    phone_e164=phone_e164,
                    phone_hash=phone_hash,
                    display_name=display_name,
                    metadata={'whatsapp_contact': contact_payload},
                    source='whatsapp_cloud_api',
                )

                conversation = await conn.fetchrow(
                    """
                    select *
                    from app.conversations
                    where tenant_id=$1
                      and contact_id=$2
                      and channel_id=$3
                      and status not in ('resolved','closed','archived')
                    order by updated_at desc
                    limit 1
                    """,
                    channel['tenant_id'],
                    contact['id'],
                    channel['id'],
                )
                if conversation:
                    conversation = await conn.fetchrow(
                        """
                        update app.conversations
                        set status=case when status='human_active' then status else 'waiting_agent' end,
                            handoff_required=case when status='human_active' then handoff_required else true end
                        where tenant_id=$1 and id=$2
                        returning *
                        """,
                        channel['tenant_id'],
                        conversation['id'],
                    )
                else:
                    conversation = await conn.fetchrow(
                        """
                        insert into app.conversations (tenant_id, contact_id, channel_id, status, opened_by, handoff_required)
                        values ($1, $2, $3, 'waiting_agent', 'user', true)
                        returning *
                        """,
                        channel['tenant_id'],
                        contact['id'],
                        channel['id'],
                    )

                message_type = message.get('type') or 'text'
                if message_type not in {'text', 'image', 'audio', 'video', 'document', 'interactive'}:
                    message_type = 'text'
                media_payload = message.get(message_type) if message_type in {'image', 'audio', 'video', 'document'} else None
                media_id = None
                mime_type = None
                if isinstance(media_payload, dict):
                    media_id = media_payload.get('id')
                    mime_type = media_payload.get('mime_type')
                body_text = message.get('text', {}).get('body') if isinstance(message.get('text'), dict) else None
                if body_text is None and isinstance(media_payload, dict):
                    body_text = media_payload.get('caption')
                timestamp = message.get('timestamp')
                received_at = None
                if timestamp:
                    try:
                        received_at = datetime.fromtimestamp(int(timestamp), UTC)
                    except (TypeError, ValueError, OSError):
                        received_at = None
                inbound_message = await conn.fetchrow(
                    """
                    insert into app.messages (
                      tenant_id, conversation_id, external_message_id, direction, sender_actor_type, sender_actor_id,
                      body_text, message_type, media_id, mime_type, payload, status, received_at
                    )
                    values ($1, $2, $3, 'inbound', 'contact', $4, $5, $6, $7, $8, $9::jsonb, 'received', coalesce($10::timestamptz, now()))
                    on conflict (tenant_id, external_message_id) do nothing
                    returning *
                    """,
                    channel['tenant_id'],
                    conversation['id'],
                    external_message_id,
                    wa_id,
                    body_text,
                    message_type,
                    str(media_id) if media_id else None,
                    str(mime_type) if mime_type else None,
                    json.dumps(message),
                    received_at,
                )
                if inbound_message:
                    await notify_operations_change(
                        conn,
                        channel['tenant_id'],
                        'conversation.changed',
                        conversation_id=conversation['id'],
                        message_id=inbound_message['id'],
                    )
    return {'accepted': True, 'payload_sha256': sha}


router.include_router(public_router)
router.include_router(webhook_router)
router.include_router(platform_admin_router)
router.include_router(tenant_signup_router)
router.include_router(tenant_admin_router)
router.include_router(tenant_ops_router)
router.include_router(system_router)
