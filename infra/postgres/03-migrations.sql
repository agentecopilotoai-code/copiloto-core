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
