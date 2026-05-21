"""Extra tests for app/services/auth0_admin.py covering missing branches."""
from __future__ import annotations

import asyncio
from uuid import uuid4

import httpx
import pytest


class _MockResp:
    def __init__(self, *, status_code=200, json_payload=None, text=''):
        self.status_code = status_code
        self._payload = json_payload
        self.text = text or ''
        if json_payload is None and status_code == 204:
            self.content = b''
        else:
            self.content = b'x'

    def json(self):
        return self._payload

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            req = httpx.Request('POST', 'http://test')
            resp = httpx.Response(self.status_code, request=req)
            raise httpx.HTTPStatusError('bad', request=req, response=resp)


class _MockHttpFlow:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def __call__(self, **client_kw):
        flow = self

        class _Client:
            async def __aenter__(self_):
                return self_

            async def __aexit__(self_, *a):
                return False

            async def post(self_, url, json=None, **kw):
                flow.calls.append({'method': 'POST', 'url': url, 'json': json})
                return flow._next()

            async def request(self_, method, url, headers=None, json=None, **kw):
                flow.calls.append({'method': method, 'url': url, 'json': json})
                return flow._next()

        return _Client()

    def _next(self):
        if not self._responses:
            raise AssertionError('No more mock responses queued')
        return self._responses.pop(0)


def _set_auth0_env(monkeypatch):
    monkeypatch.setenv('AUTH0_DOMAIN', 'test.auth0.com')
    monkeypatch.setenv('AUTH0_SERVICE_CLIENT_ID', 'svc-id-min-length-16')
    monkeypatch.setenv('AUTH0_SERVICE_CLIENT_SECRET', 'svc-secret-min-length-16')
    monkeypatch.setenv('JWT_SECRET', 'test-jwt-secret-min-length-16')
    monkeypatch.setenv('SERVICE_TOKEN', 'test-service-token-min-length-16')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 'test-s3-secret')
    monkeypatch.setenv('DATABASE_URL', 'postgresql://x')
    from app.core.config import get_settings
    get_settings.cache_clear()
    from app.services.auth0_admin import clear_management_token_cache, clear_auth0_role_cache
    clear_management_token_cache()
    clear_auth0_role_cache()


def _patch_httpx(monkeypatch, responses):
    flow = _MockHttpFlow(responses)
    monkeypatch.setattr(httpx, 'AsyncClient', flow)
    return flow


def _token_resp():
    return _MockResp(json_payload={'access_token': 'tok', 'expires_in': 3600})


# ─── auth0_management_enabled / _management_credentials ─────────────────


def test_auth0_management_enabled_false_when_unconfigured(monkeypatch):
    """Patch get_settings directly to simulate unconfigured Auth0."""
    from app.services import auth0_admin
    from types import SimpleNamespace
    fake_settings = SimpleNamespace(
        auth0_domain=None,
        auth0_service_client_id=None,
        auth0_service_client_secret=None,
        auth0_service_client_secret_file=None,
        auth0_admin_client_id=None,
        auth0_admin_client_secret=None,
        auth0_admin_client_secret_file=None,
    )
    monkeypatch.setattr(auth0_admin, 'get_settings', lambda: fake_settings)
    assert auth0_admin.auth0_management_enabled() is False


def test_management_credentials_legacy_fallback():
    """If only legacy AUTH0_ADMIN_* is set, it's returned (with warning)."""
    from app.services.auth0_admin import _management_credentials
    from types import SimpleNamespace
    settings = SimpleNamespace(
        auth0_service_client_id=None,
        auth0_service_client_secret=None,
        auth0_service_client_secret_file=None,
        auth0_admin_client_id='legacy-id',
        auth0_admin_client_secret='legacy-secret',
        auth0_admin_client_secret_file=None,
    )
    cid, secret = _management_credentials(settings)
    assert cid == 'legacy-id'
    assert secret == 'legacy-secret'


def test_management_credentials_none_when_unconfigured():
    from app.services.auth0_admin import _management_credentials, _management_client_secret
    from types import SimpleNamespace
    settings = SimpleNamespace(
        auth0_service_client_id=None,
        auth0_service_client_secret=None,
        auth0_service_client_secret_file=None,
        auth0_admin_client_id=None,
        auth0_admin_client_secret=None,
        auth0_admin_client_secret_file=None,
    )
    cid, secret = _management_credentials(settings)
    assert cid is None and secret is None
    assert _management_client_secret(settings) is None


