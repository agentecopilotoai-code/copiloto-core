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
    prod_ready: bool = False   # Dockerfile + compose.prod + gunicorn + nginx + backup (v2.1.0+)


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

# ─── Auth0 ────────────────────────────────────────────────────────────
# NO declares AUTH0_DOMAIN ni AUTH0_API_AUDIENCE acá. El script
# `python -m copiloto_core auth0-configure` los escribe en
# `.env.auth0.local` (archivo separado, gitignored). Settings
# del core lee AMBOS archivos automáticamente — no necesitás
# duplicarlos.
#
# Las credentials del Management API (MGMT_CLIENT_ID/SECRET) NUNCA
# deben vivir en disco — solo en el shell durante el comando:
#   export MGMT_CLIENT_ID='...' MGMT_CLIENT_SECRET='...'
#   export TENANT_FRIENDLY_NAME='Mi SaaS'   # ← nombre visible en login
#   python -m copiloto_core auth0-configure
#   unset MGMT_CLIENT_ID MGMT_CLIENT_SECRET
#
# Ver docs/AUTH0.md (en el repo del core) para el modelo de 3 capas
# de credenciales y el flow completo.

# ─── JWT ──────────────────────────────────────────────────────────────
JWT_SECRET=CHANGE_ME

# ─── Service-to-service token ─────────────────────────────────────────
# Usado para auth entre servicios internos (workers, webhooks,
# background jobs). Generate-secrets le pone un random de 36 bytes.
SERVICE_TOKEN=CHANGE_ME

# ─── MFA enforcement (default ON) ─────────────────────────────────────
# El core ENFORCE MFA por default para users con roles privilegiados
# (platform_owner, owner, admin). Si recién arrancás y todavía no
# activaste la MFA Policy en Auth0 dashboard, el SPA del admin entra
# en loop infinito de logout. Dos opciones:
#   1. Activar MFA Policy en Auth0 (recomendado, ver docs/AUTH0.md).
#   2. Skip explícito SOLO en dev local descomentando esta línea:
# MFA_ENFORCEMENT_ENABLED=false

# ─── Email (multi-provider, v2.0.0) ───────────────────────────────────
# v2.0.0 (BREAKING): RESEND_API_KEY ya no se lee. Los providers viven en
# `app.email_providers` (DB) y se configuran desde la admin SPA en
# `/admin/platform/email-providers`. El operador agrega Resend, SendGrid,
# Mailgun o SMTP con prioridades; el dispatcher hace fallback chain.
# Ver `docs/EMAIL.md` para la guía paso-a-paso.
#
# Lo único que sobrevive en el env es el sender global de fallback:
# EMAIL_FROM_ADDRESS=invites@tu-dominio.com
# EMAIL_FROM_NAME={project_name}

# ─── Platform master key (Fernet, OBLIGATORIA desde v2.0.0) ───────────
# Cifra TODOS los secrets de providers configurables desde el admin UI:
#   - AI providers (api keys de OpenAI/Anthropic/Grok/etc.)
#   - Email providers (api keys de Resend/SendGrid/Mailgun + SMTP passwords)
#   - Cualquier futuro provider con credentials sensibles.
#
# El nombre histórico (AI_PROVIDER_MASTER_KEY) se mantiene por compat.
# Generate-secrets pone una Fernet key válida (44 chars base64-urlsafe).
# Si la rotás, los secrets viejos quedan ilegibles — re-crealos desde
# el admin UI.
AI_PROVIDER_MASTER_KEY=CHANGE_ME

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

# ─── Post-login / Post-logout redirects (opcionales, OVERRIDE smart) ─
# Por default v1.6.2+: smart routing en el callback OAuth.
#   - Si el user es platform_owner → /admin/ (panel del core)
#   - Sino → /dashboard (UI del consumer)
# Override estos defaults SOLO si querés un target fijo para TODOS:
# POST_LOGIN_REDIRECT_URL=/dashboard    # forzar dashboard también para platform_owner
# POST_LOGOUT_REDIRECT_URL=/             # default ya es /

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
!.env.prod.example
.secrets/

# Producción (v2.1.0+) — backups locales + logs
/var/backups/
*.dump
logs/
*.log

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

Compone el core con tus módulos y branding, y agrega handlers de
landing (`/`) y dashboard (`/dashboard`) para que tu SaaS tenga UI
propia. El admin del core queda OFF por default (v1.5.0+) — para
activarlo, pasá `admin_panel=True` al create_app.

Levantá con:

  uvicorn {project_package}.main:app --reload

