"""TASK-0063: E2E test fixtures with ephemeral PostgreSQL.

These fixtures power the journey-level suite in ``tests/test_journey_e2e.py``.
They exercise the real schema (``infra/postgres/01-schema.sql``) against a live
PostgreSQL — either an ad-hoc instance provisioned by the test harness, or one
already running locally / in CI.

Activation:
    * ``RUN_E2E=1`` opts in (the suite is skipped by default).
    * ``TEST_DATABASE_URL`` (or ``DATABASE_URL``) must point at a writable
      PostgreSQL with the pgvector + btree_gist + citext extensions.
    * ``E2E_APPLY_SCHEMA=1`` re-applies the schema once per session (it drops
      the ``app`` schema first). Skip it when the DB is already prepared.

Each test that calls :func:`tenant_factory` gets a brand-new tenant; tenants are
removed via cascade delete on fixture teardown so suites stay independent. The
project does not use ``pytest-asyncio`` — fixtures are plain ``pytest``
fixtures and async helpers are entered through ``asyncio.run`` from each test.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Callable, TYPE_CHECKING

import pytest

if TYPE_CHECKING:  # pragma: no cover - import only for type checkers
    import asyncpg


REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_FILE = REPO_ROOT / 'infra' / 'postgres' / '01-schema.sql'


def e2e_enabled() -> bool:
    """Return True iff the E2E suite is opted in for this run."""
    return os.getenv('RUN_E2E') == '1'


def _database_url() -> str | None:
    return os.getenv('TEST_DATABASE_URL') or os.getenv('DATABASE_URL')


def _skip_unless_ready() -> str:
    if not e2e_enabled():
        pytest.skip('set RUN_E2E=1 to opt into the journey E2E suite')
    url = _database_url()
    if not url:
        pytest.skip('set TEST_DATABASE_URL (or DATABASE_URL) for the E2E suite')
    return url


async def _apply_schema(url: str) -> None:
    """Drop and re-create the ``app`` schema from the canonical SQL file.

    The canonical schema ends with ``GRANT ... TO copiloto_app`` (the role the
    application uses to satisfy RLS). In a production-like deploy that role is
    created by ``00-init-roles.sh`` before ``01-schema.sql`` runs. For the E2E
    job we provision the role here so the suite is self-contained.
    """
    import asyncpg

    if not SCHEMA_FILE.is_file():
        raise RuntimeError(f'schema file missing: {SCHEMA_FILE}')
    sql = SCHEMA_FILE.read_text(encoding='utf-8')
    conn = await asyncpg.connect(url)
    try:
        await conn.execute(
            """
            do $$
            begin
              if not exists (select 1 from pg_roles where rolname = 'copiloto_app') then
                create role copiloto_app login password 'copiloto_app_e2e';
              end if;
            end
            $$;
            """
        )
        await conn.execute('drop schema if exists app cascade')
        await conn.execute(sql)
    finally:
        await conn.close()


def run_async(coro):
    """Helper used by tests to drive an async coroutine to completion.

    Tests in this suite are plain sync functions; they call ``run_async`` so we
    don't need a pytest-asyncio dependency in ``pyproject.toml``.
    """
    return asyncio.run(coro)


@pytest.fixture(scope='session')
def e2e_database_url() -> str:
    return _skip_unless_ready()


@pytest.fixture(scope='session')
def e2e_session(e2e_database_url: str) -> str:
    """Session fixture that prepares the schema once (when opted in) and
    returns the DSN. Tests that need a tenant request ``tenant_factory`` which
    transitively requests this fixture."""
    if os.getenv('E2E_APPLY_SCHEMA') == '1':
        asyncio.run(_apply_schema(e2e_database_url))
    return e2e_database_url


class TenantHandle:
    """Bundles the IDs that scenarios need to drive a tenant end-to-end."""

    __slots__ = (
        'tenant_id',
        'channel_id',
        'contact_id',
        'conversation_id',
        'resource_id',
        'service_id',
        'service_code',
        'wa_id',
    )

    def __init__(
        self,
        *,
        tenant_id: uuid.UUID,
        channel_id: uuid.UUID,
        contact_id: uuid.UUID,
        conversation_id: uuid.UUID,
        resource_id: uuid.UUID,
        service_id: uuid.UUID,
        service_code: str,
        wa_id: str,
    ) -> None:
        self.tenant_id = tenant_id
        self.channel_id = channel_id
        self.contact_id = contact_id
        self.conversation_id = conversation_id
        self.resource_id = resource_id
        self.service_id = service_id
        self.service_code = service_code
        self.wa_id = wa_id


async def _seed_tenant(
    url: str,
    *,
    label: str,
    opt_in_status: str = 'unknown',
) -> TenantHandle:
    """Create a self-contained tenant with one channel, contact, conversation,
    resource and service. Returns a :class:`TenantHandle` with the IDs."""
    tenant_id = uuid.uuid4()
    channel_id = uuid.uuid4()
    contact_id = uuid.uuid4()
    conversation_id = uuid.uuid4()
    resource_id = uuid.uuid4()
    service_id = uuid.uuid4()
    service_code = f'svc-{label[:6]}'
    wa_id = f'5730000{int(uuid.uuid4().int % 10_000_000):07d}'

    import asyncpg

    conn = await asyncpg.connect(url)
    try:
        await conn.execute("select set_config('app.support_mode', 'true', false)")
        await conn.execute("select set_config('app.tenant_id', $1, false)", str(tenant_id))

        async with conn.transaction():
            await conn.execute(
                """
                insert into app.tenants
                  (id, slug, legal_name, display_name, vertical_code,
                   country_code, timezone, status)
                values ($1, $2, $3, $3, 'general', 'CO', 'America/Bogota', 'active')
                """,
                tenant_id,
                f'tenant-{label}-{tenant_id.hex[:8]}',
                f'E2E {label}',
            )
            await conn.execute(
                """
                insert into app.tenant_settings (tenant_id, escalation_policy)
                values ($1, '{"triggers": {"keywords": ["humano", "agente"], "after_bot_turns": 5}}'::jsonb)
                """,
                tenant_id,
            )
            await conn.execute(
                """
                insert into app.tenant_channels
                  (id, tenant_id, provider, phone_number_id, token_ref, account_mode, status)
                values ($1, $2, 'whatsapp_cloud_api', $3, 'whatsapp_token_ref', 'mock', 'active')
                """,
                channel_id,
                tenant_id,
                f'pn-{tenant_id.hex[:8]}',
            )
            phone_e164 = f'+{wa_id}'
            await conn.execute(
                """
                insert into app.contacts
                  (id, tenant_id, wa_id, phone_e164, phone_hash, display_name, opt_in_status)
                values ($1, $2, $3, $4, decode(md5($4), 'hex'), $5, $6)
                """,
                contact_id,
                tenant_id,
                wa_id,
                phone_e164,
                f'Cliente {label}',
                opt_in_status,
            )
            await conn.execute(
                """
                insert into app.conversations
                  (id, tenant_id, contact_id, channel_id, status, opened_by)
                values ($1, $2, $3, $4, 'open', 'user')
                """,
                conversation_id,
                tenant_id,
                contact_id,
                channel_id,
            )
            await conn.execute(
                """
                insert into app.resources
                  (id, tenant_id, vertical_code, resource_type, code, name,
                   capabilities, is_active)
                values ($1, $2, 'general', 'staff', 'res-' || $3,
                        'Profesional ' || $3, '{"services": []}'::jsonb, true)
                """,
                resource_id,
                tenant_id,
                label,
            )
            # `service_catalog` doesn't have a `code` column — appointments
            # carry `service_code` as a free-form text. We store the label-derived
            # code on the appointments table side; here we only need a service row.
            await conn.execute(
                """
                insert into app.service_catalog
                  (id, tenant_id, name, duration_minutes, is_active,
                   price_amount, price_currency)
                values ($1, $2, 'Servicio ' || $3, 30, true, 50000, 'COP')
                """,
                service_id,
                tenant_id,
                label,
            )
    finally:
        await conn.close()

    return TenantHandle(
        tenant_id=tenant_id,
        channel_id=channel_id,
        contact_id=contact_id,
        conversation_id=conversation_id,
        resource_id=resource_id,
        service_id=service_id,
        service_code=service_code,
        wa_id=wa_id,
    )


async def _delete_tenant(url: str, tenant_id: uuid.UUID) -> None:
    """Best-effort cleanup. ``on delete cascade`` from ``tenants`` removes
    everything created for this scenario."""
    import asyncpg

    conn = await asyncpg.connect(url)
    try:
        await conn.execute("select set_config('app.support_mode', 'true', false)")
        await conn.execute('delete from app.tenants where id=$1', tenant_id)
    finally:
        await conn.close()


@pytest.fixture
def tenant_factory(e2e_session: str) -> Callable[..., Any]:
    """Per-test factory: each call returns a brand-new tenant with full seed.

    Tenants are cleaned up at fixture teardown via cascade delete.
    """
    created: list[uuid.UUID] = []

    async def _factory(*, label: str = 'journey', opt_in_status: str = 'unknown') -> TenantHandle:
        handle = await _seed_tenant(e2e_session, label=label, opt_in_status=opt_in_status)
        created.append(handle.tenant_id)
        return handle

    yield _factory

    async def _cleanup() -> None:
        for tid in created:
            try:
                await _delete_tenant(e2e_session, tid)
            except Exception:
                pass

    if created:
        asyncio.run(_cleanup())


@asynccontextmanager
async def tenant_connection(
    url: str, tenant_id: uuid.UUID, *, support_mode: bool = False
) -> AsyncIterator['asyncpg.Connection']:
    """Yield an ``asyncpg`` connection bound to ``tenant_id`` (RLS context).

    Lives outside the fixture so test code can ``async with`` it inside an
    ``asyncio.run`` block without coupling to a fixture.
    """
    import asyncpg

    conn = await asyncpg.connect(url)
    try:
        await conn.execute(
            "select set_config('app.tenant_id', $1, false)", str(tenant_id)
        )
        await conn.execute(
            "select set_config('app.support_mode', $1, false)",
            'true' if support_mode else 'false',
        )
        yield conn
    finally:
        await conn.close()
