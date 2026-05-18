"""Fix-group 01: schema-related review feedback (BUG-023..BUG-027).

Tests AST/source-grep que defienden los 4 cambios concretos y dejan el
veredicto NOT-APPLICABLE para BUG-025 (ya correcto en main).

- BUG-023: ALTER TABLE migration para tenant_settings.currency.
- BUG-024: ALTER TABLE migration para messages.retry_count.
- BUG-025: NOT-APPLICABLE — `uq_contacts_tenant_id_id` ya está declarada
  ANTES de la FK `fk_consent_ledger_tenant_contact` (líneas 1102 → 1106).
- BUG-026: trigger `trg_tenant_legal_documents_archive_previous` debe ser
  BEFORE UPDATE (no AFTER) — el partial unique index se viola si la fila
  vieja sigue publicada cuando la NEW transiciona a published.
- BUG-027: FK `fk_contacts_referrer` debe especificar
  `ON DELETE SET NULL (referrer_contact_id)` (PG 15+) para no nullear el
  `tenant_id` NOT NULL.
"""
from __future__ import annotations

from pathlib import Path


SCHEMA = Path('infra/postgres/01-schema.sql')
MIGRATIONS = Path('infra/postgres/03-migrations.sql')


# ───── BUG-023 / BUG-024 — migrations idempotentes ───────────────────────


def test_migrations_file_exists():
    assert MIGRATIONS.is_file(), (
        'BUG-023/024: infra/postgres/03-migrations.sql debe existir para que '
        'operadores puedan correrlo contra DBs preexistentes (Postgres '
        'entrypoint solo corre los .sql en fresh installs).'
    )


def test_bug_023_currency_migration_present_and_idempotent():
    """tenant_settings.currency con ADD COLUMN IF NOT EXISTS."""
    src = MIGRATIONS.read_text()
    assert 'alter table app.tenant_settings' in src.lower(), (
        'BUG-023: la migración debe targetear app.tenant_settings.'
    )
    assert 'add column if not exists currency' in src.lower(), (
        'BUG-023: la migración debe usar `ADD COLUMN IF NOT EXISTS currency` '
        'para que sea no-op en fresh installs (donde la columna ya existe '
        'desde 01-schema.sql) e idempotente en re-runs.'
    )


def test_bug_024_retry_count_migration_present_and_idempotent():
    """messages.retry_count con ADD COLUMN IF NOT EXISTS."""
    src = MIGRATIONS.read_text()
    assert 'alter table app.messages' in src.lower(), (
        'BUG-024: la migración debe targetear app.messages.'
    )
    assert 'add column if not exists retry_count' in src.lower(), (
        'BUG-024: la migración debe usar `ADD COLUMN IF NOT EXISTS '
        'retry_count` para idempotencia.'
    )


# ───── BUG-025 — NOT-APPLICABLE (ya correcto) ────────────────────────────


def test_bug_025_unique_constraint_declared_before_fk():
    """`uq_contacts_tenant_id_id` debe declararse ANTES que la FK que la
    referencia. Si alguien re-ordena el schema sin notar la dependencia,
    bootstrap fallaría en base nueva con `cannot match unique constraint`.
    """
    src = SCHEMA.read_text()
    uniq_idx = src.find('add constraint uq_contacts_tenant_id_id unique (tenant_id, id)')
    fk_idx = src.find('add constraint fk_consent_ledger_tenant_contact')
    assert uniq_idx >= 0 and fk_idx >= 0, (
        'BUG-025: ambas declaraciones deben existir en 01-schema.sql.'
    )
    assert uniq_idx < fk_idx, (
        'BUG-025: `uq_contacts_tenant_id_id` debe declararse ANTES de la FK '
        '`fk_consent_ledger_tenant_contact`. Re-ordenar rompe bootstrap.'
    )


# ───── BUG-026 — trigger BEFORE UPDATE para evitar índice colisión ────────


def test_bug_026_legal_archive_trigger_runs_before_update():
    """El trigger que archiva la versión vieja debe correr BEFORE UPDATE de
    la NEW, no AFTER. Con AFTER, el partial unique index se chequea cuando
    NEW se escribe y la vieja sigue con `published_at NOT NULL AND
    archived_at NULL` → colisión → publicar v2 falla siempre.
    """
    src = SCHEMA.read_text()
    # Buscar el bloque del trigger archive_previous.
    trigger_line = 'create trigger trg_tenant_legal_documents_archive_previous'
    assert trigger_line in src, 'BUG-026: el trigger debe existir.'
    # Validar que el timing es BEFORE update.
    trigger_block_start = src.find(trigger_line)
    block = src[trigger_block_start:trigger_block_start + 200]
    assert 'before update on app.tenant_legal_documents' in block, (
        'BUG-026: el trigger debe correr BEFORE UPDATE (no AFTER) para poder '
        'archivar la fila vieja antes de que el partial unique index '
        '`ux_tenant_legal_documents_published_current` se chequee sobre NEW.'
    )
    assert 'after update on app.tenant_legal_documents' not in block, (
        'BUG-026: regresión — el trigger volvió a AFTER UPDATE. Publish de '
        'segunda versión legal vuelve a fallar.'
    )


# ───── BUG-027 — FK ON DELETE SET NULL con columna específica ────────────


def test_bug_027_referrer_fk_only_nulls_referrer_column():
    """La FK compuesta debe especificar `(referrer_contact_id)` en el SET
    NULL — sin esto, Postgres nullea TODAS las columnas de la FK (incluido
    `tenant_id` que es NOT NULL) y borrar un referrer revienta con
    `null value in column "tenant_id" violates not-null constraint`.
    Sintaxis disponible desde Postgres 15.
    """
    src = SCHEMA.read_text()
    # Anchor de la línea completa.
    target = (
        'add constraint fk_contacts_referrer foreign key '
        '(tenant_id, referrer_contact_id)'
    )
    assert target in src, (
        'BUG-027: la FK `fk_contacts_referrer` debe existir con la firma '
        'compuesta esperada.'
    )
    # El siguiente segmento debe contener `on delete set null (referrer_contact_id)`.
    fk_idx = src.find(target)
    fk_block = src[fk_idx:fk_idx + 400]
    assert 'on delete set null (referrer_contact_id)' in fk_block, (
        'BUG-027: el `ON DELETE SET NULL` debe especificar la columna '
        '`(referrer_contact_id)` (Postgres 15+). Sin esto, borrar un '
        'referrer también nullea `tenant_id` (NOT NULL) → falla.'
    )
    # Regresión: NO debe haber un `set null` sin columna en este bloque.
    set_null_no_col = 'on delete set null\n'
    # Asegurar que `set null` siempre lleva paréntesis aquí.
    block_with_specifier_count = fk_block.count('on delete set null (referrer_contact_id)')
    block_set_null_count = fk_block.lower().count('on delete set null')
    assert block_with_specifier_count == block_set_null_count, (
        'BUG-027: hay un `ON DELETE SET NULL` sin columna en el bloque del '
        'FK del referrer — regresión a la versión que nullea tenant_id.'
    )
    # Silenciador del linter.
    _ = set_null_no_col