Mapa de rutas resultante:

  /                            → landing.html (público, tiene "Iniciar sesión")
  /dashboard                   → dashboard.html (auth-required)
  /admin/login                 → OAuth flow del core (Auth0)
  /admin/callback              → callback OAuth (setea session)
  /admin/logout (POST)         → logout
  /admin/api/session           → JSON con el user logueado (usado por dashboard.html)
  /admin/                      → 404 (admin del core OFF por default)
  /v1/branding                 → branding JSON (público)
  /v1/{module_package_dashed}/* → endpoints de tu módulo demo
"""
from pathlib import Path

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from copiloto_core import (
    BrandingConfig,
    authenticate_request,
    create_app,
)

from {module_package} import module as {module_package}_module


# Cargar plantillas HTML como strings en memoria (no Jinja2 — los
# placeholders dinámicos se rellenan en el cliente via fetch al
# `/admin/api/session` que devuelve info del user logueado).
_TEMPLATES_DIR = Path(__file__).parent.parent / 'templates'
_LANDING_HTML = (_TEMPLATES_DIR / 'landing.html').read_text(encoding='utf-8')
_DASHBOARD_HTML = (_TEMPLATES_DIR / 'dashboard.html').read_text(encoding='utf-8')


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
    # admin_panel=True,  # opt-in para servir el SPA admin del core en /admin/
)


@app.get('/', include_in_schema=False, response_class=HTMLResponse)
async def landing() -> str:
    """Landing pública de {project_name}.

    Carga branding via `/v1/branding` y muestra un botón
    "Iniciar sesión" que dispara el OAuth flow del core
    (`/admin/login`). Editá `templates/landing.html` para
    customizar el HTML.
    """
    return _LANDING_HTML


@app.get('/dashboard', include_in_schema=False, response_class=HTMLResponse)
async def dashboard(_actor=Depends(authenticate_request)) -> str:
    """Dashboard de {project_name} (auth-required).

    `authenticate_request` valida el JWT del cookie de sesión
    (seteado por el flow OAuth del core). Sin login válido,
    devuelve 401 y el browser redirige a `/`.
    """
    return _DASHBOARD_HTML
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
# Templates HTML del consumer (v1.5.0)
# ──────────────────────────────────────────────────────────────────────
#
# El consumer (satguajira) sirve su propia landing en `/` y su propio
# dashboard en `/dashboard`. Vanilla HTML + CSS + un poquito de JS
# (sin React/Vue) — el operador puede customizarlos sin tocar build
# tools.
#
# La landing usa branding del core (/v1/branding) + un botón
# "Iniciar sesión" que dispara el OAuth flow del core (/admin/login).
# El dashboard fetcheas /admin/api/session para mostrar info del user.

_LANDING_HTML = '''\
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{project_name}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: #fff;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1rem;
    }}
    .container {{
      background: rgba(255, 255, 255, 0.08);
      backdrop-filter: blur(20px);
      padding: 3rem 2rem;
      border-radius: 16px;
      max-width: 480px;
      width: 100%;
      text-align: center;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
    }}
    h1 {{
      font-size: 2.5rem;
      margin-bottom: 0.5rem;
      font-weight: 700;
    }}
    .tagline {{ opacity: 0.9; margin-bottom: 2rem; font-size: 1.125rem; }}
    .login-btn {{
      display: inline-block;
      background: #fff;
      color: #667eea;
      padding: 0.875rem 2rem;
      border-radius: 8px;
      text-decoration: none;
      font-weight: 600;
      font-size: 1rem;
      transition: transform 0.15s, box-shadow 0.15s;
    }}
    .login-btn:hover {{
      transform: translateY(-1px);
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    }}
    .footer {{
      margin-top: 2rem;
      opacity: 0.6;
      font-size: 0.875rem;
    }}
    .footer a {{ color: #fff; text-decoration: underline; }}
  </style>
</head>
<body>
  <div class="container">
    <h1 id="product-name">{project_name}</h1>
    <p class="tagline" id="tagline">Cargando…</p>
    <a href="/admin/login" class="login-btn">Iniciar sesión</a>
    <p class="footer">
      Powered by <a href="https://github.com/agentecopilotoai-code/copiloto-core" target="_blank">copiloto-core</a>
    </p>
  </div>
  <script>
    // Hidrata el branding del core (logo, colores, tagline) al cargar.
    fetch('/v1/branding')
      .then(r => r.json())
      .then(b => {{
        if (b.product_name) document.getElementById('product-name').textContent = b.product_name;
        document.getElementById('tagline').textContent =
          'Bienvenido. Iniciá sesión para acceder a tu dashboard.';
      }})
      .catch(() => {{
        document.getElementById('tagline').textContent =
          'Iniciá sesión para acceder a tu dashboard.';
      }});
  </script>
</body>
</html>
'''


_DASHBOARD_HTML = '''\
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Dashboard · {project_name}</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f5f7fb;
      color: #1a1f36;
      min-height: 100vh;
    }}
    .topbar {{
      background: #fff;
      border-bottom: 1px solid #e5e9f2;
      padding: 1rem 2rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }}
    .topbar h2 {{ font-size: 1.125rem; font-weight: 600; }}
    .topbar .user {{ font-size: 0.875rem; color: #6b7280; }}
    .topbar .user button {{
      margin-left: 1rem;
      background: transparent;
      border: 1px solid #d1d5db;
      padding: 0.375rem 0.75rem;
      border-radius: 6px;
      cursor: pointer;
      color: #1a1f36;
      font: inherit;
    }}
    .topbar .user button:hover {{ background: #f3f4f6; }}
    main {{ padding: 2rem; max-width: 960px; margin: 0 auto; }}
    .card {{
      background: #fff;
      padding: 2rem;
      border-radius: 12px;
      box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
      margin-bottom: 1.5rem;
    }}
    .card h3 {{ font-size: 1.25rem; margin-bottom: 1rem; color: #1a1f36; }}
    .card pre {{
      background: #f3f4f6;
      padding: 1rem;
      border-radius: 8px;
      overflow-x: auto;
      font-size: 0.875rem;
      line-height: 1.5;
    }}
    .placeholder {{
      color: #6b7280;
      font-style: italic;
    }}
  </style>
</head>
<body>
  <header class="topbar">
    <h2 id="product-name">{project_name}</h2>
    <div class="user">
      <span id="user-email">Cargando…</span>
      <button onclick="logout()">Cerrar sesión</button>
    </div>
  </header>
  <main>
    <div class="card">
      <h3>¡Bienvenido!</h3>
      <p class="placeholder">
        Esta es tu dashboard. Editá <code>templates/dashboard.html</code>
        para construir la UI de {project_name}. La info del user logueado
        está en la variable <code>session</code> del JS abajo.
      </p>
    </div>
    <div class="card">
      <h3>Sesión actual</h3>
      <pre id="session-json">Cargando…</pre>
    </div>
    <div class="card">
      <h3>Tu módulo</h3>
      <p>Endpoints del módulo demo:</p>
      <ul>
        <li><a href="/v1/{module_package_dashed}/health" target="_blank">/v1/{module_package_dashed}/health</a> (público)</li>
        <li><a href="/v1/{module_package_dashed}/items" target="_blank">/v1/{module_package_dashed}/items</a> (auth-required)</li>
      </ul>
    </div>
  </main>
  <script>
    // Trae info del user logueado desde el endpoint de sesión del core.
    fetch('/admin/api/session')
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(session => {{
        document.getElementById('user-email').textContent =
          session.email || session.sub || 'usuario';
        document.getElementById('session-json').textContent =
          JSON.stringify(session, null, 2);
      }})
      .catch(() => {{
        // Si no hay sesión, mandar al landing
        window.location.href = '/';
      }});
    fetch('/v1/branding')
      .then(r => r.json())
      .then(b => {{
        if (b.product_name) document.getElementById('product-name').textContent = b.product_name;
      }});

    async function logout() {{
      await fetch('/admin/logout', {{ method: 'POST', credentials: 'include' }});
      window.location.href = '/';
    }}
  </script>
</body>
</html>
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
echo ""
echo "  Abrí en tu browser: http://localhost:8000/"
echo "  ⚠ Usá 'localhost' NO '0.0.0.0' — los Allowed Callback URLs de"
echo "    Auth0 se registran contra 'localhost' por default, y el"
echo "    callback OAuth falla si el browser está en otro origen."
echo ""
exec uvicorn {project_package}.main:app --reload --host 0.0.0.0 --port 8000
'''


_SECRETS_GITKEEP = '''\
# Este directorio guarda secretos locales (claves GPG, llaves privadas
# de backup, etc.) que NO deben commitearse. Ya está en .gitignore.
'''


# ═══════════════════════════════════════════════════════════════════════
# Producción (v2.1.0) — opt-in via --prod-ready
#
# Estos templates se generan cuando el usuario pasa `--prod-ready` al
# scaffolder. Son los mínimos necesarios para deployar a producción
# sin tener que escribirlos desde cero.
#
# Filosofía:
#   - Dockerfile multi-stage, USER no-root, healthcheck embebido.
#   - docker-compose.prod.yml lista para `docker compose up -d` en un
#     VPS — la app + infra en una sola unidad con restart policies.
#   - gunicorn delante de uvicorn workers (multi-process) — uvicorn
#     standalone solo recomienda 1 proceso; gunicorn maneja el fork.
#   - nginx config de ejemplo (TLS termination, /metrics deny,
#     security headers). El usuario decide si correrlo en host o
#     como sidecar container.
#   - Script de backup pg_dump con rotación + opcional rsync a S3.
#   - GitHub Actions workflow para build + push image a GHCR.
# ═══════════════════════════════════════════════════════════════════════

_DOCKERFILE = '''\
# syntax=docker/dockerfile:1.7
#
# Multi-stage build para {project_name}:
#   - builder: instala deps (gcc + headers de Postgres + Rust para
#     `cryptography` si necesitara compilar).
#   - runtime: solo Python + venv + código + USER no-root.
#
# La imagen final pesa ~250MB (python:3.12-slim + asyncpg + fastapi +
# copiloto-core + tu módulo). Si necesitás menor footprint considerá
# python:3.12-alpine, pero ojo con musl libc en wheels precompilados.

ARG PYTHON_VERSION=3.12

# ── Builder ───────────────────────────────────────────────────────────
FROM python:${{PYTHON_VERSION}}-slim AS builder

# Toolchain mínimo para wheels que requieran compilación.
RUN apt-get update && apt-get install -y --no-install-recommends \\
      build-essential \\
      libpq-dev \\
      git \\
    && rm -rf /var/lib/apt/lists/*

# venv aislado — copiable a runtime tal cual.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY pyproject.toml ./
# Si tenés requirements.txt en vez de pyproject:
# COPY requirements.txt ./
# RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir --upgrade pip && \\
    pip install --no-cache-dir gunicorn==23.0.0 && \\
    pip install --no-cache-dir .

# ── Runtime ───────────────────────────────────────────────────────────
FROM python:${{PYTHON_VERSION}}-slim AS runtime

# Solo runtime libs (libpq para asyncpg en algunos paths, ca-certs).
RUN apt-get update && apt-get install -y --no-install-recommends \\
      libpq5 \\
      ca-certificates \\
      tini \\
    && rm -rf /var/lib/apt/lists/*

# Usuario no-root — REQUERIDO por nuestra security posture.
# UID/GID 10001 evita colisión con users del host por accidente.
RUN groupadd --system --gid 10001 app && \\
    useradd --system --uid 10001 --gid app --no-create-home --shell /sbin/nologin app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \\
    PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    PORT=8000

WORKDIR /app
# Copiar el código de la app + el módulo. Sumá lo que corresponda a tu árbol.
COPY --chown=app:app {project_package} ./{project_package}
COPY --chown=app:app {module_package} ./{module_package}
COPY --chown=app:app templates ./templates
COPY --chown=app:app gunicorn_conf.py ./gunicorn_conf.py

USER app
EXPOSE 8000

# Healthcheck — pega contra /v1/livez (NO toca DB). Para readiness
# real usá el probe del orchestrator contra /v1/readyz, no este
# HEALTHCHECK del Docker.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \\
  CMD python -c "import urllib.request,sys; \\
    sys.exit(0 if urllib.request.urlopen('http://localhost:'+__import__('os').environ.get('PORT','8000')+'/v1/livez', timeout=3).status==200 else 1)"

# tini es PID 1 → reapea zombies + propaga SIGTERM correctamente.
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["gunicorn", "{project_package}.main:app", "-c", "gunicorn_conf.py"]
'''


_DOCKERIGNORE = '''\
# Lo MÍNIMO necesario para una imagen chica + builds rápidos.
.git
.github
.venv
venv
**/__pycache__
**/*.pyc
**/*.pyo
.pytest_cache
.ruff_cache
.coverage
htmlcov
.env
.env.*
!.env.example
.secrets
README.md
docs/
tests/
scripts/dev-up.sh
docker-compose.yml
.DS_Store
'''


_DOCKER_COMPOSE_PROD = '''\
# docker-compose.prod.yml — stack para deploy en un VPS único.
#
# Levanta tu app + infra como un sistema. Para escalar más allá de
# un VPS usá un orchestrator real (k8s, ECS, Nomad, Swarm). Esto es
# el sweet spot "1 VPS sirve 10-50k usuarios" sin la complejidad.
#
# Uso:
#   docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
#
# Antes del primer deploy:
#   1. Generar `.env.prod` con `python -m copiloto_core generate-secrets`
#      y editar valores reales (DATABASE_URL apuntando a `postgres`,
#      AUTH0_*, EMAIL providers, etc.).
#   2. Aplicar schema: `docker compose -f docker-compose.prod.yml run --rm app \\
#      python -m copiloto_core bootstrap --create-app-user --no-seed`
#   3. Migrate módulo: `docker compose -f docker-compose.prod.yml run --rm app \\
#      python -m copiloto_core migrate --module={module_package}`
#   4. `docker compose -f docker-compose.prod.yml up -d`

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    restart: always
    env_file: .env.prod
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    ports:
      - "127.0.0.1:8000:8000"   # bind a loopback → nginx en el host expone TLS
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/v1/readyz',timeout=3).status==200 else 1)"]
      interval: 15s
      timeout: 5s
      retries: 3
      start_period: 30s
    deploy:
      resources:
        limits:
          memory: 1G
        reservations:
          memory: 256M
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"

  postgres:
    image: pgvector/pgvector:pg16
    restart: always
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${{POSTGRES_PASSWORD:?POSTGRES_PASSWORD requerido en .env.prod}}
      POSTGRES_DB: {project_package}
    volumes:
      - postgres-data:/var/lib/postgresql/data
      - ./scripts/backup.sh:/usr/local/bin/backup.sh:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d {project_package}"]
      interval: 10s
      timeout: 5s
      retries: 10
    # NO exponer 5432 al host en prod — solo accesible desde la red interna.
    deploy:
      resources:
        limits:
          memory: 2G
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"

  redis:
    image: redis:7-alpine
    restart: always
    command: >
      redis-server
      --appendonly yes
      --maxmemory 256mb
      --maxmemory-policy allkeys-lru
      --requirepass ${{REDIS_PASSWORD:?REDIS_PASSWORD requerido en .env.prod}}
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "--no-auth-warning", "-a", "${{REDIS_PASSWORD}}", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    deploy:
      resources:
        limits:
          memory: 384M
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"

  minio:
    image: minio/minio:RELEASE.2025-04-22T22-12-26Z
    restart: always
    environment:
      MINIO_ROOT_USER: ${{S3_ACCESS_KEY_ID:?S3_ACCESS_KEY_ID requerido en .env.prod}}
      MINIO_ROOT_PASSWORD: ${{S3_SECRET_ACCESS_KEY:?S3_SECRET_ACCESS_KEY requerido en .env.prod}}
    command: server /data --console-address ":9001"
    volumes:
      - minio-data:/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 512M
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"
    # En prod, expone minio detrás de nginx con su propio subdomain
    # (ej. files.tudominio.com). NO expongas el puerto 9001 (consola)
    # al público — usá tunnel SSH o VPN para acceso admin.

