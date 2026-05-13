from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.services.locale import SUPPORTED_COUNTRIES

# TASK-0073: el MVP solo vende a 7 países LatAm. El patrón viene del catálogo
# autoritativo de `app.services.locale` para evitar drift.
SUPPORTED_COUNTRY_PATTERN = '^(' + '|'.join(SUPPORTED_COUNTRIES) + ')$'


class TenantCreate(BaseModel):
    slug: str
    legal_name: str
    display_name: str
    vertical_code: str = Field(min_length=1, max_length=64)
    business_type_label: str | None = Field(default=None, min_length=1, max_length=160)
    country_code: str = Field(default='CO', pattern=SUPPORTED_COUNTRY_PATTERN)
    # Si ``timezone`` viene vacío, el route lo deriva de ``country_code`` vía
    # ``app.services.locale.default_timezone``.
    timezone: str | None = Field(default=None, min_length=1, max_length=64)


class TenantUpdate(BaseModel):
    slug: str | None = None
    legal_name: str | None = None
    display_name: str | None = None
    vertical_code: str | None = Field(default=None, min_length=1, max_length=64)
    business_type_label: str | None = Field(default=None, min_length=1, max_length=160)
    country_code: str | None = Field(default=None, pattern=SUPPORTED_COUNTRY_PATTERN)
    timezone: str | None = None
    status: str | None = Field(default=None, pattern='^(trial|active|suspended|churned)$')


class RetentionPolicyEntry(BaseModel):
    entity: str = Field(
        pattern='^(messages|conversations|audit_logs|domain_events|webhook_events_raw|reminder_jobs)$'
    )
    retention_days: int = Field(ge=30, le=10950)
    anonymize_instead_of_delete: bool = False


class RetentionPoliciesUpdate(BaseModel):
    policies: list[RetentionPolicyEntry]


class DigestSubscriptionCreate(BaseModel):
    recipient_email: str | None = Field(default=None, max_length=320)
    recipient_whatsapp: str | None = Field(default=None, max_length=32)
    cadence: str = Field(pattern='^(daily|weekly)$')
    enabled: bool = True


class DigestSubscriptionUpdate(BaseModel):
    recipient_email: str | None = Field(default=None, max_length=320)
    recipient_whatsapp: str | None = Field(default=None, max_length=32)
    cadence: str | None = Field(default=None, pattern='^(daily|weekly)$')
    enabled: bool | None = None


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


TENANT_MEMBER_ROLES = ('owner', 'admin', 'manager', 'agent', 'viewer')
TENANT_MEMBER_ROLE_PATTERN = '^(' + '|'.join(TENANT_MEMBER_ROLES) + ')$'


class MemberInvite(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    display_name: str | None = Field(default=None, max_length=160)
    role: str = Field(pattern=TENANT_MEMBER_ROLE_PATTERN)


class MemberRoleUpdate(BaseModel):
    role: str = Field(pattern=TENANT_MEMBER_ROLE_PATTERN)


class TenantStatusTransition(BaseModel):
    status: str = Field(pattern='^(active|suspended|churned)$')
    reason: str = Field(min_length=3, max_length=500)


class ChannelModeUpdate(BaseModel):
    account_mode: str = Field(pattern='^(mock|live)$')
    reason: str = Field(min_length=3, max_length=500)


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




WHATSAPP_TEMPLATE_PURPOSES = (
    'appointment_confirmation',
    'appointment_reminder_24h',
    'appointment_reminder_1h',
    'appointment_reminder_custom',
    'no_show_confirmation_request',
    'no_show_followup',
    'post_appointment_instructions',
    'post_appointment_feedback',
    'post_appointment_rebooking',
    'reschedule_offer',
    'campaign_promo',
    'payment_request',
    'service_recall',
    'custom',
)
WHATSAPP_TEMPLATE_PURPOSE_PATTERN = '^(' + '|'.join(WHATSAPP_TEMPLATE_PURPOSES) + ')$'


class WhatsAppTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=512, pattern=r'^[a-z0-9_]+$')
    locale: str = Field(default='es', min_length=2, max_length=5)
    category: str = Field(pattern='^(utility|marketing|authentication)$')
    purpose: str = Field(pattern=WHATSAPP_TEMPLATE_PURPOSE_PATTERN)
    components: dict[str, Any] = Field(default_factory=dict)
    channel_id: UUID | None = None


class WhatsAppTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=512, pattern=r'^[a-z0-9_]+$')
    locale: str | None = Field(default=None, min_length=2, max_length=5)
    category: str | None = Field(default=None, pattern='^(utility|marketing|authentication)$')
    purpose: str | None = Field(default=None, pattern=WHATSAPP_TEMPLATE_PURPOSE_PATTERN)
    components: dict[str, Any] | None = None
    status: str | None = Field(default=None, pattern='^(draft|pending|approved|rejected|paused)$')
    meta_template_id: str | None = None
    rejection_reason: str | None = None


class ServiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    category: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    price_amount: float | None = Field(default=None, ge=0)
    price_currency: str = Field(default='COP', min_length=3, max_length=3)
    duration_minutes: int = Field(default=60, gt=0, le=1440)
    preparation_notes: str | None = Field(default=None, max_length=2000)
    post_service_notes: str | None = Field(default=None, max_length=2000)
    # TASK-0052: recall interval ("control en N días") and the template that
    # carries the nudge. Both default to null when the service is one-off.
    recall_interval_days: int | None = Field(default=None, gt=0, le=3650)
    recall_template_id: UUID | None = None
    # TASK-0054: dynamic eligibility rule against qualification answers.
    # Empty dict (default) means "always applies".
    applies_when: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    sort_order: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ServiceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    category: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    price_amount: float | None = Field(default=None, ge=0)
    price_currency: str | None = Field(default=None, min_length=3, max_length=3)
    duration_minutes: int | None = Field(default=None, gt=0, le=1440)
    preparation_notes: str | None = Field(default=None, max_length=2000)
    post_service_notes: str | None = Field(default=None, max_length=2000)
    recall_interval_days: int | None = Field(default=None, ge=0, le=3650)
    recall_template_id: UUID | None = None
    applies_when: dict[str, Any] | None = None
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] | None = None


class ServiceReorderItem(BaseModel):
    id: UUID
    sort_order: int = Field(ge=0)


class ServiceReorderRequest(BaseModel):
    order: list[ServiceReorderItem] = Field(default_factory=list)


class BranchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    code: str = Field(min_length=1, max_length=80)
    address: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    country: str = Field(default='CO', min_length=2, max_length=2)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    maps_url: str | None = Field(default=None, max_length=500)
    phone_e164: str | None = Field(default=None, max_length=32)
    timezone: str = Field(default='America/Bogota', min_length=1, max_length=64)
    opening_hours: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    sort_order: int = Field(default=0, ge=0)


class BranchUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    code: str | None = Field(default=None, min_length=1, max_length=80)
    address: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    maps_url: str | None = Field(default=None, max_length=500)
    phone_e164: str | None = Field(default=None, max_length=32)
    timezone: str | None = Field(default=None, min_length=1, max_length=64)
    opening_hours: dict[str, Any] | None = None
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)


PACKAGE_PAYMENT_STATUS_PATTERN = '^(not_required|pending|link_sent|paid|failed|refunded)$'


class TreatmentPackageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    total_sessions: int = Field(gt=0, le=500)
    validity_days: int | None = Field(default=None, gt=0, le=3650)
    price_amount: float = Field(ge=0)
    price_currency: str = Field(default='COP', min_length=3, max_length=3)
    includes_service_ids: list[UUID] = Field(default_factory=list)
    renewal_template_id: UUID | None = None
    is_active: bool = True
    sort_order: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TreatmentPackageUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    total_sessions: int | None = Field(default=None, gt=0, le=500)
    validity_days: int | None = Field(default=None, gt=0, le=3650)
    price_amount: float | None = Field(default=None, ge=0)
    price_currency: str | None = Field(default=None, min_length=3, max_length=3)
    includes_service_ids: list[UUID] | None = None
    renewal_template_id: UUID | None = None
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)
    metadata: dict[str, Any] | None = None


class ContactPackageAssign(BaseModel):
    package_id: UUID
    payment_status: str = Field(default='pending', pattern=PACKAGE_PAYMENT_STATUS_PATTERN)
    payment_amount: float | None = Field(default=None, ge=0)
    payment_currency: str | None = Field(default=None, min_length=3, max_length=3)
    expires_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)


class ContactPackagePatch(BaseModel):
    payment_status: str | None = Field(default=None, pattern=PACKAGE_PAYMENT_STATUS_PATTERN)
    payment_amount: float | None = Field(default=None, ge=0)
    payment_currency: str | None = Field(default=None, min_length=3, max_length=3)
    expires_at: datetime | None = None
    status: str | None = Field(default=None, pattern='^(active|exhausted|expired|refunded)$')
    notes: str | None = Field(default=None, max_length=2000)


class ResourceCreate(BaseModel):
    tenant_id: UUID
    vertical_code: str | None = Field(default=None, max_length=64)
    resource_type: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    capabilities: dict[str, Any] = Field(default_factory=dict)
    bio: str | None = Field(default=None, max_length=2000)
    photo_media_asset_id: UUID | None = None
    specialty: str | None = Field(default=None, max_length=160)
    license_number: str | None = Field(default=None, max_length=80)
    years_of_experience: int | None = Field(default=None, ge=0, le=99)
    public_profile: bool = True
    branch_id: UUID | None = None
    is_active: bool = True


