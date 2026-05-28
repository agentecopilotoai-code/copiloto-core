"""Generador de proyectos consumer del core (`python -m copiloto_core new-project`).

Análogo a `django-admin startproject` o `rails new`: bootstrappea un
repo Python listo para correr `pip install -e . && uvicorn` con un
módulo demo enchufado al core.

# Diseño

- **Cero dependencias extra**: templates inline como `str.format()`. No
  Jinja2, no cookiecutter. El usuario instala `copiloto-core` y ya
  tiene el comando.
- **Templates inmutables**: los strings de abajo se versionan con
  cada release del core. Bumps de templates → minor release.
- **Idempotente vs catastrófico**: si el directorio destino existe y
  NO está vacío, abortamos con `ProjectExistsError`. El usuario debe
  borrar/mover/usar otro path explícitamente. No sobreescribimos nada.
- **Naming**: el `project_name` es kebab-case (`mi-saas`). Internamente
  derivamos:
    - `project_package` = snake_case del SPA del deployment (`mi_saas`)
    - `module_package` = snake_case del módulo demo
      (por default `mi_saas_modulo`, override con `--module-name`)
  Esto evita que el módulo demo colisione con el package del deployment
  cuando se importan ambos desde `main.py`.

# Lo que NO hace

- No corre `pip install` (el usuario decide venv + python version).
- No inicializa git (el usuario decide remote + commit inicial).
- No genera Auth0 tenants / Postgres DBs / S3 buckets — eso vive en
  el runbook de onboarding (`docs/INSTALL.md` del proyecto generado).

Ver `python -m copiloto_core new-project --help` para uso.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from copiloto_core import __version__ as _CORE_VERSION


# Slug del proyecto: kebab-case, empieza con letra, 2-48 chars. Strict
# para evitar nombres que rompan pip / postgres / etc.
_PROJECT_NAME_RE = re.compile(r'^[a-z][a-z0-9-]{1,47}$')

# Slug del módulo (snake_case). Misma regla que `CoreModule.code` —
# ver `copiloto_core.extension._CODE_RE`.
_MODULE_NAME_RE = re.compile(r'^[a-z][a-z0-9_]{1,31}$')


class ScaffoldingError(Exception):
    """Base para errores del generador."""


class InvalidProjectNameError(ScaffoldingError):
    """El nombre del proyecto no matchea `_PROJECT_NAME_RE`."""


class InvalidModuleNameError(ScaffoldingError):
    """El nombre del módulo no matchea `_MODULE_NAME_RE`."""


class ProjectExistsError(ScaffoldingError):
    """El directorio destino existe y no está vacío."""


@dataclass(frozen=True)
class GenerationResult:
    """Resumen de lo que el generador escribió. Útil para tests + el
    output del CLI (no recalcular paths)."""

    project_name: str          # kebab-case (input del usuario)
    project_package: str       # snake_case del SPA del deployment
    module_package: str        # snake_case del módulo demo
    target_dir: Path           # absoluto, raíz del proyecto creado
    files_written: tuple[str, ...]   # paths relativos a target_dir
    core_version: str          # versión pinneada en el pyproject generado


def _to_snake_case(slug: str) -> str:
    """`mi-saas` → `mi_saas`. El slug ya pasó por `_PROJECT_NAME_RE`
    así que solo necesitamos cambiar dashes."""
    return slug.replace('-', '_')


def _validate_project_name(name: str) -> None:
    if not _PROJECT_NAME_RE.match(name):
        raise InvalidProjectNameError(
            f'Nombre de proyecto inválido: {name!r}. Debe matchear '
            f'{_PROJECT_NAME_RE.pattern!r} (kebab-case, empieza con '
            f'letra, 2-48 chars). Ej: mi-saas, alertas-tempranas.',
        )


def _validate_module_name(name: str) -> None:
    if not _MODULE_NAME_RE.match(name):
        raise InvalidModuleNameError(
            f'Nombre de módulo inválido: {name!r}. Debe matchear '
            f'{_MODULE_NAME_RE.pattern!r} (snake_case, empieza con '
            f'letra, 2-32 chars). Ej: alertas, mi_modulo.',
        )


def _ensure_target_dir_empty(path: Path) -> None:
    """Política: NUNCA sobreescribir. Si existe contenido, abortar.

    Mejor frustrar al usuario una vez que destruir un proyecto suyo.
    """
    if not path.exists():
        return
    # Iteramos perezosamente: si hay AL MENOS un entry, fallamos.
    try:
        next(path.iterdir())
    except StopIteration:
        return  # existe pero vacío, reusable
    raise ProjectExistsError(
        f'El directorio {path} ya existe y no está vacío. Mové/borrá '
        f'su contenido o usá `--target-dir=<otra-ruta>`.',
    )


# ──────────────────────────────────────────────────────────────────────
# Templates
# ──────────────────────────────────────────────────────────────────────
#
# Los placeholders usan `{nombre}` y se rinden con `.format(**ctx)`.
# Las llaves literales dentro del template deben duplicarse (`{{`, `}}`).

_PYPROJECT_TOML = '''\
[project]
name = "{project_name}"
version = "0.1.0"
description = "SaaS construido sobre copiloto-core"
requires-python = ">=3.12"
dependencies = [
  # Pin al core. Cuando salga `copiloto-core 2.0` querrás revisar la
  # guía de migración antes de mover este pin.
  "copiloto-core @ git+ssh://git@github.com/agentecopilotoai-code/copiloto-core.git@v{core_version}",
]

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "pytest-asyncio>=0.24",
  "httpx>=0.27",
  "ruff>=0.6",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["{project_package}*", "{module_package}*"]

[tool.setuptools.package-data]
"{module_package}" = ["migrations/*.sql"]
'''

_ENV_EXAMPLE = '''\
# Copiá este archivo a `.env` y rellená los valores reales.
# `.env` está en `.gitignore` por seguridad — nunca lo commitees.

# ─── Postgres (multi-tenant, requiere extension pgvector si usás IA) ──
DATABASE_URL=postgres://copiloto_app:CHANGE_ME@localhost:5432/{project_package}
DATABASE_ADMIN_URL=postgres://postgres:CHANGE_ME@localhost:5432/{project_package}
APP_DB_USER=copiloto_app
APP_DB_PASSWORD=CHANGE_ME

# ─── App ──────────────────────────────────────────────────────────────
APP_NAME={project_name}
APP_ENV=local
LOG_LEVEL=INFO

# ─── Auth0 (RS256 + JWKS) ─────────────────────────────────────────────
AUTH0_DOMAIN=tu-tenant.auth0.com
AUTH0_API_AUDIENCE=https://api.{project_name}.local
AUTH0_MGMT_CLIENT_ID=
AUTH0_MGMT_CLIENT_SECRET=

# ─── JWT ──────────────────────────────────────────────────────────────
# Generar con: python -c "import secrets; print(secrets.token_urlsafe(64))"
JWT_SECRET=CHANGE_ME_64_RANDOM_CHARS

# ─── Redis (sessions + OAuth state + rate-limit) ──────────────────────
REDIS_URL=redis://localhost:6379/0

# ─── S3 / MinIO (uploads, exports) ────────────────────────────────────
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY_ID=
S3_SECRET_ACCESS_KEY=
S3_BUCKET={project_package}

# ─── Rate limiting (req/min por IP+ruta) ──────────────────────────────
RATE_LIMIT_PER_MIN=60
RATE_LIMIT_WEBHOOK_PER_MIN=300

# ─── Observabilidad ───────────────────────────────────────────────────
# IPs autorizadas a leer `/metrics` (Prometheus). Default: nadie.
OBSERVABILITY_ALLOWED_IPS=127.0.0.1/32,10.0.0.0/8
'''

_GITIGNORE = '''\
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
.eggs/
build/
dist/

# Tests + coverage
.pytest_cache/
.coverage
htmlcov/
.tox/

# IDE
.vscode/
.idea/

# Secrets — NUNCA commitear
.env
.env.*
!.env.example
.secrets/

# OS
.DS_Store
Thumbs.db
'''

_README = '''\
# {project_name}

SaaS construido sobre [copiloto-core](https://github.com/agentecopilotoai-code/copiloto-core)
`v{core_version}`.

## Quickstart

```bash
# 1. Venv + dependencias
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 2. Postgres + Redis + MinIO locales (ajustá según preferencia)
docker run -d --name pg-{project_package} -p 5432:5432 \\
  -e POSTGRES_PASSWORD=postgres \\
  -e POSTGRES_DB={project_package} \\
  pgvector/pgvector:pg16

docker run -d --name redis-{project_package} -p 6379:6379 redis:7-alpine

docker run -d --name minio-{project_package} -p 9000:9000 -p 9001:9001 \\
  -e MINIO_ROOT_USER=minioadmin \\
  -e MINIO_ROOT_PASSWORD=minioadmin \\
  minio/minio server /data --console-address ":9001"

# 3. Variables de entorno
cp .env.example .env
# Editar .env con tus valores reales (especialmente JWT_SECRET y AUTH0_*)

# 4. Migraciones del módulo demo
python -m copiloto_core migrate --module={module_package}

# 5. Levantar la app
uvicorn {project_package}.main:app --reload --port 8000
```

Probá:

```bash
curl http://localhost:8000/v1/branding
curl http://localhost:8000/v1/{module_package_dashed}/health
```

## Estructura

```
{project_name}/
├── pyproject.toml           # pin a copiloto-core@v{core_version}
├── .env.example             # plantilla de variables
├── {project_package}/
│   ├── __init__.py
│   └── main.py              # app = create_app(modules=[...], branding=...)
└── {module_package}/
    ├── __init__.py          # exporta `module = CoreModule(...)`
    ├── routers.py           # tus endpoints
    └── migrations/
        └── 001_init.sql     # schema del módulo
```

## Documentación

- **Extender el core con tus módulos**: ver
  `docs/EXTENDING.md` en el repo del core.
- **Arquitectura del core**: ver `ARCHITECTURE.md` en el repo del core.

## Roadmap mínimo para producción

1. Configurar Auth0 (ver `docs/auth0_keys_rotation.md` en el core).
2. Diseñar tus migraciones SQL respetando RLS por `tenant_id`.
3. Declarar tus capabilities (`{module_package}:read`, etc.) en
   `{module_package}/__init__.py` y asignarlas a roles desde el admin.
4. Wireá tu `BrandingConfig` con tu logo + colores.
5. Configurar backup automatizado (ver `docker-compose.yml` del core
   profile `backups`).
'''

_PROJECT_INIT = '''\
"""Package principal del deployment `{project_name}`."""
'''

_PROJECT_MAIN = '''\
"""Entrypoint FastAPI del deployment.

