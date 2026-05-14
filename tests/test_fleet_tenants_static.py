"""Static tests for UI-006.1: GET /v1/tenants (Fleet · Tenants).

Repository-source assertions confirming the new fleet-list endpoint:

* It is wired on ``platform_admin_router`` (which carries
  ``authenticate_request`` + ``require_platform_owner`` +
  ``require_mfa_for_privileged`` at the router level).
* The handler enforces the documented filters (``status``, ``country``,
  ``vertical``, ``search``) with validation.
* Soft-deleted tenants are excluded.
* The handler never relaxes the router-level security dependencies.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROUTES_FILE = Path('app/api/v1/routes.py')


@pytest.fixture(scope='module')
def routes_source() -> str:
    return ROUTES_FILE.read_text()


# ── Endpoint lives on platform_admin_router ──────────────────────────────────


def test_list_tenants_fleet_endpoint_exists(routes_source: str) -> None:
    assert "@platform_admin_router.get('/tenants')" in routes_source, (
        'GET /v1/tenants must be exposed on platform_admin_router (UI-006.1)'
    )


def test_list_tenants_fleet_not_on_tenant_admin_router(routes_source: str) -> None:
    """Defense in depth: never let a tenant_admin reach the fleet list."""
    assert "@tenant_admin_router.get('/tenants')" not in routes_source
    assert "@tenant_user_router.get('/tenants')" not in routes_source


def test_platform_admin_router_block_keeps_security_dependencies(routes_source: str) -> None:
    """``platform_admin_router`` must still attach the three security
    dependencies the rest of UI-006 will rely on. Regression guard for any
    future edit that accidentally relaxes them."""
    pattern = r"platform_admin_router\s*=\s*APIRouter\((.*?)\)\n"
    match = re.search(pattern, routes_source, re.DOTALL)
    assert match, 'platform_admin_router definition not found'
    block = match.group(1)
    for dependency in (
        'authenticate_request',
        'require_platform_owner',
        'require_mfa_for_privileged',
    ):
        assert dependency in block, f'platform_admin_router lost {dependency}'


# ── Handler body invariants ──────────────────────────────────────────────────


def _handler_block(source: str, name: str) -> str:
    start = source.index(f'async def {name}(')
    end = source.index('\n\n\n', start)
    return source[start:end]


def test_handler_excludes_soft_deleted_tenants(routes_source: str) -> None:
    handler = _handler_block(routes_source, 'list_tenants_fleet')
    assert 't.deleted_at is null' in handler


def test_handler_supports_documented_filters(routes_source: str) -> None:
    handler = _handler_block(routes_source, 'list_tenants_fleet')
    for filter_kw in ('status', 'country', 'vertical', 'search'):
        assert filter_kw in handler, f'filter {filter_kw!r} missing from handler'


def test_handler_validates_status_against_lifecycle_pattern(routes_source: str) -> None:
    """Only the four lifecycle values from the schema CHECK constraint are
    accepted as filters — otherwise we return 422 instead of leaking via SQL."""
    handler = _handler_block(routes_source, 'list_tenants_fleet')
    assert '_FLEET_LIST_STATUS_PATTERN' in handler
    # The pattern is module-level and exactly matches the schema constraint.
    assert "re.compile(r'^(trial|active|suspended|churned)$')" in routes_source
    assert 'invalid status filter' in handler


def test_handler_validates_country_against_supported_locale(routes_source: str) -> None:
    """``SUPPORTED_COUNTRIES`` is the single source of truth (TASK-0073). The
    handler must consult it instead of hardcoding a list."""
    handler = _handler_block(routes_source, 'list_tenants_fleet')
    assert 'SUPPORTED_COUNTRIES' in handler
    assert 'unsupported country code' in handler


def test_handler_does_not_override_security_dependencies(routes_source: str) -> None:
    """The handler signature must not introduce its own ``dependencies=[]``
    override (which would silently bypass router-level guards)."""
    decorator_line_idx = routes_source.index("@platform_admin_router.get('/tenants')")
    handler_start = routes_source.index('async def list_tenants_fleet(', decorator_line_idx)
    decorator_block = routes_source[decorator_line_idx:handler_start]
    assert 'dependencies' not in decorator_block, (
        'Handler decorator must not declare a `dependencies=` override — the '
        'router-level platform-owner + MFA dependencies are the contract.'
    )


def test_handler_returns_paginated_envelope(routes_source: str) -> None:
    handler = _handler_block(routes_source, 'list_tenants_fleet')
    for key in ("'items'", "'total'", "'limit'", "'offset'"):
        assert key in handler, f'response envelope missing {key}'


# ── Schema sanity: ``SUPPORTED_COUNTRIES`` available at import time ──────────


def test_supported_countries_imported_at_module_top(routes_source: str) -> None:
    assert 'from app.services.locale import SUPPORTED_COUNTRIES' in routes_source
