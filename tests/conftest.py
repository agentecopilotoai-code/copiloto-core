"""Test-suite configuration del core."""
import os

# Env vars dummy para que ``app.main`` se importe sin requerir secrets/DB
# reales. Los tests unitarios mockean toda la capa de DB, así que estas URLs
# nunca se conectan.
os.environ.setdefault('DATABASE_URL', 'postgresql://x:x@localhost/x')
os.environ.setdefault('JWT_SECRET', 'x' * 32)
os.environ.setdefault('SERVICE_TOKEN', 'x' * 32)
os.environ.setdefault('S3_SECRET_ACCESS_KEY', 'x' * 32)
# Fernet key estable para tests — el helper `_get_secret_cipher` la usa al
# cifrar/descifrar API keys de proveedores IA. Generada vía
# Fernet.generate_key() y hardcoded para que los tests reproduzcan bytes
# idénticos.
os.environ.setdefault(
    'AI_PROVIDER_MASTER_KEY',
    'zmWmIxJtxg8Cu0AYJ0jZeXqGNbRkW9pTfLqo3GqAFEY=',
)

import app.main  # noqa: F401, E402  — side-effect: dispara el wiring completo.

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_http_clients_between_tests():
    """PERF-001 (audit 2026-05-27) — http_clients singletons leak entre tests.
    Tests que monkeypatchean `httpx.AsyncClient` necesitan ver un cache
    vacío para que el siguiente `get_*_client()` cree uno nuevo. Sin esto,
    el primer test crea el client real y los siguientes lo reusan
    bypaseando el monkeypatch."""
    from app.services import http_clients
    http_clients._reset_for_tests()
    yield
    http_clients._reset_for_tests()


@pytest.fixture(autouse=True)
def _reset_session_store_between_tests():
    """P0-3 (audit 2026-05-27) — el InMemorySessionStore es proceso-global.
    Tests que crean sesiones leakean entre tests si no reseteamos. Además,
    fixea el store a InMemory para tests (Redis no debe ser tocado salvo
    en tests dedicados que monkeypatchean settings.redis_url)."""
    from app.admin.session_store import (
        InMemorySessionStore, set_session_store_for_tests,
    )
    set_session_store_for_tests(InMemorySessionStore())
    yield
    set_session_store_for_tests(None)


@pytest.fixture(autouse=True)
def _reset_signup_rate_limiter_between_tests():
    """SEC-021 — el limiter de tenant-signup es proceso-global. Reset
    entre tests para evitar leak del bucket (un test que llama signup
    3 veces dejaría los siguientes con el counter saturado)."""
    from app.api.v1.handlers import tenant_signup_handlers
    tenant_signup_handlers._reset_signup_rate_limiter()
    yield
    tenant_signup_handlers._reset_signup_rate_limiter()


@pytest.fixture(autouse=True)
def _reset_oauth_state_store_between_tests():
    """P1-10 — InMemoryOAuthStateStore también es proceso-global. Tests
    del OAuth callback consumen state tokens; sin reset, el siguiente
    test que use el mismo state falla con replay rejection."""
    from app.admin.oauth_state_store import (
        InMemoryOAuthStateStore, set_oauth_state_store_for_tests,
    )
    set_oauth_state_store_for_tests(InMemoryOAuthStateStore())
    yield
    set_oauth_state_store_for_tests(None)
