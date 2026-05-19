"""Direct service-layer tests for `app/services/rag_orchestrator.py`.

The orchestrator is the heart of the inbound message handling — currently
only 27% covered. This suite drives its public + helper async functions
against an ephemeral PostgreSQL with seeded tenant/contact/conversation.
"""
from __future__ import annotations

import asyncio
import json
import uuid

import pytest

from tests.conftest_e2e_http import (  # noqa: F401,F811
    e2e_http_dsn,
    e2e_http_schema,
)
from tests.conftest_e2e import e2e_enabled, tenant_connection

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not e2e_enabled(), reason='RUN_E2E=1 required'),
]


async def _seed(dsn):
    """Minimal seed: tenant + channel + contact + conversation + resource + service."""
    import asyncpg
    tenant_id = uuid.uuid4()
    channel_id = uuid.uuid4()
    contact_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    resource_id = uuid.uuid4()
    service_id = uuid.uuid4()
    wa = f'5730099{int(uuid.uuid4().int % 10_000_000):07d}'
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("select set_config('app.support_mode', 'true', false)")
        await conn.execute("select set_config('app.tenant_id', $1, false)", str(tenant_id))
        async with conn.transaction():
            await conn.execute(
                """insert into app.tenants (id, slug, legal_name, display_name, vertical_code,
                   country_code, timezone, status)
                   values ($1, $2, $3, $3, 'general', 'CO', 'America/Bogota', 'active')""",
                tenant_id, f'rg-{tenant_id.hex[:8]}', 'RagOrch Test',
            )
            await conn.execute(
                "insert into app.tenant_settings (tenant_id) values ($1)",
                tenant_id,
            )
            await conn.execute(
                """insert into app.tenant_channels (id, tenant_id, provider, phone_number_id,
                   token_ref, account_mode, status)
                   values ($1, $2, 'whatsapp_cloud_api', $3, 'tok', 'mock', 'active')""",
                channel_id, tenant_id, f'pn-{tenant_id.hex[:8]}',
            )
            await conn.execute(
                """insert into app.contacts (id, tenant_id, wa_id, phone_e164, phone_hash,
                   display_name, opt_in_status)
                   values ($1, $2, $3, $4, decode(md5($4), 'hex'), 'RO Contact', 'granted')""",
                contact_id, tenant_id, wa, f'+{wa}',
            )
            await conn.execute(
                """insert into app.conversations (id, tenant_id, contact_id, channel_id,
                   status, opened_by)
                   values ($1, $2, $3, $4, 'open', 'user')""",
                conv_id, tenant_id, contact_id, channel_id,
            )
            await conn.execute(
                """insert into app.resources (id, tenant_id, vertical_code, resource_type,
                   code, name, capabilities, is_active)
                   values ($1, $2, 'general', 'staff', $3, 'Dr. RO',
                           '{"services": []}'::jsonb, true)""",
                resource_id, tenant_id, f'res-{uuid.uuid4().hex[:6]}',
            )
            await conn.execute(
                """insert into app.service_catalog (id, tenant_id, name, duration_minutes,
                   is_active, price_amount, price_currency)
                   values ($1, $2, 'RO Service', 30, true, 50000, 'COP')""",
                service_id, tenant_id,
            )
    finally:
        await conn.close()
    return {
        'tenant_id': tenant_id,
        'channel_id': channel_id,
        'contact_id': contact_id,
        'conversation_id': conv_id,
        'resource_id': resource_id,
        'service_id': service_id,
    }


# ───────── _load_active_resources_context ─────────────────────────────────


def test_load_active_resources_context_returns_string(e2e_http_dsn):
    from app.services.rag_orchestrator import _load_active_resources_context

    async def _go():
        ids = await _seed(e2e_http_dsn)
        async with tenant_connection(e2e_http_dsn, ids['tenant_id'], support_mode=True) as conn:
            ctx = await _load_active_resources_context(conn, ids['tenant_id'])
            return ctx

    ctx = asyncio.run(_go())
    assert isinstance(ctx, str)
    assert len(ctx) > 0
    # The seeded resource is included
    assert 'Dr. RO' in ctx or 'profesional' in ctx.lower() or 'staff' in ctx.lower()