Compone el core con tus módulos y branding. Levantá con:

  uvicorn {project_package}.main:app --reload
"""
from copiloto_core import BrandingConfig, create_app

from {module_package} import module as {module_package}_module


app = create_app(
    modules=[
        {module_package}_module,
        # Agregá acá más módulos opt-in conforme los desarrolles.
    ],
    branding=BrandingConfig(
        product_name="{project_name}",
        # logo_url="https://cdn.tudominio.com/logo.svg",
        # primary_color="#0066ff",
    ),
)
'''

_MODULE_INIT = '''\
"""Módulo `{module_package}` enchufado al core.

Exporta `module: CoreModule` para que el deployment lo monte:

  from {module_package} import module as {module_package}_module
  app = create_app(modules=[{module_package}_module])
"""
from copiloto_core import CoreModule

from {module_package}.routers import router


module = CoreModule(
    code="{module_package}",
    router=router,
    capabilities=(
        "{module_package}:read",
        "{module_package}:write",
    ),
    sql_migrations=(
        "migrations/001_init.sql",
    ),
)
'''

_MODULE_ROUTERS = '''\
"""Routers del módulo `{module_package}`.

Endpoints expuestos bajo `/v1/{module_package_dashed}/...`. El prefix
lo aplica `create_app()` automáticamente — acá solo declarás las rutas.
"""
from fastapi import APIRouter, Depends

from copiloto_core import (
    authenticate_request,
    require_capability,
)
from copiloto_core.db.pool import db


router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Endpoint público sin auth para checar que el módulo monta."""
    return {{"status": "ok", "module": "{module_package}"}}