volumes:
  postgres-data:
    name: {project_package}_postgres
  redis-data:
    name: {project_package}_redis
  minio-data:
    name: {project_package}_minio

networks:
  default:
    name: {project_package}_net
'''


_GUNICORN_CONF = '''\
"""gunicorn config para {project_name} en producción.

Convención del core: 1 master + N workers (uvicorn). El número de
workers depende del tipo de carga:

- I/O-bound (default, lo más común): (2 × CPU) + 1
- CPU-bound: matchear CPU físicos (no hyperthreads)
- Memory-constrained: medir RSS real con `ps` después de warmup

Para escalar más allá de 1 VPS, replicá horizontalmente este mismo
container y poné un load balancer (nginx, HAProxy, AWS ALB) delante.
"""
from __future__ import annotations

import multiprocessing
import os

# ── Workers ─────────────────────────────────────────────────────────────
# Override via WEB_CONCURRENCY env var (12-factor). Default = 2×CPU+1.
workers = int(os.environ.get('WEB_CONCURRENCY', (multiprocessing.cpu_count() * 2) + 1))
worker_class = 'uvicorn.workers.UvicornWorker'

# ── Network ─────────────────────────────────────────────────────────────
bind = f"0.0.0.0:{{os.environ.get('PORT', '8000')}}"
backlog = 2048

