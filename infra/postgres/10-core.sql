-- ============================================================================
-- Copiloto Core — Schema base (transversal, sin productos)
-- ============================================================================
-- Este archivo define EXCLUSIVAMENTE el "sistema operativo" del core:
-- identidad, tenants, sesiones, auditoría, retención, módulos opt-in,
-- proveedores IA transversales, roles & capabilities dinámicos.
--
-- NO contiene tablas de chatbot (contacts, conversations, messages,
-- services, appointments, campaigns, knowledge_*, etc.), influencer
-- (personas, generations, posts), ni gestión documental (radicados,
-- expedientes, firmas, perifericos).
--
-- Cada módulo de producto vive en `infra/postgres/modules/<nombre>.sql`
-- y se carga por separado vía `bootstrap.sh --module=<nombre>`.
-- ============================================================================

create extension if not exists pgcrypto;
create extension if not exists citext;

create schema if not exists app;

-- ─── RLS helpers ────────────────────────────────────────────────────────────
-- Cada request autenticada setea `app.tenant_id` (UUID del tenant activo) y
-- opcionalmente `app.support_mode` (boolean) al inicio de la transacción.
-- Las policies de RLS usan estas funciones para filtrar rows.

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

-- ─── Tenants ────────────────────────────────────────────────────────────────

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
create trigger trg_tenants_touch
  before update on app.tenants
  for each row execute function app.touch_updated_at();

-- ─── Usuarios y membresía ──────────────────────────────────────────────────

create table app.users (
  id uuid primary key default gen_random_uuid(),
  auth_subject text not null unique,   -- Auth0 `sub`
  email citext not null unique,
  display_name text not null,
  status text not null default 'active' check (status in ('active','invited','suspended')),
  mfa_enabled boolean not null default false,
  last_login_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create trigger trg_users_touch
  before update on app.users
  for each row execute function app.touch_updated_at();

create table app.user_tenant_roles (
  user_id uuid not null references app.users(id) on delete cascade,
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  -- Roles del CHROME del panel. Para roles específicos de un producto
  -- (ej. gd.profesional, influencer.publisher) usar las tablas del módulo.
  role text not null check (role in ('owner','admin','manager','agent','viewer','support')),
  scopes text[] not null default '{}',
  is_default boolean not null default false,
  created_at timestamptz not null default now(),
  primary key (user_id, tenant_id, role)
);
create index ix_user_tenant_roles_tenant on app.user_tenant_roles(tenant_id, role);

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
create trigger trg_user_preferences_touch
  before update on app.user_preferences
  for each row execute function app.touch_updated_at();

-- ─── Sesiones server-side ──────────────────────────────────────────────────
-- Cada request autenticada upsertea su sesión por `id` (jti del JWT cuando
-- Auth0 lo emite; fallback hash estable basado en `sub + iat` cuando no),
-- refrescando `last_seen_at`. DELETE marca `revoked_at`; el GET filtra
-- `revoked_at is null`.

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
create index ix_auth_sessions_user_active
  on app.auth_sessions(user_id, last_seen_at desc)
  where revoked_at is null;
create trigger trg_auth_sessions_touch
  before update on app.auth_sessions
  for each row execute function app.touch_updated_at();

-- ─── Auditoría ──────────────────────────────────────────────────────────────

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

-- RLS: cada tenant solo ve sus propias filas. Bajo support_mode el
-- platform_owner ve TODO. Filas con tenant_id=NULL son cross-tenant
-- (alertas del sistema, eventos platform) y solo visibles bajo support.
alter table app.audit_logs enable row level security;
create policy audit_logs_tenant_select on app.audit_logs
  for select using (
    tenant_id = app.current_tenant_id()
    or (tenant_id is null and app.support_mode())
    or app.support_mode()
  );
create policy audit_logs_insert on app.audit_logs for insert with check (
  tenant_id = app.current_tenant_id() or tenant_id is null or app.support_mode()
);

-- ─── Operator alerts (incidentes cross-tenant) ────────────────────────────
-- Outbound dispatch (email/whatsapp/webhook) lo agrega cada producto cuando
-- se instala. El core solo persiste la fila + sirve el listado via
-- /v1/platform/incidents.

create table app.operator_alerts (
  id uuid primary key default gen_random_uuid(),
  -- nullable para system-level alerts (e.g. backup_failure no pertenece a
  -- ningún tenant). El listado bajo support_mode ve todos los rows.
  tenant_id uuid references app.tenants(id) on delete cascade,
  kind text not null,
  payload jsonb not null default '{}'::jsonb,
  status text not null default 'pending' check (status in ('pending','sent','failed')),
  attempts integer not null default 0,
  last_error text,
  delivered_channels text[] not null default '{}',
  scheduled_for timestamptz not null default now(),
  created_at timestamptz not null default now(),
  sent_at timestamptz,
  updated_at timestamptz not null default now()
);
create index ix_operator_alerts_status on app.operator_alerts(status, scheduled_for);
create index ix_operator_alerts_tenant on app.operator_alerts(tenant_id, created_at desc);
create trigger trg_operator_alerts_touch
  before update on app.operator_alerts
  for each row execute function app.touch_updated_at();

alter table app.operator_alerts enable row level security;
create policy operator_alerts_support_select on app.operator_alerts
  for select using (
    tenant_id = app.current_tenant_id()
    or (tenant_id is null and app.support_mode())
    or app.support_mode()
  );
create policy operator_alerts_insert on app.operator_alerts for insert with check (
  tenant_id = app.current_tenant_id() or tenant_id is null or app.support_mode()
);


-- ─── Política de retención de logs ──────────────────────────────────────────

create table app.data_retention_policies (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid references app.tenants(id) on delete cascade,
  entity_type text not null,
  retention_days integer not null check (retention_days > 0),
  enabled boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, entity_type)
);
create trigger trg_data_retention_policies_touch
  before update on app.data_retention_policies
  for each row execute function app.touch_updated_at();

