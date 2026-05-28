"""Tests para `copiloto_core.bootstrap` (v1.2.0 — comando bootstrap).

No tocamos una DB real — usamos un `FakeConn` que graba las queries +
simula el estado de `app.schema_migrations`. Eso cubre la lógica de
idempotencia + el orden de aplicación + el manejo del seed.

Tests E2E contra postgres real viven en `test_integration_*` (out of
scope acá por velocidad + setup).
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from copiloto_core.bootstrap import (
    BootstrapError,
    _APP_USER_RE,
    _PLATFORM_SQL_FILES,
    apply_platform_schema,
)


class FakeConn:
    """Pretende ser asyncpg.Connection.

    Mantiene un dict `applied_versions: set[str]` para simular el
    estado de `app.schema_migrations` entre llamadas. Acepta los
    INSERT/SELECT que el bootstrap hace y los registra en `calls`
    para que los tests aserten qué pasó.
    """

    def __init__(self, *, platform_table_exists: bool = False) -> None:
        self.platform_table_exists = platform_table_exists
        self.applied_versions: set[str] = set()
        self.existing_roles: set[str] = set()
        self.executed_sql: list[str] = []
        # Lista de (sql, args) en orden para tests más estrictos
        self.calls: list[tuple[str, tuple]] = []

    async def fetchval(self, sql: str, *args: Any) -> Any:
        self.calls.append((sql, args))
        # Check si la tabla existe
        if "to_regclass('app.schema_migrations')" in sql:
            return 'app.schema_migrations' if self.platform_table_exists else None
        # Check si rol existe
        if 'pg_roles' in sql and 'rolname' in sql:
            return 1 if (args and args[0] in self.existing_roles) else None
        return None

    async def fetch(self, sql: str, *args: Any) -> list[dict]:
        self.calls.append((sql, args))
        if 'app.schema_migrations' in sql and 'version' in sql:
            return [{'version': v} for v in self.applied_versions]
        return []

    async def execute(self, sql: str, *args: Any) -> str:
        self.calls.append((sql, args))
        self.executed_sql.append(sql)
        # Simular el efecto de aplicar 10-core.sql → tabla existe
        if 'create schema if not exists app' in sql.lower() or \
           'app.schema_migrations' in sql.lower() and 'create' in sql.lower():
            self.platform_table_exists = True
        # Trackear insert de versions
        if 'insert into app.schema_migrations' in sql.lower():
            if len(args) >= 2:
                self.applied_versions.add(args[1])
        # CREATE ROLE
        if sql.lower().startswith('create role'):
            tokens = sql.split()
            if len(tokens) >= 3:
                self.existing_roles.add(tokens[2])
        return 'OK'


def _run(coro):
    return asyncio.run(coro)


# ─── Apply platform schema — happy path ──────────────────────────────────


def test_apply_platform_schema_fresh_db_applies_both_files():
    conn = FakeConn(platform_table_exists=False)
    applied = _run(apply_platform_schema(conn))
    assert applied == list(_PLATFORM_SQL_FILES)
    # 10-core.sql + 20-seed.sql aplicados
    assert '10-core' in conn.applied_versions
    assert '20-seed' in conn.applied_versions


def test_apply_platform_schema_idempotent_second_run():
    conn = FakeConn(platform_table_exists=True)
    conn.applied_versions = {'10-core', '20-seed'}
    applied = _run(apply_platform_schema(conn))
    assert applied == []


def test_apply_platform_schema_partial_apply_continues():
    """Si solo 10-core está aplicado, debe aplicar solo 20-seed."""
    conn = FakeConn(platform_table_exists=True)
    conn.applied_versions = {'10-core'}
    applied = _run(apply_platform_schema(conn))
    assert applied == ['20-seed.sql']


def test_apply_platform_schema_no_seed():
    conn = FakeConn(platform_table_exists=False)
    applied = _run(apply_platform_schema(conn, seed=False))
    assert applied == ['10-core.sql']
    assert '20-seed' not in conn.applied_versions


def test_seed_sets_allow_seed_session_var():
    """El bootstrap setea `app.allow_seed='true'` antes del 20-seed para
    bypassear el guard de DB name (dev|test|local)."""
    conn = FakeConn(platform_table_exists=False)
    _run(apply_platform_schema(conn))
    # Hay UN execute con set local app.allow_seed
    matches = [s for s in conn.executed_sql if 'allow_seed' in s]
    assert matches, f'esperaba un SET local app.allow_seed, ejecutados: {conn.executed_sql[:5]}'


# ─── Create app user ────────────────────────────────────────────────────


def test_create_app_user_requires_credentials():
    conn = FakeConn()
    with pytest.raises(BootstrapError, match='requiere app_user y app_password'):
        _run(apply_platform_schema(conn, create_app_user=True))


def test_create_app_user_creates_role_if_not_exists():
    conn = FakeConn()
    _run(apply_platform_schema(
        conn,
        create_app_user=True,
        app_user='copiloto_app',
        app_password='secret123',
    ))
    # Hubo un CREATE ROLE
    create_calls = [s for s in conn.executed_sql if 'create role' in s.lower()]
    assert len(create_calls) == 1
    assert 'copiloto_app' in create_calls[0]


def test_create_app_user_skips_if_exists():
    conn = FakeConn()
    conn.existing_roles.add('copiloto_app')
    _run(apply_platform_schema(
        conn,
        create_app_user=True,
        app_user='copiloto_app',
        app_password='secret123',
    ))
    create_calls = [s for s in conn.executed_sql if s.lower().startswith('create role')]
    assert create_calls == []


def test_app_user_password_with_quote_is_escaped():
    """Password con `'` debe escaparse para no romper la SQL injection-safe."""
    conn = FakeConn()
    _run(apply_platform_schema(
        conn,
        create_app_user=True,
        app_user='copiloto_app',
        app_password="it's complicated",
    ))
    create_calls = [s for s in conn.executed_sql if s.lower().startswith('create role')]
    assert len(create_calls) == 1
    # `'` debe haberse duplicado a `''`
    assert "it''s complicated" in create_calls[0]
    assert "it's complicated" not in create_calls[0].replace("''", '')


@pytest.mark.parametrize('bad_user', [
    '1foo', 'Foo', 'foo-bar', 'foo bar', 'x' * 32,
    "foo'; drop table users; --",
])
def test_invalid_app_user_raises(bad_user: str):
    conn = FakeConn()
    with pytest.raises(BootstrapError, match='app_user inválido'):
        _run(apply_platform_schema(
            conn,
            create_app_user=True,
            app_user=bad_user,
            app_password='pw',
        ))


def test_empty_app_user_raises_at_arg_validation():
    """Empty string cae en la validación temprana (antes del regex)."""
    conn = FakeConn()
    with pytest.raises(BootstrapError, match='requiere app_user y app_password'):
        _run(apply_platform_schema(
            conn,
            create_app_user=True,
            app_user='',
            app_password='pw',
        ))


# ─── Reading platform SQL from package resources ─────────────────────────


def test_platform_sql_files_are_readable_from_package():
    """Verifica que los .sql se empaquetan correctamente y son leíbles
    via importlib.resources (no asume layout filesystem)."""
    from copiloto_core.bootstrap import _read_platform_sql

    for f in _PLATFORM_SQL_FILES:
        content = _read_platform_sql(f)
        assert len(content) > 100, f'{f} parece vacío o no encontrado'
        assert 'app' in content.lower()


def test_platform_sql_files_contain_expected_schema():
    """10-core.sql debe crear el schema `app` y tablas críticas."""
    from copiloto_core.bootstrap import _read_platform_sql

    core_sql = _read_platform_sql('10-core.sql')
    assert 'create schema if not exists app' in core_sql.lower()
    # Tablas core esperadas
    for table in ('tenants', 'users', 'capability', 'role'):
        assert f'app.{table}' in core_sql.lower(), f'tabla app.{table} faltante en 10-core.sql'


def test_seed_sql_has_allow_seed_guard():
    from copiloto_core.bootstrap import _read_platform_sql

    seed = _read_platform_sql('20-seed.sql')
    # Confirmamos que el guard sigue existiendo (sino el bootstrap
    # podría seedear datos demo en prod sin que lo notemos)
    assert 'app.allow_seed' in seed
    assert 'dev|test|local' in seed


# ─── CLI integration ────────────────────────────────────────────────────


def test_app_user_regex_rejects_sql_injection():
    """Defensa en profundidad: el regex debe rechazar caracteres que
    podrían usarse para escapar el contexto SQL si alguna vez nos
    olvidamos del escape del password."""
    bad = ["'; drop table users;--", 'foo;bar', 'foo bar', 'foo-bar']
    for b in bad:
        assert not _APP_USER_RE.match(b), f'esperaba reject de: {b!r}'


def test_app_user_regex_accepts_canonical_names():
    for ok in ['app', 'copiloto_app', 'satguajira_app', 'a1', 'a_b_c']:
        assert _APP_USER_RE.match(ok), f'esperaba accept de: {ok!r}'


# ─── v1.3.3: orden de operaciones — rol ANTES de los SQLs ────────────────


def test_create_app_user_runs_before_platform_sqls():
    """Regression: 10-core.sql hace `GRANT ... TO copiloto_app` hard-coded.
    Si el rol no existe cuando se ejecutan los GRANTs, postgres aborta
    con UndefinedObjectError. El rol DEBE crearse antes de los SQLs."""
    conn = FakeConn(platform_table_exists=False)
    _run(apply_platform_schema(
        conn,
        create_app_user=True,
        app_user='copiloto_app',
        app_password='pw',
    ))

    # Encontrá los índices en el orden de ejecución
    create_role_idx = next(
        (i for i, sql in enumerate(conn.executed_sql)
         if sql.lower().startswith('create role')),
        None,
    )
    # 10-core.sql se ejecutó como UN solo `await conn.execute(sql_text)`
    # — el FakeConn lo registra como 'create schema if not exists app'
    # o similar. Buscamos el primer execute "grande" (proxy del SQL file).
    first_long_sql_idx = next(
        (i for i, sql in enumerate(conn.executed_sql)
         if 'create schema if not exists app' in sql.lower()
         or 'create table' in sql.lower()),
        None,
    )

    assert create_role_idx is not None, 'no se ejecutó CREATE ROLE'
    assert first_long_sql_idx is not None, 'no se ejecutó 10-core.sql'
    assert create_role_idx < first_long_sql_idx, (
        f'CREATE ROLE (idx {create_role_idx}) debe ir ANTES de los SQLs '
        f'(idx {first_long_sql_idx}) — sino los GRANTs internos fallan.'
    )


def test_grants_applied_after_sqls():
    """Los GRANTs sobre `app.*` deben aplicarse DESPUÉS de los SQLs (que
    crean el schema). Sino postgres aborta con `schema "app" does not exist`."""
    conn = FakeConn(platform_table_exists=False)
    _run(apply_platform_schema(
        conn,
        create_app_user=True,
        app_user='copiloto_app',
        app_password='pw',
    ))

    # Encontrar idx del último grant explícito a copiloto_app (los del
    # _grant_app_role_permissions, post-SQLs)
    grant_idx = next(
        (i for i in range(len(conn.executed_sql) - 1, -1, -1)
         if 'grant usage on schema app' in conn.executed_sql[i].lower()
         and 'copiloto_app' in conn.executed_sql[i]),
        None,
    )
    sql_apply_idx = next(
        (i for i, sql in enumerate(conn.executed_sql)
         if 'create schema if not exists app' in sql.lower()
         or 'create table' in sql.lower()),
        None,
    )

    assert grant_idx is not None and sql_apply_idx is not None
    assert grant_idx > sql_apply_idx, (
        f'GRANTs sobre app.* (idx {grant_idx}) deben ir DESPUÉS de '
        f'los SQLs (idx {sql_apply_idx}).'
    )
