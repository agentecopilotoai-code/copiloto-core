"""BUG-001 — el flujo de invite member fallaba con 403 Forbidden en
``POST /oauth/token`` porque el backend usaba las credenciales de la regular
web app del panel (sin ``client_credentials`` grant) en lugar de las de la
app M2M (``app_type=non_interactive``).

Estos tests bloquean la regresión:

- ``app/core/config.py`` debe declarar los settings ``auth0_service_*``.
- ``app/services/auth0_admin.py`` debe preferir las credenciales SERVICE,
  caer a las legacy ADMIN con un warning, y usar la pareja resuelta en el
  payload de ``/oauth/token``.
- ``scripts/configure-auth0.sh`` debe escribir BOTH bloques
  (``AUTH0_ADMIN_*`` para la regular web y ``AUTH0_SERVICE_*`` para la M2M)
  con sus respectivos ``*_SECRET_FILE``.
- El runtime debe emitir un log de error claro si Auth0 responde 403 al
  ``/oauth/token`` (pointer al BUG-001 + script).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

CONFIG = Path('app/core/config.py')
AUTH0_ADMIN = Path('app/services/auth0_admin.py')
SCRIPT = Path('scripts/configure-auth0.sh')
ENV_EXAMPLE = Path('.env.example')


# ── Static invariants on app/core/config.py ─────────────────────────────────


def test_config_declares_auth0_service_client_id():
    source = CONFIG.read_text()
    assert 'auth0_service_client_id: str | None' in source


def test_config_declares_auth0_service_client_secret_pair():
    source = CONFIG.read_text()
    assert 'auth0_service_client_secret: str | None' in source
    assert 'auth0_service_client_secret_file: str | None' in source


def test_config_keeps_legacy_auth0_admin_client_fields_for_panel_login():
    """The regular web app credentials are still needed for the Admin Panel
    Authorization Code flow (``app/admin/routes.py``). The fix must NOT
    remove them — only add the SERVICE counterparts."""
    source = CONFIG.read_text()
    assert 'auth0_admin_client_id: str | None' in source
    assert 'auth0_admin_client_secret: str | None' in source


# ── Static invariants on app/services/auth0_admin.py ────────────────────────


def test_auth0_admin_resolves_credentials_via_management_credentials_helper():
    source = AUTH0_ADMIN.read_text()
    assert 'def _management_credentials(settings)' in source
    # The /oauth/token payload now reads from the resolver, NOT directly from
    # settings.auth0_admin_client_id.
    token_block_start = source.index("url = f'https://{domain}/oauth/token'")
    token_block_end = source.index('response.raise_for_status()', token_block_start)
    block = source[token_block_start:token_block_end]
    assert '_management_credentials(settings)' in block
    assert "'client_id': client_id" in block
    assert "'client_secret': client_secret" in block
    # And explicitly NOT the old hard-coded admin reference:
    assert "'client_id': settings.auth0_admin_client_id" not in block


def test_auth0_admin_prefers_service_over_legacy_admin():
    source = AUTH0_ADMIN.read_text()
    start = source.index('def _management_credentials(settings)')
    end = source.index('def _management_client_secret', start)
    block = source[start:end]
    # SERVICE branch is checked first.
    service_idx = block.index('auth0_service_client_id')
    admin_idx = block.index('auth0_admin_client_id')
    assert service_idx < admin_idx, (
        'SERVICE creds must be evaluated before ADMIN fallback'
    )
    # And the ADMIN fallback emits a deprecation warning.
    assert 'legacy_admin_credentials_used_for_m2m' in block
    assert "ticket='BUG-001'" in block


def test_auth0_admin_logs_explicit_diagnostic_on_403():
    source = AUTH0_ADMIN.read_text()
    assert 'oauth_token_forbidden' in source
    # The error message should point operators at the script and the ticket.
    assert 'configure-auth0.sh' in source
    assert 'non_interactive' in source


def test_auth0_management_enabled_uses_resolver():
    source = AUTH0_ADMIN.read_text()
    start = source.index('def auth0_management_enabled()')
    end = source.index('\n\n', start)
    block = source[start:end]
    assert '_management_credentials(settings)' in block


# ── Runtime: credential preference order with mocked settings ───────────────


def _make_settings(**overrides):
    """Build a fake settings object with the attributes the resolver reads."""

    class _Stub:
        pass

    s = _Stub()
    s.auth0_domain = overrides.get('auth0_domain', 'example.auth0.com')
    s.auth0_service_client_id = overrides.get('auth0_service_client_id')
    s.auth0_service_client_secret = overrides.get('auth0_service_client_secret')
    s.auth0_service_client_secret_file = overrides.get('auth0_service_client_secret_file')
    s.auth0_admin_client_id = overrides.get('auth0_admin_client_id')
    s.auth0_admin_client_secret = overrides.get('auth0_admin_client_secret')
    s.auth0_admin_client_secret_file = overrides.get('auth0_admin_client_secret_file')
    return s


def test_management_credentials_prefers_service_when_both_set():
    from app.services.auth0_admin import _management_credentials

    s = _make_settings(
        auth0_service_client_id='svc-id',
        auth0_service_client_secret='svc-secret',
        auth0_admin_client_id='admin-id',
        auth0_admin_client_secret='admin-secret',
    )
    client_id, client_secret = _management_credentials(s)
    assert client_id == 'svc-id'
    assert client_secret == 'svc-secret'


def test_management_credentials_falls_back_to_admin_with_warning(capsys):
    from app.services.auth0_admin import _management_credentials

    s = _make_settings(
        auth0_admin_client_id='admin-id',
        auth0_admin_client_secret='admin-secret',
    )
    client_id, client_secret = _management_credentials(s)
    assert client_id == 'admin-id'
    assert client_secret == 'admin-secret'
    # structlog renders to stdout; assert the breadcrumb is emitted.
    captured = capsys.readouterr().out + capsys.readouterr().err
    # Re-capture in case structlog buffered to stderr instead.
    combined = captured
    assert (
        'legacy_admin_credentials_used_for_m2m' in combined
        or 'BUG-001' in combined
    )


def test_management_credentials_returns_none_pair_when_unconfigured():
    from app.services.auth0_admin import _management_credentials

    s = _make_settings()
    assert _management_credentials(s) == (None, None)


def test_management_credentials_ignores_service_id_without_secret():
    """A half-configured SERVICE pair must NOT shadow a working ADMIN pair.

    Otherwise a deployment that only set AUTH0_SERVICE_CLIENT_ID (but forgot
    the secret) would suddenly start sending ``client_secret=None`` to
    Auth0 — failing harder than the legacy behaviour.
    """
    from app.services.auth0_admin import _management_credentials

    s = _make_settings(
        auth0_service_client_id='svc-id',
        # no service secret
        auth0_admin_client_id='admin-id',
        auth0_admin_client_secret='admin-secret',
    )
    client_id, client_secret = _management_credentials(s)
    assert client_id == 'admin-id'
    assert client_secret == 'admin-secret'


# ── Runtime: get_management_token uses the SERVICE pair ─────────────────────


class _FakeResponse:
    def __init__(self, status_code=200, json_data=None):
        self.status_code = status_code
        self._json = json_data or {}
        self.content = b'{}' if json_data is None else b'1'
        self.text = ''

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            import httpx

            request = httpx.Request('POST', 'https://example.auth0.com/oauth/token')
            raise httpx.HTTPStatusError(
                f'{self.status_code}', request=request, response=self  # type: ignore[arg-type]
            )


class _FakeAsyncClient:
    def __init__(self, response):
        self._response = response
        self.calls: list[tuple[str, dict | None]] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def post(self, url, json=None):
        self.calls.append((url, json))
        return self._response


def _reset_token_cache():
    from app.services import auth0_admin

    auth0_admin._CACHED_TOKEN['token'] = None
    auth0_admin._CACHED_TOKEN['expires_at'] = 0.0


def test_get_management_token_uses_service_credentials(monkeypatch):
    from app.core.config import get_settings
    from app.services import auth0_admin

    monkeypatch.setenv('AUTH0_DOMAIN', 'example.auth0.com')
    monkeypatch.setenv('AUTH0_SERVICE_CLIENT_ID', 'svc-id')
    monkeypatch.setenv('AUTH0_SERVICE_CLIENT_SECRET', 'svc-secret')
    monkeypatch.delenv('AUTH0_ADMIN_CLIENT_ID', raising=False)
    monkeypatch.delenv('AUTH0_ADMIN_CLIENT_SECRET', raising=False)
    monkeypatch.delenv('AUTH0_ADMIN_CLIENT_SECRET_FILE', raising=False)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://example')
    monkeypatch.setenv('JWT_SECRET', 'local-secret-with-min-length')
    monkeypatch.setenv('SERVICE_TOKEN', 'service-token-with-min-length')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 's3-secret')
    get_settings.cache_clear()
    _reset_token_cache()

    fake_response = _FakeResponse(200, {'access_token': 'tok-xyz', 'expires_in': 3600})
    fake_client = _FakeAsyncClient(fake_response)

    with patch('app.services.auth0_admin.httpx.AsyncClient', return_value=fake_client):
        token = asyncio.run(auth0_admin.get_management_token())

    assert token == 'tok-xyz'
    assert len(fake_client.calls) == 1
    url, body = fake_client.calls[0]
    assert url == 'https://example.auth0.com/oauth/token'
    assert body['grant_type'] == 'client_credentials'
    assert body['client_id'] == 'svc-id'
    assert body['client_secret'] == 'svc-secret'


def test_get_management_token_returns_none_when_unconfigured(monkeypatch):
    from app.core.config import get_settings
    from app.services import auth0_admin

    monkeypatch.delenv('AUTH0_DOMAIN', raising=False)
    monkeypatch.delenv('AUTH0_SERVICE_CLIENT_ID', raising=False)
    monkeypatch.delenv('AUTH0_SERVICE_CLIENT_SECRET', raising=False)
    monkeypatch.delenv('AUTH0_ADMIN_CLIENT_ID', raising=False)
    monkeypatch.delenv('AUTH0_ADMIN_CLIENT_SECRET', raising=False)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://example')
    monkeypatch.setenv('JWT_SECRET', 'local-secret-with-min-length')
    monkeypatch.setenv('SERVICE_TOKEN', 'service-token-with-min-length')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 's3-secret')
    get_settings.cache_clear()
    _reset_token_cache()

    token = asyncio.run(auth0_admin.get_management_token())
    assert token is None


def test_get_management_token_logs_diagnostic_on_403(monkeypatch, capsys):
    import httpx

    from app.core.config import get_settings
    from app.services import auth0_admin

    monkeypatch.setenv('AUTH0_DOMAIN', 'example.auth0.com')
    monkeypatch.setenv('AUTH0_SERVICE_CLIENT_ID', 'wrong-id')
    monkeypatch.setenv('AUTH0_SERVICE_CLIENT_SECRET', 'wrong-secret')
    monkeypatch.delenv('AUTH0_ADMIN_CLIENT_ID', raising=False)
    monkeypatch.delenv('AUTH0_ADMIN_CLIENT_SECRET', raising=False)
    monkeypatch.delenv('AUTH0_ADMIN_CLIENT_SECRET_FILE', raising=False)
    monkeypatch.setenv('DATABASE_URL', 'postgresql://example')
    monkeypatch.setenv('JWT_SECRET', 'local-secret-with-min-length')
    monkeypatch.setenv('SERVICE_TOKEN', 'service-token-with-min-length')
    monkeypatch.setenv('S3_SECRET_ACCESS_KEY', 's3-secret')
    get_settings.cache_clear()
    _reset_token_cache()

    fake_response = _FakeResponse(403, None)
    fake_response.text = 'unauthorized_client'
    fake_client = _FakeAsyncClient(fake_response)

    with patch('app.services.auth0_admin.httpx.AsyncClient', return_value=fake_client):
        with pytest.raises(httpx.HTTPStatusError):
            asyncio.run(auth0_admin.get_management_token())

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert (
        'oauth_token_forbidden' in combined
        or 'BUG-001' in combined
        or 'configure-auth0.sh' in combined
    )


# ── Static invariants on scripts/configure-auth0.sh ─────────────────────────


def test_script_writes_both_admin_and_service_client_ids():
    source = SCRIPT.read_text()
    # The env file write must include both client_id lines and both
    # *_SECRET_FILE lines. The heredoc is delimited by EOF_AUTH0_ENV markers;
    # take the body between them (second occurrence onwards is the content).
    heredoc_open = source.index('<<EOF_AUTH0_ENV')
    body_start = source.index('\n', heredoc_open) + 1
    body_end = source.index('\nEOF_AUTH0_ENV', body_start)
    block = source[body_start:body_end]
    assert 'AUTH0_ADMIN_CLIENT_ID=$admin_client_id' in block
    assert 'AUTH0_SERVICE_CLIENT_ID=$service_client_id' in block
    assert 'AUTH0_ADMIN_CLIENT_SECRET_FILE=' in block
    assert 'AUTH0_SERVICE_CLIENT_SECRET_FILE=' in block


def test_script_creates_m2m_app_with_client_credentials_grant():
    source = SCRIPT.read_text()
    # The M2M (service) app must declare client_credentials in its grant_types
    # — that's the whole point of BUG-001. The regular web app must NOT.
    service_block_start = source.index('Upsert app M2M')
    service_block_end = source.index('Upsert client grant', service_block_start)
    service_block = source[service_block_start:service_block_end]
    assert 'non_interactive' in service_block
    assert 'client_credentials' in service_block

    admin_block_start = source.index('Upsert app $AUTH0_ADMIN_APP_NAME')
    admin_block_end = source.index('Upsert app M2M', admin_block_start)
    admin_block = source[admin_block_start:admin_block_end]
    assert 'regular_web' in admin_block
    # The regular_web app must use authorization_code + refresh_token, NOT
    # client_credentials — that's why BUG-001 hit production.
    assert '"client_credentials"' not in admin_block


def test_script_writes_service_secret_file():
    source = SCRIPT.read_text()
    assert 'write_secret_file "$AUTH0_SECRETS_DIR/auth0-service-client-secret"' in source
