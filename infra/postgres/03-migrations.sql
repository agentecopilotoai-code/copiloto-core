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

-- ============================================================================
-- TASK-INFLU-001 — Módulo Influencer / Ravit Studio
-- ============================================================================
--
-- Habilita el módulo opcional `influencer` (Ravit Studio). El módulo NO debe
-- estar disponible para tenants que no lo activen — el router responde 404
-- (no 403, para no filtrar la existencia del feature) cuando el tenant no
-- tiene la fila en `app.tenant_modules`.
--
-- Decisiones (ver docs/BACKLOG.md sección "Módulo Influencer"):
--   - D1: schema `influencer.*` separado de `app.*` para activación quirúrgica.
--   - D2: `app.tenant_modules` controla qué tenant tiene qué módulo activo.
--   - D3: la configuración de proveedores IA del módulo (TASK-INFLU-002) es
--         platform_owner-only — el tenant NO ve ni edita providers.
--   - D7: RLS por tenant_id en todas las tablas `influencer.*` (las migraciones
--         de las tablas vienen en TASK-INFLU-008+; este archivo crea solo el
--         schema vacío + el control de activación).

-- 1) Schema dedicado del módulo. Granular GRANT al rol del app para que
-- las tablas creadas posteriormente por TASK-INFLU-008+ hereden permisos.
create schema if not exists influencer;
grant usage on schema influencer to copiloto_app;
alter default privileges in schema influencer
  grant select, insert, update, delete on tables to copiloto_app;
alter default privileges in schema influencer
  grant usage, select on sequences to copiloto_app;

-- 2) Tabla `app.tenant_modules` — opt-in por tenant.
--    `module ∈ {'influencer', ...}` — sin enum dura para permitir agregar
--    módulos futuros sin migration de tipo.
--    `plan` opcional (free|pro|enterprise) para distinguir tiers cuando el
--    módulo lo necesite. Sin plan = acceso default.
create table if not exists app.tenant_modules (
  tenant_id     uuid not null references app.tenants(id) on delete cascade,
  module        text not null check (
    module in ('influencer')
    -- Cuando agreguemos más módulos, ampliar el CHECK aquí.
  ),
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

-- 3) RLS — read tenant-scoped; mutaciones gateadas en el app layer
-- (require_platform_owner + audit). NO se confía en el rol DB para la
-- escritura porque solo `platform_owner` con MFA puede activar el módulo,
-- lo que es lógica de aplicación. El SELECT sí es tenant-scoped vía RLS
-- estándar.
alter table app.tenant_modules enable row level security;

drop policy if exists tenant_modules_tenant_select on app.tenant_modules;
create policy tenant_modules_tenant_select
  on app.tenant_modules
  for select
  using (tenant_id = app.current_tenant_id() or app.support_mode());

-- Insert/update/delete: solo bajo support_mode (platform_owner) — el resto
-- de roles NO puede activar/desactivar módulos vía SQL directo, debe pasar
-- por el endpoint dedicado de platform_admin.
drop policy if exists tenant_modules_support_insert on app.tenant_modules;
create policy tenant_modules_support_insert
  on app.tenant_modules
  for insert
  with check (app.support_mode());

drop policy if exists tenant_modules_support_update on app.tenant_modules;
create policy tenant_modules_support_update
  on app.tenant_modules
  for update
  using (app.support_mode())
  with check (app.support_mode());

drop policy if exists tenant_modules_support_delete on app.tenant_modules;
create policy tenant_modules_support_delete
  on app.tenant_modules
  for delete
  using (app.support_mode());

-- ============================================================================
-- TASK-INFLU-002 — Platform AI providers + secret store
-- ============================================================================
--
-- Tabla global (sin tenant_id) que guarda la configuración del proveedor de
-- IA para cada modalidad del módulo Influencer. Decisión D3 del backlog:
-- SOLO `platform_owner` con MFA puede leer/editar estas filas — el tenant
-- jamás ve ni modifica qué proveedor está activo. Los endpoints viven en
-- `platform_admin_router`.
--
-- Modalidades:
--   - llm     → captions, descripciones de identidad, decisiones de bot
--   - image   → fotos de personajes, escenas, anuncios visuales
--   - video   → reels, historias, anuncios en video
--   - tts     → voz del personaje (sample del wizard + narración de reels)
--   - stt     → transcripción opcional para audio inputs
--
-- Storage de secretos en tabla separada `app.platform_secrets` con
-- `secret_ref` opaco — el contenido `ciphertext` nunca se devuelve por API
-- después de configurar. El operador ve solo el `hint` (últimos 4 chars).

