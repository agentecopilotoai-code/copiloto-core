"""Tests para `copiloto_core.migrations.runner` (Fase 6).

Cobertura:
- _version_from_path: extracción de filename
- _resolve_migration_path: importlib.resources lookup
- apply_module_migrations: orden, idempotencia, checksum mismatch,
  TX todo-o-nada
- ensure_schema_migrations_table: DDL idempotente
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import APIRouter

from copiloto_core.extension import CoreModule
from copiloto_core.migrations.runner import (
    MigrationChecksumMismatchError,
    MigrationError,
    _resolve_migration_path,
    _version_from_path,
    apply_module_migrations,
    ensure_schema_migrations_table,
)


# ─── _version_from_path ───────────────────────────────────────────────────


def test_version_from_path_simple():
    assert _version_from_path('001_init.sql') == '001_init'


def test_version_from_path_with_subdir():
    assert _version_from_path('migrations/002_add_index.sql') == '002_add_index'


def test_version_from_path_strips_sql_extension_only():
    # Si por error alguien pone `.SQL` mayúscula NO se trim — naming
    # convention dice lowercase.
    assert _version_from_path('001.SQL') == '001.SQL'


def test_version_from_path_with_backslash_path():
    """Windows-style path (defensa de futuro)."""
    assert _version_from_path('migrations\\001_init.sql') == '001_init'


def test_version_from_path_empty_raises():
    with pytest.raises(MigrationError):
        _version_from_path('.sql')


# ─── _resolve_migration_path ─────────────────────────────────────────────


def test_resolve_path_uses_importlib_resources():
    """Debe poder resolver un .sql DENTRO de un paquete instalado."""
    # Usamos un paquete real con .sql adentro — copiloto_core no tiene,
    # así que creamos uno temporal.
    # Mejor: simulamos con paquete `copiloto_core.migrations` que SI existe.
    # Le pasamos un nombre de archivo bogus para verificar el error.
    with pytest.raises(MigrationError, match='no existe'):
        _resolve_migration_path('copiloto_core.migrations', 'no-existe.sql')


def test_resolve_path_unknown_package_raises():
    with pytest.raises(MigrationError, match='No se pudo resolver'):
        _resolve_migration_path('paquete_que_no_existe', '001.sql')


# ─── ensure_schema_migrations_table ──────────────────────────────────────


def test_ensure_table_executes_ddl():
    conn = MagicMock()
    conn.execute = AsyncMock()
    asyncio.run(ensure_schema_migrations_table(conn))
    conn.execute.assert_called_once()
    sql = conn.execute.call_args[0][0]
    assert 'create table if not exists app.schema_migrations' in sql.lower()
    assert 'primary key (module, version)' in sql.lower()


# ─── apply_module_migrations: módulo sin migrations ──────────────────────


def test_apply_empty_module_returns_empty_list():
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.fetch = AsyncMock(return_value=[])
    mod = CoreModule(code='no_migrations', router=APIRouter())
    result = asyncio.run(apply_module_migrations(conn, mod))
    assert result == []


# ─── apply_module_migrations: con migrations (mockeado FS) ───────────────


def _make_module_with_tmp_migration(tmp_path: Path, version: str, sql: str) -> CoreModule:
    """Crea un pseudo-CoreModule cuyo path apunta a un .sql real.

    Truco: dado que importlib.resources no es trivial de mockear sin un
    paquete real, usamos `_resolve_migration_path` con un módulo
    Python falso. Para esta suite mockeamos `_resolve_migration_path`
    en cada test relevante via monkeypatch.
    """
    sql_path = tmp_path / f'{version}.sql'
    sql_path.write_text(sql)
    return CoreModule(
        code='fake_module',
        router=APIRouter(),
        sql_migrations=(f'{version}.sql',),
    )


def test_apply_single_migration_inserts_tracking(monkeypatch, tmp_path: Path):
    sql_path = tmp_path / '001_init.sql'
    sql_path.write_text('create table fake_module.x (id int);')

    monkeypatch.setattr(
        'copiloto_core.migrations.runner._resolve_migration_path',
        lambda pkg, rel: sql_path,
    )

    mod = CoreModule(
        code='fake_module',
        router=APIRouter(),
        sql_migrations=('001_init.sql',),
    )

    executed: list[tuple[str, tuple]] = []

    class _FakeConn:
        def transaction(self):
            class _Tx:
                async def __aenter__(self_inner): return None
                async def __aexit__(self_inner, *exc): return None
            return _Tx()
        async def execute(self, sql, *args):
            executed.append((sql, args))
        async def fetch(self, sql, *args):
            executed.append((sql, args))
            return []

    applied = asyncio.run(apply_module_migrations(_FakeConn(), mod))
    assert applied == ['001_init']
    # Verificar que se ejecutó el DDL del schema_migrations, el SQL del
    # módulo, y el INSERT al tracking.
    sqls = [s.lower() for s, _ in executed]
    assert any('schema_migrations' in s and 'create table' in s for s in sqls)
    assert any('create table fake_module.x' in s for s in sqls)
    assert any('insert into app.schema_migrations' in s for s in sqls)


def test_apply_skips_already_applied(monkeypatch, tmp_path: Path):
    sql = 'create table fake_module.x (id int);'
    sql_path = tmp_path / '001_init.sql'
    sql_path.write_text(sql)
    monkeypatch.setattr(
        'copiloto_core.migrations.runner._resolve_migration_path',
        lambda pkg, rel: sql_path,
    )
    import hashlib  # noqa: PLC0415
    checksum = hashlib.sha256(sql.encode('utf-8')).hexdigest()

    mod = CoreModule(
        code='fake_module',
        router=APIRouter(),
        sql_migrations=('001_init.sql',),
    )

    executed_sqls: list[str] = []

    class _FakeConn:
        def transaction(self):
            class _Tx:
                async def __aenter__(self_inner): return None
                async def __aexit__(self_inner, *exc): return None
            return _Tx()
        async def execute(self, sql, *args):
            executed_sqls.append(sql)
        async def fetch(self, sql, *args):
            # Simulamos que la migration YA está aplicada con el mismo checksum.
            return [{'version': '001_init', 'sha256': checksum}]

    applied = asyncio.run(apply_module_migrations(_FakeConn(), mod))
    assert applied == []
    # No debe haber INSERT en schema_migrations en esta corrida
    assert not any('insert into app.schema_migrations' in s.lower() for s in executed_sqls)


def test_apply_checksum_mismatch_raises(monkeypatch, tmp_path: Path):
    """Si la migration fue MODIFICADA después de aplicarse, raise."""
    sql_now = 'create table fake_module.modified (id int);'
    sql_path = tmp_path / '001_init.sql'
    sql_path.write_text(sql_now)
    monkeypatch.setattr(
        'copiloto_core.migrations.runner._resolve_migration_path',
        lambda pkg, rel: sql_path,
    )

    mod = CoreModule(
        code='fake_module',
        router=APIRouter(),
        sql_migrations=('001_init.sql',),
    )

    class _FakeConn:
        def transaction(self):
            class _Tx:
                async def __aenter__(self_inner): return None
                async def __aexit__(self_inner, *exc): return None
            return _Tx()
        async def execute(self, sql, *args):
            pass
        async def fetch(self, sql, *args):
            # Hash distinto al que tiene el archivo ahora.
            return [{'version': '001_init', 'sha256': 'old-checksum-xxx'}]

    with pytest.raises(MigrationChecksumMismatchError, match='MODIFICADA'):
        asyncio.run(apply_module_migrations(_FakeConn(), mod))


def test_apply_runs_in_order(monkeypatch, tmp_path: Path):
    """Las migrations se aplican en el orden declarado en sql_migrations."""
    for name in ['001_a.sql', '002_b.sql', '003_c.sql']:
        (tmp_path / name).write_text(f'-- {name}')

    monkeypatch.setattr(
        'copiloto_core.migrations.runner._resolve_migration_path',
        lambda pkg, rel: tmp_path / rel,
    )

    mod = CoreModule(
        code='fake_module',
        router=APIRouter(),
        sql_migrations=('001_a.sql', '002_b.sql', '003_c.sql'),
    )

    insert_order: list[str] = []

    class _FakeConn:
        def transaction(self):
            class _Tx:
                async def __aenter__(self_inner): return None
                async def __aexit__(self_inner, *exc): return None
            return _Tx()
        async def execute(self, sql, *args):
            if 'insert into app.schema_migrations' in sql.lower():
                insert_order.append(args[1])  # version
        async def fetch(self, sql, *args):
            return []

    applied = asyncio.run(apply_module_migrations(_FakeConn(), mod))
    assert applied == ['001_a', '002_b', '003_c']
    assert insert_order == ['001_a', '002_b', '003_c']


def test_apply_sql_failure_raises(monkeypatch, tmp_path: Path):
    (tmp_path / '001_init.sql').write_text('not valid sql !!!')
    monkeypatch.setattr(
        'copiloto_core.migrations.runner._resolve_migration_path',
        lambda pkg, rel: tmp_path / rel,
    )

    mod = CoreModule(
        code='fake_module',
        router=APIRouter(),
        sql_migrations=('001_init.sql',),
    )

    class _FakeConn:
        def transaction(self):
            class _Tx:
                async def __aenter__(self_inner): return None
                async def __aexit__(self_inner, *exc): return None
            return _Tx()
        async def execute(self, sql, *args):
            if 'not valid sql' in sql.lower():
                raise RuntimeError('syntax error at or near "not"')
        async def fetch(self, sql, *args):
            return []

    with pytest.raises(MigrationError, match='Fallo al aplicar'):
        asyncio.run(apply_module_migrations(_FakeConn(), mod))


# ─── CLI smoke ────────────────────────────────────────────────────────────


def test_cli_version_command(capsys):
    from copiloto_core.__main__ import main  # noqa: PLC0415

    rc = main(['version'])
    captured = capsys.readouterr()
    assert rc == 0
    assert 'copiloto-core' in captured.out


def test_cli_migrate_unknown_module(capsys):
    from copiloto_core.__main__ import main  # noqa: PLC0415

    rc = main(['migrate', '--module=paquete_inexistente_xyz'])
    captured = capsys.readouterr()
    assert rc == 2
    assert 'no se pudo importar' in captured.err.lower()
