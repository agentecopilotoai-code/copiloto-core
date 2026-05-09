import asyncio
import os
from uuid import UUID

import asyncpg
import pytest

pytestmark = pytest.mark.requires_db


TENANT_A = UUID('aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaa1')
TENANT_B = UUID('bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbb2')
CONTACT_A = UUID('aaaaaaaa-0001-4000-8000-000000000001')
CONTACT_B = UUID('bbbbbbbb-0001-4000-8000-000000000001')
CHANNEL_A = UUID('aaaaaaaa-0002-4000-8000-000000000001')
CHANNEL_B = UUID('bbbbbbbb-0002-4000-8000-000000000001')
CONVERSATION_A = UUID('aaaaaaaa-0003-4000-8000-000000000001')
CONVERSATION_B = UUID('bbbbbbbb-0003-4000-8000-000000000001')
MESSAGE_A = UUID('aaaaaaaa-0004-4000-8000-000000000001')
MESSAGE_B = UUID('bbbbbbbb-0004-4000-8000-000000000001')
STATUS_A = UUID('aaaaaaaa-0005-4000-8000-000000000001')
STATUS_B = UUID('bbbbbbbb-0005-4000-8000-000000000001')
RESOURCE_A = UUID('aaaaaaaa-0006-4000-8000-000000000001')
RESOURCE_B = UUID('bbbbbbbb-0006-4000-8000-000000000001')
SERVICE_REQUEST_A = UUID('aaaaaaaa-0007-4000-8000-000000000001')
SERVICE_REQUEST_B = UUID('bbbbbbbb-0007-4000-8000-000000000001')
QUOTE_A = UUID('aaaaaaaa-0008-4000-8000-000000000001')
QUOTE_B = UUID('bbbbbbbb-0008-4000-8000-000000000001')
APPOINTMENT_A = UUID('aaaaaaaa-0009-4000-8000-000000000001')
APPOINTMENT_B = UUID('bbbbbbbb-0009-4000-8000-000000000001')
DOCUMENT_A = UUID('aaaaaaaa-0010-4000-8000-000000000001')
DOCUMENT_B = UUID('bbbbbbbb-0010-4000-8000-000000000001')
CHUNK_A = UUID('aaaaaaaa-0011-4000-8000-000000000001')
CHUNK_B = UUID('bbbbbbbb-0011-4000-8000-000000000001')
HANDOFF_A = UUID('aaaaaaaa-0012-4000-8000-000000000001')
HANDOFF_B = UUID('bbbbbbbb-0012-4000-8000-000000000001')
WEBHOOK_A = UUID('aaaaaaaa-0013-4000-8000-000000000001')
WEBHOOK_B = UUID('bbbbbbbb-0013-4000-8000-000000000001')
EVENT_A = UUID('aaaaaaaa-0014-4000-8000-000000000001')
EVENT_B = UUID('bbbbbbbb-0014-4000-8000-000000000001')

TENANT_TABLES = [
    'tenant_channels',
    'contacts',
    'conversations',
    'messages',
    'message_status_events',
    'resources',
    'service_requests',
    'quotes',
    'appointments',
    'knowledge_documents',
    'knowledge_chunks',
    'handoffs',
    'webhook_events_raw',
    'domain_events',
    'audit_logs',
]


def _database_url() -> str | None:
    return os.getenv('TEST_DATABASE_URL') or os.getenv('DATABASE_URL')


def _requires_database() -> str:
    database_url = _database_url()
    if os.getenv('RUN_RLS_E2E') != '1':
        pytest.skip('set RUN_RLS_E2E=1 to run the PostgreSQL RLS end-to-end suite')
    if not database_url:
        pytest.skip('set TEST_DATABASE_URL or DATABASE_URL for the PostgreSQL RLS suite')
    return database_url


async def _set_context(conn: asyncpg.Connection, tenant_id: UUID | None, support_mode: bool) -> None:
    await conn.execute("select set_config('app.tenant_id', $1, false)", str(tenant_id) if tenant_id else '')
    await conn.execute(
        "select set_config('app.support_mode', $1, false)", 'true' if support_mode else 'false'
    )


