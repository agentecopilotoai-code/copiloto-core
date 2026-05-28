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

# Org de GitHub donde vive el core. Centralizado para que el día
# que migre (fork, espejo, etc.) sea un solo punto de cambio.
_CORE_GIT_ORG = 'agentecopilotoai-code'
_CORE_GIT_REPO = 'copiloto-core'

# Protocolos soportados en el pin del pyproject generado.
_GIT_PROTOCOLS = ('https', 'ssh')


class ScaffoldingError(Exception):
    """Base para errores del generador."""


class InvalidProjectNameError(ScaffoldingError):
    """El nombre del proyecto no matchea `_PROJECT_NAME_RE`."""


class InvalidModuleNameError(ScaffoldingError):
    """El nombre del módulo no matchea `_MODULE_NAME_RE`."""


class InvalidGitProtocolError(ScaffoldingError):
    """`git_protocol` no es uno de `_GIT_PROTOCOLS`."""


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
    git_protocol: str          # 'https' o 'ssh' — protocolo del pin
    with_infra: bool = False   # docker-compose + scripts/dev-up.sh incluidos


def _core_pin_url(git_protocol: str, version: str) -> str:
    """Construye el URL del pin de `copiloto-core` en `pyproject.toml`.

    - `https`: `git+https://github.com/<org>/<repo>.git@v<ver>` —
      funciona con `gh auth setup-git` sin requerir SSH key del usuario.
    - `ssh`: `git+ssh://git@github.com/<org>/<repo>.git@v<ver>` —
      requiere que la SSH key registrada en GitHub pertenezca a una
      cuenta con acceso al repo.
    """
    if git_protocol == 'https':
        return (
            f'git+https://github.com/{_CORE_GIT_ORG}/{_CORE_GIT_REPO}.git'
            f'@v{version}'
        )
    return (
        f'git+ssh://git@github.com/{_CORE_GIT_ORG}/{_CORE_GIT_REPO}.git'
        f'@v{version}'
    )


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
  #
  # Default es HTTPS porque funciona con `gh auth setup-git` sin
  # requerir que tu llave SSH personal tenga acceso al org. Si
  # preferís SSH, regenerá con --git-protocol=ssh o reemplazá la
  # línea a mano por:
  #   "copiloto-core @ git+ssh://git@github.com/agentecopilotoai-code/copiloto-core.git@v{core_version}",
  "copiloto-core @ {core_pin_url}",
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
# Copiá este archivo a `.env` y luego corré:
#   python -m copiloto_core generate-secrets
# que reemplaza los `CHANGE_ME` con valores random sin tocar el resto.
# `.env` está en `.gitignore` por seguridad — nunca lo commitees.

# ─── Postgres (multi-tenant, requiere extension pgvector si usás IA) ──
# IMPORTANTE: `localhost` asume que uvicorn corre en tu host. Si
# corrés todo dentro de docker, cambiá a `postgres` (el service name
# del compose).
DATABASE_URL=postgres://copiloto_app:CHANGE_ME@localhost:5432/{project_package}
DATABASE_ADMIN_URL=postgres://postgres:CHANGE_ME@localhost:5432/{project_package}
APP_DB_USER=copiloto_app
APP_DB_PASSWORD=CHANGE_ME
# Password del usuario `postgres` (admin). Matchea con docker-compose:
#   environment: POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD}}
POSTGRES_PASSWORD=CHANGE_ME

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
JWT_SECRET=CHANGE_ME

# ─── Redis (sessions + OAuth state + rate-limit) ──────────────────────
REDIS_URL=redis://localhost:6379/0

# ─── S3 / MinIO (uploads, exports) ────────────────────────────────────
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY_ID=minioadmin
S3_SECRET_ACCESS_KEY=CHANGE_ME
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

