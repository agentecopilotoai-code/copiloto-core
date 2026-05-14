"""Static + functional tests for UI-006.6: platform runbooks catalogue.

Covers:

* `GET /v1/platform/runbooks` and `GET /v1/platform/runbooks/{slug}` are wired
  on ``platform_admin_router`` (which carries ``authenticate_request`` +
  ``require_platform_owner`` + ``require_mfa_for_privileged``) and never on a
  tenant-scoped router.
* The detail handler renders through ``render_markdown_to_safe_html`` (TASK-0076).
* ``platform_runbooks`` lists the real ``docs/runbooks/`` files, excludes the
  README index, derives categories/titles, and defends against path traversal.
"""
from __future__ import annotations

from pathlib import Path

import pytest

ROUTES_FILE = Path('app/api/v1/routes.py')


@pytest.fixture(scope='module')
def routes_source() -> str:
    return ROUTES_FILE.read_text()


# ── Endpoints live on platform_admin_router ──────────────────────────────────


def test_runbook_endpoints_on_platform_admin_router(routes_source: str) -> None:
    assert "@platform_admin_router.get('/platform/runbooks')" in routes_source, (
        'GET /v1/platform/runbooks must be on platform_admin_router (UI-006.6)'
    )
    assert "@platform_admin_router.get('/platform/runbooks/{slug}')" in routes_source, (
        'GET /v1/platform/runbooks/{slug} must be on platform_admin_router (UI-006.6)'
    )


def test_runbook_endpoints_not_on_tenant_routers(routes_source: str) -> None:
    for router in ('tenant_admin_router', 'tenant_ops_router', 'tenant_user_router'):
        assert f"@{router}.get('/platform/runbooks')" not in routes_source
        assert f"@{router}.get('/platform/runbooks/{{slug}}')" not in routes_source


def test_runbook_detail_renders_through_safe_html(routes_source: str) -> None:
    detail_idx = routes_source.index('async def platform_runbook_detail(')
    handler = routes_source[detail_idx:detail_idx + 1200]
    assert 'render_markdown_to_safe_html(' in handler
    assert "HTTPException(status_code=404" in handler


# ── slug validation / path-traversal defense ─────────────────────────────────


def test_is_valid_slug_accepts_real_slugs_and_rejects_traversal() -> None:
    from app.services import platform_runbooks

    assert platform_runbooks.is_valid_slug('meta-token-expired') is True
    assert platform_runbooks.is_valid_slug('postgres-down') is True
    # Traversal / separators / dots / empty are all rejected.
    assert platform_runbooks.is_valid_slug('../etc/passwd') is False
    assert platform_runbooks.is_valid_slug('a/b') is False
    assert platform_runbooks.is_valid_slug('a.b') is False
    assert platform_runbooks.is_valid_slug('') is False
    assert platform_runbooks.is_valid_slug(None) is False


def test_runbook_path_rejects_escape_and_missing() -> None:
    from app.services import platform_runbooks

    assert platform_runbooks.runbook_path('../README') is None
    assert platform_runbooks.runbook_path('nonexistent-runbook') is None
    # README is reachable as a file but is excluded from the catalogue listing,
    # not from path resolution — the listing test below covers the exclusion.
    valid = platform_runbooks.runbook_path('meta-token-expired')
    assert valid is not None and valid.name == 'meta-token-expired.md'


# ── categorisation / title extraction ────────────────────────────────────────


def test_categorize_runbook() -> None:
    from app.services import platform_runbooks

    assert platform_runbooks.categorize_runbook('meta-token-expired') == 'Meta · WhatsApp'
    assert platform_runbooks.categorize_runbook('cloud-llm-rate-limited') == 'LLM · Breakers'
    assert platform_runbooks.categorize_runbook('postgres-down') == 'Infraestructura'
    assert platform_runbooks.categorize_runbook('webhook-flood') == 'Tráfico · Rate limit'
    assert platform_runbooks.categorize_runbook('consent-violation-claim') == 'Compliance'
    assert platform_runbooks.categorize_runbook('something-else') == 'General'


def test_extract_title_reads_first_h1() -> None:
    from app.services import platform_runbooks

    assert platform_runbooks.extract_title('# Runbook — Foo\n\n## Bar') == 'Runbook — Foo'
    assert platform_runbooks.extract_title('no heading here') == 'Runbook'
    assert platform_runbooks.extract_title('') == 'Runbook'


# ── catalogue listing / reading the real files ───────────────────────────────


def test_list_runbooks_returns_real_files_without_readme() -> None:
    from app.services import platform_runbooks

    items = platform_runbooks.list_runbooks()
    assert len(items) >= 8, 'expected the docs/runbooks/*.md catalogue'
    slugs = {item['slug'] for item in items}
    assert 'readme' not in {s.lower() for s in slugs}, 'README must not be listed'
    assert 'meta-token-expired' in slugs
    for item in items:
        assert set(item) == {'slug', 'filename', 'title', 'category', 'size_bytes'}
        assert item['size_bytes'] > 0


def test_read_runbook_returns_content_or_none() -> None:
    from app.services import platform_runbooks

    runbook = platform_runbooks.read_runbook('meta-token-expired')
    assert runbook is not None
    assert runbook['slug'] == 'meta-token-expired'
    assert runbook['title'].startswith('Runbook')
    assert '#' in runbook['content_md']

    assert platform_runbooks.read_runbook('../../etc/passwd') is None
    assert platform_runbooks.read_runbook('does-not-exist') is None
