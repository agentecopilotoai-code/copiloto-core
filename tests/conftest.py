"""Test-suite configuration.

Registers ``conftest_e2e`` as a pytest plugin so the journey suite can request
its fixtures (``tenant_factory``, ``e2e_database_url``) by name. The plugin
itself is inert when ``RUN_E2E != 1`` — every fixture short-circuits with
``pytest.skip``.

``tests/load/`` contains the Locust suite (TASK-0072); it is invoked by the
`load-test` GitHub Actions job and excluded from default pytest collection so
the unit-test CI does not require ``locust`` to be installed.

BUGFIX-PLATFORM-ROUTES (TASK-INFLU-002 / TASK-INFLU-019) — preloadear
``app.main`` ANTES de que cualquier test importe ``app.influencer.admin_routes``
directamente. Sin esto, una importación temprana de ``admin_routes`` corre
``from app.api.v1.routes import platform_admin_router`` cuando v1.routes
todavía no terminó de cargar; v1.routes (línea ~1713) intenta importar
``admin_routes`` de vuelta (circular), recibe el módulo a medio cargar (sin
decoradores ejecutados), e invoca ``router.include_router(platform_admin_router)``
con la lista vacía. Resultado: los endpoints quedan registrados en
``platform_admin_router.routes`` pero NUNCA aparecen en ``app.routes`` — 404
en tests con ``TestClient`` aunque el código de prod corre bien.
"""
import os

# Env vars dummy para que ``app.main`` se importe sin requerir secrets/DB
# reales. Los tests unitarios mockean toda la capa de DB, así que estas URLs
# nunca se conectan.
os.environ.setdefault('DATABASE_URL', 'postgresql://x:x@localhost/x')
os.environ.setdefault('JWT_SECRET', 'x' * 32)
os.environ.setdefault('SERVICE_TOKEN', 'x' * 32)
os.environ.setdefault('S3_SECRET_ACCESS_KEY', 'x' * 32)
# Fernet key estable para tests — el helper `_get_secret_cipher` la usa al
# cifrar/descifrar API keys de proveedores IA. Generada vía Fernet.generate_key()
# y hardcoded para que los tests reproduzcan bytes idénticos.
os.environ.setdefault(
    'AI_PROVIDER_MASTER_KEY',
    'zmWmIxJtxg8Cu0AYJ0jZeXqGNbRkW9pTfLqo3GqAFEY=',
)

import app.main  # noqa: F401, E402  — side-effect: dispara el wiring completo.

pytest_plugins = ['tests.conftest_e2e']
collect_ignore_glob = ['load/*']
