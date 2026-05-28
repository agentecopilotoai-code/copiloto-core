"""Implementación del runner de migrations.

Diseño minimalista — NO usamos Alembic ni similar porque:
1. El feature requirement es pequeño: aplicar .sql en orden + trackear.
2. Alembic asume single-app — acá tenemos N módulos cada uno con sus
   migrations.
3. Sin DSL Python para migrations (los módulos prefieren SQL crudo).

Si en el futuro un módulo necesita DDL más sofisticado (data backfills,
multi-step migrations), puede usar Alembic directamente desde su
propio paquete — el core no se opone, solo no provee el wrapper.
"""
from __future__ import annotations

import hashlib
import logging
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import asyncpg

    from copiloto_core.extension import CoreModule


logger = logging.getLogger(__name__)


class MigrationError(Exception):
    """Base de errores del runner de migrations."""


class MigrationChecksumMismatchError(MigrationError):
    """Una migration ya aplicada fue MODIFICADA después de su apply.

    El runner detecta esto comparando el SHA-256 actual del archivo
    contra el guardado en `app.schema_migrations.sha256`. Es un
    fail-closed: la migration NO se re-aplica, se levanta error para
    forzar workflow correcto (nueva migration > editar la previa).
    """


# DDL para crear la tabla de tracking. Se ejecuta idempotente al
# primer `apply_module_migrations` de cada proceso.
_SCHEMA_MIGRATIONS_DDL = '''
create table if not exists app.schema_migrations (
  module      text not null,
  version     text not null,
  applied_at  timestamptz not null default now(),
  sha256      text not null,
  primary key (module, version)
);
create index if not exists ix_schema_migrations_applied_at
  on app.schema_migrations(applied_at);
'''


async def ensure_schema_migrations_table(conn: 'asyncpg.Connection') -> None:
    """Crea `app.schema_migrations` si no existe. Idempotente."""
    await conn.execute(_SCHEMA_MIGRATIONS_DDL)


def _resolve_migration_path(module_pkg: str, rel_path: str) -> Path:
    """Resuelve `module_pkg.<sub>/<file>.sql` usando importlib.resources.

    Args:
      module_pkg: nombre del paquete Python del módulo (ej. 'mi_modulo').
      rel_path: path relativo al paquete (ej. 'migrations/001_init.sql').

    Returns:
      `Path` filesystem-resolvable al archivo SQL.

    Raises:
      MigrationError: si el archivo no existe en el paquete.
    """
    parts = rel_path.replace('\\', '/').split('/')
    if len(parts) < 1:
        raise MigrationError(f'sql_migrations path inválido: {rel_path!r}')
    *subdirs, filename = parts
    pkg_path = '.'.join((module_pkg, *subdirs)) if subdirs else module_pkg
    try:
        ref = resources.files(pkg_path).joinpath(filename)
    except (ModuleNotFoundError, AttributeError) as exc:
        raise MigrationError(
            f'No se pudo resolver el paquete {pkg_path!r} para migration {rel_path!r}: {exc}',
        ) from exc
    if not ref.is_file():
        raise MigrationError(
            f'Migration {rel_path!r} no existe en paquete {module_pkg!r} '
            f'(buscado en {pkg_path}/{filename}).',
        )
    # Usar Path para uniformidad — importlib.resources puede devolver
    # un Traversable que en wheels reside en un zip; con `as_file` se
    # extrae a tempfile transparente. Para simplicidad asumimos paquetes
    # instalados como editable/source (caso 99%).
    return Path(str(ref))


def _module_python_package(module: 'CoreModule') -> str:
    """Devuelve el nombre del paquete Python del módulo.

    Convención: el `CoreModule.code` matchea el paquete. Si la
    convención cambia, el módulo puede setear su propio attr.
    """
    # El code del módulo SIEMPRE es snake_case válido para nombre de
    # paquete Python (validado en CoreModule.__post_init__).
    return module.code


async def apply_module_migrations(
    conn: 'asyncpg.Connection',
    module: 'CoreModule',
) -> list[str]:
    """Aplica todas las migrations pendientes del módulo en orden.

    Returns:
      Lista de versiones aplicadas en este call (vacía si todas ya
      estaban aplicadas).

    Raises:
      MigrationChecksumMismatchError: si una migration ya aplicada fue
        modificada.
      MigrationError: si una migration falla en su ejecución SQL.
    """
    await ensure_schema_migrations_table(conn)

    if not module.sql_migrations:
        return []

    pkg = _module_python_package(module)
    applied: list[str] = []

    # Tracking de qué migrations YA están aplicadas para este módulo.
    # Una sola query, no por-archivo.
    rows = await conn.fetch(
        'select version, sha256 from app.schema_migrations where module = $1',
        module.code,
    )
    already_applied = {r['version']: r['sha256'] for r in rows}

    for rel_path in module.sql_migrations:
        version = _version_from_path(rel_path)
        path = _resolve_migration_path(pkg, rel_path)
        sql = path.read_text(encoding='utf-8')
        checksum = hashlib.sha256(sql.encode('utf-8')).hexdigest()

        if version in already_applied:
            if already_applied[version] != checksum:
                raise MigrationChecksumMismatchError(
                    f'Migration {module.code}/{version} fue MODIFICADA después '
                    f'de aplicarse. Esperado sha256={already_applied[version][:12]}..., '
                    f'actual sha256={checksum[:12]}.... Crea una migration nueva '
                    f'en vez de editar la previa.',
                )
            # Ya aplicada y sin cambios — skip.
            continue

        # Aplicar dentro de TX explícita para todo-o-nada.
        async with conn.transaction():
            try:
                await conn.execute(sql)
            except Exception as exc:
                raise MigrationError(
                    f'Fallo al aplicar {module.code}/{version}: {type(exc).__name__}: {exc}',
                ) from exc
            await conn.execute(
                'insert into app.schema_migrations (module, version, sha256) '
                'values ($1, $2, $3)',
                module.code, version, checksum,
            )

        logger.info(
            'migration.applied module=%s version=%s sha256=%s...',
            module.code, version, checksum[:12],
        )
        applied.append(version)

    return applied


def _version_from_path(rel_path: str) -> str:
    """Extrae el `version` del nombre del archivo.

    Convención: `<NNN>_<descripcion>.sql` → version = nombre sin `.sql`.
    Ej: `001_init.sql` → `001_init`.

    Devuelve el filename completo (sin extensión) para preservar la
    descripción en el tracking — útil para auditoría.
    """
    filename = rel_path.replace('\\', '/').rsplit('/', 1)[-1]
    if filename.endswith('.sql'):
        filename = filename[:-4]
    if not filename:
        raise MigrationError(f'sql_migrations path sin filename: {rel_path!r}')
    return filename


__all__ = [
    'MigrationChecksumMismatchError',
    'MigrationError',
    'apply_module_migrations',
    'ensure_schema_migrations_table',
]