async def _assert_app_role_uses_rls(conn: asyncpg.Connection) -> None:
    is_owner = await conn.fetchval(
        """
        select current_user = pg_get_userbyid(c.relowner)
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'app' and c.relname = 'contacts'
        """
    )
    bypasses_rls = await conn.fetchval("select rolsuper or rolbypassrls from pg_roles where rolname = current_user")
    if is_owner or bypasses_rls:
        pytest.skip('RLS E2E must run with the non-owner application role, e.g. copiloto_app')


async def _cleanup(conn: asyncpg.Connection) -> None:
    await _set_context(conn, None, True)
    tenant_ids = (TENANT_A, TENANT_B)
    for table in [
        'message_status_events',
        'domain_events',
        'webhook_events_raw',
        'handoffs',
        'appointments',
        'quotes',
        'service_requests',
        'knowledge_chunks',
        'knowledge_documents',
        'messages',
        'conversations',
        'resources',
        'contacts',
        'tenant_channels',
        'tenant_settings',
        'audit_logs',
        'tenants',
    ]:
        column = 'id' if table == 'tenants' else 'tenant_id'
        await conn.execute(f'delete from app.{table} where {column} = any($1::uuid[])', tenant_ids)


async def _seed_two_tenants(conn: asyncpg.Connection) -> None:
    await _cleanup(conn)
    await conn.executemany(
        """
        insert into app.tenants (id, slug, legal_name, display_name, vertical_code, status)
        values ($1, $2, $3, $4, 'beauty', 'active')
        """,
        [
            (TENANT_A, 'rls-e2e-a', 'RLS Tenant A SAS', 'RLS Tenant A'),
            (TENANT_B, 'rls-e2e-b', 'RLS Tenant B SAS', 'RLS Tenant B'),
        ],
    )
    await conn.executemany('insert into app.tenant_settings (tenant_id) values ($1)', [(TENANT_A,), (TENANT_B,)])
    await conn.executemany(
        """
        insert into app.tenant_channels (id, tenant_id, provider, phone_number_id, token_ref, account_mode, status)
        values ($1, $2, 'whatsapp_cloud_api', $3, $4, 'mock', 'active')
        """,
        [
            (CHANNEL_A, TENANT_A, 'rls-phone-a', f'secrets/tenants/{TENANT_A}/meta_access_token'),
            (CHANNEL_B, TENANT_B, 'rls-phone-b', f'secrets/tenants/{TENANT_B}/meta_access_token'),
        ],
    )
    await conn.executemany(
        """
        insert into app.contacts (id, tenant_id, wa_id, phone_e164, phone_hash, display_name)
        values ($1, $2, $3, $4, digest($4, 'sha256'), $5)
        """,
        [
            (CONTACT_A, TENANT_A, '570000000001', '+570000000001', 'Contacto A'),
            (CONTACT_B, TENANT_B, '570000000002', '+570000000002', 'Contacto B'),
        ],
    )
    await conn.executemany(
        """
        insert into app.resources (id, tenant_id, vertical_code, resource_type, code, name)
        values ($1, $2, 'beauty', 'chair', $3, $4)
        """,
        [(RESOURCE_A, TENANT_A, 'chair-a', 'Silla A'), (RESOURCE_B, TENANT_B, 'chair-b', 'Silla B')],
    )
    await conn.executemany(
        """
        insert into app.conversations (id, tenant_id, contact_id, channel_id, status)
        values ($1, $2, $3, $4, 'open')
        """,
        [(CONVERSATION_A, TENANT_A, CONTACT_A, CHANNEL_A), (CONVERSATION_B, TENANT_B, CONTACT_B, CHANNEL_B)],
    )
    await conn.executemany(
        """
        insert into app.messages (id, tenant_id, conversation_id, external_message_id, direction, sender_actor_type, body_text)
        values ($1, $2, $3, $4, 'inbound', 'contact', $5)
        """,
        [(MESSAGE_A, TENANT_A, CONVERSATION_A, 'rls-msg-a', 'Hola A'), (MESSAGE_B, TENANT_B, CONVERSATION_B, 'rls-msg-b', 'Hola B')],
    )
    await conn.executemany(
        """
        insert into app.message_status_events (id, tenant_id, message_id, external_message_id, status, raw_payload)
        values ($1, $2, $3, $4, 'delivered', '{}'::jsonb)
        """,
        [(STATUS_A, TENANT_A, MESSAGE_A, 'rls-msg-a'), (STATUS_B, TENANT_B, MESSAGE_B, 'rls-msg-b')],
    )
    await conn.executemany(
        """
        insert into app.service_requests (id, tenant_id, contact_id, conversation_id, vertical_code, service_type)
        values ($1, $2, $3, $4, 'beauty', 'manicure')
        """,
        [(SERVICE_REQUEST_A, TENANT_A, CONTACT_A, CONVERSATION_A), (SERVICE_REQUEST_B, TENANT_B, CONTACT_B, CONVERSATION_B)],
    )
    await conn.executemany(
        """
        insert into app.quotes (id, tenant_id, service_request_id, grand_total)
        values ($1, $2, $3, 10000)
        """,
        [(QUOTE_A, TENANT_A, SERVICE_REQUEST_A), (QUOTE_B, TENANT_B, SERVICE_REQUEST_B)],
    )
    await conn.executemany(
        """
        insert into app.appointments (id, tenant_id, contact_id, conversation_id, service_request_id, resource_id, service_code, starts_at, ends_at)
        values ($1, $2, $3, $4, $5, $6, 'manicure', $7::timestamptz, $8::timestamptz)
        """,
        [
            (APPOINTMENT_A, TENANT_A, CONTACT_A, CONVERSATION_A, SERVICE_REQUEST_A, RESOURCE_A, '2030-01-01T10:00:00Z', '2030-01-01T11:00:00Z'),
            (APPOINTMENT_B, TENANT_B, CONTACT_B, CONVERSATION_B, SERVICE_REQUEST_B, RESOURCE_B, '2030-01-02T10:00:00Z', '2030-01-02T11:00:00Z'),
        ],
    )
    await conn.executemany(
        """
        insert into app.knowledge_documents (id, tenant_id, source_type, title, status, content)
        values ($1, $2, 'manual', $3, 'active', $4)
        """,
        [(DOCUMENT_A, TENANT_A, 'Doc A', 'Precio A'), (DOCUMENT_B, TENANT_B, 'Doc B', 'Precio B')],
    )
    await conn.executemany(
        """
        insert into app.knowledge_chunks (id, tenant_id, document_id, chunk_index, chunk_text, token_count)
        values ($1, $2, $3, 0, $4, 2)
        """,
        [(CHUNK_A, TENANT_A, DOCUMENT_A, 'chunk A'), (CHUNK_B, TENANT_B, DOCUMENT_B, 'chunk B')],
    )
    await conn.executemany(
        """
        insert into app.handoffs (id, tenant_id, conversation_id, reason)
        values ($1, $2, $3, 'rls-e2e')
        """,
        [(HANDOFF_A, TENANT_A, CONVERSATION_A), (HANDOFF_B, TENANT_B, CONVERSATION_B)],
    )
    await conn.executemany(
        """
        insert into app.webhook_events_raw (id, tenant_id, provider, event_type, payload, payload_sha256)
        values ($1, $2, 'whatsapp_cloud_api', 'message', '{}'::jsonb, $3)
        """,
        [(WEBHOOK_A, TENANT_A, 'rls-webhook-a'), (WEBHOOK_B, TENANT_B, 'rls-webhook-b')],
    )
    await conn.executemany(
        """
        insert into app.domain_events (id, tenant_id, aggregate_type, aggregate_id, event_name, idempotency_key)
        values ($1, $2, 'message', $3, 'message.queued', $4)
        """,
        [(EVENT_A, TENANT_A, MESSAGE_A, 'rls-event-a'), (EVENT_B, TENANT_B, MESSAGE_B, 'rls-event-b')],
    )
    await conn.executemany(
        """
        insert into app.audit_logs (tenant_id, actor_type, action, entity_type, entity_id)
        values ($1, 'system', 'rls.seeded', 'tenant', $2)
        """,
        [(TENANT_A, str(TENANT_A)), (TENANT_B, str(TENANT_B))],
    )