-- ─── Backups (registro de runs) ─────────────────────────────────────────────

create table app.backup_runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null default 'running' check (status in ('running','success','failed')),
  artifact_path text,
  size_bytes bigint,
  error_message text,
  metadata jsonb not null default '{}'::jsonb
);
create index ix_backup_runs_started on app.backup_runs(started_at desc);

-- ─── Documentos legales del tenant ──────────────────────────────────────────
-- Términos y condiciones, política de privacidad, etc. Versionados: cada
-- update archiva la versión anterior automáticamente.

create table app.tenant_legal_documents (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete cascade,
  document_type text not null check (document_type in ('terms','privacy','dpa','custom')),
  version integer not null default 1 check (version > 0),
  title text not null,
  content text not null,
  status text not null default 'draft' check (status in ('draft','active','archived')),
  effective_from timestamptz,
  effective_until timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (tenant_id, document_type, version)
);
create index ix_tenant_legal_documents_active
  on app.tenant_legal_documents(tenant_id, document_type)
  where status = 'active';

create or replace function app.tenant_legal_documents_archive_previous() returns trigger
language plpgsql as $$
begin
  if NEW.status = 'active' then
    update app.tenant_legal_documents
       set status = 'archived', updated_at = now()
     where tenant_id = NEW.tenant_id
       and document_type = NEW.document_type
       and id <> NEW.id
       and status = 'active';
  end if;
  NEW.updated_at = now();
  return NEW;
end;
$$;
create trigger trg_tenant_legal_documents_archive
  before insert or update on app.tenant_legal_documents
  for each row execute function app.tenant_legal_documents_archive_previous();

alter table app.tenant_legal_documents enable row level security;
create policy tenant_legal_documents_tenant_scope on app.tenant_legal_documents
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

-- ─── Activación de módulos opt-in por tenant ───────────────────────────────
-- El core NO conoce módulos específicos. El CHECK permite cualquier string
-- (los módulos validan su nombre canónico en su propio bootstrap).
-- Si querés enforcement, agregá un CHECK explícito al instalar un módulo
-- nuevo (ver `docs/ARCHITECTURE.md` § "Cómo agregar un módulo nuevo").

create table app.tenant_modules (
  tenant_id     uuid not null references app.tenants(id) on delete cascade,
  module        text not null,
  enabled       boolean not null default false,
  plan          text null,
  activated_at  timestamptz null,
  activated_by  uuid null references app.users(id) on delete set null,
  notes         text null,
  primary key (tenant_id, module)
);
create index ix_tenant_modules_enabled
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

-- ─── Proveedores IA transversales ───────────────────────────────────────────
-- Config cross-modalidad (llm/image/video/tts/stt) que cualquier módulo
-- consume vía `app.ai.registry`. Solo platform_owner puede leer/escribir.

create table app.platform_secrets (
  secret_ref    text primary key,
  backend       text not null check (backend in ('env', 'aws_sm', 'vault', 'file')),
  ciphertext    bytea null,
  hint          text not null,
  created_at    timestamptz not null default now(),
  rotated_at    timestamptz null,
  created_by    uuid null references app.users(id) on delete set null
);
alter table app.platform_secrets enable row level security;
create policy platform_secrets_support_select on app.platform_secrets
  for select using (app.support_mode());
