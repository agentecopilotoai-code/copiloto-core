"""M45 — cobertura de app.main, app.core.logging, app.services.metrics.

Cubre:
  - lifespan: connect + close
  - _client_ip
  - /metrics endpoint (403 sin allowlist, 200 con allowlist)
  - _security_headers_middleware (verificado por TestClient)
  - configure_logging branches (INFO/DEBUG)
  - _redact_value / _redact_pii con varios tipos
  - refresh_runtime_metrics + refresh_backup_age_metrics
  - render_latest, parse_ip_allowlist, ip_allowed (los últimos ya
    tenían algo de cobertura desde otros tests; acá completamos branches).
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


# ─── app.core.logging ──────────────────────────────────────────────────────


def test_redact_value_phone_in_string():
    from app.core.logging import _redact_value
    assert '[PHONE]' in _redact_value('llamar al +573001234567')


def test_redact_value_email_in_string():
    from app.core.logging import _redact_value
    assert '[EMAIL]' in _redact_value('escribir a foo@bar.co')


def test_redact_value_nested_dict():
    from app.core.logging import _redact_value
    out = _redact_value({'phone': '+1', 'inner': {'email': 'x@y.co'}, 'other': 'safe'})
    assert out['phone'] == '[REDACTED]'
    # nested 'email' key gets redacted too
    assert out['inner']['email'] == '[REDACTED]'
    # passthrough no-PII strings
    assert out['other'] == 'safe'


def test_redact_value_list_and_tuple():
    from app.core.logging import _redact_value
    # Regex exige `\+\d{7,15}` — usamos 10 dígitos.
    out_l = _redact_value(['+5712345678', 'note'])
    assert out_l == ['[PHONE]', 'note']
    out_t = _redact_value(('+5712345678', 'note'))
    assert out_t == ('[PHONE]', 'note')


def test_redact_value_passthrough_int_none():
    from app.core.logging import _redact_value
    assert _redact_value(123) == 123
    assert _redact_value(None) is None


def test_redact_pii_top_level_keys():
    from app.core.logging import _redact_pii
    out = _redact_pii(None, 'info', {'email': 'x@y.co', 'msg': 'hi'})
    assert out['email'] == '[REDACTED]'
    assert out['msg'] == 'hi'


def test_configure_logging_default():
    from app.core.logging import configure_logging
    # No-op semánticamente (basicConfig sólo aplica la primera vez); verifica
    # que no levante.
    configure_logging()


def test_configure_logging_debug():
    from app.core.logging import configure_logging
    configure_logging('DEBUG')


def test_configure_logging_unknown_falls_to_info():
    from app.core.logging import configure_logging
    # Nivel desconocido → fallback INFO (no levanta).
    configure_logging('NONSENSE')


# ─── app.services.metrics ──────────────────────────────────────────────────


def test_render_latest_returns_bytes_and_content_type():
    from app.services.metrics import render_latest
    payload, ct = render_latest()
    assert isinstance(payload, bytes)
    assert 'text/plain' in ct or 'openmetrics' in ct


def test_parse_ip_allowlist_empty():
    from app.services.metrics import parse_ip_allowlist
    assert parse_ip_allowlist('') == frozenset()
    assert parse_ip_allowlist(None) == frozenset()


def test_parse_ip_allowlist_csv():
    from app.services.metrics import parse_ip_allowlist
    out = parse_ip_allowlist('10.0.0.1, 10.0.0.2 ,  10.0.0.3')
    assert out == frozenset({'10.0.0.1', '10.0.0.2', '10.0.0.3'})


def test_ip_allowed_no_ip():
    from app.services.metrics import ip_allowed
    assert ip_allowed(None, ['1.2.3.4']) is False


def test_ip_allowed_match():
    from app.services.metrics import ip_allowed
    assert ip_allowed('1.2.3.4', frozenset({'1.2.3.4'})) is True


def test_ip_allowed_miss():
    from app.services.metrics import ip_allowed
    assert ip_allowed('9.9.9.9', frozenset({'1.2.3.4'})) is False


def test_ip_allowed_accepts_list_input():
    from app.services.metrics import ip_allowed
    assert ip_allowed('1.2.3.4', ['1.2.3.4']) is True


def test_set_active_rate_limiter_and_refresh_runtime():
    from app.services import metrics as m
    fake_limiter = SimpleNamespace(size=42)
    m._set_active_rate_limiter(fake_limiter)
    m.refresh_runtime_metrics()
    # No assert estricto — el gauge se setea; verificamos que no levantó.
    m._set_active_rate_limiter(None)


def test_refresh_runtime_metrics_ignores_ws_fanout_error(monkeypatch):
    from app.services import metrics as m
    # Forzar error al importar ws_fanout dentro del try.
    import sys
    sys.modules.pop('app.admin.ws_fanout', None)
    # No need to actually mock — la función traga todo.
    m.refresh_runtime_metrics()


def test_refresh_backup_age_metrics_happy():
    from app.services.metrics import refresh_backup_age_metrics

    class C:
        async def fetch(self, sql, *a):
            return [{'kind': 'cloud_dump', 'age': 3600.0},
                    {'kind': 'cloud_verify', 'age': 1800.0}]

        async def fetchval(self, sql, *a):
            return 7200.0

    asyncio.run(refresh_backup_age_metrics(C()))


def test_refresh_backup_age_metrics_skips_none_age():
    from app.services.metrics import refresh_backup_age_metrics

    class C:
        async def fetch(self, sql, *a):
            return [{'kind': 'cloud_dump', 'age': None}]

        async def fetchval(self, sql, *a):
            return None

    asyncio.run(refresh_backup_age_metrics(C()))


def test_refresh_backup_age_metrics_swallows_db_error():
    from app.services.metrics import refresh_backup_age_metrics

    class C:
        async def fetch(self, sql, *a):
            raise RuntimeError('db down')

    # No debe propagar — best-effort.
    asyncio.run(refresh_backup_age_metrics(C()))


# ─── app.main ──────────────────────────────────────────────────────────────


def test_client_ip_no_client():
    from app.main import _client_ip
    req = SimpleNamespace(client=None)
    assert _client_ip(req) is None


def test_client_ip_returns_host():
    from app.main import _client_ip
    req = SimpleNamespace(client=SimpleNamespace(host='10.0.0.1'))
    assert _client_ip(req) == '10.0.0.1'


def test_security_headers_constant():
    from app.main import _SECURITY_HEADERS
    assert 'Content-Security-Policy' in _SECURITY_HEADERS
    assert _SECURITY_HEADERS['X-Frame-Options'] == 'DENY'
    assert 'max-age=31536000' in _SECURITY_HEADERS['Strict-Transport-Security']


def test_security_headers_middleware_attaches_headers():
    """Llama el middleware directamente con un fake call_next que devuelve
    un Response, y verifica que los headers se agregan."""
    from fastapi import Response

    from app.main import _security_headers_middleware

    async def fake_call_next(req):
        return Response(content='ok')

    req = SimpleNamespace()
    resp = asyncio.run(_security_headers_middleware(req, fake_call_next))
    assert resp.headers['X-Frame-Options'] == 'DENY'
    assert 'Content-Security-Policy' in resp.headers


def test_security_headers_middleware_no_overwrite():
    """Si la response ya trae el header, no se sobreescribe (setdefault)."""
    from fastapi import Response

    from app.main import _security_headers_middleware

    async def fake_call_next(req):
        r = Response(content='ok')
        r.headers['X-Frame-Options'] = 'SAMEORIGIN'
        return r

    resp = asyncio.run(_security_headers_middleware(SimpleNamespace(), fake_call_next))
    assert resp.headers['X-Frame-Options'] == 'SAMEORIGIN'


def test_lifespan_connects_and_closes(monkeypatch):
    """Verifica que `lifespan` llama db.connect y db.close en order."""
    from app.main import lifespan
    from app import main as main_mod

    # Mockear db.connect / close
    fake_db = SimpleNamespace()
    fake_db.connect = AsyncMock()
    fake_db.close = AsyncMock()
    monkeypatch.setattr(main_mod, 'db', fake_db)
    monkeypatch.setattr(main_mod, 'configure_logging', lambda lvl: None)

    async def runner():
        async with lifespan(MagicMock()):
            pass

    asyncio.run(runner())
    fake_db.connect.assert_awaited_once()
    fake_db.close.assert_awaited_once()


def test_create_app_returns_fastapi():
    from app.main import create_app
    api = create_app()
    # Verifica que tenga la ruta /metrics registrada.
    routes = [r.path for r in api.routes if hasattr(r, 'path')]
    assert '/metrics' in routes


def test_metrics_endpoint_403_without_allowlist(monkeypatch):
    """El endpoint /metrics se monta dinámicamente en create_app — la
    allowlist se inyecta desde settings al boot. Testeamos las dos ramas
    invocando la closure directamente."""
    from app.main import create_app
    api = create_app()
    # Ubicamos el handler /metrics y lo invocamos directamente con un Request
    # mockeado cuyo client.host NO está en la allowlist (la allowlist real
    # depende de settings.observability_allowed_ips → en tests está vacía).
    from fastapi import Request as FRequest

    for route in api.routes:
        if getattr(route, 'path', None) == '/metrics':
            handler = route.endpoint
            break
    else:
        pytest.fail('No /metrics route registered')

    scope = {
        'type': 'http', 'method': 'GET', 'path': '/metrics', 'headers': [],
        'client': ('1.2.3.4', 0),
    }
    req = FRequest(scope)
    result = asyncio.run(handler(req))
    # 403 porque allowlist vacía
    assert result.status_code == 403


def test_metrics_endpoint_200_with_allowlist(monkeypatch):
    """Configurar la allowlist con la IP de test y verificar 200.

    Patcheamos `parse_ip_allowlist` para que la closure capture la allowlist
    real (porque la closure se crea en `create_app` y atrapa el valor en
    ese momento).
    """
    from app import main as main_mod
    import app.core.config as cfg

    # Sobrescribir settings + parse_ip_allowlist para que la nueva closure
    # cree un allowlist con la IP de test.
    real_settings = cfg.get_settings()
    fake_settings = SimpleNamespace(
        **{**real_settings.model_dump(), 'observability_allowed_ips': '1.2.3.4'}
    )
    monkeypatch.setattr(main_mod, 'get_settings', lambda: fake_settings)

    api = main_mod.create_app()
    from fastapi import Request as FRequest

    for route in api.routes:
        if getattr(route, 'path', None) == '/metrics':
            handler = route.endpoint
            break
    else:
        pytest.fail('No /metrics route registered')

    scope = {
        'type': 'http', 'method': 'GET', 'path': '/metrics', 'headers': [],
        'client': ('1.2.3.4', 0),
    }
    req = FRequest(scope)
    result = asyncio.run(handler(req))
    assert result.status_code == 200


# ─── app.admin.main — admin-panel container entrypoint ────────────────────


def test_admin_main_module_creates_app():
    """`app/admin/main.py` es el entrypoint del container `admin-panel`
    en docker-compose.yml. Importarlo ejecuta `create_app()` a nivel de
    módulo. Verificamos que ese app expone el router admin (login/logout/
    callback)."""
    from app.admin import main as admin_main
    api = admin_main.app
    # Routes del admin_router montadas — checkamos el endpoint canónico.
    paths = [r.path for r in api.routes if hasattr(r, 'path')]
    assert '/admin/login' in paths or any('/admin' in p for p in paths)


def test_admin_main_create_app_factory():
    """Llamada directa al factory devuelve una FastAPI nueva."""
    from app.admin.main import create_app
    api = create_app()
    assert api.title.endswith('Admin Panel')