@router.get("/items")
async def list_items(
    _actor=Depends(authenticate_request),
    _cap=Depends(require_capability("{module_package}:read")),
) -> list[dict]:
    """Lista items del tenant del actor (RLS aplica via tenant_id de la TX).

    Patrón canónico:
      - `authenticate_request` valida JWT + carga el actor (sub/email/roles).
      - `require_capability(...)` chequea que el actor tenga el permiso.
      - `db.connection(tenant_id=...)` abre TX con `app.current_tenant`
        seteado → RLS filtra automáticamente.
    """
    async with db.connection() as conn:
        rows = await conn.fetch(
            "select id, name, created_at from {module_package}.item order by created_at desc"
        )
        return [dict(r) for r in rows]
'''

_MIGRATION_001 = '''\
-- 001_init.sql — schema inicial del módulo `{module_package}`.
--
-- Reglas que el core impone (verificables en review):
--   1. Crear un schema dedicado para el módulo (NUNCA escribir en `app.*`).
--   2. Toda tabla con datos de tenant DEBE tener `tenant_id uuid not null`.
--   3. Toda tabla tenant-scoped DEBE habilitar RLS + policy que filtre
--      por `current_setting('app.current_tenant')::uuid`.
--   4. Las migrations son inmutables — si necesitás cambiar este file
--      después de aplicado, creá `002_*.sql` con un ALTER, no editar.

