import asyncio
import csv
import hashlib
import hmac
import io
import json
import secrets
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
    AppointmentPaymentLinkRequest,
    AppointmentPaymentStatusUpdate,
    AppointmentUpdate,
    BranchCreate,
    BranchUpdate,
    CampaignCreate,
    CampaignLaunch,
    CampaignUpdate,
    ChannelCreate,
    ChannelModeUpdate,
    ContactNoteCreate,
    ContactPackageAssign,
    ContactPackagePatch,
    ContactSegmentCreate,
    ContactSegmentMembersAssign,
    ContactSegmentUpdate,
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
    MediaAssetUpdate,
    MemberInvite,
    MemberRoleUpdate,
    MessageCreate,
    PromotionCreate,
    PromotionUpdate,
    PromptCreate,
    QualificationQuestionCreate,
    QualificationQuestionUpdate,
    QualificationReorderRequest,
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
    TenantPaymentSettingsUpdate,
    TenantStatusTransition,
    TenantUpdate,
    TreatmentPackageCreate,
    TreatmentPackageUpdate,
    WebChannelUpsert,
    WebChatMessage,
    WebChatStart,
    WhatsAppTemplateCreate,
    WhatsAppTemplateUpdate,
)
from app.core.config import get_settings
from app.core.security import authenticate_request, require_min_role, require_platform_owner, require_service
from app.db.pool import get_db, record_to_dict
from app.services.audit import audit
from app.services.campaign_attribution import attribute_appointment
from app.services.auth0_admin import (
    assign_roles as auth0_assign_roles,
    auth0_management_enabled,
    invite_user as auth0_invite_user,
    revoke_tenant_roles as auth0_revoke_tenant_roles,
)
from app.services.knowledge_storage import delete_knowledge_file, is_binary_extractable, normalize_object_prefix, store_knowledge_file
from app.services.media_storage import (
    MEDIA_KINDS,
    delete_media_file,
    store_media_file,
)
from app.services.campaigns import (
    count_recipients as count_campaign_recipients,
    evaluate_segment,
    normalize_segment_filter,
    refresh_campaign_counters,
)
from app.services.segments import (
    count_segment_contacts,
    evaluate_segment_rules,
    normalize_rules as normalize_segment_rules,
    seed_preconstructed_segments,
    snapshot_segment_members,
)
from app.services.payment_provider import (
    PaymentProviderError,
    extract_external_ref,
    extract_payment_status,
    generate_payment_link as provider_generate_payment_link,
    normalize_provider as normalize_payment_provider,
    verify_mercadopago_signature,
    verify_stripe_signature,
)
from app.services.notifications import (
    cancel_appointment_reminder_jobs,
    create_appointment_reminder_jobs,
    regenerate_appointment_reminder_jobs,
)
from app.services.rag_indexing import build_indexing_result_async, vector_literal
from app.services.web_widget import (
    build_lead_source,
    constant_time_equals,
    decode_session_token,
    generate_widget_token,
    hash_phone,
    issue_session_token,
    origin_is_allowed,
    synthesize_web_identity,
)
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
    # Validate the prefix against traversal / root-like values. If the stored
    # config has a bad prefix (legacy data or a tenant admin that managed to
    # write '/' before this validation was in place), fall back to the
    # tenant-default rather than let an unrestricted prefix flow into the
    # deletion code path.
    try:
        config['prefix'] = normalize_object_prefix(config.get('prefix'), str(tenant_id))
    except ValueError:
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
    default_lead_source = build_lead_source(channel='whatsapp')
    return await conn.fetchrow(
        """
        insert into app.contacts (tenant_id, wa_id, phone_e164, phone_hash, display_name, source, metadata, lead_source)
        values ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb)
        returning *
        """,
        tenant_id,
        wa_id,
        phone_e164,
        phone_hash,
        display_name,
        source,
        json.dumps(metadata),
        json.dumps(default_lead_source),
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


@public_router.get('/tenants/{tenant_id}/resources/public')
async def list_public_resources(
    tenant_id: UUID,
    conn: asyncpg.Connection = Depends(get_db),
) -> dict[str, Any]:
    """Expose public-facing specialist profiles for the web widget.

    Returns only resources flagged ``public_profile=true`` and ``is_active=true``.
    No auth: the widget snippet renders this client-side. Sensitive fields
    (capabilities, code, license) only surface when explicitly part of the
    public profile.
    """
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        """
        select r.id, r.name, r.specialty, r.bio, r.license_number,
               r.years_of_experience, r.photo_media_asset_id,
               m.source_uri as photo_url,
               m.mime_type as photo_mime_type
        from app.resources r
        left join app.media_assets m
          on m.id = r.photo_media_asset_id and m.tenant_id = r.tenant_id
        where r.tenant_id = $1
          and r.is_active = true
          and r.public_profile = true
        order by r.name asc
        limit 50
        """,
        tenant_id,
    )
    resources = []
    for row in rows:
        resources.append({
            'id': str(row['id']),
            'name': row['name'],
            'specialty': row['specialty'],
            'bio': row['bio'],
            'license_number': row['license_number'],
            'years_of_experience': row['years_of_experience'],
            'photo_url': row['photo_url'],
            'photo_mime_type': row['photo_mime_type'],
        })
    return {'resources': resources}


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
    await seed_preconstructed_segments(conn, tenant_id)
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
    await seed_preconstructed_segments(conn, tenant_id, created_by=user_row['id'])
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
    if 'prefix' in incoming and incoming['prefix'] is not None:
        try:
            incoming['prefix'] = normalize_object_prefix(incoming['prefix'], str(tenant_id))
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail='Invalid knowledge storage prefix',
            )
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


WEB_CHANNEL_PROJECTION = (
    "id, tenant_id, provider, status, account_mode, allowed_origins, widget_config, "
    "token_ref, created_at, updated_at"
)


def _normalize_web_channel(row: asyncpg.Record | None) -> dict[str, Any] | None:
    channel = record_to_dict(row)
    if not channel:
        return None
    channel['allowed_origins'] = list(channel.get('allowed_origins') or [])
    channel['widget_config'] = parse_json_object(channel.get('widget_config'), default={})
    return channel


def _build_widget_snippet(*, tenant_slug: str, widget_token: str, color: str | None, greeting: str | None) -> str:
    attrs = [
        'src="/admin/widget.js"',
        f'data-tenant="{tenant_slug}"',
        f'data-widget-token="{widget_token}"',
    ]
    if color:
        attrs.append(f'data-color="{color}"')
    if greeting:
        safe = greeting.replace('"', '&quot;')
        attrs.append(f'data-greeting="{safe}"')
    return '<script async ' + ' '.join(attrs) + '></script>'


