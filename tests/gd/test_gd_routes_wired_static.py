"""Test estático: el router GD se monta correctamente en `app.main`.

Verifica que /v1/gd/me aparezca en `app.routes` después del wiring.
Sin este test, un import roto en el chain (app/gd/__init__ → routes → handlers)
pasaría silencioso y los tests anteriores seguirían pasando porque importan
directamente, no via app.main.
"""
from __future__ import annotations

from fastapi.routing import APIRoute

import app.main as app_main


class TestGdRouterWired:
    def test_get_api_v1_gd_me_existe(self) -> None:
        # `app_main.app` es la instancia FastAPI ya construida (side-effect del
        # import en conftest.py).
        paths = {
            route.path
            for route in app_main.app.routes
            if isinstance(route, APIRoute)
        }
        assert '/v1/gd/me' in paths, (
            f'Esperaba /v1/gd/me en app.routes. '
            f'Rutas GD encontradas: {sorted(p for p in paths if "/gd/" in p)}'
        )

    def test_modulo_gd_se_importa_sin_errores(self) -> None:
        # Test sentinel: importar el módulo entero no debe lanzar.
        import app.gd  # noqa: F401
        import app.gd.handlers  # noqa: F401
        import app.gd.handlers.me_handlers  # noqa: F401
        import app.gd.routes  # noqa: F401
        import app.gd.schemas  # noqa: F401
        import app.gd.schemas.identidad  # noqa: F401
        import app.gd.security  # noqa: F401
        import app.gd.services  # noqa: F401
        import app.gd.services.audit_emitter  # noqa: F401
