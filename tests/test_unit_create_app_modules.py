"""Tests para `create_app(modules=[...])` — wiring de módulos opt-in
(Fase 5).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient

from copiloto_core import CoreModule, create_app


# ─── Smoke: sin módulos sigue funcionando ───────────────────────────────


def test_create_app_no_modules_works():
    app = create_app()
    assert hasattr(app.state, 'core_modules')
    assert app.state.core_modules == ()


# ─── Un módulo: router montado ──────────────────────────────────────────


def test_module_router_mounted_at_url_prefix():
    router = APIRouter()

    @router.get('/ping')
    def ping():
        return {'pong': True}

    mod = CoreModule(code='mi_modulo', router=router)
    app = create_app(modules=[mod])

    client = TestClient(app)
    # url_prefix convierte snake_case → kebab-case
    resp = client.get('/v1/mi-modulo/ping')
    assert resp.status_code == 200
    assert resp.json() == {'pong': True}


def test_multiple_modules_mounted_independently():
    r1 = APIRouter()
    r2 = APIRouter()

    @r1.get('/info')
    def info1():
        return {'mod': 'one'}

    @r2.get('/info')
    def info2():
        return {'mod': 'two'}

    m1 = CoreModule(code='one', router=r1)
    m2 = CoreModule(code='two', router=r2)
    app = create_app(modules=[m1, m2])

    client = TestClient(app)
    assert client.get('/v1/one/info').json() == {'mod': 'one'}
    assert client.get('/v1/two/info').json() == {'mod': 'two'}


def test_duplicate_module_code_raises():
    r = APIRouter()
    m_a = CoreModule(code='dup', router=r)
    m_b = CoreModule(code='dup', router=r)
    with pytest.raises(ValueError, match='duplicado'):
        create_app(modules=[m_a, m_b])


def test_module_router_can_use_dependencies():
    """El router del módulo puede usar los Depends del core (smoke).

    No validamos status code específico porque el comportamiento de
    `authenticate_request` depende del entorno (en tests con env vars
    dummy puede devolver actor anónimo). Lo importante: el endpoint
    fue montado y el Depends fue invocado sin error de wiring.
    """
    from copiloto_core import authenticate_request  # noqa: PLC0415
    from fastapi import Depends  # noqa: PLC0415

    router = APIRouter()

    @router.get('/protected')
    async def protected(actor=Depends(authenticate_request)):
        return {'actor_resolved': actor is not None}

    mod = CoreModule(code='secured', router=router)
    app = create_app(modules=[mod])
    client = TestClient(app)

    resp = client.get('/v1/secured/protected')
    # OK = el endpoint existe y se ejecutó (con o sin auth real).
    # 404 = el endpoint NO se registró → bug del wiring.
    assert resp.status_code != 404


# ─── Static mounts ──────────────────────────────────────────────────────


def test_static_mount_serves_files(tmp_path: Path):
    dist = tmp_path / 'spa-dist'
    dist.mkdir()
    (dist / 'index.html').write_text('<html><body>Mi App</body></html>')
    (dist / 'app.js').write_text('console.log("ok")')

    router = APIRouter()
    mod = CoreModule(
        code='ui_module',
        router=router,
        static_mounts={'/app-ui': str(dist)},
    )
    app = create_app(modules=[mod])
    client = TestClient(app)

    # index.html accesible
    resp = client.get('/app-ui/')
    assert resp.status_code == 200
    assert 'Mi App' in resp.text

    # asset accesible
    resp = client.get('/app-ui/app.js')
    assert resp.status_code == 200
    assert 'console.log' in resp.text


def test_static_mount_html_serves_index_at_root(tmp_path: Path):
    """`html=True` sirve index.html cuando se solicita la raíz del mount.

    NOTA: Starlette's `StaticFiles(html=True)` NO hace catch-all SPA
    fallback para rutas arbitrarias. Si el módulo requiere full
    client-side routing (URLs como /spa/customers/123), debe agregar
    una ruta catch-all en su propio router que sirva el `index.html`.
    Documentado en `docs/EXTENDING.md`.
    """
    dist = tmp_path / 'spa-dist'
    dist.mkdir()
    (dist / 'index.html').write_text('<html>SPA</html>')

    mod = CoreModule(
        code='spa_module',
        router=APIRouter(),
        static_mounts={'/spa': str(dist)},
    )
    app = create_app(modules=[mod])
    client = TestClient(app)

    resp = client.get('/spa/')
    assert resp.status_code == 200
    assert 'SPA' in resp.text


# ─── Module state introspection ─────────────────────────────────────────


def test_app_state_exposes_registered_modules():
    r = APIRouter()
    m = CoreModule(code='alpha', router=r, capabilities=('alpha:read',))
    app = create_app(modules=[m])
    assert len(app.state.core_modules) == 1
    assert app.state.core_modules[0].code == 'alpha'
    assert app.state.core_modules[0].capabilities == ('alpha:read',)
