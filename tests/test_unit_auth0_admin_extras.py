"""More tests for `app/services/auth0_admin.py` covering the disabled-path
branches and the resolve/cache helpers. Complements
test_unit_auth0_admin_mocked.py which exercises the full HTTP flow."""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import pytest


def _disabled_settings():
    """Settings that disable auth0_management (no client_id/secret configured)."""
    return SimpleNamespace(
        auth0_domain=None,
        auth0_service_client_id=None,
        auth0_service_client_secret=None,
        auth0_service_client_secret_file=None,
        auth0_admin_client_id=None,
        auth0_admin_client_secret=None,
        auth0_admin_client_secret_file=None,
        auth0_callback_urls='http://localhost:3000/callback',
    )


# ───────── _read_secret_file ─────────────────────────────────────────────


def test_read_secret_file_returns_none_for_missing_relative(monkeypatch, tmp_path):
    from app.services.auth0_admin import _read_secret_file
    monkeypatch.chdir(tmp_path)
    # Relative path that doesn't exist in either /app or cwd
    assert _read_secret_file('nope.txt') is None


def test_read_secret_file_reads_absolute(tmp_path):
    from app.services.auth0_admin import _read_secret_file
    f = tmp_path / 'secret.txt'
    f.write_text('  the-secret-value  \n')
    assert _read_secret_file(str(f)) == 'the-secret-value'


def test_read_secret_file_reads_relative_from_cwd(monkeypatch, tmp_path):
    from app.services.auth0_admin import _read_secret_file
    monkeypatch.chdir(tmp_path)
    f = tmp_path / 'rel.txt'
    f.write_text('rel-secret')
    assert _read_secret_file('rel.txt') == 'rel-secret'


def test_read_secret_file_returns_none_for_missing_absolute(tmp_path):
    from app.services.auth0_admin import _read_secret_file
    assert _read_secret_file(str(tmp_path / 'nope.txt')) is None


# ───────── _service_client_secret + _legacy_admin_client_secret ──────────


def test_service_client_secret_inline():
    from app.services.auth0_admin import _service_client_secret
    s = SimpleNamespace(
        auth0_service_client_secret='inline-svc',
        auth0_service_client_secret_file=None,
    )
    assert _service_client_secret(s) == 'inline-svc'


def test_service_client_secret_from_file(tmp_path):
    from app.services.auth0_admin import _service_client_secret
    f = tmp_path / 's.txt'
    f.write_text('file-svc')
    s = SimpleNamespace(
        auth0_service_client_secret=None,
        auth0_service_client_secret_file=str(f),
    )
    assert _service_client_secret(s) == 'file-svc'


def test_service_client_secret_returns_none_when_neither_set():
    from app.services.auth0_admin import _service_client_secret
    s = SimpleNamespace(
        auth0_service_client_secret=None,
        auth0_service_client_secret_file=None,
    )
    assert _service_client_secret(s) is None


def test_legacy_admin_client_secret_inline():
    from app.services.auth0_admin import _legacy_admin_client_secret
    s = SimpleNamespace(
        auth0_admin_client_secret='legacy-inline',
        auth0_admin_client_secret_file=None,
    )
    assert _legacy_admin_client_secret(s) == 'legacy-inline'


def test_legacy_admin_client_secret_from_file(tmp_path):
    from app.services.auth0_admin import _legacy_admin_client_secret
    f = tmp_path / 'a.txt'
    f.write_text('legacy-file')
    s = SimpleNamespace(
        auth0_admin_client_secret=None,
        auth0_admin_client_secret_file=str(f),
    )
    assert _legacy_admin_client_secret(s) == 'legacy-file'


def test_legacy_admin_client_secret_none_when_unset():
    from app.services.auth0_admin import _legacy_admin_client_secret
    s = SimpleNamespace(
        auth0_admin_client_secret=None,
        auth0_admin_client_secret_file=None,
    )
    assert _legacy_admin_client_secret(s) is None


# ───────── _management_credentials ────────────────────────────────────────


def test_management_credentials_prefers_service():
    from app.services.auth0_admin import _management_credentials
    s = SimpleNamespace(
        auth0_service_client_id='svc-id',
        auth0_service_client_secret='svc-secret',
        auth0_service_client_secret_file=None,
        auth0_admin_client_id='admin-id',
        auth0_admin_client_secret='admin-secret',
        auth0_admin_client_secret_file=None,
    )
    cid, sec = _management_credentials(s)
    assert cid == 'svc-id'
    assert sec == 'svc-secret'


