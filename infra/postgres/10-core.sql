-- ============================================================================
-- Core schema — TRANSVERSAL (cargado siempre en bootstrap)
-- ============================================================================
-- Contiene:
--   * schema 'app.*' (identidad, tenants, usuarios, sesiones, contactos,
--     mensajes, citas, etc. — funcional para el chatbot base)
--   * RLS helpers (current_tenant_id, support_mode, touch_updated_at)
--   * app.tenant_modules (control de activación de módulos opt-in)
--   * app.platform_secrets + app.platform_ai_providers (IA transversal)
-- Los modules opt-in (influencer, gd) viven en infra/postgres/modules/*.sql
-- y se cargan via bootstrap.sh --module=<name>.
-- ============================================================================

create extension if not exists pgcrypto;
create extension if not exists citext;
create extension if not exists vector;
create extension if not exists btree_gist;

create schema if not exists app;

create or replace function app.current_tenant_id()
returns uuid language sql stable as $$
  select nullif(current_setting('app.tenant_id', true), '')::uuid
$$;

create or replace function app.support_mode()
returns boolean language sql stable as $$
  select coalesce(current_setting('app.support_mode', true), 'false') = 'true'
$$;

create or replace function app.touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table app.tenants (
  id uuid primary key default gen_random_uuid(),
  slug citext not null unique,
  legal_name text not null,
  display_name text not null,
  vertical_code text not null,
  business_type_label text,
  country_code char(2) not null default 'CO' check (country_code in ('CO','MX','AR','CL','PE','EC','UY')),
  timezone text not null default 'America/Bogota',
  status text not null default 'trial' check (status in ('trial','active','suspended','churned')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);

create table app.tenant_settings (
  tenant_id uuid primary key references app.tenants(id) on delete cascade,
  locale text not null default 'es-CO',
  currency char(3) not null default 'COP',
  business_hours jsonb not null default '{}'::jsonb,
  escalation_policy jsonb not null default '{}'::jsonb,
  pii_policy jsonb not null default '{"no_train":true}'::jsonb,
  no_train boolean not null default true,
  knowledge_storage jsonb not null default '{}'::jsonb,
  notification_settings jsonb not null default '{}'::jsonb,
  payment_settings jsonb not null default '{}'::jsonb,
  onboarding_progress jsonb not null default '{"last_completed_step":0,"steps":{}}'::jsonb,
  bot_personality jsonb not null default '{"tone":"neutral","formality":"tu","emoji_level":"moderate","custom_persona":""}'::jsonb,
  -- TASK-UI-012-FU: per-tenant brand logo URL, populated by
  -- ``POST /v1/tenants/{tenant_id}/branding/logo``. Stored as the public
  -- ``source_uri`` returned by ``store_media_file()`` so the shell can render
  -- it directly. Nullable: tenants without a custom logo fall back to
  -- generated initials in the admin panel (TenantBrandLogo component).
  brand_logo_url text null,
  -- TASK-UI-016.1-FU: timestamp captured when the tenant owner marks the
  -- tenant as live in production via ``POST /v1/tenants/{tenant_id}/go-live``.
  -- NULL = never marked live (still in trial / pre-launch). Once set, the
  -- tenant is in production mode; subsequent calls are idempotent and do
  -- not overwrite the original timestamp.
  go_live_at timestamptz null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint tenant_settings_brand_logo_url_len check (
    brand_logo_url is null or length(brand_logo_url) <= 1024
  )
);

-- TASK-UI-012-FU: brand_logo_url column for per-tenant branding logo.
-- For existing databases, run once:
--   alter table app.tenant_settings add column if not exists brand_logo_url text null;
--   alter table app.tenant_settings add constraint tenant_settings_brand_logo_url_len
--     check (brand_logo_url is null or length(brand_logo_url) <= 1024);

-- TASK-UI-016.1-FU: go_live_at timestamp captures when the owner marks the
-- tenant as live in production. NULL = never marked. Once set, "marking
-- again" is idempotent (preserves the original timestamp). For existing
-- databases, run once:
--   alter table app.tenant_settings add column if not exists go_live_at timestamptz null;

create table app.tenant_channels (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  provider text not null check (provider in ('whatsapp_cloud_api','web','instagram_messenger','facebook_messenger')),
  business_id text,
  waba_id text,
  phone_number_id text,
  whatsapp_business_profile_id text,
  solution_id text,
  display_phone_number text,
  page_id text,
  instagram_account_id text,
  allowed_origins text[] not null default '{}',
  widget_config jsonb not null default '{}'::jsonb,
  token_ref text not null,
  app_secret_ref text,
  verify_token_hash bytea,
  quality_rating text,
  messaging_limit_tier text,
  account_mode text not null default 'mock' check (account_mode in ('mock','live')),
  status text not null default 'provisioning' check (status in ('provisioning','active','degraded','suspended','offboarded')),
  service_window_hours integer not null default 24 check (service_window_hours > 0),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, provider)
);
create index ix_tenant_channels_phone on app.tenant_channels(phone_number_id);
-- TASK-0081 / BUG21: enforce that a given Meta phone_number_id can only be
-- bound to ONE active tenant channel at a time. Without this constraint, a
-- malicious tenant could re-register another tenant's phone_number_id and the
-- webhook handler would route inbound traffic + signature verification to the
-- attacker's row.
create unique index ux_tenant_channels_phone_number_active
  on app.tenant_channels(phone_number_id)
  where status='active' and phone_number_id is not null;
create index ix_tenant_channels_waba on app.tenant_channels(waba_id);
-- BUG-064: misma defensa que ux_tenant_channels_phone_number_active para
-- los identificadores de Meta Facebook Page e Instagram Account. Sin
-- unique partial index, dos tenants pueden reclamar el mismo page_id /
-- instagram_account_id y el webhook router atura inbound al tenant
-- equivocado (la query usa `where page_id=$1 and status='active'` y
-- devuelve el primero ordenado por updated_at — vector de hijack).
create unique index ux_tenant_channels_page_active
  on app.tenant_channels(page_id)
  where status='active' and page_id is not null;
create unique index ux_tenant_channels_ig_account_active
  on app.tenant_channels(instagram_account_id)
  where status='active' and instagram_account_id is not null;
-- Mantenemos los índices no-únicos también — sirven para queries que
-- filtran por id sin importar el status (ej. troubleshooting de canales
-- archivados).
create index ix_tenant_channels_page on app.tenant_channels(page_id) where page_id is not null;
create index ix_tenant_channels_ig_account on app.tenant_channels(instagram_account_id) where instagram_account_id is not null;

create table app.users (
  id uuid primary key default gen_random_uuid(),
  auth_subject text not null unique,
  email citext not null unique,
  display_name text not null,
  status text not null default 'active' check (status in ('active','invited','suspended')),
  mfa_enabled boolean not null default false,
  last_login_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table app.user_tenant_roles (
  user_id uuid not null references app.users(id) on delete cascade,
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  role text not null check (role in ('owner','admin','manager','agent','viewer','support')),
  scopes text[] not null default '{}',
  is_default boolean not null default false,
  created_at timestamptz not null default now(),
  primary key (user_id, tenant_id, role)
);
create index ix_user_tenant_roles_tenant on app.user_tenant_roles(tenant_id, role);

-- TASK-UI-016.7-FU: user preferences (per-user, not per-tenant).
-- name/email/phone are cached from Auth0 (their identity layer) with a refresh
-- timestamp (`auth0_synced_at`); locale/timezone/theme_override/notification_matrix
-- are app-managed. The PK is `user_id` (FK -> app.users.id, which stores the
-- Auth0 `sub` as `auth_subject`). For existing deployments:
--   create table if not exists app.user_preferences (...);
--   create trigger if not exists trg_user_preferences_touch ...
create table app.user_preferences (
  user_id uuid primary key references app.users(id) on delete cascade,
  display_name text null,
  phone text null,
  locale text null default 'es-CO',
  timezone text null default 'America/Bogota',
  theme_override text null check (theme_override is null or theme_override in ('auto','light','dark')),
  notification_matrix jsonb not null default '{}'::jsonb,
  auth0_synced_at timestamptz null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- TASK-UI-016.7-FU-SESSIONS: server-side session store.
-- Cierra el follow-up declarado en UI-016.7-FU: los endpoints
-- `/v1/me/sessions` y `/v1/me/sessions/{sid}` vivían como stubs porque no
-- existía esta tabla. Ahora cada request autenticada upsertea su sesión por
-- `id` (jti del JWT cuando Auth0 lo emite; fallback determinístico hash
-- estable basado en `sub + iat` cuando no), refrescando `last_seen_at`. Al
-- DELETE marcamos `revoked_at` y el GET filtra `revoked_at is null`. El FK a
-- `app.users(id)` se cascadea (si el usuario se borra, sus sesiones también).
-- Para deployments existentes:
--   create table if not exists app.auth_sessions (...);
--   create index if not exists ix_auth_sessions_user_active ...
--   create trigger if not exists trg_auth_sessions_touch ...
create table app.auth_sessions (
  id text primary key,
  user_id uuid not null references app.users(id) on delete cascade,
  device text null,
  user_agent text null,
  ip inet null,
  location text null,
  created_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  revoked_at timestamptz null,
  updated_at timestamptz not null default now()
);
create index ix_auth_sessions_user_active on app.auth_sessions(user_id, last_seen_at desc) where revoked_at is null;

create table app.contacts (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  wa_id text not null,
  phone_e164 text not null,
  phone_hash bytea not null,
  display_name text,
  locale text default 'es-CO',
  source text,
  opt_in_status text not null default 'unknown' check (opt_in_status in ('unknown','granted','revoked','suppressed')),
  opt_in_at timestamptz,
  opt_out_at timestamptz,
  consent_version int not null default 1,
  tags text[] not null default '{}',
  metadata jsonb not null default '{}'::jsonb,
  lead_source jsonb not null default '{}'::jsonb,
  qualification jsonb not null default '{}'::jsonb,
  referrer_contact_id uuid,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, wa_id),
  unique (tenant_id, phone_e164),
  constraint chk_contacts_referrer_not_self check (referrer_contact_id is null or referrer_contact_id <> id)
);
create index ix_contacts_tenant_phone on app.contacts(tenant_id, phone_e164);
create index gin_contacts_tags on app.contacts using gin(tags);
create index gin_contacts_lead_source on app.contacts using gin(lead_source);
create index ix_contacts_tenant_referrer on app.contacts(tenant_id, referrer_contact_id) where referrer_contact_id is not null;

create table app.conversations (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  contact_id uuid not null references app.contacts(id) on delete cascade,
  channel_id uuid not null references app.tenant_channels(id) on delete restrict,
  status text not null default 'open' check (status in ('open','waiting_user','waiting_agent','human_required','human_active','resolved','closed','archived')),
  opened_by text not null default 'user' check (opened_by in ('user','agent','system')),
  current_owner_user_id uuid references app.users(id),
  current_intent text,
  vertical_case_type text,
  handoff_required boolean not null default false,
  service_window_expires_at timestamptz,
  summary text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index ix_conv_tenant_status on app.conversations(tenant_id, status, updated_at desc);
create index ix_conv_contact_open on app.conversations(contact_id, status);
create index gin_conv_metadata on app.conversations using gin(metadata);

create table app.messages (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  conversation_id uuid not null references app.conversations(id) on delete cascade,
  external_message_id text,
  direction text not null check (direction in ('inbound','outbound')),
  sender_actor_type text not null check (sender_actor_type in ('contact','bot','agent','system')),
  sender_actor_id text,
  message_type text not null default 'text' check (message_type in ('text','image','audio','video','document','interactive','template','system')),
  body_text text,
  media_id text,
  mime_type text,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'received' check (status in ('received','queued','sent','delivered','read','failed')),
  received_at timestamptz,
  sent_at timestamptz,
  delivered_at timestamptz,
  read_at timestamptz,
  failed_at timestamptz,
  error_code text,
  error_message text,
  reply_to_external_message_id text,
  campaign_id uuid,
  -- SEC-010 (DLQ retry idempotency): contador estable de re-encolados manuales del
  -- DLQ. El handler `outbound_dlq.requeue_message` lo incrementa atomicamente con
  -- `UPDATE ... WHERE status='failed' RETURNING retry_count` y deriva el
  -- idempotency_key del domain_event de `(message_id, retry_count)` para que dos
  -- requeues concurrentes del MISMO mensaje no puedan emitir 2 eventos distintos.
  retry_count integer not null default 0,
  created_at timestamptz not null default now(),
  unique (tenant_id, external_message_id)
);
create index ix_messages_conversation_time on app.messages(conversation_id, created_at);
create index ix_messages_tenant_status on app.messages(tenant_id, status);

create table app.message_status_events (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  message_id uuid references app.messages(id) on delete set null,
  external_message_id text not null,
  status text not null,
  recipient_id text,
  conversation_external_id text,
  pricing_category text,
  billable boolean,
  errors jsonb not null default '[]'::jsonb,
  raw_payload jsonb not null,
  occurred_at timestamptz not null default now()
);
create index ix_message_status_external on app.message_status_events(external_message_id);

-- TASK-0050: branches (multi-sede) - cada tenant puede tener varias ubicaciones.
create table app.branches (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  name text not null,
  code text not null,
  address text,
  city text,
  state text,
  country char(2) not null default 'CO',
  lat numeric(10,7),
  lng numeric(10,7),
  maps_url text,
  phone_e164 text,
  timezone text not null default 'America/Bogota',
  opening_hours jsonb not null default '{}'::jsonb,
  is_active boolean not null default true,
  sort_order int not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, code)
);
create index ix_branches_tenant_active on app.branches(tenant_id, is_active, sort_order);

create table app.resources (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  vertical_code text not null,
  resource_type text not null,
  code text not null,
  name text not null,
  capabilities jsonb not null default '{}'::jsonb,
  bio text,
  photo_media_asset_id uuid,
  specialty text,
  license_number text,
  years_of_experience int check (years_of_experience is null or years_of_experience >= 0),
  public_profile boolean not null default true,
  branch_id uuid,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, code)
);
create index ix_resources_branch on app.resources(tenant_id, branch_id) where branch_id is not null;
create index ix_resources_type on app.resources(tenant_id, resource_type);
create index ix_resources_public on app.resources(tenant_id, public_profile, is_active);

create table app.service_catalog (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  category text,
  name text not null,
  description text,
  price_amount numeric(10,2),
  price_currency char(3) not null default 'COP',
  duration_minutes int not null default 60 check (duration_minutes > 0),
  preparation_notes text,
  post_service_notes text,
  -- TASK-0052: per-service recall ("control en N días") configuration. When
  -- recall_interval_days is null, no recall is scheduled. The template, if set,
  -- must point at an approved whatsapp_templates row with purpose='service_recall'.
  recall_interval_days int check (recall_interval_days is null or recall_interval_days > 0),
  recall_template_id uuid,
  -- TASK-0054: dynamic eligibility rule evaluated against the conversation's
  -- qualification answers. Empty object means "always applies". Shape mirrors
  -- the segment rules normalizer in app.services.segments (all_of / any_of of
  -- {key, op, value} predicates).
  applies_when jsonb not null default '{}'::jsonb,
  is_active boolean not null default true,
  sort_order int not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index ix_service_catalog_tenant_active on app.service_catalog(tenant_id, is_active, sort_order);

create table app.service_requests (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  contact_id uuid not null references app.contacts(id) on delete restrict,
  conversation_id uuid references app.conversations(id) on delete set null,
  vertical_code text not null,
  service_type text not null,
  asset_type text,
  asset_brand text,
  asset_model text,
  problem_summary text,
  location_address text,
  location_lat numeric(10,7),
  location_lng numeric(10,7),
  urgency text not null default 'normal' check (urgency in ('low','normal','high','emergency')),
  preferred_date date,
  preferred_slot text,
  status text not null default 'open' check (status in ('open','qualified','quoted','scheduled','cancelled','resolved')),
  intake jsonb not null default '{}'::jsonb,
  assigned_resource_id uuid references app.resources(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index ix_service_requests_status on app.service_requests(tenant_id, status, created_at);
create index gin_service_requests_intake on app.service_requests using gin(intake);

create table app.quotes (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  service_request_id uuid not null references app.service_requests(id) on delete cascade,
  currency char(3) not null default 'COP',
  subtotal numeric(14,2) not null default 0,
  discount_total numeric(14,2) not null default 0,
  tax_total numeric(14,2) not null default 0,
  grand_total numeric(14,2) not null default 0,
  line_items jsonb not null default '[]'::jsonb,
  status text not null default 'draft' check (status in ('draft','sent','accepted','rejected','expired')),
  valid_until timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, service_request_id)
);
create index ix_quotes_status on app.quotes(tenant_id, status);

create table app.appointments (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  contact_id uuid not null references app.contacts(id) on delete restrict,
  conversation_id uuid references app.conversations(id) on delete set null,
  service_request_id uuid references app.service_requests(id) on delete set null,
  service_id uuid references app.service_catalog(id) on delete set null,
  resource_id uuid not null references app.resources(id) on delete restrict,
  service_code text not null,
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  timezone text not null default 'America/Bogota',
  status text not null default 'scheduled' check (status in ('scheduled','confirmed','completed','cancelled','no_show')),
  location_type text not null default 'onsite' check (location_type in ('onsite','customer_location','virtual')),
  location_data jsonb not null default '{}'::jsonb,
  confirmation_status text not null default 'pending' check (confirmation_status in ('pending','confirmed','declined')),
  notes text,
  payment_status text not null default 'not_required' check (payment_status in ('not_required','pending','link_sent','paid','failed','refunded')),
  payment_amount numeric(10,2),
  payment_currency char(3) not null default 'COP',
  payment_link text,
  payment_provider text,
  payment_provider_reference text,
  payment_link_generated_at timestamptz,
  payment_link_sent_at timestamptz,
  payment_paid_at timestamptz,
  branch_id uuid,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (starts_at < ends_at),
  exclude using gist (resource_id with =, tstzrange(starts_at, ends_at, '[)') with &&) where (status in ('scheduled','confirmed'))
);
create index ix_appointments_payment_ref on app.appointments(tenant_id, payment_provider, payment_provider_reference) where payment_provider_reference is not null;
create index ix_appointments_payment_status on app.appointments(tenant_id, payment_status);
create index ix_appointments_tenant_starts on app.appointments(tenant_id, starts_at);
create index ix_appointments_contact_status on app.appointments(contact_id, status);
create index ix_appointments_branch on app.appointments(tenant_id, branch_id, starts_at) where branch_id is not null;
create index ix_appointments_closed_by on app.appointments(tenant_id, (metadata->>'closed_by_user_id'))
  where metadata ? 'closed_by_user_id';

create table app.whatsapp_templates (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  channel_id uuid references app.tenant_channels(id) on delete set null,
  name text not null,
  locale char(5) not null default 'es',
  category text not null check (category in ('utility','marketing','authentication')),
  status text not null default 'draft' check (status in ('draft','pending','approved','rejected','paused')),
  purpose text not null check (purpose in (
    'appointment_confirmation','appointment_reminder_24h','appointment_reminder_1h',
    'appointment_reminder_custom','no_show_confirmation_request','no_show_followup',
    'post_appointment_instructions','post_appointment_feedback','post_appointment_rebooking',
    'reschedule_offer','campaign_promo','payment_request','service_recall',
    'subscription_payment_failed',
    'consent_request','consent_reaffirm','custom'
  )),
  components jsonb not null default '{}'::jsonb,
  meta_template_id text,
  rejection_reason text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, name, locale)
);
create index ix_whatsapp_templates_tenant_purpose on app.whatsapp_templates(tenant_id, purpose, status);

create table app.appointment_feedback (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  appointment_id uuid not null references app.appointments(id) on delete cascade,
  contact_id uuid not null references app.contacts(id) on delete cascade,
  rating int not null check (rating between 1 and 5),
  comment text,
  created_at timestamptz not null default now()
);
create index ix_appointment_feedback_tenant on app.appointment_feedback(tenant_id, created_at desc);

create table app.contact_tags (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  name text not null,
  color varchar(7),
  description text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, name)
);
create index ix_contact_tags_tenant on app.contact_tags(tenant_id, name);

create table app.contact_tag_assignments (
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  contact_id uuid not null references app.contacts(id) on delete cascade,
  tag_id uuid not null references app.contact_tags(id) on delete cascade,
  assigned_by uuid references app.users(id) on delete set null,
  assigned_at timestamptz not null default now(),
  primary key (contact_id, tag_id)
);
create index ix_contact_tag_assignments_tag on app.contact_tag_assignments(tag_id);
create index ix_contact_tag_assignments_tenant on app.contact_tag_assignments(tenant_id);

create table app.contact_notes (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  contact_id uuid not null references app.contacts(id) on delete cascade,
  body text not null,
  created_by uuid references app.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index ix_contact_notes_contact on app.contact_notes(tenant_id, contact_id, created_at desc);

create table app.qualification_questions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  position int not null default 0,
  label text not null,
  -- TASK-0054: optional stable identifier used by service_catalog.applies_when
  -- rules. Must be snake_case ([a-z0-9_]+) so admins can write predicates like
  -- {key:'first_visit', op:'eq', value:true} without juggling UUIDs.
  key text check (key is null or key ~ '^[a-z][a-z0-9_]{0,59}$'),
  kind text not null check (kind in ('free_text','single_choice','multi_choice','yes_no','number')),
  options jsonb not null default '[]'::jsonb,
  required boolean not null default true,
  applies_to_service_ids uuid[] not null default '{}',
  preset text check (preset is null or preset in ('budget_tier','urgency_level')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index ix_qualification_questions_tenant on app.qualification_questions(tenant_id, position);
create unique index uq_qualification_questions_tenant_key
  on app.qualification_questions(tenant_id, key) where key is not null;

create table app.media_assets (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  kind text not null check (kind in ('image','video','pdf','audio')),
  label text not null,
  description text,
  storage_backend text not null check (storage_backend in ('local','s3')),
  storage_bucket text,
  object_key text not null,
  source_uri text not null,
  mime_type text not null,
  sha256 text not null,
  size_bytes bigint not null check (size_bytes > 0),
  tags text[] not null default '{}',
  uploaded_by_user_id uuid references app.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index ix_media_assets_tenant on app.media_assets(tenant_id, created_at desc);
create index gin_media_assets_tags on app.media_assets using gin(tags);

create table app.promotions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  name text not null,
  description text,
  media_asset_id uuid references app.media_assets(id) on delete set null,
  valid_from timestamptz,
  valid_until timestamptz,
  applies_to_service_ids uuid[] not null default '{}',
  coupon_code text,
  discount_percent numeric(5,2),
  is_active boolean not null default true,
  sort_order int not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (valid_from is null or valid_until is null or valid_from <= valid_until)
);
create index ix_promotions_tenant_active on app.promotions(tenant_id, is_active, sort_order);
create index gin_promotions_services on app.promotions using gin(applies_to_service_ids);

create table app.campaigns (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  name text not null,
  status text not null default 'draft' check (status in ('draft','scheduled','running','completed','cancelled')),
  template_id uuid references app.whatsapp_templates(id) on delete restrict,
  template_variables jsonb not null default '{}'::jsonb,
  segment_filter jsonb not null default '{}'::jsonb,
  segment_id uuid,
  launched_snapshot_at timestamptz,
  scheduled_at timestamptz,
  recipient_count int not null default 0,
  sent_count int not null default 0,
  delivered_count int not null default 0,
  read_count int not null default 0,
  failed_count int not null default 0,
  started_at timestamptz,
  completed_at timestamptz,
  cost_amount numeric(12,2),
  cost_currency char(3) not null default 'COP',
  attribution_window_days int not null default 14 check (attribution_window_days between 1 and 90),
  created_by uuid references app.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index ix_campaigns_tenant_status on app.campaigns(tenant_id, status, scheduled_at);
create index ix_campaigns_due on app.campaigns(scheduled_at) where status='scheduled';

create table app.campaign_attributions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  campaign_id uuid not null,
  contact_id uuid not null,
  appointment_id uuid not null,
  attributed_at timestamptz not null default now(),
  unique (tenant_id, appointment_id)
);
create index ix_campaign_attributions_campaign on app.campaign_attributions(tenant_id, campaign_id, attributed_at desc);
create index ix_campaign_attributions_contact on app.campaign_attributions(tenant_id, contact_id);

create table app.contact_segments (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  name text not null,
  description text,
  kind text not null default 'dynamic' check (kind in ('dynamic','static')),
  rules jsonb not null default '{}'::jsonb,
  contact_count int not null default 0,
  last_refreshed_at timestamptz,
  is_system boolean not null default false,
  created_by uuid references app.users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, name)
);
create index ix_contact_segments_tenant on app.contact_segments(tenant_id, kind);
create index ix_contact_segments_refresh on app.contact_segments(last_refreshed_at) where kind='dynamic';

create table app.contact_segment_members (
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  segment_id uuid not null references app.contact_segments(id) on delete cascade,
  contact_id uuid not null references app.contacts(id) on delete cascade,
  snapshot_at timestamptz not null default now(),
  primary key (segment_id, contact_id, snapshot_at)
);
create index ix_contact_segment_members_segment on app.contact_segment_members(segment_id, snapshot_at desc);
create index ix_contact_segment_members_tenant on app.contact_segment_members(tenant_id);

create table app.reminder_jobs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  -- BUG-134: 'contact' agregado al check para que el consent reaffirm job
  -- (insert en app/services/consent.py::enqueue_consent_reaffirm_jobs) no
  -- viole el constraint. El reaffirm es un reminder standalone sin
  -- appointment/quote/service_request asociado — el target es el contact mismo.
  target_type text not null check (target_type in ('appointment','quote','service_request','conversation','contact_subscription','contact')),
  target_id uuid not null,
  channel_id uuid references app.tenant_channels(id) on delete set null,
  template_name text not null,
  template_locale text not null default 'es_CO',
  payload jsonb not null default '{}'::jsonb,
  scheduled_for timestamptz not null,
  status text not null default 'pending' check (status in ('pending','processing','sent','failed','cancelled')),
  retry_count integer not null default 0,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index ix_reminder_jobs_due on app.reminder_jobs(scheduled_for, status);

-- TASK-0051: treatment packages / multi-session plans.
create table app.treatment_packages (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  name text not null,
  description text,
  total_sessions int not null check (total_sessions > 0),
  validity_days int check (validity_days is null or validity_days > 0),
  price_amount numeric(10,2) not null check (price_amount >= 0),
  price_currency char(3) not null default 'COP',
  includes_service_ids uuid[] not null default '{}',
  renewal_template_id uuid,
  is_active boolean not null default true,
  sort_order int not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index ix_treatment_packages_tenant_active
  on app.treatment_packages(tenant_id, is_active, sort_order);
create index gin_treatment_packages_services
  on app.treatment_packages using gin(includes_service_ids);

create table app.contact_packages (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  contact_id uuid not null references app.contacts(id) on delete restrict,
  package_id uuid not null references app.treatment_packages(id) on delete restrict,
  purchased_at timestamptz not null default now(),
  expires_at timestamptz,
  remaining_sessions int not null check (remaining_sessions >= 0),
  total_sessions int not null check (total_sessions > 0),
  status text not null default 'active' check (status in ('active','exhausted','expired','refunded')),
  payment_status text not null default 'pending'
    check (payment_status in ('not_required','pending','link_sent','paid','failed','refunded')),
  payment_amount numeric(10,2),
  payment_currency char(3) not null default 'COP',
  payment_link text,
  payment_provider text,
  payment_provider_reference text,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index ix_contact_packages_contact_active
  on app.contact_packages(tenant_id, contact_id, status);
create index ix_contact_packages_expiry
  on app.contact_packages(expires_at) where status='active' and expires_at is not null;

-- TASK-0075: recurring subscriptions / memberships.
create table app.subscription_plans (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  name text not null,
  description text,
  billing_period text not null check (billing_period in ('monthly','quarterly','yearly')),
  price_amount numeric(10,2) not null check (price_amount >= 0),
  currency char(3) not null default 'COP',
  included_services jsonb not null default '[]'::jsonb,
  status text not null default 'active' check (status in ('active','archived')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index ix_subscription_plans_tenant_status
  on app.subscription_plans(tenant_id, status, name);

create table app.contact_subscriptions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  contact_id uuid not null references app.contacts(id) on delete restrict,
  plan_id uuid not null references app.subscription_plans(id) on delete restrict,
  status text not null default 'active' check (status in ('active','past_due','cancelled')),
  started_at timestamptz not null default now(),
  next_billing_at timestamptz,
  cancelled_at timestamptz,
  payment_provider text not null check (payment_provider in ('mercadopago','stripe')),
  payment_provider_subscription_id text,
  payment_method_id text,
  last_invoice_status text,
  last_invoice_at timestamptz,
  retry_payment_link text,
  -- BUG-112: snapshot del precio vigente al momento del subscribe. Las queries
  -- de MRR usan `coalesce(cs.price_locked_amount, sp.price_amount)` para que
  -- subir el precio del plan NO altere retroactivamente el MRR ni la factura
  -- de los suscriptores existentes (cada uno mantiene su precio "locked-in").
  price_locked_amount numeric(12,2),
  price_locked_currency text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index ix_contact_subscriptions_tenant_status
  on app.contact_subscriptions(tenant_id, status, next_billing_at);
create index ix_contact_subscriptions_contact
  on app.contact_subscriptions(tenant_id, contact_id, status);
create unique index ux_contact_subscriptions_provider_ref
  on app.contact_subscriptions(payment_provider, payment_provider_subscription_id)
  where payment_provider_subscription_id is not null;

create table app.appointment_package_links (
  appointment_id uuid not null,
  contact_package_id uuid not null references app.contact_packages(id) on delete restrict,
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  consumed_at timestamptz,
  created_at timestamptz not null default now(),
  primary key (appointment_id)
);
create index ix_appointment_package_links_pkg
  on app.appointment_package_links(contact_package_id);

create table app.knowledge_documents (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  source_type text not null check (source_type in ('upload','url','manual','integration')),
  document_type text not null default 'reference' check (document_type in ('faq','policy','reference')),
  title text not null,
  source_uri text,
  checksum text,
  mime_type text,
  content text,
  visibility text not null default 'tenant' check (visibility in ('tenant','agents_only','public')),
  status text not null default 'draft' check (status in ('draft','indexing','active','failed')),
  uploaded_by_user_id uuid references app.users(id) on delete set null,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index ix_knowledge_documents_status on app.knowledge_documents(tenant_id, status);
create index ix_knowledge_documents_visibility on app.knowledge_documents(tenant_id, visibility);

create table app.knowledge_chunks (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  document_id uuid not null references app.knowledge_documents(id) on delete cascade,
  chunk_index integer not null,
  section_path text,
  chunk_text text not null,
  token_count integer not null default 0,
  embedding vector(1536),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique (document_id, chunk_index)
);
create index ix_knowledge_chunks_tenant on app.knowledge_chunks(tenant_id, document_id);

create table app.prompt_templates (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid references app.tenants(id) on delete cascade,
  vertical_code text not null,
  prompt_type text not null,
  name text not null,
  version integer not null check (version > 0),
  content text not null,
  variables jsonb not null default '[]'::jsonb,
  is_active boolean not null default false,
  checksum text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, name, version)
);

create table app.handoffs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  conversation_id uuid not null references app.conversations(id) on delete cascade,
  assigned_to uuid references app.users(id) on delete set null,
  reason text not null,
  status text not null default 'open' check (status in ('open','accepted','resolved','cancelled')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table app.webhook_events_raw (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid references app.tenants(id) on delete set null,
  provider text not null check (provider in ('whatsapp_cloud_api','mercadopago','stripe','instagram_messenger','facebook_messenger')),
  provider_event_id text,
  event_type text not null,
  headers jsonb not null default '{}'::jsonb,
  payload jsonb not null,
  payload_sha256 text not null unique,
  received_at timestamptz not null default now(),
  processing_status text not null default 'pending' check (processing_status in ('pending','processing','processed','failed')),
  processed_at timestamptz,
  last_error text
);
create index ix_webhook_events_status on app.webhook_events_raw(processing_status);

create table app.domain_events (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  aggregate_type text not null,
  aggregate_id uuid not null,
  event_name text not null,
  event_version integer not null default 1 check (event_version > 0),
  idempotency_key text not null,
  payload jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default now(),
  published_at timestamptz,
  unique (tenant_id, idempotency_key)
);
create index ix_domain_events_aggregate on app.domain_events(aggregate_type, aggregate_id);
create index ix_domain_events_unpublished on app.domain_events(published_at) where published_at is null;

create table app.audit_logs (
  id bigserial primary key,
  tenant_id uuid references app.tenants(id) on delete set null,
  actor_type text not null check (actor_type in ('anonymous','contact','bot','agent','user','service','system','support')),
  actor_id text,
  action text not null,
  entity_type text not null,
  entity_id text,
  ip inet,
  user_agent text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index ix_audit_logs_tenant_time on app.audit_logs(tenant_id, created_at desc);
create index ix_audit_logs_entity on app.audit_logs(entity_type, entity_id);

-- TASK-0057: outbound operator alerts (email / WhatsApp / webhook). The
-- worker consumes ``status='pending'`` rows with exponential retry and stops
-- after 5 failed attempts.
create table app.operator_alerts (
  id uuid primary key default gen_random_uuid(),
  -- ``tenant_id`` is nullable to allow system-level alerts (TASK-0064
  -- ``backup_failure`` does not belong to any tenant). RLS only surfaces NULL
  -- rows under ``app.support_mode()``, which is the expected operator path.
  tenant_id uuid references app.tenants(id) on delete cascade,
  kind text not null check (kind in ('negative_feedback','complaint','backup_failure','outbound_dlq_threshold')),
  constraint chk_operator_alerts_system_alerts_have_no_tenant check (
    (kind = 'backup_failure') or (tenant_id is not null)
  ),
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending' check (status in ('pending','sent','failed')),
  attempts integer not null default 0,
  last_error text,
  -- BUG-159: rastreo de canales ya entregados para que un retry tras error
  -- parcial (ej. email OK pero webhook 500) no re-envíe el email exitoso.
  -- El dispatcher escribe el nombre del canal en este array al cerrar con
  -- éxito y lo lee al entrar para hacer skip de canales ya OK.
  delivered_channels text[] not null default '{}',
  scheduled_for timestamptz not null default now(),
  created_at timestamptz not null default now(),
  sent_at timestamptz,
  updated_at timestamptz not null default now()
);
create index ix_operator_alerts_due on app.operator_alerts(scheduled_for, status);
create index ix_operator_alerts_tenant on app.operator_alerts(tenant_id, created_at desc);

-- TASK-0062: append-only ledger of consent events for Ley 1581 / GDPR.
-- The orquestador intercepts the first inbound from a new contact and sends a
-- double opt-in template; only after the client clicks "Acepto" the flow
-- continues and a `granted` event is written here. Opt-out by keyword writes
-- a `revoked` event. The scheduler emits a `reaffirm` template once per year.
-- An admin endpoint exposes the full ledger paginated for derecho-de-acceso
-- requests. Rows are append-only: a trigger raises insufficient_privilege
-- (SQLSTATE 42501) on any UPDATE or DELETE.
create table app.consent_ledger (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  contact_id uuid not null,
  event text not null check (event in ('granted','revoked','reaffirmed','suppressed')),
  channel text not null check (channel in ('whatsapp','web','admin','import')),
  legal_basis text,
  purpose text,
  copy_shown text,
  evidence_payload jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default now(),
  ip inet,
  user_agent text
);
create index ix_consent_ledger_tenant_contact_time
  on app.consent_ledger(tenant_id, contact_id, occurred_at desc);
create index ix_consent_ledger_tenant_event
  on app.consent_ledger(tenant_id, event, occurred_at desc);
-- NOTE: the composite FK `fk_consent_ledger_tenant_contact` requires the
-- unique constraint `uq_contacts_tenant_id_id` (created below at the
-- "Tenant consistency guards" block) so it lives there, not here.

create or replace function app.consent_ledger_block_mutations() returns trigger
language plpgsql as $$
begin
  raise exception 'consent_ledger is append-only (Ley 1581 audit trail)'
    using errcode = '42501';
end;
$$;
create trigger trg_consent_ledger_no_update
  before update on app.consent_ledger
  for each row execute function app.consent_ledger_block_mutations();
create trigger trg_consent_ledger_no_delete
  before delete on app.consent_ledger
  for each row execute function app.consent_ledger_block_mutations();

-- TASK-0061: per-tenant retention policy. The retention worker reads one row
-- per (tenant, entity) and either DELETEs or anonymizes rows older than
-- ``retention_days``. ``audit_logs`` only supports DELETE for compliance.
create table app.data_retention_policies (
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  entity text not null check (entity in (
    'messages','conversations','audit_logs','domain_events','webhook_events_raw','reminder_jobs'
  )),
  retention_days integer not null check (retention_days >= 30),
  anonymize_instead_of_delete boolean not null default false,
  updated_at timestamptz not null default now(),
  primary key (tenant_id, entity),
  constraint chk_audit_logs_no_anonymize check (
    entity <> 'audit_logs' or anonymize_instead_of_delete = false
  )
);
create index ix_data_retention_policies_tenant on app.data_retention_policies(tenant_id);

-- TASK-0064: operational ledger of cloud backup runs. Append-only (the verify
-- step writes a separate ``audit_logs`` row, never updates the original). Not
-- tenant-scoped: a backup snapshots the whole cluster.
create table app.backup_runs (
  id uuid primary key default gen_random_uuid(),
  kind text not null default 'cloud_dump' check (kind in ('cloud_dump','cloud_verify')),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null default 'running' check (status in ('running','ok','failed')),
  sha256 text,
  size_bytes bigint check (size_bytes is null or size_bytes >= 0),
  duration_seconds numeric(10,3) check (duration_seconds is null or duration_seconds >= 0),
  evidence_path text,
  error text,
  metadata jsonb not null default '{}'::jsonb
);
create index ix_backup_runs_started on app.backup_runs(started_at desc);
create index ix_backup_runs_kind_status on app.backup_runs(kind, status, started_at desc);


-- TASK-0067: digest_subscriptions — destinatarios del resumen periódico
-- (diario / semanal) que un worker dedicado entrega vía email y/o WhatsApp
-- a las 08:00 hora del tenant. ``last_sent_at`` es la garantía de
-- idempotencia: el worker solo despacha si la última corrida fue en un día
-- (daily) o lunes (weekly) distinto al actual en la zona horaria del tenant.
create table app.digest_subscriptions (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  recipient_email text,
  recipient_whatsapp text,
  cadence text not null check (cadence in ('daily','weekly')),
  enabled boolean not null default true,
  last_sent_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint chk_digest_subscriptions_recipient check (
    coalesce(nullif(recipient_email, ''), nullif(recipient_whatsapp, '')) is not null
  )
);
create index ix_digest_subscriptions_tenant on app.digest_subscriptions(tenant_id, cadence);
create index ix_digest_subscriptions_due on app.digest_subscriptions(enabled, cadence, last_sent_at);


-- TASK-0076: páginas legales por tenant (Términos, Privacidad, Consentimiento).
-- Append-only por versión: cada publicación inserta una fila nueva; nunca se
-- borra ni se reescribe contenido publicado, porque la Circular SIC 002 y
-- Ley 1581 exigen evidencia histórica del aviso vigente al momento del
-- consentimiento. ``archived_at`` se setea por trigger cuando una versión
-- superior es publicada en el mismo (kind, language).
create table app.tenant_legal_documents (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  kind text not null check (kind in ('terms','privacy','consent')),
  language text not null default 'es' check (length(language) between 2 and 8),
  version int not null check (version >= 1),
  title text not null,
  content_md text not null,
  published_at timestamptz,
  archived_at timestamptz,
  created_by_user_id uuid,
  created_at timestamptz not null default now(),
  constraint uq_tenant_legal_documents_version unique (tenant_id, kind, language, version),
  constraint chk_tenant_legal_documents_archived_only_if_published check (
    archived_at is null or published_at is not null
  )
);
create index ix_tenant_legal_documents_tenant_kind
  on app.tenant_legal_documents(tenant_id, kind, language, version desc);
create unique index ux_tenant_legal_documents_published_current
  on app.tenant_legal_documents(tenant_id, kind, language)
  where published_at is not null and archived_at is null;

create or replace function app.tenant_legal_documents_block_content_mutations() returns trigger
language plpgsql as $$
begin
  if old.content_md is distinct from new.content_md
     or old.kind is distinct from new.kind
     or old.language is distinct from new.language
     or old.version is distinct from new.version
     or old.tenant_id is distinct from new.tenant_id then
    raise exception 'tenant_legal_documents is append-only by version (TASK-0076)'
      using errcode = '42501';
  end if;
  return new;
end;
$$;
create trigger trg_tenant_legal_documents_no_content_update
  before update on app.tenant_legal_documents
  for each row execute function app.tenant_legal_documents_block_content_mutations();

create or replace function app.tenant_legal_documents_block_delete() returns trigger
language plpgsql as $$
begin
  raise exception 'tenant_legal_documents rows cannot be deleted (TASK-0076 audit trail)'
    using errcode = '42501';
end;
$$;
create trigger trg_tenant_legal_documents_no_delete
  before delete on app.tenant_legal_documents
  for each row execute function app.tenant_legal_documents_block_delete();

create or replace function app.tenant_legal_documents_archive_previous() returns trigger
language plpgsql as $$
begin
  if new.published_at is not null and (old.published_at is null) then
    update app.tenant_legal_documents
      set archived_at = new.published_at
      where tenant_id = new.tenant_id
        and kind = new.kind
        and language = new.language
        and id <> new.id
        and published_at is not null
        and archived_at is null;
  end if;
  return new;
end;
$$;
-- BUG-026: usar BEFORE UPDATE — el partial unique index
-- `ux_tenant_legal_documents_published_current` se chequea cuando la fila
-- NEW se escribe. Si la fila vieja seguía con `published_at IS NOT NULL AND
-- archived_at IS NULL` cuando NEW transiciona a published, la UPDATE viola
-- el índice ANTES de que un AFTER trigger pueda archivar la fila vieja.
-- BEFORE UPDATE permite archivar la fila vieja primero (sale del partial
-- index) y recién después dejar que la fila NEW se inserte en el índice.
create trigger trg_tenant_legal_documents_archive_previous
  before update on app.tenant_legal_documents
  for each row execute function app.tenant_legal_documents_archive_previous();


-- Tenant consistency guards for operational rows. RLS limits each statement to the
-- current tenant, while these composite foreign keys prevent same-tenant writes
-- from linking to records that belong to another tenant.
alter table app.tenant_channels add constraint uq_tenant_channels_tenant_id_id unique (tenant_id, id);
alter table app.contacts add constraint uq_contacts_tenant_id_id unique (tenant_id, id);
-- TASK-0062: append-only consent ledger references contacts by composite key.
-- The FK depends on `uq_contacts_tenant_id_id` being in place first.
alter table app.consent_ledger
  add constraint fk_consent_ledger_tenant_contact
    foreign key (tenant_id, contact_id)
    references app.contacts(tenant_id, id) on delete cascade;
-- TASK-0055: referrer_contact_id is tenant-scoped (cannot reference a contact
-- from another tenant); on delete set null so deleting the referrer does not
-- cascade-delete the referee.
-- BUG-027: especificar la columna en `ON DELETE SET NULL` (sintaxis Postgres
-- 15+). Sin el `(referrer_contact_id)`, el SET NULL aplica a TODAS las
-- columnas de la FK — incluido `tenant_id` que es NOT NULL — y borrar al
-- referrer revienta con `null value in column "tenant_id" violates not-null
-- constraint`. Solo queremos nullear `referrer_contact_id`.
alter table app.contacts
  add constraint fk_contacts_referrer foreign key (tenant_id, referrer_contact_id)
    references app.contacts(tenant_id, id) on delete set null (referrer_contact_id);
alter table app.conversations add constraint uq_conversations_tenant_id_id unique (tenant_id, id);
alter table app.messages add constraint uq_messages_tenant_id_id unique (tenant_id, id);
alter table app.resources add constraint uq_resources_tenant_id_id unique (tenant_id, id);
alter table app.service_catalog add constraint uq_service_catalog_tenant_id_id unique (tenant_id, id);
alter table app.whatsapp_templates add constraint uq_whatsapp_templates_tenant_id_id unique (tenant_id, id);
alter table app.appointment_feedback add constraint uq_appointment_feedback_tenant_id_id unique (tenant_id, id);
alter table app.service_requests add constraint uq_service_requests_tenant_id_id unique (tenant_id, id);
alter table app.quotes add constraint uq_quotes_tenant_id_id unique (tenant_id, id);
alter table app.appointments add constraint uq_appointments_tenant_id_id unique (tenant_id, id);
alter table app.knowledge_documents add constraint uq_knowledge_documents_tenant_id_id unique (tenant_id, id);
alter table app.knowledge_chunks add constraint uq_knowledge_chunks_tenant_id_id unique (tenant_id, id);
alter table app.handoffs add constraint uq_handoffs_tenant_id_id unique (tenant_id, id);
alter table app.contact_tags add constraint uq_contact_tags_tenant_id_id unique (tenant_id, id);
alter table app.contact_notes add constraint uq_contact_notes_tenant_id_id unique (tenant_id, id);
alter table app.qualification_questions add constraint uq_qualification_questions_tenant_id_id unique (tenant_id, id);
alter table app.media_assets add constraint uq_media_assets_tenant_id_id unique (tenant_id, id);
alter table app.promotions add constraint uq_promotions_tenant_id_id unique (tenant_id, id);
alter table app.promotions
  add constraint fk_promotions_tenant_media foreign key (tenant_id, media_asset_id) references app.media_assets(tenant_id, id);
alter table app.resources
  add constraint fk_resources_tenant_photo foreign key (tenant_id, photo_media_asset_id) references app.media_assets(tenant_id, id) on delete set null;
alter table app.contact_tag_assignments
  add constraint fk_contact_tag_assignments_tenant_contact foreign key (tenant_id, contact_id) references app.contacts(tenant_id, id),
  add constraint fk_contact_tag_assignments_tenant_tag foreign key (tenant_id, tag_id) references app.contact_tags(tenant_id, id);
alter table app.contact_notes
  add constraint fk_contact_notes_tenant_contact foreign key (tenant_id, contact_id) references app.contacts(tenant_id, id);
alter table app.campaigns add constraint uq_campaigns_tenant_id_id unique (tenant_id, id);

alter table app.campaigns
  add constraint fk_campaigns_tenant_template foreign key (tenant_id, template_id) references app.whatsapp_templates(tenant_id, id);
alter table app.campaign_attributions
  add constraint fk_campaign_attributions_tenant_campaign foreign key (tenant_id, campaign_id) references app.campaigns(tenant_id, id) on delete cascade,
  add constraint fk_campaign_attributions_tenant_contact foreign key (tenant_id, contact_id) references app.contacts(tenant_id, id) on delete cascade,
  add constraint fk_campaign_attributions_tenant_appointment foreign key (tenant_id, appointment_id) references app.appointments(tenant_id, id) on delete cascade;
alter table app.contact_segments add constraint uq_contact_segments_tenant_id_id unique (tenant_id, id);
alter table app.campaigns
  add constraint fk_campaigns_tenant_segment foreign key (tenant_id, segment_id) references app.contact_segments(tenant_id, id) on delete set null;
alter table app.contact_segment_members
  add constraint fk_contact_segment_members_tenant_segment foreign key (tenant_id, segment_id) references app.contact_segments(tenant_id, id) on delete cascade,
  add constraint fk_contact_segment_members_tenant_contact foreign key (tenant_id, contact_id) references app.contacts(tenant_id, id) on delete cascade;
alter table app.messages
  add constraint fk_messages_tenant_campaign foreign key (tenant_id, campaign_id) references app.campaigns(tenant_id, id) on delete set null;
create index ix_messages_tenant_campaign on app.messages(tenant_id, campaign_id) where campaign_id is not null;

alter table app.conversations
  add constraint fk_conversations_tenant_contact foreign key (tenant_id, contact_id) references app.contacts(tenant_id, id),
  add constraint fk_conversations_tenant_channel foreign key (tenant_id, channel_id) references app.tenant_channels(tenant_id, id);
alter table app.messages
  add constraint fk_messages_tenant_conversation foreign key (tenant_id, conversation_id) references app.conversations(tenant_id, id);
alter table app.message_status_events
  add constraint fk_message_status_events_tenant_message foreign key (tenant_id, message_id) references app.messages(tenant_id, id);
alter table app.service_requests
  add constraint fk_service_requests_tenant_contact foreign key (tenant_id, contact_id) references app.contacts(tenant_id, id),
  add constraint fk_service_requests_tenant_conversation foreign key (tenant_id, conversation_id) references app.conversations(tenant_id, id),
  add constraint fk_service_requests_tenant_resource foreign key (tenant_id, assigned_resource_id) references app.resources(tenant_id, id);
alter table app.quotes
  add constraint fk_quotes_tenant_service_request foreign key (tenant_id, service_request_id) references app.service_requests(tenant_id, id);
alter table app.branches add constraint uq_branches_tenant_id_id unique (tenant_id, id);
alter table app.resources
  add constraint fk_resources_tenant_branch foreign key (tenant_id, branch_id) references app.branches(tenant_id, id) on delete set null;
alter table app.appointments
  add constraint fk_appointments_tenant_contact foreign key (tenant_id, contact_id) references app.contacts(tenant_id, id),
  add constraint fk_appointments_tenant_conversation foreign key (tenant_id, conversation_id) references app.conversations(tenant_id, id),
  add constraint fk_appointments_tenant_service_request foreign key (tenant_id, service_request_id) references app.service_requests(tenant_id, id),
  add constraint fk_appointments_tenant_resource foreign key (tenant_id, resource_id) references app.resources(tenant_id, id),
  add constraint fk_appointments_tenant_service foreign key (tenant_id, service_id) references app.service_catalog(tenant_id, id),
  add constraint fk_appointments_tenant_branch foreign key (tenant_id, branch_id) references app.branches(tenant_id, id) on delete restrict;
alter table app.reminder_jobs
  add constraint fk_reminder_jobs_tenant_channel foreign key (tenant_id, channel_id) references app.tenant_channels(tenant_id, id);
-- TASK-0052: at most one active recall job per appointment. The partial unique
-- index lets us re-create a recall after a previous one has been cancelled or
-- already sent, while preventing duplicate live jobs.
create unique index ux_reminder_jobs_service_recall_appointment
  on app.reminder_jobs (tenant_id, target_id)
  where target_type = 'appointment'
    and (payload->>'purpose') = 'service_recall'
    and status in ('pending','processing');
-- TASK-0056: at most one active auto-rebook timeout per conversation. The
-- scheduler reads ``payload->>'kind' = 'auto_rebook_timeout'`` to dispatch the
-- silent-decline escalation; the index keeps duplicates from piling up if the
-- flow is re-armed (e.g. the customer declines a second time).
create unique index ux_reminder_jobs_auto_rebook_timeout
  on app.reminder_jobs (tenant_id, target_id)
  where target_type = 'conversation'
    and (payload->>'kind') = 'auto_rebook_timeout'
    and status in ('pending','processing');
alter table app.service_catalog
  add constraint fk_service_catalog_tenant_recall_template
    foreign key (tenant_id, recall_template_id)
    references app.whatsapp_templates(tenant_id, id) on delete set null;
alter table app.treatment_packages add constraint uq_treatment_packages_tenant_id_id unique (tenant_id, id);
alter table app.treatment_packages
  add constraint fk_treatment_packages_tenant_renewal_template foreign key (tenant_id, renewal_template_id)
    references app.whatsapp_templates(tenant_id, id) on delete set null;
alter table app.contact_packages add constraint uq_contact_packages_tenant_id_id unique (tenant_id, id);
alter table app.contact_packages
  add constraint fk_contact_packages_tenant_contact foreign key (tenant_id, contact_id)
    references app.contacts(tenant_id, id),
  add constraint fk_contact_packages_tenant_package foreign key (tenant_id, package_id)
    references app.treatment_packages(tenant_id, id);
alter table app.appointment_package_links
  add constraint fk_appointment_package_links_tenant_appointment foreign key (tenant_id, appointment_id)
    references app.appointments(tenant_id, id) on delete cascade,
  add constraint fk_appointment_package_links_tenant_contact_package foreign key (tenant_id, contact_package_id)
    references app.contact_packages(tenant_id, id);
alter table app.subscription_plans add constraint uq_subscription_plans_tenant_id_id unique (tenant_id, id);
alter table app.contact_subscriptions add constraint uq_contact_subscriptions_tenant_id_id unique (tenant_id, id);
alter table app.contact_subscriptions
  add constraint fk_contact_subscriptions_tenant_contact foreign key (tenant_id, contact_id)
    references app.contacts(tenant_id, id),
  add constraint fk_contact_subscriptions_tenant_plan foreign key (tenant_id, plan_id)
    references app.subscription_plans(tenant_id, id);
alter table app.knowledge_chunks
  add constraint fk_knowledge_chunks_tenant_document foreign key (tenant_id, document_id) references app.knowledge_documents(tenant_id, id);
alter table app.handoffs
  add constraint fk_handoffs_tenant_conversation foreign key (tenant_id, conversation_id) references app.conversations(tenant_id, id);

create trigger trg_tenants_touch before update on app.tenants for each row execute function app.touch_updated_at();
create trigger trg_tenant_settings_touch before update on app.tenant_settings for each row execute function app.touch_updated_at();
create trigger trg_tenant_channels_touch before update on app.tenant_channels for each row execute function app.touch_updated_at();
create trigger trg_contacts_touch before update on app.contacts for each row execute function app.touch_updated_at();
create trigger trg_conversations_touch before update on app.conversations for each row execute function app.touch_updated_at();
create trigger trg_resources_touch before update on app.resources for each row execute function app.touch_updated_at();
create trigger trg_service_catalog_touch before update on app.service_catalog for each row execute function app.touch_updated_at();
create trigger trg_whatsapp_templates_touch before update on app.whatsapp_templates for each row execute function app.touch_updated_at();
create trigger trg_service_requests_touch before update on app.service_requests for each row execute function app.touch_updated_at();
create trigger trg_quotes_touch before update on app.quotes for each row execute function app.touch_updated_at();
create trigger trg_appointments_touch before update on app.appointments for each row execute function app.touch_updated_at();
create trigger trg_reminder_jobs_touch before update on app.reminder_jobs for each row execute function app.touch_updated_at();
create trigger trg_operator_alerts_touch before update on app.operator_alerts for each row execute function app.touch_updated_at();
create trigger trg_data_retention_policies_touch before update on app.data_retention_policies for each row execute function app.touch_updated_at();
create trigger trg_digest_subscriptions_touch before update on app.digest_subscriptions for each row execute function app.touch_updated_at();
create trigger trg_knowledge_documents_touch before update on app.knowledge_documents for each row execute function app.touch_updated_at();
create trigger trg_prompt_templates_touch before update on app.prompt_templates for each row execute function app.touch_updated_at();
create trigger trg_handoffs_touch before update on app.handoffs for each row execute function app.touch_updated_at();
create trigger trg_contact_tags_touch before update on app.contact_tags for each row execute function app.touch_updated_at();
create trigger trg_contact_notes_touch before update on app.contact_notes for each row execute function app.touch_updated_at();
create trigger trg_qualification_questions_touch before update on app.qualification_questions for each row execute function app.touch_updated_at();
create trigger trg_media_assets_touch before update on app.media_assets for each row execute function app.touch_updated_at();
create trigger trg_promotions_touch before update on app.promotions for each row execute function app.touch_updated_at();
create trigger trg_campaigns_touch before update on app.campaigns for each row execute function app.touch_updated_at();
create trigger trg_contact_segments_touch before update on app.contact_segments for each row execute function app.touch_updated_at();
create trigger trg_branches_touch before update on app.branches for each row execute function app.touch_updated_at();
create trigger trg_treatment_packages_touch before update on app.treatment_packages for each row execute function app.touch_updated_at();
create trigger trg_contact_packages_touch before update on app.contact_packages for each row execute function app.touch_updated_at();
create trigger trg_subscription_plans_touch before update on app.subscription_plans for each row execute function app.touch_updated_at();
create trigger trg_contact_subscriptions_touch before update on app.contact_subscriptions for each row execute function app.touch_updated_at();
-- TASK-UI-016.7-FU
create trigger trg_user_preferences_touch before update on app.user_preferences for each row execute function app.touch_updated_at();
-- TASK-UI-016.7-FU-SESSIONS
create trigger trg_auth_sessions_touch before update on app.auth_sessions for each row execute function app.touch_updated_at();

-- TASK-0051: consume one session from the linked package when an appointment
-- is closed as completed. Idempotent: the appointment row is updated only
-- once via the same trigger, and the link.consumed_at guard prevents double
-- decrement if the row is touched again. When the package reaches zero
-- sessions it is marked exhausted; if its remaining count drops to 1 we emit
-- a domain event so a renewal template can be dispatched.
create or replace function app.consume_package_on_appointment() returns trigger
language plpgsql as $$
declare
  link_row app.appointment_package_links%rowtype;
  pkg app.contact_packages%rowtype;
  new_remaining int;
  new_status text;
begin
  if new.status <> 'completed' then
    return new;
  end if;
  if old.status = 'completed' then
    return new;
  end if;
  select * into link_row
    from app.appointment_package_links
    where appointment_id = new.id
    for update;
  if not found then
    return new;
  end if;
  if link_row.consumed_at is not null then
    return new;
  end if;
  select * into pkg
    from app.contact_packages
    where id = link_row.contact_package_id and tenant_id = new.tenant_id
    for update;
  if not found then
    return new;
  end if;
  if pkg.status <> 'active' then
    update app.appointment_package_links
      set consumed_at = now()
      where appointment_id = new.id;
    return new;
  end if;
  new_remaining := greatest(pkg.remaining_sessions - 1, 0);
  new_status := case when new_remaining = 0 then 'exhausted' else pkg.status end;
  update app.contact_packages
    set remaining_sessions = new_remaining,
        status = new_status,
        updated_at = now()
    where id = pkg.id;
  update app.appointment_package_links
    set consumed_at = now()
    where appointment_id = new.id;
  -- Emit a renewal-due event on the penultimate consumption (remaining=1)
  -- so retention workflows can dispatch a renewal offer.
  if new_remaining = 1 then
    insert into app.domain_events (
      tenant_id, aggregate_type, aggregate_id, event_name,
      idempotency_key, payload
    )
    values (
      new.tenant_id, 'contact_package', pkg.id, 'package.renewal_offer_due',
      'pkg_renewal:' || pkg.id::text,
      jsonb_build_object(
        'contact_id', pkg.contact_id,
        'package_id', pkg.package_id,
        'contact_package_id', pkg.id,
        'remaining_sessions', new_remaining
      )
    )
    on conflict (tenant_id, idempotency_key) do nothing;
  end if;
  return new;
end;
$$;
create trigger trg_appointments_consume_package
  after update of status on app.appointments
  for each row execute function app.consume_package_on_appointment();

-- TASK-0052: when an appointment is closed as `completed`, schedule a service
-- recall job (e.g. "tu control de 6 meses") if the linked service defines a
-- `recall_interval_days`. The unique index ux_reminder_jobs_service_recall_appointment
-- guarantees idempotency: a second trigger fire for the same appointment will
-- collide and be ignored.
create or replace function app.schedule_service_recall_on_completion() returns trigger
language plpgsql as $$
declare
  svc app.service_catalog%rowtype;
  recall_at timestamptz;
  channel_id uuid;
begin
  if new.status <> 'completed' then
    return new;
  end if;
  if old.status = 'completed' then
    return new;
  end if;
  if new.service_id is null then
    return new;
  end if;
  select * into svc
    from app.service_catalog
    where tenant_id = new.tenant_id and id = new.service_id;
  if not found then
    return new;
  end if;
  if svc.recall_interval_days is null then
    return new;
  end if;
  recall_at := new.ends_at + make_interval(days => svc.recall_interval_days);
  -- Pick the channel from the appointment conversation, if any. Falls back to
  -- the tenant's WhatsApp Cloud channel so the scheduler still has a target.
  select cv.channel_id into channel_id
    from app.conversations cv
    where cv.tenant_id = new.tenant_id and cv.id = new.conversation_id;
  if channel_id is null then
    select id into channel_id
      from app.tenant_channels
      where tenant_id = new.tenant_id and provider = 'whatsapp_cloud_api'
      order by created_at
      limit 1;
  end if;
  insert into app.reminder_jobs (
    tenant_id, target_type, target_id, channel_id,
    template_name, template_locale, payload, scheduled_for
  )
  values (
    new.tenant_id, 'appointment', new.id, channel_id,
    'service_recall', 'es',
    jsonb_build_object(
      'purpose', 'service_recall',
      'appointment_id', new.id::text,
      'service_id', svc.id::text,
      'contact_id', new.contact_id::text,
      'conversation_id', coalesce(new.conversation_id::text, ''),
      'recall_interval_days', svc.recall_interval_days,
      'recall_template_id', coalesce(svc.recall_template_id::text, '')
    ),
    recall_at
  )
  on conflict do nothing;
  return new;
end;
$$;
create trigger trg_appointments_schedule_service_recall
  after update of status on app.appointments
  for each row execute function app.schedule_service_recall_on_completion();

-- TASK-0052: when a contact books a new appointment for the same service, any
-- still-pending recall for an earlier completed visit of that service becomes
-- obsolete. Cancel it so we don't nudge a client who already rebooked.
create or replace function app.cancel_pending_recall_on_rebook() returns trigger
language plpgsql as $$
begin
  if new.service_id is null then
    return new;
  end if;
  if new.status not in ('scheduled','confirmed') then
    return new;
  end if;
  update app.reminder_jobs rj
    set status = 'cancelled',
        last_error = 'cancelled_by_rebook',
        updated_at = now()
   where rj.tenant_id = new.tenant_id
     and rj.target_type = 'appointment'
     and rj.status in ('pending','processing')
     and (rj.payload->>'purpose') = 'service_recall'
     and rj.target_id <> new.id
     and (rj.payload->>'service_id') = new.service_id::text
     and (rj.payload->>'contact_id') = new.contact_id::text;
  return new;
end;
$$;
create trigger trg_appointments_cancel_recall_on_rebook
  after insert on app.appointments
  for each row execute function app.cancel_pending_recall_on_rebook();

alter table app.tenant_channels enable row level security;
alter table app.contacts enable row level security;
alter table app.conversations enable row level security;
alter table app.messages enable row level security;
alter table app.message_status_events enable row level security;
alter table app.resources enable row level security;
alter table app.service_catalog enable row level security;
alter table app.whatsapp_templates enable row level security;
alter table app.appointment_feedback enable row level security;
alter table app.service_requests enable row level security;
alter table app.quotes enable row level security;
alter table app.appointments enable row level security;
alter table app.reminder_jobs enable row level security;
alter table app.knowledge_documents enable row level security;
alter table app.knowledge_chunks enable row level security;
alter table app.prompt_templates enable row level security;
alter table app.handoffs enable row level security;
alter table app.contact_tags enable row level security;
alter table app.contact_tag_assignments enable row level security;
alter table app.contact_notes enable row level security;
alter table app.qualification_questions enable row level security;
alter table app.media_assets enable row level security;
alter table app.promotions enable row level security;
alter table app.campaigns enable row level security;
alter table app.campaign_attributions enable row level security;
alter table app.contact_segments enable row level security;
alter table app.contact_segment_members enable row level security;
alter table app.branches enable row level security;
alter table app.treatment_packages enable row level security;
alter table app.contact_packages enable row level security;
alter table app.appointment_package_links enable row level security;
alter table app.subscription_plans enable row level security;
alter table app.contact_subscriptions enable row level security;
alter table app.webhook_events_raw enable row level security;
alter table app.domain_events enable row level security;
alter table app.audit_logs enable row level security;
alter table app.operator_alerts enable row level security;
alter table app.data_retention_policies enable row level security;
alter table app.consent_ledger enable row level security;
alter table app.digest_subscriptions enable row level security;
alter table app.tenant_legal_documents enable row level security;

do $$
declare t text;
begin
  foreach t in array array[
    'tenant_channels','contacts','conversations','messages','message_status_events','resources','service_catalog','whatsapp_templates','appointment_feedback','service_requests','quotes',
    'appointments','reminder_jobs','knowledge_documents','knowledge_chunks','prompt_templates','handoffs',
    'contact_tags','contact_tag_assignments','contact_notes',
    'qualification_questions',
    'media_assets','promotions',
    'campaigns','campaign_attributions',
    'contact_segments','contact_segment_members',
    'branches',
    'treatment_packages','contact_packages','appointment_package_links',
    'subscription_plans','contact_subscriptions',
    'webhook_events_raw','domain_events','audit_logs','operator_alerts','data_retention_policies',
    'consent_ledger','digest_subscriptions','tenant_legal_documents'
  ] loop
    execute format('create policy %I_tenant_select on app.%I for select using (tenant_id = app.current_tenant_id() or app.support_mode())', t, t);
    execute format('create policy %I_tenant_insert on app.%I for insert with check (tenant_id = app.current_tenant_id() or app.support_mode())', t, t);
    execute format('create policy %I_tenant_update on app.%I for update using (tenant_id = app.current_tenant_id() or app.support_mode()) with check (tenant_id = app.current_tenant_id() or app.support_mode())', t, t);
    execute format('create policy %I_tenant_delete on app.%I for delete using (tenant_id = app.current_tenant_id() or app.support_mode())', t, t);
  end loop;
end $$;

grant usage on schema app to copiloto_app;
grant select, insert, update, delete on all tables in schema app to copiloto_app;
grant usage, select on all sequences in schema app to copiloto_app;
alter default privileges in schema app grant select, insert, update, delete on tables to copiloto_app;
alter default privileges in schema app grant usage, select on sequences to copiloto_app;
create policy webhook_events_raw_public_insert on app.webhook_events_raw for insert with check (tenant_id is null);
create policy prompt_templates_global_select on app.prompt_templates for select using (tenant_id is null);
create policy prompt_templates_global_insert on app.prompt_templates for insert with check (tenant_id is null or tenant_id = app.current_tenant_id() or app.support_mode());
-- Audits user-scope (sin tenant): los endpoints `/v1/me/*` corren con
-- `app.tenant_id` sin setear, por lo que `app.current_tenant_id()` es NULL.
-- La policy genérica (`tenant_id = app.current_tenant_id()`) evalúa a NULL
-- en ese caso y rechaza el INSERT con `new row violates row-level security`.
-- Esta policy adicional habilita el caso simétrico: sesión sin tenant
-- insertando una fila sin tenant. No abre la puerta a cross-tenant porque
-- aplica solo cuando ambos lados son NULL (un usuario con tenant activo
-- sigue obligado a pasar por la policy genérica).
create policy audit_logs_user_scope_insert on app.audit_logs for insert with check (tenant_id is null and app.current_tenant_id() is null);

-- ============================================================================
-- TASK-INFLU-001 — Módulo Influencer / Ravit Studio (fresh-install)
-- ============================================================================
-- Schema dedicado + tabla `app.tenant_modules`. Ver `03-migrations.sql` para
-- el mismo bloque idempotente que se aplica sobre DBs existentes y los
-- detalles de decisión (D1/D2/D3/D7).


create table if not exists app.tenant_modules (
  tenant_id     uuid not null references app.tenants(id) on delete cascade,
  -- Catálogo extendido por PLATFORM-MODULES-EXPAND. Si añades un módulo aquí,
  -- replica el cambio en `03-migrations.sql` (constraint `tenant_modules_module_check`)
  -- y en el catálogo de la UI `admin-panel/src/features/platform/fleet-tenants/components/TenantModulesPanel.jsx`.
  module        text not null check (module in (
    'influencer',
    'chatbot',
    'widget_web',
    'campaigns',
    'analytics',
    'payments',
    'gestion_documental'
  )),
  enabled       boolean not null default false,
  plan          text null,
  activated_at  timestamptz null,
  activated_by  uuid null references app.users(id) on delete set null,
  notes         text null,
  primary key (tenant_id, module)
);

create index if not exists ix_tenant_modules_enabled
  on app.tenant_modules (tenant_id, module)
  where enabled = true;

alter table app.tenant_modules enable row level security;
create policy tenant_modules_tenant_select on app.tenant_modules
  for select using (tenant_id = app.current_tenant_id() or app.support_mode());
create policy tenant_modules_support_insert on app.tenant_modules
  for insert with check (app.support_mode());
create policy tenant_modules_support_update on app.tenant_modules
  for update using (app.support_mode()) with check (app.support_mode());
create policy tenant_modules_support_delete on app.tenant_modules
  for delete using (app.support_mode());

-- ============================================================================
-- TASK-INFLU-002 — Platform AI providers + secret store (fresh-install)
-- ============================================================================
-- Ver `03-migrations.sql` para el bloque idempotente equivalente + la
-- discusión de decisión D3 (config solo para platform_owner).

create table if not exists app.platform_secrets (
  secret_ref    text primary key,
  backend       text not null check (backend in ('env', 'aws_sm', 'vault', 'file')),
  ciphertext    bytea null,
  hint          text not null,
  created_at    timestamptz not null default now(),
  rotated_at    timestamptz null,
  created_by    uuid null references app.users(id) on delete set null
);
alter table app.platform_secrets enable row level security;

create table if not exists app.platform_ai_providers (
  modality      text primary key check (modality in ('llm', 'image', 'video', 'tts', 'stt')),
  provider      text not null,
  secret_ref    text null references app.platform_secrets(secret_ref) on delete set null,
  model         text null,
  params        jsonb not null default '{}'::jsonb,
  updated_at    timestamptz not null default now(),
  updated_by    uuid null references app.users(id) on delete set null
);
alter table app.platform_ai_providers enable row level security;

insert into app.platform_ai_providers (modality, provider, model)
values
  ('llm',   'unset', null),
  ('image', 'unset', null),
  ('video', 'unset', null),
  ('tts',   'unset', null),
  ('stt',   'unset', null)
on conflict (modality) do nothing;

-- BUGFIX-AI-PROVIDERS-RLS: policies que permiten CRUD bajo support_mode.
-- Ver comentario completo en 03-migrations.sql.
drop policy if exists platform_ai_providers_support_select on app.platform_ai_providers;
create policy platform_ai_providers_support_select
  on app.platform_ai_providers
  for select
  using (current_setting('app.support_mode', true) = 'true');
drop policy if exists platform_ai_providers_support_insert on app.platform_ai_providers;
create policy platform_ai_providers_support_insert
  on app.platform_ai_providers
  for insert
  with check (current_setting('app.support_mode', true) = 'true');
drop policy if exists platform_ai_providers_support_update on app.platform_ai_providers;
create policy platform_ai_providers_support_update
  on app.platform_ai_providers
  for update
  using (current_setting('app.support_mode', true) = 'true')
  with check (current_setting('app.support_mode', true) = 'true');
drop policy if exists platform_ai_providers_support_delete on app.platform_ai_providers;
create policy platform_ai_providers_support_delete
  on app.platform_ai_providers
  for delete
  using (current_setting('app.support_mode', true) = 'true');

drop policy if exists platform_secrets_support_select on app.platform_secrets;
create policy platform_secrets_support_select
  on app.platform_secrets
  for select
  using (current_setting('app.support_mode', true) = 'true');
drop policy if exists platform_secrets_support_insert on app.platform_secrets;
create policy platform_secrets_support_insert
  on app.platform_secrets
  for insert
  with check (current_setting('app.support_mode', true) = 'true');
drop policy if exists platform_secrets_support_update on app.platform_secrets;
create policy platform_secrets_support_update
  on app.platform_secrets
  for update
  using (current_setting('app.support_mode', true) = 'true')
  with check (current_setting('app.support_mode', true) = 'true');
drop policy if exists platform_secrets_support_delete on app.platform_secrets;
create policy platform_secrets_support_delete
  on app.platform_secrets
  for delete
  using (current_setting('app.support_mode', true) = 'true');

-- ============================================================================
-- Migraciones idempotentes del core (legacy DBs)
-- ============================================================================
-- ─────────────────────────────────────────────────────────────────────────
-- Migraciones idempotentes para DBs preexistentes (review feedback 2026-05).
-- ─────────────────────────────────────────────────────────────────────────
--
-- ESTE ARCHIVO debe ejecutarse manualmente contra DBs de producción que
-- existen desde ANTES de que las columnas/constraints declaradas en
-- `01-schema.sql` fueran agregadas. Postgres entrypoint corre todos los
-- `.sql` de `/docker-entrypoint-initdb.d/` SOLO en la primera inicialización
-- de un volumen, así que en DBs existentes este archivo nunca corre y el
-- schema queda divergente (`UndefinedColumnError` al hacer SELECT/UPDATE).
--
-- En fresh installs este archivo es NO-OP — todas las columnas/constraints
-- ya existen desde `01-schema.sql`, así que cada `IF NOT EXISTS` es vacío.
--
-- ## Cómo correr en producción
--
-- ```bash
-- docker compose exec -T postgres psql -U <usuario> -d <dbname> \
--   < infra/postgres/03-migrations.sql
-- ```
--
-- Cada bloque es atómico: si falla uno, los anteriores ya quedaron
-- commiteados. Idempotente — se puede correr múltiples veces.
--
-- ## Cobertura
--
-- - BUG-023: `tenant_settings.currency` agregada por TASK-0073/UI-007.12 pero
--   sin migración para DBs existentes (Codex vmantilla#105 r3236261928).
-- - BUG-024: `messages.retry_count` agregada por SEC-010 DLQ idempotency
--   pero sin migración para DBs existentes (Codex vmantilla#220 r3252061874).
--
-- Bugs futuros del mismo tipo (columna nueva en schema) deben sumarse a
-- este archivo respetando idempotencia.

-- BUG-023: tenant_settings.currency
alter table app.tenant_settings
  add column if not exists currency char(3) not null default 'COP';

-- BUG-024: messages.retry_count
alter table app.messages
  add column if not exists retry_count integer not null default 0;

-- BUG-064: partial unique indices para page_id / instagram_account_id de
-- Meta channels, mirroring lo que hicimos con phone_number_id en SEC-003.
-- Idempotente: `IF NOT EXISTS` no salta si el índice ya existe.
create unique index if not exists ux_tenant_channels_page_active
  on app.tenant_channels(page_id)
  where status='active' and page_id is not null;
create unique index if not exists ux_tenant_channels_ig_account_active
  on app.tenant_channels(instagram_account_id)
  where status='active' and instagram_account_id is not null;

-- BUG-112: precio "locked-in" del suscriptor al momento del subscribe.
-- Sin esto, MRR/invoicing usaban el precio actual del plan y subir el
-- precio del plan alteraba retroactivamente el MRR de los suscriptores
-- existentes. Las queries usan `coalesce(cs.price_locked_amount, sp.price_amount)`
-- para back-compat con filas viejas (price_locked_amount NULL).
alter table app.contact_subscriptions
  add column if not exists price_locked_amount numeric(12,2);
alter table app.contact_subscriptions
  add column if not exists price_locked_currency text;

-- BUG-134: el consent reaffirm worker inserta en `reminder_jobs` con
-- `target_type='contact'`, pero el check original solo permitía
-- appointment/quote/service_request/conversation/contact_subscription
-- → CHECK violation y el job nunca enqueueaba. Recreamos el constraint
-- agregando 'contact'. Idempotente: drop con IF EXISTS antes de re-add.
alter table app.reminder_jobs
  drop constraint if exists reminder_jobs_target_type_check;
alter table app.reminder_jobs
  add constraint reminder_jobs_target_type_check
    check (target_type in (
      'appointment','quote','service_request',
      'conversation','contact_subscription','contact'
    ));

-- BUG-159: rastreo de canales ya entregados en operator_alerts. Sin esto,
-- un retry tras error parcial (ej. email OK + webhook 500) reenvía el
-- email exitoso en cada attempt hasta que el webhook termine.
alter table app.operator_alerts
  add column if not exists delivered_channels text[] not null default '{}';

-- BUG-169 (codex P1 sobre fix-group-01): los fixes de BUG-026 y BUG-027
-- recrearon trigger + FK en `01-schema.sql` (fresh installs), pero esta
-- migración solo añadía columnas, dejando intacto el trigger AFTER UPDATE
-- y el FK sin column-spec en DBs existentes. La regresión se reproduce
-- en prod cualquier vez que `01-schema.sql` no se aplique sobre un
-- volumen vacío. Recreamos ambos objetos idempotentemente acá.

-- BUG-026 recreate: el trigger debe ser BEFORE UPDATE para que la fila
-- vieja se archive PRIMERO (salga del partial unique index) y la NEW no
-- choque. Drop + create es seguro: misma función `tenant_legal_documents_archive_previous`,
-- solo cambia el timing.
do $$
begin
  if exists (
    select 1 from pg_trigger
    where tgname = 'trg_tenant_legal_documents_archive_previous'
      and tgrelid = 'app.tenant_legal_documents'::regclass
  ) then
    drop trigger trg_tenant_legal_documents_archive_previous
      on app.tenant_legal_documents;
  end if;
end$$;

create trigger trg_tenant_legal_documents_archive_previous
  before update on app.tenant_legal_documents
  for each row execute function app.tenant_legal_documents_archive_previous();

-- BUG-027 recreate: el FK `fk_contacts_referrer` necesita el column-spec
-- `(referrer_contact_id)` en el `on delete set null` para que Postgres 15+
-- limite el SET NULL a esa columna específica (sin el spec, limpia toda
-- la tupla compuesta tenant_id+referrer_contact_id, rompiendo la
-- referencia tenant del contacto). Drop + add es seguro: el data no se mueve.
alter table app.contacts
  drop constraint if exists fk_contacts_referrer;
alter table app.contacts
  add constraint fk_contacts_referrer
    foreign key (tenant_id, referrer_contact_id)
    references app.contacts(tenant_id, id)
    on delete set null (referrer_contact_id);