create table if not exists app.platform_secrets (
  secret_ref    text primary key,                       -- e.g. 'aws-sm://copilotoia/grok/prod'
  backend       text not null check (backend in ('env', 'aws_sm', 'vault', 'file')),
  ciphertext    bytea null,                             -- opcional: encriptado at-rest (env/aws_sm pueden delegar)
  hint          text not null,                          -- últimos 4 chars en claro — para que el operador identifique cuál key está activa
  created_at    timestamptz not null default now(),
  rotated_at    timestamptz null,
  created_by    uuid null references app.users(id) on delete set null
);

-- NO RLS: la tabla es accesible solo desde funciones SECURITY DEFINER o
-- desde el path del app después de `require_platform_owner`. Sin policy
-- equivale a "deny all" en el rol del app — el código tiene que pasar por
-- el dependency de auth antes de leer/escribir.
alter table app.platform_secrets enable row level security;

create table if not exists app.platform_ai_providers (
  modality      text primary key check (modality in ('llm', 'image', 'video', 'tts', 'stt')),
  provider      text not null,                          -- 'grok' | 'anthropic' | 'openai' | 'elevenlabs' | 'ollama' | 'local_sdxl' | 'local_whisper'
  secret_ref    text null references app.platform_secrets(secret_ref) on delete set null,
  model         text null,                              -- e.g. 'grok-4.3', 'grok-imagine-image-quality', 'claude-3-5-sonnet'
  params        jsonb not null default '{}'::jsonb,     -- { fallback_chain: [...], timeout_seconds: 30, ... }
  updated_at    timestamptz not null default now(),
  updated_by    uuid null references app.users(id) on delete set null
);

alter table app.platform_ai_providers enable row level security;

-- Seed de las 5 modalidades sin proveedor — endpoints PATCH luego setean
-- provider + secret. Esto permite que el helper `resolve_provider` siempre
-- vea las 5 filas y caiga a fallback env-var si no hay configuración.
insert into app.platform_ai_providers (modality, provider, model)
values
  ('llm',   'unset', null),
  ('image', 'unset', null),
  ('video', 'unset', null),
  ('tts',   'unset', null),
  ('stt',   'unset', null)
on conflict (modality) do nothing;

-- BUGFIX-AI-PROVIDERS-RLS: con `enable row level security` y CERO policies,
-- la tabla queda en deny-all para `copiloto_app` (no owner, no BYPASSRLS).
-- Resultado: GET /v1/platform/ai-providers devolvía 0 filas (la UI las
-- pintaba con fallback "— sin configurar") y PATCH devolvía 404 "modality
-- llm not found" porque el UPDATE no afectaba filas. Estas policies abren
-- el acceso CRUD bajo `app.support_mode='on'` — el gate efectivo sigue
-- siendo `require_platform_owner` + MFA en el dependency del endpoint, que
-- corre antes de setear el config y entrar a la transacción.
drop policy if exists platform_ai_providers_support_select on app.platform_ai_providers;
create policy platform_ai_providers_support_select
  on app.platform_ai_providers
  for select
  using (current_setting('app.support_mode', true) = 'on');

drop policy if exists platform_ai_providers_support_insert on app.platform_ai_providers;
create policy platform_ai_providers_support_insert
  on app.platform_ai_providers
  for insert
  with check (current_setting('app.support_mode', true) = 'on');

drop policy if exists platform_ai_providers_support_update on app.platform_ai_providers;
create policy platform_ai_providers_support_update
  on app.platform_ai_providers
  for update
  using (current_setting('app.support_mode', true) = 'on')
  with check (current_setting('app.support_mode', true) = 'on');

drop policy if exists platform_ai_providers_support_delete on app.platform_ai_providers;
create policy platform_ai_providers_support_delete
  on app.platform_ai_providers
  for delete
  using (current_setting('app.support_mode', true) = 'on');