def test_management_credentials_falls_back_to_admin():
    from app.services.auth0_admin import _management_credentials
    s = SimpleNamespace(
        auth0_service_client_id=None,
        auth0_service_client_secret=None,
        auth0_service_client_secret_file=None,
        auth0_admin_client_id='admin-id',
        auth0_admin_client_secret='admin-secret',
        auth0_admin_client_secret_file=None,
    )
    cid, sec = _management_credentials(s)
    assert cid == 'admin-id'
    assert sec == 'admin-secret'


def test_management_credentials_returns_none_pair_when_unconfigured():
    from app.services.auth0_admin import _management_credentials
    cid, sec = _management_credentials(_disabled_settings())
    assert cid is None
    assert sec is None


def test_management_client_secret_legacy_accessor():
    from app.services.auth0_admin import _management_client_secret
    s = SimpleNamespace(
        auth0_service_client_id='svc',
        auth0_service_client_secret='svc-sec',
        auth0_service_client_secret_file=None,
        auth0_admin_client_id=None,
        auth0_admin_client_secret=None,
        auth0_admin_client_secret_file=None,
    )
    assert _management_client_secret(s) == 'svc-sec'


# ───────── _management_audience / _admin_panel_result_url ────────────────


def test_management_audience_strips_scheme():
    from app.services.auth0_admin import _management_audience
    s = SimpleNamespace(auth0_domain='https://tenant.auth0.com/')
    assert _management_audience(s) == 'https://tenant.auth0.com/api/v2/'


def test_admin_panel_result_url_first_callback():
    from app.services.auth0_admin import _admin_panel_result_url
    s = SimpleNamespace(
        auth0_callback_urls='https://prod.example.com/callback,https://staging.example.com/callback',
    )
    assert _admin_panel_result_url(s) == 'https://prod.example.com/callback'


def test_admin_panel_result_url_default():
    from app.services.auth0_admin import _admin_panel_result_url
    s = SimpleNamespace(auth0_callback_urls=None)
    assert _admin_panel_result_url(s) == 'http://localhost:3000/callback'


# ───────── auth0_management_enabled ──────────────────────────────────────


def test_auth0_management_enabled_false_when_unconfigured(monkeypatch):
    from app.services import auth0_admin as mod
    monkeypatch.setattr(mod, 'get_settings', _disabled_settings)
    assert mod.auth0_management_enabled() is False


def test_auth0_management_enabled_true_with_full_config(monkeypatch):
    from app.services import auth0_admin as mod

    def _settings():
        return SimpleNamespace(
            auth0_domain='tenant.auth0.com',
            auth0_service_client_id='svc',
            auth0_service_client_secret='secret',
            auth0_service_client_secret_file=None,
            auth0_admin_client_id=None,
            auth0_admin_client_secret=None,
            auth0_admin_client_secret_file=None,
        )

    monkeypatch.setattr(mod, 'get_settings', _settings)
    assert mod.auth0_management_enabled() is True


# ───────── clear_management_token_cache + clear_auth0_role_cache ────────


def test_clear_management_token_cache_resets():
    from app.services import auth0_admin as mod
    mod._CACHED_TOKEN['token'] = 'fake'
    mod._CACHED_TOKEN['expires_at'] = 9999.9
    mod.clear_management_token_cache()
    assert mod._CACHED_TOKEN['token'] is None
    assert mod._CACHED_TOKEN['expires_at'] == 0.0


def test_clear_auth0_role_cache_resets():
    from app.services import auth0_admin as mod
    mod._AUTH0_ROLE_ID_CACHE['admin'] = 'role-id-1'
    mod.clear_auth0_role_cache()
    assert mod._AUTH0_ROLE_ID_CACHE == {}


# ───────── get_management_token returns None when disabled ──────────────


def test_get_management_token_returns_none_when_disabled(monkeypatch):
    from app.services import auth0_admin as mod
    monkeypatch.setattr(mod, 'get_settings', _disabled_settings)
    mod.clear_management_token_cache()

    async def _go():
        return await mod.get_management_token()

    assert asyncio.run(_go()) is None