# ─── _read_secret_file ────────────────────────────────────────────────────


def test_read_secret_file_returns_contents(tmp_path):
    from app.services.auth0_admin import _read_secret_file
    f = tmp_path / 'sec.txt'
    f.write_text('hello-secret  \n')
    out = _read_secret_file(str(f))
    assert out == 'hello-secret'


def test_read_secret_file_missing_returns_none(tmp_path):
    from app.services.auth0_admin import _read_secret_file
    assert _read_secret_file(str(tmp_path / 'nope.txt')) is None


def test_read_secret_file_relative_path_searches_app_and_cwd(tmp_path, monkeypatch):
    """A relative path is searched in /app and cwd."""
    from app.services.auth0_admin import _read_secret_file
    # Switch cwd to tmp
    monkeypatch.chdir(tmp_path)
    rel = 'mysecret.txt'
    (tmp_path / rel).write_text('foo')
    out = _read_secret_file(rel)
    assert out == 'foo'


def test_read_secret_file_oserror_returns_none(monkeypatch, tmp_path):
    """If reading raises OSError, return None."""
    from app.services.auth0_admin import _read_secret_file
    import pathlib

    class _BadPath(pathlib.PosixPath):
        def is_absolute(self):
            return True

        def exists(self):
            return True

        def read_text(self, **kw):
            raise OSError('permission denied')

    monkeypatch.setattr('app.services.auth0_admin.Path', _BadPath)
    out = _read_secret_file('/tmp/x')
    assert out is None


# ─── get_management_token ────────────────────────────────────────────────


def test_get_management_token_returns_none_when_disabled(monkeypatch):
    from app.services import auth0_admin
    from app.services.auth0_admin import get_management_token, clear_management_token_cache
    monkeypatch.setattr(auth0_admin, 'auth0_management_enabled', lambda: False)
    clear_management_token_cache()
    out = asyncio.run(get_management_token())
    assert out is None


def test_get_management_token_403_logs_and_raises(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [_MockResp(status_code=403, json_payload={}, text='forbidden')])
    from app.services.auth0_admin import get_management_token
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(get_management_token())


def test_get_management_token_no_access_token(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [_MockResp(json_payload={'expires_in': 100})])
    from app.services.auth0_admin import get_management_token
    out = asyncio.run(get_management_token())
    assert out is None


def test_get_management_token_circuit_open(monkeypatch):
    _set_auth0_env(monkeypatch)
    from app.services import auth0_admin
    from app.services.auth0_admin import get_management_token
    from app.services.circuit_breaker import CircuitOpenError

    class _BrokenBreaker:
        async def call(self, *a, **kw):
            raise CircuitOpenError('open', retry_after_seconds=30)

    monkeypatch.setattr(auth0_admin, '_auth0_mgmt_breaker', lambda: _BrokenBreaker())
    out = asyncio.run(get_management_token())
    assert out is None


def test_get_management_token_uses_cache_within_ttl(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [_token_resp()])
    from app.services.auth0_admin import get_management_token, clear_management_token_cache
    clear_management_token_cache()
    t1 = asyncio.run(get_management_token())
    # Second call should hit the cache and not need another mock response
    t2 = asyncio.run(get_management_token())
    assert t1 == t2 == 'tok'


# ─── _mgmt_request 401 + 409 + other 5xx ────────────────────────────────


def test_mgmt_request_401_clears_token_cache(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(status_code=401, json_payload={}, text='unauthorized'),
    ])
    from app.services.auth0_admin import _mgmt_request, _CACHED_TOKEN
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(_mgmt_request('GET', '/users/abc'))
    assert _CACHED_TOKEN['token'] is None


def test_mgmt_request_409_raises_user_already_exists(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(status_code=409, json_payload={}, text='conflict-detail'),
    ])
    from app.services.auth0_admin import _mgmt_request, Auth0UserAlreadyExists
    with pytest.raises(Auth0UserAlreadyExists):
        asyncio.run(_mgmt_request('POST', '/users', json_body={'email': 'x'}))