@tenant_admin_router.get('/tenants/{tenant_id}/channels/web')
async def get_web_channel(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow(
        f'select {WEB_CHANNEL_PROJECTION} from app.tenant_channels where tenant_id=$1 and provider=$2',
        tenant_id,
        'web',
    )
    if not row:
        return {'channel': None, 'snippet': None, 'has_widget_token': False}
    channel = _normalize_web_channel(row)
    token_ref = channel.get('token_ref') if channel else None
    widget_token = resolve_secret_ref(token_ref) if token_ref else None
    tenant_slug = await conn.fetchval('select slug from app.tenants where id=$1', tenant_id)
    snippet = _build_widget_snippet(
        tenant_slug=tenant_slug or str(tenant_id),
        widget_token=widget_token or '<missing-widget-token>',
        color=(channel or {}).get('widget_config', {}).get('primary_color'),
        greeting=(channel or {}).get('widget_config', {}).get('greeting'),
    )
    return {
        'channel': channel,
        'snippet': snippet,
        'has_widget_token': bool(widget_token),
        'tenant_slug': tenant_slug,
    }


@tenant_admin_router.put('/tenants/{tenant_id}/channels/web')
async def upsert_web_channel(
    tenant_id: UUID,
    payload: WebChannelUpsert,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    token_ref = tenant_secret_ref(tenant_id, 'widget_token')
    needs_token = payload.rotate_widget_token or not secret_ref_is_configured(token_ref)
    if needs_token:
        new_token = generate_widget_token()
        write_tenant_secret(token_ref, new_token)

    widget_config = {
        'primary_color': payload.primary_color,
        'greeting': payload.greeting,
    }
    next_status = 'active' if payload.enabled else 'suspended'
    cleaned_origins = [origin.strip().rstrip('/') for origin in payload.allowed_origins if origin and origin.strip()]
    row = await conn.fetchrow(
        """
        insert into app.tenant_channels (
          tenant_id, provider, token_ref, account_mode, status, allowed_origins, widget_config
        )
        values ($1, 'web', $2, 'live', $3, $4, $5::jsonb)
        on conflict (tenant_id, provider) do update set
          token_ref=excluded.token_ref,
          status=excluded.status,
          allowed_origins=excluded.allowed_origins,
          widget_config=excluded.widget_config,
          updated_at=now()
        returning """ + WEB_CHANNEL_PROJECTION,
        tenant_id,
        token_ref,
        next_status,
        cleaned_origins,
        json.dumps(widget_config),
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='web_channel.upserted',
        entity_type='tenant_channel',
        entity_id=str(row['id']),
        metadata={
            'enabled': payload.enabled,
            'allowed_origins_count': len(cleaned_origins),
            'widget_token_rotated': needs_token,
        },
    )
    channel = _normalize_web_channel(row)
    widget_token = resolve_secret_ref(token_ref)
    tenant_slug = await conn.fetchval('select slug from app.tenants where id=$1', tenant_id)
    snippet = _build_widget_snippet(
        tenant_slug=tenant_slug or str(tenant_id),
        widget_token=widget_token or '',
        color=widget_config.get('primary_color'),
        greeting=widget_config.get('greeting'),
    )
    return {
        'channel': channel,
        'snippet': snippet,
        'has_widget_token': bool(widget_token),
        'tenant_slug': tenant_slug,
    }


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


# ───── Branches (TASK-0050) ────────────────────────────────────────────────


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


@tenant_admin_router.post('/branches', status_code=201)
async def create_branch(payload: BranchCreate, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    tenant_id = await tenant_id_from_request(request, conn)
    try:
        row = await conn.fetchrow(
            """
            insert into app.branches (
                tenant_id, name, code, address, city, state, country,
                lat, lng, maps_url, phone_e164, timezone, opening_hours,
                is_active, sort_order
            )
            values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13::jsonb,$14,$15)
            returning *
            """,
            tenant_id,
            payload.name,
            payload.code,
            payload.address,
            payload.city,
            payload.state,
            payload.country,
            payload.lat,
            payload.lng,
            payload.maps_url,
            payload.phone_e164,
            payload.timezone,
            json.dumps(payload.opening_hours),
            payload.is_active,
            payload.sort_order,
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail='Branch code already exists for tenant') from exc
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='branch.created',
        entity_type='branch',
        entity_id=str(row['id']),
    )
    return record_to_dict(row)


@tenant_admin_router.patch('/branches/{branch_id}')
async def update_branch(branch_id: UUID, payload: BranchUpdate, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    tenant_id = await tenant_id_from_request(request, conn)
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        row = await conn.fetchrow('select * from app.branches where tenant_id=$1 and id=$2', tenant_id, branch_id)
        if not row:
            raise HTTPException(status_code=404, detail='Branch not found')
        return record_to_dict(row)
    try:
        row = await conn.fetchrow(
            """
            update app.branches
            set name=coalesce($3, name),
                code=coalesce($4, code),
                address=case when $14::boolean then $5 else address end,
                city=case when $15::boolean then $6 else city end,
                state=case when $16::boolean then $7 else state end,
                country=coalesce($8, country),
                lat=case when $17::boolean then $9 else lat end,
                lng=case when $18::boolean then $10 else lng end,
                maps_url=case when $19::boolean then $11 else maps_url end,
                phone_e164=case when $20::boolean then $12 else phone_e164 end,
                timezone=coalesce($13, timezone),
                opening_hours=coalesce($21::jsonb, opening_hours),
                is_active=coalesce($22, is_active),
                sort_order=coalesce($23, sort_order)
            where tenant_id=$1 and id=$2
            returning *
            """,
            tenant_id,
            branch_id,
            update_data.get('name'),
            update_data.get('code'),
            update_data.get('address'),
            update_data.get('city'),
            update_data.get('state'),
            update_data.get('country'),
            update_data.get('lat'),
            update_data.get('lng'),
            update_data.get('maps_url'),
            update_data.get('phone_e164'),
            update_data.get('timezone'),
            'address' in update_data,
            'city' in update_data,
            'state' in update_data,
            'lat' in update_data,
            'lng' in update_data,
            'maps_url' in update_data,
            'phone_e164' in update_data,
            json.dumps(update_data['opening_hours']) if 'opening_hours' in update_data else None,
            update_data.get('is_active'),
            update_data.get('sort_order'),
        )
    except asyncpg.UniqueViolationError as exc:
        raise HTTPException(status_code=409, detail='Branch code already exists for tenant') from exc
    if not row:
        raise HTTPException(status_code=404, detail='Branch not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='branch.updated',
        entity_type='branch',
        entity_id=str(branch_id),
    )
    return record_to_dict(row)


@tenant_admin_router.delete('/branches/{branch_id}', status_code=204)
async def deactivate_branch(branch_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)):
    tenant_id = await tenant_id_from_request(request, conn)
    row = await conn.fetchrow(
        """
        update app.branches
        set is_active=false
        where tenant_id=$1 and id=$2
        returning id
        """,
        tenant_id,
        branch_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Branch not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='branch.deleted',
        entity_type='branch',
        entity_id=str(branch_id),
    )
    return Response(status_code=204)


# ───── Treatment packages (TASK-0051) ──────────────────────────────────────


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


@tenant_admin_router.post('/packages', status_code=201)
async def create_treatment_package(
    payload: TreatmentPackageCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    if payload.renewal_template_id is not None:
        owns = await conn.fetchval(
            'select 1 from app.whatsapp_templates where tenant_id=$1 and id=$2',
            tenant_id,
            payload.renewal_template_id,
        )
        if not owns:
            raise HTTPException(status_code=400, detail='renewal_template_id not found for tenant')
    row = await conn.fetchrow(
        """
        insert into app.treatment_packages (
            tenant_id, name, description, total_sessions, validity_days,
            price_amount, price_currency, includes_service_ids,
            renewal_template_id, is_active, sort_order, metadata
        )
        values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12::jsonb)
        returning *
        """,
        tenant_id,
        payload.name,
        payload.description,
        payload.total_sessions,
        payload.validity_days,
        payload.price_amount,
        payload.price_currency,
        [str(s) for s in payload.includes_service_ids],
        payload.renewal_template_id,
        payload.is_active,
        payload.sort_order,
        json.dumps(payload.metadata),
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='package.created',
        entity_type='treatment_package',
        entity_id=str(row['id']),
    )
    return record_to_dict(row)


@tenant_admin_router.patch('/packages/{package_id}')
async def update_treatment_package(
    package_id: UUID,
    payload: TreatmentPackageUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        row = await conn.fetchrow(
            'select * from app.treatment_packages where tenant_id=$1 and id=$2',
            tenant_id,
            package_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail='Package not found')
        return record_to_dict(row)
    if 'renewal_template_id' in update_data and update_data['renewal_template_id'] is not None:
        owns = await conn.fetchval(
            'select 1 from app.whatsapp_templates where tenant_id=$1 and id=$2',
            tenant_id,
            update_data['renewal_template_id'],
        )
        if not owns:
            raise HTTPException(status_code=400, detail='renewal_template_id not found for tenant')
    row = await conn.fetchrow(
        """
        update app.treatment_packages
        set name=coalesce($3, name),
            description=case when $13::boolean then $4 else description end,
            total_sessions=coalesce($5, total_sessions),
            validity_days=case when $14::boolean then $6 else validity_days end,
            price_amount=coalesce($7, price_amount),
            price_currency=coalesce($8, price_currency),
            includes_service_ids=coalesce($9, includes_service_ids),
            renewal_template_id=case when $15::boolean then $10 else renewal_template_id end,
            is_active=coalesce($11, is_active),
            sort_order=coalesce($12, sort_order),
            metadata=coalesce($16::jsonb, metadata)
        where tenant_id=$1 and id=$2
        returning *
        """,
        tenant_id,
        package_id,
        update_data.get('name'),
        update_data.get('description'),
        update_data.get('total_sessions'),
        update_data.get('validity_days'),
        update_data.get('price_amount'),
        update_data.get('price_currency'),
        [str(s) for s in update_data['includes_service_ids']] if 'includes_service_ids' in update_data else None,
        update_data.get('renewal_template_id'),
        update_data.get('is_active'),
        update_data.get('sort_order'),
        'description' in update_data,
        'validity_days' in update_data,
        'renewal_template_id' in update_data,
        json.dumps(update_data['metadata']) if 'metadata' in update_data else None,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Package not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='package.updated',
        entity_type='treatment_package',
        entity_id=str(package_id),
    )
    return record_to_dict(row)


@tenant_admin_router.delete('/packages/{package_id}', status_code=204)
async def deactivate_treatment_package(
    package_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    row = await conn.fetchrow(
        """
        update app.treatment_packages
        set is_active=false
        where tenant_id=$1 and id=$2
        returning id
        """,
        tenant_id,
        package_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Package not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='package.deleted',
        entity_type='treatment_package',
        entity_id=str(package_id),
    )
    return Response(status_code=204)


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


@tenant_ops_router.post('/contacts/{contact_id}/packages', status_code=201)
async def assign_contact_package(
    contact_id: UUID,
    payload: ContactPackageAssign,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    pkg = await conn.fetchrow(
        """
        select id, total_sessions, validity_days, price_amount, price_currency
        from app.treatment_packages
        where tenant_id=$1 and id=$2 and is_active=true
        """,
        tenant_id,
        payload.package_id,
    )
    if not pkg:
        raise HTTPException(status_code=404, detail='Package not found or inactive')
    contact = await conn.fetchval(
        'select 1 from app.contacts where tenant_id=$1 and id=$2',
        tenant_id,
        contact_id,
    )
    if not contact:
        raise HTTPException(status_code=404, detail='Contact not found')
    expires_at = payload.expires_at
    if expires_at is None and pkg['validity_days']:
        expires_at = datetime.now(UTC) + timedelta(days=int(pkg['validity_days']))
    payment_amount = payload.payment_amount if payload.payment_amount is not None else float(pkg['price_amount'])
    currency = payload.payment_currency or pkg['price_currency']
    row = await conn.fetchrow(
        """
        insert into app.contact_packages (
            tenant_id, contact_id, package_id, expires_at,
            remaining_sessions, total_sessions, payment_status,
            payment_amount, payment_currency, notes
        )
        values ($1,$2,$3,$4,$5,$5,$6,$7,$8,$9)
        returning *
        """,
        tenant_id,
        contact_id,
        payload.package_id,
        expires_at,
        pkg['total_sessions'],
        payload.payment_status,
        payment_amount,
        currency,
        payload.notes,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='contact_package.assigned',
        entity_type='contact_package',
        entity_id=str(row['id']),
        metadata={'package_id': str(payload.package_id), 'contact_id': str(contact_id)},
    )
    return record_to_dict(row)


@tenant_ops_router.patch('/contacts/{contact_id}/packages/{contact_package_id}')
async def update_contact_package(
    contact_id: UUID,
    contact_package_id: UUID,
    payload: ContactPackagePatch,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    tenant_id = await tenant_id_from_request(request, conn)
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        row = await conn.fetchrow(
            'select * from app.contact_packages where tenant_id=$1 and contact_id=$2 and id=$3',
            tenant_id,
            contact_id,
            contact_package_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail='Contact package not found')
        return record_to_dict(row)
    row = await conn.fetchrow(
        """
        update app.contact_packages
        set payment_status=coalesce($4, payment_status),
            payment_amount=case when $9::boolean then $5 else payment_amount end,
            payment_currency=coalesce($6, payment_currency),
            expires_at=case when $10::boolean then $7 else expires_at end,
            status=coalesce($8, status),
            notes=case when $11::boolean then $12 else notes end
        where tenant_id=$1 and contact_id=$2 and id=$3
        returning *
        """,
        tenant_id,
        contact_id,
        contact_package_id,
        update_data.get('payment_status'),
        update_data.get('payment_amount'),
        update_data.get('payment_currency'),
        update_data.get('expires_at'),
        update_data.get('status'),
        'payment_amount' in update_data,
        'expires_at' in update_data,
        'notes' in update_data,
        update_data.get('notes'),
    )
    if not row:
        raise HTTPException(status_code=404, detail='Contact package not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='contact_package.updated',
        entity_type='contact_package',
        entity_id=str(contact_package_id),
    )
    return record_to_dict(row)


@tenant_ops_router.delete('/contacts/{contact_id}/packages/{contact_package_id}', status_code=204)
async def refund_contact_package(
    contact_id: UUID,
    contact_package_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    """Mark a contact package as refunded.

    Sets status=refunded, payment_status=refunded, and zeroes the remaining
    sessions so the booking flow no longer offers them. Existing
    appointment_package_links are preserved for audit, but the package is no
    longer 'active'.
    """
    tenant_id = await tenant_id_from_request(request, conn)
    row = await conn.fetchrow(
        """
        update app.contact_packages
        set status='refunded',
            payment_status='refunded',
            remaining_sessions=0
        where tenant_id=$1 and contact_id=$2 and id=$3
        returning id
        """,
        tenant_id,
        contact_id,
        contact_package_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Contact package not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='contact_package.refunded',
        entity_type='contact_package',
        entity_id=str(contact_package_id),
    )
    return Response(status_code=204)


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
    'recall_interval_days',
    'recall_template_id',
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
          duration_minutes, preparation_notes, post_service_notes,
          recall_interval_days, recall_template_id,
          is_active, sort_order, metadata
        )
        values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14::jsonb)
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
        payload.recall_interval_days,
        payload.recall_template_id,
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
    # TASK-0052: recall_interval_days / recall_template_id can be cleared back
    # to null. We pass a "<field>_set" flag so SQL knows whether the caller
    # really sent the field (clear) vs. omitted it (keep current).
    recall_days_set = 'recall_interval_days' in update_data
    recall_template_set = 'recall_template_id' in update_data
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
            recall_interval_days = case when $14::boolean then $15 else recall_interval_days end,
            recall_template_id   = case when $16::boolean then $17 else recall_template_id end,
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
        recall_days_set,
        update_data.get('recall_interval_days'),
        recall_template_set,
        update_data.get('recall_template_id'),
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


# ── Qualification questions (TASK-0042) ─────────────────────────────────────
QUALIFICATION_PROJECTION = (
    'id, tenant_id, position, label, kind, options, required, '
    'applies_to_service_ids, created_at, updated_at'
)


def normalize_qualification_question(row: asyncpg.Record | None) -> dict | None:
    question = record_to_dict(row)
    if not question:
        return None
    options = question.get('options')
    if isinstance(options, str):
        try:
            question['options'] = json.loads(options)
        except json.JSONDecodeError:
            question['options'] = []
    elif not isinstance(options, list):
        question['options'] = []
    applies = question.get('applies_to_service_ids') or []
    question['applies_to_service_ids'] = [str(item) for item in applies]
    return question


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


@tenant_admin_router.post(
    '/tenants/{tenant_id}/qualification-questions', status_code=201
)
async def create_qualification_question(
    tenant_id: UUID,
    payload: QualificationQuestionCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    options_json = json.dumps([o.model_dump(mode='json') for o in payload.options])
    applies = [str(sid) for sid in payload.applies_to_service_ids]
    row = await conn.fetchrow(
        f"""
        insert into app.qualification_questions (
          tenant_id, position, label, kind, options, required, applies_to_service_ids
        )
        values ($1, $2, $3, $4, $5::jsonb, $6, $7::uuid[])
        returning {QUALIFICATION_PROJECTION}
        """,
        tenant_id,
        payload.position,
        payload.label,
        payload.kind,
        options_json,
        payload.required,
        applies,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='qualification.created',
        entity_type='qualification_question',
        entity_id=str(row['id']),
        metadata={'label': payload.label, 'kind': payload.kind},
    )
    return normalize_qualification_question(row)


@tenant_admin_router.patch(
    '/tenants/{tenant_id}/qualification-questions/{question_id}'
)
async def update_qualification_question(
    tenant_id: UUID,
    question_id: UUID,
    payload: QualificationQuestionUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        row = await conn.fetchrow(
            f'select {QUALIFICATION_PROJECTION} from app.qualification_questions '
            'where tenant_id=$1 and id=$2',
            tenant_id,
            question_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail='Question not found')
        return normalize_qualification_question(row)
    options_json = (
        json.dumps([o.model_dump(mode='json') for o in payload.options])
        if payload.options is not None
        else None
    )
    applies = (
        [str(sid) for sid in payload.applies_to_service_ids]
        if payload.applies_to_service_ids is not None
        else None
    )
    row = await conn.fetchrow(
        f"""
        update app.qualification_questions
        set label=coalesce($3, label),
            kind=coalesce($4, kind),
            options=coalesce($5::jsonb, options),
            required=coalesce($6, required),
            position=coalesce($7, position),
            applies_to_service_ids=coalesce($8::uuid[], applies_to_service_ids)
        where tenant_id=$1 and id=$2
        returning {QUALIFICATION_PROJECTION}
        """,
        tenant_id,
        question_id,
        updates.get('label'),
        updates.get('kind'),
        options_json,
        updates.get('required'),
        updates.get('position'),
        applies,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Question not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='qualification.updated',
        entity_type='qualification_question',
        entity_id=str(question_id),
    )
    return normalize_qualification_question(row)


@tenant_admin_router.delete(
    '/tenants/{tenant_id}/qualification-questions/{question_id}', status_code=204
)
async def delete_qualification_question(
    tenant_id: UUID,
    question_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    deleted = await conn.fetchval(
        'delete from app.qualification_questions where tenant_id=$1 and id=$2 returning id',
        tenant_id,
        question_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail='Question not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='qualification.deleted',
        entity_type='qualification_question',
        entity_id=str(question_id),
    )
    return Response(status_code=204)


@tenant_admin_router.post('/tenants/{tenant_id}/qualification-questions/reorder')
async def reorder_qualification_questions(
    tenant_id: UUID,
    payload: QualificationReorderRequest,
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
                update app.qualification_questions
                set position=$3
                where tenant_id=$1 and id=$2
                """,
                tenant_id,
                item.id,
                item.position,
            )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='qualification.reordered',
        entity_type='qualification_question',
        entity_id=str(tenant_id),
    )
    return {'updated': len(payload.order)}


# ── Media library + promotions (TASK-0046) ─────────────────────────────────
MEDIA_ASSET_COLUMNS = (
    'id, tenant_id, kind, label, description, storage_backend, storage_bucket, '
    'object_key, source_uri, mime_type, sha256, size_bytes, tags, '
    'uploaded_by_user_id, created_at, updated_at'
)
PROMOTION_COLUMNS = (
    'id, tenant_id, name, description, media_asset_id, valid_from, valid_until, '
    'applies_to_service_ids, coupon_code, discount_percent, is_active, '
    'sort_order, created_at, updated_at'
)


def normalize_media_asset(row: asyncpg.Record | None) -> dict | None:
    asset = record_to_dict(row)
    if not asset:
        return None
    asset['tags'] = list(asset.get('tags') or [])
    return asset


def normalize_promotion(row: asyncpg.Record | None) -> dict | None:
    promo = record_to_dict(row)
    if not promo:
        return None
    promo['applies_to_service_ids'] = [str(s) for s in (promo.get('applies_to_service_ids') or [])]
    if promo.get('discount_percent') is not None:
        promo['discount_percent'] = float(promo['discount_percent'])
    return promo


@tenant_admin_router.get('/tenants/{tenant_id}/media')
async def list_media_assets(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    kind: str | None = Query(default=None),
    tag: str | None = Query(default=None),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    if kind is not None and kind not in MEDIA_KINDS:
        raise HTTPException(status_code=422, detail='Unsupported media kind')
    rows = await conn.fetch(
        f"""
        select {MEDIA_ASSET_COLUMNS}
        from app.media_assets
        where tenant_id = $1
          and ($2::text is null or kind = $2)
          and ($3::text is null or $3 = any(tags))
        order by created_at desc
        """,
        tenant_id,
        kind,
        tag,
    )
    return [normalize_media_asset(row) for row in rows]


@tenant_admin_router.post('/tenants/{tenant_id}/media', status_code=201)
async def upload_media_asset(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    try:
        form = await request.form()
    except AssertionError as exc:
        raise HTTPException(
            status_code=500, detail='python-multipart dependency is required for file uploads'
        ) from exc
    kind = str(form.get('kind') or '').strip()
    label = str(form.get('label') or '').strip()
    description = form.get('description')
    description_text = str(description).strip() if description else None
    raw_tags = form.get('tags')
    tags: list[str] = []
    if raw_tags:
        tags = [t.strip() for t in str(raw_tags).split(',') if t.strip()]
    file = form.get('file')
    if kind not in MEDIA_KINDS:
        raise HTTPException(status_code=422, detail='kind must be one of image|video|pdf|audio')
    if not label:
        raise HTTPException(status_code=422, detail='label is required')
    if not file or not hasattr(file, 'read'):
        raise HTTPException(status_code=422, detail='file is required')

    data = await file.read()
    filename = getattr(file, 'filename', None) or 'media.bin'
    mime_type = getattr(file, 'content_type', None)
    asset_id = uuid4()
    settings = get_settings()
    try:
        stored = store_media_file(
            data=data,
            tenant_id=str(tenant_id),
            asset_id=str(asset_id),
            kind=kind,
            filename=filename,
            mime_type=mime_type,
            settings=settings,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    uploader_id = await current_user_id_from_request(request, conn)
    row = await conn.fetchrow(
        f"""
        insert into app.media_assets (
          id, tenant_id, kind, label, description,
          storage_backend, storage_bucket, object_key, source_uri,
          mime_type, sha256, size_bytes, tags, uploaded_by_user_id
        )
        values ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13::text[], $14)
        returning {MEDIA_ASSET_COLUMNS}
        """,
        asset_id,
        tenant_id,
        kind,
        label,
        description_text,
        stored.storage_backend,
        stored.bucket,
        stored.object_key,
        stored.source_uri,
        stored.mime_type,
        stored.sha256,
        stored.size_bytes,
        tags,
        uploader_id,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='media_asset.created',
        entity_type='media_asset',
        entity_id=str(asset_id),
        metadata={'kind': kind, 'size_bytes': stored.size_bytes, 'label': label},
    )
    return normalize_media_asset(row)


@tenant_admin_router.patch('/tenants/{tenant_id}/media/{asset_id}')
async def update_media_asset(
    tenant_id: UUID,
    asset_id: UUID,
    payload: MediaAssetUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        row = await conn.fetchrow(
            f'select {MEDIA_ASSET_COLUMNS} from app.media_assets where tenant_id=$1 and id=$2',
            tenant_id,
            asset_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail='Media asset not found')
        return normalize_media_asset(row)
    row = await conn.fetchrow(
        f"""
        update app.media_assets
        set label=coalesce($3, label),
            description=coalesce($4, description),
            tags=coalesce($5::text[], tags)
        where tenant_id=$1 and id=$2
        returning {MEDIA_ASSET_COLUMNS}
        """,
        tenant_id,
        asset_id,
        updates.get('label'),
        updates.get('description'),
        updates.get('tags'),
    )
    if not row:
        raise HTTPException(status_code=404, detail='Media asset not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='media_asset.updated',
        entity_type='media_asset',
        entity_id=str(asset_id),
    )
    return normalize_media_asset(row)


@tenant_admin_router.delete('/tenants/{tenant_id}/media/{asset_id}', status_code=204)
async def delete_media_asset(
    tenant_id: UUID,
    asset_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await conn.fetchrow(
        """
        select storage_backend, storage_bucket, object_key, source_uri
        from app.media_assets
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        asset_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Media asset not found')
    settings = get_settings()
    delete_media_file(
        storage_backend=row['storage_backend'],
        object_key=row['object_key'],
        source_uri=row['source_uri'],
        bucket=row['storage_bucket'],
        settings=settings,
    )
    await conn.execute(
        'delete from app.media_assets where tenant_id=$1 and id=$2',
        tenant_id,
        asset_id,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='media_asset.deleted',
        entity_type='media_asset',
        entity_id=str(asset_id),
    )
    return Response(status_code=204)


@tenant_admin_router.get('/tenants/{tenant_id}/promotions')
async def list_promotions(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    include_inactive: bool = Query(default=True),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        f"""
        select {PROMOTION_COLUMNS}
        from app.promotions
        where tenant_id=$1
          and ($2::boolean is true or is_active is true)
        order by sort_order asc, created_at desc
        """,
        tenant_id,
        include_inactive,
    )
    return [normalize_promotion(row) for row in rows]


@tenant_admin_router.post('/tenants/{tenant_id}/promotions', status_code=201)
async def create_promotion(
    tenant_id: UUID,
    payload: PromotionCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    if payload.media_asset_id:
        owns = await conn.fetchval(
            'select 1 from app.media_assets where tenant_id=$1 and id=$2',
            tenant_id,
            payload.media_asset_id,
        )
        if not owns:
            raise HTTPException(status_code=422, detail='media_asset_id does not belong to this tenant')
    if payload.valid_from and payload.valid_until and payload.valid_from > payload.valid_until:
        raise HTTPException(status_code=422, detail='valid_from must be <= valid_until')
    applies = [str(sid) for sid in payload.applies_to_service_ids]
    row = await conn.fetchrow(
        f"""
        insert into app.promotions (
          tenant_id, name, description, media_asset_id, valid_from, valid_until,
          applies_to_service_ids, coupon_code, discount_percent, is_active, sort_order
        )
        values ($1, $2, $3, $4, $5, $6, $7::uuid[], $8, $9, $10, $11)
        returning {PROMOTION_COLUMNS}
        """,
        tenant_id,
        payload.name,
        payload.description,
        payload.media_asset_id,
        payload.valid_from,
        payload.valid_until,
        applies,
        payload.coupon_code,
        payload.discount_percent,
        payload.is_active,
        payload.sort_order,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='promotion.created',
        entity_type='promotion',
        entity_id=str(row['id']),
        metadata={'name': payload.name},
    )
    return normalize_promotion(row)


@tenant_admin_router.patch('/tenants/{tenant_id}/promotions/{promotion_id}')
async def update_promotion(
    tenant_id: UUID,
    promotion_id: UUID,
    payload: PromotionUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        row = await conn.fetchrow(
            f'select {PROMOTION_COLUMNS} from app.promotions where tenant_id=$1 and id=$2',
            tenant_id,
            promotion_id,
        )
        if not row:
            raise HTTPException(status_code=404, detail='Promotion not found')
        return normalize_promotion(row)
    if 'media_asset_id' in updates and updates['media_asset_id']:
        owns = await conn.fetchval(
            'select 1 from app.media_assets where tenant_id=$1 and id=$2',
            tenant_id,
            updates['media_asset_id'],
        )
        if not owns:
            raise HTTPException(status_code=422, detail='media_asset_id does not belong to this tenant')
    applies = (
        [str(sid) for sid in payload.applies_to_service_ids]
        if payload.applies_to_service_ids is not None
        else None
    )
    row = await conn.fetchrow(
        f"""
        update app.promotions
        set name=coalesce($3, name),
            description=coalesce($4, description),
            media_asset_id=coalesce($5, media_asset_id),
            valid_from=coalesce($6, valid_from),
            valid_until=coalesce($7, valid_until),
            applies_to_service_ids=coalesce($8::uuid[], applies_to_service_ids),
            coupon_code=coalesce($9, coupon_code),
            discount_percent=coalesce($10, discount_percent),
            is_active=coalesce($11, is_active),
            sort_order=coalesce($12, sort_order)
        where tenant_id=$1 and id=$2
        returning {PROMOTION_COLUMNS}
        """,
        tenant_id,
        promotion_id,
        updates.get('name'),
        updates.get('description'),
        updates.get('media_asset_id'),
        updates.get('valid_from'),
        updates.get('valid_until'),
        applies,
        updates.get('coupon_code'),
        updates.get('discount_percent'),
        updates.get('is_active'),
        updates.get('sort_order'),
    )
    if not row:
        raise HTTPException(status_code=404, detail='Promotion not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='promotion.updated',
        entity_type='promotion',
        entity_id=str(promotion_id),
    )
    return normalize_promotion(row)


@tenant_admin_router.delete('/tenants/{tenant_id}/promotions/{promotion_id}', status_code=204)
async def delete_promotion(
    tenant_id: UUID,
    promotion_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    deleted = await conn.fetchval(
        'delete from app.promotions where tenant_id=$1 and id=$2 returning id',
        tenant_id,
        promotion_id,
    )
    if not deleted:
        raise HTTPException(status_code=404, detail='Promotion not found')
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='promotion.deleted',
        entity_type='promotion',
        entity_id=str(promotion_id),
    )
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
    branch_id: UUID | None = Query(default=None),
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
          and ($4::uuid is null or a.branch_id=$4)
        order by a.starts_at desc
        limit 250
        """,
        tenant_id,
        resource_id,
        status_filter,
        branch_id,
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


def _normalize_payment_settings(value: Any) -> dict[str, Any]:
    """Read tenant payment_settings jsonb into a dict with predictable keys."""
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            value = {}
    if not isinstance(value, dict):
        value = {}
    provider = value.get('provider') or 'none'
    if provider not in {'mercadopago', 'stripe', 'none'}:
        provider = 'none'
    return {
        'provider': provider,
        'currency': (value.get('currency') or 'COP').upper()[:3],
        'default_amount': value.get('default_amount'),
        'api_key_ref': value.get('api_key_ref'),
        'webhook_secret_ref': value.get('webhook_secret_ref'),
    }


def _public_payment_settings(tenant_id: UUID, settings: dict[str, Any]) -> dict[str, Any]:
    """Strip secrets from payment settings before returning them to the panel."""
    normalized = _normalize_payment_settings(settings)
    return {
        'provider': normalized['provider'],
        'currency': normalized['currency'],
        'default_amount': normalized['default_amount'],
        'api_key_configured': secret_ref_is_configured(normalized['api_key_ref']),
        'webhook_secret_configured': secret_ref_is_configured(normalized['webhook_secret_ref']),
        'tenant_id': str(tenant_id),
    }


async def _fetch_tenant_payment_settings(
    conn: asyncpg.Connection, tenant_id: UUID
) -> dict[str, Any]:
    value = await conn.fetchval(
        'select payment_settings from app.tenant_settings where tenant_id=$1', tenant_id
    )
    return _normalize_payment_settings(value)


@tenant_admin_router.get('/tenants/{tenant_id}/payments/settings')
async def get_tenant_payment_settings(
    tenant_id: UUID, request: Request, conn: asyncpg.Connection = Depends(get_db)
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    settings = await _fetch_tenant_payment_settings(conn, tenant_id)
    return _public_payment_settings(tenant_id, settings)


@tenant_admin_router.put('/tenants/{tenant_id}/payments/settings')
async def update_tenant_payment_settings(
    tenant_id: UUID,
    payload: TenantPaymentSettingsUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    current = await _fetch_tenant_payment_settings(conn, tenant_id)
    next_settings = {
        **current,
        'provider': payload.provider,
        'currency': payload.currency.upper(),
        'default_amount': payload.default_amount,
    }
    api_key_value = (payload.api_key or '').strip()
    if api_key_value:
        ref = tenant_secret_ref(tenant_id, 'payment_api_key')
        write_tenant_secret(ref, api_key_value)
        next_settings['api_key_ref'] = ref
    elif payload.provider == 'none':
        next_settings['api_key_ref'] = None
    webhook_secret_value = (payload.webhook_secret or '').strip()
    if webhook_secret_value:
        ref = tenant_secret_ref(tenant_id, 'payment_webhook_secret')
        write_tenant_secret(ref, webhook_secret_value)
        next_settings['webhook_secret_ref'] = ref
    elif payload.provider == 'none':
        next_settings['webhook_secret_ref'] = None
    if payload.provider != 'none' and not next_settings.get('webhook_secret_ref'):
        raise HTTPException(
            status_code=422,
            detail='Webhook signing secret is required to enable a payment provider',
        )
    await conn.execute(
        """
        update app.tenant_settings
        set payment_settings=$2::jsonb, updated_at=now()
        where tenant_id=$1
        """,
        tenant_id,
        json.dumps(next_settings),
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='tenant_payment_settings.updated',
        entity_type='tenant_settings',
        entity_id=str(tenant_id),
        metadata={'provider': next_settings['provider']},
    )
    return _public_payment_settings(tenant_id, next_settings)


def _appointment_payment_external_ref(tenant_id: UUID, appointment_id: UUID) -> str:
    return f'tenant:{tenant_id}:appointment:{appointment_id}'


def _parse_appointment_external_ref(ref: str | None) -> UUID | None:
    if not ref:
        return None
    tokens = ref.split(':')
    for index, token in enumerate(tokens):
        if token == 'appointment' and index + 1 < len(tokens):
            try:
                return UUID(tokens[index + 1])
            except ValueError:
                return None
    return None


def _appointment_payment_summary(row: asyncpg.Record) -> dict[str, Any]:
    appointment = record_to_dict(row)
    return {
        'appointment_id': appointment.get('id'),
        'payment_status': appointment.get('payment_status'),
        'payment_amount': appointment.get('payment_amount'),
        'payment_currency': appointment.get('payment_currency'),
        'payment_link': appointment.get('payment_link'),
        'payment_provider': appointment.get('payment_provider'),
        'payment_provider_reference': appointment.get('payment_provider_reference'),
        'payment_link_generated_at': appointment.get('payment_link_generated_at'),
        'payment_link_sent_at': appointment.get('payment_link_sent_at'),
        'payment_paid_at': appointment.get('payment_paid_at'),
    }


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


@webhook_router.post('/payments/{provider}', status_code=202)
async def receive_payment_webhook(
    provider: str,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    try:
        normalized_provider = normalize_payment_provider(provider)
    except PaymentProviderError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if normalized_provider == 'none':
        raise HTTPException(status_code=404, detail='Unknown payment provider')
    body = await request.body()
    try:
        payload = json.loads(body or b'{}')
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail='Invalid payment webhook payload') from exc

    external_ref = extract_external_ref(normalized_provider, payload)
    appointment_id = _parse_appointment_external_ref(external_ref)
    if not appointment_id:
        raise HTTPException(status_code=400, detail='Payment webhook payload missing external_reference')

    await conn.execute("select set_config('app.support_mode', 'true', true)")
    appointment = await conn.fetchrow(
        'select tenant_id, id, conversation_id, contact_id from app.appointments where id=$1',
        appointment_id,
    )
    if not appointment:
        raise HTTPException(status_code=404, detail='Appointment not found for payment webhook')
    tenant_id = appointment['tenant_id']
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    payment_settings = await _fetch_tenant_payment_settings(conn, tenant_id)
    secret = resolve_secret_ref(payment_settings.get('webhook_secret_ref'))
    if not secret:
        raise HTTPException(
            status_code=401,
            detail='Payment webhook signing secret is not configured for this tenant',
        )
    if normalized_provider == 'mercadopago':
        sig_header = request.headers.get('x-signature')
        request_id = request.headers.get('x-request-id')
        data_id = None
        data = payload.get('data') if isinstance(payload, dict) else None
        if isinstance(data, dict):
            data_id = data.get('id')
        signature_ok = verify_mercadopago_signature(
            body, sig_header, secret, request_id=request_id, data_id=str(data_id) if data_id else None,
        )
    else:
        sig_header = request.headers.get('stripe-signature')
        signature_ok = verify_stripe_signature(body, sig_header, secret)
    if not signature_ok:
        raise HTTPException(status_code=401, detail='Invalid payment webhook signature')

    sha = hashlib.sha256(body).hexdigest()
    await conn.execute(
        """
        insert into app.webhook_events_raw (tenant_id, provider, event_type, headers, payload, payload_sha256)
        values ($1, $2, $3, $4::jsonb, $5::jsonb, $6)
        on conflict (payload_sha256) do nothing
        """,
        tenant_id,
        normalized_provider,
        str(payload.get('type') or payload.get('action') or 'payment'),
        json.dumps(dict(request.headers)),
        json.dumps(payload),
        sha,
    )

    new_status = extract_payment_status(normalized_provider, payload)
    if not new_status:
        return {'status': 'ignored', 'reason': 'no_status_mapped'}

    row = await conn.fetchrow(
        """
        update app.appointments
        set payment_status=$3,
            payment_paid_at=case when $3='paid' then now() else payment_paid_at end
        where tenant_id=$1 and id=$2
        returning *
        """,
        tenant_id,
        appointment_id,
        new_status,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type='service',
        actor_id=f'payment_provider:{normalized_provider}',
        action='appointment.payment_webhook',
        entity_type='appointment',
        entity_id=str(appointment_id),
        metadata={'payment_status': new_status, 'provider': normalized_provider},
    )

    if new_status == 'paid' and appointment['conversation_id']:
        confirmation_text = '✅ Pago recibido. Tu cita queda confirmada.'
        message = await conn.fetchrow(
            """
            insert into app.messages
              (tenant_id, conversation_id, direction, sender_actor_type, body_text, message_type, payload, status)
            values ($1,$2,'outbound','system',$3,'text','{}','queued')
            returning id
            """,
            tenant_id,
            appointment['conversation_id'],
            confirmation_text,
        )
        await conn.execute(
            "insert into app.domain_events (tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key, payload) values ($1,'message',$2,'message.queued',$3,$4::jsonb) on conflict do nothing",
            tenant_id,
            message['id'],
            f'payment-confirmation-{appointment_id}',
            json.dumps({'conversation_id': str(appointment['conversation_id']), 'appointment_id': str(appointment_id)}),
        )

    return _appointment_payment_summary(row)


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

    # Delete physical file from local disk or S3.
    # NOTE: source_uri and metadata.* are tenant-admin-writable via the
    # create/patch APIs, so they cannot be trusted to determine the deletion
    # target. The storage backend, bucket, and tenant prefix are re-derived
    # from server-controlled tenant configuration and passed to
    # delete_knowledge_file(), which enforces containment of the target path
    # under the tenant's storage region before unlinking / deleting.
    storage_meta = _coerce_jsonb(doc['metadata']) or {}
    settings = get_settings()
    storage_config = await fetch_tenant_knowledge_storage_config(conn, tenant_id)
    storage_secret = (
        resolve_secret_ref(storage_config.get('secret_ref'))
        if storage_config.get('backend') == 's3' and storage_config.get('secret_ref')
        else None
    )
    trusted_backend = (storage_config.get('backend') or settings.knowledge_storage_backend)
    trusted_bucket = storage_config.get('bucket') or settings.knowledge_storage_bucket
    trusted_prefix = storage_config.get('prefix') or f'tenants/{tenant_id}/knowledge'
    delete_knowledge_file(
        source_uri=doc['source_uri'] or '',
        storage_backend=trusted_backend,
        object_key=storage_meta.get('storage_key'),
        bucket=trusted_bucket,
        settings=settings,
        tenant_prefix=trusted_prefix,
        expected_bucket=trusted_bucket,
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


web_router = APIRouter(prefix='/web', tags=['public-web-widget'])


def _resolve_web_session(
    request: Request,
    authorization: str | None,
) -> dict[str, Any]:
    if not authorization:
        raise HTTPException(status_code=401, detail='Session token required')
    scheme, _, token = authorization.partition(' ')
    if scheme.lower() != 'bearer' or not token:
        raise HTTPException(status_code=401, detail='Invalid session token header')
    settings = get_settings()
    try:
        return decode_session_token(
            token,
            secret_key=settings.jwt_secret,
            issuer=settings.jwt_issuer,
        )
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


async def _persist_bot_reply_sync(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    conversation_id: UUID,
) -> dict[str, Any] | None:
    """After the orchestrator runs, claim the latest pending outbound message.

    The RAG orchestrator queues the bot's outbound message via
    ``message.queued`` for the event worker (WhatsApp delivery). For the web
    channel we deliver synchronously: we mark the message as ``sent`` and
    publish the event right here so the response is returned to the browser
    immediately.
    """
    row = await conn.fetchrow(
        """
        select id, body_text, message_type, payload, created_at
        from app.messages
        where tenant_id=$1 and conversation_id=$2
          and direction='outbound' and status='queued'
        order by created_at desc
        limit 1
        """,
        tenant_id,
        conversation_id,
    )
    if not row:
        return None
    await conn.execute(
        """
        update app.messages
        set status='sent', sent_at=now()
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        row['id'],
    )
    await conn.execute(
        """
        update app.domain_events
        set published_at=now()
        where tenant_id=$1 and aggregate_id=$2 and event_name='message.queued'
          and published_at is null
        """,
        tenant_id,
        row['id'],
    )
    return {
        'id': str(row['id']),
        'body_text': row['body_text'] or '',
        'message_type': row['message_type'],
        'created_at': row['created_at'].isoformat() if row.get('created_at') else None,
    }


@web_router.post('/chat/start', status_code=201)
async def web_chat_start(
    payload: WebChatStart,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await conn.execute("select set_config('app.support_mode', 'true', true)")
    tenant_row = await conn.fetchrow(
        'select id, slug from app.tenants where slug=$1 and deleted_at is null',
        payload.tenant_slug,
    )
    if not tenant_row:
        raise HTTPException(status_code=404, detail='Tenant not found')
    tenant_id: UUID = tenant_row['id']

    channel = await conn.fetchrow(
        f"select {WEB_CHANNEL_PROJECTION} from app.tenant_channels where tenant_id=$1 and provider='web'",
        tenant_id,
    )
    if not channel or channel['status'] != 'active':
        raise HTTPException(status_code=404, detail='Web channel is not active for this tenant')

    expected_token = resolve_secret_ref(channel['token_ref'])
    if not constant_time_equals(payload.widget_token, expected_token):
        raise HTTPException(status_code=401, detail='Invalid widget token')

    origin = request.headers.get('origin') or request.headers.get('referer')
    allowed = list(channel['allowed_origins'] or [])
    if allowed and not origin_is_allowed(origin, allowed):
        raise HTTPException(status_code=403, detail='Origin not allowed for this widget')

    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    lead_source = build_lead_source(
        utm_source=payload.utm_source,
        utm_medium=payload.utm_medium,
        utm_campaign=payload.utm_campaign,
        referrer=payload.referrer,
    )

    # SECURITY: Anonymous web widget sessions cannot prove ownership of the
    # phone/email they submit. Reusing an existing contact based on an
    # unverified phone enables customer impersonation (an attacker who knows a
    # victim's phone can submit a message like "no" and mutate the victim's
    # appointment confirmation state via the orchestrator). Always synthesize
    # a fresh web-only identity and store the user-supplied phone/email as
    # unverified metadata. Operations can later verify and merge contacts
    # through an authenticated flow.
    seed = f'{tenant_id}:{payload.phone or ""}:{payload.email or ""}:{secrets.token_hex(16)}'
    wa_id, phone_e164 = synthesize_web_identity(seed)
    contact_metadata: dict[str, Any] = {'phone_verified': False, 'email_verified': False}
    if payload.phone:
        contact_metadata['unverified_phone'] = payload.phone.strip()
    if payload.email:
        contact_metadata['unverified_email'] = payload.email.strip()
    contact = await conn.fetchrow(
        """
        insert into app.contacts (
          tenant_id, wa_id, phone_e164, phone_hash, display_name, source, metadata, lead_source
        )
        values ($1, $2, $3, $4, $5, 'web_widget', $6::jsonb, $7::jsonb)
        returning *
        """,
        tenant_id,
        wa_id,
        phone_e164,
        hash_phone(phone_e164),
        payload.name.strip(),
        json.dumps(contact_metadata),
        json.dumps(lead_source),
    )

    conversation = await conn.fetchrow(
        """
        insert into app.conversations (tenant_id, contact_id, channel_id, status, opened_by, handoff_required)
        values ($1, $2, $3, 'open', 'user', false)
        returning *
        """,
        tenant_id,
        contact['id'],
        channel['id'],
    )

    inbound_message = await conn.fetchrow(
        """
        insert into app.messages (
          tenant_id, conversation_id, direction, sender_actor_type,
          body_text, message_type, status, received_at, payload
        )
        values ($1, $2, 'inbound', 'contact', $3, 'text', 'received', now(), $4::jsonb)
        returning *
        """,
        tenant_id,
        conversation['id'],
        payload.message.strip(),
        json.dumps({
            'channel': 'web',
            'origin': origin,
            'lead_source': lead_source,
        }),
    )

    await notify_operations_change(
        conn,
        tenant_id,
        'conversation.changed',
        conversation_id=conversation['id'],
        message_id=inbound_message['id'],
    )

    try:
        await orchestrate_inbound_message(
            conn,
            tenant_id=tenant_id,
            channel_id=channel['id'],
            channel_account_mode=channel['account_mode'] or 'live',
            conversation=conversation,
            contact=contact,
            inbound_message=inbound_message,
        )
    except Exception:
        log.exception(
            'web_widget.orchestrator_error',
            tenant_id=str(tenant_id),
            conversation_id=str(conversation['id']),
        )

    bot_reply = await _persist_bot_reply_sync(
        conn,
        tenant_id=tenant_id,
        conversation_id=conversation['id'],
    )

    settings = get_settings()
    session_token, expires_at = issue_session_token(
        secret_key=settings.jwt_secret,
        tenant_id=tenant_id,
        conversation_id=conversation['id'],
        contact_id=contact['id'],
        issuer=settings.jwt_issuer,
    )

    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type='anonymous',
        actor_id=str(contact['id']),
        action='web_widget.chat_started',
        entity_type='conversation',
        entity_id=str(conversation['id']),
        metadata={'lead_source': lead_source},
    )

    return {
        'conversation_id': str(conversation['id']),
        'contact_id': str(contact['id']),
        'session_token': session_token,
        'session_expires_at': expires_at.isoformat(),
        'inbound_message_id': str(inbound_message['id']),
        'bot_reply': bot_reply,
        'lead_source': lead_source,
    }


@web_router.post('/chat/{conversation_id}/messages', status_code=201)
async def web_chat_send_message(
    conversation_id: UUID,
    payload: WebChatMessage,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    session = _resolve_web_session(request, authorization)
    if session.get('conversation_id') != str(conversation_id):
        raise HTTPException(status_code=403, detail='Session token does not match conversation')

    tenant_id = UUID(session['tenant_id'])
    contact_id = UUID(session['contact_id'])
    await conn.execute("select set_config('app.support_mode', 'true', true)")
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))

    conversation = await conn.fetchrow(
        'select * from app.conversations where tenant_id=$1 and id=$2',
        tenant_id,
        conversation_id,
    )
    if not conversation or conversation['contact_id'] != contact_id:
        raise HTTPException(status_code=404, detail='Conversation not found')

    channel = await conn.fetchrow(
        'select * from app.tenant_channels where tenant_id=$1 and id=$2',
        tenant_id,
        conversation['channel_id'],
    )
    if not channel or channel['provider'] != 'web':
        raise HTTPException(status_code=400, detail='Conversation is not on the web channel')

    contact = await conn.fetchrow(
        'select * from app.contacts where tenant_id=$1 and id=$2',
        tenant_id,
        contact_id,
    )
    if not contact:
        raise HTTPException(status_code=404, detail='Contact not found')

    inbound_message = await conn.fetchrow(
        """
        insert into app.messages (
          tenant_id, conversation_id, direction, sender_actor_type,
          body_text, message_type, status, received_at, payload
        )
        values ($1, $2, 'inbound', 'contact', $3, 'text', 'received', now(), $4::jsonb)
        returning *
        """,
        tenant_id,
        conversation_id,
        payload.body.strip(),
        json.dumps({'channel': 'web'}),
    )

    await notify_operations_change(
        conn,
        tenant_id,
        'conversation.changed',
        conversation_id=conversation_id,
        message_id=inbound_message['id'],
    )

    try:
        await orchestrate_inbound_message(
            conn,
            tenant_id=tenant_id,
            channel_id=channel['id'],
            channel_account_mode=channel['account_mode'] or 'live',
            conversation=conversation,
            contact=contact,
            inbound_message=inbound_message,
        )
    except Exception:
        log.exception(
            'web_widget.orchestrator_error',
            tenant_id=str(tenant_id),
            conversation_id=str(conversation_id),
        )

    bot_reply = await _persist_bot_reply_sync(
        conn,
        tenant_id=tenant_id,
        conversation_id=conversation_id,
    )

    return {
        'inbound_message_id': str(inbound_message['id']),
        'bot_reply': bot_reply,
    }


@web_router.get('/chat/{conversation_id}/messages')
async def web_chat_history(
    conversation_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    authorization: str | None = Header(default=None),
):
    session = _resolve_web_session(request, authorization)
    if session.get('conversation_id') != str(conversation_id):
        raise HTTPException(status_code=403, detail='Session token does not match conversation')
    tenant_id = UUID(session['tenant_id'])
    await conn.execute("select set_config('app.support_mode', 'true', true)")
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        """
        select id, direction, sender_actor_type, body_text, message_type, created_at
        from app.messages
        where tenant_id=$1 and conversation_id=$2
        order by created_at asc
        """,
        tenant_id,
        conversation_id,
    )
    return {
        'conversation_id': str(conversation_id),
        'messages': [
            {
                'id': str(row['id']),
                'direction': row['direction'],
                'sender_actor_type': row['sender_actor_type'],
                'body_text': row['body_text'] or '',
                'message_type': row['message_type'],
                'created_at': row['created_at'].isoformat() if row['created_at'] else None,
            }
            for row in rows
        ],
    }


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
                # WhatsApp surfaces the quoted message id in `context.id` when the
                # contact uses the native "reply" affordance. Persist it on the
                # column so reply-stitching (analytics, threading) can stop reading
                # from the raw payload.
                context_obj = message.get('context') if isinstance(message, dict) else None
                reply_to_external_id = None
                if isinstance(context_obj, dict):
                    candidate = context_obj.get('id')
                    if isinstance(candidate, str) and candidate:
                        reply_to_external_id = candidate
                inbound_message = await conn.fetchrow(
                    """
                    insert into app.messages (
                      tenant_id, conversation_id, external_message_id, direction, sender_actor_type, sender_actor_id,
                      body_text, message_type, media_id, mime_type, payload, status, received_at,
                      reply_to_external_message_id
                    )
                    values ($1, $2, $3, 'inbound', 'contact', $4, $5, $6, $7, $8, $9::jsonb, 'received', coalesce($10::timestamptz, now()), $11)
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
                    reply_to_external_id,
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

    lead_source_rows = await conn.fetch(
        """
        select coalesce(nullif(lead_source->>'channel', ''), 'unknown') as channel,
               count(*)::int as count
        from app.contacts
        where tenant_id = $1 and created_at >= $2 and created_at < $3
        group by 1
        order by count desc
        """,
        tenant_id, range_start, range_end,
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
        'lead_sources': [
            {'channel': row['channel'], 'count': row['count']}
            for row in lead_source_rows
        ],
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
    branch_id: UUID | None = Query(default=None),
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
          and ($4::uuid is null or a.branch_id = $4)
        group by 1, 2
        order by count desc
        limit 10
        """,
        tenant_id, range_start, range_end, branch_id,
    )
    statuses = await conn.fetch(
        """
        select status, count(*) as count
        from app.appointments
        where tenant_id = $1 and created_at >= $2 and created_at < $3
          and ($4::uuid is null or branch_id = $4)
        group by status
        order by count desc
        """,
        tenant_id, range_start, range_end, branch_id,
    )
    no_shows_dow = await conn.fetch(
        """
        select extract(dow from starts_at)::int as dow, count(*) as count
        from app.appointments
        where tenant_id = $1 and status = 'no_show'
          and starts_at >= $2 and starts_at < $3
          and ($4::uuid is null or branch_id = $4)
        group by 1
        order by 1
        """,
        tenant_id, range_start, range_end, branch_id,
    )
    daily = await conn.fetch(
        """
        select date_trunc('day', created_at)::date as date,
               count(*) as created,
               count(*) filter (where status = 'completed') as completed
        from app.appointments
        where tenant_id = $1 and created_at >= $2 and created_at < $3
          and ($4::uuid is null or branch_id = $4)
        group by 1
        order by 1
        """,
        tenant_id, range_start, range_end, branch_id,
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


def _funnel_step(label: str, count: int, prev_count: int, top_count: int) -> dict:
    return {
        'step': label,
        'count': count,
        'conversion_from_previous_pct': (
            round(count / prev_count * 100, 1) if prev_count else 0.0
        ),
        'conversion_from_top_pct': (
            round(count / top_count * 100, 1) if top_count else 0.0
        ),
    }


@tenant_analytics_router.get('/analytics/funnel')
async def analytics_funnel(
    request: Request,
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    conn: asyncpg.Connection = Depends(get_db),
):
    """Conversion funnel: leads → engaged → scheduled → completed → repeat.

    Returns aggregated counts plus a per-channel breakdown using
    ``contacts.lead_source->>'channel'``.
    """
    tenant_id = await tenant_id_from_request(request, conn)
    start, end = _resolve_analytics_range(from_date, to_date)
    range_start, range_end = _range_bounds(start, end)
    repeat_window_start = range_end - timedelta(days=90)

    funnel_rows = await conn.fetch(
        """
        with leads as (
          select
            id as contact_id,
            coalesce(nullif(lead_source->>'channel', ''), 'unknown') as channel
          from app.contacts
          where tenant_id = $1 and created_at >= $2 and created_at < $3
        ),
        engaged as (
          select distinct conv.contact_id
          from app.conversations conv
          join app.messages m on m.tenant_id = conv.tenant_id
                              and m.conversation_id = conv.id
          where conv.tenant_id = $1
            and m.direction = 'outbound'
            and m.sender_actor_type in ('bot','agent')
            and m.created_at >= $2 and m.created_at < $3
        ),
        scheduled as (
          select distinct contact_id
          from app.appointments
          where tenant_id = $1
            and created_at >= $2 and created_at < $3
        ),
        completed as (
          select distinct contact_id
          from app.appointments
          where tenant_id = $1
            and status = 'completed'
            and starts_at >= $2 and starts_at < $3
        ),
        repeat_customers as (
          select contact_id
          from app.appointments
          where tenant_id = $1
            and status = 'completed'
            and starts_at >= $4 and starts_at < $3
          group by contact_id
          having count(*) >= 2
        )
        select
          l.channel as channel,
          count(distinct l.contact_id) as leads,
          count(distinct e.contact_id) as engaged,
          count(distinct s.contact_id) as scheduled,
          count(distinct c.contact_id) as completed,
          count(distinct r.contact_id) as repeat_customers
        from leads l
        left join engaged e on e.contact_id = l.contact_id
        left join scheduled s on s.contact_id = l.contact_id
        left join completed c on c.contact_id = l.contact_id
        left join repeat_customers r on r.contact_id = l.contact_id
        group by l.channel
        order by leads desc
        """,
        tenant_id, range_start, range_end, repeat_window_start,
    )

    total_leads = sum(int(row['leads'] or 0) for row in funnel_rows)
    total_engaged = sum(int(row['engaged'] or 0) for row in funnel_rows)
    total_scheduled = sum(int(row['scheduled'] or 0) for row in funnel_rows)
    total_completed = sum(int(row['completed'] or 0) for row in funnel_rows)
    total_repeat = sum(int(row['repeat_customers'] or 0) for row in funnel_rows)

    total_steps = [
        _funnel_step('leads', total_leads, total_leads, total_leads),
        _funnel_step('engaged', total_engaged, total_leads, total_leads),
        _funnel_step('appointments_scheduled', total_scheduled, total_engaged, total_leads),
        _funnel_step('appointments_completed', total_completed, total_scheduled, total_leads),
        _funnel_step('repeat_customers', total_repeat, total_completed, total_leads),
    ]

    by_channel = []
    for row in funnel_rows:
        leads = int(row['leads'] or 0)
        engaged = int(row['engaged'] or 0)
        scheduled = int(row['scheduled'] or 0)
        completed = int(row['completed'] or 0)
        repeat = int(row['repeat_customers'] or 0)
        by_channel.append({
            'channel': row['channel'],
            'steps': [
                _funnel_step('leads', leads, leads, leads),
                _funnel_step('engaged', engaged, leads, leads),
                _funnel_step('appointments_scheduled', scheduled, engaged, leads),
                _funnel_step('appointments_completed', completed, scheduled, leads),
                _funnel_step('repeat_customers', repeat, completed, leads),
            ],
        })

    return {
        'range': {'from_date': start.isoformat(), 'to_date': end.isoformat()},
        'repeat_window_days': 90,
        'total': total_steps,
        'by_channel': by_channel,
    }


@tenant_analytics_router.get('/analytics/campaigns')
async def analytics_campaigns(
    request: Request,
    from_date: str | None = Query(None),
    to_date: str | None = Query(None),
    conn: asyncpg.Connection = Depends(get_db),
):
    """Per-campaign performance with attributed appointments and revenue.

    Includes campaigns whose ``started_at`` (or ``created_at`` if not yet
    launched) falls within the range. ``appointments_attributed`` and
    ``revenue_attributed`` come from ``app.campaign_attributions`` joined
    with service prices.
    """
    tenant_id = await tenant_id_from_request(request, conn)
    start, end = _resolve_analytics_range(from_date, to_date)
    range_start, range_end = _range_bounds(start, end)

    rows = await conn.fetch(
        """
        with cam as (
          select
            c.id, c.name, c.status, c.scheduled_at, c.started_at, c.completed_at,
            c.recipient_count, c.sent_count, c.delivered_count, c.read_count,
            c.failed_count, c.cost_amount, c.cost_currency,
            c.attribution_window_days
          from app.campaigns c
          where c.tenant_id = $1
            and coalesce(c.started_at, c.created_at) >= $2
            and coalesce(c.started_at, c.created_at) < $3
        ),
        replies as (
          -- A "reply" is any inbound message that lands in the same conversation
          -- as a campaign-tagged outbound, within that campaign's attribution
          -- window. We can't rely on inbound rows carrying campaign_id (the
          -- WhatsApp webhook never sets it) nor on reply_to_external_message_id
          -- (only present when the contact uses the native quote affordance),
          -- so we stitch by conversation+time exactly like campaign_attributions
          -- already does for appointments.
          select om.campaign_id, count(distinct om.conversation_id) as replied
          from app.messages om
          join app.campaigns c
            on c.tenant_id = om.tenant_id and c.id = om.campaign_id
          where om.tenant_id = $1
            and om.direction = 'outbound'
            and om.campaign_id is not null
            and exists (
              select 1
              from app.messages im
              where im.tenant_id = om.tenant_id
                and im.conversation_id = om.conversation_id
                and im.direction = 'inbound'
                and im.received_at >= coalesce(om.sent_at, om.created_at)
                and im.received_at < coalesce(om.sent_at, om.created_at)
                                      + (c.attribution_window_days || ' days')::interval
            )
          group by om.campaign_id
        ),
        attribution as (
          select
            ca.campaign_id,
            count(*) as attributed_count,
            count(*) filter (where a.status = 'completed') as attributed_completed,
            coalesce(sum(s.price_amount) filter (where a.status = 'completed'), 0)::float
              as revenue_attributed
          from app.campaign_attributions ca
          join app.appointments a on a.tenant_id = ca.tenant_id
                                  and a.id = ca.appointment_id
          left join app.service_catalog s on s.tenant_id = a.tenant_id
                                          and s.id = a.service_id
          where ca.tenant_id = $1
          group by ca.campaign_id
        )
        select
          cam.*,
          coalesce(replies.replied, 0) as replied,
          coalesce(attribution.attributed_count, 0) as appointments_attributed,
          coalesce(attribution.attributed_completed, 0) as appointments_completed,
          coalesce(attribution.revenue_attributed, 0.0) as revenue_attributed
        from cam
        left join replies on replies.campaign_id = cam.id
        left join attribution on attribution.campaign_id = cam.id
        order by revenue_attributed desc, cam.started_at desc nulls last
        """,
        tenant_id, range_start, range_end,
    )

    items = []
    for row in rows:
        recipients = int(row['recipient_count'] or 0)
        delivered = int(row['delivered_count'] or 0)
        read = int(row['read_count'] or 0)
        replied = int(row['replied'] or 0)
        cost_amount = float(row['cost_amount']) if row['cost_amount'] is not None else None
        revenue = float(row['revenue_attributed'] or 0.0)
        roi = None
        if cost_amount and cost_amount > 0:
            roi = round(revenue / cost_amount, 2)
        items.append({
            'campaign_id': str(row['id']),
            'name': row['name'],
            'status': row['status'],
            'started_at': row['started_at'].isoformat() if row['started_at'] else None,
            'recipients': recipients,
            'sent': int(row['sent_count'] or 0),
            'delivered': delivered,
            'read': read,
            'replied': replied,
            'failed': int(row['failed_count'] or 0),
            'response_rate_pct': (
                round(replied / delivered * 100, 1) if delivered else 0.0
            ),
            'appointments_attributed': int(row['appointments_attributed'] or 0),
            'appointments_completed': int(row['appointments_completed'] or 0),
            'revenue_attributed': round(revenue, 2),
            'cost_amount': round(cost_amount, 2) if cost_amount is not None else None,
            'cost_currency': row['cost_currency'],
            'roi_estimated': roi,
            'attribution_window_days': int(row['attribution_window_days'] or 14),
        })

    totals = {
        'campaigns': len(items),
        'appointments_attributed': sum(item['appointments_attributed'] for item in items),
        'appointments_completed': sum(item['appointments_completed'] for item in items),
        'revenue_attributed': round(
            sum(item['revenue_attributed'] for item in items), 2
        ),
    }

    return {
        'range': {'from_date': start.isoformat(), 'to_date': end.isoformat()},
        'totals': totals,
        'items': items,
    }


SEGMENT_PROJECTION = (
    'id, tenant_id, name, description, kind, rules, contact_count, '
    'last_refreshed_at, is_system, created_by, created_at, updated_at'
)


def normalize_segment_row(row: asyncpg.Record | None) -> dict | None:
    seg = record_to_dict(row)
    if not seg:
        return None
    seg['rules'] = parse_json_object(seg.get('rules'), default={})
    return seg


async def _fetch_segment_or_404(
    conn: asyncpg.Connection, tenant_id: UUID, segment_id: UUID
) -> asyncpg.Record:
    row = await conn.fetchrow(
        f'select {SEGMENT_PROJECTION} from app.contact_segments where tenant_id=$1 and id=$2',
        tenant_id,
        segment_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Segment not found')
    return row


@tenant_admin_router.get('/tenants/{tenant_id}/segments')
async def list_contact_segments(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    kind: str | None = Query(default=None, pattern='^(dynamic|static)$'),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        f"""
        select {SEGMENT_PROJECTION}
        from app.contact_segments
        where tenant_id=$1 and ($2::text is null or kind=$2)
        order by is_system desc, name asc
        """,
        tenant_id,
        kind,
    )
    return [normalize_segment_row(row) for row in rows]


@tenant_admin_router.post('/tenants/{tenant_id}/segments', status_code=201)
async def create_contact_segment(
    tenant_id: UUID,
    payload: ContactSegmentCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rules = normalize_segment_rules(payload.rules) if payload.kind == 'dynamic' else {}
    created_by = await current_user_id_from_request(request, conn)
    initial_count = (
        await count_segment_contacts(conn, tenant_id, rules) if payload.kind == 'dynamic' else 0
    )
    row = await conn.fetchrow(
        f"""
        insert into app.contact_segments (
          tenant_id, name, description, kind, rules, contact_count, last_refreshed_at, created_by
        )
        values ($1, $2, $3, $4, $5::jsonb, $6, case when $4='dynamic' then now() else null end, $7)
        returning {SEGMENT_PROJECTION}
        """,
        tenant_id,
        payload.name.strip(),
        payload.description,
        payload.kind,
        json.dumps(rules),
        initial_count,
        created_by,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='segment.created',
        entity_type='contact_segment',
        entity_id=str(row['id']),
        metadata={'kind': payload.kind, 'contact_count': initial_count},
    )
    return normalize_segment_row(row)


@tenant_admin_router.get('/tenants/{tenant_id}/segments/{segment_id}')
async def get_contact_segment(
    tenant_id: UUID,
    segment_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_segment_or_404(conn, tenant_id, segment_id)
    return normalize_segment_row(row)


@tenant_admin_router.patch('/tenants/{tenant_id}/segments/{segment_id}')
async def patch_contact_segment(
    tenant_id: UUID,
    segment_id: UUID,
    payload: ContactSegmentUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_segment_or_404(conn, tenant_id, segment_id)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return normalize_segment_row(row)
    next_kind = data.get('kind') or row['kind']
    if 'rules' in data:
        rules = normalize_segment_rules(data['rules']) if next_kind == 'dynamic' else {}
    else:
        rules = None
    new_count = None
    if next_kind == 'dynamic' and rules is not None:
        new_count = await count_segment_contacts(conn, tenant_id, rules)
    updated = await conn.fetchrow(
        f"""
        update app.contact_segments
        set name=coalesce($3, name),
            description=coalesce($4, description),
            kind=coalesce($5, kind),
            rules=coalesce($6::jsonb, rules),
            contact_count=coalesce($7, contact_count),
            last_refreshed_at=case when $5='dynamic' and $6 is not null then now() else last_refreshed_at end,
            updated_at=now()
        where tenant_id=$1 and id=$2
        returning {SEGMENT_PROJECTION}
        """,
        tenant_id,
        segment_id,
        data.get('name'),
        data.get('description'),
        data.get('kind'),
        json.dumps(rules) if rules is not None else None,
        new_count,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='segment.updated',
        entity_type='contact_segment',
        entity_id=str(segment_id),
        metadata={'fields': sorted(data.keys())},
    )
    return normalize_segment_row(updated)


@tenant_admin_router.delete(
    '/tenants/{tenant_id}/segments/{segment_id}', status_code=204
)
async def delete_contact_segment(
    tenant_id: UUID,
    segment_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_segment_or_404(conn, tenant_id, segment_id)
    if row['is_system']:
        raise HTTPException(
            status_code=409,
            detail='System segments cannot be deleted; edit the rules instead.',
        )
    await conn.execute(
        'delete from app.contact_segments where tenant_id=$1 and id=$2',
        tenant_id,
        segment_id,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='segment.deleted',
        entity_type='contact_segment',
        entity_id=str(segment_id),
    )


@tenant_admin_router.get('/tenants/{tenant_id}/segments/{segment_id}/preview')
async def preview_contact_segment(
    tenant_id: UUID,
    segment_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    limit: int = Query(default=25, ge=1, le=100),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_segment_or_404(conn, tenant_id, segment_id)
    rules = parse_json_object(row['rules'], default={})
    if row['kind'] == 'dynamic':
        sample = await evaluate_segment_rules(conn, tenant_id, rules, limit=limit)
        total = await count_segment_contacts(conn, tenant_id, rules)
    else:
        # Static segments: pull the most recent snapshot's members.
        members = await conn.fetch(
            """
            select m.contact_id as contact_id, c.display_name, c.phone_e164, c.opt_in_status
            from app.contact_segment_members m
            join app.contacts c on c.tenant_id=m.tenant_id and c.id=m.contact_id
            where m.tenant_id=$1 and m.segment_id=$2
              and m.snapshot_at = (
                select max(snapshot_at) from app.contact_segment_members
                where segment_id=$2
              )
            order by c.display_name nulls last
            limit $3
            """,
            tenant_id,
            segment_id,
            limit,
        )
        sample = [dict(r) for r in members]
        total = await conn.fetchval(
            """
            select count(*) from app.contact_segment_members
            where segment_id=$1
              and snapshot_at = (
                select max(snapshot_at) from app.contact_segment_members
                where segment_id=$1
              )
            """,
            segment_id,
        ) or 0
    return {
        'segment_id': str(segment_id),
        'contact_count': int(total),
        'sample': [
            {
                'contact_id': str(item['contact_id']),
                'display_name': item.get('display_name'),
                'phone_e164': item.get('phone_e164'),
                'opt_in_status': item.get('opt_in_status'),
            }
            for item in sample
        ],
    }


@tenant_admin_router.post('/tenants/{tenant_id}/segments/{segment_id}/refresh')
async def refresh_contact_segment(
    tenant_id: UUID,
    segment_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_segment_or_404(conn, tenant_id, segment_id)
    rules = parse_json_object(row['rules'], default={})
    count, _snapshot_at = await snapshot_segment_members(conn, tenant_id, segment_id, rules)
    refreshed = await _fetch_segment_or_404(conn, tenant_id, segment_id)
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='segment.refreshed',
        entity_type='contact_segment',
        entity_id=str(segment_id),
        metadata={'contact_count': count},
    )
    return normalize_segment_row(refreshed)


@tenant_admin_router.post('/tenants/{tenant_id}/segments/{segment_id}/members')
async def set_static_segment_members(
    tenant_id: UUID,
    segment_id: UUID,
    payload: ContactSegmentMembersAssign,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_segment_or_404(conn, tenant_id, segment_id)
    if row['kind'] != 'static':
        raise HTTPException(
            status_code=409,
            detail='Only static segments accept manually managed members.',
        )
    snapshot_at = await conn.fetchval('select now()')
    if payload.contact_ids:
        await conn.executemany(
            """
            insert into app.contact_segment_members (tenant_id, segment_id, contact_id, snapshot_at)
            values ($1, $2, $3, $4)
            on conflict (segment_id, contact_id, snapshot_at) do nothing
            """,
            [(tenant_id, segment_id, cid, snapshot_at) for cid in payload.contact_ids],
        )
    await conn.execute(
        """
        update app.contact_segments
        set contact_count=$3, last_refreshed_at=$4, updated_at=now()
        where tenant_id=$1 and id=$2
        """,
        tenant_id,
        segment_id,
        len(payload.contact_ids),
        snapshot_at,
    )
    return normalize_segment_row(
        await _fetch_segment_or_404(conn, tenant_id, segment_id)
    )


CAMPAIGN_PROJECTION = (
    'id, tenant_id, name, status, template_id, template_variables, '
    'segment_filter, segment_id, launched_snapshot_at, scheduled_at, '
    'recipient_count, sent_count, delivered_count, read_count, '
    'failed_count, started_at, completed_at, cost_amount, cost_currency, '
    'attribution_window_days, created_by, created_at, updated_at'
)


def normalize_campaign(row: asyncpg.Record | None) -> dict | None:
    campaign = record_to_dict(row)
    if not campaign:
        return None
    campaign['template_variables'] = parse_json_object(campaign.get('template_variables'), default={})
    campaign['segment_filter'] = parse_json_object(campaign.get('segment_filter'), default={})
    return campaign


def _campaign_segment_filter_dict(payload_segment) -> dict[str, Any]:
    if payload_segment is None:
        return {}
    if hasattr(payload_segment, 'model_dump'):
        raw = payload_segment.model_dump(exclude_none=True)
    elif isinstance(payload_segment, dict):
        raw = payload_segment
    else:
        raw = {}
    # UUIDs in the pydantic dump come back as UUID instances; the helper
    # converts them to strings so the JSON encoder doesn't trip up.
    if isinstance(raw.get('tags'), list):
        raw['tags'] = [str(tag) for tag in raw['tags']]
    return normalize_segment_filter(raw)


async def _fetch_campaign_or_404(
    conn: asyncpg.Connection, tenant_id: UUID, campaign_id: UUID
) -> asyncpg.Record:
    row = await conn.fetchrow(
        f'select {CAMPAIGN_PROJECTION} from app.campaigns where tenant_id=$1 and id=$2',
        tenant_id,
        campaign_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Campaign not found')
    return row


async def _ensure_template_approved(
    conn: asyncpg.Connection, tenant_id: UUID, template_id: UUID
) -> asyncpg.Record:
    row = await conn.fetchrow(
        'select id, name, status, category from app.whatsapp_templates where tenant_id=$1 and id=$2',
        tenant_id,
        template_id,
    )
    if not row:
        raise HTTPException(status_code=404, detail='Template not found')
    if row['status'] != 'approved':
        raise HTTPException(
            status_code=400,
            detail='Campaign templates must be approved by Meta before launch',
        )
    return row


@tenant_admin_router.post('/tenants/{tenant_id}/campaigns', status_code=201)
async def create_campaign(
    tenant_id: UUID,
    payload: CampaignCreate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    await _ensure_template_approved(conn, tenant_id, payload.template_id)
    segment = _campaign_segment_filter_dict(payload.segment_filter)
    segment_row = None
    if payload.segment_id is not None:
        segment_row = await _fetch_segment_or_404(conn, tenant_id, payload.segment_id)
        recipient_count = int(segment_row['contact_count'] or 0)
    else:
        recipient_count = await count_campaign_recipients(conn, tenant_id, segment)
    created_by = await current_user_id_from_request(request, conn)
    row = await conn.fetchrow(
        f"""
        insert into app.campaigns (
          tenant_id, name, template_id, template_variables,
          segment_filter, segment_id, scheduled_at, recipient_count,
          cost_amount, cost_currency, attribution_window_days, created_by
        )
        values ($1, $2, $3, $4::jsonb, $5::jsonb, $6, $7, $8,
                $9, coalesce($10, 'COP'), coalesce($11, 14), $12)
        returning {CAMPAIGN_PROJECTION}
        """,
        tenant_id,
        payload.name.strip(),
        payload.template_id,
        json.dumps(payload.template_variables or {}),
        json.dumps(segment),
        payload.segment_id,
        payload.scheduled_at,
        recipient_count,
        payload.cost_amount,
        (payload.cost_currency or '').upper() or None,
        payload.attribution_window_days,
        created_by,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='campaign.created',
        entity_type='campaign',
        entity_id=str(row['id']),
        metadata={
            'template_id': str(payload.template_id),
            'recipient_count': recipient_count,
        },
    )
    return normalize_campaign(row)


@tenant_admin_router.get('/tenants/{tenant_id}/campaigns')
async def list_campaigns(
    tenant_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    status_filter: str | None = Query(default=None, alias='status'),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    rows = await conn.fetch(
        f"""
        select {CAMPAIGN_PROJECTION}
        from app.campaigns
        where tenant_id=$1
          and ($2::text is null or status=$2)
        order by created_at desc
        """,
        tenant_id,
        status_filter,
    )
    return [normalize_campaign(row) for row in rows]


@tenant_admin_router.get('/tenants/{tenant_id}/campaigns/{campaign_id}')
async def get_campaign(
    tenant_id: UUID,
    campaign_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_campaign_or_404(conn, tenant_id, campaign_id)
    # Counter refresh on read so the admin panel sees the latest metrics
    # rolled up from app.messages (sent/delivered/read/failed).
    if row['status'] in ('running', 'completed'):
        await refresh_campaign_counters(conn, tenant_id, campaign_id)
        row = await _fetch_campaign_or_404(conn, tenant_id, campaign_id)
    return normalize_campaign(row)


@tenant_admin_router.patch('/tenants/{tenant_id}/campaigns/{campaign_id}')
async def patch_campaign(
    tenant_id: UUID,
    campaign_id: UUID,
    payload: CampaignUpdate,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_campaign_or_404(conn, tenant_id, campaign_id)
    if row['status'] != 'draft':
        raise HTTPException(
            status_code=409,
            detail='Only campaigns in draft can be edited',
        )
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return normalize_campaign(row)
    if payload.template_id is not None:
        await _ensure_template_approved(conn, tenant_id, payload.template_id)
    segment = (
        _campaign_segment_filter_dict(payload.segment_filter)
        if payload.segment_filter is not None
        else None
    )
    next_segment_id = data.get('segment_id') if 'segment_id' in data else row['segment_id']
    if next_segment_id is not None and 'segment_id' in data:
        segment_row = await _fetch_segment_or_404(conn, tenant_id, next_segment_id)
        new_recipient_count = int(segment_row['contact_count'] or 0)
    elif segment is not None:
        new_recipient_count = await count_campaign_recipients(conn, tenant_id, segment)
    else:
        new_recipient_count = None
    cost_currency_value = data.get('cost_currency')
    if isinstance(cost_currency_value, str):
        cost_currency_value = cost_currency_value.upper()
    updated = await conn.fetchrow(
        f"""
        update app.campaigns
        set name=coalesce($3, name),
            template_id=coalesce($4, template_id),
            template_variables=coalesce($5::jsonb, template_variables),
            segment_filter=coalesce($6::jsonb, segment_filter),
            segment_id=case when $9 then $10 else segment_id end,
            scheduled_at=coalesce($7, scheduled_at),
            recipient_count=coalesce($8, recipient_count),
            cost_amount=case when $11 then $12 else cost_amount end,
            cost_currency=coalesce($13, cost_currency),
            attribution_window_days=coalesce($14, attribution_window_days),
            updated_at=now()
        where tenant_id=$1 and id=$2
        returning {CAMPAIGN_PROJECTION}
        """,
        tenant_id,
        campaign_id,
        data.get('name'),
        data.get('template_id'),
        json.dumps(data['template_variables']) if 'template_variables' in data else None,
        json.dumps(segment) if segment is not None else None,
        data.get('scheduled_at'),
        new_recipient_count,
        'segment_id' in data,
        data.get('segment_id'),
        'cost_amount' in data,
        data.get('cost_amount'),
        cost_currency_value,
        data.get('attribution_window_days'),
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='campaign.updated',
        entity_type='campaign',
        entity_id=str(campaign_id),
        metadata={'fields': sorted(data.keys())},
    )
    return normalize_campaign(updated)


@tenant_admin_router.post('/tenants/{tenant_id}/campaigns/{campaign_id}/preview')
async def preview_campaign(
    tenant_id: UUID,
    campaign_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_campaign_or_404(conn, tenant_id, campaign_id)
    if row['segment_id'] is not None:
        seg_row = await _fetch_segment_or_404(conn, tenant_id, row['segment_id'])
        rules = parse_json_object(seg_row['rules'], default={})
        total = await count_segment_contacts(conn, tenant_id, rules)
        sample_rows = await evaluate_segment_rules(conn, tenant_id, rules, limit=5)
        sample = [
            {
                'id': str(item['contact_id']),
                'display_name': item.get('display_name'),
                'phone_e164': item.get('phone_e164'),
                'opt_in_status': item.get('opt_in_status'),
            }
            for item in sample_rows
        ]
    else:
        segment = parse_json_object(row['segment_filter'], default={})
        total = await count_campaign_recipients(conn, tenant_id, segment)
        sample_rows = await evaluate_segment(conn, tenant_id, segment, limit=5)
        sample = [
            {
                'id': str(item['id']),
                'display_name': item.get('display_name'),
                'phone_e164': item.get('phone_e164'),
                'opt_in_status': item.get('opt_in_status'),
            }
            for item in sample_rows
        ]
    return {
        'recipient_count': total,
        'sample': sample,
    }


@tenant_admin_router.post('/tenants/{tenant_id}/campaigns/{campaign_id}/launch')
async def launch_campaign(
    tenant_id: UUID,
    campaign_id: UUID,
    payload: CampaignLaunch,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_campaign_or_404(conn, tenant_id, campaign_id)
    if row['status'] not in ('draft', 'scheduled'):
        raise HTTPException(
            status_code=409,
            detail=f'Campaign cannot be launched from status={row["status"]}',
        )
    await _ensure_template_approved(conn, tenant_id, row['template_id'])
    next_scheduled = payload.scheduled_at or row['scheduled_at'] or datetime.now(UTC)
    launched_snapshot_at = None
    if row['segment_id'] is not None:
        seg_row = await _fetch_segment_or_404(conn, tenant_id, row['segment_id'])
        rules = parse_json_object(seg_row['rules'], default={})
        if seg_row['kind'] == 'dynamic':
            _count, launched_snapshot_at = await snapshot_segment_members(
                conn, tenant_id, row['segment_id'], rules
            )
        else:
            # Static segment: use the latest manual snapshot.
            launched_snapshot_at = await conn.fetchval(
                """
                select max(snapshot_at) from app.contact_segment_members
                where segment_id=$1
                """,
                row['segment_id'],
            )
    updated = await conn.fetchrow(
        f"""
        update app.campaigns
        set status='scheduled', scheduled_at=$3,
            launched_snapshot_at=coalesce($4, launched_snapshot_at),
            updated_at=now()
        where tenant_id=$1 and id=$2
        returning {CAMPAIGN_PROJECTION}
        """,
        tenant_id,
        campaign_id,
        next_scheduled,
        launched_snapshot_at,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='campaign.launched',
        entity_type='campaign',
        entity_id=str(campaign_id),
        metadata={'scheduled_at': next_scheduled.isoformat()},
    )
    return normalize_campaign(updated)


@tenant_admin_router.post('/tenants/{tenant_id}/campaigns/{campaign_id}/cancel')
async def cancel_campaign(
    tenant_id: UUID,
    campaign_id: UUID,
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
):
    await ensure_tenant_access(request, tenant_id, conn)
    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
    row = await _fetch_campaign_or_404(conn, tenant_id, campaign_id)
    if row['status'] in ('completed', 'cancelled'):
        raise HTTPException(
            status_code=409,
            detail=f'Campaign already in terminal status={row["status"]}',
        )
    updated = await conn.fetchrow(
        f"""
        update app.campaigns
        set status='cancelled', completed_at=now(), updated_at=now()
        where tenant_id=$1 and id=$2
        returning {CAMPAIGN_PROJECTION}
        """,
        tenant_id,
        campaign_id,
    )
    await audit(
        conn,
        tenant_id=tenant_id,
        actor_type=request.state.actor_type,
        actor_id=request.state.actor_id,
        action='campaign.cancelled',
        entity_type='campaign',
        entity_id=str(campaign_id),
    )
    return normalize_campaign(updated)


router.include_router(public_router)
router.include_router(web_router)
router.include_router(webhook_router)
router.include_router(platform_admin_router)
router.include_router(tenant_signup_router)
router.include_router(tenant_user_router)
router.include_router(tenant_admin_router)
router.include_router(tenant_catalog_router)
router.include_router(tenant_ops_router)
router.include_router(tenant_analytics_router)
router.include_router(system_router)