# ── Timeouts ────────────────────────────────────────────────────────────
# El default de gunicorn (30s) es OK para APIs típicas. Subir si tenés
# requests que legítimamente tardan más (PDFs grandes, embeddings,
# upload de archivos). NO subas a "infinito" — los workers colgados
# bloquean el slot.
timeout = int(os.environ.get('GUNICORN_TIMEOUT', '60'))
graceful_timeout = 30
keepalive = 5

# ── Worker lifecycle ────────────────────────────────────────────────────
# Reciclar workers cada N requests para evitar leaks acumulados.
max_requests = int(os.environ.get('GUNICORN_MAX_REQUESTS', '1000'))
max_requests_jitter = 100   # evita que todos los workers reciclen juntos
preload_app = False         # cada worker re-importa (compatible con cuda/torch en futuro)

# ── Logging ─────────────────────────────────────────────────────────────
# stdout/stderr → docker logs / journalctl / log shipping
accesslog = '-'
errorlog = '-'
loglevel = os.environ.get('GUNICORN_LOG_LEVEL', 'info')
# Formato compatible con structlog del core. JSON para shippers (Loki,
# CloudWatch, Datadog). Si preferís humano-legible, comentá el access
# log format o usá '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s'.
access_log_format = (
    '{{"remote":"%(h)s","time":"%(t)s","method":"%(m)s","path":"%(U)s",'
    '"status":%(s)s,"bytes":%(B)s,"duration_us":%(D)s,"ua":"%(a)s"}}'
)

