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
  country_code char(2) not null default 'CO',
  timezone text not null default 'America/Bogota',
  status text not null default 'trial' check (status in ('trial','active','suspended','churned')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz
);

create table app.tenant_settings (
  tenant_id uuid primary key references app.tenants(id) on delete cascade,
  locale text not null default 'es-CO',
  business_hours jsonb not null default '{}'::jsonb,
  escalation_policy jsonb not null default '{}'::jsonb,
  pii_policy jsonb not null default '{"no_train":true}'::jsonb,
  no_train boolean not null default true,
  knowledge_storage jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table app.tenant_channels (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  provider text not null check (provider in ('whatsapp_cloud_api')),
  business_id text,
  waba_id text,
  phone_number_id text,
  whatsapp_business_profile_id text,
  solution_id text,
  display_phone_number text,
  token_ref text not null,
  app_secret_ref text,
  verify_token_hash bytea,
  quality_rating text,
  messaging_limit_tier text,
  account_mode text not null default 'mock' check (account_mode in ('mock','live')),
  status text not null default 'provisioning' check (status in ('provisioning','active','degraded','suspended','offboarded')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, provider)
);
create index ix_tenant_channels_phone on app.tenant_channels(phone_number_id);
create index ix_tenant_channels_waba on app.tenant_channels(waba_id);

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
  tags text[] not null default '{}',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, wa_id),
  unique (tenant_id, phone_e164)
);
create index ix_contacts_tenant_phone on app.contacts(tenant_id, phone_e164);
create index gin_contacts_tags on app.contacts using gin(tags);

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

create table app.resources (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  vertical_code text not null,
  resource_type text not null,
  code text not null,
  name text not null,
  capabilities jsonb not null default '{}'::jsonb,
  is_active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, code)
);
create index ix_resources_type on app.resources(tenant_id, resource_type);

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
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (starts_at < ends_at),
  exclude using gist (resource_id with =, tstzrange(starts_at, ends_at, '[)') with &&) where (status in ('scheduled','confirmed'))
);
create index ix_appointments_tenant_starts on app.appointments(tenant_id, starts_at);
create index ix_appointments_contact_status on app.appointments(contact_id, status);

create table app.reminder_jobs (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  target_type text not null check (target_type in ('appointment','quote','service_request','conversation')),
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
  provider text not null check (provider in ('whatsapp_cloud_api')),
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


-- Tenant consistency guards for operational rows. RLS limits each statement to the
-- current tenant, while these composite foreign keys prevent same-tenant writes
-- from linking to records that belong to another tenant.
alter table app.tenant_channels add constraint uq_tenant_channels_tenant_id_id unique (tenant_id, id);
alter table app.contacts add constraint uq_contacts_tenant_id_id unique (tenant_id, id);
alter table app.conversations add constraint uq_conversations_tenant_id_id unique (tenant_id, id);
alter table app.messages add constraint uq_messages_tenant_id_id unique (tenant_id, id);
alter table app.resources add constraint uq_resources_tenant_id_id unique (tenant_id, id);
alter table app.service_catalog add constraint uq_service_catalog_tenant_id_id unique (tenant_id, id);
alter table app.service_requests add constraint uq_service_requests_tenant_id_id unique (tenant_id, id);
alter table app.quotes add constraint uq_quotes_tenant_id_id unique (tenant_id, id);
alter table app.appointments add constraint uq_appointments_tenant_id_id unique (tenant_id, id);
alter table app.knowledge_documents add constraint uq_knowledge_documents_tenant_id_id unique (tenant_id, id);
alter table app.knowledge_chunks add constraint uq_knowledge_chunks_tenant_id_id unique (tenant_id, id);
alter table app.handoffs add constraint uq_handoffs_tenant_id_id unique (tenant_id, id);

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
alter table app.appointments
  add constraint fk_appointments_tenant_contact foreign key (tenant_id, contact_id) references app.contacts(tenant_id, id),
  add constraint fk_appointments_tenant_conversation foreign key (tenant_id, conversation_id) references app.conversations(tenant_id, id),
  add constraint fk_appointments_tenant_service_request foreign key (tenant_id, service_request_id) references app.service_requests(tenant_id, id),
  add constraint fk_appointments_tenant_resource foreign key (tenant_id, resource_id) references app.resources(tenant_id, id),
  add constraint fk_appointments_tenant_service foreign key (tenant_id, service_id) references app.service_catalog(tenant_id, id);
alter table app.reminder_jobs
  add constraint fk_reminder_jobs_tenant_channel foreign key (tenant_id, channel_id) references app.tenant_channels(tenant_id, id);
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
create trigger trg_service_requests_touch before update on app.service_requests for each row execute function app.touch_updated_at();
create trigger trg_quotes_touch before update on app.quotes for each row execute function app.touch_updated_at();
create trigger trg_appointments_touch before update on app.appointments for each row execute function app.touch_updated_at();
create trigger trg_reminder_jobs_touch before update on app.reminder_jobs for each row execute function app.touch_updated_at();
create trigger trg_knowledge_documents_touch before update on app.knowledge_documents for each row execute function app.touch_updated_at();
create trigger trg_prompt_templates_touch before update on app.prompt_templates for each row execute function app.touch_updated_at();
create trigger trg_handoffs_touch before update on app.handoffs for each row execute function app.touch_updated_at();

alter table app.tenant_channels enable row level security;
alter table app.contacts enable row level security;
alter table app.conversations enable row level security;
alter table app.messages enable row level security;
alter table app.message_status_events enable row level security;
alter table app.resources enable row level security;
alter table app.service_catalog enable row level security;
alter table app.service_requests enable row level security;
alter table app.quotes enable row level security;
alter table app.appointments enable row level security;
alter table app.reminder_jobs enable row level security;
alter table app.knowledge_documents enable row level security;
alter table app.knowledge_chunks enable row level security;
alter table app.prompt_templates enable row level security;
alter table app.handoffs enable row level security;
alter table app.webhook_events_raw enable row level security;
alter table app.domain_events enable row level security;
alter table app.audit_logs enable row level security;

do $$
declare t text;
begin
  foreach t in array array[
    'tenant_channels','contacts','conversations','messages','message_status_events','resources','service_catalog','service_requests','quotes',
    'appointments','reminder_jobs','knowledge_documents','knowledge_chunks','prompt_templates','handoffs',
    'webhook_events_raw','domain_events','audit_logs'
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
