"""HTTP-boundary E2E fixtures — spin up the real FastAPI app + ephemeral DB.

Where ``conftest_e2e.py`` exercises the service layer directly via ``asyncpg``,
this conftest builds the FastAPI ``app`` from ``app.main:create_app()`` and
issues real HTTP requests via Starlette's ``TestClient``. This catches:

* Middleware contracts (rate-limit, CORS, exception handlers).
* Auth dependencies (``authenticate_request``, ``require_min_role``,
  ``require_mfa_for_privileged``, ``require_platform_owner``).
* Cookie-based ``support_mode`` opt-in (BUG-008, AUDIT-49 dual service_token).
* Webhook entrypoints (Meta, Stripe, MercadoPago) including signature
  verification and freshness checks (AUDIT-48 / AUDIT-51 pre-scan).
* Response shape contracts (status code, headers, body keys).

Activation: identical to ``conftest_e2e`` — needs ``RUN_E2E=1`` +
``TEST_DATABASE_URL`` pointing at an ephemeral PostgreSQL with the schema
applied.  These fixtures REUSE the schema-bootstrapping done by
``conftest_e2e:_apply_schema`` (the suite shares the same DB across files).

Token forging:
    Tests need to send authenticated requests but the real Auth0 RS256 flow
    requires JWKS / a live Auth0 tenant. We work around that by setting
    ``auth0_domain=None`` for the in-process app (forces HS256 local fallback)
    and signing tokens with the ``jwt_secret`` from the test env. Real Auth0
    integration is covered by ``test_auth0_*_static.py`` and the manual
    smoke tests in ``docs/runbooks``.

Naming:
    These tests live in files named ``test_e2e_http_*.py`` so the existing
    ``test_journey_e2e.py`` (service-layer) and these HTTP-boundary suites
    can be discovered/run independently.
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid
from typing import Any, Callable

import pytest

from tests.conftest_e2e import (
    _apply_schema,
    _database_url,
    _require_ephemeral_e2e_url,
    e2e_enabled,
    tenant_connection,
)

# ── Bootstrap env so `app.main:create_app()` can be imported without crashing ─

# We set these BEFORE the app/test fixtures import `app.main` (which calls
# `get_settings()` at import time via the lazy `Settings` constructor). The
# real prod env values come from `.env`; here we override with test-safe ones.
_TEST_JWT_SECRET = 'test-jwt-secret-min-length-16'
_TEST_SERVICE_TOKEN = 'test-service-token-min-length-16'
_TEST_S3_SECRET = 'test-s3-secret'


def _require_e2e_http_env() -> str:
    """Hard-gate: same as `conftest_e2e._skip_unless_ready` but additionally
    seeds the env vars the FastAPI app needs to import. Returns the DSN."""
    if not e2e_enabled():
        pytest.skip('set RUN_E2E=1 to opt into HTTP E2E suite')
    url = _database_url()
    if not url:
        pytest.skip('set TEST_DATABASE_URL (or DATABASE_URL) for HTTP E2E')
    _require_ephemeral_e2e_url(url)
    os.environ['DATABASE_URL'] = url
    # FORCE these — overrides any .env / .env.auth0.local values pydantic-settings
    # loads from disk. We OVERWRITE (not setdefault) for determinism.
    os.environ['JWT_SECRET'] = _TEST_JWT_SECRET
    os.environ['SERVICE_TOKEN'] = _TEST_SERVICE_TOKEN
    os.environ['S3_SECRET_ACCESS_KEY'] = _TEST_S3_SECRET
    # Force the local HS256 path so token forging stays simple. pydantic-settings
    # treats an empty-string env var as "unset" only for `str | None` fields
    # IF an empty-string validator strips it. For `AUTH0_DOMAIN` (str | None,
    # no validator), an empty string parses as `''` — which is truthy enough
    # to trigger the RS256 path. We override with `'__disabled__'` AND patch
    # the security helpers to accept the local path when domain doesn't look
    # like a real Auth0 tenant. The cleanest path is to delete the keys AND
    # tell pydantic-settings not to load the .env file.
    os.environ.pop('AUTH0_DOMAIN', None)
    os.environ.pop('AUTH0_ISSUER', None)
    os.environ.pop('AUTH0_AUDIENCE', None)
    # Tell pydantic-settings to ignore the on-disk .env files.
    os.environ['SETTINGS_DISABLE_ENV_FILE'] = '1'
    # Disable MFA enforcement in HTTP E2E — we forge tokens directly and
    # don't simulate the full Auth0 challenge flow.
    os.environ['MFA_ENFORCEMENT_ENABLED'] = 'false'
    # Make rate limiter generous so tests don't trip the 60/min default.
    os.environ['RATE_LIMIT_PER_MIN'] = '10000'
    os.environ['RATE_LIMIT_WEBHOOK_PER_MIN'] = '10000'
    # Allow the local IP scheme used by TestClient (`testclient`) into /metrics.
    os.environ['OBSERVABILITY_ALLOWED_IPS'] = 'testclient,127.0.0.1'
    return url


@pytest.fixture(scope='session')
def e2e_http_dsn() -> str:
    """Session-scoped: validate env + return ephemeral DSN."""
    return _require_e2e_http_env()


@pytest.fixture(scope='session', autouse=False)
def e2e_http_schema(e2e_http_dsn: str) -> str:
    """Apply schema once per session if ``E2E_APPLY_SCHEMA=1`` is set. Returns
    the DSN. Tests requesting `http_app` transitively use this."""
    if os.getenv('E2E_APPLY_SCHEMA') == '1':
        asyncio.run(_apply_schema(e2e_http_dsn))
    return e2e_http_dsn


# ── FastAPI app + TestClient ────────────────────────────────────────────────


@pytest.fixture(scope='session')
def http_app(e2e_http_schema: str):
    """Build the FastAPI app once per session.

    `app.main:create_app()` reads `get_settings()` lazily — by the time we
    call it here, the env vars set in `_require_e2e_http_env` are in place.
    The DB pool is connected via the app's `lifespan` context manager (which
    `TestClient` triggers automatically when used as a context manager).

    We DISABLE the on-disk `.env` files at the pydantic-settings layer so
    AUTH0_DOMAIN (which a developer may have configured) doesn't leak in and
    push the auth decoder to RS256 — we want the HS256 local path for token
    forging. The monkeypatch is one-line: rewrite `Settings.model_config`
    `env_file=()` before any `Settings()` instantiation.
    """
    from app.core.config import Settings, get_settings  # noqa: PLC0415
    from pydantic_settings import SettingsConfigDict  # noqa: PLC0415

    # Rebuild model_config WITHOUT the env_file list (forces env-vars-only).
    Settings.model_config = SettingsConfigDict(
        env_file=(),
        env_file_encoding='utf-8',
        extra='ignore',
        populate_by_name=True,
    )
    get_settings.cache_clear()

    from app.main import create_app  # noqa: PLC0415

    return create_app()


@pytest.fixture
def http_client(http_app):
    """Per-test TestClient with the lifespan ACTIVE (so the DB pool is open).

    Each test gets a fresh client; cookies and headers don't leak between tests.
    """
    from fastapi.testclient import TestClient  # noqa: PLC0415

    with TestClient(http_app) as client:
        yield client


# ── Token forging (HS256 local fallback) ────────────────────────────────────


def _claims(
    *,
    sub: str,
    tenant_id: uuid.UUID | str,
    roles: list[str],
    namespace: str = 'https://copilotoia.com/claims/',
    ttl_seconds: int = 3600,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the claims dict the local HS256 decoder expects."""
    now = int(time.time())
    base = {
        'sub': sub,
        'iat': now,
        'exp': now + ttl_seconds,
        'iss': os.environ.get('JWT_ISSUER', 'copilotoia-local'),
        'aud': os.environ.get('JWT_AUDIENCE', 'copilotoia-panel'),
        f'{namespace}tenant_id': str(tenant_id),
        f'{namespace}roles': roles,
    }
    if extra:
        base.update(extra)
    return base


