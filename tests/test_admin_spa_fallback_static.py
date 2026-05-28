from pathlib import Path

ADMIN_ROUTES = Path('copiloto_core/admin/routes.py')


def test_spa_fallback_route_registered():
    """BUG-002: any /admin/<react-router-path> must serve index.html via the
    SPA catch-all so hard refresh / deep link doesn't return 404.

    v1.5.0: SPA handlers viven en `spa_router` (no en `router`) para
    que `create_app(admin_panel=False)` pueda omitirlos sin perder
    los handlers de auth.
    """
    source = ADMIN_ROUTES.read_text()
    assert "@spa_router.get('/admin/{spa_path:path}'" in source
    assert 'admin_spa_fallback' in source
    assert 'return _dist_file()' in source


def test_spa_fallback_is_last_get_route_for_admin_paths():
    """The SPA catch-all (en spa_router) must be registered AFTER
    /admin/assets — único otro handler GET en el mismo router que
    podría colisionar por match-by-order.

    Auth handlers (/admin/login, /admin/callback, /admin/api/session)
    viven en el `router` principal — NO pueden ser shadowed por el
    catch-all del spa_router porque main.py monta `router` ANTES que
    `spa_router`, y FastAPI matchea contra los routers en orden de
    include."""
    source = ADMIN_ROUTES.read_text()
    catch_all_pos = source.index("@spa_router.get('/admin/{spa_path:path}'")
    # Assets vive en el MISMO router (spa_router) — debe ir antes que el catch-all.
    assets_pos = source.find("@spa_router.get('/admin/assets/{asset_path:path}'")
    assert assets_pos != -1, 'Missing /admin/assets route en spa_router'
    assert assets_pos < catch_all_pos, (
        '/admin/assets debe registrarse ANTES que el catch-all SPA '
        'dentro del mismo spa_router.'
    )
    # Auth handlers existen en `router` (no en spa_router) — verificamos
    # presencia, no orden relativo al catch-all.
    for specific in (
        "@router.get('/admin/login'",
        "@router.get('/admin/callback'",
        "@router.get('/admin/api/session')",
    ):
        assert specific in source, f'Missing auth route: {specific}'


def test_spa_fallback_does_not_intercept_api_proxy():
    """The /admin/api/core/{path:path} proxy uses api_route (not get), so it
    handles POST/PATCH/DELETE on /admin/api/core/v1/... and the SPA fallback
    (a GET-only route) doesn't shadow it. Sanity-check the proxy still exists."""
    source = ADMIN_ROUTES.read_text()
    assert "@router.api_route(" in source
    assert "'/admin/api/core/{path:path}'" in source
