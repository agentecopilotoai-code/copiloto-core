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