# ── Proxy headers ───────────────────────────────────────────────────────
# Si tenés nginx/ALB delante, confiar en X-Forwarded-For y X-Forwarded-Proto.
# IMPORTANTE: forwarded_allow_ips debe coincidir con la IP del proxy
# real — '*' es OK si la app solo escucha en loopback (no expuesta).
forwarded_allow_ips = os.environ.get('FORWARDED_ALLOW_IPS', '127.0.0.1')
proxy_protocol = False

# ── Security ────────────────────────────────────────────────────────────
limit_request_line = 8190      # default Apache; bajar si NO usás query strings largos
limit_request_fields = 100
limit_request_field_size = 8190
'''


_NGINX_CONF_EXAMPLE = '''\
# nginx.conf.example — reverse proxy delante de {project_name} en prod.
#
# Asumimos que la app corre en `127.0.0.1:8000` (bind via
# docker-compose.prod.yml mappeado a loopback) y nginx en el host
# termina TLS + sirve estáticos + bloquea /metrics.
#
# Pegá esto en `/etc/nginx/sites-available/{project_package}.conf` y
# linkealo con `ln -s ... /etc/nginx/sites-enabled/`.
#
# Para TLS gratis usá certbot:
#   sudo certbot --nginx -d tudominio.com -d www.tudominio.com

# ── Rate limit zones (defínelas en http{{}} de /etc/nginx/nginx.conf) ─
# limit_req_zone $binary_remote_addr zone=app_general:10m rate=30r/s;
# limit_req_zone $binary_remote_addr zone=app_login:10m rate=5r/m;

upstream {project_package}_upstream {{
  server 127.0.0.1:8000;
  keepalive 32;
}}

# ── Redirect HTTP → HTTPS ──────────────────────────────────────────────
server {{
  listen 80;
  listen [::]:80;
  server_name tudominio.com www.tudominio.com;
  return 301 https://$host$request_uri;
}}

# ── App principal (HTTPS) ──────────────────────────────────────────────
server {{
  listen 443 ssl http2;
  listen [::]:443 ssl http2;
  server_name tudominio.com www.tudominio.com;

  # Certbot rellena estos paths automáticamente.
  ssl_certificate     /etc/letsencrypt/live/tudominio.com/fullchain.pem;
  ssl_certificate_key /etc/letsencrypt/live/tudominio.com/privkey.pem;
  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_prefer_server_ciphers on;
  ssl_session_cache shared:SSL:10m;
  ssl_session_timeout 1d;

  # ── Security headers (defense-in-depth, además del CSP del core) ───
  add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
  add_header X-Content-Type-Options "nosniff" always;
  add_header X-Frame-Options "DENY" always;
  add_header Referrer-Policy "strict-origin-when-cross-origin" always;
  add_header Permissions-Policy "geolocation=(), camera=(), microphone=()" always;

  # ── Body size — afinar según tu caso. Default 1MB es bajo para upload. ─
  client_max_body_size 25M;
  client_body_timeout 30s;

  # ── Bloquear /metrics al público (Prometheus debe ir por VPN o internal) ─
  location /metrics {{
    # Solo IPs de Prometheus / monitoring.
    allow 10.0.0.0/8;
    allow 127.0.0.1;
    deny all;
    proxy_pass http://{project_package}_upstream;
  }}

  # ── Rate limit en /admin/login (anti-brute) ────────────────────────
  location /admin/login {{
    limit_req zone=app_login burst=10 nodelay;
    proxy_pass http://{project_package}_upstream;
    include /etc/nginx/proxy_params;
  }}

  # ── Rate limit general en todo lo demás ────────────────────────────
  location / {{
    limit_req zone=app_general burst=60 nodelay;
    proxy_pass http://{project_package}_upstream;

    # Forward de IP real + esquema al backend (gunicorn lee X-Forwarded-*).
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host $host;

    # Timeouts amplios para uploads + streaming responses.
    proxy_connect_timeout 10s;
    proxy_read_timeout 90s;
    proxy_send_timeout 90s;

    # Keepalive con el upstream para evitar setup TCP por request.
    proxy_http_version 1.1;
    proxy_set_header Connection "";

    # Buffering: OFF para SSE/WebSocket si tu app las usa.
    # proxy_buffering off;
  }}

  # ── Logs (rotalos con logrotate, opcional log shipping) ────────────
  access_log /var/log/nginx/{project_package}_access.log combined buffer=32k flush=5s;
  error_log  /var/log/nginx/{project_package}_error.log warn;
}}
'''


_PROD_UP_SH = '''\
#!/usr/bin/env bash
# scripts/prod-up.sh — deploy + update idempotente del stack prod.
#
# Espejado del flow de `dev-up.sh` pero contra `docker-compose.prod.yml`.
# Pensado para correr DENTRO del VPS (o un runner CI con SSH al VPS) —
# NO en tu máquina local de desarrollo.
#
# Asume:
#   - Estás en el directorio raíz del proyecto en el VPS.
#   - `.env.prod` existe con secrets reales (no los CHANGE_ME del template).
#   - Docker Compose v2 está instalado y el usuario está en el grupo `docker`.
#
# Hace, en orden:
#   1. Build de la imagen `app` (rebuild si cambió el código).
#   2. Levanta postgres/redis/minio + espera healthy.
#   3. Bootstrap idempotente del schema platform (`app.*`).
#   4. Migrate de las migrations del módulo.
#   5. Up del service `app` (recreate si la imagen cambió).
#   6. Health check contra `/v1/readyz` con timeout 60s.
#
# Idempotente: re-correrlo después de cambios solo rebuilda + redeploya
# sin tocar volúmenes ni perder data.
#
# Para rollback manual a la imagen anterior:
#   docker compose -f docker-compose.prod.yml --env-file .env.prod \\
#     up -d --no-deps --force-recreate app
# (usando el tag de la imagen previa que tengas en local registry).
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f .env.prod ]; then
  echo "FALTA .env.prod — copialo de .env.prod.example y completá secrets:" >&2
  echo "    cp .env.prod.example .env.prod" >&2
  echo "    python -m copiloto_core generate-secrets --target=.env.prod" >&2
  exit 1