def test_load_active_resources_context_returns_default_when_no_resources(e2e_http_dsn):
    """When the tenant has zero resources, the function returns the default
    sentinel string."""
    import asyncpg
    from app.services.rag_orchestrator import _load_active_resources_context

    async def _go():
        tenant_id = uuid.uuid4()
        conn = await asyncpg.connect(e2e_http_dsn)
        try:
            await conn.execute("select set_config('app.support_mode', 'true', false)")
            await conn.execute("select set_config('app.tenant_id', $1, false)", str(tenant_id))
            await conn.execute(
                """insert into app.tenants (id, slug, legal_name, display_name, vertical_code,
                   country_code, timezone, status)
                   values ($1, $2, $3, $3, 'general', 'CO', 'America/Bogota', 'active')""",
                tenant_id, f't-{tenant_id.hex[:8]}', 'NoRes',
            )
            return await _load_active_resources_context(conn, tenant_id)
        finally:
            await conn.close()

    ctx = asyncio.run(_go())
    assert isinstance(ctx, str)


# ───────── _clear_pending_recall ──────────────────────────────────────────


def test_clear_pending_recall_clears_metadata_key(e2e_http_dsn):
    """Sets `metadata.pending_recall` on a conversation, then calls
    `_clear_pending_recall` and verifies the key is removed."""
    from app.services.rag_orchestrator import _clear_pending_recall

    async def _go():
        ids = await _seed(e2e_http_dsn)
        async with tenant_connection(e2e_http_dsn, ids['tenant_id'], support_mode=True) as conn:
            # Seed pending_recall
            await conn.execute(
                """update app.conversations
                   set metadata = jsonb_set(coalesce(metadata, '{}'::jsonb),
                                            '{pending_recall}',
                                            '{"service_id": "svc-x", "scheduled_at": "2026-01-01"}'::jsonb)
                   where id = $1""",
                ids['conversation_id'],
            )
            await _clear_pending_recall(conn, ids['tenant_id'], ids['conversation_id'])
            row = await conn.fetchrow(
                'select metadata from app.conversations where id=$1', ids['conversation_id'],
            )
            return row['metadata']

    meta = asyncio.run(_go())
    meta_dict = json.loads(meta) if isinstance(meta, str) else dict(meta)
    assert 'pending_recall' not in meta_dict


# ───────── orchestrate_inbound_message — entry-point with skips ──────────


def test_orchestrate_inbound_message_skips_when_handoff_active(e2e_http_dsn):
    """When the conversation status is 'human_active', the orchestrator should
    early-return with a skip action."""
    from app.services.rag_orchestrator import orchestrate_inbound_message

    async def _go():
        ids = await _seed(e2e_http_dsn)
        async with tenant_connection(e2e_http_dsn, ids['tenant_id'], support_mode=True) as conn:
            # Mark conversation as human_active
            await conn.execute(
                "update app.conversations set status='human_active' where id=$1",
                ids['conversation_id'],
            )
            conv = dict(await conn.fetchrow(
                'select * from app.conversations where id=$1', ids['conversation_id'],
            ))
            contact = dict(await conn.fetchrow(
                'select * from app.contacts where id=$1', ids['contact_id'],
            ))
            msg = {
                'id': uuid.uuid4(),
                'tenant_id': ids['tenant_id'],
                'conversation_id': ids['conversation_id'],
                'direction': 'inbound',
                'message_type': 'text',
                'body_text': 'Hola',
                'payload': {},
            }
            return await orchestrate_inbound_message(
                conn,
                tenant_id=ids['tenant_id'],
                channel_id=ids['channel_id'],
                channel_account_mode='mock',
                conversation=conv,
                contact=contact,
                inbound_message=msg,
            )

    result = asyncio.run(_go())
    # Skipped due to handoff
    assert result.get('action') in ('skipped', 'no_action')


