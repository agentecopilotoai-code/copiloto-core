"""Fix-group 12: BUG-078..BUG-082.

- BUG-078: NOT-APPLICABLE. Runbook ya usa columnas correctas (`event`,
  `evidence_payload`, `occurred_at`, `contact_id` via JOIN).
- BUG-079: VIGENTE. `verify-backup.sh` solo chequeaba GOODSIG; faltaba
  validar fingerprint contra `BACKUP_SIGNER_FPR`. Fix: extraer
  fingerprint del `GOODSIG <fpr>` line y comparar.
- BUG-080: VIGENTE. `TenantSetupWizard` hook data corre antes del
  `RequirePermission`. Fix: split en outer (gate) + inner (body).
- BUG-081: VIGENTE. `FormField` `wrapControl` propagaba `required: false`
  (default) sobre cualquier `required` que el child declarara. Fix:
  pasar `required` al wrapperProps SOLO si es true.
- BUG-082: NOT-APPLICABLE. `.wizard-selected-tenant` no se usa en ningún
  JSX vivo del repo (verificado con grep).
"""
from __future__ import annotations

from pathlib import Path


VERIFY_BACKUP = Path('scripts/verify-backup.sh')
TENANT_SETUP_WIZARD = Path('admin-panel/src/features/owner-admin/tenant-setup/TenantSetupWizard.jsx')
FORM_FIELD = Path('admin-panel/src/components/ui/FormField.jsx')
RUNBOOK = Path('docs/runbooks/consent-violation-claim.md')
ADMIN_SRC = Path('admin-panel/src')


# ───── BUG-078 — NOT-APPLICABLE (runbook columnas correctas) ─────────────


def test_bug_078_runbook_uses_canonical_consent_ledger_columns():
    src = RUNBOOK.read_text()
    assert 'evidence_payload' in src, (
        'BUG-078: regresión — el runbook ya no menciona `evidence_payload` '
        '(el nombre canónico del schema). Probablemente volvió `metadata`.'
    )
    assert 'occurred_at' in src, (
        'BUG-078: regresión — el runbook ya no menciona `occurred_at`. '
        'Probablemente volvió `created_at` (que no es el campo correcto).'
    )


# ───── BUG-079 — verifier valida signer fingerprint ─────────────────────


def test_bug_079_verifier_checks_signer_fingerprint():
    src = VERIFY_BACKUP.read_text()
    assert 'BACKUP_SIGNER_FPR' in src, (
        'BUG-079: el verifier debe usar `BACKUP_SIGNER_FPR` para validar '
        'que la firma viene del signer canónico — sin esto, cualquier key '
        'del keyring (incluida la de encryption) pasa GOODSIG.'
    )
    assert 'gpg_verify_wrong_signer' in src, (
        'BUG-079: debe haber un report_failure específico cuando el '
        'fingerprint no matchea — facilita el triage operativo.'
    )


# ───── BUG-080 — TenantSetupWizard split outer/inner ────────────────────


def test_bug_080_tenant_setup_wizard_gates_before_data_hook():
    """El componente outer debe llamar `<RequirePermission>` ANTES de
    montar el body que tiene `useTenantSetupData`.
    """
    src = TENANT_SETUP_WIZARD.read_text()
    assert 'TenantSetupWizardBody' in src, (
        'BUG-080: el split debe introducir `TenantSetupWizardBody` (donde '
        'viven los hooks de fetch) para que el outer pueda gatear antes.'
    )
    # El outer NO debe llamar useTenantSetupData directamente.
    outer_start = src.find('export function TenantSetupWizard(props)')
    body_start = src.find('function TenantSetupWizardBody(')
    assert outer_start >= 0 and body_start > outer_start, (
        'BUG-080: el outer debe declararse antes del body.'
    )
    outer_block = src[outer_start:body_start]
    assert 'useTenantSetupData' not in outer_block, (
        'BUG-080: el outer NO debe invocar `useTenantSetupData` — el hook '
        'vive en el body para que el RequirePermission lo gatee.'
    )
    # El outer DEBE invocar RequirePermission.
    assert '<RequirePermission' in outer_block, (
        'BUG-080: el outer debe envolver el body en `<RequirePermission>`.'
    )


# ───── BUG-081 — FormField required NO pisa el child ───────────────────


def test_bug_081_form_field_does_not_force_required_false():
    src = FORM_FIELD.read_text()
    # El patrón viejo destructuraba `required` y SIEMPRE lo metía en wrapperProps.
    # El fix usa un `if (required) { wrapperProps.required = true; }`.
    assert "if (required)" in src, (
        'BUG-081: el FormField debe condicionalmente agregar `required` a '
        'wrapperProps SOLO si es true. Sin esto, `required: false` (default) '
        'sobrescribe cualquier `required` que el child haya declarado.'
    )
    # Defensa contra regresión: el spread directo del bug viejo.
    assert ', required })' not in src, (
        'BUG-081: regresión — `, required })` reaparece en wrapControl call. '
        'Sin la guarda `if (required)`, el bug vuelve.'
    )


# ───── BUG-082 — NOT-APPLICABLE (wizard-selected-tenant no usado) ──────


def test_bug_082_wizard_selected_tenant_class_not_used_in_jsx():
    """La clase `.wizard-selected-tenant` solo vive en `global.css` como
    dead code (ya no referenciada por ningún JSX). El bug original era
    sobre el side card que usaba esta clase y se rompía por la regla
    `.module-heading > div { min-width: 0 }`. Sin uso JSX, el bug no se
    manifiesta.
    """
    for path in ADMIN_SRC.rglob('*.jsx'):
        content = path.read_text()
        assert 'wizard-selected-tenant' not in content, (
            f'BUG-082: regresión — `{path}` referencia '
            '`wizard-selected-tenant`. Reabrir BUG-082 (limitar `.module-heading > div` '
            'a la columna de título o usar selector más específico).'
        )
