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
