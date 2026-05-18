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