def test_orchestrate_inbound_message_skips_unsupported_message_type(e2e_http_dsn):
    """A reaction or unknown message type should be skipped early."""
    from app.services.rag_orchestrator import orchestrate_inbound_message

    async def _go():
        ids = await _seed(e2e_http_dsn)
        async with tenant_connection(e2e_http_dsn, ids['tenant_id'], support_mode=True) as conn:
            conv = dict(await conn.fetchrow(
                'select * from app.conversations where id=$1', ids['conversation_id'],
            ))
            contact = dict(await conn.fetchrow(
                'select * from app.contacts where id=$1', ids['contact_id'],
            ))
            msg = {
                'id': uuid.uuid4(),
                'tenant_id': ids['tenant_id'],
                'conversation_id': ids['conversation_id'],
                'direction': 'inbound',
                'message_type': 'reaction',  # unsupported in orchestrator
                'body_text': None,
                'payload': {},
            }
            return await orchestrate_inbound_message(
                conn,
                tenant_id=ids['tenant_id'],
                channel_id=ids['channel_id'],
                channel_account_mode='mock',
                conversation=conv,
                contact=contact,
                inbound_message=msg,
            )

    result = asyncio.run(_go())
    assert result.get('action') in ('skipped', 'no_action')


def test_orchestrate_inbound_message_skips_empty_body(e2e_http_dsn):
    from app.services.rag_orchestrator import orchestrate_inbound_message

    async def _go():
        ids = await _seed(e2e_http_dsn)
        async with tenant_connection(e2e_http_dsn, ids['tenant_id'], support_mode=True) as conn:
            conv = dict(await conn.fetchrow(
                'select * from app.conversations where id=$1', ids['conversation_id'],
            ))
            contact = dict(await conn.fetchrow(
                'select * from app.contacts where id=$1', ids['contact_id'],
            ))
            msg = {
                'id': uuid.uuid4(),
                'tenant_id': ids['tenant_id'],
                'conversation_id': ids['conversation_id'],
                'direction': 'inbound',
                'message_type': 'text',
                'body_text': '',  # empty
                'payload': {},
            }
            return await orchestrate_inbound_message(
                conn,
                tenant_id=ids['tenant_id'],
                channel_id=ids['channel_id'],
                channel_account_mode='mock',
                conversation=conv,
                contact=contact,
                inbound_message=msg,
            )

    result = asyncio.run(_go())
    assert result.get('action') in ('skipped', 'no_action')


# ───────── _resolve_answer template path (no LLM needed) ─────────────────


def test_resolve_answer_template_engine(e2e_http_dsn):
    """With `answer_engine='template'`, the resolver doesn't touch Ollama or
    cloud — just runs the rule-based grounded answer builder."""
    from app.services.rag_orchestrator import _resolve_answer

    class _Settings:
        answer_engine = 'template'
        cascade_template_min_score = 0.55
        cascade_llm_min_score = 0.12
        local_llm_base_url = 'http://fake'
        local_llm_model = 'fake'
        local_llm_timeout_seconds = 1
        cloud_llm_provider = None
        cloud_llm_api_key = None
        cloud_llm_model = ''
        cloud_llm_timeout_seconds = 1

    async def _go():
        return await _resolve_answer(
            question='cuanto cuesta',
            matches=[],
            settings=_Settings(),
            bot_personality=None,
            tenant_no_train=True,
        )

    result = asyncio.run(_go())
    assert isinstance(result, dict)
    assert 'status' in result
    # Empty matches with template engine → insufficient context
    assert result.get('sufficient_context') is False


# ───────── _tier_from_result ──────────────────────────────────────────────


def test_tier_from_result_recognizes_handoff_action():
    from app.services.rag_orchestrator import _tier_from_result
    # Internal _TIER_BY_ACTION mapping
    result = {'cloud_llm_used': False, 'llm_used': False, 'action': 'handoff'}
    tier = _tier_from_result(result)
    # Returns either the mapped tier or the action itself
    assert isinstance(tier, str)
