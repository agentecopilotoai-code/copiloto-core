import asyncio
import csv
import hashlib
import hmac
import io
import json
from pathlib import Path
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import httpx
import asyncpg
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status

from app.api.v1.schemas import (
    AppointmentCreate,
    AppointmentUpdate,
    ChannelCreate,
    ChannelModeUpdate,
    ContactNoteCreate,
    ContactTagAssign,
    ContactTagCreate,
    ContactTagUpdate,
    ContactUpsert,
    ConversationCreate,
    ConversationStart,
    IntentEvaluateRequest,
    KnowledgeDocumentCreate,
    KnowledgeDocumentUpdate,
    KnowledgeStorageUpdate,
    MemberInvite,
    MemberRoleUpdate,
    MessageCreate,
    PromptCreate,
    QuoteCreate,
    QuotePatch,
    ResourceCreate,
    ResourceUpdate,
    ServiceCreate,
    ServiceReorderRequest,
    ServiceRequestCreate,
    ServiceRequestPatch,
    ServiceUpdate,
    TenantCreate,
    TenantStatusTransition,
    TenantUpdate,
    WhatsAppTemplateCreate,
    WhatsAppTemplateUpdate,
)
from app.core.config import get_settings
from app.core.security import authenticate_request, require_min_role, require_platform_owner, require_service
from app.db.pool import get_db, record_to_dict
from app.services.audit import audit
from app.services.auth0_admin import (
    assign_roles as auth0_assign_roles,
    auth0_management_enabled,
    invite_user as auth0_invite_user,
    revoke_tenant_roles as auth0_revoke_tenant_roles,
)
from app.services.knowledge_storage import delete_knowledge_file, is_binary_extractable, store_knowledge_file
from app.services.notifications import (
    cancel_appointment_reminder_jobs,
    create_appointment_reminder_jobs,
    regenerate_appointment_reminder_jobs,
)
from app.services.rag_indexing import build_indexing_result_async, vector_literal
from app.services.intent_classifier import classify_intent
from app.services.rag_orchestrator import orchestrate_inbound_message
from app.services.rag_retrieval import build_grounded_answer, rank_chunks, retrieval_match_to_dict
from app.services.whatsapp import (
    delete_template_from_meta,
    download_whatsapp_media,
    fetch_templates_from_meta,
    normalize_meta_app_secret,
    parse_interactive_reply,
    resolve_secret_ref,
    secret_ref_is_configured,
    submit_template_to_meta,
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


def tenant_knowledge_s3_secret_ref(tenant_id: UUID) -> str:
    return tenant_secret_ref(tenant_id, 'knowledge_s3_secret_access_key')


def default_knowledge_storage_config(tenant_id: UUID) -> dict[str, Any]:
    return {
        'backend': 'local',
        'bucket': None,
        'region': None,
        'endpoint_url': None,
        'prefix': f'tenants/{tenant_id}/knowledge',
        'access_key_id': None,
        'secret_ref': None,
    }


def normalize_knowledge_storage_config(tenant_id: UUID, value: Any) -> dict[str, Any]:
    config = default_knowledge_storage_config(tenant_id)
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {}
    if isinstance(value, dict):
        for key in ('backend', 'bucket', 'region', 'endpoint_url', 'prefix', 'access_key_id', 'secret_ref'):
            if key in value:
                config[key] = value[key]
    config['backend'] = config.get('backend') if config.get('backend') in {'local', 's3'} else 'local'
    if not config.get('prefix'):
        config['prefix'] = f'tenants/{tenant_id}/knowledge'
    return config


async def fetch_tenant_knowledge_storage_config(
    conn: asyncpg.Connection, tenant_id: UUID
) -> dict[str, Any]:
    value = await conn.fetchval(
        'select knowledge_storage from app.tenant_settings where tenant_id=$1', tenant_id
    )
    return normalize_knowledge_storage_config(tenant_id, value)


def public_knowledge_storage_config(tenant_id: UUID, config: dict[str, Any]) -> dict[str, Any]:
    response = normalize_knowledge_storage_config(tenant_id, config)
    response['secret_configured'] = secret_ref_is_configured(response.get('secret_ref'))
    response['effective_bucket'] = response.get('bucket') or get_settings().knowledge_storage_bucket
    return response



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
tenant_catalog_router = APIRouter(
    tags=['tenant-catalog'],
    dependencies=[Depends(authenticate_request), Depends(require_min_role('admin', allow_service=True))],
)
tenant_ops_router = APIRouter(
    tags=['tenant-operations'],
    dependencies=[Depends(authenticate_request), Depends(require_min_role('agent', allow_service=True))],
)
tenant_analytics_router = APIRouter(
    tags=['tenant-analytics'],
    dependencies=[Depends(authenticate_request), Depends(require_min_role('manager'))],
)
tenant_signup_router = APIRouter(
    tags=['tenant-signup'],
    dependencies=[Depends(authenticate_request), Depends(require_min_role('admin'))],
)
# Endpoints that any authenticated user must be able to call regardless of the
# role they currently hold inside their default tenant.  Used for the Slack-style
# tenant switcher (listing tenants the user belongs to).
tenant_user_router = APIRouter(
    tags=['tenant-user'],
    dependencies=[Depends(authenticate_request)],
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
KNOWLEDGE_DOCUMENT_PROJECTION = ', '.join(KNOWLEDGE_DOCUMENT_RESPONSE_COLUMNS)


def parse_json_object(value: Any, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return default or {}
    if isinstance(value, dict):
        return value
    return default or {}


def normalize_knowledge_document(row: asyncpg.Record | None) -> dict | None:
    document = record_to_dict(row)
    if not document:
        return None
    document['metadata'] = parse_json_object(document.get('metadata'), default={})
    return document


def normalize_knowledge_documents(rows: list[asyncpg.Record]) -> list[dict]:
    return [normalize_knowledge_document(row) for row in rows]


def metadata_extracted_text(value: Any) -> str | None:
    metadata = parse_json_object(value, default={})
    extracted_text = metadata.get('extracted_text')
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
        insert into app.tenants (slug, legal_name, display_name, vertical_code, business_type_label, country_code, timezone)
        values ($1, $2, $3, $4, $5, $6, $7)
        returning *
        """,
        payload.slug,
        payload.legal_name,
        payload.display_name,
        payload.vertical_code,
        payload.business_type_label,
        payload.country_code,
        payload.timezone,
    )
    tenant_id = row['id']
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    default_escalation_policy = {
        'handoff_message': 'En este momento te conecto con un asesor. En breve te atienden 😊',
        'triggers': {
            'keywords': ['humano', 'asesor', 'agente', 'persona', 'queja', 'reclamo'],
            'after_bot_turns': 10,
            'confidence_below': 0.0,
        },
    }
    await conn.execute(
        """
        insert into app.tenant_settings (tenant_id, escalation_policy)
        values ($1, $2::jsonb)
        """,
        tenant_id,
        json.dumps(default_escalation_policy),
    )
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
            business_type_label=$6,
            country_code=$7,
            timezone=$8,
            status=$9,
            updated_at=now()
        where id=$1 and deleted_at is null
        returning *
        """,
        tenant_id,
        merged['slug'],
        merged['legal_name'],
        merged['display_name'],
        merged['vertical_code'],
        merged.get('business_type_label'),
        merged['country_code'],
        merged['timezone'],
        merged['status'],
    )
    if not row:
        raise HTTPException(status_code=404, detail='Tenant not found')
    return row


@tenant_user_router.get('/me/tenants')
async def list_my_tenants(request: Request, conn: asyncpg.Connection = Depends(get_db)):
    """Return every tenant the authenticated user belongs to with their role.

    Drives the Slack-style tenant switcher in the Admin Panel.  Any
    authenticated user can hit this regardless of which role they hold in
    their current tenant, because they may have a different role in a
    different tenant.
    """
    actor_id = getattr(request.state, 'actor_id', None)
    if not actor_id:
        raise HTTPException(status_code=401, detail='Authentication required')
    rows = await conn.fetch(
        """
        select t.id, t.slug, t.legal_name, t.display_name, t.vertical_code,
               t.business_type_label, t.country_code, t.timezone, t.status,
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
               bool_or(utr.is_default) as is_default,
               min(utr.created_at) as joined_at
        from app.users u
        join app.user_tenant_roles utr on utr.user_id = u.id
        join app.tenants t on t.id = utr.tenant_id
        where u.auth_subject=$1 and t.deleted_at is null
        group by t.id
        order by bool_or(utr.is_default) desc, min(utr.created_at) asc
        """,
        actor_id,
    )
    tenants = []
    for row in rows:
        record = record_to_dict(row)
        roles = list(record.get('roles') or [])
        record['roles'] = roles
        # Keep backwards-compatible single role field (highest role wins).
        record['role'] = roles[0] if roles else None
        tenants.append(record)
    return tenants


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
        insert into app.tenants (slug, legal_name, display_name, vertical_code, business_type_label, country_code, timezone)
        values ($1, $2, $3, $4, $5, $6, $7)
        returning *
        """,
        payload.slug,
        payload.legal_name,
        payload.display_name,
        payload.vertical_code,
        payload.business_type_label,
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


_VALID_STATUS_TRANSITIONS: dict[str, set[str]] = {
    'trial': {'active', 'suspended', 'churned'},
    'active': {'suspended', 'churned'},
    'suspended': {'active', 'churned'},
    'churned': set(),
}


@tenant_admin_router.patch('/tenants/{tenant_id}/status')
async def patch_tenant_status(
    tenant_id: UUID,
    payload: TenantStatusTransition,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow('select * from app.tenants where id=$1 and deleted_at is null', tenant_id)
    if not row:
        raise HTTPException(status_code=404, detail='Tenant not found')
    current_status = row['status']
    allowed = _VALID_STATUS_TRANSITIONS.get(current_status, set())
    if payload.status not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Transición inválida: {current_status!r} → {payload.status!r}. "
                   f"Transiciones permitidas desde '{current_status}': {sorted(allowed) or 'ninguna'}.",
        )
    updated = await conn.fetchrow(
        'update app.tenants set status=$2, updated_at=now() where id=$1 and deleted_at is null returning *',
        tenant_id,
        payload.status,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant.status_changed',
        entity_type='tenant',
        entity_id=str(tenant_id),
        metadata={'from_status': current_status, 'to_status': payload.status, 'reason': payload.reason},
    )
    return record_to_dict(updated)


_TENANT_MEMBER_ROLES = ('owner', 'admin', 'manager', 'agent', 'viewer')


async def _ensure_caller_can_target_role(
    request: Request, conn: asyncpg.Connection, tenant_id: UUID, target_role: str
) -> None:
    """Only an existing owner of the tenant may assign or modify the owner role."""
    if target_role != 'owner':
        return
    if is_service_or_support(request):
        return
    actor_id = getattr(request.state, 'actor_id', None)
    if not actor_id:
        raise HTTPException(status_code=403, detail='Only an owner can manage the owner role')
    caller_is_owner = await conn.fetchval(
        """
        select exists(
          select 1
          from app.users u
          join app.user_tenant_roles utr on utr.user_id = u.id
          where u.auth_subject=$1 and utr.tenant_id=$2 and utr.role='owner'
        )
        """,
        actor_id,
        tenant_id,
    )
    if not caller_is_owner:
        raise HTTPException(status_code=403, detail='Only an owner can manage the owner role')


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


@tenant_admin_router.get('/tenants/{tenant_id}/members')
async def list_tenant_members(
    tenant_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
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
        from app.user_tenant_roles utr
        join app.users u on u.id = utr.user_id
        where utr.tenant_id=$1
        group by u.id
        order by min(utr.created_at) asc
        """,
        tenant_id,
    )
    members = []
    for row in rows:
        record = record_to_dict(row)
        record['roles'] = list(record.get('roles') or [])
        members.append(record)
    return {
        'members': members,
        'auth0_management_enabled': auth0_management_enabled(),
    }


@tenant_admin_router.post(
    '/tenants/{tenant_id}/members', status_code=status.HTTP_201_CREATED
)
async def invite_tenant_member(
    tenant_id: UUID,
    payload: MemberInvite,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    await _ensure_caller_can_target_role(request, conn, tenant_id, payload.role)

    email = payload.email.strip().lower()
    if '@' not in email:
        raise HTTPException(status_code=422, detail='A valid email is required')

    existing = await conn.fetchrow(
        'select id, auth_subject from app.users where email=$1', email
    )

    if existing:
        user_id = existing['id']
        auth_subject = existing['auth_subject']
        # Refresh display_name when provided.
        if payload.display_name:
            await conn.execute(
                'update app.users set display_name=$2, updated_at=now() where id=$1',
                user_id,
                payload.display_name,
            )
    else:
        # No Auth0 subject yet — use a stable placeholder so the schema's
        # NOT NULL/UNIQUE constraints on auth_subject are satisfied.
        pending_subject = f'pending|{uuid5(NAMESPACE_URL, email).hex}'
        row = await conn.fetchrow(
            """
            insert into app.users (auth_subject, email, display_name, status)
            values ($1, $2, $3, 'invited')
            returning id, auth_subject
            """,
            pending_subject,
            email,
            payload.display_name or email.split('@', 1)[0],
        )
        user_id = row['id']
        auth_subject = row['auth_subject']

    already_member = await conn.fetchval(
        'select 1 from app.user_tenant_roles where user_id=$1 and tenant_id=$2 limit 1',
        user_id,
        tenant_id,
    )
    if already_member:
        raise HTTPException(
            status_code=409,
            detail='This user already belongs to the tenant; update their role instead.',
        )

    is_default = not bool(
        await conn.fetchval(
            'select 1 from app.user_tenant_roles where user_id=$1 limit 1', user_id
        )
    )
    await conn.execute(
        """
        insert into app.user_tenant_roles (user_id, tenant_id, role, is_default)
        values ($1, $2, $3, $4)
        on conflict (user_id, tenant_id, role) do update set is_default=excluded.is_default
        """,
        user_id,
        tenant_id,
        payload.role,
        is_default,
    )

    auth0_result: dict[str, Any] = {'disabled': True}
    if not existing or (auth_subject and auth_subject.startswith('pending|')):
        # New user — try to send invitation ticket through Auth0.
        try:
            auth0_result = await auth0_invite_user(
                email=email,
                role=payload.role,
                tenant_id=tenant_id,
                display_name=payload.display_name,
            )
        except Exception as exc:  # noqa: BLE001 - log and continue without Auth0
            log.warning('tenant_member.auth0_invite_failed', error=str(exc))
            auth0_result = {'disabled': False, 'error': str(exc)}
    else:
        # Existing Auth0 user — keep their tenant_roles claim in sync.
        try:
            roles_payload = await conn.fetch(
                """
                select utr.tenant_id::text as tenant_id, utr.role
                from app.user_tenant_roles utr
                where utr.user_id=$1
                """,
                user_id,
            )
            roles_list = [
                {'tenant_id': r['tenant_id'], 'role': r['role']} for r in roles_payload
            ]
            auth0_result = await auth0_assign_roles(
                auth_subject=auth_subject, roles=roles_list
            )
        except Exception as exc:  # noqa: BLE001
            log.warning('tenant_member.auth0_assign_failed', error=str(exc))
            auth0_result = {'disabled': False, 'error': str(exc)}

    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant_member.invited',
        entity_type='user',
        entity_id=str(user_id),
        metadata={'email': email, 'role': payload.role},
    )

    member = await _tenant_member_payload(conn, tenant_id, user_id)
    member['auth0'] = auth0_result
    member['auth0_skipped'] = bool(auth0_result.get('disabled'))
    return member


@tenant_admin_router.patch('/tenants/{tenant_id}/members/{user_id}')
async def update_tenant_member_role(
    tenant_id: UUID,
    user_id: UUID,
    payload: MemberRoleUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    user_row = await conn.fetchrow(
        'select id, auth_subject from app.users where id=$1', user_id
    )
    if not user_row:
        raise HTTPException(status_code=404, detail='User not found')

    current_role_row = await conn.fetchrow(
        """
        select role
        from app.user_tenant_roles
        where user_id=$1 and tenant_id=$2
        order by case role
            when 'owner' then 1
            when 'admin' then 2
            when 'manager' then 3
            when 'agent' then 4
            when 'viewer' then 5
            else 6
        end
        limit 1
        """,
        user_id,
        tenant_id,
    )
    if not current_role_row:
        raise HTTPException(status_code=404, detail='Member not found in tenant')
    previous_role = current_role_row['role']
    if previous_role == payload.role:
        member = await _tenant_member_payload(conn, tenant_id, user_id)
        member['auth0'] = {'disabled': not auth0_management_enabled(), 'skipped': 'no_change'}
        return member

    await _ensure_caller_can_target_role(request, conn, tenant_id, payload.role)
    await _ensure_caller_can_target_role(request, conn, tenant_id, previous_role)

    if previous_role == 'owner' and payload.role != 'owner':
        owner_count = await _tenant_owner_count(conn, tenant_id)
        if owner_count <= 1:
            raise HTTPException(
                status_code=409,
                detail='Cannot demote the last owner of the tenant. Promote another user to owner first.',
            )

    async with conn.transaction():
        await conn.execute(
            'delete from app.user_tenant_roles where user_id=$1 and tenant_id=$2',
            user_id,
            tenant_id,
        )
        await conn.execute(
            """
            insert into app.user_tenant_roles (user_id, tenant_id, role, is_default)
            values ($1, $2, $3, true)
            on conflict (user_id, tenant_id, role) do update set is_default=true
            """,
            user_id,
            tenant_id,
            payload.role,
        )

    # Sync the user's tenant_roles claim list in Auth0 user_metadata.
    auth0_result: dict[str, Any] = {'disabled': True}
    try:
        roles_payload = await conn.fetch(
            """
            select utr.tenant_id::text as tenant_id, utr.role
            from app.user_tenant_roles utr
            where utr.user_id=$1
            """,
            user_id,
        )
        roles_list = [
            {'tenant_id': r['tenant_id'], 'role': r['role']} for r in roles_payload
        ]
        auth0_result = await auth0_assign_roles(
            auth_subject=user_row['auth_subject'], roles=roles_list
        )
    except Exception as exc:  # noqa: BLE001
        log.warning('tenant_member.auth0_assign_failed', error=str(exc))
        auth0_result = {'disabled': False, 'error': str(exc)}

    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant_member.role_updated',
        entity_type='user',
        entity_id=str(user_id),
        metadata={'previous_role': previous_role, 'new_role': payload.role},
    )

    member = await _tenant_member_payload(conn, tenant_id, user_id)
    member['auth0'] = auth0_result
    return member


@tenant_admin_router.delete(
    '/tenants/{tenant_id}/members/{user_id}', status_code=status.HTTP_204_NO_CONTENT
)
async def remove_tenant_member(
    tenant_id: UUID,
    user_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> Response:
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    user_row = await conn.fetchrow(
        'select id, auth_subject from app.users where id=$1', user_id
    )
    if not user_row:
        raise HTTPException(status_code=404, detail='User not found')

    role_rows = await conn.fetch(
        'select role from app.user_tenant_roles where user_id=$1 and tenant_id=$2',
        user_id,
        tenant_id,
    )
    if not role_rows:
        raise HTTPException(status_code=404, detail='Member not found in tenant')
    member_roles = [row['role'] for row in role_rows]

    if 'owner' in member_roles:
        await _ensure_caller_can_target_role(request, conn, tenant_id, 'owner')
        owner_count = await _tenant_owner_count(conn, tenant_id)
        if owner_count <= 1:
            raise HTTPException(
                status_code=409,
                detail='Cannot remove the last owner of the tenant.',
            )

    await conn.execute(
        'delete from app.user_tenant_roles where user_id=$1 and tenant_id=$2',
        user_id,
        tenant_id,
    )

    try:
        await auth0_revoke_tenant_roles(
            auth_subject=user_row['auth_subject'], tenant_id=tenant_id
        )
    except Exception as exc:  # noqa: BLE001
        log.warning('tenant_member.auth0_revoke_failed', error=str(exc))

    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant_member.removed',
        entity_type='user',
        entity_id=str(user_id),
        metadata={'previous_roles': member_roles},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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


def _coerce_jsonb(value: Any) -> Any:
    """Ensure a value that may arrive as a JSON string is returned as a Python dict/list."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            pass
    return value


@tenant_admin_router.patch('/tenants/{tenant_id}/settings')
async def patch_settings(tenant_id: UUID, payload: dict, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    allowed = {
        k: payload[k]
        for k in ('locale', 'business_hours', 'escalation_policy', 'pii_policy', 'no_train', 'notification_settings')
        if k in payload
    }
    current = await conn.fetchrow('select * from app.tenant_settings where tenant_id=$1', tenant_id)
    if not current:
        raise HTTPException(status_code=404, detail='Settings not found')
    merged = dict(current)
    merged.update(allowed)

    # Normalize jsonb fields: accept both raw dicts and JSON strings from clients
    for jsonb_key in ('business_hours', 'escalation_policy', 'pii_policy', 'notification_settings'):
        merged[jsonb_key] = _coerce_jsonb(merged[jsonb_key]) or {}

    row = await conn.fetchrow(
        """
        update app.tenant_settings
        set locale=$2, business_hours=$3::jsonb, escalation_policy=$4::jsonb, pii_policy=$5::jsonb,
            no_train=$6, notification_settings=$7::jsonb
        where tenant_id=$1 returning *
        """,
        tenant_id,
        merged['locale'],
        json.dumps(merged['business_hours']),
        json.dumps(merged['escalation_policy']),
        json.dumps(merged['pii_policy']),
        merged['no_train'],
        json.dumps(merged['notification_settings']),
    )
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='tenant_settings.updated', entity_type='tenant_settings', entity_id=str(tenant_id))
    return record_to_dict(row)


@tenant_admin_router.get('/tenants/{tenant_id}/knowledge/storage')
async def get_knowledge_storage_settings(
    tenant_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    config = await fetch_tenant_knowledge_storage_config(conn, tenant_id)
    return public_knowledge_storage_config(tenant_id, config)


@tenant_admin_router.patch('/tenants/{tenant_id}/knowledge/storage')
async def patch_knowledge_storage_settings(
    tenant_id: UUID,
    payload: KnowledgeStorageUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    current = await fetch_tenant_knowledge_storage_config(conn, tenant_id)
    incoming = payload.model_dump(exclude_unset=True)
    secret_access_key = incoming.pop('secret_access_key', None)
    next_config = {**current, **incoming}
    next_config = normalize_knowledge_storage_config(tenant_id, next_config)

    if next_config['backend'] == 's3':
        if not next_config.get('bucket'):
            raise HTTPException(status_code=400, detail='S3 bucket is required for tenant knowledge storage')
        if secret_access_key and not next_config.get('access_key_id'):
            raise HTTPException(
                status_code=400,
                detail='S3 access_key_id is required when configuring a tenant secret access key',
            )
        if secret_access_key:
            secret_ref = tenant_knowledge_s3_secret_ref(tenant_id)
            write_tenant_secret(secret_ref, secret_access_key)
            next_config['secret_ref'] = secret_ref
        elif next_config.get('access_key_id') and not secret_ref_is_configured(next_config.get('secret_ref')):
            raise HTTPException(
                status_code=400,
                detail='S3 secret access key is required the first time access_key_id is configured',
            )
    else:
        next_config = default_knowledge_storage_config(tenant_id)

    row = await conn.fetchrow(
        """
        update app.tenant_settings
        set knowledge_storage=$2::jsonb
        where tenant_id=$1
        returning knowledge_storage
        """,
        tenant_id,
        json.dumps(next_config),
    )
    if not row:
        raise HTTPException(status_code=404, detail='Settings not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant_knowledge_storage.updated',
        entity_type='tenant_settings',
        entity_id=str(tenant_id),
        metadata={
            'backend': next_config.get('backend'),
            'bucket': next_config.get('bucket'),
            'prefix': next_config.get('prefix'),
            'secret_configured': secret_ref_is_configured(next_config.get('secret_ref')),
        },
    )
    return public_knowledge_storage_config(tenant_id, next_config)


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


@tenant_admin_router.patch('/tenants/{tenant_id}/channels/whatsapp/mode')
async def patch_channel_mode(
    tenant_id: UUID,
    payload: ChannelModeUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow(
        """
        update app.tenant_channels
        set account_mode=$2, updated_at=now()
        where tenant_id=$1 and provider='whatsapp_cloud_api'
        returning id, tenant_id, provider, account_mode, status, updated_at
        """,
        tenant_id,
        payload.account_mode,
    )
    if not row:
        raise HTTPException(status_code=404, detail='WhatsApp channel not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='channel.mode_changed',
        entity_type='tenant_channel',
        entity_id=str(row['id']),
        metadata={'account_mode': payload.account_mode, 'reason': payload.reason},
    )
    return record_to_dict(row)


WHATSAPP_TEMPLATE_COLUMNS = (
    'id',
    'tenant_id',
    'channel_id',
    'name',
    'locale',
    'category',
    'status',
    'purpose',
    'components',
    'meta_template_id',
    'rejection_reason',
    'created_at',
    'updated_at',
)
WHATSAPP_TEMPLATE_PROJECTION = ', '.join(WHATSAPP_TEMPLATE_COLUMNS)

WHATSAPP_TEMPLATE_REQUIRED_PURPOSES = (
    'appointment_confirmation',
    'appointment_reminder_24h',
)


def normalize_whatsapp_template(row: asyncpg.Record | None) -> dict | None:
    template = record_to_dict(row)
    if not template:
        return None
    template['components'] = parse_json_object(template.get('components'), default={})
    return template


async def _fetch_template_or_404(
    conn: asyncpg.Connection, tenant_id: UUID, template_id: UUID
) -> asyncpg.Record:
    row = await conn.fetchrow(
        f'select {WHATSAPP_TEMPLATE_PROJECTION} from app.whatsapp_templates where tenant_id=$1 and id=$2',
        tenant_id,
        template_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Template not found')
    return row


async def _resolve_channel_for_template(
    conn: asyncpg.Connection, tenant_id: UUID, channel_id: UUID | None
) -> asyncpg.Record:
    if channel_id:
        row = await conn.fetchrow(
            "select id, waba_id, token_ref, account_mode from app.tenant_channels where tenant_id=$1 and id=$2 and provider='whatsapp_cloud_api'",
            tenant_id,
            channel_id,
        )
    else:
        row = await conn.fetchrow(
            "select id, waba_id, token_ref, account_mode from app.tenant_channels where tenant_id=$1 and provider='whatsapp_cloud_api'",
            tenant_id,
        )
    if not row:
        raise HTTPException(status_code=404, detail='WhatsApp channel not found')
    return row


@tenant_admin_router.post('/tenants/{tenant_id}/whatsapp/templates', status_code=201)
async def create_whatsapp_template(
    tenant_id: UUID,
    payload: WhatsAppTemplateCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    channel = await _resolve_channel_for_template(conn, tenant_id, payload.channel_id)
    initial_status = 'draft'
    meta_template_id: str | None = None
    rejection_reason: str | None = None
    if (channel['account_mode'] or 'mock') == 'live' and channel['waba_id']:
        try:
            meta_response = await submit_template_to_meta(
                channel['waba_id'],
                channel['token_ref'],
                name=payload.name,
                locale=payload.locale,
                category=payload.category,
                components=payload.components,
            )
        except Exception as exc:
            rejection_reason = str(exc)[:500]
        else:
            meta_template_id = (
                meta_response.get('id') if isinstance(meta_response, dict) else None
            )
            initial_status = 'pending'
    try:
        row = await conn.fetchrow(
            f"""
            insert into app.whatsapp_templates (
              tenant_id, channel_id, name, locale, category, status,
              purpose, components, meta_template_id, rejection_reason
            )
            values ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9,$10)
            returning {WHATSAPP_TEMPLATE_PROJECTION}
            """,
            tenant_id,
            channel['id'],
            payload.name,
            payload.locale,
            payload.category,
            initial_status,
            payload.purpose,
            json.dumps(payload.components),
            meta_template_id,
            rejection_reason,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(
            status_code=409,
            detail='A template with this name and locale already exists for the tenant',
        ) from exc
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='whatsapp_template.created',
        entity_type='whatsapp_template',
        entity_id=str(row['id']),
        metadata={
            'purpose': payload.purpose,
            'status': initial_status,
            'meta_template_id': meta_template_id,
        },
    )
    return normalize_whatsapp_template(row)


@tenant_admin_router.get('/tenants/{tenant_id}/whatsapp/templates')
async def list_whatsapp_templates(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    purpose: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias='status'),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        f"""
        select {WHATSAPP_TEMPLATE_PROJECTION}
        from app.whatsapp_templates
        where tenant_id=$1
          and ($2::text is null or purpose=$2)
          and ($3::text is null or status=$3)
        order by purpose asc, created_at desc
        """,
        tenant_id,
        purpose,
        status_filter,
    )
    return [normalize_whatsapp_template(row) for row in rows]


@tenant_admin_router.get('/tenants/{tenant_id}/whatsapp/templates/{template_id}')
async def get_whatsapp_template(
    tenant_id: UUID,
    template_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_template_or_404(conn, tenant_id, template_id)
    return normalize_whatsapp_template(row)


@tenant_admin_router.patch('/tenants/{tenant_id}/whatsapp/templates/{template_id}')
async def update_whatsapp_template(
    tenant_id: UUID,
    template_id: UUID,
    payload: WhatsAppTemplateUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    await _fetch_template_or_404(conn, tenant_id, template_id)
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        row = await _fetch_template_or_404(conn, tenant_id, template_id)
        return normalize_whatsapp_template(row)
    row = await conn.fetchrow(
        f"""
        update app.whatsapp_templates
        set name=coalesce($3, name),
            locale=coalesce($4, locale),
            category=coalesce($5, category),
            purpose=coalesce($6, purpose),
            components=coalesce($7::jsonb, components),
            status=coalesce($8, status),
            meta_template_id=coalesce($9, meta_template_id),
            rejection_reason=coalesce($10, rejection_reason)
        where tenant_id=$1 and id=$2
        returning {WHATSAPP_TEMPLATE_PROJECTION}
        """,
        tenant_id,
        template_id,
        update_data.get('name'),
        update_data.get('locale'),
        update_data.get('category'),
        update_data.get('purpose'),
        json.dumps(update_data['components']) if 'components' in update_data else None,
        update_data.get('status'),
        update_data.get('meta_template_id'),
        update_data.get('rejection_reason'),
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='whatsapp_template.updated',
        entity_type='whatsapp_template',
        entity_id=str(template_id),
        metadata={'status': update_data.get('status')},
    )
    return normalize_whatsapp_template(row)


@tenant_admin_router.post('/tenants/{tenant_id}/whatsapp/templates/sync')
async def sync_whatsapp_templates(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    channel = await _resolve_channel_for_template(conn, tenant_id, None)
    if (channel['account_mode'] or 'mock') != 'live' or not channel['waba_id']:
        raise HTTPException(
            status_code=400,
            detail='Template sync requires the WhatsApp channel in live mode with a configured waba_id',
        )
    try:
        meta_templates = await fetch_templates_from_meta(channel['waba_id'], channel['token_ref'])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f'Meta sync failed: {exc}') from exc
    by_key = {
        (item.get('name'), (item.get('language') or '').lower()): item
        for item in meta_templates
        if isinstance(item, dict) and item.get('name')
    }
    rows = await conn.fetch(
        'select id, name, locale from app.whatsapp_templates where tenant_id=$1',
        tenant_id,
    )
    updated = 0
    for row in rows:
        key = (row['name'], (row['locale'] or '').lower())
        meta_entry = by_key.get(key)
        if not meta_entry:
            continue
        meta_status = (meta_entry.get('status') or '').upper()
        next_status_map = {
            'APPROVED': 'approved',
            'PENDING': 'pending',
            'REJECTED': 'rejected',
            'PAUSED': 'paused',
        }
        next_status = next_status_map.get(meta_status)
        if not next_status:
            continue
        rejection_reason = meta_entry.get('rejected_reason') or meta_entry.get('reason')
        await conn.execute(
            """
            update app.whatsapp_templates
            set status=$3,
                meta_template_id=coalesce($4, meta_template_id),
                rejection_reason=$5
            where tenant_id=$1 and id=$2
            """,
            tenant_id,
            row['id'],
            next_status,
            str(meta_entry.get('id')) if meta_entry.get('id') is not None else None,
            str(rejection_reason)[:500] if rejection_reason else None,
        )
        updated += 1
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='whatsapp_template.synced',
        entity_type='whatsapp_template',
        entity_id=str(tenant_id),
        metadata={'updated': updated, 'meta_total': len(meta_templates)},
    )
    return {'updated': updated, 'meta_total': len(meta_templates)}


@tenant_admin_router.delete('/tenants/{tenant_id}/whatsapp/templates/{template_id}', status_code=204)
async def delete_whatsapp_template(
    tenant_id: UUID,
    template_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    template = await _fetch_template_or_404(conn, tenant_id, template_id)
    channel = await _resolve_channel_for_template(conn, tenant_id, template['channel_id'])
    if (channel['account_mode'] or 'mock') == 'live' and channel['waba_id']:
        try:
            await delete_template_from_meta(
                channel['waba_id'],
                channel['token_ref'],
                template_name=template['name'],
            )
        except Exception as exc:
            log.warning(
                'whatsapp_template.delete_meta_failed',
                tenant_id=str(tenant_id),
                template_id=str(template_id),
                error=str(exc)[:200],
            )
    await conn.execute(
        'delete from app.whatsapp_templates where tenant_id=$1 and id=$2',
        tenant_id,
        template_id,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='whatsapp_template.deleted',
        entity_type='whatsapp_template',
        entity_id=str(template_id),
    )
    return Response(status_code=204)


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
    return {
        'contact': record_to_dict(contact),
        'tags': [record_to_dict(row) for row in tags],
        'appointments': [record_to_dict(row) for row in appointments],
        'conversations': [record_to_dict(row) for row in conversations],
        'notes': [record_to_dict(row) for row in notes],
        'stats': {
            'total_appointments': stats['total_appointments'] if stats else 0,
            'completed_appointments': stats['completed_appointments'] if stats else 0,
            'first_visit_at': stats['first_visit_at'] if stats else None,
            'last_visit_at': stats['last_visit_at'] if stats else None,
            'average_rating': feedback['average_rating'] if feedback else None,
            'ratings_count': feedback['ratings_count'] if feedback else 0,
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


@tenant_admin_router.post('/tenants/{tenant_id}/contact-tags', status_code=201)
async def create_contact_tag(
    tenant_id: UUID,
    payload: ContactTagCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    try:
        row = await conn.fetchrow(
            """
            insert into app.contact_tags (tenant_id, name, color, description)
            values ($1, $2, $3, $4)
            returning *
            """,
            tenant_id,
            payload.name.strip(),
            payload.color,
            payload.description,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail='Tag name already exists for this tenant') from exc
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='contact_tag.created',
        entity_type='contact_tag',
        entity_id=str(row['id']),
    )
    return record_to_dict(row)


@tenant_admin_router.patch('/tenants/{tenant_id}/contact-tags/{tag_id}')
async def update_contact_tag(
    tenant_id: UUID,
    tag_id: UUID,
    payload: ContactTagUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        row = await conn.fetchrow(
            'select * from app.contact_tags where tenant_id=$1 and id=$2', tenant_id, tag_id
        )
        if not row:
            raise HTTPException(status_code=404, detail='Tag not found')
        return record_to_dict(row)
    set_clauses = []
    params: list[Any] = [tenant_id, tag_id]
    for field, value in updates.items():
        params.append(value)
        set_clauses.append(f'{field}=${len(params)}')
    try:
        row = await conn.fetchrow(
            f"""
            update app.contact_tags
            set {', '.join(set_clauses)}
            where tenant_id=$1 and id=$2
            returning *
            """,
            *params,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail='Tag name already exists for this tenant') from exc
    if not row:
        raise HTTPException(status_code=404, detail='Tag not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='contact_tag.updated',
        entity_type='contact_tag',
        entity_id=str(tag_id),
    )
    return record_to_dict(row)


@tenant_admin_router.delete('/tenants/{tenant_id}/contact-tags/{tag_id}', status_code=204)
async def delete_contact_tag(
    tenant_id: UUID,
    tag_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    deleted = await conn.fetchval(
        'delete from app.contact_tags where tenant_id=$1 and id=$2 returning id',
        tenant_id,
        tag_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail='Tag not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='contact_tag.deleted',
        entity_type='contact_tag',
        entity_id=str(tag_id),
    )
    return Response(status_code=204)


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
    vertical_code = (payload.vertical_code or '').strip()
    if not vertical_code:
        vertical_code = (
            await conn.fetchval('select vertical_code from app.tenants where id=$1', payload.tenant_id)
            or 'general'
        )
    try:
        row = await conn.fetchrow(
            """
            insert into app.resources (tenant_id, vertical_code, resource_type, code, name, capabilities, is_active)
            values ($1,$2,$3,$4,$5,$6::jsonb,$7)
            returning *
            """,
            payload.tenant_id,
            vertical_code,
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


WEEKDAY_KEYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')


def parse_iso_date(value: str) -> datetime:
    try:
        return datetime.strptime(value, '%Y-%m-%d')
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail='date must use YYYY-MM-DD format') from exc


def working_hours_for_date(capabilities: Any, target_date: datetime) -> list[dict[str, str]]:
    """Read resources.capabilities.working_hours and return franjas of the target weekday."""
    config = parse_json_object(capabilities, default={})
    working_hours = config.get('working_hours')
    if not isinstance(working_hours, dict):
        return []
    weekday_key = WEEKDAY_KEYS[target_date.weekday()]
    franjas = working_hours.get(weekday_key)
    if not isinstance(franjas, list):
        return []
    normalized: list[dict[str, str]] = []
    for franja in franjas:
        if not isinstance(franja, dict):
            continue
        start = franja.get('start')
        end = franja.get('end')
        if isinstance(start, str) and isinstance(end, str) and start and end:
            normalized.append({'start': start, 'end': end})
    return normalized


def slot_start_minutes(value: str) -> int:
    hours, _, minutes = value.partition(':')
    try:
        return int(hours) * 60 + int(minutes or 0)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f'Invalid time format: {value}') from exc


def minutes_to_hhmm(minutes: int) -> str:
    return f'{minutes // 60:02d}:{minutes % 60:02d}'


def compute_free_slots(
    franjas: list[dict[str, str]],
    busy_intervals: list[tuple[int, int]],
    duration_minutes: int,
    step_minutes: int | None = None,
) -> list[dict[str, str]]:
    """Yield free slots of `duration_minutes` skipping any overlap with busy_intervals.

    Slots are aligned to the franja start and advance in `step_minutes`
    (defaults to duration_minutes — back-to-back slots).
    """
    if duration_minutes <= 0:
        return []
    step = step_minutes or duration_minutes
    slots: list[dict[str, str]] = []
    for franja in franjas:
        franja_start = slot_start_minutes(franja['start'])
        franja_end = slot_start_minutes(franja['end'])
        if franja_end <= franja_start:
            continue
        cursor = franja_start
        while cursor + duration_minutes <= franja_end:
            slot_start = cursor
            slot_end = cursor + duration_minutes
            overlaps = False
            for busy_start, busy_end in busy_intervals:
                if slot_start < busy_end and busy_start < slot_end:
                    overlaps = True
                    break
            if not overlaps:
                slots.append({
                    'start_time': minutes_to_hhmm(slot_start),
                    'end_time': minutes_to_hhmm(slot_end),
                })
            cursor += step
    return slots


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


SERVICE_CATALOG_COLUMNS = (
    'id',
    'tenant_id',
    'name',
    'category',
    'description',
    'price_amount',
    'price_currency',
    'duration_minutes',
    'preparation_notes',
    'post_service_notes',
    'is_active',
    'sort_order',
    'metadata',
    'created_at',
    'updated_at',
)
SERVICE_CATALOG_PROJECTION = ', '.join(SERVICE_CATALOG_COLUMNS)


def normalize_service_catalog_row(row: asyncpg.Record | None) -> dict | None:
    service = record_to_dict(row)
    if not service:
        return None
    service['metadata'] = parse_json_object(service.get('metadata'), default={})
    if service.get('price_amount') is not None:
        service['price_amount'] = float(service['price_amount'])
    return service


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


@tenant_admin_router.post('/tenants/{tenant_id}/services', status_code=201)
async def create_service(
    tenant_id: UUID,
    payload: ServiceCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow(
        f"""
        insert into app.service_catalog (
          tenant_id, name, category, description, price_amount, price_currency,
          duration_minutes, preparation_notes, post_service_notes, is_active, sort_order, metadata
        )
        values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb)
        returning {SERVICE_CATALOG_PROJECTION}
        """,
        tenant_id,
        payload.name,
        payload.category,
        payload.description,
        payload.price_amount,
        payload.price_currency.upper(),
        payload.duration_minutes,
        payload.preparation_notes,
        payload.post_service_notes,
        payload.is_active,
        payload.sort_order,
        json.dumps(payload.metadata),
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='service_catalog.created',
        entity_type='service_catalog',
        entity_id=str(row['id']),
    )
    return normalize_service_catalog_row(row)


@tenant_admin_router.patch('/tenants/{tenant_id}/services/{service_id}')
async def update_service(
    tenant_id: UUID,
    service_id: UUID,
    payload: ServiceUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        row = await conn.fetchrow(
            f'select {SERVICE_CATALOG_PROJECTION} from app.service_catalog where tenant_id=$1 and id=$2',
            tenant_id,
            service_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail='Service not found')
        return normalize_service_catalog_row(row)
    if 'price_currency' in update_data and update_data['price_currency']:
        update_data['price_currency'] = update_data['price_currency'].upper()
    row = await conn.fetchrow(
        f"""
        update app.service_catalog
        set name=coalesce($3, name),
            category=coalesce($4, category),
            description=coalesce($5, description),
            price_amount=coalesce($6, price_amount),
            price_currency=coalesce($7, price_currency),
            duration_minutes=coalesce($8, duration_minutes),
            preparation_notes=coalesce($9, preparation_notes),
            post_service_notes=coalesce($10, post_service_notes),
            is_active=coalesce($11, is_active),
            sort_order=coalesce($12, sort_order),
            metadata=coalesce($13::jsonb, metadata)
        where tenant_id=$1 and id=$2
        returning {SERVICE_CATALOG_PROJECTION}
        """,
        tenant_id,
        service_id,
        update_data.get('name'),
        update_data.get('category'),
        update_data.get('description'),
        update_data.get('price_amount'),
        update_data.get('price_currency'),
        update_data.get('duration_minutes'),
        update_data.get('preparation_notes'),
        update_data.get('post_service_notes'),
        update_data.get('is_active'),
        update_data.get('sort_order'),
        json.dumps(update_data['metadata']) if 'metadata' in update_data else None,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Service not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='service_catalog.updated',
        entity_type='service_catalog',
        entity_id=str(service_id),
    )
    return normalize_service_catalog_row(row)


@tenant_admin_router.delete('/tenants/{tenant_id}/services/{service_id}', status_code=204)
async def deactivate_service(
    tenant_id: UUID,
    service_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow(
        """
        update app.service_catalog
        set is_active=false
        where tenant_id=$1 and id=$2
        returning id
        """,
        tenant_id,
        service_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Service not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='service_catalog.deactivated',
        entity_type='service_catalog',
        entity_id=str(service_id),
    )
    return Response(status_code=204)


@tenant_admin_router.post('/tenants/{tenant_id}/services/reorder')
async def reorder_services(
    tenant_id: UUID,
    payload: ServiceReorderRequest,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    if not payload.order:
        return {'updated': 0}
    async with conn.transaction():
        for item in payload.order:
            await conn.execute(
                """
                update app.service_catalog
                set sort_order=$3
                where tenant_id=$1 and id=$2
                """,
                tenant_id,
                item.id,
                item.sort_order,
            )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='service_catalog.reordered',
        entity_type='service_catalog',
        entity_id=str(tenant_id),
    )
    return {'updated': len(payload.order)}


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
            insert into app.appointments (tenant_id, contact_id, conversation_id, service_request_id, service_id, resource_id, service_code, starts_at, ends_at, notes)
            values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) returning *
            """,
            payload.tenant_id, payload.contact_id, payload.conversation_id, payload.service_request_id, payload.service_id, payload.resource_id, payload.service_code, payload.starts_at, payload.ends_at, payload.notes,
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
    rows = await conn.fetch(
        f"""
        select {KNOWLEDGE_DOCUMENT_PROJECTION}
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

    # Intent classification
    intent_result = await classify_intent(payload.question, settings=get_settings())

    response = {
        'tenant_id': str(tenant_id),
        'question': payload.question,
        'intent': intent_result.intent,
        'confidence': round(intent_result.confidence, 4),
        'resolved_by': intent_result.resolved_by,
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
            'intent': intent_result.intent,
            'confidence': round(intent_result.confidence, 4),
            'resolved_by': intent_result.resolved_by,
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
    payload_values = payload.model_dump()
    insert_columns = ['tenant_id', *KNOWLEDGE_DOCUMENT_WRITABLE_COLUMNS]
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
        returning {KNOWLEDGE_DOCUMENT_PROJECTION}
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


@tenant_admin_router.post('/knowledge/documents/upload', status_code=201)
async def upload_knowledge_document(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    try:
        form = await request.form()
    except AssertionError as exc:
        raise HTTPException(
            status_code=500, detail='python-multipart dependency is required for file uploads'
        ) from exc

    raw_tenant_id = form.get('tenant_id')
    raw_title = form.get('title')
    title = str(raw_title or '').strip()
    document_type = str(form.get('document_type') or 'reference')
    visibility = str(form.get('visibility') or 'tenant')
    file = form.get('file')
    if not raw_tenant_id or not title or not file or not hasattr(file, 'read'):
        raise HTTPException(status_code=422, detail='tenant_id, title and file are required')
    try:
        tenant_id = UUID(str(raw_tenant_id))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail='Invalid tenant_id') from exc

    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    if document_type not in {'faq', 'policy', 'reference'}:
        raise HTTPException(status_code=422, detail='Unsupported document_type')
    if visibility not in {'tenant', 'agents_only', 'public'}:
        raise HTTPException(status_code=422, detail='Unsupported visibility')

    data = await file.read()
    filename = getattr(file, 'filename', None) or 'upload.bin'
    mime_type = getattr(file, 'content_type', None)
    document_id = uuid4()
    settings = get_settings()
    storage_config = await fetch_tenant_knowledge_storage_config(conn, tenant_id)
    storage_secret = (
        resolve_secret_ref(storage_config.get('secret_ref'))
        if storage_config.get('backend') == 's3' and storage_config.get('secret_ref')
        else None
    )
    try:
        stored = store_knowledge_file(
            data=data,
            tenant_id=str(tenant_id),
            document_id=str(document_id),
            filename=filename,
            mime_type=mime_type,
            settings=settings,
            backend=storage_config.get('backend'),
            bucket=storage_config.get('bucket'),
            endpoint_url=storage_config.get('endpoint_url'),
            access_key_id=storage_config.get('access_key_id'),
            secret_access_key=storage_secret,
            region_name=storage_config.get('region'),
            prefix=storage_config.get('prefix'),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    needs_async_extraction = is_binary_extractable(filename, mime_type) and not stored.extracted_text
    metadata = {
        'editor': 'admin-panel',
        'registered_source': True,
        'original_filename': filename,
        'storage_backend': stored.storage_backend,
        'storage_bucket': stored.bucket,
        'storage_key': stored.object_key,
        'size_bytes': stored.size_bytes,
    }
    if stored.extracted_text:
        metadata['extracted_text'] = stored.extracted_text
    if needs_async_extraction:
        metadata['extraction_pending'] = True

    insert_columns = [
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
        'metadata',
    ]
    values_by_column = {
        'id': document_id,
        'tenant_id': tenant_id,
        'source_type': 'upload',
        'document_type': document_type,
        'title': title,
        'source_uri': stored.source_uri,
        'checksum': stored.checksum,
        'mime_type': mime_type or 'application/octet-stream',
        'content': stored.content,
        'visibility': visibility,
        'status': 'draft',
        'metadata': metadata,
    }
    values = [
        json.dumps(values_by_column[column]) if column == 'metadata' else values_by_column[column]
        for column in insert_columns
    ]
    placeholders = [
        f'${index}::jsonb' if column == 'metadata' else f'${index}'
        for index, column in enumerate(insert_columns, start=1)
    ]
    row = await conn.fetchrow(
        f"""
        insert into app.knowledge_documents ({', '.join(insert_columns)})
        values ({', '.join(placeholders)})
        returning {KNOWLEDGE_DOCUMENT_PROJECTION}
        """,
        *values,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='knowledge_document.uploaded',
        entity_type='knowledge_document',
        entity_id=str(document_id),
        metadata={
            'storage_backend': stored.storage_backend,
            'storage_key': stored.object_key,
            'checksum': stored.checksum,
            'size_bytes': stored.size_bytes,
            'extraction_pending': needs_async_extraction,
        },
    )
    document = normalize_knowledge_document(row)
    document['_extraction_pending'] = needs_async_extraction
    return document


@tenant_admin_router.get('/knowledge/documents/{document_id}')
async def get_knowledge_document(
    document_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow(
        f"""
        select {KNOWLEDGE_DOCUMENT_PROJECTION}
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
    current = await conn.fetchrow(
        f"""
        select {KNOWLEDGE_DOCUMENT_PROJECTION}
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
        if column in KNOWLEDGE_DOCUMENT_WRITABLE_COLUMNS
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
            returning {KNOWLEDGE_DOCUMENT_PROJECTION}
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
    document = await conn.fetchrow(
        f"""
        select {KNOWLEDGE_DOCUMENT_PROJECTION}
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
        result = await build_indexing_result_async(
            normalize_knowledge_document(document),
            max_tokens=settings.rag_chunk_max_tokens,
            overlap_tokens=settings.rag_chunk_overlap_tokens,
            embedding_dimensions=settings.rag_embedding_dimensions,
            embedding_provider=settings.rag_embedding_provider,
            embedding_model=settings.rag_embedding_model,
            embedding_api_key=settings.rag_embedding_api_key,
        )
    except (ValueError, RuntimeError) as exc:
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
        status_code = 422 if isinstance(exc, ValueError) else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc

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
            returning {KNOWLEDGE_DOCUMENT_PROJECTION}
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


@tenant_admin_router.post('/knowledge/reindex-all')
async def reindex_all_knowledge_documents(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    """Re-index all active knowledge documents for the tenant using the current embedding provider."""
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    docs = await conn.fetch(
        f"""
        select {KNOWLEDGE_DOCUMENT_PROJECTION}
        from app.knowledge_documents
        where tenant_id=$1 and status in ('active', 'draft')
        order by updated_at asc
        """,
        tenant_id,
    )
    settings = get_settings()
    indexed = 0
    failed = 0
    errors: list[dict] = []
    for doc in docs:
        doc_id = doc['id']
        try:
            result = await build_indexing_result_async(
                normalize_knowledge_document(doc),
                max_tokens=settings.rag_chunk_max_tokens,
                overlap_tokens=settings.rag_chunk_overlap_tokens,
                embedding_dimensions=settings.rag_embedding_dimensions,
                embedding_provider=settings.rag_embedding_provider,
                embedding_model=settings.rag_embedding_model,
                embedding_api_key=settings.rag_embedding_api_key,
            )
        except (ValueError, RuntimeError) as exc:
            failed += 1
            errors.append({'document_id': str(doc_id), 'error': str(exc)})
            continue
        indexing_ts = datetime.now(UTC).isoformat()
        async with conn.transaction():
            await conn.execute(
                """
                update app.knowledge_documents
                set status='indexing', metadata=metadata || $3::jsonb
                where tenant_id=$1 and id=$2
                """,
                tenant_id, doc_id, json.dumps({'last_indexing_started_at': indexing_ts}),
            )
            await conn.execute(
                'delete from app.knowledge_chunks where tenant_id=$1 and document_id=$2',
                tenant_id, doc_id,
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
                    tenant_id, doc_id,
                    chunk.chunk_index, chunk.section_path, chunk.chunk_text,
                    chunk.token_count, vector_literal(chunk.embedding),
                    json.dumps(chunk.metadata),
                )
            await conn.execute(
                """
                update app.knowledge_documents
                set status='active', metadata=metadata || $3::jsonb
                where tenant_id=$1 and id=$2
                """,
                tenant_id, doc_id,
                json.dumps({
                    'chunk_count': len(result.chunks),
                    'last_indexing_completed_at': datetime.now(UTC).isoformat(),
                    'embedding_provider': result.embedding_provider,
                    'embedding_model': result.embedding_model,
                }),
            )
        indexed += 1
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='knowledge.reindex_all',
        entity_type='tenant',
        entity_id=str(tenant_id),
        metadata={
            'indexed': indexed,
            'failed': failed,
            'embedding_provider': settings.rag_embedding_provider,
            'embedding_model': settings.rag_embedding_model,
        },
    )
    return {
        'tenant_id': str(tenant_id),
        'indexed': indexed,
        'failed': failed,
        'errors': errors,
        'embedding_provider': settings.rag_embedding_provider,
        'embedding_model': settings.rag_embedding_model,
        'embedding_dimensions': settings.rag_embedding_dimensions,
    }


@tenant_admin_router.delete('/knowledge/documents/{document_id}', status_code=204)
async def delete_knowledge_document(
    document_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    # Fetch storage metadata before deleting so we can remove the physical file
    doc = await conn.fetchrow(
        'select source_uri, metadata from app.knowledge_documents where tenant_id=$1 and id=$2',
        tenant_id, document_id,
    )
    if not doc:
        raise HTTPException(status_code=404, detail='Knowledge document not found')

    # Delete from DB — knowledge_chunks cascade automatically via FK on delete cascade
    await conn.execute(
        'delete from app.knowledge_documents where tenant_id=$1 and id=$2', tenant_id, document_id
    )

    # Delete physical file from local disk or S3
    storage_meta = _coerce_jsonb(doc['metadata']) or {}
    settings = get_settings()
    storage_config = await fetch_tenant_knowledge_storage_config(conn, tenant_id)
    storage_secret = (
        resolve_secret_ref(storage_config.get('secret_ref'))
        if storage_config.get('backend') == 's3' and storage_config.get('secret_ref')
        else None
    )
    delete_knowledge_file(
        source_uri=doc['source_uri'] or '',
        storage_backend=storage_meta.get('storage_backend') or storage_config.get('backend') or settings.knowledge_storage_backend,
        object_key=storage_meta.get('storage_key'),
        bucket=storage_meta.get('storage_bucket') or storage_config.get('bucket'),
        settings=settings,
        endpoint_url=storage_config.get('endpoint_url'),
        access_key_id=storage_config.get('access_key_id'),
        secret_access_key=storage_secret,
        region_name=storage_config.get('region'),
    )

    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='knowledge_document.deleted',
        entity_type='knowledge_document',
        entity_id=str(document_id),
        metadata={
            'storage_backend': storage_meta.get('storage_backend'),
            'storage_key': storage_meta.get('storage_key'),
        },
    )
    return Response(status_code=204)


@tenant_admin_router.post('/prompts', status_code=201)
async def create_prompt(payload: PromptCreate, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    if payload.tenant_id:
        await ensure_tenant_access(request, payload.tenant_id, conn)
    row = await conn.fetchrow("insert into app.prompt_templates (tenant_id, vertical_code, prompt_type, name, version, content, variables, checksum) values ($1,$2,$3,$4,$5,$6,$7::jsonb, encode(sha256($6::bytea),'hex')) returning *", payload.tenant_id, payload.vertical_code, payload.prompt_type, payload.name, payload.version, payload.content, json.dumps(payload.variables))
    return record_to_dict(row)


def readiness_check(key: str, label: str, ready: bool, reason: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        'key': key,
        'label': label,
        'ready': ready,
        'reason': reason,
        'details': details or {},
    }


def readiness_truthy_object(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, dict | list | tuple | set):
        return bool(value)
    return bool(str(value).strip()) if isinstance(value, str) else bool(value)


def readiness_positive_int(value: Any) -> bool:
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def readiness_response(tenant_id: UUID, checks: list[dict[str, Any]], smoke_question: str) -> dict[str, Any]:
    reasons = [check['reason'] for check in checks if not check['ready']]
    ready = not reasons
    return {
        'tenant_id': str(tenant_id),
        'checked_at': datetime.now(UTC).isoformat(),
        'status': 'ready' if ready else 'not_ready',
        'ready': ready,
        'reasons': reasons,
        'smoke_question': smoke_question,
        'checks': checks,
    }


async def build_tenant_readiness_report(
    conn: asyncpg.Connection,
    tenant_id: UUID,
    *,
    smoke_question: str = 'horarios políticas servicios garantías precios contacto',
    retrieval_min_score: float = 0.12,
) -> dict[str, Any]:
    tenant = await conn.fetchrow(
        'select id, slug, display_name, status, deleted_at from app.tenants where id=$1',
        tenant_id,
    )
    checks: list[dict[str, Any]] = []

    tenant_ready = bool(tenant and tenant['status'] == 'active' and tenant['deleted_at'] is None)
    checks.append(
        readiness_check(
            'tenant_active',
            'Tenant activo',
            tenant_ready,
            'Tenant activo y disponible.' if tenant_ready else 'El tenant no existe, no está activo o fue eliminado.',
            record_to_dict(tenant) if tenant else {},
        )
    )

    settings = await conn.fetchrow(
        'select locale, business_hours, escalation_policy, pii_policy, no_train from app.tenant_settings where tenant_id=$1',
        tenant_id,
    )
    settings_dict = record_to_dict(settings) if settings else {}
    settings_ready = bool(
        settings
        and readiness_truthy_object(settings['locale'])
        and readiness_truthy_object(settings['business_hours'])
        and readiness_truthy_object(settings['pii_policy'])
    )
    checks.append(
        readiness_check(
            'tenant_settings',
            'Settings operativos',
            settings_ready,
            'Settings mínimos configurados.' if settings_ready else 'Faltan settings mínimos: locale, horarios o PII policy.',
            settings_dict,
        )
    )

    channel = await conn.fetchrow(
        """
        select id, provider, business_id, waba_id, phone_number_id, token_ref, app_secret_ref,
               verify_token_hash is not null as verify_token_hash_configured, account_mode, status
        from app.tenant_channels
        where tenant_id=$1 and provider='whatsapp_cloud_api'
        """,
        tenant_id,
    )
    channel_dict = record_to_dict(channel) if channel else {}
    whatsapp_token_ready = token_ref_is_configured(channel['token_ref']) if channel else False
    whatsapp_secret_ready = secret_ref_is_configured(channel['app_secret_ref']) if channel else False
    whatsapp_verify_ready = secret_ref_is_configured(tenant_secret_ref(tenant_id, 'whatsapp_verify_token')) if channel else False
    whatsapp_ready = bool(
        channel
        and channel['status'] == 'active'
        and channel['business_id']
        and channel['waba_id']
        and channel['phone_number_id']
        and channel['account_mode'] == 'live'
        and whatsapp_token_ready
        and whatsapp_secret_ready
        and whatsapp_verify_ready
    )
    checks.append(
        readiness_check(
            'whatsapp_channel',
            'Canal WhatsApp',
            whatsapp_ready,
            (
                'Canal WhatsApp activo en modo live con secretos resueltos.'
                if whatsapp_ready
                else 'El canal WhatsApp no está activo, no está en modo live o faltan IDs/secretos reales.'
            ),
            {
                **channel_dict,
                'meta_access_token_configured': whatsapp_token_ready,
                'app_secret_configured': whatsapp_secret_ready,
                'verify_token_configured': whatsapp_verify_ready,
                'delivery_mode_live': channel['account_mode'] == 'live' if channel else False,
            },
        )
    )

    knowledge_counts = await conn.fetchrow(
        """
        select
          count(distinct kd.id) as active_documents,
          count(kc.id) as active_chunks
        from app.knowledge_documents kd
        left join app.knowledge_chunks kc on kc.tenant_id=kd.tenant_id and kc.document_id=kd.id
        where kd.tenant_id=$1 and kd.status='active'
        """,
        tenant_id,
    )
    retrieval_rows = await conn.fetch(
        """
        select kc.id, kc.document_id, kd.title as document_title, kd.source_uri, kd.source_type,
               kd.document_type, kd.visibility, kc.chunk_index, kc.section_path, kc.chunk_text,
               kc.token_count, kc.metadata
        from app.knowledge_chunks kc
        join app.knowledge_documents kd on kd.id=kc.document_id and kd.tenant_id=kc.tenant_id
        where kc.tenant_id=$1 and kd.status='active'
        order by kd.updated_at desc, kc.chunk_index asc
        limit 500
        """,
        tenant_id,
    )
    matches = rank_chunks(smoke_question, [record_to_dict(row) for row in retrieval_rows], max_chunks=3)
    retrieval_answer = build_grounded_answer(smoke_question, matches, min_score=retrieval_min_score)
    knowledge_ready = bool(
        knowledge_counts
        and knowledge_counts['active_documents'] > 0
        and knowledge_counts['active_chunks'] > 0
        and retrieval_answer['sufficient_context']
    )
    checks.append(
        readiness_check(
            'knowledge_retrieval',
            'Documentos activos y retrieval smoke test',
            knowledge_ready,
            'Knowledge base activa y retrieval smoke test con contexto suficiente.' if knowledge_ready else 'No hay documentos/chunks activos o el retrieval smoke test no recuperó contexto suficiente.',
            {
                'active_documents': knowledge_counts['active_documents'] if knowledge_counts else 0,
                'active_chunks': knowledge_counts['active_chunks'] if knowledge_counts else 0,
                'returned_chunk_count': len(matches),
                'top_score': matches[0].score if matches else None,
                'sufficient_context': retrieval_answer['sufficient_context'],
            },
        )
    )

    escalation_policy = _coerce_jsonb(settings_dict.get('escalation_policy') or {}) or {}
    if not isinstance(escalation_policy, dict):
        escalation_policy = {}
    ep_triggers = escalation_policy.get('triggers') or {}

    _ep_has_triggers = bool(
        ep_triggers.get('keywords')
        or ep_triggers.get('after_bot_turns')
        or ep_triggers.get('confidence_below')
    )
    _ep_has_message = bool(escalation_policy.get('handoff_message'))

    if not settings or not escalation_policy:
        handoff_ready = False
        handoff_reason = 'Política de escalamiento ausente. Configura la política en la pestaña Escalamiento del Tenant Setup.'
    elif escalation_policy.get('enabled') is False:
        handoff_ready = False
        handoff_reason = 'Política de escalamiento deshabilitada (enabled=false). Actívala en la pestaña Escalamiento del Tenant Setup.'
    elif not escalation_policy.get('queue'):
        handoff_ready = False
        handoff_reason = 'Sin cola de escalamiento (queue vacía). Configura la cola en la pestaña Escalamiento del Tenant Setup.'
    elif not _ep_has_triggers and not _ep_has_message:
        handoff_ready = False
        handoff_reason = 'Sin triggers ni mensaje de handoff. Configura keywords, after_bot_turns, confidence_below o handoff_message en la pestaña Escalamiento.'
    else:
        handoff_ready = True
        handoff_reason = 'Política de handoff configurada.'

    checks.append(
        readiness_check(
            'handoff',
            'Handoff humano',
            handoff_ready,
            handoff_reason,
            {'escalation_policy': escalation_policy},
        )
    )

    # Policy engine check: at least after_bot_turns > 0 and one trigger defined.
    pe_after_bot_turns = readiness_positive_int(ep_triggers.get('after_bot_turns'))
    pe_has_triggers = bool(ep_triggers.get('keywords') or ep_triggers.get('after_bot_turns'))
    policy_engine_ready = bool(pe_after_bot_turns and pe_has_triggers)
    if not settings:
        policy_engine_reason = 'Sin configuración de tenant settings. Configura el policy engine en la pestaña Escalamiento.'
    elif not pe_after_bot_turns:
        policy_engine_reason = 'triggers.after_bot_turns debe ser mayor que cero. Configura el límite en la pestaña Escalamiento.'
    elif not pe_has_triggers:
        policy_engine_reason = 'Sin triggers de escalamiento. Configura keywords o after_bot_turns en la pestaña Escalamiento.'
    else:
        policy_engine_reason = 'Policy engine configurado con triggers válidos.'
    checks.append(
        readiness_check(
            'policy_engine',
            'Policy engine configurado',
            policy_engine_ready,
            policy_engine_reason,
            {
                'after_bot_turns': ep_triggers.get('after_bot_turns'),
                'has_trigger_keywords': bool(ep_triggers.get('keywords')),
                'consecutive_no_context_limit': escalation_policy.get('consecutive_no_context_limit'),
            },
        )
    )

    template_rows = await conn.fetch(
        """
        select purpose, status
        from app.whatsapp_templates
        where tenant_id=$1 and purpose = any($2::text[])
        """,
        tenant_id,
        list(WHATSAPP_TEMPLATE_REQUIRED_PURPOSES),
    )
    approved_purposes = {
        row['purpose'] for row in template_rows if row['status'] == 'approved'
    }
    missing_purposes = [
        purpose for purpose in WHATSAPP_TEMPLATE_REQUIRED_PURPOSES
        if purpose not in approved_purposes
    ]
    templates_ready = not missing_purposes
    template_reason = (
        'Plantillas mínimas aprobadas para confirmación y recordatorio 24 h.'
        if templates_ready
        else f'Faltan plantillas aprobadas: {", ".join(missing_purposes)}. '
             'Crea y sincroniza con Meta desde la pestaña Plantillas de WhatsApp.'
    )
    checks.append(
        readiness_check(
            'whatsapp_templates',
            'Plantillas mínimas aprobadas',
            templates_ready,
            template_reason,
            {
                'required_purposes': list(WHATSAPP_TEMPLATE_REQUIRED_PURPOSES),
                'approved_purposes': sorted(approved_purposes),
                'missing_purposes': missing_purposes,
            },
        )
    )

    audit_count = await conn.fetchval('select count(*) from app.audit_logs where tenant_id=$1', tenant_id)
    audit_count = audit_count or 0
    audit_ready = audit_count > 0
    checks.append(
        readiness_check(
            'audit',
            'Auditoría',
            audit_ready,
            'Auditoría con eventos registrados.' if audit_ready else 'No hay eventos de auditoría para evidenciar cambios del tenant.',
            {'audit_log_entries': audit_count},
        )
    )

    return readiness_response(tenant_id, checks, smoke_question)


@tenant_admin_router.get('/tenants/{tenant_id}/readiness')
async def get_tenant_readiness(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    smoke_question: str = Query(default='horarios políticas servicios garantías precios contacto', min_length=3, max_length=1000),
    retrieval_min_score: float = Query(default=0.12, ge=0, le=1),
):
    await require_min_role('admin')(request)
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    report = await build_tenant_readiness_report(
        conn,
        tenant_id,
        smoke_question=smoke_question,
        retrieval_min_score=retrieval_min_score,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant.readiness_checked',
        entity_type='tenant',
        entity_id=str(tenant_id),
        metadata={
            'status': report['status'],
            'not_ready_reasons': report['reasons'],
            'smoke_question': smoke_question,
        },
    )
    return report


@tenant_admin_router.get('/audit-logs')
async def list_audit_logs(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    action: str | None = Query(default=None),
    actor_type: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
):
    tenant_id = await tenant_id_from_request(request, conn)
    rows = await conn.fetch(
        """
        select * from app.audit_logs
        where tenant_id=$1
          and ($2::text is null or action=$2)
          and ($3::text is null or actor_type=$3)
          and ($4::text is null or entity_type=$4)
          and ($5::timestamptz is null or created_at>=$5::timestamptz)
          and ($6::timestamptz is null or created_at<=$6::timestamptz)
        order by created_at desc
        limit $7
        """,
        tenant_id, action, actor_type, entity_type, from_date, to_date, limit,
    )
    return [record_to_dict(r) for r in rows]


@tenant_admin_router.get('/audit-logs/export')
async def export_audit_logs(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    action: str | None = Query(default=None),
    actor_type: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    from_date: str | None = Query(default=None),
    to_date: str | None = Query(default=None),
):
    tenant_id = await tenant_id_from_request(request, conn)
    rows = await conn.fetch(
        """
        select id, created_at, actor_type, actor_id, action, entity_type, entity_id, metadata
        from app.audit_logs
        where tenant_id=$1
          and ($2::text is null or action=$2)
          and ($3::text is null or actor_type=$3)
          and ($4::text is null or entity_type=$4)
          and ($5::timestamptz is null or created_at>=$5::timestamptz)
          and ($6::timestamptz is null or created_at<=$6::timestamptz)
        order by created_at desc
        limit 10000
        """,
        tenant_id, action, actor_type, entity_type, from_date, to_date,
    )
    fieldnames = ['id', 'created_at', 'actor_type', 'actor_id', 'action', 'entity_type', 'entity_id', 'metadata']
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction='ignore')
    writer.writeheader()
    for row in rows:
        writer.writerow({k: str(v) if v is not None else '' for k, v in record_to_dict(row).items()})
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='audit_logs.exported', entity_type='tenant', entity_id=str(tenant_id))
    return Response(
        content=buf.getvalue(),
        media_type='text/csv',
        headers={'Content-Disposition': f'attachment; filename="audit-logs-{tenant_id}.csv"'},
    )


@tenant_admin_router.post('/contacts/{contact_id}/suppress', status_code=200)
async def suppress_contact(
    contact_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await require_min_role('admin')(request)
    tenant_id = await tenant_id_from_request(request, conn)
    existing = await conn.fetchrow('select id from app.contacts where tenant_id=$1 and id=$2', tenant_id, contact_id)
    if not existing:
        raise HTTPException(status_code=404, detail='Contact not found')
    pseudo = f'suppressed+{contact_id}'
    row = await conn.fetchrow(
        """
        update app.contacts set
          display_name = null,
          phone_e164 = $3,
          wa_id = $3,
          phone_hash = decode(encode(sha256($3::bytea), 'hex'), 'hex'),
          opt_in_status = 'suppressed',
          opt_out_at = now(),
          tags = '{}',
          metadata = '{}'::jsonb
        where tenant_id=$1 and id=$2
        returning id, tenant_id, opt_in_status, updated_at
        """,
        tenant_id, contact_id, pseudo,
    )
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='contact.suppressed', entity_type='contact', entity_id=str(contact_id))
    return record_to_dict(row)


@tenant_admin_router.get('/tenants/{tenant_id}/data-export')
async def export_tenant_data(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await require_min_role('owner')(request)
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    tenant = await conn.fetchrow('select * from app.tenants where id=$1', tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail='Tenant not found')
    settings = await conn.fetchrow('select * from app.tenant_settings where tenant_id=$1', tenant_id)
    channels = await conn.fetch("select id, provider, status, account_mode, created_at from app.tenant_channels where tenant_id=$1", tenant_id)
    counts = await conn.fetchrow(
        """
        select
          (select count(*) from app.contacts where tenant_id=$1) as contacts,
          (select count(*) from app.conversations where tenant_id=$1) as conversations,
          (select count(*) from app.messages where tenant_id=$1) as messages,
          (select count(*) from app.service_requests where tenant_id=$1) as service_requests,
          (select count(*) from app.quotes where tenant_id=$1) as quotes,
          (select count(*) from app.knowledge_documents where tenant_id=$1) as knowledge_documents,
          (select count(*) from app.audit_logs where tenant_id=$1) as audit_log_entries
        """,
        tenant_id,
    )
    bundle = {
        'exported_at': datetime.now(UTC).isoformat(),
        'tenant': record_to_dict(tenant),
        'settings': record_to_dict(settings) if settings else {},
        'channels': [record_to_dict(ch) for ch in channels],
        'data_counts': dict(counts),
        'privacy': {
            'no_train': (settings or {}).get('no_train', True),
            'pii_policy': record_to_dict(settings).get('pii_policy', {}) if settings else {},
            'data_retention_days': 365,
            'dpa_version': '1.0',
        },
    }
    await audit(conn, tenant_id=tenant_id, actor_type=request.state.actor_type, actor_id=request.state.actor_id, action='tenant.data_exported', entity_type='tenant', entity_id=str(tenant_id))
    content = json.dumps(bundle, default=str, indent=2, ensure_ascii=False)
    return Response(
        content=content,
        media_type='application/json',
        headers={'Content-Disposition': f'attachment; filename="tenant-data-{tenant_id}.json"'},
    )


@webhook_router.get('/whatsapp')
async def verify_whatsapp_webhook(
    hub_mode: str | None = Query(default=None, alias='hub.mode'),
    hub_verify_token: str | None = Query(default=None, alias='hub.verify_token'),
    hub_challenge: str | None = Query(default=None, alias='hub.challenge'),
    conn: asyncpg.Connection = Depends(get_db),
):
    if hub_mode != 'subscribe' or not hub_verify_token:
        raise HTTPException(status_code=403, detail='Invalid verify token')
    await conn.execute("select set_config('app.support_mode', 'true', true)")
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

    await conn.execute("select set_config('app.support_mode', 'true', true)")
    channel = await conn.fetchrow(
        """
        select id, tenant_id, app_secret_ref, account_mode
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
                        set status=case
                                when status='human_active' then 'human_active'
                                when status='waiting_agent' and handoff_required then 'waiting_agent'
                                else 'waiting_user'
                            end,
                            handoff_required=case
                                when status='human_active' then handoff_required
                                when status='waiting_agent' and handoff_required then true
                                else false
                            end,
                            updated_at=now()
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
                        values ($1, $2, $3, 'open', 'user', false)
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
                interactive_reply = parse_interactive_reply(message) if message_type == 'interactive' else None
                if interactive_reply:
                    message = {**message, **interactive_reply}
                    if not body_text:
                        body_text = interactive_reply['interactive_title']
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
                    try:
                        await orchestrate_inbound_message(
                            conn,
                            tenant_id=channel['tenant_id'],
                            channel_id=channel['id'],
                            channel_account_mode=channel['account_mode'] or 'mock',
                            conversation=conversation,
                            contact=contact,
                            inbound_message=inbound_message,
                        )
                    except Exception:
                        log.exception(
                            'rag_orchestrator.error',
                            tenant_id=str(channel['tenant_id']),
                            conversation_id=str(conversation['id']),
                        )
    return {'accepted': True, 'payload_sha256': sha}


def _resolve_analytics_range(from_date: str | None, to_date: str | None) -> tuple[date, date]:
    today = datetime.now(UTC).date()
    end = date.fromisoformat(to_date) if to_date else today
    start = date.fromisoformat(from_date) if from_date else (end - timedelta(days=29))
    if start > end:
        raise HTTPException(status_code=400, detail='from_date must be on or before to_date')
    return start, end


def _range_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    range_start = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
    range_end = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    return range_start, range_end


@tenant_analytics_router.get('/analytics/overview')
async def analytics_overview(
    request: Request,
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    start, end = _resolve_analytics_range(from_date, to_date)
    range_start, range_end = _range_bounds(start, end)
    retention_start = range_end - timedelta(days=90)

    conv_row = await conn.fetchrow(
        """
        select
          count(*) as total,
          count(*) filter (where status in ('open','waiting_user','waiting_agent')) as open_count,
          count(*) filter (where status in ('resolved','closed','archived')) as resolved_count,
          count(*) filter (where status in ('human_required','human_active') or handoff_required) as handoff_count
        from app.conversations
        where tenant_id = $1 and created_at >= $2 and created_at < $3
        """,
        tenant_id, range_start, range_end,
    )
    appt_row = await conn.fetchrow(
        """
        select
          count(*) as created,
          count(*) filter (where status = 'confirmed') as confirmed,
          count(*) filter (where status = 'completed') as completed,
          count(*) filter (where status = 'cancelled') as cancelled,
          count(*) filter (where status = 'no_show') as no_shows
        from app.appointments
        where tenant_id = $1 and created_at >= $2 and created_at < $3
        """,
        tenant_id, range_start, range_end,
    )
    revenue_row = await conn.fetchrow(
        """
        select coalesce(sum(s.price_amount), 0)::float as revenue
        from app.appointments a
        left join app.service_catalog s on s.id = a.service_id and s.tenant_id = a.tenant_id
        where a.tenant_id = $1 and a.status = 'completed'
          and a.starts_at >= $2 and a.starts_at < $3
        """,
        tenant_id, range_start, range_end,
    )
    feedback_row = await conn.fetchrow(
        """
        select coalesce(avg(rating), 0)::float as avg_rating, count(*) as ratings_count
        from app.appointment_feedback
        where tenant_id = $1 and created_at >= $2 and created_at < $3
        """,
        tenant_id, range_start, range_end,
    )
    msg_row = await conn.fetchrow(
        """
        select
          count(*) filter (where direction = 'inbound') as inbound,
          count(*) filter (where direction = 'outbound') as outbound
        from app.messages
        where tenant_id = $1 and created_at >= $2 and created_at < $3
        """,
        tenant_id, range_start, range_end,
    )
    retention_row = await conn.fetchrow(
        """
        with completed as (
          select contact_id, count(*) as ct
          from app.appointments
          where tenant_id = $1 and status = 'completed'
            and starts_at >= $2 and starts_at < $3
          group by contact_id
        )
        select
          count(*) filter (where ct >= 2)::int as recurring_contacts,
          count(*)::int as total_contacts
        from completed
        """,
        tenant_id, retention_start, range_end,
    )

    conv_total = conv_row['total'] or 0
    handoff_count = conv_row['handoff_count'] or 0
    handoff_rate = (handoff_count / conv_total * 100) if conv_total else 0.0
    completed = appt_row['completed'] or 0
    no_shows = appt_row['no_shows'] or 0
    no_show_base = completed + no_shows
    no_show_rate = (no_shows / no_show_base * 100) if no_show_base else 0.0
    recurring = retention_row['recurring_contacts'] or 0
    total_retention = retention_row['total_contacts'] or 0
    retention_rate = (recurring / total_retention * 100) if total_retention else 0.0

    return {
        'range': {'from_date': start.isoformat(), 'to_date': end.isoformat()},
        'conversations': {
            'total': conv_total,
            'open': conv_row['open_count'] or 0,
            'resolved': conv_row['resolved_count'] or 0,
            'handoff': handoff_count,
            'handoff_rate_pct': round(handoff_rate, 2),
        },
        'appointments': {
            'created': appt_row['created'] or 0,
            'confirmed': appt_row['confirmed'] or 0,
            'completed': completed,
            'cancelled': appt_row['cancelled'] or 0,
            'no_shows': no_shows,
            'no_show_rate_pct': round(no_show_rate, 2),
        },
        'revenue': {
            'estimated_amount': round(revenue_row['revenue'] or 0.0, 2),
        },
        'feedback': {
            'average_rating': round(feedback_row['avg_rating'] or 0.0, 2),
            'ratings_count': feedback_row['ratings_count'] or 0,
        },
        'messages': {
            'inbound': msg_row['inbound'] or 0,
            'outbound': msg_row['outbound'] or 0,
        },
        'retention': {
            'recurring_contacts': recurring,
            'total_contacts_completed': total_retention,
            'retention_rate_pct': round(retention_rate, 2),
            'window_days': 90,
        },
    }


@tenant_analytics_router.get('/analytics/conversations')
async def analytics_conversations(
    request: Request,
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    start, end = _resolve_analytics_range(from_date, to_date)
    range_start, range_end = _range_bounds(start, end)

    intents = await conn.fetch(
        """
        select coalesce(current_intent, 'unknown') as intent, count(*) as count
        from app.conversations
        where tenant_id = $1 and created_at >= $2 and created_at < $3
        group by 1
        order by count desc
        limit 10
        """,
        tenant_id, range_start, range_end,
    )
    statuses = await conn.fetch(
        """
        select status, count(*) as count
        from app.conversations
        where tenant_id = $1 and created_at >= $2 and created_at < $3
        group by status
        order by count desc
        """,
        tenant_id, range_start, range_end,
    )
    first_response_row = await conn.fetchrow(
        """
        with first_inbound as (
          select conversation_id, min(created_at) as inbound_at
          from app.messages
          where tenant_id = $1 and direction = 'inbound'
            and created_at >= $2 and created_at < $3
          group by conversation_id
        ), first_bot as (
          select m.conversation_id, min(m.created_at) as bot_at
          from app.messages m
          where m.tenant_id = $1 and m.direction = 'outbound' and m.sender_actor_type = 'bot'
            and m.created_at >= $2 and m.created_at < $3
          group by m.conversation_id
        )
        select coalesce(
          avg(extract(epoch from (b.bot_at - i.inbound_at))),
          0
        )::float as avg_seconds
        from first_inbound i
        join first_bot b on b.conversation_id = i.conversation_id
        where b.bot_at >= i.inbound_at
        """,
        tenant_id, range_start, range_end,
    )
    daily = await conn.fetch(
        """
        select date_trunc('day', created_at)::date as date, count(*) as count
        from app.conversations
        where tenant_id = $1 and created_at >= $2 and created_at < $3
        group by 1
        order by 1
        """,
        tenant_id, range_start, range_end,
    )
    total_intents = sum(row['count'] for row in intents) or 1
    return {
        'range': {'from_date': start.isoformat(), 'to_date': end.isoformat()},
        'top_intents': [
            {
                'intent': row['intent'],
                'count': row['count'],
                'percentage': round(row['count'] / total_intents * 100, 2),
            }
            for row in intents
        ],
        'status_distribution': [
            {'status': row['status'], 'count': row['count']} for row in statuses
        ],
        'avg_first_bot_response_seconds': round(first_response_row['avg_seconds'] or 0.0, 2),
        'daily_evolution': [
            {'date': row['date'].isoformat(), 'count': row['count']} for row in daily
        ],
    }


@tenant_analytics_router.get('/analytics/appointments')
async def analytics_appointments(
    request: Request,
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    start, end = _resolve_analytics_range(from_date, to_date)
    range_start, range_end = _range_bounds(start, end)

    top_services = await conn.fetch(
        """
        select coalesce(s.name, a.service_code) as service_name,
               coalesce(s.id::text, a.service_code) as service_key,
               count(*) as count
        from app.appointments a
        left join app.service_catalog s on s.id = a.service_id and s.tenant_id = a.tenant_id
        where a.tenant_id = $1 and a.created_at >= $2 and a.created_at < $3
        group by 1, 2
        order by count desc
        limit 10
        """,
        tenant_id, range_start, range_end,
    )
    statuses = await conn.fetch(
        """
        select status, count(*) as count
        from app.appointments
        where tenant_id = $1 and created_at >= $2 and created_at < $3
        group by status
        order by count desc
        """,
        tenant_id, range_start, range_end,
    )
    no_shows_dow = await conn.fetch(
        """
        select extract(dow from starts_at)::int as dow, count(*) as count
        from app.appointments
        where tenant_id = $1 and status = 'no_show'
          and starts_at >= $2 and starts_at < $3
        group by 1
        order by 1
        """,
        tenant_id, range_start, range_end,
    )
    daily = await conn.fetch(
        """
        select date_trunc('day', created_at)::date as date,
               count(*) as created,
               count(*) filter (where status = 'completed') as completed
        from app.appointments
        where tenant_id = $1 and created_at >= $2 and created_at < $3
        group by 1
        order by 1
        """,
        tenant_id, range_start, range_end,
    )
    return {
        'range': {'from_date': start.isoformat(), 'to_date': end.isoformat()},
        'top_services': [
            {
                'service_key': row['service_key'],
                'service_name': row['service_name'],
                'count': row['count'],
            }
            for row in top_services
        ],
        'status_distribution': [
            {'status': row['status'], 'count': row['count']} for row in statuses
        ],
        'no_shows_by_weekday': [
            {'weekday': row['dow'], 'count': row['count']} for row in no_shows_dow
        ],
        'daily_evolution': [
            {
                'date': row['date'].isoformat(),
                'created': row['created'],
                'completed': row['completed'],
            }
            for row in daily
        ],
    }


@tenant_analytics_router.get('/analytics/contacts')
async def analytics_contacts(
    request: Request,
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    start, end = _resolve_analytics_range(from_date, to_date)
    range_start, range_end = _range_bounds(start, end)

    new_vs_recurring = await conn.fetchrow(
        """
        with new_contacts as (
          select id from app.contacts
          where tenant_id = $1 and created_at >= $2 and created_at < $3
        ), active_contacts as (
          select distinct contact_id as id from app.appointments
          where tenant_id = $1 and created_at >= $2 and created_at < $3
        )
        select
          (select count(*) from new_contacts) as new_count,
          (select count(*) from active_contacts a
             where a.id not in (select id from new_contacts)) as recurring_count
        """,
        tenant_id, range_start, range_end,
    )
    top_tags = await conn.fetch(
        """
        select t.id, t.name, t.color, count(cta.contact_id) as count
        from app.contact_tags t
        left join app.contact_tag_assignments cta on cta.tag_id = t.id and cta.tenant_id = t.tenant_id
        where t.tenant_id = $1
        group by t.id
        order by count desc
        limit 10
        """,
        tenant_id,
    )
    opt_row = await conn.fetchrow(
        """
        select
          count(*) as total,
          count(*) filter (where opt_in_status in ('revoked','suppressed')) as opted_out
        from app.contacts
        where tenant_id = $1
        """,
        tenant_id,
    )
    sources = await conn.fetch(
        """
        select coalesce(source, 'unknown') as source, count(*) as count
        from app.contacts
        where tenant_id = $1
        group by 1
        order by count desc
        """,
        tenant_id,
    )

    total_contacts = opt_row['total'] or 0
    opted_out = opt_row['opted_out'] or 0
    opt_out_rate = (opted_out / total_contacts * 100) if total_contacts else 0.0

    return {
        'range': {'from_date': start.isoformat(), 'to_date': end.isoformat()},
        'new_contacts': new_vs_recurring['new_count'] or 0,
        'recurring_contacts': new_vs_recurring['recurring_count'] or 0,
        'top_tags': [
            {
                'id': str(row['id']),
                'name': row['name'],
                'color': row['color'],
                'count': row['count'],
            }
            for row in top_tags
        ],
        'opt_out_rate_pct': round(opt_out_rate, 2),
        'total_contacts': total_contacts,
        'opted_out': opted_out,
        'source_distribution': [
            {'source': row['source'], 'count': row['count']} for row in sources
        ],
    }


router.include_router(public_router)
router.include_router(webhook_router)
router.include_router(platform_admin_router)
router.include_router(tenant_signup_router)
router.include_router(tenant_user_router)
router.include_router(tenant_admin_router)
router.include_router(tenant_catalog_router)
router.include_router(tenant_ops_router)
router.include_router(tenant_analytics_router)
router.include_router(system_router)
