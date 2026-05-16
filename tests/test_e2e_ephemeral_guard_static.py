"""SEC-010 (Hardcoded E2E DB role password) — defienden el ephemeral guard.

El finding original era: ``_apply_schema`` en ``tests/conftest_e2e.py``
hace ``drop schema if exists app cascade`` Y crea el rol ``copiloto_app``
con password conocido (``'copiloto_app_e2e'``). Sin un guard, un developer
que corra ``RUN_E2E=1 pytest`` con ``DATABASE_URL`` apuntando a prod
podría:

1. Borrar TODO el schema ``app`` de producción.
2. Recrear el rol ``copiloto_app`` con un password trivial conocido.

El fix agrega ``_require_ephemeral_e2e_url(url)`` que rechaza HARD
(``RuntimeError``, no ``pytest.skip``) cualquier URL que no matchee un
patrón obviamente efímero (host ``localhost``/``127.0.0.1``/etc, o db
con marker ``_e2e``/``_test``/etc). El guard se invoca en DOS lugares
(defense en profundidad): el fixture session que gatea el suite
(``_skip_unless_ready``) Y el helper destructivo
(``_apply_schema``) para cubrir el caso de scripts que invoquen
``_apply_schema`` directo.

Si alguno de los invariantes se rompe, una próxima corrida descuidada
podría borrar producción.
"""
from __future__ import annotations

import inspect
import textwrap
from pathlib import Path

import pytest

from tests import conftest_e2e

CONFTEST_E2E = Path('tests/conftest_e2e.py')
RLS_E2E = Path('tests/test_rls_multitenant_e2e.py')


def _handler_source(name: str) -> str:
    return textwrap.dedent(inspect.getsource(getattr(conftest_e2e, name)))


# ───── _is_ephemeral_e2e_url: matching de hosts / db markers ─────────────


def test_localhost_variants_recognized_as_ephemeral():
    """Los hosts locales típicos deben ser reconocidos sin necesidad de
    markers en el nombre de la DB. IPv6 requiere notación con brackets en
    URLs (RFC 2732)."""
    cases = (
        ('localhost', 'postgresql://user:pass@localhost:5432/copilotoia'),
        ('127.0.0.1', 'postgresql://user:pass@127.0.0.1:5432/copilotoia'),
        ('::1', 'postgresql://user:pass@[::1]:5432/copilotoia'),
        ('host.docker.internal', 'postgresql://user:pass@host.docker.internal:5432/copilotoia'),
    )
    for host, url in cases:
        ok, reason = conftest_e2e._is_ephemeral_e2e_url(url)
        assert ok is True, f'host {host} should be ephemeral but got: {reason}'


def test_ephemeral_host_prefixes_recognized():
    """CI runners suelen usar nombres como `e2e-postgres-1` o
    `test-pg-cluster` para los containers efímeros."""
    for host in ('e2e-postgres', 'test-pg-1', 'ci-db-cluster'):
        url = f'postgresql://user:pass@{host}:5432/copilotoia'
        ok, reason = conftest_e2e._is_ephemeral_e2e_url(url)
        assert ok is True, f'host {host} should be ephemeral but got: {reason}'


def test_ephemeral_db_markers_recognized_even_with_prod_host():
    """Si la URL apunta a un host prod-like pero la DB se llama explícitamente
    ``copilotoia_e2e``, lo aceptamos — convención de DBA usar la misma
    instancia prod-like con databases separados."""
    for db_name in (
        'copilotoia_e2e',
        'e2e_copilotoia',
        'copilotoia_test',
        'test_copilotoia',
        'copilotoia_ci',
    ):
        url = f'postgresql://user:pass@db.acme.com:5432/{db_name}'
        ok, reason = conftest_e2e._is_ephemeral_e2e_url(url)
        assert ok is True, f'db {db_name} should be ephemeral but got: {reason}'


