"""Fix-group 09: BUG-063..BUG-067.

- BUG-063: NOT-APPLICABLE. UI-017 ya monta `RouterProvider` siempre que
  la sesión esté resuelta (autenticada o anónima). El `IndexRedirect`
  decide qué pintar.
- BUG-064: VIGENTE. `page_id` / `instagram_account_id` sin partial unique
  index → dos tenants pueden reclamar el mismo Meta ID. Fix: agregar
  `ux_tenant_channels_page_active` y `ux_tenant_channels_ig_account_active`
  (mirroring de SEC-003 para phone_number_id).
- BUG-065: VIGENTE. MFA Action en `configure-auth0.sh` llamaba
  `challengeWith({ type: 'otp' })` hardcoded → usuarios con factor
  WebAuthn/push/SMS no podían loguear. Fix: usar `event.user.enrolledFactors`
  + `challengeWithAny(enrolled)` con fallback a OTP si ninguno.
- BUG-066: NOT-APPLICABLE. `audit_durably` (en audit.py) ya setea el GUC
  `app.tenant_id` antes del INSERT (BUG-010), así que TODAS las llamadas
  desde routes.py heredan el fix.
- BUG-067: NOT-APPLICABLE. `scripts/lib/postgres-url.sh::parse_db_url` ya
  hace URL-decode del password (líneas 38, 73).
"""
from __future__ import annotations

from pathlib import Path


SCHEMA = Path('infra/postgres/01-schema.sql')
MIGRATIONS = Path('infra/postgres/03-migrations.sql')
CONFIGURE_AUTH0 = Path('scripts/configure-auth0.sh')
AUDIT = Path('app/services/audit.py')
URL_HELPER = Path('scripts/lib/postgres-url.sh')
APP_JSX = Path('admin-panel/src/App.jsx')


# ───── BUG-063 — NOT-APPLICABLE (router siempre mount) ───────────────────


def test_bug_063_router_provider_mounts_when_session_resolved():
    src = APP_JSX.read_text()
    # El RouterProvider debe estar dentro del else de isLoading, sin
    # condición isAuthenticated alrededor.
    assert 'RouterProvider router={appRouter}' in src, (
        'BUG-063: regresión — `RouterProvider` desapareció de App.jsx.'
    )
    # No debe haber un gate isAuthenticated alrededor del RouterProvider.
    routerprov_idx = src.find('RouterProvider router={appRouter}')
    surrounding = src[max(0, routerprov_idx - 200):routerprov_idx]
    assert 'isAuthenticated' not in surrounding, (
        'BUG-063: regresión — `RouterProvider` volvió a gatearse por '
        '`isAuthenticated` → `/admin/` anon muestra LoginScreen viejo en '
        'vez del IndexRedirect que rutea a `<Landing />`.'
    )


# ───── BUG-064 — partial unique index para page/ig ───────────────────────


def test_bug_064_schema_has_unique_index_for_page_active():
    src = SCHEMA.read_text()
    assert 'ux_tenant_channels_page_active' in src, (
        'BUG-064: el schema debe declarar `ux_tenant_channels_page_active` '
        '(partial unique index sobre `page_id WHERE status=active`).'
    )
    assert "where status='active' and page_id is not null" in src, (
        'BUG-064: el WHERE del partial unique debe filtrar `status=active` y '
        '`page_id is not null` — el mismo predicado que phone_number_id.'
    )


def test_bug_064_schema_has_unique_index_for_ig_active():
    src = SCHEMA.read_text()
    assert 'ux_tenant_channels_ig_account_active' in src, (
        'BUG-064: el schema debe declarar `ux_tenant_channels_ig_account_active`.'
    )
    assert "where status='active' and instagram_account_id is not null" in src, (
        'BUG-064: WHERE específico para instagram_account_id.'
    )


def test_bug_064_migration_adds_partial_unique_indices():
    src = MIGRATIONS.read_text()
    assert 'create unique index if not exists ux_tenant_channels_page_active' in src, (
        'BUG-064: la migración debe crear el unique index idempotentemente.'
    )
    assert 'create unique index if not exists ux_tenant_channels_ig_account_active' in src, (
        'BUG-064: misma migración para instagram_account_id.'
    )


# ───── BUG-065 — MFA Action respeta enrolled factors ────────────────────


def test_bug_065_mfa_action_reads_enrolled_factors():
    src = CONFIGURE_AUTH0.read_text()
    assert 'event.user.enrolledFactors' in src, (
        'BUG-065: la MFA Action debe leer `event.user.enrolledFactors` '
        'para respetar el factor que el usuario tiene enrolado.'
    )
    assert 'challengeWithAny(enrolled)' in src, (
        "BUG-065: debe usar `challengeWithAny(enrolled)` con los factores "
        "enrolados, no `challengeWith({ type: 'otp' })` hardcoded."
    )


def test_bug_065_mfa_action_only_filters_confirmed_factors():
    src = CONFIGURE_AUTH0.read_text()
    assert "f.status === 'confirmed'" in src, (
        'BUG-065: solo factores con `status === confirmed` cuentan — los que '
        'están `pending` o `revoked` no se pueden challenge.'
    )


# ───── BUG-066 — NOT-APPLICABLE (audit_durably common fix) ──────────────


def test_bug_066_audit_durably_sets_tenant_id_guc():
    src = AUDIT.read_text()
    assert "set_config('app.tenant_id'" in src, (
        'BUG-066/045: regresión — `audit_durably` ya no setea `app.tenant_id` '
        'GUC. RLS volverá a rechazar inserts con tenant_id != NULL.'
    )


# ───── BUG-067 — NOT-APPLICABLE (parse_db_url decodes) ──────────────────


def test_bug_067_parse_db_url_decodes_url_encoded_passwords():
    src = URL_HELPER.read_text()
    assert 'parse_db_url' in src, (
        'BUG-067: el helper `parse_db_url` debe existir.'
    )
    # El comment / la implementación menciona %40 -> @ decode.
    assert '%40' in src, (
        'BUG-067: el helper debe documentar/implementar el URL-decode de '
        '`%40` → `@` (caso clásico de passwords con `@` URL-encoded).'
    )
