"""Static + functional tests for UI-006.8: platform feature-flags catalogue.

Covers:

* `GET /v1/platform/feature-flags` is wired on ``platform_admin_router`` (which
  carries ``authenticate_request`` + ``require_platform_owner`` +
  ``require_mfa_for_privileged``) and never on a tenant-scoped router.
* The endpoint is read-only — there is no write/toggle handler (the writable
  system is deferred to a backend ticket).
* ``feature_flags`` exposes a well-formed static registry and summarises it.
"""
from __future__ import annotations


import pytest
from tests._routes_aggregator import routes_aggregated_source

@pytest.fixture(scope='module')
def routes_source() -> str:
    return routes_aggregated_source()


# ── Endpoint lives on platform_admin_router, read-only ───────────────────────


def test_feature_flags_endpoint_on_platform_admin_router(routes_source: str) -> None:
    assert "@platform_admin_router.get('/platform/feature-flags')" in routes_source, (
        'GET /v1/platform/feature-flags must be on platform_admin_router (UI-006.8)'
    )


def test_feature_flags_not_on_tenant_routers(routes_source: str) -> None:
    for router in ('tenant_admin_router', 'tenant_ops_router', 'tenant_user_router'):
        assert f"@{router}.get('/platform/feature-flags')" not in routes_source


def test_feature_flags_endpoint_is_read_only(routes_source: str) -> None:
    """The writable feature-flag system is deferred — no POST/PATCH/PUT/DELETE
    handler may exist for the feature-flags path."""
    for verb in ('post', 'patch', 'put', 'delete'):
        assert f"@platform_admin_router.{verb}('/platform/feature-flags" not in routes_source


# ── feature_flags static registry ────────────────────────────────────────────


def test_registry_entries_are_well_formed() -> None:
    from app.services import feature_flags

    flags = feature_flags.list_feature_flags()
    assert len(flags) >= 8, 'expected the product feature-flag catalogue'
    keys = {flag['key'] for flag in flags}
    assert len(keys) == len(flags), 'flag keys must be unique'
    for flag in flags:
        assert set(flag) == {
            'key', 'description', 'type', 'default', 'rollout_pct', 'related_task',
        }
        assert flag['type'] in feature_flags.FLAG_TYPES
        assert flag['default'] in ('on', 'off', 'beta')
        assert 0 <= flag['rollout_pct'] <= 100
        # Every flag maps to a real shipped TASK — no fabricated experiments.
        assert 'TASK-' in flag['related_task']


def test_list_feature_flags_returns_copies() -> None:
    from app.services import feature_flags

    first = feature_flags.list_feature_flags()
    first[0]['key'] = 'mutated'
    second = feature_flags.list_feature_flags()
    assert second[0]['key'] != 'mutated', 'list_feature_flags must return fresh copies'


def test_summarize_feature_flags_counts() -> None:
    from app.services import feature_flags

    summary = feature_flags.summarize_feature_flags(feature_flags.list_feature_flags())
    assert summary['total'] == len(feature_flags.FEATURE_FLAGS)
    assert summary['on'] + summary['off'] == summary['total']
    assert sum(summary['by_type'].values()) == summary['total']
    for flag_type in summary['by_type']:
        assert flag_type in feature_flags.FLAG_TYPES
