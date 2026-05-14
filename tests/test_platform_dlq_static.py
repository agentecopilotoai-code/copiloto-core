"""Static + functional tests for UI-006.5: platform-wide Outbound DLQ.

Covers:

* `GET /v1/platform/outbound-dlq` and `POST /v1/platform/outbound-dlq/retry`
  are wired on ``platform_admin_router`` (which carries ``authenticate_request``
  + ``require_platform_owner`` + ``require_mfa_for_privileged``) and never on a
  tenant-scoped router.
* Both handlers enable ``app.support_mode`` transaction-locally for the
  cross-tenant read of ``app.messages``.
* The bulk-retry handler delegates to ``outbound_dlq.requeue_tenant_dlq`` and
  audits the action.
* ``platform_dlq`` folds the granular aggregate rows and derives runbooks.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROUTES_FILE = Path('app/api/v1/routes.py')


@pytest.fixture(scope='module')
def routes_source() -> str:
    return ROUTES_FILE.read_text()


# ── Endpoints live on platform_admin_router ──────────────────────────────────


def test_dlq_endpoints_on_platform_admin_router(routes_source: str) -> None:
    assert "@platform_admin_router.get('/platform/outbound-dlq')" in routes_source, (
        'GET /v1/platform/outbound-dlq must be on platform_admin_router (UI-006.5)'
    )
    assert "@platform_admin_router.post('/platform/outbound-dlq/retry')" in routes_source, (
        'POST /v1/platform/outbound-dlq/retry must be on platform_admin_router (UI-006.5)'
    )


def test_dlq_endpoints_not_on_tenant_routers(routes_source: str) -> None:
    """Defense in depth: never let a tenant-scoped role reach the fleet DLQ."""
    for router in ('tenant_admin_router', 'tenant_ops_router', 'tenant_user_router'):
        assert f"@{router}.get('/platform/outbound-dlq')" not in routes_source
        assert f"@{router}.post('/platform/outbound-dlq/retry')" not in routes_source


def test_dlq_handlers_use_support_mode(routes_source: str) -> None:
    list_idx = routes_source.index("async def platform_outbound_dlq(")
    list_handler = routes_source[list_idx:list_idx + 3000]
    assert "set_config('app.support_mode', 'true', true)" in list_handler
    assert 'platform_dlq.fold_dlq_by_tenant(' in list_handler

    retry_idx = routes_source.index("async def platform_outbound_dlq_retry(")
    retry_handler = routes_source[retry_idx:retry_idx + 2000]
    assert "set_config('app.support_mode', 'true', true)" in retry_handler
    assert 'requeue_tenant_dlq(' in retry_handler
    # The bulk retry must be audited.
    assert "action='platform.outbound_dlq.bulk_retried'" in retry_handler


def test_requeue_tenant_dlq_is_exported() -> None:
    from app.services import outbound_dlq

    assert hasattr(outbound_dlq, 'requeue_tenant_dlq')
    assert 'requeue_tenant_dlq' in outbound_dlq.__all__


# ── platform_dlq pure helpers ────────────────────────────────────────────────


def _rows() -> list[dict]:
    return [
        {'tenant_id': 't1', 'slug': 'a', 'display_name': 'A', 'error_code': '80007', 'count': 14},
        {'tenant_id': 't1', 'slug': 'a', 'display_name': 'A', 'error_code': '190', 'count': 3},
        {'tenant_id': 't2', 'slug': 'b', 'display_name': 'B', 'error_code': '131026', 'count': 6},
        {'tenant_id': 't3', 'slug': 'c', 'display_name': 'C', 'error_code': 'transport_error', 'count': 2},
    ]


def test_fold_dlq_by_tenant_aggregates_and_picks_top_error() -> None:
    from app.services import platform_dlq

    folded = platform_dlq.fold_dlq_by_tenant(_rows())
    assert [t['tenant_id'] for t in folded] == ['t1', 't2', 't3']  # sorted by total desc
    t1 = folded[0]
    assert t1['total'] == 17
    assert t1['top_error_code'] == '80007'
    assert t1['top_error_count'] == 14


def test_summarize_by_error_code_attaches_runbooks() -> None:
    from app.services import platform_dlq

    summary = platform_dlq.summarize_by_error_code(_rows())
    assert summary[0] == {'error_code': '80007', 'count': 14, 'runbook': 'rate-limit-meta-hit.md'}
    by_code = {item['error_code']: item for item in summary}
    assert by_code['190']['runbook'] == 'meta-token-expired.md'
    # Codes without a published runbook stay None instead of guessing.
    assert by_code['131026']['runbook'] is None
    assert by_code['transport_error']['runbook'] is None


def test_summarize_fleet_dlq_counts_totals_and_top_error() -> None:
    from app.services import platform_dlq

    summary = platform_dlq.summarize_fleet_dlq(_rows())
    assert summary['total'] == 25
    assert summary['affected_tenants'] == 3
    assert summary['top_error_code'] == '80007'
    assert summary['top_error_count'] == 14


def test_runbook_for_error_code() -> None:
    from app.services import platform_dlq

    assert platform_dlq.runbook_for_error_code('190') == 'meta-token-expired.md'
    assert platform_dlq.runbook_for_error_code('80007') == 'rate-limit-meta-hit.md'
    assert platform_dlq.runbook_for_error_code('999999') is None
    assert platform_dlq.runbook_for_error_code(None) is None
