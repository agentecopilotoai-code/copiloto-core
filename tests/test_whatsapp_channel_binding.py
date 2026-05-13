"""Static tests for TASK-0081: WhatsApp webhook binding & uniqueness.

Covers BUG20 (handler used a single channel/tenant for all changes in the
payload) and BUG21 (no global uniqueness on ``phone_number_id`` between
tenants).
"""
from __future__ import annotations

from pathlib import Path

SCHEMA = Path('infra/postgres/01-schema.sql')
ROUTES = Path('app/api/v1/routes.py')


def test_schema_has_unique_partial_index_on_active_phone_number_id():
    source = SCHEMA.read_text()
    assert 'ux_tenant_channels_phone_number_active' in source
    # The index must be partial (active rows only) to allow re-claiming a
    # number after offboarding the previous tenant.
    idx = source.index('ux_tenant_channels_phone_number_active')
    block = source[max(0, idx - 100):idx + 400]
    assert 'unique index' in block.lower()
    assert "status='active'" in block
    assert 'phone_number_id is not null' in block


def test_schema_keeps_non_unique_lookup_index_for_speed():
    """The non-unique lookup index ``ix_tenant_channels_phone`` is kept for
    cheap webhook lookups (no UNIQUE constraint check on every read)."""
    source = SCHEMA.read_text()
    assert 'ix_tenant_channels_phone on app.tenant_channels(phone_number_id)' in source


# ── BUG21: admin endpoint refuses cross-tenant phone_number_id reuse ─────────


def test_create_channel_rejects_phone_number_id_active_in_another_tenant():
    source = ROUTES.read_text()
    start = source.index("@tenant_admin_router.post('/tenants/{tenant_id}/channels/whatsapp'")
    end = source.index("@tenant_admin_router.get('/tenants/{tenant_id}/channels/whatsapp/health'")
    block = source[start:end]
    # The handler queries for an existing active row with the same phone_number_id
    # in a DIFFERENT tenant and returns 409.
    assert "tenant_id <> $2" in block
    assert "status_code=409" in block
    assert 'phone_number_id is already bound' in block
    assert "support_mode" in block  # cross-tenant lookup needs RLS bypass


def test_create_channel_runs_uniqueness_check_before_writing_secrets():
    """If we wrote secrets first and only then realized the binding was
    forbidden, the secret store would carry orphan secrets. The 409 path must
    short-circuit before ``write_tenant_secret`` is called."""
    source = ROUTES.read_text()
    start = source.index("@tenant_admin_router.post('/tenants/{tenant_id}/channels/whatsapp'")
    end = source.index("@tenant_admin_router.get('/tenants/{tenant_id}/channels/whatsapp/health'")
    block = source[start:end]
    idx_409 = block.index("status_code=409")
    idx_write = block.index("write_tenant_secret")
    assert idx_409 < idx_write


# ── BUG20: webhook handler re-resolves per change ────────────────────────────


def test_webhook_handler_validates_change_phone_number_id_against_signed_channel():
    source = ROUTES.read_text()
    start = source.index("async def receive_whatsapp_webhook(")
    block = source[start:start + 8000]
    # The handler captures the signed channel's phone_number_id and uses it
    # to validate each change.
    assert "signed_channel_phone_id = phone_number_id" in block
    assert "change_phone_id" in block
    assert "metadata" in block
    assert 'webhook.phone_number_id_mismatch' in block


def test_webhook_handler_drops_mismatched_changes_with_audit():
    source = ROUTES.read_text()
    start = source.index("async def receive_whatsapp_webhook(")
    block = source[start:start + 8000]
    # The mismatch branch must (a) emit audit + (b) continue iterating; the
    # rest of the changes must still be processed.
    mismatch_idx = block.index('webhook.phone_number_id_mismatch')
    after = block[mismatch_idx:mismatch_idx + 800]
    assert 'continue' in after
    assert 'signed_phone_number_id' in block
    assert 'change_phone_number_id' in block


def test_webhook_handler_uses_system_actor_type_for_audit_compliance():
    """``audit_logs.actor_type`` only accepts a fixed set including
    ``system``; the bug fix must NOT introduce a new value that the CHECK
    constraint would reject at runtime."""
    source = ROUTES.read_text()
    start = source.index("async def receive_whatsapp_webhook(")
    block = source[start:start + 8000]
    mismatch_idx = block.index('webhook.phone_number_id_mismatch')
    # Look for the actor_type in the audit() call immediately above
    window = block[max(0, mismatch_idx - 600):mismatch_idx + 200]
    assert "actor_type='system'" in window


def test_audit_logs_actor_type_check_includes_system():
    """Regression guard: the audit row produced by the mismatch branch must
    pass the actor_type CHECK constraint."""
    schema = SCHEMA.read_text()
    constraint = schema[schema.index('audit_logs'):schema.index('audit_logs') + 2000]
    assert "'system'" in constraint
