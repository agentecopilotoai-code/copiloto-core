"""Static + functional tests for UI-006.3: GET /v1/platform/billing/mrr.

Covers:

* The endpoint is wired on ``platform_admin_router`` (which carries
  ``authenticate_request`` + ``require_platform_owner`` +
  ``require_mfa_for_privileged`` at the router level) and never on a
  tenant-scoped router.
* The handler enables ``app.support_mode`` transaction-locally for the
  cross-tenant read (the codebase's intended RLS bypass — TASK-0077).
* ``platform_billing.normalize_mrr`` normalises billing periods to a monthly
  figure and never raises on bad input.
* ``platform_billing.fold_tenant_rows`` / ``summarize_mrr_by_currency`` fold the
  granular aggregate rows into the response shape.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROUTES_FILE = Path('app/api/v1/routes.py')


@pytest.fixture(scope='module')
def routes_source() -> str:
    return ROUTES_FILE.read_text()


# ── Endpoint lives on platform_admin_router ──────────────────────────────────


def test_billing_mrr_endpoint_on_platform_admin_router(routes_source: str) -> None:
    assert "@platform_admin_router.get('/platform/billing/mrr')" in routes_source, (
        'GET /v1/platform/billing/mrr must be exposed on platform_admin_router (UI-006.3)'
    )


def test_billing_mrr_not_on_tenant_routers(routes_source: str) -> None:
    """Defense in depth: never let a tenant-scoped role reach the fleet billing."""
    for router in ('tenant_admin_router', 'tenant_ops_router', 'tenant_user_router'):
        assert f"@{router}.get('/platform/billing/mrr')" not in routes_source


def test_billing_mrr_handler_uses_support_mode_and_service(routes_source: str) -> None:
    # The cross-tenant read must go through the support_mode RLS bypass and the
    # pure aggregation helpers — not bespoke inline logic.
    handler_idx = routes_source.index("async def platform_billing_mrr(")
    handler = routes_source[handler_idx:handler_idx + 8000]
    assert "set_config('app.support_mode', 'true', true)" in handler
    assert 'platform_billing.fold_tenant_rows(' in handler
    assert 'platform_billing.summarize_mrr_by_currency(' in handler


# ── normalize_mrr ────────────────────────────────────────────────────────────


def test_normalize_mrr_normalises_each_period() -> None:
    from app.services import platform_billing

    assert platform_billing.normalize_mrr('monthly', 100) == 100.0
    assert platform_billing.normalize_mrr('quarterly', 300) == 100.0
    assert platform_billing.normalize_mrr('yearly', 1200) == 100.0


def test_normalize_mrr_is_total_on_bad_input() -> None:
    from app.services import platform_billing

    assert platform_billing.normalize_mrr('weekly', 100) == 0.0
    assert platform_billing.normalize_mrr('monthly', None) == 0.0
    assert platform_billing.normalize_mrr(None, 100) == 0.0


# ── fold_tenant_rows ─────────────────────────────────────────────────────────


def _sample_rows() -> list[dict]:
    return [
        {
            'tenant_id': 't1', 'slug': 'a', 'display_name': 'A', 'country_code': 'CO',
            'currency': 'COP', 'billing_period': 'monthly', 'price_sum': 480,
            'active_subscriptions': 2, 'past_due_subscriptions': 1, 'next_billing_at': '2026-05-21',
        },
        {
            'tenant_id': 't1', 'slug': 'a', 'display_name': 'A', 'country_code': 'CO',
            'currency': 'COP', 'billing_period': 'yearly', 'price_sum': 1200,
            'active_subscriptions': 1, 'past_due_subscriptions': 0, 'next_billing_at': '2026-06-01',
        },
        {
            'tenant_id': 't2', 'slug': 'b', 'display_name': 'B', 'country_code': 'MX',
            'currency': 'USD', 'billing_period': 'monthly', 'price_sum': 50,
            'active_subscriptions': 1, 'past_due_subscriptions': 0, 'next_billing_at': None,
        },
    ]


def test_fold_tenant_rows_aggregates_and_sorts_by_mrr() -> None:
    from app.services import platform_billing

    folded = platform_billing.fold_tenant_rows(_sample_rows())
    assert [t['tenant_id'] for t in folded] == ['t1', 't2']  # sorted by mrr desc

    t1 = folded[0]
    # monthly 480 + yearly 1200/12 (=100) = 580
    assert t1['mrr_total'] == 580.0
    assert t1['active_subscriptions'] == 3
    assert t1['past_due_subscriptions'] == 1
    assert t1['next_billing_at'] == '2026-05-21'  # earliest of the two
    assert t1['mrr_by_currency'] == [{'currency': 'COP', 'mrr': 580.0}]


def test_summarize_mrr_by_currency_sums_per_currency() -> None:
    from app.services import platform_billing

    summary = platform_billing.summarize_mrr_by_currency(_sample_rows())
    assert summary == [
        {'currency': 'COP', 'mrr': 580.0, 'active_subscriptions': 3},
        {'currency': 'USD', 'mrr': 50.0, 'active_subscriptions': 1},
    ]