-- `platform_secrets` requiere el mismo tratamiento: el PATCH inserta/upserta
-- una fila en `platform_secrets` cuando rota la key, y luego lee `hint`
-- para devolverlo en el response.
drop policy if exists platform_secrets_support_select on app.platform_secrets;
create policy platform_secrets_support_select
  on app.platform_secrets
  for select
  using (current_setting('app.support_mode', true) = 'on');

drop policy if exists platform_secrets_support_insert on app.platform_secrets;
create policy platform_secrets_support_insert
  on app.platform_secrets
  for insert
  with check (current_setting('app.support_mode', true) = 'on');

drop policy if exists platform_secrets_support_update on app.platform_secrets;
create policy platform_secrets_support_update
  on app.platform_secrets
  for update
  using (current_setting('app.support_mode', true) = 'on')
  with check (current_setting('app.support_mode', true) = 'on');

drop policy if exists platform_secrets_support_delete on app.platform_secrets;
create policy platform_secrets_support_delete
  on app.platform_secrets
  for delete
  using (current_setting('app.support_mode', true) = 'on');

-- ============================================================================
-- TASK-INFLU-008 — `influencer.personas` + CRUD
-- ============================================================================
-- Tabla principal del módulo Ravit Studio: cada fila representa un personaje
-- (influencer virtual) que el tenant ha creado mediante el wizard de 5 pasos
-- (UI-INFLU-008..012). Los 5 jsonb (face/body/identity/voice/platforms) se
-- llenan progresivamente — un persona en estado 'draft' puede tener algunos
-- vacíos. El estado pasa a 'active' cuando completa el wizard.
--
-- RLS: aislamiento estricto por tenant. Endpoints leen via `authenticate_request`
-- que populates `tenant_id` en `request.state`; las queries usan SET LOCAL
-- `app.tenant_id` para que las policies funcionen.
--
-- Soft delete via `archived_at` (no DELETE físico): protege el handle de
-- reuso accidental y mantiene referencias de assets/generations vivas.

create table if not exists influencer.personas (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references app.tenants(id) on delete cascade,
  name          text not null,
  handle        text not null,
  status        text not null default 'draft'
                  check (status in ('draft', 'active', 'paused', 'archived')),
  category      text null,
  face          jsonb not null default '{}'::jsonb,
  body          jsonb not null default '{}'::jsonb,
  identity      jsonb not null default '{}'::jsonb,
  voice         jsonb not null default '{}'::jsonb,
  platforms     jsonb not null default '{}'::jsonb,
  mode          text not null default 'manual_approval'
                  check (mode in ('auto_generate', 'manual_approval', 'hybrid')),
  disclose_ai   boolean not null default true,
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now(),
  created_by    uuid null references app.users(id) on delete set null,
  archived_at   timestamptz null
);

-- Handle único por tenant (case-insensitive).
create unique index if not exists ux_personas_tenant_handle_lower
  on influencer.personas (tenant_id, lower(handle));

-- Lookup primario: lista por tenant filtrada por status, ordenada por
-- created_at desc.
create index if not exists ix_personas_tenant_status_created
  on influencer.personas (tenant_id, status, created_at desc);

-- RLS: aislamiento por tenant + bypass para support_mode (platform_owner).
alter table influencer.personas enable row level security;

drop policy if exists personas_tenant_isolation on influencer.personas;
create policy personas_tenant_isolation
  on influencer.personas
  using (
    tenant_id::text = current_setting('app.tenant_id', true)
    or current_setting('app.support_mode', true) = 'on'
  );

drop policy if exists personas_tenant_write on influencer.personas;
create policy personas_tenant_write
  on influencer.personas
  for all
  using (
    tenant_id::text = current_setting('app.tenant_id', true)
    or current_setting('app.support_mode', true) = 'on'
  )
  with check (
    tenant_id::text = current_setting('app.tenant_id', true)
    or current_setting('app.support_mode', true) = 'on'
  );

-- ============================================================================
-- TASK-INFLU-009 — Audit tables del wizard
-- ============================================================================
-- Cada PUT al wizard emite una fila aquí — útil para entender qué se editó
-- antes del `activate`. Cada activate emite una fila en
-- `persona_activated`.

create table if not exists influencer.persona_step_updated (
  id            bigserial primary key,
  tenant_id     uuid not null references app.tenants(id) on delete cascade,
  persona_id    uuid not null references influencer.personas(id) on delete cascade,
  step          text not null check (step in ('face', 'body', 'identity', 'voice', 'platforms')),
  fields_changed text[] not null default '{}',
  occurred_at   timestamptz not null default now()
);