# ───────── disabled-path returns for higher-level helpers ───────────────


def test_invite_user_disabled_returns_disabled_dict(monkeypatch):
    from app.services import auth0_admin as mod
    monkeypatch.setattr(mod, 'get_settings', _disabled_settings)

    async def _go():
        return await mod.invite_user(
            email='x@y.com', tenant_id=uuid4(),
            role='agent', display_name='X',
        )

    out = asyncio.run(_go())
    assert out == {'disabled': True}


def test_assign_roles_disabled_returns_disabled(monkeypatch):
    from app.services import auth0_admin as mod
    monkeypatch.setattr(mod, 'get_settings', _disabled_settings)

    async def _go():
        return await mod.assign_roles(auth_subject='auth0|x', roles=['admin'])

    assert asyncio.run(_go()) == {'disabled': True}


def test_assign_roles_skips_when_auth_subject_missing(monkeypatch):
    from app.services import auth0_admin as mod

    def _enabled():
        return SimpleNamespace(
            auth0_domain='tenant.auth0.com',
            auth0_service_client_id='svc',
            auth0_service_client_secret='sec',
            auth0_service_client_secret_file=None,
            auth0_admin_client_id=None,
            auth0_admin_client_secret=None,
            auth0_admin_client_secret_file=None,
        )

    monkeypatch.setattr(mod, 'get_settings', _enabled)

    async def _go():
        return await mod.assign_roles(auth_subject=None, roles=['admin'])

    out = asyncio.run(_go())
    assert out == {'disabled': False, 'skipped': 'no_auth_subject'}


def test_revoke_tenant_roles_disabled_returns_disabled(monkeypatch):
    from app.services import auth0_admin as mod
    monkeypatch.setattr(mod, 'get_settings', _disabled_settings)

    async def _go():
        return await mod.revoke_tenant_roles(
            auth_subject='auth0|x', tenant_id=uuid4(),
        )

    assert asyncio.run(_go()) == {'disabled': True}


def test_revoke_tenant_roles_skips_when_subject_missing(monkeypatch):
    from app.services import auth0_admin as mod

    def _enabled():
        return SimpleNamespace(
            auth0_domain='tenant.auth0.com',
            auth0_service_client_id='svc',
            auth0_service_client_secret='sec',
            auth0_service_client_secret_file=None,
            auth0_admin_client_id=None,
            auth0_admin_client_secret=None,
            auth0_admin_client_secret_file=None,
        )

    monkeypatch.setattr(mod, 'get_settings', _enabled)

    async def _go():
        return await mod.revoke_tenant_roles(
            auth_subject=None, tenant_id=uuid4(),
        )

    out = asyncio.run(_go())
    assert out == {'disabled': False, 'skipped': 'no_auth_subject'}


def test_set_user_tenant_metadata_disabled(monkeypatch):
    from app.services import auth0_admin as mod
    monkeypatch.setattr(mod, 'get_settings', _disabled_settings)

    async def _go():
        return await mod.set_user_tenant_metadata(
            auth_subject='auth0|x', tenant_id=uuid4(),
        )

    assert asyncio.run(_go()) == {'disabled': True}


def test_assign_auth0_role_by_name_disabled(monkeypatch):
    from app.services import auth0_admin as mod
    monkeypatch.setattr(mod, 'get_settings', _disabled_settings)

    async def _go():
        return await mod.assign_auth0_role_by_name(
            auth_subject='auth0|x', role_name='admin',
        )

    assert asyncio.run(_go()) == {'disabled': True}


def test_assign_auth0_role_by_name_skips_when_subject_missing(monkeypatch):
    from app.services import auth0_admin as mod

    def _enabled():
        return SimpleNamespace(
            auth0_domain='tenant.auth0.com',
            auth0_service_client_id='svc',
            auth0_service_client_secret='sec',
            auth0_service_client_secret_file=None,
            auth0_admin_client_id=None,
            auth0_admin_client_secret=None,
            auth0_admin_client_secret_file=None,
        )

    monkeypatch.setattr(mod, 'get_settings', _enabled)

    async def _go():
        return await mod.assign_auth0_role_by_name(
            auth_subject=None, role_name='admin',
        )

    assert asyncio.run(_go()) == {'disabled': False, 'skipped': 'no_auth_subject'}