fi

COMPOSE="docker compose -f docker-compose.prod.yml --env-file .env.prod"

echo "→ Build de la imagen app…"
$COMPOSE build app

echo "→ Levantando infra (postgres, redis, minio) + esperando healthy…"
$COMPOSE up -d postgres redis minio
for i in {{1..60}}; do
  if $COMPOSE exec -T postgres pg_isready -U postgres > /dev/null 2>&1; then
    echo "  ✓ postgres listo"
    break
  fi
  sleep 1
done

echo "→ Bootstrap platform schema (idempotente — no-op si ya está aplicado)…"
$COMPOSE run --rm app python -m copiloto_core bootstrap --create-app-user --no-seed

echo "→ Aplicando migrations del módulo {module_package}…"
$COMPOSE run --rm app python -m copiloto_core migrate --module={module_package}

echo "→ Levantando app (recreate si la imagen cambió)…"
$COMPOSE up -d app

echo "→ Esperando /v1/readyz responda 200 (timeout 60s)…"
for i in {{1..30}}; do
  if curl -fsS http://127.0.0.1:8000/v1/readyz > /dev/null 2>&1; then
    echo ""
    echo "✓ deploy OK"
    echo "  /v1/readyz: $(curl -s http://127.0.0.1:8000/v1/readyz)"
    echo ""
    echo "  Si nginx ya está delante, validá HTTPS:"
    echo "    curl https://tudominio.com/v1/livez"
    exit 0
  fi
  sleep 2
done

echo "" >&2
echo "✗ /v1/readyz nunca respondió 200 en 60s." >&2
echo "  Logs del container app:" >&2
$COMPOSE logs --tail=50 app >&2
echo "" >&2
echo "  Rollback manual:" >&2
echo "    $COMPOSE down app  # detiene la nueva versión" >&2
echo "    # restorá la imagen previa via tag o re-deployá desde un commit anterior" >&2
exit 1
'''


_BACKUP_SH = '''\
#!/usr/bin/env bash
# scripts/backup.sh — backup de la DB de {project_name}.
#
# Estrategia:
#   1. pg_dump custom format (-Fc) — comprimido + restoreable parcial.
#   2. Rotación local: mantener últimos N días.
#   3. (opcional) rsync/aws-cli a S3 / minio remoto / backblaze para
#      protección off-site.
#
# Ejecutar via cron (en el host del docker-compose, NO dentro del
# container de postgres):
#
#   # /etc/cron.d/{project_package}-backup
#   0 3 * * * root /opt/{project_package}/scripts/backup.sh
#
# O via systemd timer (preferido — mejor logging + control):
#   ver docs/DEPLOYMENT.md § "Backup automatizado".

set -euo pipefail

# ── Config (override via env) ──────────────────────────────────────────
PROJECT="${{PROJECT:-{project_package}}}"
BACKUP_DIR="${{BACKUP_DIR:-/var/backups/$PROJECT}}"
RETENTION_DAYS="${{RETENTION_DAYS:-14}}"
COMPOSE_FILE="${{COMPOSE_FILE:-docker-compose.prod.yml}}"
PG_SERVICE="${{PG_SERVICE:-postgres}}"
PG_USER="${{PG_USER:-postgres}}"
PG_DB="${{PG_DB:-$PROJECT}}"

# Opcional — S3-compatible (minio remoto, AWS S3, backblaze, etc.)
S3_BUCKET="${{S3_BUCKET:-}}"
S3_ENDPOINT="${{S3_ENDPOINT:-}}"   # vacío = AWS

