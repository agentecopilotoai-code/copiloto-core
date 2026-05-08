from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TenantCreate(BaseModel):
    slug: str
    legal_name: str
    display_name: str
    vertical_code: str = Field(pattern='^(field_service|beauty|pet_grooming)$')
    country_code: str = 'CO'
    timezone: str = 'America/Bogota'


class TenantUpdate(BaseModel):
    slug: str | None = None
    legal_name: str | None = None
    display_name: str | None = None
    vertical_code: str | None = Field(default=None, pattern='^(field_service|beauty|pet_grooming)$')
    country_code: str | None = None
    timezone: str | None = None


class KnowledgeStorageUpdate(BaseModel):
    backend: str = Field(default='local', pattern='^(local|s3)$')
    bucket: str | None = Field(default=None, min_length=3, max_length=255)
    region: str | None = Field(default=None, max_length=64)
    endpoint_url: str | None = Field(default=None, max_length=512)
    prefix: str | None = Field(default=None, max_length=512)
    access_key_id: str | None = Field(default=None, min_length=1, max_length=255)
    secret_access_key: str | None = Field(default=None, min_length=1)


class ChannelCreate(BaseModel):
    business_id: str | None = None
    waba_id: str | None = None
    phone_number_id: str
    meta_access_token: str | None = Field(default=None, min_length=1)
    app_secret: str | None = Field(default=None, min_length=1)
    verify_token: str | None = Field(default=None, min_length=16)
    account_mode: str = Field(default='mock', pattern='^(mock|live)$')


class ContactUpsert(BaseModel):
    tenant_id: UUID
    wa_id: str
    phone_e164: str
    display_name: str | None = None
    opt_in_status: str = 'unknown'
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationCreate(BaseModel):
    tenant_id: UUID
    contact_id: UUID
    channel_id: UUID
    opened_by: str = 'user'
    current_intent: str | None = None


class ConversationStart(BaseModel):
    tenant_id: UUID
    phone_e164: str = Field(min_length=6, max_length=32)
    wa_id: str | None = None
    display_name: str | None = None
    initial_message: str | None = Field(default=None, max_length=4096)
    initial_message_type: str = Field(default='text', pattern='^(text|image|audio|video)$')
    initial_media_id: str | None = None
    initial_media_url: str | None = None
    initial_mime_type: str | None = None
    current_intent: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageCreate(BaseModel):
    tenant_id: UUID
    conversation_id: UUID
    direction: str = 'outbound'
    sender_actor_type: str = 'agent'
    body_text: str | None = None
    message_type: str = Field(default='text', pattern='^(text|image|audio|video|document|interactive|template|system)$')
    media_id: str | None = None
    mime_type: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)




class ResourceCreate(BaseModel):
    tenant_id: UUID
    vertical_code: str = Field(pattern='^(field_service|beauty|pet_grooming)$')
    resource_type: str = Field(pattern='^(technician|chair|stylist|groomer|room|vehicle)$')
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class ResourceUpdate(BaseModel):
    vertical_code: str | None = Field(default=None, pattern='^(field_service|beauty|pet_grooming)$')
    resource_type: str | None = Field(default=None, pattern='^(technician|chair|stylist|groomer|room|vehicle)$')
    code: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    capabilities: dict[str, Any] | None = None
    is_active: bool | None = None


class ServiceRequestCreate(BaseModel):
    tenant_id: UUID
    contact_id: UUID
    conversation_id: UUID | None = None
    vertical_code: str
    service_type: str
    problem_summary: str | None = None
    urgency: str = 'normal'
    intake: dict[str, Any] = Field(default_factory=dict)


class ServiceRequestPatch(BaseModel):
    status: str | None = Field(default=None, pattern='^(open|qualified|quoted|scheduled|cancelled|resolved)$')
    assigned_resource_id: UUID | None = None
    problem_summary: str | None = None
    urgency: str | None = Field(default=None, pattern='^(low|normal|high|emergency)$')
    preferred_date: str | None = None
    preferred_slot: str | None = None
    intake: dict[str, Any] | None = None


class QuoteLineItem(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    qty: float = Field(default=1.0, gt=0)
    unit_price: float = Field(ge=0)


class QuoteCreate(BaseModel):
    line_items: list[QuoteLineItem] = Field(default_factory=list)
    currency: str = Field(default='COP', min_length=3, max_length=3)
    discount_total: float = Field(default=0.0, ge=0)
    tax_total: float = Field(default=0.0, ge=0)
    valid_until: datetime | None = None


class QuotePatch(BaseModel):
    line_items: list[QuoteLineItem] | None = None
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    discount_total: float | None = Field(default=None, ge=0)
    tax_total: float | None = Field(default=None, ge=0)
    status: str | None = Field(default=None, pattern='^(draft|sent|accepted|rejected|expired)$')
    valid_until: datetime | None = None


class AppointmentCreate(BaseModel):
    tenant_id: UUID
    contact_id: UUID
    resource_id: UUID
    service_code: str
    starts_at: datetime
    ends_at: datetime
    conversation_id: UUID | None = None
    service_request_id: UUID | None = None
    notes: str | None = None




class AppointmentUpdate(BaseModel):
    resource_id: UUID | None = None
    service_code: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: str | None = Field(default=None, pattern='^(scheduled|confirmed|completed|cancelled|no_show)$')
    confirmation_status: str | None = Field(default=None, pattern='^(pending|confirmed|declined)$')
    notes: str | None = None


class KnowledgeDocumentCreate(BaseModel):
    tenant_id: UUID
    title: str
    source_type: str = Field(default='manual', pattern='^(upload|url|manual|integration)$')
    document_type: str = Field(default='reference', pattern='^(faq|policy|reference)$')
    source_uri: str | None = None
    checksum: str | None = None
    mime_type: str | None = None
    content: str | None = None
    visibility: str = Field(default='tenant', pattern='^(tenant|agents_only|public)$')
    status: str = Field(default='draft', pattern='^(draft|indexing|active|failed)$')
    metadata: dict[str, Any] = Field(default_factory=dict)


class KnowledgeDocumentUpdate(BaseModel):
    title: str | None = None
    source_type: str | None = Field(default=None, pattern='^(upload|url|manual|integration)$')
    document_type: str | None = Field(default=None, pattern='^(faq|policy|reference)$')
    source_uri: str | None = None
    checksum: str | None = None
    mime_type: str | None = None
    content: str | None = None
    visibility: str | None = Field(default=None, pattern='^(tenant|agents_only|public)$')
    status: str | None = Field(default=None, pattern='^(draft|indexing|active|failed)$')
    metadata: dict[str, Any] | None = None


class IntentEvaluateRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)
    max_chunks: int = Field(default=5, ge=1, le=10)
    min_score: float = Field(default=0.12, ge=0, le=1)


class PromptCreate(BaseModel):
    tenant_id: UUID | None = None
    vertical_code: str = 'common'
    prompt_type: str
    name: str
    version: int = 1
    content: str
    variables: list[str] = Field(default_factory=list)
