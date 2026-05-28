"""CLI mínimo para tareas operativas del core.

Comandos disponibles:

  python -m copiloto_core version
      Imprime la versión instalada.

  python -m copiloto_core migrate --module=<code>
      Aplica las migrations pendientes del módulo indicado contra la
      DB definida en `DATABASE_URL`. Requiere que el paquete del módulo
      sea importable en el venv actual.

Uso típico en producción (un step del deploy):

  python -m copiloto_core migrate --module=mi_modulo
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import sys

from copiloto_core import __version__


def _cmd_version(_args: argparse.Namespace) -> int:
    print(f'copiloto-core {__version__}')
    return 0


def _cmd_migrate(args: argparse.Namespace) -> int:
    """Importa el módulo + corre apply_module_migrations contra DATABASE_URL."""
    module_code = args.module
    try:
        pkg = importlib.import_module(module_code)
    except ImportError as exc:
        print(f'ERROR: no se pudo importar el módulo {module_code!r}: {exc}',
              file=sys.stderr)
        return 2

    mod = getattr(pkg, 'module', None)
    if mod is None:
        print(
            f"ERROR: el paquete {module_code!r} no exporta `module` (debe "
            f'ser una instancia de CoreModule).',
            file=sys.stderr,
        )
        return 2

    # Late import — evita cargar pool de DB si solo se llama `version`.
    from copiloto_core.core.config import get_settings  # noqa: PLC0415
    from copiloto_core.db.pool import db  # noqa: PLC0415
    from copiloto_core.migrations import apply_module_migrations  # noqa: PLC0415

    settings = get_settings()

    async def _run() -> list[str]:
        # Usamos admin URL si está disponible — DDL requiere permisos
        # más amplios que los del usuario app.
        dsn = (
            getattr(settings, 'database_admin_url', None)
            or settings.database_url
        )
        await db.connect(dsn)
        try:
            async with db.connection() as conn:
                return await apply_module_migrations(conn, mod)
        finally:
            await db.close()

    try:
        applied = asyncio.run(_run())
    except Exception as exc:  # noqa: BLE001
        print(f'ERROR durante migration: {type(exc).__name__}: {exc}',
              file=sys.stderr)
        return 3

    if applied:
        print(f'Aplicadas {len(applied)} migrations para {module_code}:')
        for v in applied:
            print(f'  - {v}')
    else:
        print(f'Sin migrations pendientes para {module_code}.')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='copiloto-core',
        description='CLI operativo del core',
    )
    sub = parser.add_subparsers(dest='cmd', required=True)

    sub_version = sub.add_parser('version', help='Imprime la versión instalada')
    sub_version.set_defaults(func=_cmd_version)

    sub_migrate = sub.add_parser('migrate', help='Aplica migrations de un módulo')
    sub_migrate.add_argument(
        '--module', required=True,
        help='code del módulo (debe ser importable: `import <code>`)',
    )
    sub_migrate.set_defaults(func=_cmd_migrate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