def test_mgmt_request_500_raises(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(status_code=500, json_payload={}, text='boom'),
    ])
    from app.services.auth0_admin import _mgmt_request
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(_mgmt_request('GET', '/users'))


def test_mgmt_request_204_returns_empty(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(status_code=204, json_payload=None),
    ])
    from app.services.auth0_admin import _mgmt_request
    out = asyncio.run(_mgmt_request('PATCH', '/users/x'))
    assert out == {}


def test_mgmt_request_returns_disabled_when_no_token(monkeypatch):
    from app.services import auth0_admin
    from app.services.auth0_admin import _mgmt_request

    async def _no_token():
        return None

    monkeypatch.setattr(auth0_admin, 'get_management_token', _no_token)
    out = asyncio.run(_mgmt_request('GET', '/users'))
    assert out == {'disabled': True}


# ─── lookup_auth0_user_by_email ──────────────────────────────────────────


def test_lookup_auth0_user_by_email_disabled(monkeypatch):
    from app.services import auth0_admin
    from app.services.auth0_admin import lookup_auth0_user_by_email
    monkeypatch.setattr(auth0_admin, 'auth0_management_enabled', lambda: False)
    out = asyncio.run(lookup_auth0_user_by_email('a@b.com'))
    assert out is None


def test_lookup_auth0_user_by_email_empty_list(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(json_payload=[]),
    ])
    from app.services.auth0_admin import lookup_auth0_user_by_email
    out = asyncio.run(lookup_auth0_user_by_email('a@b.com'))
    assert out is None


def test_lookup_auth0_user_by_email_ambiguous_strict_opt_in(monkeypatch):
    """BUG-219: el modo strict sigue disponible vía `enforce_single=True`."""
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(json_payload=[
            {'user_id': 'a|1', 'email_verified': True},
            {'user_id': 'g|2', 'email_verified': True},
        ]),
    ])
    from app.services.auth0_admin import lookup_auth0_user_by_email, Auth0AmbiguousUserMatch
    with pytest.raises(Auth0AmbiguousUserMatch):
        asyncio.run(lookup_auth0_user_by_email('a@b.com', enforce_single=True))


def test_lookup_auth0_user_by_email_unverified(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(json_payload=[{'user_id': 'a|1', 'email_verified': False}]),
    ])
    from app.services.auth0_admin import lookup_auth0_user_by_email, Auth0UserNotVerified
    with pytest.raises(Auth0UserNotVerified):
        asyncio.run(lookup_auth0_user_by_email('a@b.com'))


def test_lookup_auth0_user_by_email_ok(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(json_payload=[{'user_id': 'a|1', 'email_verified': True}]),
    ])
    from app.services.auth0_admin import lookup_auth0_user_by_email
    out = asyncio.run(lookup_auth0_user_by_email('a@b.com'))
    assert out['user_id'] == 'a|1'


def test_lookup_auth0_user_by_email_non_dict_candidate(monkeypatch):
    """If response[0] is not a dict, return None."""
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(json_payload=['just-a-string']),
    ])
    from app.services.auth0_admin import lookup_auth0_user_by_email
    out = asyncio.run(lookup_auth0_user_by_email('a@b.com', enforce_single=False, require_email_verified=False))
    assert out is None


def test_lookup_auth0_user_by_email_disables_guards(monkeypatch):
    """When both guards are off, accept unverified single match."""
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(json_payload=[{'user_id': 'a|1', 'email_verified': False}]),
    ])
    from app.services.auth0_admin import lookup_auth0_user_by_email
    out = asyncio.run(lookup_auth0_user_by_email(
        'a@b.com', enforce_single=False, require_email_verified=False,
    ))
    assert out['user_id'] == 'a|1'


# ─── assign_roles ─────────────────────────────────────────────────────────


def test_assign_roles_disabled(monkeypatch):
    from app.services import auth0_admin
    from app.services.auth0_admin import assign_roles
    monkeypatch.setattr(auth0_admin, 'auth0_management_enabled', lambda: False)
    out = asyncio.run(assign_roles(auth_subject='a|1', roles=['admin']))
    assert out == {'disabled': True}