create schema if not exists {module_package};

create table if not exists {module_package}.item (
    id          uuid primary key default gen_random_uuid(),
    tenant_id   uuid not null,
    name        text not null,
    created_at  timestamptz not null default now()
);

alter table {module_package}.item enable row level security;

-- RLS policy: solo filas del tenant activo (seteado por
-- `db.connection(tenant_id=...)` del core).
create policy item_tenant_isolation on {module_package}.item
    for all
    using (tenant_id = current_setting('app.current_tenant', true)::uuid)
    with check (tenant_id = current_setting('app.current_tenant', true)::uuid);

-- Concedé permisos al user de runtime de la app.
grant usage on schema {module_package} to copiloto_app;
grant select, insert, update, delete on all tables in schema {module_package} to copiloto_app;
alter default privileges in schema {module_package}
    grant select, insert, update, delete on tables to copiloto_app;
'''


def _render_files(ctx: dict[str, str]) -> dict[str, str]:
    """Renderiza todos los templates con el contexto. Devuelve un
    dict `{path_relativo: contenido}`.

    Centralizado para que los tests verifiquen exactamente lo que se
    escribe a disco sin tocar el FS.
    """
    project_pkg = ctx['project_package']
    module_pkg = ctx['module_package']
    return {
        'pyproject.toml': _PYPROJECT_TOML.format(**ctx),
        '.env.example': _ENV_EXAMPLE.format(**ctx),
        '.gitignore': _GITIGNORE,
        'README.md': _README.format(**ctx),
        f'{project_pkg}/__init__.py': _PROJECT_INIT.format(**ctx),
        f'{project_pkg}/main.py': _PROJECT_MAIN.format(**ctx),
        f'{module_pkg}/__init__.py': _MODULE_INIT.format(**ctx),
        f'{module_pkg}/routers.py': _MODULE_ROUTERS.format(**ctx),
        f'{module_pkg}/migrations/001_init.sql': _MIGRATION_001.format(**ctx),
    }


def generate_project(
    project_name: str,
    target_dir: Path | str | None = None,
    module_name: str | None = None,
    core_version: str | None = None,
) -> GenerationResult:
    """Genera el árbol de archivos de un nuevo proyecto consumer.

    Args:
      project_name: kebab-case, e.g. `mi-saas`. Será el `[project].name`
        en `pyproject.toml`.
      target_dir: dónde escribir. Default: `./{project_name}` (relativo
        al cwd). Si existe debe estar vacío (sino raise).
      module_name: nombre snake_case del módulo demo. Default:
        `{project_package}_modulo` para evitar colisión con el package
        del deployment.
      core_version: versión del core a pinnear en `pyproject.toml`.
        Default: la versión actual de `copiloto_core.__version__`. Útil
        para tests + para fijar releases experimentales.

    Returns:
      `GenerationResult` con todo lo escrito + paths resueltos.

    Raises:
      InvalidProjectNameError, InvalidModuleNameError, ProjectExistsError.
    """
    _validate_project_name(project_name)
    project_package = _to_snake_case(project_name)

    if module_name is None:
        module_name = f'{project_package}_modulo'
    _validate_module_name(module_name)

    if module_name == project_package:
        # Si colisionan, el `from {module_package} import ...` en main.py
        # se importa a sí mismo. Forzar override explícito.
        raise InvalidModuleNameError(
            f'El nombre del módulo ({module_name!r}) no puede ser igual '
            f'al package del proyecto ({project_package!r}). Pasá '
            f'--module-name=<otro>.',
        )

    if core_version is None:
        core_version = _CORE_VERSION

    resolved_target = (
        Path(target_dir) if target_dir is not None else Path.cwd() / project_name
    ).resolve()
    _ensure_target_dir_empty(resolved_target)

    ctx = {
        'project_name': project_name,
        'project_package': project_package,
        'module_package': module_name,
        'module_package_dashed': module_name.replace('_', '-'),
        'core_version': core_version,
    }

    files = _render_files(ctx)
    resolved_target.mkdir(parents=True, exist_ok=True)
    for rel_path, content in files.items():
        full = resolved_target / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding='utf-8')

    return GenerationResult(
        project_name=project_name,
        project_package=project_package,
        module_package=module_name,
        target_dir=resolved_target,
        files_written=tuple(sorted(files.keys())),
        core_version=core_version,
    )


__all__ = [
    'GenerationResult',
    'InvalidModuleNameError',
    'InvalidProjectNameError',
    'ProjectExistsError',
    'ScaffoldingError',
    'generate_project',
]