ts=$(date -u +%Y%m%d-%H%M%S)
out="$BACKUP_DIR/${{PROJECT}}-${{ts}}.dump"

mkdir -p "$BACKUP_DIR"

echo "→ Dumping $PG_DB → $out"
docker compose -f "$COMPOSE_FILE" exec -T "$PG_SERVICE" \\
  pg_dump -U "$PG_USER" -d "$PG_DB" -Fc --no-owner --no-acl \\
  > "$out"

# Verificar integridad — pg_restore --list lista los objetos sin restore.
if ! docker compose -f "$COMPOSE_FILE" exec -T "$PG_SERVICE" \\
       pg_restore --list < "$out" > /dev/null; then
  echo "ERROR: dump corrupto. NO se rota." >&2
  rm -f "$out"
  exit 1
fi
echo "  ✓ integridad OK ($(du -h "$out" | cut -f1))"

# ── Rotación local ─────────────────────────────────────────────────────
echo "→ Rotando dumps > ${{RETENTION_DAYS}} días en $BACKUP_DIR"
find "$BACKUP_DIR" -name "${{PROJECT}}-*.dump" -type f \\
  -mtime "+${{RETENTION_DAYS}}" -print -delete

# ── Off-site (opcional) ────────────────────────────────────────────────
if [ -n "$S3_BUCKET" ]; then
  echo "→ Subiendo a s3://$S3_BUCKET/"
  endpoint_arg=""
  if [ -n "$S3_ENDPOINT" ]; then
    endpoint_arg="--endpoint-url $S3_ENDPOINT"
  fi
  aws s3 cp $endpoint_arg "$out" "s3://$S3_BUCKET/$(basename "$out")" \\
    --storage-class STANDARD_IA
fi

echo "✓ backup completo: $out"
'''


_GITHUB_ACTIONS_DEPLOY = '''\
# .github/workflows/deploy.yml — build + push image + deploy SSH.
#
# Triggers:
#   - push a `main` → deploy automático a prod
#   - manual via "Run workflow" en GitHub UI → permite especificar tag
#
# Requiere los siguientes secrets en el repo (Settings → Secrets):
#
#   DEPLOY_HOST        — IP o hostname del VPS (ej. "prod.tudominio.com")
#   DEPLOY_USER        — usuario SSH (recomendado: usuario dedicado, NO root)
#   DEPLOY_SSH_KEY     — private key PEM (genera con `ssh-keygen -t ed25519`,
#                        agregá la public a ~/.ssh/authorized_keys del VPS)
#   DEPLOY_PATH        — path absoluto donde vive el compose (ej. "/opt/{project_package}")
#
# La imagen se publica a GHCR (ghcr.io/<owner>/{project_package}) — gratis
# para repos públicos, y para privados requiere GHCR token configurado
# en el VPS (`docker login ghcr.io`).

name: deploy

on:
  push:
    branches: [main]
  workflow_dispatch:
    inputs:
      tag:
        description: 'Tag a deployar (default: latest commit SHA)'
        required: false
        default: ''

permissions:
  contents: read
  packages: write

env:
  REGISTRY: ghcr.io
  IMAGE: ${{{{ github.repository_owner }}}}/{project_package}

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    outputs:
      image_tag: ${{{{ steps.meta.outputs.tag }}}}
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{{{ env.REGISTRY }}}}
          username: ${{{{ github.actor }}}}
          password: ${{{{ secrets.GITHUB_TOKEN }}}}

      - name: Compute tag
        id: meta
        run: |
          if [ -n "${{{{ inputs.tag }}}}" ]; then
            echo "tag=${{{{ inputs.tag }}}}" >> $GITHUB_OUTPUT
          else
            echo "tag=${{{{ github.sha }}}}" >> $GITHUB_OUTPUT
          fi

      - name: Build + push
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: |
            ${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE }}}}:${{{{ steps.meta.outputs.tag }}}}
            ${{{{ env.REGISTRY }}}}/${{{{ env.IMAGE }}}}:latest
          cache-from: type=gha
          cache-to: type=gha,mode=max

  deploy:
    needs: build-and-push
    runs-on: ubuntu-latest
    steps:
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1.2.0
        with:
          host: ${{{{ secrets.DEPLOY_HOST }}}}
          username: ${{{{ secrets.DEPLOY_USER }}}}
          key: ${{{{ secrets.DEPLOY_SSH_KEY }}}}
          script: |
            set -e
            cd ${{{{ secrets.DEPLOY_PATH }}}}
            docker compose -f docker-compose.prod.yml pull app
            # Ejecutar migrations ANTES de levantar la nueva versión.
            # Si fallan, abortamos el deploy y el container viejo sigue corriendo.
            docker compose -f docker-compose.prod.yml run --rm app \\
              python -m copiloto_core migrate --module={module_package}
            docker compose -f docker-compose.prod.yml up -d --no-deps app
            # Esperar que el nuevo /readyz responda 200 — sino rollback manual.
            for i in $(seq 1 30); do
              if curl -fsS http://127.0.0.1:8000/v1/readyz > /dev/null; then
                echo "✓ deploy OK"
                exit 0
              fi
              sleep 2
            done
            echo "✗ deploy fail — /v1/readyz nunca respondió 200"
            exit 1
'''


_ENV_PROD_EXAMPLE = '''\
# .env.prod.example — variables de entorno para deploy en producción.
#
# Copialo a `.env.prod` (NO commitear) y completá los valores reales.
# El comando `python -m copiloto_core generate-secrets --target=.env.prod`
# rellena los CHANGE_ME automáticamente.
#
# IMPORTANTE: en prod las URLs apuntan a los nombres de servicio del
# docker-compose (`postgres`, `redis`, `minio`), NO a `localhost`.