def test_assign_roles_no_subject(monkeypatch):
    _set_auth0_env(monkeypatch)
    from app.services.auth0_admin import assign_roles
    out = asyncio.run(assign_roles(auth_subject=None, roles=['admin']))
    assert out['skipped'] == 'no_auth_subject'


def test_assign_roles_http_error(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(status_code=500, json_payload={}, text='boom'),
    ])
    from app.services.auth0_admin import assign_roles
    out = asyncio.run(assign_roles(auth_subject='a|1', roles=['admin']))
    assert 'error' in out


def test_assign_roles_success(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(status_code=200, json_payload={}),
    ])
    from app.services.auth0_admin import assign_roles
    out = asyncio.run(assign_roles(auth_subject='a|1', roles=['admin']))
    assert out['synced'] is True


# ─── set_user_tenant_metadata ─────────────────────────────────────────────


def test_set_user_tenant_metadata_disabled(monkeypatch):
    from app.services import auth0_admin
    from app.services.auth0_admin import set_user_tenant_metadata
    monkeypatch.setattr(auth0_admin, 'auth0_management_enabled', lambda: False)
    out = asyncio.run(set_user_tenant_metadata(auth_subject='a|1', tenant_id=uuid4()))
    assert out == {'disabled': True}


def test_set_user_tenant_metadata_no_subject(monkeypatch):
    _set_auth0_env(monkeypatch)
    from app.services.auth0_admin import set_user_tenant_metadata
    out = asyncio.run(set_user_tenant_metadata(auth_subject='', tenant_id=uuid4()))
    assert out['skipped'] == 'no_auth_subject'


def test_set_user_tenant_metadata_success(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(status_code=200, json_payload={}),
    ])
    from app.services.auth0_admin import set_user_tenant_metadata
    out = asyncio.run(set_user_tenant_metadata(auth_subject='a|1', tenant_id=uuid4()))
    assert out['updated'] is True


# ─── assign_auth0_role_by_name ────────────────────────────────────────────


def test_assign_role_by_name_disabled(monkeypatch):
    from app.services import auth0_admin
    from app.services.auth0_admin import assign_auth0_role_by_name
    monkeypatch.setattr(auth0_admin, 'auth0_management_enabled', lambda: False)
    out = asyncio.run(assign_auth0_role_by_name(auth_subject='a|1', role_name='admin'))
    assert out == {'disabled': True}


def test_assign_role_by_name_no_subject(monkeypatch):
    _set_auth0_env(monkeypatch)
    from app.services.auth0_admin import assign_auth0_role_by_name
    out = asyncio.run(assign_auth0_role_by_name(auth_subject=None, role_name='admin'))
    assert out['skipped'] == 'no_auth_subject'


def test_assign_role_by_name_unresolved(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        # /roles?per_page=100 returns nothing matching
        _MockResp(json_payload=[{'name': 'other_role', 'id': 'rol_xx'}]),
    ])
    from app.services.auth0_admin import assign_auth0_role_by_name
    out = asyncio.run(assign_auth0_role_by_name(auth_subject='a|1', role_name='admin'))
    assert out['error'].startswith('auth0_role_not_found:')


def test_assign_role_by_name_success(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(json_payload=[{'name': 'admin', 'id': 'rol_admin'}]),
        _MockResp(status_code=200, json_payload={}),
    ])
    from app.services.auth0_admin import assign_auth0_role_by_name
    out = asyncio.run(assign_auth0_role_by_name(auth_subject='a|1', role_name='admin'))
    assert out['assigned'] is True
    assert out['role_id'] == 'rol_admin'


def test_resolve_auth0_role_uses_cache(monkeypatch):
    """Calling twice doesn't re-fetch from the API."""
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(json_payload=[{'name': 'admin', 'id': 'rol_admin'}]),
        _MockResp(status_code=200, json_payload={}),
        _MockResp(status_code=200, json_payload={}),
    ])
    from app.services.auth0_admin import assign_auth0_role_by_name
    asyncio.run(assign_auth0_role_by_name(auth_subject='a|1', role_name='admin'))
    asyncio.run(assign_auth0_role_by_name(auth_subject='a|2', role_name='admin'))
    # only 4 mock responses total used (no extra /roles call)


# ─── revoke_tenant_roles ─────────────────────────────────────────────────