create policy platform_secrets_support_insert on app.platform_secrets
  for insert with check (app.support_mode());
create policy platform_secrets_support_update on app.platform_secrets
  for update using (app.support_mode()) with check (app.support_mode());
create policy platform_secrets_support_delete on app.platform_secrets
  for delete using (app.support_mode());

create table app.platform_ai_providers (
  modality      text primary key check (modality in ('llm', 'image', 'video', 'tts', 'stt')),
  provider      text not null,
  secret_ref    text null references app.platform_secrets(secret_ref) on delete set null,
  model         text null,
  params        jsonb not null default '{}'::jsonb,
  updated_at    timestamptz not null default now(),
  updated_by    uuid null references app.users(id) on delete set null
);
alter table app.platform_ai_providers enable row level security;
create policy platform_ai_providers_support_select on app.platform_ai_providers
  for select using (app.support_mode());
create policy platform_ai_providers_support_insert on app.platform_ai_providers
  for insert with check (app.support_mode());
create policy platform_ai_providers_support_update on app.platform_ai_providers
  for update using (app.support_mode()) with check (app.support_mode());
create policy platform_ai_providers_support_delete on app.platform_ai_providers
  for delete using (app.support_mode());

insert into app.platform_ai_providers (modality, provider, model) values
  ('llm',   'unset', null),
  ('image', 'unset', null),
  ('video', 'unset', null),
  ('tts',   'unset', null),
  ('stt',   'unset', null)
on conflict (modality) do nothing;

-- ─── Feature flags (catálogo del producto) ─────────────────────────────────