def test_prod_like_url_rejected():
    """Caso central del fix: una URL prod-like sin marker efímero debe ser
    rechazada. Sin el guard, RUN_E2E=1 contra esta URL haría DROP SCHEMA
    + sobrescribiría el password del rol copiloto_app."""
    url = 'postgresql://copilotoia:realsecret@prod-db.acme.com:5432/copilotoia'
    ok, reason = conftest_e2e._is_ephemeral_e2e_url(url)
    assert ok is False
    # El reason debe ser explícito sobre qué falló — el operador necesita
    # entender por qué.
    assert 'prod-db.acme.com' in reason
    assert 'ephemeral' in reason.lower()


def test_rejection_reason_does_not_leak_password():
    """Defense en profundidad: el reason va a stderr/logs, NUNCA debe
    incluir la URL completa porque puede tener un password embebido."""
    url = 'postgresql://copilotoia:SUPER_SECRET_PROD_PWD@prod.db.acme.com:5432/copilotoia'
    ok, reason = conftest_e2e._is_ephemeral_e2e_url(url)
    assert ok is False
    assert 'SUPER_SECRET_PROD_PWD' not in reason
    assert 'copilotoia:' not in reason  # avoid user:pass leak


def test_malformed_url_returns_false_with_clear_reason():
    """URLs corruptas deben rechazarse con un mensaje útil — no crash."""
    ok, reason = conftest_e2e._is_ephemeral_e2e_url('not a url at all')
    # urlsplit accepta strings raros sin raise, así que la rama "malformed"
    # solo aplica a casos verdaderamente patológicos. La rama normal de
    # rechazo (host vacío) es la que captura esto.
    assert ok is False
    assert len(reason) > 0


# ───── _require_ephemeral_e2e_url: aborta hard ───────────────────────────


def test_require_ephemeral_raises_for_prod_like_url():
    """El guard debe RAISE (no skip, no warning) cuando la URL no es
    efímera. Un skip silencioso ocultaría la misconfiguración."""
    url = 'postgresql://app:secret@prod.acme.com:5432/copilotoia'
    with pytest.raises(RuntimeError) as excinfo:
        conftest_e2e._require_ephemeral_e2e_url(url)
    # El error debe mencionar SEC-010 + qué hacer.
    assert 'SEC-010' in str(excinfo.value)
    assert 'ephemeral' in str(excinfo.value).lower()


def test_require_ephemeral_passes_for_localhost():
    """Sanity: localhost no debe hacer raise."""
    url = 'postgresql://app:secret@localhost:5432/copilotoia'
    conftest_e2e._require_ephemeral_e2e_url(url)  # no raise


def test_require_ephemeral_passes_for_e2e_db_name():
    """Sanity: nombre con marker _e2e no debe hacer raise."""
    url = 'postgresql://app:secret@db.acme.com:5432/copilotoia_e2e'
    conftest_e2e._require_ephemeral_e2e_url(url)  # no raise


# ───── Defense en profundidad: ambos sitios invocan el guard ─────────────


def test_skip_unless_ready_invokes_ephemeral_guard():
    """El path normal (test collection) debe pasar por el guard. Si alguien
    quita esa línea pensando que es redundante, el bug regresa."""
    src = _handler_source('_skip_unless_ready')
    assert '_require_ephemeral_e2e_url(url)' in src


def test_apply_schema_invokes_ephemeral_guard():
    """Defense en profundidad: si un script bypassa el fixture y llama
    _apply_schema directo, el segundo guard lo intercepta antes del DROP.
    """
    src = _handler_source('_apply_schema')
    assert '_require_ephemeral_e2e_url(url)' in src
    # El guard debe correr ANTES de cualquier conn.execute destructivo.
    guard_pos = src.find('_require_ephemeral_e2e_url(url)')
    connect_pos = src.find('await asyncpg.connect(url)')
    assert guard_pos < connect_pos, (
        '_require_ephemeral_e2e_url debe correr ANTES de abrir la conexión — '
        'una conexión a la DB equivocada ya es un problema (puede aparecer en logs)'
    )


