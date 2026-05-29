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

  # Crear nuevo SaaS (dev local):
  python -m copiloto_core new-project mi-saas --with-infra
  cd mi-saas
  python3.12 -m venv .venv && source .venv/bin/activate
  pip install -e ".[dev]"
  cp .env.example .env  # editar con valores reales
  docker compose up -d
  python -m copiloto_core bootstrap --create-app-user
  python -m copiloto_core migrate --module=mi_saas_modulo
  uvicorn mi_saas.main:app --reload

  # Crear nuevo SaaS con kit de producción (v2.1.0+):
  python -m copiloto_core new-project mi-saas --with-infra --prod-ready
  # Genera además: Dockerfile + docker-compose.prod.yml + gunicorn_conf.py
  # + nginx.conf.example + scripts/prod-up.sh (v2.1.1+) + scripts/backup.sh
  # + .github/workflows/deploy.yml + .env.prod.example + .dockerignore
  # Ver docs/DEPLOYMENT.md del core para el flow completo de deploy.

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
from copiloto_core._scripts import (
    ScriptError,
    run_packaged_script,
)
from copiloto_core.bootstrap import (
    BootstrapError,
    apply_platform_schema,
)
from copiloto_core.scaffolding import (
    ScaffoldingError,
    generate_project,
)


# ─── Catálogo de scripts shipeados ───────────────────────────────────────
#
# Map subcomando CLI → archivo `.sh` dentro de copiloto_core/scripts/.
# Agregar acá nuevos scripts es un cambio MINOR (additive). Renombrar
# o eliminar un subcomando rompe contratos públicos — bump MAJOR.

_PACKAGED_SCRIPTS: dict[str, tuple[str, str]] = {
    # cli_name: (script_filename, short_help)
    #
    # NOTA: `generate-secrets` no aparece acá porque tiene un handler
    # Python dedicado (`_cmd_generate_secrets`) que respeta el `.env.example`
    # del consumer (host=localhost, project name, etc.). El bash original
    # asumía contexto del core (hostnames docker-internal) y rompía en
    # consumer flows. El handler Python preserva config existente.
    'auth0-configure': (
        'configure-auth0.sh',
        'Configura tenant Auth0 vía Management API (apps, scopes, actions)',
    ),
    'backup-local': (
        'backup-local.sh',
        'Hace pg_dump local + cifra con GPG en ./backups/local/',
    ),
    'restore-local': (
        'restore-local.sh',
        'Restaura un backup local con verificación',
    ),
    'backup-cloud': (
        'backup-to-cloud.sh',
        'Backup automatizado a S3 con GPG (TASK-0064)',
    ),
    'verify-backup': (
        'verify-backup.sh',
        'Verifica integridad GPG de un backup cloud',
    ),
    'smoke-test': (
        'smoke-test.sh',
        'Curl health check de endpoints públicos',
    ),
    'reset-local': (
        'reset-local-dev.sh',
        'Nuke volúmenes Docker locales (DESTRUCTIVO — requiere --yes)',
    ),
}


def _resolve_admin_dsn() -> str | None:
    """Resuelve el DSN admin para operaciones que necesitan superuser.

    Bootstrap + migrate ambos hacen DDL (CREATE EXTENSION, CREATE SCHEMA,
    CREATE ROLE) que el user runtime de la app NO tiene permiso de hacer.
    Necesitan el admin URL.

    Settings de pydantic NO declara `database_admin_url` como field, así
    que getattr siempre devuelve None. Leemos directo de os.environ.
    Fallback a settings.database_url (con WARNING) para flujos donde el
    user app SÍ es superuser (uncommon — solo dev sin separación).

    Returns:
      DSN string, o None si ni DATABASE_ADMIN_URL ni DATABASE_URL están.
    """
    admin_dsn = os.environ.get('DATABASE_ADMIN_URL')
    if admin_dsn:
        return admin_dsn

    # Fallback con warning
    from copiloto_core.core.config import get_settings  # noqa: PLC0415
    settings = get_settings()
    if settings.database_url:
        print(
            'WARNING: DATABASE_ADMIN_URL no está seteado. Usando '
            'DATABASE_URL como fallback — esto va a fallar si el user '
            'de la app no tiene permisos de superuser (CREATE SCHEMA, '
            'CREATE EXTENSION, CREATE ROLE).',
            file=sys.stderr,
        )
        return settings.database_url
    return None


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
            prod_ready=args.prod_ready,
        )
    except ScaffoldingError as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 2

    print(f'✓ Proyecto {result.project_name!r} creado en {result.target_dir}')
    print(f'  copiloto-core pinneado a v{result.core_version} ({result.git_protocol})')
    print(f'  package del deployment: {result.project_package}/')
    print(f'  módulo demo: {result.module_package}/')
    if result.with_infra:
        print('  infra dev: docker-compose.yml + scripts/dev-up.sh')
    if result.prod_ready:
        print('  prod kit: Dockerfile + docker-compose.prod.yml + gunicorn_conf.py')
        print('            nginx.conf.example + scripts/prod-up.sh + scripts/backup.sh')
        print('            .env.prod.example + .github/workflows/deploy.yml')
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
    if result.prod_ready:
        print('')
        print('Cuando estés listo para deploy a prod (ver docs/DEPLOYMENT.md):')
        print('  cp .env.prod.example .env.prod  # editar con valores reales de prod')
        print('  python -m copiloto_core generate-secrets --target=.env.prod')
        print('  docker compose -f docker-compose.prod.yml build')
        print('  docker compose -f docker-compose.prod.yml --env-file .env.prod up -d')
    return 0


