"""M59 — tests del cliente Auth0 Management API.

Mockea httpx + settings sin pegarle a Auth0 real.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest

from copiloto_core.services import auth0_admin as a0


# ─── _service_client_secret + is_configured ───────────────────────────────


def test_secret_from_plaintext_setting(monkeypatch):
    fake = SimpleNamespace(
        auth0_domain='test.auth0.com',
        auth0_service_client_id='cid',
        auth0_service_client_secret='plaintext-secret',
        auth0_service_client_secret_file=None,
    )
    monkeypatch.setattr(a0, 'get_settings', lambda: fake)
    assert a0._service_client_secret() == 'plaintext-secret'


def test_secret_from_file(monkeypatch, tmp_path):
    secret_file = tmp_path / 'svc-secret'
    secret_file.write_text('file-secret\n')
    fake = SimpleNamespace(
        auth0_domain='test.auth0.com',
        auth0_service_client_id='cid',
        auth0_service_client_secret=None,
        auth0_service_client_secret_file=str(secret_file),
    )
    monkeypatch.setattr(a0, 'get_settings', lambda: fake)
    assert a0._service_client_secret() == 'file-secret'


def test_secret_missing_raises(monkeypatch):
    fake = SimpleNamespace(
        auth0_domain='test.auth0.com',
        auth0_service_client_id='cid',
        auth0_service_client_secret=None,
        auth0_service_client_secret_file=None,
    )
    monkeypatch.setattr(a0, 'get_settings', lambda: fake)
    with pytest.raises(a0.Auth0NotConfiguredError):
        a0._service_client_secret()


def test_is_configured_true(monkeypatch):
    fake = SimpleNamespace(
        auth0_domain='test.auth0.com',
        auth0_service_client_id='cid',
        auth0_service_client_secret='s',
        auth0_service_client_secret_file=None,
    )
    monkeypatch.setattr(a0, 'get_settings', lambda: fake)
    assert a0.is_configured() is True


def test_is_configured_false_missing_domain(monkeypatch):
    fake = SimpleNamespace(
        auth0_domain=None,
        auth0_service_client_id='cid',
        auth0_service_client_secret='s',
        auth0_service_client_secret_file=None,
    )
    monkeypatch.setattr(a0, 'get_settings', lambda: fake)
    assert a0.is_configured() is False


def test_is_configured_false_missing_client_id(monkeypatch):
    fake = SimpleNamespace(
        auth0_domain='test.auth0.com',
        auth0_service_client_id=None,
        auth0_service_client_secret='s',
        auth0_service_client_secret_file=None,
    )
    monkeypatch.setattr(a0, 'get_settings', lambda: fake)
    assert a0.is_configured() is False


# ─── make_pending_auth_subject ─────────────────────────────────────────────


def test_make_pending_deterministic():
    """Lower-case email + sha256 truncado. Mismo email → mismo subject."""
    a = a0.make_pending_auth_subject('Foo@BAR.co')
    b = a0.make_pending_auth_subject('foo@bar.co')
    assert a == b
    assert a.startswith('pending|')


def test_make_pending_different_emails_differ():
    a = a0.make_pending_auth_subject('foo@bar.co')
    b = a0.make_pending_auth_subject('baz@bar.co')
    assert a != b


# ─── _get_management_token (caching) ───────────────────────────────────────


def _configured_settings():
    return SimpleNamespace(
        auth0_domain='test.auth0.com',
        auth0_service_client_id='cid',
        auth0_service_client_secret='secret',
        auth0_service_client_secret_file=None,
        auth0_mgmt_token_cache_ttl_seconds=20 * 3600,
    )


def _httpx_async_client(post_response=None, request_response=None):
    """Builds a mock that mimics `async with httpx.AsyncClient(...) as c`."""
    class FakeClient:
        async def __aenter__(self_inner): return self_inner
        async def __aexit__(self_inner, *exc): return False
        async def post(self_inner, url, **kw):
            return post_response
        async def request(self_inner, method, url, **kw):
            return request_response

    def fake_ctor(*args, **kwargs):
        return FakeClient()
    return fake_ctor


def test_get_management_token_caches(monkeypatch):
    monkeypatch.setattr(a0, 'get_settings', _configured_settings)
    a0._clear_token_cache()
    call_count = {'n': 0}

    class FakeResp:
        status_code = 200
        text = ''
        def json(self_inner):
            call_count['n'] += 1
            return {'access_token': f'token-{call_count["n"]}', 'expires_in': 86400}

    monkeypatch.setattr(
        httpx, 'AsyncClient', _httpx_async_client(post_response=FakeResp()),
    )

    token1 = asyncio.run(a0._get_management_token())
    token2 = asyncio.run(a0._get_management_token())
    assert token1 == token2 == 'token-1'  # segunda llamada usa cache
    assert call_count['n'] == 1


def test_get_management_token_refresh_after_expiry(monkeypatch):
    monkeypatch.setattr(a0, 'get_settings', _configured_settings)
    a0._clear_token_cache()
    call_count = {'n': 0}

    class FakeResp:
        status_code = 200
        text = ''
        def json(self_inner):
            call_count['n'] += 1
            return {'access_token': f'token-{call_count["n"]}', 'expires_in': 86400}

    monkeypatch.setattr(
        httpx, 'AsyncClient', _httpx_async_client(post_response=FakeResp()),
    )

    token1 = asyncio.run(a0._get_management_token())
    # Forzar expiración del cache.
    a0._mgmt_token_cache['expires_at'] = 0
    token2 = asyncio.run(a0._get_management_token())
    assert token1 == 'token-1'
    assert token2 == 'token-2'


def test_get_management_token_auth0_error(monkeypatch):
    monkeypatch.setattr(a0, 'get_settings', _configured_settings)
    a0._clear_token_cache()

    class FakeResp:
        status_code = 401
        text = '{"error":"access_denied"}'
        def json(self_inner): return {}

    monkeypatch.setattr(
        httpx, 'AsyncClient', _httpx_async_client(post_response=FakeResp()),
    )
    with pytest.raises(a0.Auth0ApiError) as exc:
        asyncio.run(a0._get_management_token())
    assert exc.value.status_code == 401


# ─── _mgmt_api ─────────────────────────────────────────────────────────────


def test_mgmt_api_happy(monkeypatch):
    monkeypatch.setattr(a0, 'get_settings', _configured_settings)
    a0._mgmt_token_cache['token'] = 'cached-token'
    a0._mgmt_token_cache['expires_at'] = 9_999_999_999

    class FakeResp:
        status_code = 200
        content = b'{"ok":1}'
        text = '{"ok":1}'
        def json(self_inner): return {'ok': 1}

    monkeypatch.setattr(
        httpx, 'AsyncClient', _httpx_async_client(request_response=FakeResp()),
    )
    out = asyncio.run(a0._mgmt_api('GET', '/users/abc'))
    assert out == {'ok': 1}


def test_mgmt_api_204_returns_none(monkeypatch):
    monkeypatch.setattr(a0, 'get_settings', _configured_settings)
    a0._mgmt_token_cache['token'] = 'cached'
    a0._mgmt_token_cache['expires_at'] = 9_999_999_999

    class FakeResp:
        status_code = 204
        content = b''
        text = ''
        def json(self_inner): return None

    monkeypatch.setattr(
        httpx, 'AsyncClient', _httpx_async_client(request_response=FakeResp()),
    )
    assert asyncio.run(a0._mgmt_api('DELETE', '/users/abc/multifactor/google-authenticator')) is None


def test_mgmt_api_500_raises(monkeypatch):
    monkeypatch.setattr(a0, 'get_settings', _configured_settings)
    a0._mgmt_token_cache['token'] = 'cached'
    a0._mgmt_token_cache['expires_at'] = 9_999_999_999

    class FakeResp:
        status_code = 500
        content = b'oops'
        text = 'internal server error'
        def json(self_inner): return {}

    monkeypatch.setattr(
        httpx, 'AsyncClient', _httpx_async_client(request_response=FakeResp()),
    )
    with pytest.raises(a0.Auth0ApiError) as exc:
        asyncio.run(a0._mgmt_api('GET', '/users/abc'))
    assert exc.value.status_code == 500


# ─── invite_user ───────────────────────────────────────────────────────────


def test_invite_user_creates_new(monkeypatch):
    """No existe → POST /users + POST /tickets/password-change."""
    calls = []

    async def fake_api(method, path, **kw):
        calls.append((method, path, kw.get('json_body')))
        if method == 'GET' and path == '/users-by-email':
            return []  # no existe
        if method == 'POST' and path == '/users':
            return {'user_id': 'auth0|new123', 'email': kw['json_body']['email']}
        if method == 'POST' and path == '/tickets/password-change':
            return {'ticket': 'https://test.auth0.com/u/reset?ticket=abc'}
        raise AssertionError(f'unexpected: {method} {path}')

    monkeypatch.setattr(a0, '_mgmt_api', fake_api)
    out = asyncio.run(a0.invite_user(email='new@x.co', name='New User'))
    assert out['reused_existing'] is False
    assert out['user']['user_id'] == 'auth0|new123'
    assert out['invitation_ticket_url'].startswith('https://')
    # Verifica que NO emitió password en respuesta + sí mandó email_verified=False
    user_post = next(c for c in calls if c[0] == 'POST' and c[1] == '/users')
    assert 'password' in user_post[2]
    assert user_post[2]['email_verified'] is False


def test_invite_user_reuses_existing(monkeypatch):
    """Email ya existe → no crea ni emite ticket. Devuelve reused_existing=True."""
    calls = []

    async def fake_api(method, path, **kw):
        calls.append((method, path))
        if method == 'GET' and path == '/users-by-email':
            return [{'user_id': 'auth0|existing456', 'email': kw['params']['email']}]
        raise AssertionError(f'unexpected: {method} {path}')

    monkeypatch.setattr(a0, '_mgmt_api', fake_api)
    out = asyncio.run(a0.invite_user(email='existing@x.co'))
    assert out['reused_existing'] is True
    assert out['user']['user_id'] == 'auth0|existing456'
    assert out['invitation_ticket_url'] is None
    # Solo una call (no POST /users ni /tickets).
    assert len(calls) == 1


# ─── block / unblock / reset_mfa / delete ─────────────────────────────────


def test_block_user(monkeypatch):
    body_seen = {}

    async def fake_api(method, path, **kw):
        body_seen[path] = (method, kw.get('json_body'))
        return None

    monkeypatch.setattr(a0, '_mgmt_api', fake_api)
    asyncio.run(a0.block_user('auth0|abc'))
    assert body_seen['/users/auth0|abc'] == ('PATCH', {'blocked': True})


def test_unblock_user(monkeypatch):
    seen = {}

    async def fake_api(method, path, **kw):
        seen[path] = (method, kw.get('json_body'))

    monkeypatch.setattr(a0, '_mgmt_api', fake_api)
    asyncio.run(a0.unblock_user('auth0|abc'))
    assert seen['/users/auth0|abc'] == ('PATCH', {'blocked': False})


def test_reset_mfa_deletes_all_providers(monkeypatch):
    deleted_providers = []

    async def fake_api(method, path, **kw):
        if method == 'DELETE' and '/multifactor/' in path:
            provider = path.split('/')[-1]
            deleted_providers.append(provider)
        return None

    monkeypatch.setattr(a0, '_mgmt_api', fake_api)
    asyncio.run(a0.reset_mfa('auth0|abc'))
    # Should iterate over all known providers.
    assert 'google-authenticator' in deleted_providers
    assert 'guardian' in deleted_providers
    assert len(deleted_providers) >= 4


def test_reset_mfa_swallows_404(monkeypatch):
    """Si un provider no estaba enrolled (404), seguimos con los demás."""
    async def fake_api(method, path, **kw):
        if 'google-authenticator' in path:
            raise a0.Auth0ApiError(404, '{"statusCode":404}')
        return None

    monkeypatch.setattr(a0, '_mgmt_api', fake_api)
    # No debe levantar.
    asyncio.run(a0.reset_mfa('auth0|abc'))


def test_reset_mfa_propagates_500(monkeypatch):
    async def fake_api(method, path, **kw):
        raise a0.Auth0ApiError(500, 'server error')

    monkeypatch.setattr(a0, '_mgmt_api', fake_api)
    with pytest.raises(a0.Auth0ApiError) as exc:
        asyncio.run(a0.reset_mfa('auth0|abc'))
    assert exc.value.status_code == 500


def test_delete_user(monkeypatch):
    seen = {}

    async def fake_api(method, path, **kw):
        seen[path] = method

    monkeypatch.setattr(a0, '_mgmt_api', fake_api)
    asyncio.run(a0.delete_user('auth0|abc'))
    assert seen['/users/auth0|abc'] == 'DELETE'


# ─── get_user_by_email ─────────────────────────────────────────────────────


def test_get_user_by_email_hit(monkeypatch):
    async def fake_api(method, path, **kw):
        return [{'user_id': 'auth0|1', 'email': 'x@y.co'}]

    monkeypatch.setattr(a0, '_mgmt_api', fake_api)
    out = asyncio.run(a0.get_user_by_email('x@y.co'))
    assert out['user_id'] == 'auth0|1'


def test_get_user_by_email_miss(monkeypatch):
    async def fake_api(method, path, **kw):
        return []

    monkeypatch.setattr(a0, '_mgmt_api', fake_api)
    assert asyncio.run(a0.get_user_by_email('none@x.co')) is None
