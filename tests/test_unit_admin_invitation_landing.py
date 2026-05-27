"""Tests del BFF `GET /i/<token>` — landing page del email de invitación (M65).

Cubre los caminos:
  - Token mal-formado (no 64 hex chars) → 400 sin tocar el Core.
  - Core devuelve 404 → HTML "no encontrada" + status 404.
  - Core devuelve 200 con redeemed=False → HTML + cookie pending_invitation seteado.
  - Core devuelve 200 con redeemed=True → HTML "ya aceptaste" sin cookie.
  - Core unreachable → 502 con HTML "error temporal".

Strategy: monkeypatch `httpx.AsyncClient` para devolver responses
controladas sin pegarle al Core real.
"""
from __future__ import annotations


def _build_app():
    from fastapi import FastAPI
    from app.admin import routes

    app = FastAPI()
    app.include_router(routes.router)
    return app


def _client(app):
    from fastapi.testclient import TestClient
    return TestClient(app)


class _StubResponse:
    def __init__(self, status_code: int, json_body=None, text: str = ''):
        self.status_code = status_code
        self._json = json_body
        self.text = text or (str(json_body) if json_body is not None else '')

    def json(self):
        return self._json


class _StubAsyncClient:
    """Replacement de `httpx.AsyncClient` que devuelve responses pre-fijadas.
    Soporta `async with` y los métodos `get`/`post` que usa el BFF."""

    def __init__(self, *, get_response=None, post_response=None,
                 raise_on_get=None, raise_on_post=None):
        self._get_response = get_response
        self._post_response = post_response
        self._raise_on_get = raise_on_get
        self._raise_on_post = raise_on_post
        self.get_calls: list[tuple[str, dict]] = []
        self.post_calls: list[tuple[str, dict]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        if self._raise_on_get:
            raise self._raise_on_get
        return self._get_response

    async def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        if self._raise_on_post:
            raise self._raise_on_post
        return self._post_response


def _patch_async_client(monkeypatch, **kwargs):
    """Reemplaza `httpx.AsyncClient` (usado por el handler `/i/{token}`)."""
    from app.admin import routes
    stub = _StubAsyncClient(**kwargs)
    monkeypatch.setattr(
        routes.httpx, 'AsyncClient', lambda *a, **kw: stub,
    )
    return stub


# ─── /i/{token} — formato del token ──────────────────────────────────────


def test_landing_400_when_token_too_short():
    resp = _client(_build_app()).get('/i/abc123')
    assert resp.status_code == 400
    assert 'inválido' in resp.text.lower()


def test_landing_400_when_token_has_non_hex_chars():
    bad = 'g' * 64  # 'g' no es hex
    resp = _client(_build_app()).get(f'/i/{bad}')
    assert resp.status_code == 400


# ─── /i/{token} — Core responses ─────────────────────────────────────────


def test_landing_404_when_core_returns_404(monkeypatch):
    _patch_async_client(monkeypatch, get_response=_StubResponse(404, text='not found'))
    resp = _client(_build_app()).get(f'/i/{"a" * 64}')
    assert resp.status_code == 404
    assert 'no encontrada' in resp.text.lower()
    # No setea cookie pending.
    assert 'copilotoia_pending_invitation' not in resp.headers.get('set-cookie', '')


def test_landing_502_when_core_unreachable(monkeypatch):
    import httpx
    _patch_async_client(monkeypatch, raise_on_get=httpx.ConnectError('boom'))
    resp = _client(_build_app()).get(f'/i/{"a" * 64}')
    assert resp.status_code == 502
    assert 'error temporal' in resp.text.lower()


def test_landing_502_when_core_returns_unexpected_status(monkeypatch):
    _patch_async_client(monkeypatch, get_response=_StubResponse(500))
    resp = _client(_build_app()).get(f'/i/{"a" * 64}')
    assert resp.status_code == 502


def test_landing_200_when_valid_sets_pending_cookie(monkeypatch):
    """Flujo happy: invitación válida y pending → cookie + HTML con CTA login."""
    preview = {
        'invitation_id': 'inv-1', 'tenant_id': 't-1',
        'tenant_name': 'Acme Corp', 'role': 'admin',
        'email': 'invitee@example.com',
        'expires_at': '2027-01-01T00:00:00+00:00',
        'redeemed': False,
    }
    _patch_async_client(monkeypatch, get_response=_StubResponse(200, json_body=preview))
    resp = _client(_build_app()).get(f'/i/{"a" * 64}')
    assert resp.status_code == 200
    # HTML muestra el nombre del tenant + role + email.
    assert 'Acme Corp' in resp.text
    assert 'admin' in resp.text
    assert 'invitee@example.com' in resp.text
    # CTA al login.
    assert '/admin/login' in resp.text
    # Cookie pending_invitation seteada con el token.
    set_cookie = resp.headers.get('set-cookie', '')
    assert 'copilotoia_pending_invitation' in set_cookie
    assert 'a' * 64 in set_cookie
    assert 'samesite=lax' in set_cookie.lower()
    assert 'httponly' in set_cookie.lower()


def test_landing_200_when_already_redeemed_no_cookie(monkeypatch):
    preview = {
        'invitation_id': 'inv-1', 'tenant_id': 't-1',
        'tenant_name': 'Acme Corp', 'role': 'admin',
        'email': 'invitee@example.com',
        'expires_at': '2027-01-01T00:00:00+00:00',
        'redeemed': True,
    }
    _patch_async_client(monkeypatch, get_response=_StubResponse(200, json_body=preview))
    resp = _client(_build_app()).get(f'/i/{"a" * 64}')
    assert resp.status_code == 200
    assert 'ya aceptaste' in resp.text.lower()
    # No setea cookie — la invitación ya fue procesada.
    assert 'copilotoia_pending_invitation' not in resp.headers.get('set-cookie', '')


def test_landing_html_escapes_xss_in_tenant_name(monkeypatch):
    """Defense XSS: si tenant_name del Core trae chars HTML, NO deben
    renderizarse como HTML — `html.escape` los convierte a entidades."""
    preview = {
        'invitation_id': 'inv-1', 'tenant_id': 't-1',
        'tenant_name': '<script>alert(1)</script>',
        'role': 'admin',
        'email': 'invitee@example.com',
        'expires_at': '2027-01-01T00:00:00+00:00',
        'redeemed': False,
    }
    _patch_async_client(monkeypatch, get_response=_StubResponse(200, json_body=preview))
    resp = _client(_build_app()).get(f'/i/{"a" * 64}')
    assert resp.status_code == 200
    # Crudo NO presente:
    assert '<script>alert(1)</script>' not in resp.text
    # Encodeado SÍ:
    assert '&lt;script&gt;' in resp.text
