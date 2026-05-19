"""Static tests for TASK-0082: contact identity validation & mutation.

Covers BUG05 (widget web reusing existing contact by phone match) and BUG22
(``POST /v1/conversations/start`` accepting ``wa_id`` and overwriting
``phone_e164``/``wa_id`` on conflict via ``upsert_whatsapp_contact``).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.api.v1.schemas import ContactPhoneUpdate, ConversationStart
from tests._routes_aggregator import routes_aggregated_source

SCHEMAS = Path('app/api/v1/schemas.py')


# ── BUG22 schema: wa_id is gone, contact_id is the canonical identifier ─────


def test_conversation_start_schema_no_longer_accepts_wa_id():
    fields = ConversationStart.model_fields
    assert 'wa_id' not in fields
    assert 'contact_id' in fields
    assert 'phone_e164' in fields


def test_conversation_start_phone_is_optional_when_contact_id_provided():
    fields = ConversationStart.model_fields
    # phone_e164 must be optional; the endpoint enforces the "at least one of"
    # rule and rejects with 422 if neither is provided.
    assert fields['phone_e164'].is_required() is False
    assert fields['contact_id'].is_required() is False


def test_conversation_start_payload_accepts_contact_id_only():
    payload = ConversationStart(
        tenant_id='00000000-0000-0000-0000-000000000001',
        contact_id='00000000-0000-0000-0000-000000000002',
    )
    assert payload.contact_id is not None
    assert payload.phone_e164 is None


def test_conversation_start_payload_accepts_phone_only():
    payload = ConversationStart(
        tenant_id='00000000-0000-0000-0000-000000000001',
        phone_e164='+573001234567',
    )
    assert payload.phone_e164 == '+573001234567'
    assert payload.contact_id is None


def test_conversation_start_rejects_arbitrary_wa_id_field():
    with pytest.raises(Exception):
        ConversationStart.model_validate(
            {
                'tenant_id': '00000000-0000-0000-0000-000000000001',
                'phone_e164': '+573001234567',
                'wa_id': '573001234567',
            },
            strict=False,
        )


# ── BUG22 endpoint: start_conversation never mutates an existing contact ────


def test_start_conversation_never_calls_upsert_whatsapp_contact():
    """The legacy path called ``upsert_whatsapp_contact`` which UPDATEd
    phone_e164/wa_id on conflict. The new handler must not invoke it from
    this endpoint."""
    source = routes_aggregated_source()
    start = source.index('async def start_conversation(')
    end = source.index('\n@', start + 1)
    block = source[start:end]
    assert 'upsert_whatsapp_contact' not in block


def test_start_conversation_requires_contact_id_or_phone_e164():
    source = routes_aggregated_source()
    start = source.index('async def start_conversation(')
    end = source.index('\n@', start + 1)
    block = source[start:end]
    assert 'contact_id or phone_e164 is required' in block
    assert 'status_code=422' in block


def test_start_conversation_creates_new_contact_only_when_phone_unknown():
    source = routes_aggregated_source()
    start = source.index('async def start_conversation(')
    end = source.index('\n@', start + 1)
    block = source[start:end]
    # The new code looks up by phone_e164 first; only INSERTs when no row
    # already exists.
    assert "select * from app.contacts where tenant_id=$1 and phone_e164=$2" in block
    assert 'if not contact:' in block
    assert 'insert into app.contacts' in block


def test_start_conversation_rejects_unknown_contact_id():
    source = routes_aggregated_source()
    start = source.index('async def start_conversation(')
    end = source.index('\n@', start + 1)
    block = source[start:end]
    assert "select * from app.contacts where tenant_id=$1 and id=$2" in block
    assert 'Contact not found in this tenant' in block


# ── PATCH /contacts/{id}/phone: dedicated endpoint, manager+ only, audited ──


def test_patch_contact_phone_endpoint_exists_with_manager_gate():
    source = routes_aggregated_source()
    assert "@tenant_ops_router.patch('/contacts/{contact_id}/phone')" in source
    start = source.index("@tenant_ops_router.patch('/contacts/{contact_id}/phone')")
    end = source.index('\n@', start + 1)
    block = source[start:end]
    assert "ensure_tenant_role(request, conn, tenant_id, 'manager')" in block


def test_patch_contact_phone_writes_audit_log():
    source = routes_aggregated_source()
    start = source.index("@tenant_ops_router.patch('/contacts/{contact_id}/phone')")
    end = source.index('\n@', start + 1)
    block = source[start:end]
    assert "action='contact.phone_changed'" in block
    assert 'previous_phone_last4' in block
    assert 'new_phone_last4' in block


def test_patch_contact_phone_rejects_collision_with_another_contact():
    source = routes_aggregated_source()
    start = source.index("@tenant_ops_router.patch('/contacts/{contact_id}/phone')")
    end = source.index('\n@', start + 1)
    block = source[start:end]
    assert 'status_code=409' in block
    assert 'already has this phone_e164' in block


def test_patch_contact_phone_updates_wa_id_and_phone_hash_together():
    """Identity columns must stay consistent — phone_e164, wa_id, phone_hash
    are derived from each other."""
    source = routes_aggregated_source()
    start = source.index("@tenant_ops_router.patch('/contacts/{contact_id}/phone')")
    end = source.index('\n@', start + 1)
    block = source[start:end]
    assert 'phone_e164=$3' in block
    assert 'wa_id=$4' in block
    assert 'phone_hash=$5' in block


def test_contact_phone_update_schema_accepts_phone_and_reason():
    payload = ContactPhoneUpdate(phone_e164='+573001234567', reason='Cliente cambió')
    assert payload.phone_e164 == '+573001234567'
    assert payload.reason == 'Cliente cambió'


def test_contact_phone_update_schema_rejects_short_phone():
    with pytest.raises(Exception):
        ContactPhoneUpdate(phone_e164='+1')


# ── BUG05 documentation: widget already synthesizes fresh identity ──────────


def test_web_chat_start_synthesizes_fresh_identity_not_reuse_existing():
    """BUG05 was fixed previously: the widget creates a new contact with a
    synthesized wa_id and stores the user-supplied phone as ``unverified_phone``
    metadata. This regression guard pins the behaviour so a future refactor
    cannot re-introduce phone-based contact reuse from the widget."""
    source = routes_aggregated_source()
    start = source.index('async def web_chat_start(')
    end = source.index('\n@', start + 1) if '\n@' in source[start:] else len(source)
    block = source[start:end]
    assert 'synthesize_web_identity' in block
    assert "'phone_verified': False" in block
    assert 'unverified_phone' in block
    # Most importantly: the widget must NOT call upsert_whatsapp_contact
    # (which would reuse a contact by phone match).
    assert 'upsert_whatsapp_contact' not in block


def test_web_chat_start_seed_includes_random_nonce():
    """Even if two visitors submit the same phone/email, the synthesized
    identity must differ — the seed mixes a 16-byte nonce."""
    source = routes_aggregated_source()
    start = source.index('async def web_chat_start(')
    end = start + 5000
    block = source[start:end]
    assert 'secrets.token_hex(16)' in block
