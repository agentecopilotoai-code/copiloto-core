"""Additional unit tests for `app/admin/routes.py` — push BFF coverage to ≥85%.

Targets the OAuth callback flow, admin_session/mfa_status endpoints, the core
API proxy and the WebSocket conversations stream — all of which are mocked
via TestClient + monkeypatched httpx so we don't need a live Auth0 or upstream
Core API.

These tests do NOT depend on RUN_E2E; they exercise the BFF in isolation by
constructing a minimal FastAPI app that mounts just the admin router.
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest


# ──────────────────────────── helpers ────────────────────────────────────


def _build_app():
    """Create a minimal FastAPI app with only the admin router mounted."""
    from fastapi import FastAPI
    from copiloto_core.admin import routes

    app = FastAPI()
    app.include_router(routes.router)
    return app


def _client(app):
    from fastapi.testclient import TestClient

    return TestClient(app)


def _make_session(*, expires_in=3600, profile=None) -> tuple[str, dict]:
    """Inject a fresh session into the in-memory store and return its id+payload.

    P0-3: usa el `session_store` API en vez de mutar `_sessions` directo.
    """
    import asyncio
    from copiloto_core.admin.session_store import get_session_store

    sid = f'sid-{uuid4().hex}'
    payload = {
        'access_token': 'tok-abc',
        'id_token': 'id-abc',
        'profile': profile if profile is not None else {
            'sub': 'auth0|u1',
            'name': 'User One',
            'email': 'u1@example.com',
            'picture': None,
            'tenant_id': None,
            'tenant_slug': None,
            'roles': [],
            'permissions': [],
            'support_mode': False,
            'mfa_verified': True,
        },
    }
    asyncio.run(get_session_store().set(sid, payload, expires_in))
    # Return payload con `expires_at` calculado (los tests legacy lo leen
    # del payload). El store ya lo setea internamente.
    payload['expires_at'] = time.time() + expires_in
    return sid, payload


# Mock httpx.AsyncClient for the OAuth callback + core proxy paths.
class _FakeResp:
    def __init__(self, *, status_code=200, json_payload=None, text='', headers=None, content=b''):
        self.status_code = status_code
        self._payload = json_payload
        self.text = text
        self.content = content if content else (json.dumps(json_payload).encode() if json_payload else b'')

        # httpx.Headers supports get_list; use a SimpleNamespace mimic
        class _Headers:
            def __init__(self, src):
                self._d = src or {}

            def get(self, key, default=None):
                # case-insensitive lookup
                for k, v in self._d.items():
                    if k.lower() == key.lower():
                        if isinstance(v, list):
                            return v[0] if v else default
                        return v
                return default

            def get_list(self, key):
                for k, v in self._d.items():
                    if k.lower() == key.lower():
                        if isinstance(v, list):
                            return v
                        return [v]
                return []

        self.headers = _Headers(headers or {})

    def json(self):
        return self._payload

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            req = httpx.Request('GET', 'http://test')
            resp = httpx.Response(self.status_code, request=req)
            raise httpx.HTTPStatusError('bad', request=req, response=resp)


class _FakeFlow:
    """Sequenced fake responses for httpx.AsyncClient."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, **kw):
        flow = self

        class _C:
            async def __aenter__(self_):
                return self_

            async def __aexit__(self_, *a):
                return False

            async def post(self_, url, json=None, headers=None, **kw):
                flow.calls.append({'method': 'POST', 'url': url, 'json': json})
                return flow._next()

            async def get(self_, url, headers=None, **kw):
                flow.calls.append({'method': 'GET', 'url': url})
                return flow._next()

            async def request(self_, method, url, headers=None, content=None, **kw):
                flow.calls.append({'method': method, 'url': url})
                return flow._next()

        return _C()

    def _next(self):
        if not self._responses:
            raise AssertionError('no more mock responses')
        return self._responses.pop(0)


def _patch_httpx(monkeypatch, responses):
    flow = _FakeFlow(responses)
    monkeypatch.setattr(httpx, 'AsyncClient', flow)
    return flow


# ─────────────────────── _session_mfa_required ──────────────────────────


