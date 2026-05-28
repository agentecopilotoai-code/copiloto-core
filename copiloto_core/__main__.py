"""CLI mínimo para tareas operativas del core.

Comandos disponibles:

  python -m copiloto_core version
      Imprime la versión instalada.

  python -m copiloto_core new-project <name> [--target-dir=...] [--module-name=...]
      Bootstrapea un nuevo proyecto Python consumer del core. Genera
      pyproject.toml (pinneado al core), .env.example, .gitignore,
      package del deployment (`<name>/main.py` con `create_app(...)`)
      y un módulo demo con migration RLS-ready.

  python -m copiloto_core bootstrap
      Aplica el schema platform del core (`app.*`) en la DB conectada.
      Necesario UNA VEZ tras crear una DB nueva, ANTES del primer
      `migrate --module=...`. Usa `DATABASE_ADMIN_URL` (requiere
      CREATE EXTENSION, CREATE ROLE, etc.). Opcionalmente crea el
      rol runtime de la app con `--create-app-user`.

  python -m copiloto_core migrate --module=<code>
      Aplica las migrations pendientes del módulo indicado contra la
      DB definida en `DATABASE_URL`. Requiere que el paquete del módulo
      sea importable en el venv actual.

Uso típico:

  # Crear nuevo SaaS:
  python -m copiloto_core new-project mi-saas --with-infra
  cd mi-saas
  python3.12 -m venv .venv && source .venv/bin/activate
  pip install -e ".[dev]"
  cp .env.example .env  # editar con valores reales
  docker compose up -d
  python -m copiloto_core bootstrap --create-app-user
  python -m copiloto_core migrate --module=mi_saas_modulo
  uvicorn mi_saas.main:app --reload

  # Step del deploy en producción:
  python -m copiloto_core bootstrap  # idempotente
  python -m copiloto_core migrate --module=mi_modulo
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import os
import sys
from pathlib import Path

from copiloto_core import __version__
from copiloto_core.bootstrap import (
    BootstrapError,
    apply_platform_schema,
)
from copiloto_core.scaffolding import (
    ScaffoldingError,
    generate_project,
)


def _load_dotenv_into_environ(env_path: str = '.env') -> None:
    """Carga `.env` del cwd a `os.environ` si existe.

    Necesario porque los subcomandos `bootstrap` y `migrate` leen
    variables de `os.environ` directamente (no sólo via pydantic-settings).
    En v1.2.0 el script `dev-up.sh` hacía `source .env`, pero eso rompe
    apenas hay un `#` con paréntesis o comilla rara — bash interpreta
    cada línea aunque sea comentario adyacente a sintaxis válida.

    Usamos python-dotenv (dep transitiva de pydantic-settings, ya
    instalado). Idempotente: NO sobreescribe vars ya seteadas en el
    entorno (`override=False`), así un user que setea
    `DATABASE_URL=...` en su shell sigue ganando.
    """
    try:
        from dotenv import load_dotenv  # noqa: PLC0415
    except ImportError:
        return  # python-dotenv no disponible — no es fatal
    if Path(env_path).is_file():
        load_dotenv(env_path, override=False)


def _cmd_version(_args: argparse.Namespace) -> int:
    print(f'copiloto-core {__version__}')
    return 0


def _cmd_new_project(args: argparse.Namespace) -> int:
    """Genera el árbol de un nuevo proyecto consumer.

    El comando NO crea venv, NO instala dependencias, NO inicializa git
    — el README generado guía esos pasos. Mantenerse acotado evita
    asumir el flujo de trabajo del usuario.
    """
    target_dir: Path | None = (
        Path(args.target_dir) if args.target_dir else None
    )
    try:
        result = generate_project(
            project_name=args.name,
            target_dir=target_dir,
            module_name=args.module_name,
            git_protocol=args.git_protocol,
            with_infra=args.with_infra,
        )
    except ScaffoldingError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2

    print(f'✓ Proyecto {result.project_name!r} creado en {result.target_dir}')
    print(f'  copiloto-core pinneado a v{result.core_version} ({result.git_protocol})')
    print(f'  package del deployment: {result.project_package}/')
    print(f'  módulo demo: {result.module_package}/')
    if result.with_infra:
        print('  infra: docker-compose.yml + scripts/dev-up.sh')
    print(f'  archivos: {len(result.files_written)}')
    print('')
    print('Próximos pasos:')
    print(f'  cd {result.target_dir.name}')
    print('  python3.12 -m venv .venv && source .venv/bin/activate')
    print('  pip install -e ".[dev]"')
    print('  cp .env.example .env  # editar con valores reales')
    if result.with_infra:
        print('  ./scripts/dev-up.sh   # levanta docker + bootstrap + migrate + uvicorn')
    else:
        print('  # Sin --with-infra debés levantar postgres/redis/minio a mano y luego:')
        print('  python -m copiloto_core bootstrap --create-app-user')
        print(f'  python -m copiloto_core migrate --module={result.module_package}')
        print(f'  uvicorn {result.project_package}.main:app --reload')
    return 0


def _cmd_bootstrap(args: argparse.Namespace) -> int:
    """Aplica el schema platform del core.

    Idempotente: si ya está aplicado, no hace nada y retorna 0.
    Lee DATABASE_ADMIN_URL del entorno (o DATABASE_URL si la admin no
    está seteada — falla más adelante con un error claro si la URL no
    tiene permisos suficientes).
    """
    _load_dotenv_into_environ()

    from copiloto_core.core.config import get_settings  # noqa: PLC0415
    from copiloto_core.db.pool import db  # noqa: PLC0415

    settings = get_settings()
    dsn = (
        getattr(settings, 'database_admin_url', None)
        or settings.database_url
    )
    if not dsn:
        print(
            'ERROR: ni DATABASE_ADMIN_URL ni DATABASE_URL están seteadas '
            'en el entorno.', file=sys.stderr,
        )
        return 2

    # Si --create-app-user, leer credenciales del entorno
    create_user = bool(args.create_app_user)
    app_user = args.app_user or os.environ.get('APP_DB_USER')
    app_password = args.app_password or os.environ.get('APP_DB_PASSWORD')
    if create_user and (not app_user or not app_password):
        print(
            'ERROR: --create-app-user requiere APP_DB_USER y APP_DB_PASSWORD '
            'en el entorno (o --app-user/--app-password).', file=sys.stderr,
        )
        return 2

    async def _run() -> list[str]:
        await db.connect(dsn)
        try:
            async with db.connection() as conn:
                return await apply_platform_schema(
                    conn,
                    seed=not args.no_seed,
                    create_app_user=create_user,
                    app_user=app_user,
                    app_password=app_password,
                )
        finally:
            await db.close()

    try:
        applied = asyncio.run(_run())
    except BootstrapError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 3
    except Exception as exc:  # noqa: BLE001
        print(f'ERROR durante bootstrap: {type(exc).__name__}: {exc}',
              file=sys.stderr)
        return 3

    if applied:
        print(f'✓ Platform schema aplicado ({len(applied)} archivos):')
        for f in applied:
            print(f'  - {f}')
    else:
        print('✓ Platform schema ya estaba aplicado (no-op).')
    if create_user:
        print(f'  rol runtime: {app_user} (creado o ya existía)')
    return 0


def _cmd_migrate(args: argparse.Namespace) -> int:
    """Importa el módulo + corre apply_module_migrations contra DATABASE_URL."""
    _load_dotenv_into_environ()

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

    sub_new = sub.add_parser(
        'new-project',
        help='Bootstrapea un nuevo proyecto consumer del core',
        description=(
            'Genera el árbol de un nuevo proyecto Python que consume '
            'copiloto-core como librería. Crea pyproject.toml '
            '(pinneado al core), .env.example, .gitignore, package '
            'del deployment con `create_app(...)` y un módulo demo '
            'con migration RLS-ready.'
        ),
    )
    sub_new.add_argument(
        'name',
        help='Nombre kebab-case del proyecto. Ej: mi-saas, alertas-tempranas.',
    )
    sub_new.add_argument(
        '--target-dir',
        default=None,
        help='Dónde escribir el proyecto. Default: ./<name>.',
    )
    sub_new.add_argument(
        '--module-name',
        default=None,
        help=(
            'Nombre snake_case del módulo demo. '
            'Default: <project_package>_modulo.'
        ),
    )
    sub_new.add_argument(
        '--git-protocol',
        choices=('https', 'ssh'),
        default='https',
        help=(
            'Protocolo del pin de copiloto-core en pyproject.toml. '
            'Default: https (funciona con `gh auth setup-git` sin '
            'requerir SSH key). Usá ssh si tu SSH key tiene acceso '
            'directo al repo del core.'
        ),
    )
    sub_new.add_argument(
        '--with-infra', action='store_true',
        help=(
            'Incluir docker-compose.yml (postgres + redis + minio), '
            'scripts/dev-up.sh y .secrets/.gitkeep para arrancar local '
            'con un solo comando. Recomendado para dev nuevo desde cero.'
        ),
    )
    sub_new.set_defaults(func=_cmd_new_project)

    sub_bootstrap = sub.add_parser(
        'bootstrap',
        help='Aplica el schema platform del core (UNA VEZ por DB nueva)',
        description=(
            'Aplica el schema platform del core (`app.*` — tenants, users, '
            'rbac, audit, sessions…) idempotentemente. Necesario UNA VEZ '
            'tras crear una DB nueva, ANTES del primer `migrate --module=`. '
            'Usa DATABASE_ADMIN_URL del entorno (que requiere permisos '
            'de superuser para CREATE EXTENSION / CREATE ROLE).'
        ),
    )
    sub_bootstrap.add_argument(
        '--no-seed', action='store_true',
        help=(
            'No aplicar 20-seed.sql (que inserta el tenant demo). '
            'Recomendado para producción.'
        ),
    )
    sub_bootstrap.add_argument(
        '--create-app-user', action='store_true',
        help=(
            'Crear el rol runtime de la app (lee APP_DB_USER + '
            'APP_DB_PASSWORD del entorno, o usá --app-user/--app-password).'
        ),
    )
    sub_bootstrap.add_argument(
        '--app-user', default=None,
        help='Override de APP_DB_USER (snake_case, 1-31 chars).',
    )
    sub_bootstrap.add_argument(
        '--app-password', default=None,
        help='Override de APP_DB_PASSWORD.',
    )
    sub_bootstrap.set_defaults(func=_cmd_bootstrap)

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
