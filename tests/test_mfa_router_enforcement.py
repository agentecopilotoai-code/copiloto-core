"""Static tests for TASK-0080: MFA enforcement attached to privileged routers
(BUG15) and BFF proxy gate when MFA is required (BUG14).

These are repository-source tests: they assert that the dependency is wired
at router construction, that the proxy returns 403 when the session has
``mfa_required=true``, and that the admin UI overlay is non-dismissable.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROUTES_FILE = Path('app/api/v1/routes.py')
ADMIN_ROUTES_FILE = Path('app/admin/routes.py')
ROUTER_FILE = Path('admin-panel/src/app/router.jsx')
MFA_BLOCKER_FILE = Path('admin-panel/src/components/domain/MfaRequiredBlocker.jsx')


# ── BUG15: require_mfa_for_privileged attached to privileged routers ─────────


def _router_block(source: str, router_name: str) -> str:
    pattern = rf"{router_name}\s*=\s*APIRouter\((.*?)\)\n"
    match = re.search(pattern, source, re.DOTALL)
    assert match, f'router {router_name} not found'
    return match.group(1)


def test_tenant_admin_router_attaches_mfa_dependency():
    source = ROUTES_FILE.read_text()
    block = _router_block(source, 'tenant_admin_router')
    assert 'require_mfa_for_privileged' in block


def test_platform_admin_router_attaches_mfa_dependency():
    source = ROUTES_FILE.read_text()
    block = _router_block(source, 'platform_admin_router')
    assert 'require_mfa_for_privileged' in block


def test_tenant_signup_router_attaches_mfa_dependency():
    source = ROUTES_FILE.read_text()
    block = _router_block(source, 'tenant_signup_router')
    assert 'require_mfa_for_privileged' in block


def test_tenant_catalog_router_attaches_mfa_dependency():
    source = ROUTES_FILE.read_text()
    block = _router_block(source, 'tenant_catalog_router')
    assert 'require_mfa_for_privileged' in block


def test_tenant_ops_router_does_not_require_mfa():
    """Agents (handoff helpers) explicitly do not need MFA — the dependency
    only fires for privileged roles."""
    source = ROUTES_FILE.read_text()
    block = _router_block(source, 'tenant_ops_router')
    assert 'require_mfa_for_privileged' not in block


def test_tenant_analytics_router_does_not_require_mfa():
    source = ROUTES_FILE.read_text()
    block = _router_block(source, 'tenant_analytics_router')
    assert 'require_mfa_for_privileged' not in block


def test_routes_import_includes_require_mfa():
    source = ROUTES_FILE.read_text()
    assert 'require_mfa_for_privileged' in source
    # Confirm the import isn't dead code:
    occurrences = source.count('require_mfa_for_privileged')
    assert occurrences >= 5, occurrences


# ── BUG14 (server half): BFF proxy returns 403 when mfa_required ─────────────


def test_admin_proxy_gates_on_session_mfa_required():
    source = ADMIN_ROUTES_FILE.read_text()
    proxy_start = source.index('async def admin_core_api_proxy(')
    # BUG-008 cambió la línea final del proxy (Response se construye antes
    # del Set-Cookie forwarding y se retorna como `proxied` tras los append).
    # Apuntamos al construct de Response (cualquier shape) como marker.
    proxy_end = source.index('Response(\n        content=upstream_response.content,', proxy_start)
    block = source[proxy_start:proxy_end]
    assert '_session_mfa_required(session)' in block
    assert 'status_code=403' in block
    assert "'mfa_required'" in block


def test_admin_proxy_blocks_before_relaying_request_body():
    """The MFA check MUST happen BEFORE the proxy reads the request body or
    forwards anything upstream. Otherwise the Core API briefly receives the
    request despite the gate."""
    source = ADMIN_ROUTES_FILE.read_text()
    proxy_start = source.index('async def admin_core_api_proxy(')
    end = source.index('async with httpx.AsyncClient', proxy_start)
    head = source[proxy_start:end]
    assert head.index('_session_mfa_required(session)') < head.index('body = await request.body()')


# ── BUG14 (UI half): overlay is non-dismissable, no "Continuar sin MFA" ──────


def test_admin_layout_overlay_has_no_continue_without_mfa_button():
    source = MFA_BLOCKER_FILE.read_text()
    assert 'Continuar sin MFA' not in source


def test_admin_layout_overlay_is_blocking_not_dismissable():
    """When mfa_required, the router root (RootLayout) returns ONLY the overlay
    — no shell/sidebar/workspace renders. That is how we hard-stop the user from
    clicking through to anything privileged (UI-003 moved the gate here)."""
    source = ROUTER_FILE.read_text()
    assert 'if (session?.mfa_required === true) {' in source
    assert 'return <MfaRequiredBlocker />' in source
    # No dismissable state should remain
    assert 'setMfaDismissed' not in source
    assert 'mfaDismissed' not in source


def test_admin_layout_overlay_offers_only_logout_action():
    source = MFA_BLOCKER_FILE.read_text()
    block_start = source.index('function MfaRequiredBlocker(')
    block_end = source.index('\n}\n', block_start)
    block = source[block_start:block_end]
    # The only action button is Cerrar sesión, the form posts to /admin/logout.
    assert "adminPath('/admin/logout')" in block
    assert 'Cerrar sesión' in block
    # No "skip", "continuar", or "dismiss" verbs in the markup
    lowered = block.lower()
    for forbidden in ('continuar sin mfa', 'omitir', 'descartar', 'skip-mfa'):
        assert forbidden not in lowered, forbidden


# ── BUG14 + BUG15 integration via direct dependency check ────────────────────


def test_require_mfa_for_privileged_403s_unverified_admin(monkeypatch):
    """Smoke: with Auth0 active, an admin session without mfa_verified raises
    403 from the dependency. This complements the dedicated MFA tests by
    asserting the dependency is reachable from the routes module."""
    import asyncio

    from fastapi import HTTPException

    from app.api.v1.routes import require_mfa_for_privileged
    from app.core.config import get_settings
    from starlette.requests import Request

    monkeypatch.setenv('DATABASE_URL', 'postgresql://example')
    monkeypatch.setenv('JWT_SECRET', 'local-secret-with-min-length')
    monkeypatch.setenv('SERVICE_TOKEN', 'service-token-with-min-length')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 's3-secret')
    monkeypatch.setenv('AUTH0_DOMAIN', 'example.auth0.com')
    get_settings.cache_clear()

    request = Request({'type': 'http', 'method': 'GET', 'path': '/', 'headers': []})
    request.state.actor_type = 'user'
    request.state.actor_id = 'user-1'
    request.state.roles = ['admin']
    request.state.mfa_verified = False

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(require_mfa_for_privileged(request))
    assert exc_info.value.status_code == 403
    get_settings.cache_clear()


def test_require_mfa_for_privileged_passes_unprivileged_session(monkeypatch):
    """Agents and managers are not privileged — they pass without MFA even
    when Auth0 is active."""
    import asyncio

    from app.api.v1.routes import require_mfa_for_privileged
    from app.core.config import get_settings
    from starlette.requests import Request

    monkeypatch.setenv('DATABASE_URL', 'postgresql://example')
    monkeypatch.setenv('JWT_SECRET', 'local-secret-with-min-length')
    monkeypatch.setenv('SERVICE_TOKEN', 'service-token-with-min-length')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 's3-secret')
    monkeypatch.setenv('AUTH0_DOMAIN', 'example.auth0.com')
    get_settings.cache_clear()

    request = Request({'type': 'http', 'method': 'GET', 'path': '/', 'headers': []})
    request.state.actor_type = 'user'
    request.state.actor_id = 'user-1'
    request.state.roles = ['agent']
    request.state.mfa_verified = False

    # Should not raise
    asyncio.run(require_mfa_for_privileged(request))
    get_settings.cache_clear()


def test_require_mfa_for_privileged_passes_service_tokens(monkeypatch):
    import asyncio

    from app.api.v1.routes import require_mfa_for_privileged
    from app.core.config import get_settings
    from starlette.requests import Request

    monkeypatch.setenv('DATABASE_URL', 'postgresql://example')
    monkeypatch.setenv('JWT_SECRET', 'local-secret-with-min-length')
    monkeypatch.setenv('SERVICE_TOKEN', 'service-token-with-min-length')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 's3-secret')
    monkeypatch.setenv('AUTH0_DOMAIN', 'example.auth0.com')
    get_settings.cache_clear()

    request = Request({'type': 'http', 'method': 'GET', 'path': '/', 'headers': []})
    request.state.actor_type = 'service'
    request.state.actor_id = 'service-account'
    request.state.roles = ['admin']
    request.state.mfa_verified = False

    asyncio.run(require_mfa_for_privileged(request))
    get_settings.cache_clear()


# ── Proxy returns the standard JSON shape on 403 ─────────────────────────────


def test_proxy_403_payload_is_json_with_detail_mfa_required():
    source = ADMIN_ROUTES_FILE.read_text()
    proxy_start = source.index('async def admin_core_api_proxy(')
    block = source[proxy_start:proxy_start + 1500]
    # The fastapi.exception_handlers convention is {"detail": "<reason>"}.
    detail_match = re.search(r"json\.dumps\(\{'detail':\s*'mfa_required'\}\)", block)
    assert detail_match, 'expected json detail mfa_required'
    media_match = re.search(r"media_type='application/json'", block)
    assert media_match


# ── Session payload still emits ``mfa_required`` for the UI gate ─────────────


def test_session_endpoint_still_publishes_mfa_required_flag():
    source = ADMIN_ROUTES_FILE.read_text()
    session_start = source.index("@router.get('/admin/api/session')")
    end = source.index('@router.', session_start + 1)
    block = source[session_start:end]
    assert "'mfa_required': _session_mfa_required(session)" in block
