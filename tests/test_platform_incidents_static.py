"""Static + functional tests for UI-006.4: GET /v1/platform/incidents.

Covers:

* The endpoint is wired on ``platform_admin_router`` (which carries
  ``authenticate_request`` + ``require_platform_owner`` +
  ``require_mfa_for_privileged`` at the router level) and never on a
  tenant-scoped router.
* The handler enables ``app.support_mode`` transaction-locally for the
  cross-tenant read of ``app.operator_alerts`` (the documented operator path
  for system-level NULL-tenant alerts — TASK-0064).
* ``platform_incidents`` derives severity / runbook / open-state per alert kind
  and summarises KPI counters.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROUTES_FILE = Path('app/api/v1/routes.py')


@pytest.fixture(scope='module')
def routes_source() -> str:
    return ROUTES_FILE.read_text()


# ── Endpoint lives on platform_admin_router ──────────────────────────────────


def test_incidents_endpoint_on_platform_admin_router(routes_source: str) -> None:
    assert "@platform_admin_router.get('/platform/incidents')" in routes_source, (
        'GET /v1/platform/incidents must be exposed on platform_admin_router (UI-006.4)'
    )


def test_incidents_not_on_tenant_routers(routes_source: str) -> None:
    """Defense in depth: never let a tenant-scoped role reach the fleet feed."""
    for router in ('tenant_admin_router', 'tenant_ops_router', 'tenant_user_router'):
        assert f"@{router}.get('/platform/incidents')" not in routes_source


def test_incidents_handler_uses_support_mode_and_service(routes_source: str) -> None:
    handler_idx = routes_source.index("async def platform_incidents_feed(")
    handler = routes_source[handler_idx:handler_idx + 6000]
    assert "set_config('app.support_mode', 'true', true)" in handler
    assert 'platform_incidents.severity_for_kind(' in handler
    assert 'platform_incidents.summarize_incidents(' in handler


# ── severity / runbook / open-state derivation ───────────────────────────────


def test_severity_for_kind_maps_each_kind() -> None:
    from app.services import platform_incidents

    assert platform_incidents.severity_for_kind('backup_failure') == 'P1'
    assert platform_incidents.severity_for_kind('outbound_dlq_threshold') == 'P2'
    assert platform_incidents.severity_for_kind('complaint') == 'P2'
    assert platform_incidents.severity_for_kind('negative_feedback') == 'P3'
    # Unknown kinds fall back to the lowest severity rather than raising.
    assert platform_incidents.severity_for_kind('something_new') == 'P3'


def test_runbook_and_open_state() -> None:
    from app.services import platform_incidents

    assert platform_incidents.runbook_for_kind('outbound_dlq_threshold') == 'rate-limit-meta-hit.md'
    assert platform_incidents.runbook_for_kind('complaint') is None
    assert platform_incidents.is_open('pending') is True
    assert platform_incidents.is_open('failed') is True
    assert platform_incidents.is_open('sent') is False


# ── summarize_incidents ──────────────────────────────────────────────────────


def test_summarize_incidents_aggregates_counters() -> None:
    from app.services import platform_incidents

    incidents = [
        {'severity': 'P1', 'status': 'failed', 'is_open': True, 'tenant_id': None},
        {'severity': 'P2', 'status': 'pending', 'is_open': True, 'tenant_id': 't1'},
        {'severity': 'P3', 'status': 'sent', 'is_open': False, 'tenant_id': 't1'},
        {'severity': 'P2', 'status': 'sent', 'is_open': False, 'tenant_id': 't2'},
    ]
    summary = platform_incidents.summarize_incidents(incidents)
    assert summary['total'] == 4
    assert summary['open'] == 2
    assert summary['resolved'] == 2
    assert summary['by_severity'] == {'P1': 1, 'P2': 2, 'P3': 1}
    assert summary['by_status'] == {'failed': 1, 'pending': 1, 'sent': 2}
    # NULL-tenant (system-level) alerts do not count toward affected tenants.
    assert summary['affected_tenants'] == 2


def test_summarize_incidents_empty() -> None:
    from app.services import platform_incidents

    summary = platform_incidents.summarize_incidents([])
    assert summary == {
        'total': 0,
        'open': 0,
        'resolved': 0,
        'by_severity': {},
        'by_status': {},
        'affected_tenants': 0,
    }