def test_rls_e2e_suite_invokes_ephemeral_guard():
    """El otro suite E2E (RLS multitenant) hace DELETEs masivos sobre `app`.
    También debe invocar el guard."""
    src = RLS_E2E.read_text()
    assert '_require_ephemeral_e2e_url' in src, (
        'tests/test_rls_multitenant_e2e.py debe importar y usar el guard de '
        'SEC-010 — DELETE FROM app.* contra prod también es catastrófico'
    )


# ───── Skip se mantiene para RUN_E2E unset / URL missing ─────────────────


def test_skip_path_still_skips_not_raises_when_run_e2e_unset(monkeypatch):
    """Cuando RUN_E2E no está set, el comportamiento histórico (skip) se
    mantiene — el guard solo se activa CUANDO el suite quiere correr."""
    monkeypatch.delenv('RUN_E2E', raising=False)
    with pytest.raises(pytest.skip.Exception):
        conftest_e2e._skip_unless_ready()


def test_skip_path_still_skips_when_url_missing(monkeypatch):
    """Cuando RUN_E2E=1 pero TEST_DATABASE_URL/DATABASE_URL no, mantenemos
    skip — el operador olvidó configurar la URL, no es un caso de
    misconfiguración peligrosa."""
    monkeypatch.setenv('RUN_E2E', '1')
    monkeypatch.delenv('TEST_DATABASE_URL', raising=False)
    monkeypatch.delenv('DATABASE_URL', raising=False)
    with pytest.raises(pytest.skip.Exception):
        conftest_e2e._skip_unless_ready()


def test_skip_path_raises_runtimeerror_for_prod_like_url(monkeypatch):
    """Path central del fix: RUN_E2E=1 + URL prod-like → RuntimeError, NO
    skip. Esto es la diferencia que cierra el bug."""
    monkeypatch.setenv('RUN_E2E', '1')
    monkeypatch.setenv(
        'TEST_DATABASE_URL',
        'postgresql://app:secret@prod-db.acme.com:5432/copilotoia',
    )
    with pytest.raises(RuntimeError, match='SEC-010'):
        conftest_e2e._skip_unless_ready()


# ───── AST anti-regression: no podemos perder el guard silenciosamente ───


def test_conftest_e2e_module_exposes_validator():
    """La función debe existir con la firma esperada — un PR futuro no
    puede borrarla sin disparar este test."""
    assert hasattr(conftest_e2e, '_is_ephemeral_e2e_url')
    assert hasattr(conftest_e2e, '_require_ephemeral_e2e_url')
    sig = inspect.signature(conftest_e2e._is_ephemeral_e2e_url)
    assert 'url' in sig.parameters


def test_ephemeral_hosts_includes_minimum_safe_set():
    """Anti-regression: nadie debe poder hacer el guard "más estricto"
    rompiendo dev local. Estos hosts son la base mínima."""
    for host in ('localhost', '127.0.0.1'):
        assert host in conftest_e2e._EPHEMERAL_HOSTS


def test_ephemeral_db_markers_includes_minimum_safe_set():
    """Anti-regression: los markers _e2e y _test son los más comunes en
    DBA conventions — no removerlos sin actualizar este test Y las docs."""
    for marker in ('_e2e', '_test'):
        assert marker in conftest_e2e._EPHEMERAL_DB_MARKERS


# ───── Documentación del módulo menciona el guard ────────────────────────


def test_conftest_e2e_module_docstring_mentions_sec010():
    """El docstring del módulo debe documentar el guard para que un
    contribuidor no piense que es lógica de skip 'extra' que puede
    simplificar."""
    src = CONFTEST_E2E.read_text()
    assert 'SEC-010' in src
    assert 'ephemeral' in src.lower()