async def _assert_count(conn: asyncpg.Connection, table: str, expected: int) -> None:
    count = await conn.fetchval(f'select count(*) from app.{table}')
    assert count == expected, table


async def _assert_rejected(statement, *args) -> None:
    with pytest.raises((asyncpg.CheckViolationError, asyncpg.ForeignKeyViolationError, asyncpg.InsufficientPrivilegeError)):
        await statement(*args)


def test_postgres_rls_isolates_two_real_tenants_and_blocks_cross_tenant_writes():
    async def run_test():
        conn = await asyncpg.connect(_requires_database())
        try:
            await _assert_app_role_uses_rls(conn)
            await _seed_two_tenants(conn)

            await _set_context(conn, TENANT_A, False)
            for table in TENANT_TABLES:
                await _assert_count(conn, table, 1)
            assert await conn.fetchval('select display_name from app.contacts') == 'Contacto A'

            await _assert_rejected(
                conn.execute,
                """
                insert into app.contacts (tenant_id, wa_id, phone_e164, phone_hash)
                values ($1, 'blocked-wa', '+579999999999', digest('+579999999999', 'sha256'))
                """,
                TENANT_B,
            )
            await _assert_rejected(
                conn.execute,
                "insert into app.conversations (tenant_id, contact_id, channel_id) values ($1, $2, $3)",
                TENANT_A,
                CONTACT_B,
                CHANNEL_A,
            )
            await _assert_rejected(
                conn.execute,
                "insert into app.messages (tenant_id, conversation_id, direction, sender_actor_type) values ($1, $2, 'inbound', 'contact')",
                TENANT_A,
                CONVERSATION_B,
            )
            await _assert_rejected(
                conn.execute,
                "insert into app.message_status_events (tenant_id, message_id, external_message_id, status, raw_payload) values ($1, $2, 'blocked', 'sent', '{}'::jsonb)",
                TENANT_A,
                MESSAGE_B,
            )
            await _assert_rejected(
                conn.execute,
                "insert into app.service_requests (tenant_id, contact_id, vertical_code, service_type) values ($1, $2, 'beauty', 'manicure')",
                TENANT_A,
                CONTACT_B,
            )
            await _assert_rejected(
                conn.execute,
                "insert into app.quotes (tenant_id, service_request_id) values ($1, $2)",
                TENANT_A,
                SERVICE_REQUEST_B,
            )
            await _assert_rejected(
                conn.execute,
                """
                insert into app.appointments (tenant_id, contact_id, resource_id, service_code, starts_at, ends_at)
                values ($1, $2, $3, 'manicure', '2030-01-03T10:00:00Z', '2030-01-03T11:00:00Z')
                """,
                TENANT_A,
                CONTACT_B,
                RESOURCE_A,
            )
            await _assert_rejected(
                conn.execute,
                "insert into app.knowledge_chunks (tenant_id, document_id, chunk_index, chunk_text) values ($1, $2, 99, 'blocked')",
                TENANT_A,
                DOCUMENT_B,
            )
            await _assert_rejected(
                conn.execute,
                "insert into app.handoffs (tenant_id, conversation_id, reason) values ($1, $2, 'blocked')",
                TENANT_A,
                CONVERSATION_B,
            )

            await _set_context(conn, TENANT_B, False)
            for table in TENANT_TABLES:
                await _assert_count(conn, table, 1)
            assert await conn.fetchval('select display_name from app.contacts') == 'Contacto B'

            await _set_context(conn, None, False)
            for table in TENANT_TABLES:
                await _assert_count(conn, table, 0)

            await _set_context(conn, None, True)
            for table in TENANT_TABLES:
                await _assert_count(conn, table, 2)
        finally:
            await _cleanup(conn)
            await conn.close()

    asyncio.run(run_test())