def _cmd_bootstrap(args: argparse.Namespace) -> int:
    """Aplica el schema platform del core.

    Idempotente: si ya está aplicado, no hace nada y retorna 0.
    Lee DATABASE_ADMIN_URL del entorno (o DATABASE_URL si la admin no
    está seteada — falla más adelante con un error claro si la URL no
    tiene permisos suficientes).
    """
    _load_dotenv_into_environ()

    from copiloto_core.db.pool import db  # noqa: PLC0415

    # v1.3.6: helper compartido con `migrate`. Bootstrap requiere admin
    # DSN para CREATE EXTENSION + CREATE SCHEMA + CREATE ROLE.
    dsn = _resolve_admin_dsn()
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


def _cmd_generate_secrets(args: argparse.Namespace) -> int:
    """Reescribe `.env` reemplazando `CHANGE_ME` con valores random.

    Diseño (v1.3.1):
      - Si NO existe `.env` y SÍ existe `.env.example`: copia .example → .env.
      - Si NO existe ninguno: error claro al user (no asumimos layout).
      - Si existe `.env`: edita en lugar, solo toca líneas con `CHANGE_ME`.
      - Hostnames (localhost, postgres, etc.) NO se tocan — el user/scaffolder
        ya los configuró según su deployment. El bash original rompía en
        consumer flow porque generaba siempre con `@postgres:` docker-internal.
      - APP_DB_PASSWORD y POSTGRES_PASSWORD también se reemplazan
        inline dentro de DATABASE_URL / DATABASE_ADMIN_URL para mantener
        consistencia.
    """
    import re  # noqa: PLC0415
    import secrets  # noqa: PLC0415

    env_path = Path.cwd() / '.env'
    example_path = Path.cwd() / '.env.example'

    if not env_path.exists():
        if not example_path.exists():
            print(
                'ERROR: no encontré .env ni .env.example en el cwd. '
                'Generate-secrets necesita uno de los dos como base. '
                'Si arrancaste con `new-project`, deberías estar en el '
                'directorio del proyecto generado.',
                file=sys.stderr,
            )
            return 2
        env_path.write_text(example_path.read_text(encoding='utf-8'), encoding='utf-8')
        print(f'  ✓ creado .env desde .env.example')

    content = env_path.read_text(encoding='utf-8')

    # Mapeo: env var → cuántos bytes random para el valor.
    # Los nombres están alineados con el `.env.example` que genera el
    # scaffolder (v1.3.1+).
    _SECRET_KEYS: dict[str, int] = {
        'APP_DB_PASSWORD': 24,
        'POSTGRES_PASSWORD': 24,
        'JWT_SECRET': 48,
        'S3_SECRET_ACCESS_KEY': 32,
        'SERVICE_TOKEN': 36,
        # AI_PROVIDER_MASTER_KEY: NO usa secrets.token_urlsafe (genera 43
        # chars sin padding). Fernet exige EXACTAMENTE 32 bytes
        # base64-urlsafe-encoded = 44 chars con `=` al final. Caso especial
        # abajo en _gen_value.
        'AI_PROVIDER_MASTER_KEY': 32,
    }

    def _gen_value(key: str) -> str:
        """Genera el valor random para un secret.

        v2.0.1: AI_PROVIDER_MASTER_KEY usa Fernet.generate_key() (formato
        específico requerido por la lib cryptography). Los demás usan
        secrets.token_urlsafe (random base64-urlsafe sin restricciones
        de formato).
        """
        if key == 'AI_PROVIDER_MASTER_KEY':
            from cryptography.fernet import Fernet  # noqa: PLC0415
            return Fernet.generate_key().decode('ascii')
        return secrets.token_urlsafe(_SECRET_KEYS[key])

    generated: dict[str, str] = {}

    def _replace_simple(match: re.Match) -> str:
        key = match.group(1)
        value = match.group(2)
        if key in _SECRET_KEYS and value.strip().startswith('CHANGE_ME'):
            new_value = _gen_value(key)
            generated[key] = new_value
            return f'{key}={new_value}'
        return match.group(0)

    # Pase 1: reemplazar valores simples `KEY=CHANGE_ME`.
    pattern = re.compile(r'^([A-Z][A-Z0-9_]*)=(.*)$', re.MULTILINE)
    content = pattern.sub(_replace_simple, content)

    # Pase 2: reemplazar passwords inline en DATABASE_URLs para que
    # matcheen con APP_DB_PASSWORD y POSTGRES_PASSWORD.
    if 'APP_DB_PASSWORD' in generated:
        pw = generated['APP_DB_PASSWORD']
        # DATABASE_URL=postgres(ql)?://copiloto_app:CHANGE_ME@... → ...:<pw>@...
        content = re.sub(
            r'(DATABASE_URL=postgres(?:ql)?://copiloto_app:)CHANGE_ME(@)',
            lambda m: f'{m.group(1)}{pw}{m.group(2)}',
            content,
        )
    if 'POSTGRES_PASSWORD' in generated:
        pw = generated['POSTGRES_PASSWORD']
        content = re.sub(
            r'(DATABASE_ADMIN_URL=postgres(?:ql)?://postgres:)CHANGE_ME(@)',
            lambda m: f'{m.group(1)}{pw}{m.group(2)}',
            content,
        )

    env_path.write_text(content, encoding='utf-8')
    env_path.chmod(0o600)

    if generated:
        print(f'✓ {len(generated)} secrets generados en {env_path}:')
        for k in sorted(generated):
            print(f'  - {k}')
        print(f'  permisos: 600 (solo owner puede leer)')
    else:
        print(f'✓ {env_path} sin CHANGE_ME pendientes. Nada para regenerar.')
    return 0


