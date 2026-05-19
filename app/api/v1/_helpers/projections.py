"""Projection string constants extracted from app/api/v1/routes.py."""
from __future__ import annotations


WEB_CHANNEL_PROJECTION = (
    "id, tenant_id, provider, status, account_mode, allowed_origins, widget_config, "
    "token_ref, created_at, updated_at"
)


MESSENGER_CHANNEL_PROJECTION = (
    "id, tenant_id, provider, business_id, page_id, instagram_account_id, "
    "account_mode, status, service_window_hours, token_ref, app_secret_ref, "
    "verify_token_hash, created_at, updated_at"
)


SERVICE_CATALOG_COLUMNS = (
    'id',
    'tenant_id',
    'name',
    'category',
    'description',
    'price_amount',
    'price_currency',
    'duration_minutes',
    'preparation_notes',
    'post_service_notes',
    'recall_interval_days',
    'recall_template_id',
    'applies_when',
    'is_active',
    'sort_order',
    'metadata',
    'created_at',
    'updated_at',
)
SERVICE_CATALOG_PROJECTION = ', '.join(SERVICE_CATALOG_COLUMNS)


# ── Qualification questions (TASK-0042) ─────────────────────────────────────
QUALIFICATION_PROJECTION = (
    'id, tenant_id, position, label, kind, options, required, '
    'applies_to_service_ids, preset, key, created_at, updated_at'
)


# ── Media library + promotions (TASK-0046) ─────────────────────────────────
MEDIA_ASSET_COLUMNS = (
    'id, tenant_id, kind, label, description, storage_backend, storage_bucket, '
    'object_key, source_uri, mime_type, sha256, size_bytes, tags, '
    'uploaded_by_user_id, created_at, updated_at'
)
PROMOTION_COLUMNS = (
    'id, tenant_id, name, description, media_asset_id, valid_from, valid_until, '
    'applies_to_service_ids, coupon_code, discount_percent, is_active, '
    'sort_order, created_at, updated_at'
)


SEGMENT_PROJECTION = (
    'id, tenant_id, name, description, kind, rules, contact_count, '
    'last_refreshed_at, is_system, created_by, created_at, updated_at'
)


CAMPAIGN_PROJECTION = (
    'id, tenant_id, name, status, template_id, template_variables, '
    'segment_filter, segment_id, launched_snapshot_at, scheduled_at, '
    'recipient_count, sent_count, delivered_count, read_count, '
    'failed_count, started_at, completed_at, cost_amount, cost_currency, '
    'attribution_window_days, created_by, created_at, updated_at'
)