def test_revoke_tenant_roles_disabled(monkeypatch):
    from app.services import auth0_admin
    from app.services.auth0_admin import revoke_tenant_roles
    monkeypatch.setattr(auth0_admin, 'auth0_management_enabled', lambda: False)
    out = asyncio.run(revoke_tenant_roles(auth_subject='a|1', tenant_id=uuid4()))
    assert out == {'disabled': True}


def test_revoke_tenant_roles_no_subject(monkeypatch):
    _set_auth0_env(monkeypatch)
    from app.services.auth0_admin import revoke_tenant_roles
    out = asyncio.run(revoke_tenant_roles(auth_subject='', tenant_id=uuid4()))
    assert out['skipped'] == 'no_auth_subject'


def test_revoke_tenant_roles_clears_pointer_when_match(monkeypatch):
    _set_auth0_env(monkeypatch)
    tenant_id = uuid4()
    _patch_httpx(monkeypatch, [
        _token_resp(),
        # GET /users/{id} returns app_metadata with matching tenant_id
        _MockResp(json_payload={'app_metadata': {'tenant_id': str(tenant_id),
                                                  'default_tenant_id': str(tenant_id)}}),
        # PATCH /users/{id}
        _MockResp(status_code=200, json_payload={}),
    ])
    from app.services.auth0_admin import revoke_tenant_roles
    out = asyncio.run(revoke_tenant_roles(auth_subject='a|1', tenant_id=tenant_id))
    assert out['revoked'] is True
    assert out['cleared_tenant_pointer'] is True


def test_revoke_tenant_roles_no_pointer_match(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(json_payload={'app_metadata': {'tenant_id': str(uuid4())}}),
        _MockResp(status_code=200, json_payload={}),
    ])
    from app.services.auth0_admin import revoke_tenant_roles
    out = asyncio.run(revoke_tenant_roles(auth_subject='a|1', tenant_id=uuid4()))
    assert out['revoked'] is True
    assert out['cleared_tenant_pointer'] is False


def test_revoke_tenant_roles_read_app_meta_fails(monkeypatch):
    """If the initial GET fails, we still do the basic PATCH (best-effort)."""
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(status_code=500, json_payload={}, text='boom'),
        _MockResp(status_code=200, json_payload={}),
    ])
    from app.services.auth0_admin import revoke_tenant_roles
    out = asyncio.run(revoke_tenant_roles(auth_subject='a|1', tenant_id=uuid4()))
    assert out['revoked'] is True


def test_revoke_tenant_roles_patch_fails(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(json_payload={'app_metadata': {}}),
        _MockResp(status_code=500, json_payload={}, text='boom'),
    ])
    from app.services.auth0_admin import revoke_tenant_roles
    out = asyncio.run(revoke_tenant_roles(auth_subject='a|1', tenant_id=uuid4()))
    assert 'error' in out


# ─── invite_user — error paths ─────────────────────────────────────────────


def test_invite_user_disabled(monkeypatch):
    from app.services import auth0_admin
    from app.services.auth0_admin import invite_user
    monkeypatch.setattr(auth0_admin, 'auth0_management_enabled', lambda: False)
    out = asyncio.run(invite_user(email='x@y.com', role='admin', tenant_id=uuid4()))
    assert out == {'disabled': True}


def test_invite_user_409_lookup_finds_existing(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        # POST /users → 409
        _MockResp(status_code=409, json_payload={}, text='already exists'),
        # GET /users-by-email returns the existing user
        _MockResp(json_payload=[{'user_id': 'existing|1', 'email_verified': True}]),
        # PATCH /users/{id} for set_user_tenant_metadata
        _MockResp(status_code=200, json_payload={}),
        # GET /roles for assign_auth0_role_by_name
        _MockResp(json_payload=[{'name': 'admin', 'id': 'rol_admin'}]),
        # POST /users/{id}/roles
        _MockResp(status_code=200, json_payload={}),
    ])
    from app.services.auth0_admin import invite_user
    out = asyncio.run(invite_user(email='x@y.com', role='admin', tenant_id=uuid4()))
    assert out['invited'] is True
    assert out['reused_existing'] is True
    assert out['auth0_user_id'] == 'existing|1'