class ResourceUpdate(BaseModel):
    vertical_code: str | None = Field(default=None, max_length=64)
    resource_type: str | None = Field(default=None, min_length=1, max_length=64)
    code: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    capabilities: dict[str, Any] | None = None
    bio: str | None = Field(default=None, max_length=2000)
    photo_media_asset_id: UUID | None = None
    specialty: str | None = Field(default=None, max_length=160)
    license_number: str | None = Field(default=None, max_length=80)
    years_of_experience: int | None = Field(default=None, ge=0, le=99)
    public_profile: bool | None = None
    branch_id: UUID | None = None
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
    service_id: UUID | None = None
    notes: str | None = None




class AppointmentUpdate(BaseModel):
    resource_id: UUID | None = None
    service_code: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: str | None = Field(default=None, pattern='^(scheduled|confirmed|completed|cancelled|no_show)$')
    confirmation_status: str | None = Field(default=None, pattern='^(pending|confirmed|declined)$')
    notes: str | None = None


class AppointmentPaymentLinkRequest(BaseModel):
    amount: float | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    description: str | None = Field(default=None, max_length=200)


class AppointmentPaymentStatusUpdate(BaseModel):
    payment_status: str = Field(pattern='^(not_required|pending|link_sent|paid|failed|refunded)$')
    payment_amount: float | None = Field(default=None, ge=0)
    payment_currency: str | None = Field(default=None, min_length=3, max_length=3)


class TenantPaymentSettingsUpdate(BaseModel):
    provider: str = Field(pattern='^(mercadopago|stripe|none)$')
    currency: str = Field(default='COP', min_length=3, max_length=3)
    default_amount: float | None = Field(default=None, ge=0)
    api_key: str | None = Field(default=None, max_length=500)
    webhook_secret: str | None = Field(default=None, max_length=500)


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


class ContactTagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    color: str | None = Field(default=None, pattern=r'^#[0-9a-fA-F]{6}$')
    description: str | None = Field(default=None, max_length=500)


class ContactTagUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    color: str | None = Field(default=None, pattern=r'^#[0-9a-fA-F]{6}$')
    description: str | None = Field(default=None, max_length=500)


class ContactTagAssign(BaseModel):
    tag_ids: list[UUID] = Field(default_factory=list)


