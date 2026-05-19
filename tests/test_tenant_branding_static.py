"""Static tests for UI-012-FU — Backend support para ``brand_logo_url``.

These tests inspect source files (no FastAPI app spin-up, no DB) so they
run in CI without Docker. They cover:

- the schema declares the ``brand_logo_url`` column + length constraint;
- the PATCH ``/tenants/{id}/settings`` whitelists ``brand_logo_url`` and
  enforces the 1024-char limit;
- the POST ``/tenants/{id}/branding/logo`` endpoint exists, uses
  ``ensure_tenant_access``, sets ``app.tenant_id`` for RLS, reuses
  ``store_media_file`` with ``kind='image'``, updates
  ``tenant_settings.brand_logo_url`` and emits the
  ``tenant_settings.branding_updated`` audit event;
- the admin panel exposes the ``uploadTenantBrandLogo`` API helper and
  surfaces the uploader in ``BotPersonalityTab``.
"""
from pathlib import Path
from tests._routes_aggregator import routes_aggregated_source

SCHEMA = Path('infra/postgres/01-schema.sql')
CORE_API = Path('admin-panel/src/services/coreApi.js')
BOT_TAB = Path(
    'admin-panel/src/features/owner-admin/tenant-setup/components/BotPersonalityTab.jsx'
)
SETUP_HOOK = Path(
    'admin-panel/src/features/owner-admin/tenant-setup/hooks/useTenantSetupData.js'
)


def test_schema_declares_brand_logo_url_column():
    source = SCHEMA.read_text()
    # The column lives in app.tenant_settings.
    assert 'brand_logo_url text null' in source
    # Length constraint is part of the table contract.
    assert 'tenant_settings_brand_logo_url_len' in source
    assert 'length(brand_logo_url) <= 1024' in source
    # Migration hint for existing databases.
    assert 'TASK-UI-012-FU' in source
    assert 'alter table app.tenant_settings add column if not exists brand_logo_url' in source


def test_patch_settings_whitelists_brand_logo_url():
    source = routes_aggregated_source()
    # ``brand_logo_url`` must appear inside the ``allowed`` tuple of
    # patch_settings. We use a soft check: the literal must show up
    # near 'no_train', 'notification_settings', 'bot_personality'.
    assert "'brand_logo_url'" in source
    assert "brand_logo_url=$9" in source  # update statement
    # Length sanity check at request time.
    assert 'brand_logo_url must be at most 1024 chars' in source
    assert 'brand_logo_url must be a string or null' in source


def test_logo_upload_endpoint_is_registered_under_admin_router():
    source = routes_aggregated_source()
    assert "@tenant_admin_router.post('/tenants/{tenant_id}/branding/logo')" in source
    assert 'async def upload_tenant_brand_logo' in source


def test_logo_upload_enforces_tenant_access_and_rls():
    source = routes_aggregated_source()
    # Carve out the upload_tenant_brand_logo function and assert it
    # individually uses the four security primitives.
    start = source.index('async def upload_tenant_brand_logo')
    end = source.index('@tenant_admin_router.get', start)
    fn_source = source[start:end]
    assert 'ensure_tenant_access' in fn_source
    assert "set_config('app.tenant_id'" in fn_source
    assert 'await audit(' in fn_source
    # action name must match the spec (auditable from the alerts UI).
    assert "action='tenant_settings.branding_updated'" in fn_source


def test_logo_upload_reuses_media_storage():
    source = routes_aggregated_source()
    start = source.index('async def upload_tenant_brand_logo')
    end = source.index('@tenant_admin_router.get', start)
    fn_source = source[start:end]
    # Reuse the existing storage helper so MIME allowlist + size limits
    # apply uniformly.
    assert 'store_media_file(' in fn_source
    assert "kind='image'" in fn_source
    # The resulting public URL must be persisted in tenant_settings.
    assert 'update app.tenant_settings set brand_logo_url=' in fn_source
    # The asset must be tracked in media_assets so it can be deleted/listed.
    assert 'insert into app.media_assets' in fn_source


def test_admin_panel_exposes_brand_logo_helper():
    source = CORE_API.read_text()
    assert 'export function uploadTenantBrandLogo' in source
    assert "/tenants/${tenantId}/branding/logo" in source
    # The helper must use FormData (multipart) — JSON would fail at the
    # multipart parser on the backend.
    helper_start = source.index('export function uploadTenantBrandLogo')
    helper_end = source.index('export function listRetentionPolicies', helper_start)
    helper_src = source[helper_start:helper_end]
    assert 'FormData' in helper_src
    assert "formData.append('file'" in helper_src


def test_bot_personality_tab_renders_brand_logo_uploader():
    source = BOT_TAB.read_text()
    assert 'Logo de marca' in source
    assert 'image/png,image/jpeg,image/webp' in source
    assert 'handleUploadBrandLogo' in source
    assert 'handleClearBrandLogo' in source
    # The empty/preview branch must be there for the no-logo case.
    assert 'brand-logo-empty' in source


def test_use_tenant_setup_data_wires_brand_logo_handlers():
    source = SETUP_HOOK.read_text()
    assert 'uploadTenantBrandLogo' in source
    assert 'handleUploadBrandLogo' in source
    assert 'handleClearBrandLogo' in source
    assert 'brandLogoUrl' in source
