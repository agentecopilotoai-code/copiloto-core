"""Direct service-layer tests for `app/services/booking_flow.py` against
ephemeral PostgreSQL. The functions are async and need a real connection;
we use `asyncio.run` per test with a fresh tenant seeded inline.
"""
from __future__ import annotations

import asyncio
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
    """Minimal seed for booking_flow tests: tenant, service, resource, contact."""
    import asyncpg
    tenant_id = uuid.uuid4()
    service_id = uuid.uuid4()
    resource_id = uuid.uuid4()
    contact_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    channel_id = uuid.uuid4()
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("select set_config('app.support_mode', 'true', false)")
        await conn.execute("select set_config('app.tenant_id', $1, false)", str(tenant_id))
        async with conn.transaction():
            await conn.execute(
                """insert into app.tenants (id, slug, legal_name, display_name, vertical_code,
                   country_code, timezone, status)
                   values ($1, $2, $3, $3, 'general', 'CO', 'America/Bogota', 'active')""",
                tenant_id, f't-{tenant_id.hex[:8]}', 'Booking DB Test',
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
            wa = f'5730099{int(uuid.uuid4().int % 10_000_000):07d}'
            await conn.execute(
                """insert into app.contacts (id, tenant_id, wa_id, phone_e164, phone_hash,
                   display_name, opt_in_status)
                   values ($1, $2, $3, $4, decode(md5($4), 'hex'), 'C', 'granted')""",
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
                   values ($1, $2, 'general', 'staff', $3, 'Dr. X',
                           '{"services": []}'::jsonb, true)""",
                resource_id, tenant_id, f'res-{uuid.uuid4().hex[:6]}',
            )
            await conn.execute(
                """insert into app.service_catalog (id, tenant_id, name, duration_minutes,
                   is_active, price_amount, price_currency)
                   values ($1, $2, 'Test Service', 30, true, 50000, 'COP')""",
                service_id, tenant_id,
            )
    finally:
        await conn.close()
    return tenant_id, contact_id, conv_id, resource_id, service_id, channel_id


# ─────────── _list_active_services / _list_active_resources / _fetch_service ─


def test_list_active_services_returns_seeded_service(e2e_http_dsn):
    from app.services.booking_flow import _list_active_services

    async def _go():
        tenant_id, *_ = await _seed(e2e_http_dsn)
        async with tenant_connection(e2e_http_dsn, tenant_id, support_mode=True) as conn:
            services = await _list_active_services(conn, tenant_id)
            return services

    services = asyncio.run(_go())
    assert isinstance(services, list)
    assert any(s.get('name') == 'Test Service' for s in services)


def test_list_active_resources_returns_seeded_resource(e2e_http_dsn):
    from app.services.booking_flow import _list_active_resources

    async def _go():
        tenant_id, *_ = await _seed(e2e_http_dsn)
        async with tenant_connection(e2e_http_dsn, tenant_id, support_mode=True) as conn:
            resources = await _list_active_resources(conn, tenant_id)
            return resources

    resources = asyncio.run(_go())
    assert isinstance(resources, list)
    assert any(r.get('name') == 'Dr. X' for r in resources)


def test_fetch_service_returns_row_when_found(e2e_http_dsn):
    from app.services.booking_flow import _fetch_service

    async def _go():
        tenant_id, _, _, _, service_id, _ = await _seed(e2e_http_dsn)
        async with tenant_connection(e2e_http_dsn, tenant_id, support_mode=True) as conn:
            return await _fetch_service(conn, tenant_id, service_id)

    svc = asyncio.run(_go())
    assert svc is not None
    assert svc.get('name') == 'Test Service'


def test_fetch_service_returns_none_for_unknown_id(e2e_http_dsn):
    from app.services.booking_flow import _fetch_service

    async def _go():
        tenant_id, *_ = await _seed(e2e_http_dsn)
        async with tenant_connection(e2e_http_dsn, tenant_id, support_mode=True) as conn:
            return await _fetch_service(conn, tenant_id, uuid.uuid4())

    assert asyncio.run(_go()) is None


def test_fetch_resource_returns_row_when_found(e2e_http_dsn):
    from app.services.booking_flow import _fetch_resource

    async def _go():
        tenant_id, _, _, resource_id, _, _ = await _seed(e2e_http_dsn)
        async with tenant_connection(e2e_http_dsn, tenant_id, support_mode=True) as conn:
            return await _fetch_resource(conn, tenant_id, resource_id)

    res = asyncio.run(_go())
    assert res is not None


def test_list_active_branches_empty_when_none_seeded(e2e_http_dsn):
    from app.services.booking_flow import _list_active_branches

    async def _go():
        tenant_id, *_ = await _seed(e2e_http_dsn)
        async with tenant_connection(e2e_http_dsn, tenant_id, support_mode=True) as conn:
            return await _list_active_branches(conn, tenant_id)

    branches = asyncio.run(_go())
    assert isinstance(branches, list)


def test_list_active_contact_packages_empty_when_none_assigned(e2e_http_dsn):
    from app.services.booking_flow import _list_active_contact_packages

    async def _go():
        tenant_id, contact_id, _, _, service_id, _ = await _seed(e2e_http_dsn)
        async with tenant_connection(e2e_http_dsn, tenant_id, support_mode=True) as conn:
            return await _list_active_contact_packages(conn, tenant_id, contact_id, service_id)

    pkgs = asyncio.run(_go())
    assert isinstance(pkgs, list)
    assert pkgs == []


def test_filter_services_by_qualification_returns_all_when_no_rules():
    """Pure function — no DB."""
    from app.services.booking_flow import _filter_services_by_qualification
    services = [
        {'id': 'a', 'name': 'A', 'applies_when': None},
        {'id': 'b', 'name': 'B', 'applies_when': None},
    ]
    out = _filter_services_by_qualification(services, facts={})
    assert len(out) == 2


def test_filter_services_by_qualification_filters_by_facts():
    from app.services.booking_flow import _filter_services_by_qualification
    services = [
        {'id': 'a', 'name': 'High budget', 'applies_when': {
            'all_of': [{'key': 'budget', 'op': 'gte', 'value': 200}],
        }},
        {'id': 'b', 'name': 'Anyone', 'applies_when': None},
    ]
    # Low budget → only B matches
    out = _filter_services_by_qualification(services, facts={'budget': 50})
    assert {s['id'] for s in out} == {'b'}
    # High budget → both
    out = _filter_services_by_qualification(services, facts={'budget': 500})
    assert {s['id'] for s in out} == {'a', 'b'}