# ── Core ───────────────────────────────────────────────────────────────
ENV=production
LOG_LEVEL=info
PORT=8000
WEB_CONCURRENCY=4    # ajustar según tus CPUs reales

# ── DB (apunta al service `postgres` del compose) ──────────────────────
POSTGRES_PASSWORD=CHANGE_ME
DATABASE_URL=postgresql://{project_package}_app:CHANGE_ME@postgres:5432/{project_package}
DATABASE_ADMIN_URL=postgresql://postgres:CHANGE_ME@postgres:5432/{project_package}
APP_DB_USER={project_package}_app
APP_DB_PASSWORD=CHANGE_ME

# ── Redis (apunta al service `redis` del compose, con password) ────────
REDIS_PASSWORD=CHANGE_ME
REDIS_URL=redis://:CHANGE_ME@redis:6379/0

# ── S3 / minio (apunta al service `minio` del compose) ─────────────────
S3_ENDPOINT=http://minio:9000
S3_ACCESS_KEY_ID=CHANGE_ME
S3_SECRET_ACCESS_KEY=CHANGE_ME
S3_BUCKET={project_package}-prod

# ── Secrets internos del core ──────────────────────────────────────────
SERVICE_TOKEN=CHANGE_ME
SESSION_SECRET=CHANGE_ME
AI_PROVIDER_MASTER_KEY=CHANGE_ME

# ── Auth0 (producción — tenant distinto al de dev) ─────────────────────
AUTH0_DOMAIN=tu-tenant-prod.auth0.com
AUTH0_AUDIENCE=https://api.tudominio.com
AUTH0_ADMIN_CLIENT_ID=CHANGE_ME
AUTH0_ADMIN_CLIENT_SECRET=CHANGE_ME

POST_LOGIN_REDIRECT_URL=https://tudominio.com/dashboard
POST_LOGOUT_REDIRECT_URL=https://tudominio.com/

# MFA en prod SIEMPRE ON.
MFA_ENFORCEMENT_ENABLED=true

# Forwarded headers — solo si nginx está delante.
FORWARDED_ALLOW_IPS=127.0.0.1
'''


def _render_files(
    ctx: dict[str, str], *, with_infra: bool, prod_ready: bool = False,
) -> dict[str, str]:
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
        # v1.5.0: landing pública + dashboard auth-required del consumer.
        # El consumer customiza estos HTMLs sin tocar Python.
        'templates/landing.html': _LANDING_HTML.format(**ctx),
        'templates/dashboard.html': _DASHBOARD_HTML.format(**ctx),
        f'{module_pkg}/__init__.py': _MODULE_INIT.format(**ctx),
        f'{module_pkg}/routers.py': _MODULE_ROUTERS.format(**ctx),
        f'{module_pkg}/migrations/001_init.sql': _MIGRATION_001.format(**ctx),
    }
    if with_infra:
        files['docker-compose.yml'] = _DOCKER_COMPOSE.format(**ctx)
        files['scripts/dev-up.sh'] = _DEV_UP_SH.format(**ctx)
        files['.secrets/.gitkeep'] = _SECRETS_GITKEEP
    if prod_ready:
        # v2.1.0 — Production Deployment Kit.
        # Estos artefactos son aditivos: no rompen el flujo dev (el
        # consumer sigue usando `dev-up.sh` para iterar local). Son la
        # base mínima para deployar a un VPS o a un orchestrator.
        files['Dockerfile'] = _DOCKERFILE.format(**ctx)
        files['.dockerignore'] = _DOCKERIGNORE
        files['docker-compose.prod.yml'] = _DOCKER_COMPOSE_PROD.format(**ctx)
        files['gunicorn_conf.py'] = _GUNICORN_CONF.format(**ctx)
        files['nginx.conf.example'] = _NGINX_CONF_EXAMPLE.format(**ctx)
        # v2.1.1: espejo de dev-up.sh para el flow VPS+Compose.
        # Idempotente — re-correr solo rebuilda + redeploya.
        files['scripts/prod-up.sh'] = _PROD_UP_SH.format(**ctx)
        files['scripts/backup.sh'] = _BACKUP_SH.format(**ctx)
        files['.github/workflows/deploy.yml'] = _GITHUB_ACTIONS_DEPLOY.format(**ctx)
        files['.env.prod.example'] = _ENV_PROD_EXAMPLE.format(**ctx)
    return files


def generate_project(
    project_name: str,
    target_dir: Path | str | None = None,
    module_name: str | None = None,
    core_version: str | None = None,
    git_protocol: str = 'https',
    with_infra: bool = False,
    prod_ready: bool = False,
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
      prod_ready: si True (v2.1.0+), incluye **Production Deployment
        Kit**: `Dockerfile` multi-stage USER no-root,
        `docker-compose.prod.yml` con healthchecks + restart policies +
        resource limits, `gunicorn_conf.py` (workers + timeouts + JSON
        access log), `nginx.conf.example` (TLS + security headers +
        rate limit + /metrics deny), `scripts/backup.sh` (pg_dump con
        rotación + opcional S3 off-site), workflow de GitHub Actions
        (build → push GHCR → deploy SSH), `.env.prod.example` y
        `.dockerignore`. Se puede combinar con `with_infra` (los dos
        no se pisan: dev compose escucha en localhost, prod compose
        usa volúmenes nombrados y bind a loopback).

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

    files = _render_files(ctx, with_infra=with_infra, prod_ready=prod_ready)
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
        prod_ready=prod_ready,
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
