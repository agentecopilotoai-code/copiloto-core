-- ============================================================================
-- Copiloto Core — v2.0.0: Multi-provider email subsystem
-- ============================================================================
-- Espeja el patrón de `app.platform_ai_providers` (10-core.sql:392):
--   - Tabla principal de configuración (`app.email_providers`).
--   - Tabla de audit log de cada envío (`app.email_dispatch_log`),
--     análoga a `app.provider_dispatch` para IA.
--   - RLS solo para platform_owner (vía `app.support_mode()`).
--   - Grants a `copiloto_app` (rol runtime de la app).
--
-- BREAKING CHANGE — v2.0.0:
--   Antes (≤1.6.x): `copiloto_core.services.email` leía `RESEND_API_KEY`
--   del entorno y instanciaba un único `ResendProvider` global.
--   Ahora (≥2.0.0): el dispatcher recorre `app.email_providers ORDER BY
--   priority ASC`, intenta cada provider activo, hace fallback al siguiente
--   si el actual devuelve un error retryable.
-- ============================================================================


-- ─── Tabla principal: providers configurados por el platform_owner ─────────

create table app.email_providers (
  id                       uuid primary key default gen_random_uuid(),
  -- Code es el identificador legible que el operador usa en la UI
  -- (e.g. `resend-main`, `sendgrid-fallback`). Unique para evitar dos
  -- entradas con el mismo nombre — facilita el debugging por log.
  code                     text not null unique,
  -- Tipo del provider: `resend`, `sendgrid`, `mailgun`, `smtp`. El CHECK
  -- está cerrado para evitar typos. Si en el futuro se agrega un provider
  -- (e.g. SES), bump del schema con `30-email-providers-v2.sql`.
  provider_type            text not null check (provider_type in (
    'resend', 'sendgrid', 'mailgun', 'smtp'
  )),
  -- Nombre humano para mostrar en la UI (e.g. "Resend principal").
  name                     text not null,
  -- Config shape varía por provider_type — el adapter lo valida con
  -- Pydantic al instanciar (ver `copiloto_core/email/providers/*.py`).
  -- Defaults a `{}` para evitar NULL handling en el adapter.
  config_jsonb             jsonb not null default '{}'::jsonb,
  -- API key cifrada con Fernet (master key `AI_PROVIDER_MASTER_KEY` —
  -- reusamos la misma para no agregar otro env var). Para SMTP, esto
  -- guarda la password del username. Para Resend/SendGrid/Mailgun: la
  -- API key. Plaintext jamás se persiste.
  --
  -- BIG WARNING: rotar la master key sin re-cifrar estas filas las deja
  -- inservibles — la decryption levanta InvalidToken. Plan de rotación:
  -- al cambiar la master, leer cada fila con la VIEJA, re-cifrar con la
  -- NUEVA, persistir. Por ahora la rotación se documenta como op-runbook,
  -- no automatizada.
  api_key_ciphertext       text null,
  -- Overrides del sender por provider. Útil cuando cada provider tiene
  -- un dominio verificado distinto (e.g. main `notifications@app.copilotoia.com`
  -- en Resend, fallback `noreply@copilotoia.com` en SendGrid).
  -- Si NULL → fallback al `email_from_address` / `email_from_name` global
  -- de Settings.
  from_address_override    text null,
  from_name_override       text null,
  -- Toggle de activación. is_active=false → el dispatcher lo saltea.
  -- Útil para tener un provider de respaldo "frío" que se activa solo
  -- cuando el primario se rompe.
  is_active                boolean not null default true,
  -- Priority orden ASC: el provider con `priority=10` se intenta antes que
  -- el de `priority=100`. Por convención: dejar gaps de 10 para insertar
  -- providers nuevos en el medio sin renumerar (10, 20, 30, ...).
  priority                 integer not null default 100,
  created_at               timestamptz not null default now(),
  updated_at               timestamptz not null default now(),
  created_by               uuid null references app.users(id) on delete set null
);
-- RLS: solo platform_owner (support_mode) ve y modifica esta tabla.
-- Es config global de la plataforma, no per-tenant.
alter table app.email_providers enable row level security;
create policy email_providers_support_select on app.email_providers
  for select using (app.support_mode());
create policy email_providers_support_insert on app.email_providers
  for insert with check (app.support_mode());
create policy email_providers_support_update on app.email_providers
  for update using (app.support_mode()) with check (app.support_mode());
create policy email_providers_support_delete on app.email_providers
  for delete using (app.support_mode());
-- A8 pattern: FK created_by sin índice = seq-scan en delete users.
create index ix_email_providers_created_by
  on app.email_providers (created_by)
  where created_by is not null;
-- Índice de selección por prioridad para el dispatcher (hot path).
create index ix_email_providers_active_priority
  on app.email_providers (priority asc)
  where is_active = true;
create trigger trg_email_providers_touch
  before update on app.email_providers
  for each row execute function app.touch_updated_at();


-- ─── Audit trail: cada attempt del dispatcher graba acá ────────────────────
-- Análogo a `app.provider_dispatch` pero para emails. El platform_owner
-- puede investigar fallos de envío, mapear bounces, etc. La inserción es
-- best-effort: si la tabla no existe (DB anterior a v2.0.0) el dispatcher
-- loguea y sigue (ver `EmailDispatcher._audit_attempt`).

create table app.email_dispatch_log (
  id                bigserial primary key,
  -- FK opcional (ON DELETE SET NULL) — si el platform_owner borra un
  -- provider config, los logs históricos siguen siendo útiles para
  -- diagnóstico. El `code` del provider queda implícito en `error_message`
  -- / `provider_code` ya que reusamos audit_logs separado para metadata.
  email_provider_id uuid null references app.email_providers(id) on delete set null,
  to_address        text not null,
  subject           text not null,
  status            text not null check (status in ('sent', 'failed', 'retried')),
  error_message     text null,
  latency_ms        integer not null default 0,
  dispatched_at     timestamptz not null default now()
);
alter table app.email_dispatch_log enable row level security;
create policy email_dispatch_log_support_select on app.email_dispatch_log
  for select using (app.support_mode());
create policy email_dispatch_log_support_insert on app.email_dispatch_log
  for insert with check (app.support_mode());
-- Para fines de retención: borrar logs > 90 días con cron job.
create policy email_dispatch_log_support_delete on app.email_dispatch_log
  for delete using (app.support_mode());
-- Índices: por provider (drill-down) y por fecha desc (lista cronológica).
create index ix_email_dispatch_log_provider
  on app.email_dispatch_log (email_provider_id, dispatched_at desc)
  where email_provider_id is not null;
create index ix_email_dispatch_log_dispatched
  on app.email_dispatch_log (dispatched_at desc);
create index ix_email_dispatch_log_status
  on app.email_dispatch_log (status, dispatched_at desc);


-- ─── Grants al rol runtime ──────────────────────────────────────────────────
-- Sin esto, la app (que se conecta como `copiloto_app`, no como `postgres`)
-- no puede leer ni escribir estas tablas. Los GRANTs son idempotentes;
-- las default privileges del schema `app` ya cubren tablas futuras pero
-- explicitamos por claridad operativa.

grant select, insert, update, delete on app.email_providers to copiloto_app;
grant select, insert, delete on app.email_dispatch_log to copiloto_app;
grant usage, select on sequence app.email_dispatch_log_id_seq to copiloto_app;