create table app.feature_flags (
  key         text primary key,
  description text,
  enabled     boolean not null default false,
  rollout_pct integer not null default 0 check (rollout_pct between 0 and 100),
  metadata    jsonb not null default '{}'::jsonb,
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create trigger trg_feature_flags_touch
  before update on app.feature_flags
  for each row execute function app.touch_updated_at();

-- ─── Roles, Capabilities & Asignación (Fase 2) ─────────────────────────────
-- Catálogo platform-scope (sin tenant_id) editable por platform_owner desde
-- la UI. Reemplaza la matriz hardcodeada que vivía en
-- `admin-panel/src/permissions/matrix.js`.
--
-- `is_system=true` protege los 6 roles base + capabilities seedeadas: no se
-- pueden borrar (solo desactivar). Roles custom (creados por platform_owner)
-- tienen is_system=false y se pueden borrar libremente.

create table app.role (
  code         text primary key,
  name         text not null,
  description  text null,
  is_system    boolean not null default false,
  is_active    boolean not null default true,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create trigger trg_role_touch
  before update on app.role
  for each row execute function app.touch_updated_at();

create table app.capability (
  code         text primary key,
  name         text not null,
  description  text null,
  group_label  text null,
  is_system    boolean not null default false,
  is_active    boolean not null default true,
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);
create trigger trg_capability_touch
  before update on app.capability
  for each row execute function app.touch_updated_at();

create table app.role_capability (
  role_code        text not null references app.role(code) on delete cascade,
  capability_code  text not null references app.capability(code) on delete cascade,
  access_level     text not null check (access_level in ('RW', 'R', 'partial', 'own_only')),
  granted_at       timestamptz not null default now(),
  granted_by       uuid null references app.users(id) on delete set null,
  primary key (role_code, capability_code)
);
create index ix_role_capability_role on app.role_capability(role_code);
create index ix_role_capability_cap on app.role_capability(capability_code);

-- Seed de los 6 roles del sistema (chrome del panel).
insert into app.role (code, name, description, is_system) values
  ('platform_owner', 'Platform Owner', 'Dueño de la plataforma. Cross-tenant + support_mode + MFA obligatorio.', true),
  ('owner',          'Owner',          'Dueño del tenant. Acceso total al tenant.', true),
  ('admin',          'Admin',          'Administrador del tenant. Configuración + operación.', true),
  ('manager',        'Manager',        'Manager del tenant. Análisis + campañas + segmentos.', true),
  ('agent',          'Agent',          'Agente del tenant. Operación diaria.', true),
  ('viewer',         'Viewer',         'Lectura del tenant. Sin permisos de escritura.', true)
on conflict (code) do nothing;

-- Seed inicial de capabilities del CORE (sin chatbot/influencer/gd).
insert into app.capability (code, name, description, group_label, is_system) values
  ('tenant_setup.read',  'Leer configuración del tenant', null, 'Administración del tenant', true),
  ('tenant_setup.write', 'Editar configuración del tenant', null, 'Administración del tenant', true),
  ('team.read',          'Leer equipo', null, 'Administración del tenant', true),
  ('team.write',         'Gestionar equipo', null, 'Administración del tenant', true),
  ('legal.read',         'Leer documentos legales', null, 'Administración del tenant', true),
  ('legal.write',        'Editar documentos legales', null, 'Administración del tenant', true),
  ('audit.read',         'Consultar auditoría', null, 'Administración del tenant', true),
  ('platform.tenants.read',           'Listar tenants',                          null, 'Platform Owner', true),
  ('platform.tenants.write',          'Gestionar tenants',                       null, 'Platform Owner', true),
  ('platform.system_health.read',     'Ver salud de la plataforma',              null, 'Platform Owner', true),
  ('platform.billing.read',           'Ver billing & MRR',                       null, 'Platform Owner', true),
  ('platform.incidents.read',         'Ver incidentes',                          null, 'Platform Owner', true),
  ('platform.incidents.write',        'Gestionar incidentes',                    null, 'Platform Owner', true),
  ('platform.outbound_dlq.read',      'Ver DLQ outbound',                        null, 'Platform Owner', true),
  ('platform.outbound_dlq.retry',     'Reintentar DLQ',                          null, 'Platform Owner', true),
  ('platform.runbooks.read',          'Leer runbooks',                           null, 'Platform Owner', true),
  ('platform.roles_acl.read',         'Ver roles & ACL',                         null, 'Platform Owner', true),
  ('platform.roles_acl.write',        'Editar roles & ACL',                      null, 'Platform Owner', true),
  ('platform.feature_flags.read',     'Ver feature flags',                       null, 'Platform Owner', true),
  ('platform.feature_flags.write',    'Editar feature flags',                    null, 'Platform Owner', true),
  ('platform.tenant_modules.read',    'Ver módulos por tenant',                  null, 'Platform Owner', true),
  ('platform.tenant_modules.write',   'Activar/desactivar módulos por tenant',   null, 'Platform Owner', true),
  ('platform.ai_providers.configure', 'Configurar proveedores IA',               null, 'Platform Owner', true)
on conflict (code) do nothing;

insert into app.role_capability (role_code, capability_code, access_level) values
  ('viewer',  'legal.read',         'R'),
  ('agent',   'legal.read',         'R'),
  ('manager', 'legal.read',         'R'),
  ('manager', 'team.read',          'R'),
  ('admin',   'tenant_setup.read',  'R'),
  ('admin',   'tenant_setup.write', 'RW'),
  ('admin',   'team.read',          'R'),
  ('admin',   'team.write',         'RW'),
  ('admin',   'legal.read',         'R'),
  ('admin',   'legal.write',        'RW'),
  ('admin',   'audit.read',         'R'),
  ('owner',   'tenant_setup.read',  'R'),
  ('owner',   'tenant_setup.write', 'RW'),
  ('owner',   'team.read',          'R'),
  ('owner',   'team.write',         'RW'),
  ('owner',   'legal.read',         'R'),
  ('owner',   'legal.write',        'RW'),
  ('owner',   'audit.read',         'R'),
  ('platform_owner', 'platform.tenants.read',           'R'),
  ('platform_owner', 'platform.tenants.write',          'RW'),
  ('platform_owner', 'platform.system_health.read',     'R'),
  ('platform_owner', 'platform.billing.read',           'R'),
  ('platform_owner', 'platform.incidents.read',         'R'),
  ('platform_owner', 'platform.incidents.write',        'RW'),
  ('platform_owner', 'platform.outbound_dlq.read',      'R'),
  ('platform_owner', 'platform.outbound_dlq.retry',     'RW'),
  ('platform_owner', 'platform.runbooks.read',          'R'),
  ('platform_owner', 'platform.roles_acl.read',         'R'),
  ('platform_owner', 'platform.roles_acl.write',        'RW'),
  ('platform_owner', 'platform.feature_flags.read',     'R'),
  ('platform_owner', 'platform.feature_flags.write',    'RW'),
  ('platform_owner', 'platform.tenant_modules.read',    'R'),
  ('platform_owner', 'platform.tenant_modules.write',   'RW'),
  ('platform_owner', 'platform.ai_providers.configure', 'RW')
on conflict (role_code, capability_code) do nothing;

-- ─── Grants al rol de aplicación ───────────────────────────────────────────

grant usage on schema app to copiloto_app;
grant select, insert, update, delete on all tables in schema app to copiloto_app;
grant usage, select on all sequences in schema app to copiloto_app;
alter default privileges in schema app
  grant select, insert, update, delete on tables to copiloto_app;
alter default privileges in schema app
  grant usage, select on sequences to copiloto_app;