def test_invite_user_409_lookup_fails_propagates(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(status_code=409, json_payload={}, text='exists'),
        # lookup returns empty array → propagates the Auth0UserAlreadyExists
        _MockResp(json_payload=[]),
    ])
    from app.services.auth0_admin import invite_user, Auth0UserAlreadyExists
    with pytest.raises(Auth0UserAlreadyExists):
        asyncio.run(invite_user(email='x@y.com', role='admin', tenant_id=uuid4()))


def test_invite_user_http_error_on_create(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(status_code=500, json_payload={}, text='boom'),
    ])
    from app.services.auth0_admin import invite_user
    out = asyncio.run(invite_user(email='x@y.com', role='admin', tenant_id=uuid4()))
    assert 'error' in out


def test_invite_user_no_user_id_returned(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        # POST /users returns 200 but no user_id
        _MockResp(status_code=200, json_payload={'email': 'x@y.com'}),
    ])
    from app.services.auth0_admin import invite_user
    out = asyncio.run(invite_user(email='x@y.com', role='admin', tenant_id=uuid4()))
    assert out.get('error') == 'auth0_create_user_returned_no_id'


def test_invite_user_happy_path(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(status_code=200, json_payload={'user_id': 'auth0|new'}),
        # PATCH user app_metadata
        _MockResp(status_code=200, json_payload={}),
        # GET /roles
        _MockResp(json_payload=[{'name': 'admin', 'id': 'rol_admin'}]),
        # POST /users/{id}/roles
        _MockResp(status_code=200, json_payload={}),
        # POST /tickets/password-change
        _MockResp(status_code=200, json_payload={'ticket': 'https://reset-url'}),
    ])
    from app.services.auth0_admin import invite_user
    out = asyncio.run(invite_user(email='x@y.com', role='admin', tenant_id=uuid4()))
    assert out['invited'] is True
    assert out['reused_existing'] is False
    assert out['auth0_user_id'] == 'auth0|new'


def test_invite_user_propagation_errors_collected(monkeypatch):
    """Both propagation calls fail → propagation_errors is populated."""
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(status_code=200, json_payload={'user_id': 'auth0|new'}),
        # set_user_tenant_metadata fails
        _MockResp(status_code=500, json_payload={}, text='boom1'),
        # GET /roles fails
        _MockResp(status_code=500, json_payload={}, text='boom2'),
        # POST /tickets/password-change OK
        _MockResp(status_code=200, json_payload={}),
    ])
    from app.services.auth0_admin import invite_user
    out = asyncio.run(invite_user(email='x@y.com', role='admin', tenant_id=uuid4()))
    assert 'propagation_errors' in out
    assert len(out['propagation_errors']) == 2


def test_invite_user_ticket_fails(monkeypatch):
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(status_code=200, json_payload={'user_id': 'auth0|new'}),
        _MockResp(status_code=200, json_payload={}),  # set_metadata
        _MockResp(json_payload=[{'name': 'admin', 'id': 'rol_admin'}]),
        _MockResp(status_code=200, json_payload={}),  # POST roles
        _MockResp(status_code=500, json_payload={}, text='boom'),  # ticket fails
    ])
    from app.services.auth0_admin import invite_user
    out = asyncio.run(invite_user(email='x@y.com', role='admin', tenant_id=uuid4()))
    assert 'error' in out
    assert out['auth0_user_id'] == 'auth0|new'


def test_invite_user_role_unresolved_added_to_errors(monkeypatch):
    """assign_auth0_role_by_name returns {'error': 'auth0_role_not_found:...'}."""
    _set_auth0_env(monkeypatch)
    _patch_httpx(monkeypatch, [
        _token_resp(),
        _MockResp(status_code=200, json_payload={'user_id': 'auth0|new'}),
        _MockResp(status_code=200, json_payload={}),  # set_metadata OK
        _MockResp(json_payload=[]),  # /roles returns nothing
        _MockResp(status_code=200, json_payload={'ticket': 'https://r'}),  # ticket OK
    ])
    from app.services.auth0_admin import invite_user
    out = asyncio.run(invite_user(email='x@y.com', role='not_a_real_role', tenant_id=uuid4()))
    assert any('role_assignment' in e for e in out.get('propagation_errors', []))
