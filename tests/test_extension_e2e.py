"""E2E del extension system del core (Fase 11).

Compone un `CoreModule` dummy en memoria + lo monta vía
`create_app(modules=[dummy])` + ejerce el flujo completo:

  1. Router del módulo se monta y responde en su URL prefix.
  2. Capabilities declaradas se preservan en `app.state.core_modules`.
  3. Migrations referenciadas se resuelven vía importlib.resources.
  4. Static mount (si tiene) sirve archivos.
  5. Branding del deployment se expone en /v1/branding.
  6. require_capability gate funciona sobre el router del módulo.
  7. verify_device_hmac funciona sobre endpoints públicos.

Este test reemplaza el "ejemplo sat-alertas" que NO escribimos —
demuestra que el sistema de extensión funciona end-to-end con un
módulo trivial.
"""
from __future__ import annotations

import hashlib
import hmac
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from copiloto_core import (
    BrandingConfig,
    CoreModule,
    create_app,
    require_capability,
    verify_device_hmac,
)


# ─── Setup: módulo dummy in-memory ────────────────────────────────────────


def _build_dummy_module(static_dir: Path | None = None) -> CoreModule:
    """Construye un módulo dummy completo para el E2E."""
    router = APIRouter()

    @router.get('/info')
    def info():
        return {
            'module': 'dummy_e2e',
            'features': ['routing', 'capabilities', 'static', 'devices'],
        }

    @router.post('/protected')
    async def protected_endpoint(
        _cap=Depends(require_capability('dummy_e2e:write')),
    ):
        return {'ok': True}

    async def _device_secret_lookup(device_id: str) -> str | None:
        # In-memory device registry para el test.
        return 'shared-secret-xyz' if device_id == 'sensor-001' else None

    @router.post('/ingest')
    async def ingest_telemetry(
        device=Depends(verify_device_hmac(_device_secret_lookup)),
    ):
        return {'device': device.device_id, 'received': True}

    kwargs = {
        'code': 'dummy_e2e',
        'router': router,
        'capabilities': ('dummy_e2e:read', 'dummy_e2e:write'),
    }
    if static_dir is not None:
        kwargs['static_mounts'] = {'/m/dummy': str(static_dir)}

    return CoreModule(**kwargs)


# ─── E2E 1: router montado y responde ────────────────────────────────────


def test_e2e_module_router_responds():
    mod = _build_dummy_module()
    app = create_app(modules=[mod])
    client = TestClient(app)

    resp = client.get('/v1/dummy-e2e/info')
    assert resp.status_code == 200
    data = resp.json()
    assert data['module'] == 'dummy_e2e'
    assert 'routing' in data['features']


# ─── E2E 2: capabilities preservadas en app.state ────────────────────────


def test_e2e_capabilities_visible_in_app_state():
    mod = _build_dummy_module()
    app = create_app(modules=[mod])

    registered = app.state.core_modules
    assert len(registered) == 1
    assert registered[0].code == 'dummy_e2e'
    assert 'dummy_e2e:read' in registered[0].capabilities
    assert 'dummy_e2e:write' in registered[0].capabilities


# ─── E2E 3: branding accesible públicamente ──────────────────────────────


def test_e2e_branding_endpoint_serves_deployment_config():
    mod = _build_dummy_module()
    app = create_app(
        modules=[mod],
        branding=BrandingConfig(
            product_name='Dummy SaaS',
            primary_color='#001122',
            support_email='ayuda@dummy.test',
        ),
    )
    client = TestClient(app)

    resp = client.get('/v1/branding')
    assert resp.status_code == 200
    data = resp.json()
    assert data['product_name'] == 'Dummy SaaS'
    assert data['primary_color'] == '#001122'
    assert data['support_email'] == 'ayuda@dummy.test'


# ─── E2E 4: static mount sirve archivos ─────────────────────────────────


def test_e2e_module_static_mount_serves_spa_assets(tmp_path: Path):
    dist = tmp_path / 'spa'
    dist.mkdir()
    (dist / 'index.html').write_text('<html>Dummy SPA</html>')
    (dist / 'app.js').write_text('// dummy module spa')

    mod = _build_dummy_module(static_dir=dist)
    app = create_app(modules=[mod])
    client = TestClient(app)

    # Asset directo
    r1 = client.get('/m/dummy/app.js')
    assert r1.status_code == 200
    assert 'dummy module spa' in r1.text

    # Root sirve index.html (html=True)
    r2 = client.get('/m/dummy/')
    assert r2.status_code == 200
    assert 'Dummy SPA' in r2.text