create index if not exists ix_persona_step_updated_persona_occurred
  on influencer.persona_step_updated (persona_id, occurred_at desc);

create table if not exists influencer.persona_activated (
  id            bigserial primary key,
  tenant_id     uuid not null references app.tenants(id) on delete cascade,
  persona_id    uuid not null references influencer.personas(id) on delete cascade,
  activated_by  uuid null references app.users(id) on delete set null,
  occurred_at   timestamptz not null default now()
);

create index if not exists ix_persona_activated_tenant_occurred
  on influencer.persona_activated (tenant_id, occurred_at desc);

-- ============================================================================
-- TASK-INFLU-010 — face_variation_requests
-- ============================================================================
-- Las variaciones de cara son async: el POST inserta una fila aquí con
-- `status='queued'`; el generation_worker (TASK-INFLU-012) lo levanta, llama
-- al image provider, persiste los assets en S3 + `influencer.assets`, y
-- actualiza `status='completed'`. El UI hace WS / polling al endpoint
-- GET .../face/variations/{id} para refresh.

create table if not exists influencer.face_variation_requests (
  id            uuid primary key default gen_random_uuid(),
  tenant_id     uuid not null references app.tenants(id) on delete cascade,
  persona_id    uuid not null references influencer.personas(id) on delete cascade,
  requested_count int not null check (requested_count between 1 and 10) default 4,
  status        text not null default 'queued'
                  check (status in ('queued', 'in_progress', 'completed', 'failed')),
  prompt_used   text null,
  error_message text null,
  requested_by  uuid null references app.users(id) on delete set null,
  requested_at  timestamptz not null default now(),
  started_at    timestamptz null,
  completed_at  timestamptz null
);

create index if not exists ix_face_variation_requests_persona_requested
  on influencer.face_variation_requests (persona_id, requested_at desc);

create index if not exists ix_face_variation_requests_queued
  on influencer.face_variation_requests (status, requested_at)
  where status in ('queued', 'in_progress');

alter table influencer.face_variation_requests enable row level security;

drop policy if exists fvr_tenant_isolation on influencer.face_variation_requests;
create policy fvr_tenant_isolation
  on influencer.face_variation_requests
  using (
    tenant_id::text = current_setting('app.tenant_id', true)
    or current_setting('app.support_mode', true) = 'on'
  );

-- ============================================================================
-- TASK-INFLU-011 — generations + assets
-- ============================================================================

create table if not exists influencer.generations (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references app.tenants(id) on delete cascade,
  persona_id      uuid not null references influencer.personas(id) on delete cascade,
  kind            text not null
                    check (kind in ('photo', 'reel', 'carousel', 'story', 'ad',
                                     'face_variation', 'voice_sample')),
  prompt          text not null default '',
  format          text not null default '1:1',
  count_requested int not null default 1 check (count_requested between 1 and 10),
  status          text not null default 'queued'
                    check (status in ('queued', 'running', 'succeeded', 'failed', 'canceled')),
  provider_used   text null,
  cost_credits    int not null default 0,
  params          jsonb not null default '{}'::jsonb,
  error_message   text null,
  requested_by    uuid null references app.users(id) on delete set null,
  created_at      timestamptz not null default now(),
  started_at      timestamptz null,
  completed_at    timestamptz null
);

create index if not exists ix_generations_persona_status_created
  on influencer.generations (persona_id, status, created_at desc);

create index if not exists ix_generations_tenant_status
  on influencer.generations (tenant_id, status);

create index if not exists ix_generations_queue
  on influencer.generations (status, created_at)
  where status in ('queued', 'running');

alter table influencer.generations enable row level security;
drop policy if exists generations_tenant_isolation on influencer.generations;
create policy generations_tenant_isolation
  on influencer.generations
  using (
    tenant_id::text = current_setting('app.tenant_id', true)
    or current_setting('app.support_mode', true) = 'on'
  );

