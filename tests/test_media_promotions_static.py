"""Static tests for TASK-0046 — Media library + active promotions.

Coverage:
- Schema additions for ``media_assets`` and ``promotions`` (RLS, constraints,
  triggers, GIN indexes).
- Storage validators (mime-type allowlists and per-kind size caps that mirror
  Meta WhatsApp Cloud API limits).
- The new endpoints exist under ``tenant_admin_router`` and audit correctly.
- ``promotions.attach_active_promo`` returns the right row based on validity
  windows and ``applies_to_service_ids``; ``promo_caption`` produces useful
  text.
- ``booking_flow`` calls the helper before presenting services and after the
  booking summary.
- Admin Panel registers the **Medios y promociones** module, the route
  resolves it, and ServiceCatalog wires the active-promo lookup.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.services.media_storage import (
    MEDIA_MIME_ALLOWLIST,
    MEDIA_SIZE_LIMITS_BYTES,
    media_object_key,
    validate_media_upload,
)
from app.services.promotions import (
    attach_active_promo,
    promo_caption,
    queue_promo_message,
)


SCHEMA = Path('infra/postgres/01-schema.sql')
ROUTES = Path('app/api/v1/routes.py')
SCHEMAS = Path('app/api/v1/schemas.py')
BOOKING_FLOW = Path('app/services/booking_flow.py')
PROMOTIONS = Path('app/services/promotions.py')
MEDIA_STORAGE = Path('app/services/media_storage.py')
CORE_API = Path('admin-panel/src/services/coreApi.js')
ADMIN_LAYOUT = Path('admin-panel/src/app/moduleRegistry.js')
MODULES = Path('admin-panel/src/data/modules.js')
SERVICE_CATALOG = Path('admin-panel/src/components/modules/services/ServiceCatalog.jsx')
MEDIA_MODULE = Path('admin-panel/src/components/modules/media/MediaLibraryModule.jsx')


# ───── Schema ──────────────────────────────────────────────────────────────


def test_schema_creates_media_assets_with_rls_and_index():
    schema = SCHEMA.read_text()
    assert 'create table app.media_assets' in schema
    assert "check (kind in ('image','video','pdf','audio'))" in schema
    assert 'create index gin_media_assets_tags on app.media_assets using gin(tags)' in schema
    assert (
        'alter table app.media_assets add constraint uq_media_assets_tenant_id_id '
        'unique (tenant_id, id)'
    ) in schema
    assert 'alter table app.media_assets enable row level security' in schema
    assert "'media_assets'," in schema


def test_schema_creates_promotions_with_constraints():
    schema = SCHEMA.read_text()
    assert 'create table app.promotions' in schema
    assert 'check (valid_from is null or valid_until is null or valid_from <= valid_until)' in schema
    assert (
        'alter table app.promotions add constraint uq_promotions_tenant_id_id '
        'unique (tenant_id, id)'
    ) in schema
    assert (
        'add constraint fk_promotions_tenant_media foreign key (tenant_id, media_asset_id)'
    ) in schema
    assert 'create trigger trg_promotions_touch' in schema
    assert "'promotions'," in schema


# ───── Storage validation ──────────────────────────────────────────────────


def test_mime_allowlists_per_kind_match_meta():
    assert 'image/jpeg' in MEDIA_MIME_ALLOWLIST['image']
    assert 'image/png' in MEDIA_MIME_ALLOWLIST['image']
    assert 'video/mp4' in MEDIA_MIME_ALLOWLIST['video']
    assert 'application/pdf' in MEDIA_MIME_ALLOWLIST['pdf']
    assert 'image/gif' not in MEDIA_MIME_ALLOWLIST['image']  # not Meta-supported


def test_size_caps_match_meta_limits():
    assert MEDIA_SIZE_LIMITS_BYTES['image'] == 5 * 1024 * 1024
    assert MEDIA_SIZE_LIMITS_BYTES['video'] == 16 * 1024 * 1024
    assert MEDIA_SIZE_LIMITS_BYTES['audio'] == 16 * 1024 * 1024
    assert MEDIA_SIZE_LIMITS_BYTES['pdf'] == 100 * 1024 * 1024


def test_validate_media_upload_accepts_valid_image():
    normalized = validate_media_upload(
        b'\x89PNG\r\n\x1a\n', kind='image', filename='lobby.png', mime_type='image/png'
    )
    assert normalized == 'image/png'


def test_validate_media_upload_rejects_invalid_mime_for_kind():
    with pytest.raises(ValueError):
        validate_media_upload(b'data', kind='image', filename='x.gif', mime_type='image/gif')


def test_validate_media_upload_rejects_oversized_image():
    too_big = b'x' * (MEDIA_SIZE_LIMITS_BYTES['image'] + 1)
    with pytest.raises(ValueError, match='exceeds'):
        validate_media_upload(too_big, kind='image', filename='big.jpg', mime_type='image/jpeg')


def test_validate_media_upload_rejects_unknown_kind():
    with pytest.raises(ValueError):
        validate_media_upload(b'data', kind='unknown', filename='x', mime_type='image/png')


def test_validate_media_upload_rejects_missing_data():
    with pytest.raises(ValueError, match='empty'):
        validate_media_upload(b'', kind='image', filename='x.png', mime_type='image/png')


def test_media_object_key_namespaces_by_tenant():
    key = media_object_key(
        tenant_id='abc',
        asset_id='asset-123',
        filename='hello world.jpg',
        digest='0123456789abcdef0123456789abcdef',
    )
    assert key.startswith('media/abc/asset-123/')
    # Filename is sanitized — spaces collapsed.
    assert ' ' not in key
    assert key.endswith('hello-world.jpg')


# ───── API surface ─────────────────────────────────────────────────────────


def test_media_endpoints_registered_under_admin_router():
    source = ROUTES.read_text()
    assert "@tenant_admin_router.get('/tenants/{tenant_id}/media')" in source
    assert "@tenant_admin_router.post('/tenants/{tenant_id}/media', status_code=201)" in source
    assert "@tenant_admin_router.patch('/tenants/{tenant_id}/media/{asset_id}')" in source
    assert "@tenant_admin_router.delete('/tenants/{tenant_id}/media/{asset_id}', status_code=204)" in source


def test_promotion_endpoints_registered_under_admin_router():
    source = ROUTES.read_text()
    assert "@tenant_admin_router.get('/tenants/{tenant_id}/promotions')" in source
    assert "@tenant_admin_router.post('/tenants/{tenant_id}/promotions', status_code=201)" in source
    assert "@tenant_admin_router.patch('/tenants/{tenant_id}/promotions/{promotion_id}')" in source
    assert "@tenant_admin_router.delete('/tenants/{tenant_id}/promotions/{promotion_id}', status_code=204)" in source


def test_media_and_promotion_endpoints_emit_audit():
    source = ROUTES.read_text()
    for action in (
        'media_asset.created',
        'media_asset.updated',
        'media_asset.deleted',
        'promotion.created',
        'promotion.updated',
        'promotion.deleted',
    ):
        assert action in source


def test_pydantic_promotion_schemas_exist_with_constraints():
    source = SCHEMAS.read_text()
    assert 'class PromotionCreate(BaseModel)' in source
    assert 'class PromotionUpdate(BaseModel)' in source
    assert 'class MediaAssetUpdate(BaseModel)' in source
    assert "MEDIA_KINDS = ('image', 'video', 'pdf', 'audio')" in source
    # discount_percent is bounded 0..100
    assert 'ge=0, le=100' in source


# ───── attach_active_promo helper (FakeConn) ───────────────────────────────


class FakeConn:
    def __init__(self, row=None):
        self.row = row
        self.queries = []
        self.executed = []

    async def fetchrow(self, query, *args):
        self.queries.append((query, args))
        if 'from app.promotions p' in query and 'left join app.media_assets m' in query:
            return self.row
        if 'insert into app.messages' in query:
            return {'id': uuid4()}
        return None

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return None


def test_attach_active_promo_returns_none_when_no_match():
    conn = FakeConn(row=None)
    result = asyncio.run(attach_active_promo(conn, uuid4(), uuid4()))
    assert result is None


def test_attach_active_promo_normalizes_row_to_dict():
    promo_id = uuid4()
    fake_row = {
        'id': promo_id,
        'name': 'Promo Limpieza',
        'description': 'Limpieza dental con 20% off',
        'coupon_code': 'LIMPIA20',
        'discount_percent': 20.0,
        'valid_from': None,
        'valid_until': datetime(2030, 1, 1, tzinfo=UTC),
        'applies_to_service_ids': [],
        'is_active': True,
        'sort_order': 0,
        'media_asset_id': None,
        'media_id': None,
        'media_kind': None,
        'media_label': None,
        'media_source_uri': None,
        'media_object_key': None,
        'media_storage_backend': None,
        'media_storage_bucket': None,
        'media_mime_type': None,
    }
    conn = FakeConn(row=fake_row)
    result = asyncio.run(attach_active_promo(conn, uuid4(), uuid4()))
    assert result['id'] == promo_id
    # The SQL must filter active and valid_from/until and service membership.
    assert conn.queries
    sql = conn.queries[0][0]
    assert 'p.is_active = true' in sql
    assert 'valid_from is null or p.valid_from <= $2' in sql
    assert "any(p.applies_to_service_ids)" in sql


def test_promo_caption_includes_name_discount_and_coupon():
    promo = {
        'name': 'Limpieza dental',
        'description': 'Estado de bienestar',
        'discount_percent': 20,
        'coupon_code': 'MAYO',
        'valid_until': datetime(2030, 5, 31, tzinfo=UTC),
    }
    caption = promo_caption(promo)
    assert 'Limpieza dental' in caption
    assert '20% de descuento' in caption
    assert 'MAYO' in caption
    assert 'Válido hasta' in caption


def test_queue_promo_message_queues_outbound_and_event():
    conn = FakeConn(row=None)
    promo = {
        'id': uuid4(),
        'name': 'Promo',
        'description': 'Mensaje empático',
        'discount_percent': None,
        'coupon_code': None,
        'media_source_uri': 'file:///app/media/foo.jpg',
        'media_kind': 'image',
        'media_mime_type': 'image/png',
        'valid_until': None,
    }
    asyncio.run(
        queue_promo_message(
            conn,
            tenant_id=uuid4(),
            conversation_id=uuid4(),
            channel_id=uuid4(),
            channel_account_mode='mock',
            promo=promo,
        )
    )
    # One insert into app.messages + one domain_event (message.queued).
    assert any('insert into app.messages' in q for q, _ in conn.queries)
    assert any('insert into app.domain_events' in q for q, _ in conn.executed)


# ───── booking_flow integration ────────────────────────────────────────────


def test_booking_flow_imports_promotion_helpers():
    source = BOOKING_FLOW.read_text()
    assert 'from app.services.promotions import attach_active_promo, queue_promo_message' in source
    # Hook in _present_services
    assert 'booking_flow.promo_send_failed' in source
    # Hook after booking summary
    assert 'booking_flow.promo_close_failed' in source


# ───── Admin panel wiring ──────────────────────────────────────────────────


def test_admin_modules_register_media_library():
    source = MODULES.read_text()
    assert "id: 'media-library'" in source
    assert "Medios y promociones" in source
    # UI-005: minRole → capability de la matriz de permisos.
    assert "capability: 'media.write'" in source


def test_admin_layout_routes_media_library():
    source = ADMIN_LAYOUT.read_text()
    assert "import { MediaLibraryModule }" in source
    assert "'media-library': {" in source
    assert 'Component: MediaLibraryModule' in source


def test_core_api_exposes_media_and_promotion_helpers():
    source = CORE_API.read_text()
    for fn in (
        'listMediaAssets',
        'uploadMediaAsset',
        'updateMediaAsset',
        'deleteMediaAsset',
        'listPromotions',
        'createPromotion',
        'updatePromotion',
        'deletePromotion',
    ):
        assert f'export function {fn}' in source or f'export async function {fn}' in source


def test_media_library_module_renders_uploader_and_promotions():
    source = MEDIA_MODULE.read_text()
    assert 'uploadMediaAsset' in source
    assert 'createPromotion' in source
    assert 'updatePromotion' in source
    assert 'applies_to_service_ids' in source
    # Size limit hint shown to the user.
    assert 'Imagen 5MB' in source
    # File-picker accepts the right mime types.
    assert 'image/jpeg' in source
    assert 'video/mp4' in source


def test_service_catalog_loads_and_renders_active_promotions():
    source = SERVICE_CATALOG.read_text()
    assert 'listPromotions' in source
    assert 'servicePromos' in source
    assert 'data-service-promos' in source