# 2. Variables de entorno
cp .env.example .env
# Editar .env con tus valores reales (especialmente JWT_SECRET y AUTH0_*)
```

### Si generaste con `--with-infra` (un solo comando)

```bash
./scripts/dev-up.sh
```

`dev-up.sh` arranca docker compose (postgres + redis + minio),
aplica el schema platform del core (`python -m copiloto_core bootstrap`),
aplica las migraciones (`python -m copiloto_core migrate --module={module_package}`)
y deja la app corriendo en `uvicorn {project_package}.main:app`.

### Sin `--with-infra` (BYO infra)

```bash
# Levantá postgres + redis + minio donde prefieras (RDS, Docker, etc.),
# y actualizá DATABASE_URL/REDIS_URL/S3_* en .env.

# Una vez tras crear la DB (idempotente):
python -m copiloto_core bootstrap --create-app-user

# Cada vez que agregás migrations al módulo:
python -m copiloto_core migrate --module={module_package}

# Arrancar la app:
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
├── docker-compose.yml       # postgres + redis + minio
├── scripts/
│   └── dev-up.sh            # compose up + bootstrap + migrate + uvicorn
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


# ──────────────────────────────────────────────────────────────────────
# Templates infra (opt-in con --with-infra) — v1.2.0
# ──────────────────────────────────────────────────────────────────────

_DOCKER_COMPOSE = '''\
# docker-compose para dev local. Levanta solo lo MÍNIMO que el core
# necesita: postgres (con pgvector), redis, minio (S3-compatible).
#
# Para producción usá managed services (RDS/Cloud SQL, ElastiCache,
# S3 real). Este archivo es para iterar local — no para deploy.

services:
  postgres:
    image: pgvector/pgvector:pg16
    restart: unless-stopped
    # docker-compose lee `.env` del cwd para interpolar ${{VAR}}.
    # POSTGRES_PASSWORD viene del .env, generado por
    # `python -m copiloto_core generate-secrets`.
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD:-postgres}}
      POSTGRES_DB: {project_package}
    ports:
      - "5432:5432"
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d {project_package}"]
      interval: 5s
      timeout: 5s
      retries: 20

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    command: redis-server --appendonly yes
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data

  minio:
    image: minio/minio:RELEASE.2025-04-22T22-12-26Z
    restart: unless-stopped
    environment:
      MINIO_ROOT_USER: ${{S3_ACCESS_KEY_ID:-minioadmin}}
      MINIO_ROOT_PASSWORD: ${{S3_SECRET_ACCESS_KEY:-minioadmin}}
    command: server /data --console-address ":9001"
    ports:
      - "9000:9000"   # API S3
      - "9001:9001"   # consola web
    volumes:
      - minio-data:/data

volumes:
  postgres-data:
  redis-data:
  minio-data:
'''


_DEV_UP_SH = '''\
#!/usr/bin/env bash
# scripts/dev-up.sh — flujo full de dev local en un comando.
#
# Hace, en orden:
#   1. docker compose up -d (postgres + redis + minio)
#   2. Espera a que postgres esté healthy
#   3. python -m copiloto_core bootstrap --create-app-user
#      (aplica el schema platform `app.*` + crea el rol runtime)
#   4. python -m copiloto_core migrate --module={module_package}
#      (aplica las migraciones del módulo)
#   5. uvicorn {project_package}.main:app --reload
#
# Idempotente: re-correrlo con la infra ya levantada solo arranca el
# uvicorn (los pasos 3+4 son no-op si ya se aplicaron).
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
  echo "FALTA .env — copialo de .env.example y editalo:" >&2
  echo "    cp .env.example .env" >&2
  exit 1
fi

# Notar que NO sourceamos .env desde bash acá. El core ya lo lee
# automáticamente via pydantic-settings + python-dotenv cuando se
# carga `get_settings()`. Sourcear desde bash era frágil porque
# cualquier comentario con paréntesis, comilla rara o backtick rompe
# el parser (`line N: X: command not found`). v1.2.1 lo removió.

echo "→ Levantando docker compose…"
docker compose up -d

echo "→ Esperando a que postgres esté healthy…"
for i in {{1..30}}; do
  if docker compose ps postgres --format json 2>/dev/null \\
      | grep -q '"Health":"healthy"'; then
    echo "  ✓ postgres listo"
    break
  fi
  sleep 1
done

echo "→ Aplicando platform schema del core…"
python -m copiloto_core bootstrap --create-app-user

echo "→ Aplicando migrations del módulo {module_package}…"
python -m copiloto_core migrate --module={module_package}

echo "→ Arrancando uvicorn (Ctrl+C para detener)…"
exec uvicorn {project_package}.main:app --reload --host 0.0.0.0 --port 8000
'''