create table if not exists influencer.assets (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references app.tenants(id) on delete cascade,
  persona_id      uuid not null references influencer.personas(id) on delete cascade,
  generation_id   uuid null references influencer.generations(id) on delete set null,
  kind            text not null
                    check (kind in ('photo', 'reel', 'carousel', 'story', 'ad',
                                     'face_variation', 'voice_sample')),
  storage_key     text not null,
  mime            text not null default 'application/octet-stream',
  width           int null,
  height          int null,
  duration_s      double precision null,
  bytes           bigint null,
  marked_canonical boolean not null default false,
  created_at      timestamptz not null default now()
);

create index if not exists ix_assets_persona_kind_created
  on influencer.assets (persona_id, kind, created_at desc);

create index if not exists ix_assets_generation
  on influencer.assets (generation_id);

alter table influencer.assets enable row level security;
drop policy if exists assets_tenant_isolation on influencer.assets;
create policy assets_tenant_isolation
  on influencer.assets
  using (
    tenant_id::text = current_setting('app.tenant_id', true)
    or current_setting('app.support_mode', true) = 'on'
  );

-- ============================================================================
-- TASK-INFLU-014 — platform_connections (Instagram first)
-- ============================================================================

create table if not exists influencer.platform_connections (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references app.tenants(id) on delete cascade,
  persona_id      uuid not null references influencer.personas(id) on delete cascade,
  platform        text not null
                    check (platform in ('instagram', 'tiktok', 'youtube',
                                         'threads', 'x', 'facebook')),
  external_account_id text null,
  external_handle text null,
  oauth_token_ref text null references app.platform_secrets(secret_ref)
                    on delete set null,
  refresh_token_ref text null references app.platform_secrets(secret_ref)
                    on delete set null,
  expires_at      timestamptz null,
  scopes          text[] not null default '{}',
  posts_per_week  int not null default 3 check (posts_per_week between 0 and 50),
  status          text not null default 'pending'
                    check (status in ('connected', 'expired', 'disconnected', 'pending')),
  connected_at    timestamptz null,
  last_used_at    timestamptz null,
  created_at      timestamptz not null default now()
);

create unique index if not exists ux_platform_connections_persona_platform
  on influencer.platform_connections (persona_id, platform)
  where status <> 'disconnected';

create index if not exists ix_platform_connections_tenant_platform_status
  on influencer.platform_connections (tenant_id, platform, status);

alter table influencer.platform_connections enable row level security;
drop policy if exists platform_connections_tenant_isolation on influencer.platform_connections;
create policy platform_connections_tenant_isolation
  on influencer.platform_connections
  using (
    tenant_id::text = current_setting('app.tenant_id', true)
    or current_setting('app.support_mode', true) = 'on'
  );

-- ============================================================================
-- TASK-INFLU-015 — posts + publish queue
-- ============================================================================

create table if not exists influencer.posts (
  id              uuid primary key default gen_random_uuid(),
  tenant_id       uuid not null references app.tenants(id) on delete cascade,
  persona_id      uuid not null references influencer.personas(id) on delete cascade,
  generation_id   uuid null references influencer.generations(id) on delete set null,
  kind            text not null
                    check (kind in ('photo', 'reel', 'carousel', 'story', 'ad')),
  caption         text not null default '',
  hashtags        text[] not null default '{}',
  scheduled_at    timestamptz not null,
  platforms       text[] not null check (cardinality(platforms) > 0),
  status          text not null default 'scheduled'
                    check (status in ('scheduled', 'approved', 'publishing',
                                       'published', 'failed', 'canceled')),
  approved_by     uuid null references app.users(id) on delete set null,
  approved_at     timestamptz null,
  published_at    timestamptz null,
  external_post_ids jsonb not null default '{}'::jsonb,
  error_message   text null,
  created_at      timestamptz not null default now()
);

create index if not exists ix_posts_tenant_status_scheduled
  on influencer.posts (tenant_id, status, scheduled_at);

create index if not exists ix_posts_publish_queue
  on influencer.posts (scheduled_at)
  where status = 'approved';

create index if not exists ix_posts_persona_scheduled
  on influencer.posts (persona_id, scheduled_at desc);

alter table influencer.posts enable row level security;
drop policy if exists posts_tenant_isolation on influencer.posts;
create policy posts_tenant_isolation
  on influencer.posts
  using (
    tenant_id::text = current_setting('app.tenant_id', true)
    or current_setting('app.support_mode', true) = 'on'
  );