class ContactNoteCreate(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


class CampaignSegmentFilter(BaseModel):
    tags: list[UUID] | None = None
    min_appointments: int | None = Field(default=None, ge=0)
    last_visit_before_days: int | None = Field(default=None, ge=0)
    last_visit_after_days: int | None = Field(default=None, ge=0)
    has_upcoming_appointment: bool | None = None


class CampaignCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    template_id: UUID
    template_variables: dict[str, Any] = Field(default_factory=dict)
    segment_filter: CampaignSegmentFilter = Field(default_factory=CampaignSegmentFilter)
    segment_id: UUID | None = None
    scheduled_at: datetime | None = None
    cost_amount: float | None = Field(default=None, ge=0)
    cost_currency: str | None = Field(default=None, min_length=3, max_length=3)
    attribution_window_days: int | None = Field(default=None, ge=1, le=90)


class CampaignUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    template_id: UUID | None = None
    template_variables: dict[str, Any] | None = None
    segment_filter: CampaignSegmentFilter | None = None
    segment_id: UUID | None = None
    scheduled_at: datetime | None = None
    cost_amount: float | None = Field(default=None, ge=0)
    cost_currency: str | None = Field(default=None, min_length=3, max_length=3)
    attribution_window_days: int | None = Field(default=None, ge=1, le=90)


SEGMENT_KIND_PATTERN = '^(dynamic|static)$'


class ContactSegmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    kind: str = Field(default='dynamic', pattern=SEGMENT_KIND_PATTERN)
    rules: dict[str, Any] = Field(default_factory=dict)


class ContactSegmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    kind: str | None = Field(default=None, pattern=SEGMENT_KIND_PATTERN)
    rules: dict[str, Any] | None = None


class ContactSegmentMembersAssign(BaseModel):
    contact_ids: list[UUID] = Field(default_factory=list, max_length=10000)


class CampaignLaunch(BaseModel):
    scheduled_at: datetime | None = None


class WebChannelUpsert(BaseModel):
    enabled: bool = True
    allowed_origins: list[str] = Field(default_factory=list)
    primary_color: str | None = Field(default=None, pattern=r'^#[0-9a-fA-F]{6}$')
    greeting: str | None = Field(default=None, max_length=500)
    # TASK-0070: customisation surfaced by the CDN-distributed widget snippet.
    logo_url: str | None = Field(default=None, max_length=2048)
    welcome_copy: str | None = Field(default=None, max_length=500)
    button_position: str | None = Field(default=None, pattern=r'^(left|right)$')
    rotate_widget_token: bool = False


class WebChatStart(BaseModel):
    tenant_slug: str = Field(min_length=1, max_length=160)
    widget_token: str = Field(min_length=8, max_length=512)
    name: str = Field(min_length=1, max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    email: str | None = Field(default=None, max_length=320)
    message: str = Field(min_length=1, max_length=4000)
    utm_source: str | None = Field(default=None, max_length=160)
    utm_medium: str | None = Field(default=None, max_length=160)
    utm_campaign: str | None = Field(default=None, max_length=160)
    referrer: str | None = Field(default=None, max_length=2048)
    # TASK-0055: optional UUID of the contact who referred this lead, sourced
    # from ``data-ref`` or ``?ref=`` on the embedding page.
    referrer_contact_id: UUID | None = Field(default=None)


class WebChatMessage(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


QUALIFICATION_QUESTION_KINDS = (
    'free_text',
    'single_choice',
    'multi_choice',
    'yes_no',
    'number',
)
QUALIFICATION_QUESTION_KIND_PATTERN = '^(' + '|'.join(QUALIFICATION_QUESTION_KINDS) + ')$'
QUALIFICATION_QUESTION_PRESETS = ('budget_tier', 'urgency_level')
QUALIFICATION_QUESTION_PRESET_PATTERN = '^(' + '|'.join(QUALIFICATION_QUESTION_PRESETS) + ')$'
# TASK-0054: human-readable key for service_catalog.applies_when rules.
QUALIFICATION_QUESTION_KEY_PATTERN = '^[a-z][a-z0-9_]{0,59}$'
URGENCY_NORMALIZED_VALUES = ('emergency', 'high', 'normal', 'low')
URGENCY_NORMALIZED_PATTERN = '^(' + '|'.join(URGENCY_NORMALIZED_VALUES) + ')$'


class QualificationOption(BaseModel):
    value: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=120)
    service_id: UUID | None = None
    tier_value: float | None = Field(default=None, ge=0)
    urgency_normalized: str | None = Field(default=None, pattern=URGENCY_NORMALIZED_PATTERN)


class QualificationQuestionCreate(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    kind: str = Field(pattern=QUALIFICATION_QUESTION_KIND_PATTERN)
    options: list[QualificationOption] = Field(default_factory=list)
    required: bool = True
    position: int = Field(default=0, ge=0)
    applies_to_service_ids: list[UUID] = Field(default_factory=list)
    preset: str | None = Field(default=None, pattern=QUALIFICATION_QUESTION_PRESET_PATTERN)
    # TASK-0054: optional stable key for applies_when rules.
    key: str | None = Field(default=None, pattern=QUALIFICATION_QUESTION_KEY_PATTERN)


class QualificationQuestionUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    kind: str | None = Field(default=None, pattern=QUALIFICATION_QUESTION_KIND_PATTERN)
    options: list[QualificationOption] | None = None
    required: bool | None = None
    position: int | None = Field(default=None, ge=0)
    applies_to_service_ids: list[UUID] | None = None
    preset: str | None = Field(default=None, pattern=QUALIFICATION_QUESTION_PRESET_PATTERN)
    key: str | None = Field(default=None, pattern=QUALIFICATION_QUESTION_KEY_PATTERN)


class QualificationReorderItem(BaseModel):
    id: UUID
    position: int = Field(ge=0)


class QualificationReorderRequest(BaseModel):
    order: list[QualificationReorderItem] = Field(default_factory=list)


MEDIA_KINDS = ('image', 'video', 'pdf', 'audio')
MEDIA_KIND_PATTERN = '^(' + '|'.join(MEDIA_KINDS) + ')$'


class MediaAssetUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    tags: list[str] | None = Field(default=None, max_length=20)


class PromotionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    media_asset_id: UUID | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    applies_to_service_ids: list[UUID] = Field(default_factory=list)
    coupon_code: str | None = Field(default=None, max_length=80)
    discount_percent: float | None = Field(default=None, ge=0, le=100)
    is_active: bool = True
    sort_order: int = Field(default=0, ge=0)


class PromotionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    media_asset_id: UUID | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    applies_to_service_ids: list[UUID] | None = None
    coupon_code: str | None = Field(default=None, max_length=80)
    discount_percent: float | None = Field(default=None, ge=0, le=100)
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0)


class PromptCreate(BaseModel):
    tenant_id: UUID | None = None
    vertical_code: str = 'common'
    prompt_type: str
    name: str
    version: int = 1
    content: str
    variables: list[str] = Field(default_factory=list)
