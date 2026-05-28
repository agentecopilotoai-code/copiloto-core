from pathlib import Path

ADMIN_ROUTES = Path('copiloto_core/admin/routes.py')


def test_spa_fallback_route_registered():
    """BUG-002: any /admin/<react-router-path> must serve index.html via the
    SPA catch-all so hard refresh / deep link doesn't return 404."""
    source = ADMIN_ROUTES.read_text()
    assert "@router.get('/admin/{spa_path:path}'" in source
    assert 'admin_spa_fallback' in source
    assert 'return _dist_file()' in source


def test_spa_fallback_is_last_get_route_for_admin_paths():
    """The SPA catch-all must be registered AFTER all specific /admin/* GET
    handlers so FastAPI's match-by-order picks the specific routes first
    (/admin/login, /admin/callback, /admin/assets/*, /admin/api/*) and only
    falls through to the catch-all for unrecognized paths."""
    source = ADMIN_ROUTES.read_text()
    catch_all_pos = source.index("@router.get('/admin/{spa_path:path}'")
    # Specific routes that MUST be registered before the catch-all.
    for specific in (
        "@router.get('/admin/login'",
        "@router.get('/admin/callback'",
        "@router.get('/admin/api/session')",
        "@router.get('/admin/assets/{asset_path:path}'",
    ):
        specific_pos = source.find(specific)
        assert specific_pos != -1, f'Missing specific route: {specific}'
        assert specific_pos < catch_all_pos, (
            f'Specific route {specific!r} is registered AFTER the SPA catch-all; '
            'FastAPI would never reach it. Move the catch-all to the END of the file.'
        )


def test_spa_fallback_does_not_intercept_api_proxy():
    """The /admin/api/core/{path:path} proxy uses api_route (not get), so it
    handles POST/PATCH/DELETE on /admin/api/core/v1/... and the SPA fallback
    (a GET-only route) doesn't shadow it. Sanity-check the proxy still exists."""
    source = ADMIN_ROUTES.read_text()
    assert "@router.api_route(" in source
    assert "'/admin/api/core/{path:path}'" in source