-- ============================================================================
-- TASK-INFLU-016 — credit_ledger + generation_pricing
-- ============================================================================

create table if not exists influencer.credit_ledger (
  id              bigserial primary key,
  tenant_id       uuid not null references app.tenants(id) on delete cascade,
  delta           int not null check (delta <> 0),
  balance_after   int not null check (balance_after >= 0),
  reason          text not null,
  ref             text null,
  actor_id        uuid null references app.users(id) on delete set null,
  created_at      timestamptz not null default now()
);

create index if not exists ix_credit_ledger_tenant_created
  on influencer.credit_ledger (tenant_id, created_at desc);

create index if not exists ix_credit_ledger_tenant_id_id
  on influencer.credit_ledger (tenant_id, id desc);

alter table influencer.credit_ledger enable row level security;
drop policy if exists credit_ledger_tenant_isolation on influencer.credit_ledger;
create policy credit_ledger_tenant_isolation
  on influencer.credit_ledger
  using (
    tenant_id::text = current_setting('app.tenant_id', true)
    or current_setting('app.support_mode', true) = 'on'
  );

create table if not exists influencer.generation_pricing (
  kind            text primary key
                    check (kind in ('photo', 'reel', 'carousel', 'story', 'ad',
                                     'face_variation', 'voice_sample')),
  cost_credits    int not null check (cost_credits > 0),
  updated_at      timestamptz not null default now()
);

-- Seed pricing inicial. PATCH del platform_owner lo override después.
insert into influencer.generation_pricing (kind, cost_credits) values
  ('photo',          3),
  ('reel',           8),
  ('carousel',      10),
  ('story',          2),
  ('ad',             5),
  ('face_variation', 1),
  ('voice_sample',   2)
on conflict (kind) do nothing;

-- ============================================================================
-- TASK-INFLU-017 — persona_stats_cache (TTL 1h)
-- ============================================================================

create table if not exists influencer.persona_stats_cache (
  persona_id      uuid primary key references influencer.personas(id) on delete cascade,
  tenant_id       uuid not null references app.tenants(id) on delete cascade,
  posts_total     int not null default 0,
  reach_30d       bigint not null default 0,
  engagement_rate double precision not null default 0,
  scheduled_count int not null default 0,
  computed_at     timestamptz not null default now()
);

create index if not exists ix_persona_stats_cache_tenant
  on influencer.persona_stats_cache (tenant_id);

alter table influencer.persona_stats_cache enable row level security;
drop policy if exists persona_stats_cache_tenant_isolation on influencer.persona_stats_cache;
create policy persona_stats_cache_tenant_isolation
  on influencer.persona_stats_cache
  using (
    tenant_id::text = current_setting('app.tenant_id', true)
    or current_setting('app.support_mode', true) = 'on'
  );


-- ============================================================================
-- PLATFORM-MODULES-EXPAND — Amplia catálogo de módulos toggleables
--
-- Hasta ahora `app.tenant_modules.module` solo permitía `'influencer'`.
-- Esta migración extiende el CHECK constraint para soportar los módulos del
-- producto principal + el módulo externo de Gestión Documental. La UI
-- platform-owner (FleetTenants drawer) consume esta lista para mostrar
-- toggles activables/desactivables solo accesibles por `platform_owner`.
--
-- Decisión:
--   * Módulos top-level del producto principal: chatbot, widget_web,
--     campaigns, analytics, payments. (`influencer` ya estaba.)
--   * Módulo externo: `gestion_documental` como un único toggle top-level.
--     Sus sub-features (pqrsd_legal, pqrsd_tickets, correspondencia, etc.)
--     viven en `gd.organizacion_modulo_activacion` cuando el módulo GD se
--     implemente. Ese desglose NO es responsabilidad de `tenant_modules`.
-- ============================================================================

alter table app.tenant_modules
  drop constraint if exists tenant_modules_module_check;

alter table app.tenant_modules
  add constraint tenant_modules_module_check
  check (module in (
    'influencer',
    'chatbot',
    'widget_web',
    'campaigns',
    'analytics',
    'payments',
    'gestion_documental'
  ));

-- No se siembra ninguna fila. Cada tenant decide qué módulos activa.
-- La activación se hace vía `PATCH /admin/api/core/v1/platform/tenant-modules/{tenant_id}/{module}`
-- (require_platform_owner + MFA).