_SECRETS_GITKEEP = '''\
# Este directorio guarda secretos locales (claves GPG, llaves privadas
# de backup, etc.) que NO deben commitearse. Ya está en .gitignore.
'''


def _render_files(ctx: dict[str, str], *, with_infra: bool) -> dict[str, str]:
    """Renderiza todos los templates con el contexto. Devuelve un
    dict `{path_relativo: contenido}`.

    Centralizado para que los tests verifiquen exactamente lo que se
    escribe a disco sin tocar el FS.
    """
    project_pkg = ctx['project_package']
    module_pkg = ctx['module_package']
    files = {
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
    if with_infra:
        files['docker-compose.yml'] = _DOCKER_COMPOSE.format(**ctx)
        files['scripts/dev-up.sh'] = _DEV_UP_SH.format(**ctx)
        files['.secrets/.gitkeep'] = _SECRETS_GITKEEP
    return files


def generate_project(
    project_name: str,
    target_dir: Path | str | None = None,
    module_name: str | None = None,
    core_version: str | None = None,
    git_protocol: str = 'https',
    with_infra: bool = False,
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
      git_protocol: protocolo del pin generado en `pyproject.toml`.
        - `'https'` (DEFAULT, v1.1.1+): pin via HTTPS. Funciona con
          `gh auth setup-git` sin necesidad de SSH key configurada
          en GitHub. Recomendado para onboarding.
        - `'ssh'`: pin via `git+ssh://`. Requiere que la SSH key del
          usuario esté registrada en una cuenta con acceso al repo.
          Comportamiento pre-v1.1.1.
      with_infra: si True (v1.2.0+), incluye `docker-compose.yml`
        (postgres + redis + minio), `scripts/dev-up.sh` (un solo
        comando para levantar todo) y `.secrets/.gitkeep`. Pensado
        para arrancar local sin tener que escribir docker run a mano.

    Returns:
      `GenerationResult` con todo lo escrito + paths resueltos.

    Raises:
      InvalidProjectNameError, InvalidModuleNameError,
      InvalidGitProtocolError, ProjectExistsError.
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

    if git_protocol not in _GIT_PROTOCOLS:
        raise InvalidGitProtocolError(
            f'git_protocol inválido: {git_protocol!r}. Debe ser uno de '
            f'{_GIT_PROTOCOLS}.',
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
        'core_pin_url': _core_pin_url(git_protocol, core_version),
    }

    files = _render_files(ctx, with_infra=with_infra)
    resolved_target.mkdir(parents=True, exist_ok=True)
    for rel_path, content in files.items():
        full = resolved_target / rel_path
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, encoding='utf-8')
        # scripts/*.sh nacen ejecutables; sino el usuario tiene que
        # acordarse de `chmod +x` y nos comemos otro error de onboarding.
        if rel_path.endswith('.sh'):
            full.chmod(0o755)

    return GenerationResult(
        project_name=project_name,
        project_package=project_package,
        module_package=module_name,
        target_dir=resolved_target,
        files_written=tuple(sorted(files.keys())),
        core_version=core_version,
        git_protocol=git_protocol,
        with_infra=with_infra,
    )


__all__ = [
    'GenerationResult',
    'InvalidGitProtocolError',
    'InvalidModuleNameError',
    'InvalidProjectNameError',
    'ProjectExistsError',
    'ScaffoldingError',
    'generate_project',
]