def forge_token(
    *,
    sub: str = 'auth0|test-user',
    tenant_id: uuid.UUID | str,
    roles: list[str],
    ttl_seconds: int = 3600,
    extra: dict[str, Any] | None = None,
) -> str:
    """Sign a JWT with the local HS256 secret. Tests put it in `Authorization`
    as ``Bearer <token>``."""
    from jose import jwt  # noqa: PLC0415

    secret = os.environ.get('JWT_SECRET', _TEST_JWT_SECRET)
    return jwt.encode(_claims(sub=sub, tenant_id=tenant_id, roles=roles, ttl_seconds=ttl_seconds, extra=extra), secret, algorithm='HS256')


def auth_headers(
    *,
    tenant_id: uuid.UUID | str,
    roles: list[str],
    sub: str = 'auth0|test-user',
    include_tenant_header: bool = True,
    ttl_seconds: int = 3600,
    extra: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Build the headers a tenant-scoped request needs.

    `extra` adds arbitrary claims (e.g. `{'sid': '...'}` for session tests).
    """
    token = forge_token(sub=sub, tenant_id=tenant_id, roles=roles, ttl_seconds=ttl_seconds, extra=extra)
    headers = {'Authorization': f'Bearer {token}'}
    if include_tenant_header:
        headers['X-Tenant-Id'] = str(tenant_id)
    return headers


def service_headers(tenant_id: uuid.UUID | str | None = None) -> dict[str, str]:
    """Headers for service-to-service auth (bypasses tenant checks via support_mode)."""
    headers = {'Authorization': f'Bearer {os.environ.get("SERVICE_TOKEN", _TEST_SERVICE_TOKEN)}'}
    if tenant_id is not None:
        headers['X-Tenant-Id'] = str(tenant_id)
    return headers


# ── Tenant + user seed helpers ──────────────────────────────────────────────


async def _seed_tenant_with_user(
    url: str,
    *,
    label: str,
    role: str = 'admin',
    auth_subject: str = 'auth0|test-user',
) -> tuple[uuid.UUID, uuid.UUID]:
    """Create a tenant + an associated ``app.users`` + ``user_tenant_roles``
    row so ``ensure_tenant_access`` resolves to ``role`` for ``auth_subject``.

    Returns ``(tenant_id, user_id)``.
    """
    import asyncpg

    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    conn = await asyncpg.connect(url)
    try:
        await conn.execute("select set_config('app.support_mode', 'true', false)")
        await conn.execute(
            "select set_config('app.tenant_id', $1, false)", str(tenant_id)
        )
        async with conn.transaction():
            await conn.execute(
                """
                insert into app.tenants
                  (id, slug, legal_name, display_name, vertical_code,
                   country_code, timezone, status)
                values ($1, $2, $3, $3, 'general', 'CO', 'America/Bogota', 'active')
                """,
                tenant_id,
                f'tenant-http-{label}-{tenant_id.hex[:8]}',
                f'HTTP E2E {label}',
            )
            await conn.execute(
                """
                insert into app.tenant_settings (tenant_id)
                values ($1)
                """,
                tenant_id,
            )
            await conn.execute(
                """
                insert into app.users (id, auth_subject, email, display_name, status)
                values ($1, $2, $3, $4, 'active')
                """,
                user_id,
                auth_subject,
                f'user-{user_id.hex[:8]}@example.local',
                f'E2E HTTP User {label}',
            )
            await conn.execute(
                """
                insert into app.user_tenant_roles (user_id, tenant_id, role)
                values ($1, $2, $3)
                """,
                user_id,
                tenant_id,
                role,
            )
    finally:
        await conn.close()
    return tenant_id, user_id


async def _delete_tenant(url: str, tenant_id: uuid.UUID) -> None:
    import asyncpg

    conn = await asyncpg.connect(url)
    try:
        await conn.execute("select set_config('app.support_mode', 'true', false)")
        await conn.execute('delete from app.tenants where id=$1', tenant_id)
    finally:
        await conn.close()


class TenantContext:
    """Bundle that `http_tenant_factory` returns. Tests use `.headers(...)` to
    get auth headers pre-wired with the seeded subject — no risk of forging
    a JWT whose `sub` doesn't match a DB row."""

    __slots__ = ('tenant_id', 'user_id', 'auth_subject', 'role')

    def __init__(self, *, tenant_id: uuid.UUID, user_id: uuid.UUID, auth_subject: str, role: str) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.auth_subject = auth_subject
        self.role = role

    def headers(self, *, roles: list[str] | None = None, extra_claims: dict[str, Any] | None = None) -> dict[str, str]:
        """Build auth headers with the right `sub` and matching tenant header."""
        roles_to_send = roles if roles is not None else [self.role]
        return auth_headers(
            tenant_id=self.tenant_id,
            roles=roles_to_send,
            sub=self.auth_subject,
        ) | (
            {}  # placeholder — `extra_claims` is for future use
            if not extra_claims else {}
        )

    # Backwards-compat tuple unpacking: `tenant_id, user_id, sub = factory(...)`.
    def __iter__(self):
        return iter((self.tenant_id, self.user_id, self.auth_subject))


@pytest.fixture
def http_tenant_factory(e2e_http_schema: str) -> Callable[..., TenantContext]:
    """Per-test factory that returns a `TenantContext` (also unpackable as
    `tenant_id, user_id, auth_subject` for backwards compatibility)."""
    created: list[uuid.UUID] = []

    def _factory(*, label: str = 'http', role: str = 'admin', auth_subject: str | None = None) -> TenantContext:
        subject = auth_subject or f'auth0|test-{uuid.uuid4().hex[:8]}'
        tenant_id, user_id = asyncio.run(
            _seed_tenant_with_user(e2e_http_schema, label=label, role=role, auth_subject=subject)
        )
        created.append(tenant_id)
        return TenantContext(
            tenant_id=tenant_id,
            user_id=user_id,
            auth_subject=subject,
            role=role,
        )

    yield _factory

    if created:
        async def _cleanup() -> None:
            for tid in created:
                try:
                    await _delete_tenant(e2e_http_schema, tid)
                except Exception:
                    pass
        asyncio.run(_cleanup())


__all__ = (
    'auth_headers',
    'e2e_http_dsn',
    'e2e_http_schema',
    'forge_token',
    'http_app',
    'http_client',
    'http_tenant_factory',
    'service_headers',
    'tenant_connection',
)