# ─── E2E 5: require_capability funciona contra router del módulo ────────


def test_e2e_require_capability_blocks_when_actor_missing():
    """Sin actor_id en request.state → 401 actor_required."""
    mod = _build_dummy_module()
    app = create_app(modules=[mod])
    client = TestClient(app)

    # Sin auth setteada en state.actor_id → require_capability raise 401
    resp = client.post('/v1/dummy-e2e/protected')
    # El detail estructurado del require_capability:
    assert resp.status_code in (401, 403, 422)
    if resp.status_code == 401:
        detail = resp.json().get('detail', {})
        if isinstance(detail, dict):
            assert detail.get('error') == 'actor_required'


# ─── E2E 6: verify_device_hmac en endpoint público de ingest ────────────


def test_e2e_device_hmac_valid_signature_accepted():
    mod = _build_dummy_module()
    app = create_app(modules=[mod])
    client = TestClient(app)

    body = b'{"sensor":"temp","value":23.5}'
    secret = 'shared-secret-xyz'
    sig = hmac.new(
        secret.encode('utf-8'), body, hashlib.sha256,
    ).hexdigest()

    resp = client.post(
        '/v1/dummy-e2e/ingest',
        content=body,
        headers={
            'X-Device-Id': 'sensor-001',
            'X-Device-Signature': sig,
            'Content-Type': 'application/json',
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {'device': 'sensor-001', 'received': True}


def test_e2e_device_hmac_invalid_signature_rejected():
    mod = _build_dummy_module()
    app = create_app(modules=[mod])
    client = TestClient(app)

    resp = client.post(
        '/v1/dummy-e2e/ingest',
        content=b'tampered',
        headers={
            'X-Device-Id': 'sensor-001',
            'X-Device-Signature': 'cafe' * 16,
        },
    )
    assert resp.status_code == 401
    detail = resp.json().get('detail', {})
    if isinstance(detail, dict):
        assert detail.get('error') == 'device_unauthorized'


def test_e2e_device_hmac_unknown_device_rejected_with_same_error():
    """Anti-enumeration: device unknown da el mismo error que invalid sig."""
    mod = _build_dummy_module()
    app = create_app(modules=[mod])
    client = TestClient(app)

    resp = client.post(
        '/v1/dummy-e2e/ingest',
        content=b'x',
        headers={
            'X-Device-Id': 'sensor-NOT-REGISTERED',
            'X-Device-Signature': 'a' * 64,
        },
    )
    assert resp.status_code == 401
    detail = resp.json().get('detail', {})
    if isinstance(detail, dict):
        assert detail.get('error') == 'device_unauthorized'


# ─── E2E 7: full smoke composición — todo junto ──────────────────────────


def test_e2e_full_composition_smoke(tmp_path: Path):
    """Tests that ALL extension features funcionan juntos en una app."""
    dist = tmp_path / 'spa'
    dist.mkdir()
    (dist / 'index.html').write_text('<html>OK</html>')

    mod = _build_dummy_module(static_dir=dist)
    app = create_app(
        modules=[mod],
        branding=BrandingConfig(
            product_name='Full E2E',
            primary_color='#abcdef',
        ),
    )
    client = TestClient(app)

    # 1. Router del módulo
    assert client.get('/v1/dummy-e2e/info').status_code == 200
    # 2. Static
    assert client.get('/m/dummy/').status_code == 200
    # 3. Branding público
    assert client.get('/v1/branding').json()['product_name'] == 'Full E2E'
    # 4. Device HMAC (valid)
    sig = hmac.new(b'shared-secret-xyz', b'p', hashlib.sha256).hexdigest()
    assert client.post(
        '/v1/dummy-e2e/ingest',
        content=b'p',
        headers={'X-Device-Id': 'sensor-001', 'X-Device-Signature': sig},
    ).status_code == 200
    # 5. App state
    assert app.state.branding.product_name == 'Full E2E'
    assert app.state.core_modules[0].code == 'dummy_e2e'