def test_session_mfa_required_disabled_when_mfa_off(monkeypatch):
    from copiloto_core.admin import routes
    fake_settings = SimpleNamespace(
        mfa_enforcement_enabled=False,
        auth0_domain='example.auth0.com',
        auth0_issuer=None,
        auth0_audience='aud',
        auth0_claims_namespace='https://copilotoia.com/claims/',
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    session = {'profile': {'roles': ['admin'], 'mfa_verified': False}}
    assert routes._session_mfa_required(session) is False


def test_session_mfa_required_disabled_when_no_auth0(monkeypatch):
    from copiloto_core.admin import routes
    fake_settings = SimpleNamespace(
        mfa_enforcement_enabled=True,
        auth0_domain=None,
        auth0_audience='aud',
        auth0_claims_namespace='https://copilotoia.com/claims/',
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    session = {'profile': {'roles': ['admin'], 'mfa_verified': False}}
    assert routes._session_mfa_required(session) is False


def test_session_mfa_required_disabled_when_not_privileged(monkeypatch):
    from copiloto_core.admin import routes
    fake_settings = SimpleNamespace(
        mfa_enforcement_enabled=True,
        auth0_domain='x.auth0.com',
        auth0_issuer=None,
        auth0_audience='aud',
        auth0_claims_namespace='https://copilotoia.com/claims/',
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    session = {'profile': {'roles': ['agent'], 'mfa_verified': False}}
    assert routes._session_mfa_required(session) is False


def test_session_mfa_required_true_when_privileged_no_mfa(monkeypatch):
    from copiloto_core.admin import routes
    fake_settings = SimpleNamespace(
        mfa_enforcement_enabled=True,
        auth0_domain='x.auth0.com',
        auth0_issuer=None,
        auth0_audience='aud',
        auth0_claims_namespace='https://copilotoia.com/claims/',
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    session = {'profile': {'roles': ['admin'], 'mfa_verified': False}}
    assert routes._session_mfa_required(session) is True


def test_session_mfa_required_false_when_privileged_with_mfa(monkeypatch):
    from copiloto_core.admin import routes
    fake_settings = SimpleNamespace(
        mfa_enforcement_enabled=True,
        auth0_domain='x.auth0.com',
        auth0_issuer=None,
        auth0_audience='aud',
        auth0_claims_namespace='https://copilotoia.com/claims/',
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    session = {'profile': {'roles': ['owner'], 'mfa_verified': True}}
    assert routes._session_mfa_required(session) is False


# ─────────────────────── /admin/api/session ──────────────────────────────


def test_admin_session_401_when_no_cookie():
    app = _build_app()
    with _client(app) as c:
        r = c.get('/admin/api/session')
        assert r.status_code == 401


def test_admin_session_200_when_active():
    from copiloto_core.admin.routes import SESSION_COOKIE
    sid, _ = _make_session(profile={'roles': ['admin'], 'mfa_verified': True, 'sub': 'u|1'})
    app = _build_app()
    with _client(app) as c:
        c.cookies.set(SESSION_COOKIE, sid)
        r = c.get('/admin/api/session')
        assert r.status_code == 200
        body = r.json()
        assert body['authenticated'] is True
        assert body['profile']['sub'] == 'u|1'
        assert 'api' in body
        assert 'modules' in body


# ─────────────────────── /admin/api/mfa-status ───────────────────────────


# M42 — tests para `/admin/api/mfa-status` borrados: el endpoint se
# eliminó del BFF cuando el único caller (`MfaRequiredBlocker.jsx`) fue
# purgado durante la limpieza del branch core. Su 404 actual lo cubre el
# behavior por defecto de FastAPI; no necesita test dedicado.


# ─────────────────────── /admin/login ────────────────────────────────────


def test_admin_login_redirects_when_session_active():
    from copiloto_core.admin.routes import SESSION_COOKIE
    sid, _ = _make_session()
    app = _build_app()
    with _client(app) as c:
        c.cookies.set(SESSION_COOKIE, sid)
        r = c.get('/admin/login', follow_redirects=False)
        # When already logged in → 303 redirect to /admin/
        assert r.status_code in (302, 303, 307)


def test_admin_login_503_when_unconfigured(monkeypatch):
    from copiloto_core.admin import routes
    fake_settings = SimpleNamespace(
        auth0_domain='x.auth0.com',
        auth0_issuer=None,
        auth0_admin_client_id=None,
        auth0_audience=None,
        auth0_callback_urls='http://localhost:3000/callback',
        auth0_logout_urls='http://localhost:3000/admin/',
        auth0_web_origins='http://localhost:3000',
        auth0_claims_namespace='https://copilotoia.com/claims/',
        admin_session_secret='secret-min-length-16-chars',
        jwt_secret='secret-min-length-16-chars',
        admin_core_api_base_url='http://127.0.0.1:8000',
        mfa_enforcement_enabled=False,
        state_secret='secret-min-length-16-chars',
        cookies_secure=False,
        app_env='local',
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    app = _build_app()
    with _client(app) as c:
        r = c.get('/admin/login', follow_redirects=False)
        # No client_id → 503
        assert r.status_code == 503


def test_admin_login_redirects_to_auth0(monkeypatch):
    from copiloto_core.admin import routes
    fake_settings = SimpleNamespace(
        auth0_domain='x.auth0.com',
        auth0_issuer=None,
        auth0_admin_client_id='client-id-min-length-16',
        auth0_audience='aud',
        auth0_callback_urls='http://localhost:3000/callback',
        auth0_logout_urls='http://localhost:3000/admin/',
        auth0_web_origins='http://localhost:3000',
        auth0_claims_namespace='https://copilotoia.com/claims/',
        admin_session_secret='secret-min-length-32-chars-long-enough',
        jwt_secret='secret-min-length-16-chars',
        admin_core_api_base_url='http://127.0.0.1:8000',
        mfa_enforcement_enabled=False,
        state_secret='secret-min-length-32-chars-long-enough',
        cookies_secure=False,
        app_env='local',
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    app = _build_app()
    with _client(app) as c:
        r = c.get('/admin/login', follow_redirects=False)
        assert r.status_code in (302, 307)
        assert 'x.auth0.com/authorize' in r.headers['location']


# ─────────────────────── /admin/callback ─────────────────────────────────


def _make_id_token(claims):
    """Build a fake JWT with the claims payload (header+payload+sig, no real sig).

    Pairs with `_stub_id_token_decode` which makes the BFF accept it by
    bypassing JWT signature verification.
    """
    header = base64.urlsafe_b64encode(b'{"alg":"HS256","typ":"JWT"}').rstrip(b'=').decode()
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b'=').decode()
    return f'{header}.{payload}.sig'


def _stub_id_token_decode(monkeypatch):
    """Bypass `decode_auth0_id_token` in the BFF so `_make_id_token` works."""
    from copiloto_core.admin import routes as admin_routes  # noqa: PLC0415
    async def fake_decode(token, **kwargs):
        # `_make_id_token` builds `header.payload.sig`; extract payload b64.
        import base64 as b64  # noqa: PLC0415
        import json as j  # noqa: PLC0415
        payload = token.split('.')[1]
        padding = '=' * (-len(payload) % 4)
        return j.loads(b64.urlsafe_b64decode(payload + padding))
    monkeypatch.setattr(admin_routes, 'decode_auth0_id_token', fake_decode)


def test_admin_callback_with_error_param():
    """M56 — los errores del callback ya NO devuelven 400 JSON. Redirigen
    303 a `/admin/?login_error=<reason>` para que el SPA muestre un
    banner explicativo + el botón "Iniciar sesión" para reintentar."""
    app = _build_app()
    with _client(app) as c:
        r = c.get('/admin/callback?error=access_denied&error_description=user_cancel',
                  follow_redirects=False)
        assert r.status_code == 303
        assert 'login_error=auth0_access_denied' in r.headers['location']


def test_admin_callback_missing_code():
    """M56 — sin code/state → redirect 303 con login_error=missing_params."""
    app = _build_app()
    with _client(app) as c:
        r = c.get('/admin/callback?state=anything', follow_redirects=False)
        assert r.status_code == 303
        assert 'login_error=missing_params' in r.headers['location']


def test_admin_callback_invalid_state():
    """M56 — state cookie missing → redirect con login_error=state_missing."""
    app = _build_app()
    with _client(app) as c:
        r = c.get('/admin/callback?code=ok&state=does_not_match',
                  follow_redirects=False)
        assert r.status_code == 303
        assert 'login_error=state_missing' in r.headers['location']


def test_admin_callback_happy_path(monkeypatch):
    """Full OAuth callback flow with mocked Auth0."""
    from copiloto_core.admin import routes
    fake_settings = SimpleNamespace(
        auth0_domain='x.auth0.com',
        auth0_issuer=None,
        auth0_admin_client_id='client-id-min-length-16',
        auth0_admin_client_secret='client-secret-min-length-16',
        auth0_admin_client_secret_file=None,
        auth0_audience='aud',
        auth0_callback_urls='http://localhost:3000/callback',
        auth0_logout_urls='http://localhost:3000/admin/',
        auth0_web_origins='http://localhost:3000',
        auth0_claims_namespace='https://copilotoia.com/claims/',
        admin_session_secret='secret-min-length-32-chars-long-enough',
        jwt_secret='secret-min-length-16-chars',
        admin_core_api_base_url='http://127.0.0.1:8000',
        mfa_enforcement_enabled=False,
        state_secret='secret-min-length-32-chars-long-enough',
        cookies_secure=False,
        app_env='local',
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)

    # Build a valid state cookie
    state = 'random-state-value'
    state_cookie = routes._pack_state({
        'state': state, 'nonce': 'nonce-1', 'created_at': int(time.time())
    })

    # Mock httpx responses: token exchange + userinfo
    _stub_id_token_decode(monkeypatch)
    id_token = _make_id_token({
        'sub': 'auth0|abc',
        'amr': ['mfa'],
        'https://copilotoia.com/claims/tenant_id': str(uuid4()),
        'https://copilotoia.com/claims/roles': ['admin'],
        'https://copilotoia.com/claims/permissions': ['read'],
        'https://copilotoia.com/claims/support_mode': False,
    })
    _patch_httpx(monkeypatch, [
        _FakeResp(status_code=200, json_payload={
            'access_token': 'access-token-abc',
            'id_token': id_token,
        }),
        _FakeResp(status_code=200, json_payload={
            'sub': 'auth0|abc',
            'email': 'abc@example.com',
            'name': 'Alice',
            'picture': 'http://x/img.png',
        }),
    ])

    app = _build_app()
    with _client(app) as c:
        c.cookies.set(routes.STATE_COOKIE, state_cookie)
        r = c.get(f'/admin/callback?code=fake-code&state={state}', follow_redirects=False)
        assert r.status_code in (302, 307)
        assert routes.SESSION_COOKIE in r.cookies or 'set-cookie' in (k.lower() for k in r.headers.keys())


def test_admin_callback_token_exchange_fails(monkeypatch):
    from copiloto_core.admin import routes
    fake_settings = SimpleNamespace(
        auth0_domain='x.auth0.com',
        auth0_issuer=None,
        auth0_admin_client_id='client-id-min-length-16',
        auth0_admin_client_secret='client-secret-min-length-16',
        auth0_admin_client_secret_file=None,
        auth0_audience='aud',
        auth0_callback_urls='http://localhost:3000/callback',
        auth0_logout_urls='http://localhost:3000/admin/',
        auth0_web_origins='http://localhost:3000',
        auth0_claims_namespace='https://copilotoia.com/claims/',
        admin_session_secret='secret-min-length-32-chars-long-enough',
        jwt_secret='secret-min-length-16-chars',
        admin_core_api_base_url='http://127.0.0.1:8000',
        mfa_enforcement_enabled=False,
        state_secret='secret-min-length-32-chars-long-enough',
        cookies_secure=False,
        app_env='local',
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    state = 'state-1'
    state_cookie = routes._pack_state({'state': state, 'nonce': 'n', 'created_at': int(time.time())})

    _patch_httpx(monkeypatch, [
        _FakeResp(status_code=401, json_payload={'error': 'invalid_grant'}),
    ])
    app = _build_app()
    with _client(app) as c:
        c.cookies.set(routes.STATE_COOKIE, state_cookie)
        r = c.get(f'/admin/callback?code=bad&state={state}', follow_redirects=False)
        assert r.status_code == 401


def test_admin_callback_userinfo_fails(monkeypatch):
    from copiloto_core.admin import routes
    fake_settings = SimpleNamespace(
        auth0_domain='x.auth0.com',
        auth0_issuer=None,
        auth0_admin_client_id='client-id-min-length-16',
        auth0_admin_client_secret='client-secret-min-length-16',
        auth0_admin_client_secret_file=None,
        auth0_audience='aud',
        auth0_callback_urls='http://localhost:3000/callback',
        auth0_logout_urls='http://localhost:3000/admin/',
        auth0_web_origins='http://localhost:3000',
        auth0_claims_namespace='https://copilotoia.com/claims/',
        admin_session_secret='secret-min-length-32-chars-long-enough',
        jwt_secret='secret-min-length-16-chars',
        admin_core_api_base_url='http://127.0.0.1:8000',
        mfa_enforcement_enabled=False,
        state_secret='secret-min-length-32-chars-long-enough',
        cookies_secure=False,
        app_env='local',
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    state = 'state-2'
    state_cookie = routes._pack_state({'state': state, 'nonce': 'n', 'created_at': int(time.time())})

    _patch_httpx(monkeypatch, [
        _FakeResp(status_code=200, json_payload={
            'access_token': 'tok',
            'id_token': _make_id_token({'sub': 'auth0|x'}),
        }),
        _FakeResp(status_code=403, json_payload={'error': 'forbidden'}),
    ])
    app = _build_app()
    with _client(app) as c:
        c.cookies.set(routes.STATE_COOKIE, state_cookie)
        r = c.get(f'/admin/callback?code=ok&state={state}', follow_redirects=False)
        assert r.status_code == 401


def test_admin_callback_expired_state():
    """M56 — state.created_at older than 600s → redirect 303 con
    login_error=state_expired. Antes era 400 JSON crudo."""
    from copiloto_core.admin import routes
    state = 'state-3'
    state_cookie = routes._pack_state({
        'state': state, 'nonce': 'n', 'created_at': int(time.time()) - 3600
    })
    app = _build_app()
    with _client(app) as c:
        c.cookies.set(routes.STATE_COOKIE, state_cookie)
        r = c.get(f'/admin/callback?code=c&state={state}', follow_redirects=False)
        assert r.status_code == 303
        assert 'login_error=state_expired' in r.headers['location']


def test_admin_callback_state_mismatch():
    """M56 — cookie state≠URL state (user abrió varias pestañas) → 303
    con login_error=state_mismatch."""
    from copiloto_core.admin import routes
    cookie_state = 'state-from-tab-A'
    state_cookie = routes._pack_state({
        'state': cookie_state, 'nonce': 'n', 'created_at': int(time.time()),
    })
    app = _build_app()
    with _client(app) as c:
        c.cookies.set(routes.STATE_COOKIE, state_cookie)
        # Llega state diferente (de otra pestaña).
        r = c.get('/admin/callback?code=c&state=state-from-tab-B',
                  follow_redirects=False)
        assert r.status_code == 303
        assert 'login_error=state_mismatch' in r.headers['location']


def test_admin_callback_amr_as_string(monkeypatch):
    """amr returned as a string instead of a list — coerced to list."""
    from copiloto_core.admin import routes
    fake_settings = SimpleNamespace(
        auth0_domain='x.auth0.com',
        auth0_issuer=None,
        auth0_admin_client_id='client-id-min-length-16',
        auth0_admin_client_secret='client-secret-min-length-16',
        auth0_admin_client_secret_file=None,
        auth0_audience='aud',
        auth0_callback_urls='http://localhost:3000/callback',
        auth0_logout_urls='http://localhost:3000/admin/',
        auth0_web_origins='http://localhost:3000',
        auth0_claims_namespace='https://copilotoia.com/claims/',
        admin_session_secret='secret-min-length-32-chars-long-enough',
        jwt_secret='secret-min-length-16-chars',
        admin_core_api_base_url='http://127.0.0.1:8000',
        mfa_enforcement_enabled=False,
        state_secret='secret-min-length-32-chars-long-enough',
        cookies_secure=False,
        app_env='local',
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    state = 'state-amr'
    state_cookie = routes._pack_state({'state': state, 'nonce': 'n', 'created_at': int(time.time())})

    _stub_id_token_decode(monkeypatch)
    id_token = _make_id_token({
        'sub': 'auth0|y',
        'amr': 'mfa',  # string form
    })
    _patch_httpx(monkeypatch, [
        _FakeResp(status_code=200, json_payload={'access_token': 't', 'id_token': id_token}),
        _FakeResp(status_code=200, json_payload={'sub': 'auth0|y', 'email': 'y@y.com'}),
    ])
    app = _build_app()
    with _client(app) as c:
        c.cookies.set(routes.STATE_COOKIE, state_cookie)
        r = c.get(f'/admin/callback?code=ok&state={state}', follow_redirects=False)
        assert r.status_code in (302, 307)


# ─────────────────────── /admin/logout ───────────────────────────────────


def test_admin_logout_clears_cookie_and_redirects(monkeypatch):
    from copiloto_core.admin import routes
    fake_settings = SimpleNamespace(
        auth0_domain='x.auth0.com',
        auth0_issuer=None,
        auth0_admin_client_id='client-id-min-length-16',
        auth0_admin_client_secret='client-secret-min-length-16',
        auth0_admin_client_secret_file=None,
        auth0_audience='aud',
        auth0_callback_urls='http://localhost:3000/callback',
        auth0_logout_urls='http://localhost:3000/admin/',
        auth0_web_origins='http://localhost:3000',
        auth0_claims_namespace='https://copilotoia.com/claims/',
        admin_session_secret='secret-min-length-32-chars-long-enough',
        jwt_secret='secret-min-length-16-chars',
        admin_core_api_base_url='http://127.0.0.1:8000',
        mfa_enforcement_enabled=False,
        state_secret='secret-min-length-32-chars-long-enough',
        cookies_secure=False,
        app_env='local',
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)

    sid, _ = _make_session()
    app = _build_app()
    with _client(app) as c:
        c.cookies.set(routes.SESSION_COOKIE, sid)
        r = c.post('/admin/logout', headers={'x-requested-with': 'fetch'}, follow_redirects=False)
        assert r.status_code == 303
        # Session should be removed (P0-3: via store API).
        from copiloto_core.admin.session_store import get_session_store
        assert asyncio.run(get_session_store().get(sid)) is None


def test_admin_logout_no_session_still_works(monkeypatch):
    """Logout when no session — falls back to /admin/."""
    from copiloto_core.admin import routes
    fake_settings = SimpleNamespace(
        auth0_domain=None,
        auth0_admin_client_id=None,
        auth0_admin_client_secret=None,
        auth0_admin_client_secret_file=None,
        auth0_audience='aud',
        auth0_callback_urls='http://localhost:3000/callback',
        auth0_logout_urls='',
        auth0_web_origins='',
        auth0_claims_namespace='https://copilotoia.com/claims/',
        admin_session_secret='secret-min-length-32-chars-long-enough',
        jwt_secret='secret-min-length-16-chars',
        admin_core_api_base_url='http://127.0.0.1:8000',
        mfa_enforcement_enabled=False,
        state_secret='secret-min-length-32-chars-long-enough',
        cookies_secure=False,
        app_env='local',
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    app = _build_app()
    with _client(app) as c:
        r = c.post('/admin/logout', headers={'x-requested-with': 'fetch'}, follow_redirects=False)
        assert r.status_code == 303


# ─────────────────────── /admin/api/core proxy ───────────────────────────


def test_admin_core_api_proxy_no_session():
    app = _build_app()
    with _client(app) as c:
        r = c.get('/admin/api/core/v1/foo')
        assert r.status_code == 401


def test_admin_core_api_proxy_mfa_required(monkeypatch):
    from copiloto_core.admin import routes
    fake_settings = SimpleNamespace(
        mfa_enforcement_enabled=True,
        auth0_domain='x.auth0.com',
        auth0_issuer=None,
        auth0_audience='aud',
        auth0_claims_namespace='https://copilotoia.com/claims/',
        admin_core_api_base_url='http://127.0.0.1:8000',
        jwt_secret='secret-min-length-16-chars',
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    sid, _ = _make_session(profile={'roles': ['admin'], 'mfa_verified': False})
    app = _build_app()
    with _client(app) as c:
        c.cookies.set(routes.SESSION_COOKIE, sid)
        r = c.get('/admin/api/core/v1/anything')
        assert r.status_code == 403
        assert r.json()['detail'] == 'mfa_required'


def test_admin_core_api_proxy_happy_path(monkeypatch):
    from copiloto_core.admin import routes
    fake_settings = SimpleNamespace(
        mfa_enforcement_enabled=False,
        auth0_domain=None,
        auth0_audience='aud',
        auth0_claims_namespace='https://copilotoia.com/claims/',
        admin_core_api_base_url='http://127.0.0.1:8000',
        jwt_secret='secret-min-length-16-chars',
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    # _core_api_headers does `from copiloto_core.core.config import get_settings` to build
    # the X-Admin-Identity HMAC when sub+email are present. In CI the global
    # Settings() can't initialize (missing env). Patch at source.
    import copiloto_core.core.config as _core_config
    monkeypatch.setattr(
        _core_config,
        'get_settings',
        lambda: SimpleNamespace(jwt_secret='secret-min-length-16-chars'),
    )
    sid, _ = _make_session(profile={
        'sub': 'u|1', 'email': 'u@x.com', 'roles': ['admin'], 'mfa_verified': True,
    })

    # Mock upstream Core API: returns 200 + JSON + set-cookie header
    _patch_httpx(monkeypatch, [
        _FakeResp(
            status_code=200,
            json_payload={'ok': True},
            content=b'{"ok":true}',
            headers={
                'content-type': 'application/json',
                'set-cookie': ['copilotoia_support_mode=v; Path=/', 'other=v2; Path=/'],
            },
        ),
    ])
    app = _build_app()
    with _client(app) as c:
        c.cookies.set(routes.SESSION_COOKIE, sid)
        r = c.get('/admin/api/core/v1/users?page=1')
        assert r.status_code == 200
        assert r.json() == {'ok': True}


def test_admin_core_api_proxy_upstream_error(monkeypatch):
    from copiloto_core.admin import routes
    fake_settings = SimpleNamespace(
        mfa_enforcement_enabled=False,
        auth0_domain=None,
        auth0_audience='aud',
        auth0_claims_namespace='https://copilotoia.com/claims/',
        admin_core_api_base_url='http://127.0.0.1:8000',
        jwt_secret='secret-min-length-16-chars',
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    # _core_api_headers does `from copiloto_core.core.config import get_settings` to build
    # the X-Admin-Identity HMAC when sub+email are present. In CI the global
    # Settings() can't initialize (missing env). Patch at source.
    import copiloto_core.core.config as _core_config
    monkeypatch.setattr(
        _core_config,
        'get_settings',
        lambda: SimpleNamespace(jwt_secret='secret-min-length-16-chars'),
    )
    sid, _ = _make_session(profile={'sub': 'u|1', 'email': 'u@x.com', 'roles': ['admin'], 'mfa_verified': True})

    class _BrokenClient:
        def __call__(self, **kw):
            class _C:
                async def __aenter__(self_):
                    return self_

                async def __aexit__(self_, *a):
                    return False

                async def request(self_, method, url, content=None, headers=None, **kw):
                    raise httpx.ConnectError('upstream unreachable', request=httpx.Request(method, url))

            return _C()

    monkeypatch.setattr(httpx, 'AsyncClient', _BrokenClient())
    app = _build_app()
    with _client(app) as c:
        c.cookies.set(routes.SESSION_COOKIE, sid)
        r = c.get('/admin/api/core/v1/foo')
        assert r.status_code == 502


def test_admin_core_api_proxy_upstream_401_expired_purges_session(monkeypatch):
    """B-002: si upstream devuelve 401 con detail típico de token expirado
    (e.g. 'Expired token', 'Session has been revoked'), el proxy purga la
    sesión local + delete-cookie + devuelve session_expired al SPA."""
    from copiloto_core.admin import routes
    fake_settings = SimpleNamespace(
        mfa_enforcement_enabled=False,
        auth0_domain=None,
        auth0_audience='aud',
        auth0_claims_namespace='https://copilotoia.com/claims/',
        admin_core_api_base_url='http://127.0.0.1:8000',
        jwt_secret='secret-min-length-16-chars',
        cookies_secure=False,
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    import copiloto_core.core.config as _core_config
    monkeypatch.setattr(
        _core_config, 'get_settings',
        lambda: SimpleNamespace(jwt_secret='secret-min-length-16-chars'),
    )
    sid, _ = _make_session(profile={
        'sub': 'u|1', 'email': 'u@x.com', 'roles': ['admin'],
        'mfa_verified': True,
    })
    from copiloto_core.admin.session_store import get_session_store
    assert asyncio.run(get_session_store().get(sid)) is not None

    # Upstream Core responde 401 'Expired token' (lo que jose tira post-A-002).
    _patch_httpx(monkeypatch, [
        _FakeResp(
            status_code=401,
            json_payload={'detail': 'Expired token'},
            content=b'{"detail":"Expired token"}',
            headers={'content-type': 'application/json'},
        ),
    ])
    app = _build_app()
    with _client(app) as c:
        c.cookies.set(routes.SESSION_COOKIE, sid)
        r = c.get('/admin/api/core/v1/users')
        assert r.status_code == 401
        body = r.json()
        # B-002: respuesta enriquecida — el SPA puede actuar específico.
        assert body['reason'] == 'token_expired'
        assert 'session_expired' in body['detail']
    # La sesión fue purgada del store (P0-3 via session_store API).
    assert asyncio.run(get_session_store().get(sid)) is None


def test_admin_core_api_proxy_upstream_401_other_preserved(monkeypatch):
    """B-002: 401 con detail genérico (no expired/revoked) NO purga la
    sesión — puede ser un permisos issue, no expiración. Pasamos el 401
    al SPA tal cual."""
    from copiloto_core.admin import routes
    fake_settings = SimpleNamespace(
        mfa_enforcement_enabled=False,
        auth0_domain=None,
        auth0_audience='aud',
        auth0_claims_namespace='https://copilotoia.com/claims/',
        admin_core_api_base_url='http://127.0.0.1:8000',
        jwt_secret='secret-min-length-16-chars',
        cookies_secure=False,
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    import copiloto_core.core.config as _core_config
    monkeypatch.setattr(
        _core_config, 'get_settings',
        lambda: SimpleNamespace(jwt_secret='secret-min-length-16-chars'),
    )
    sid, _ = _make_session(profile={
        'sub': 'u|1', 'email': 'u@x.com', 'roles': ['admin'],
        'mfa_verified': True,
    })

    _patch_httpx(monkeypatch, [
        _FakeResp(
            status_code=401,
            json_payload={'detail': 'Authentication required'},
            content=b'{"detail":"Authentication required"}',
            headers={'content-type': 'application/json'},
        ),
    ])
    app = _build_app()
    with _client(app) as c:
        c.cookies.set(routes.SESSION_COOKIE, sid)
        r = c.get('/admin/api/core/v1/foo')
        assert r.status_code == 401
        # Detail tal cual del upstream — no marcado como expired.
        assert r.json() == {'detail': 'Authentication required'}
    # Sesión preservada (P0-3 via session_store API).
    from copiloto_core.admin.session_store import get_session_store
    assert asyncio.run(get_session_store().get(sid)) is not None


def test_admin_callback_uses_expires_in_from_token_response(monkeypatch):
    """B-002: el TTL del cookie + session viene del access_token Auth0
    (`expires_in`), no del hardcoded 8h previo."""
    from copiloto_core.admin import routes
    fake_settings = SimpleNamespace(
        mfa_enforcement_enabled=False,
        auth0_domain='t.auth0.com',
        auth0_admin_client_id='client-x',
        auth0_admin_client_secret_file=None,
        auth0_audience='aud',
        auth0_issuer=None,
        auth0_claims_namespace='https://copilotoia.com/claims/',
        auth0_callback_urls='http://localhost:3000/callback,http://testserver/callback',
        admin_core_api_base_url='http://127.0.0.1:8000',
        jwt_secret='secret-min-length-16-chars',
        state_secret='state-secret-min-16-chars',
        cookies_secure=False,
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    monkeypatch.setattr(routes, '_admin_client_secret', lambda: 'sec')
    _stub_id_token_decode(monkeypatch)

    import time as _t
    state = 'state-' + 'x' * 20
    state_cookie = routes._pack_state({
        'state': state, 'nonce': 'n', 'created_at': int(_t.time()),
    })
    id_token = _make_id_token({'sub': 'auth0|x', 'email': 'x@y.co', 'nonce': 'n'})

    _patch_httpx(monkeypatch, [
        # /oauth/token — el response trae expires_in custom (e.g. 3600 = 1h).
        _FakeResp(status_code=200, json_payload={
            'access_token': 'at-x', 'id_token': id_token,
            'refresh_token': 'rt-x', 'expires_in': 3600,
        }, content=b'{}'),
        # /userinfo
        _FakeResp(status_code=200, json_payload={
            'sub': 'auth0|x', 'email': 'x@y.co',
        }, content=b'{}'),
    ])
    app = _build_app()
    with _client(app) as c:
        c.cookies.set(routes.STATE_COOKIE, state_cookie)
        r = c.get(f'/callback?code=abc&state={state}', follow_redirects=False)
    assert r.status_code in (302, 303, 307)
    # La sesión nueva fue creada con expires_at ≈ now + 3600.
    # P0-3: usamos el _raw del InMemoryStore para iterar (tests-only).
    from copiloto_core.admin.session_store import InMemorySessionStore, get_session_store
    store = get_session_store()
    assert isinstance(store, InMemorySessionStore)  # test fixture lo garantiza
    raw = store._raw  # noqa: SLF001
    sids = [k for k, v in raw.items() if v.get('profile', {}).get('sub') == 'auth0|x']
    assert sids, 'sesión nueva no creada'
    sess = raw[sids[-1]]
    delta = sess['expires_at'] - _t.time()
    assert 3500 < delta < 3700  # ~1h (con margen)
    # refresh_token guardado.
    assert sess['refresh_token'] == 'rt-x'


def test_admin_core_api_proxy_post_with_body(monkeypatch):
    from copiloto_core.admin import routes
    fake_settings = SimpleNamespace(
        mfa_enforcement_enabled=False,
        auth0_domain=None,
        auth0_audience='aud',
        auth0_claims_namespace='https://copilotoia.com/claims/',
        admin_core_api_base_url='http://127.0.0.1:8000',
        jwt_secret='secret-min-length-16-chars',
    )
    monkeypatch.setattr(routes, 'get_admin_settings', lambda: fake_settings)
    # _core_api_headers does `from copiloto_core.core.config import get_settings` to build
    # the X-Admin-Identity HMAC when sub+email are present. In CI the global
    # Settings() can't initialize (missing env). Patch at source.
    import copiloto_core.core.config as _core_config
    monkeypatch.setattr(
        _core_config,
        'get_settings',
        lambda: SimpleNamespace(jwt_secret='secret-min-length-16-chars'),
    )
    sid, _ = _make_session(profile={'sub': 'u|1', 'email': 'u@x.com', 'roles': ['admin'], 'mfa_verified': True})

    _patch_httpx(monkeypatch, [
        _FakeResp(status_code=201, json_payload={'id': 'x'}, content=b'{"id":"x"}',
                  headers={'content-type': 'application/json'}),
    ])
    app = _build_app()
    with _client(app) as c:
        c.cookies.set(routes.SESSION_COOKIE, sid)
        r = c.post('/admin/api/core/v1/items', json={'name': 'x'}, headers={'x-requested-with': 'fetch'})
        assert r.status_code == 201


# ─────────────────────── WebSocket conversations stream ──────────────────


def test_ws_stream_no_session_closes_1008():
    from starlette.websockets import WebSocketDisconnect
    app = _build_app()
    with _client(app) as c:
        with pytest.raises(WebSocketDisconnect) as exc:
            with c.websocket_connect(
                f'/admin/api/core/v1/conversations/stream?tenant_id={uuid4()}'
            ):
                pass
        assert exc.value.code == 1008


def test_ws_stream_invalid_tenant_id():
    from starlette.websockets import WebSocketDisconnect
    from copiloto_core.admin.routes import SESSION_COOKIE
    sid, _ = _make_session(profile={'sub': 'u|1', 'roles': ['admin']})
    app = _build_app()
    with _client(app) as c:
        c.cookies.set(SESSION_COOKIE, sid)
        with pytest.raises(WebSocketDisconnect) as exc:
            with c.websocket_connect(
                '/admin/api/core/v1/conversations/stream?tenant_id=not-a-uuid'
            ):
                pass
        assert exc.value.code == 1008


def test_ws_stream_no_db_pool(monkeypatch):
    """When db.pool is None → close 1011."""
    from starlette.websockets import WebSocketDisconnect
    from copiloto_core.admin.routes import SESSION_COOKIE
    from copiloto_core.db.pool import db

    sid, _ = _make_session(profile={'sub': 'u|1', 'roles': ['admin'], 'support_mode': True})
    original_pool = db.pool
    db.pool = None
    try:
        app = _build_app()
        with _client(app) as c:
            c.cookies.set(SESSION_COOKIE, sid)
            with pytest.raises(WebSocketDisconnect) as exc:
                with c.websocket_connect(
                    f'/admin/api/core/v1/conversations/stream?tenant_id={uuid4()}'
                ):
                    pass
            assert exc.value.code == 1011
    finally:
        db.pool = original_pool


def test_ws_stream_no_access_closes(monkeypatch):
    """Session has no role + no support_mode + no pool → close 1011 (pool check first)."""
    from starlette.websockets import WebSocketDisconnect
    from copiloto_core.admin.routes import SESSION_COOKIE

    sid, _ = _make_session(profile={'sub': 'u|1', 'roles': [], 'support_mode': False})
    from copiloto_core.db.pool import db
    original_pool = db.pool
    db.pool = None
    try:
        app = _build_app()
        with _client(app) as c:
            c.cookies.set(SESSION_COOKIE, sid)
            with pytest.raises(WebSocketDisconnect):
                with c.websocket_connect(
                    f'/admin/api/core/v1/conversations/stream?tenant_id={uuid4()}'
                ):
                    pass
    finally:
        db.pool = original_pool


@pytest.mark.skip(reason="Flaky: TestClient behavior with WS close in error path varies — covered by integration")
def test_ws_stream_subscribe_runtime_error_closes_1011(monkeypatch):
    """When ws_fanout.subscribe raises RuntimeError → close 1011."""
    from starlette.websockets import WebSocketDisconnect
    from copiloto_core.admin import routes
    from copiloto_core.admin.routes import SESSION_COOKIE
    from copiloto_core.db.pool import db

    sid, _ = _make_session(profile={'sub': 'u|1', 'roles': ['admin'], 'support_mode': True})

    class _FakePool:
        pass

    db_pool_orig = db.pool
    db.pool = _FakePool()

    class _BrokenFanout:
        async def subscribe(self, pool, tenant_id):
            raise RuntimeError('listen unavailable')

        async def unsubscribe(self, tenant_id, queue):
            pass

    monkeypatch.setattr(routes, 'ws_fanout', _BrokenFanout())
    try:
        app = _build_app()
        with _client(app) as c:
            c.cookies.set(SESSION_COOKIE, sid)
            with pytest.raises(WebSocketDisconnect) as exc:
                with c.websocket_connect(
                    f'/admin/api/core/v1/conversations/stream?tenant_id={uuid4()}'
                ):
                    pass
            assert exc.value.code == 1011
    finally:
        db.pool = db_pool_orig


def test_ws_stream_happy_path_sends_connected_then_heartbeat(monkeypatch):
    """Subscribe success → 'connected' frame is sent, then heartbeat on timeout."""
    from copiloto_core.admin import routes
    from copiloto_core.admin.routes import SESSION_COOKIE
    from copiloto_core.db.pool import db

    sid, _ = _make_session(profile={'sub': 'u|1', 'roles': ['admin'], 'support_mode': True})

    class _FakePool:
        pass

    db_pool_orig = db.pool
    db.pool = _FakePool()

    # The queue never receives messages; the WS handler will hit the heartbeat
    # branch after the (asyncio.wait_for) timeout. We monkeypatch asyncio.wait_for
    # to raise TimeoutError immediately so we don't actually wait 25s. To avoid
    # a tight loop that hangs CI (when client-side close doesn't propagate fast
    # enough across Python versions), the second call raises WebSocketDisconnect
    # to exit the handler's `while True` cleanly via its except branch.
    real_wait_for = asyncio.wait_for
    call_count = {'n': 0}

    async def _fast_wait_for(awaitable, timeout):
        from starlette.websockets import WebSocketDisconnect
        if asyncio.iscoroutine(awaitable):
            awaitable.close()
        call_count['n'] += 1
        if call_count['n'] >= 2:
            raise WebSocketDisconnect(1000)
        raise asyncio.TimeoutError

    class _Fanout:
        def __init__(self):
            self.unsubscribed = False

        async def subscribe(self, pool, tenant_id):
            return asyncio.Queue()

        async def unsubscribe(self, tenant_id, queue):
            self.unsubscribed = True

    fanout = _Fanout()
    monkeypatch.setattr(routes, 'ws_fanout', fanout)
    # A2: el shortcut support_mode ahora exige cookie tid matching. Bypass
    # con un stub que devuelve True para este test (cubrimos el flow del
    # handler, no la lógica de auth — eso vive en test_unit_admin_routes_more).
    async def _gate_ok(*args, **kwargs):
        return True
    monkeypatch.setattr(routes, '_session_can_stream_tenant', _gate_ok)
    # Patch wait_for in the routes module's asyncio attribute via monkeypatch on
    # asyncio module itself works since the code references asyncio.wait_for.
    monkeypatch.setattr(asyncio, 'wait_for', _fast_wait_for)

    try:
        app = _build_app()
        with _client(app) as c:
            c.cookies.set(SESSION_COOKIE, sid)
            with c.websocket_connect(
                f'/admin/api/core/v1/conversations/stream?tenant_id={uuid4()}'
            ) as ws:
                # First frame: connected
                connected = ws.receive_json()
                assert connected['type'] == 'connected'
                # Second frame: heartbeat (because wait_for raises TimeoutError)
                heartbeat = ws.receive_json()
                assert heartbeat['type'] == 'heartbeat'
                # The 2nd wait_for call raises WebSocketDisconnect → server
                # exits the loop cleanly. The TestClient detects the close
                # when we leave the context manager.
        # Unsubscribed at finally
        assert fanout.unsubscribed is True
    finally:
        db.pool = db_pool_orig
        # restore wait_for
        asyncio.wait_for = real_wait_for


# ─────────────────────── _session_can_stream_tenant with DB ──────────────


def test_session_can_stream_tenant_db_path(monkeypatch):
    """Exercises the DB-check branch (sub set, pool set)."""
    from copiloto_core.admin import routes
    from copiloto_core.db.pool import db

    class _FakeConn:
        async def fetch(self, query, *args):
            # Return a row that satisfies role >= agent
            return [{'role': 'admin'}]

        def __aenter__(self):
            return self

        def __aexit__(self, *a):
            return False

    class _FakePoolAcquire:
        def acquire(self):
            class _Ctx:
                async def __aenter__(self_):
                    return _FakeConn()

                async def __aexit__(self_, *a):
                    return False
            return _Ctx()

    original_pool = db.pool
    db.pool = _FakePoolAcquire()
    try:
        session = {'profile': {'sub': 'auth0|abc', 'roles': []}}
        out = asyncio.run(routes._session_can_stream_tenant(session, uuid4()))
        assert out is True
    finally:
        db.pool = original_pool


def test_session_can_stream_tenant_db_returns_false_when_no_role(monkeypatch):
    from copiloto_core.admin import routes
    from copiloto_core.db.pool import db

    class _FakeConn:
        async def fetch(self, query, *args):
            return []  # no role found

    class _FakePoolAcquire:
        def acquire(self):
            class _Ctx:
                async def __aenter__(self_):
                    return _FakeConn()

                async def __aexit__(self_, *a):
                    return False
            return _Ctx()

    original_pool = db.pool
    db.pool = _FakePoolAcquire()
    try:
        session = {'profile': {'sub': 'auth0|abc', 'roles': []}}
        out = asyncio.run(routes._session_can_stream_tenant(session, uuid4()))
        assert out is False
    finally:
        db.pool = original_pool