def _make_script_cmd(script_filename: str):
    """Devuelve un handler argparse que invoca el script empaquetado.

    Cualquier arg pos/flag después del subcomando va pass-through
    al script bash. Eso permite que e.g. `python -m copiloto_core
    auth0-configure --domain=...` reciba `--domain=...` igual que
    `bash configure-auth0.sh --domain=...`.
    """
    def handler(args: argparse.Namespace) -> int:
        _load_dotenv_into_environ()
        try:
            return run_packaged_script(
                script_filename,
                args=list(getattr(args, 'script_args', []) or []),
            )
        except ScriptError as exc:
            print(f'ERROR: {exc}', file=sys.stderr)
            return 2
    return handler


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

    # v1.3.6: usar admin DSN — las migrations del módulo hacen CREATE
    # SCHEMA / CREATE TABLE / GRANT que requieren permisos superuser.
    # El user app (copiloto_app) no los tiene.
    dsn = _resolve_admin_dsn()
    if not dsn:
        print(
            'ERROR: ni DATABASE_ADMIN_URL ni DATABASE_URL están seteadas '
            'en el entorno.', file=sys.stderr,
        )
        return 2

    async def _run() -> list[str]:
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
    sub_new.add_argument(
        '--prod-ready', action='store_true',
        help=(
            'v2.1.0+: incluir Production Deployment Kit — Dockerfile '
            'multi-stage USER no-root, docker-compose.prod.yml con '
            'healthchecks + restart policies, gunicorn_conf.py, '
            'nginx.conf.example (TLS + security headers + rate limit), '
            'scripts/backup.sh (pg_dump + rotación + opcional S3), '
            '.github/workflows/deploy.yml (build + push GHCR + deploy SSH) '
            'y .env.prod.example. Se puede combinar con --with-infra.'
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

    # ─── generate-secrets — handler Python (v1.3.1) ─────────────────
    # Python-native (no bash) para respetar el .env.example del
    # consumer (host=localhost, project name, etc.). Antes era un
    # alias del bash que rompía en consumer flow.
    sub_gen = sub.add_parser(
        'generate-secrets',
        help='Reemplaza CHANGE_ME en .env con valores random (respeta hostnames + project name)',
        description=(
            'Lee .env (o crea desde .env.example si no existe) y '
            'reemplaza los valores CHANGE_ME con secrets random '
            'criptográficamente seguros. NO toca hostnames, project '
            'name, ni nada que no matchee CHANGE_ME. Idempotente.'
        ),
    )
    sub_gen.set_defaults(func=_cmd_generate_secrets)

    # ─── Subcomandos que invocan scripts bash empaquetados (v1.3.0) ──
    for cli_name, (script_filename, help_text) in _PACKAGED_SCRIPTS.items():
        sub_script = sub.add_parser(
            cli_name,
            help=help_text,
            description=(
                f'{help_text}. Pass-through: cualquier argumento después '
                f'del subcomando va al script `{script_filename}` tal cual.'
            ),
        )
        sub_script.add_argument(
            'script_args',
            nargs=argparse.REMAINDER,
            help='Argumentos pass-through al script bash.',
        )
        sub_script.set_defaults(func=_make_script_cmd(script_filename))

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == '__main__':
    sys.exit(main())
