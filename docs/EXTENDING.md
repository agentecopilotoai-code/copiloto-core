# Extender CopilotoIA Core — guía del autor de módulos

Esta guía es para vos si querés construir un SaaS encima del core
sin reescribir auth, MFA, RLS, RBAC, audit, backups u observabilidad.

> **TL;DR**: tu módulo es un paquete Python con `pyproject.toml` que
> declara `copiloto-core` como dependencia y exporta un
> `CoreModule(...)`. El deployment compone con
> `create_app(modules=[tu_modulo])`. Todo lo demás (seguridad, DB,
> dispatch IA, observabilidad) lo hereda del core.

## Atajo: scaffolder (desde `v1.1.0`)

El core trae un comando para crear un proyecto completo (pyproject,
package del deployment, módulo demo, migration RLS-ready) en un solo
paso. Si arrancás desde cero, **usá esto en vez de pegar los snippets
manualmente** de esta guía:

```bash
pip install "copiloto-core @ git+ssh://git@github.com/agentecopilotoai-code/copiloto-core.git@v1.1.0"
python -m copiloto_core new-project mi-saas
cd mi-saas
pip install -e ".[dev]"
cp .env.example .env  # editar
python -m copiloto_core migrate --module=mi_saas_modulo
uvicorn mi_saas.main:app --reload
```

El resto de esta guía describe cómo el código generado funciona,
cómo extenderlo y qué te da el core.

---

## Tabla de contenidos

1. [Anatomía mínima de un módulo](#1-anatomía-mínima-de-un-módulo)
2. [Estructura de carpetas recomendada](#2-estructura-de-carpetas-recomendada)
3. [Declarar tu `CoreModule`](#3-declarar-tu-coremodule)
4. [Routers + `Depends` del core](#4-routers--depends-del-core)
5. [Schema SQL del módulo + migrations](#5-schema-sql-del-módulo--migrations)
6. [Capabilities + permisos](#6-capabilities--permisos)
7. [Hook de activación por tenant](#7-hook-de-activación-por-tenant)
8. [Admin frontend con marca propia](#8-admin-frontend-con-marca-propia)
9. [Devices / IoT / webhooks firmados](#9-devices--iot--webhooks-firmados)
10. [Composición en tu deployment](#10-composición-en-tu-deployment)
11. [Versionado + upgrades del core](#11-versionado--upgrades-del-core)
12. [Boundary del core — qué NO podés hacer](#12-boundary-del-core--qué-no-podés-hacer)
13. [Checklist de seguridad antes de prod](#13-checklist-de-seguridad-antes-de-prod)

---

## 1. Anatomía mínima de un módulo

El módulo más simple posible que funciona contra el core son 3 archivos:

```python
# mi_modulo/__init__.py
from copiloto_core import CoreModule
from mi_modulo.routers import router

module = CoreModule(code="mi_modulo", router=router)
```

```python
# mi_modulo/routers.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/ping")
def ping():
    return {"pong": True}
```

```toml
# pyproject.toml
[project]
name = "mi-modulo"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "copiloto-core @ git+ssh://git@github.com/agentecopilotoai-code/copiloto-core.git@v1.0.0",
  "fastapi>=0.115",
]

[tool.setuptools.packages.find]
include = ["mi_modulo*"]
```

Eso es. Ahora un deployment con `pip install -e .` + `from mi_modulo
import module; app = create_app(modules=[module])` y tu endpoint
`/v1/mi-modulo/ping` está vivo.

---

## 2. Estructura de carpetas recomendada

Para módulos reales (más de un endpoint), esta organización escala:

```
mi-modulo/
├── pyproject.toml
├── README.md
├── mi_modulo/                          ← paquete Python (NOMBRE = code)
│   ├── __init__.py                     ← exporta `module = CoreModule(...)`
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── inventario.py               ← /v1/mi-modulo/inventario/*
│   │   ├── historial.py                ← /v1/mi-modulo/historial/*
│   │   └── ingest.py                   ← /v1/mi-modulo/ingest (device HMAC)
│   ├── service/                        ← lógica de negocio (no FastAPI)
│   │   ├── alarms.py
│   │   └── notifications.py
│   ├── workers/
│   │   └── alarma_evaluator.py         ← loop async corrido por scheduler
│   ├── schemas.py                      ← Pydantic models
│   ├── migrations/
│   │   ├── 001_init.sql
│   │   ├── 002_add_indexes.sql
│   │   └── 003_partition_lectura.sql
│   ├── admin-spa/                      ← SPA propia con tu marca (opcional)
│   │   ├── package.json
│   │   ├── vite.config.js
│   │   ├── src/
│   │   └── dist/                       ← built al deploy
│   └── emails/                         ← templates para overrides del core
│       └── invitation.html
└── tests/
    ├── test_unit_routers.py
    └── test_unit_alarms.py
```

**Convenciones críticas**:
- El nombre del paquete Python (`mi_modulo/`) **debe matchear** el
  `CoreModule.code` (igual snake_case). El runner de migrations usa
  `code` para resolver el paquete con `importlib.resources`.
- Los paths en `sql_migrations` son **relativos al paquete Python**
  (no a la raíz del repo del módulo).

---

## 3. Declarar tu `CoreModule`

```python
# mi_modulo/__init__.py
from copiloto_core import CoreModule
from mi_modulo.routers.inventario import router as inventario_router
from mi_modulo.routers.historial import router as historial_router
from mi_modulo.routers.ingest import router as ingest_router
from mi_modulo.service.tenant_seed import seed_default_catalogs

# Composé los routers en uno solo (FastAPI los anida con prefix interno)
from fastapi import APIRouter

router = APIRouter()
router.include_router(inventario_router, prefix="/inventario")
router.include_router(historial_router,  prefix="/historial")
router.include_router(ingest_router,     prefix="/ingest")

module = CoreModule(
    code="mi_modulo",
    router=router,
    sql_migrations=(
        "migrations/001_init.sql",
        "migrations/002_add_indexes.sql",
        "migrations/003_partition_lectura.sql",
    ),
    capabilities=(
        "mi_modulo:inventario:read",
        "mi_modulo:inventario:write",
        "mi_modulo:historial:read",
        "mi_modulo:ingest:write",
    ),
    on_tenant_activate=seed_default_catalogs,
    static_mounts={
        "/m/mi-modulo": "mi_modulo/admin-spa/dist",  # SPA con tu marca
    },
)
```

### Reglas

- `code` debe matchear `^[a-z][a-z0-9_]{1,31}$` y ser el **nombre del
  paquete Python**.
- `capabilities` deben empezar con `<code>:` (anti-colisión cross-módulo).
- `sql_migrations` se aplican en el orden declarado. Usa naming
  `NNN_descripcion.sql` para que el orden sea evidente.
- `static_mounts` es opcional. Si lo usás, sirve tu SPA bajo el URL
  prefix indicado (ver § 8).

---

## 4. Routers + `Depends` del core

Todos los `Depends` que tu router necesite los importás de
`copiloto_core` directamente:

```python
# mi_modulo/routers/inventario.py
from fastapi import APIRouter, Depends
from copiloto_core import (
    authenticate_request,
    require_capability,
    require_module,
    audit,
)
from copiloto_core.db.pool import db

router = APIRouter()

@router.get("/zonas")
async def list_zonas(
    actor = Depends(authenticate_request),                   # Auth0 OIDC
    _gate = Depends(require_module("mi_modulo")),            # tenant_modules
    _cap  = Depends(require_capability("mi_modulo:inventario:read")),
):
    async with db.connection() as conn:           # RLS auto por TX
        rows = await conn.fetch("select * from mi_modulo.zona")
        return [dict(r) for r in rows]


@router.post("/zonas")
async def create_zona(
    payload: ZonaCreate,
    actor = Depends(authenticate_request),
    _gate = Depends(require_module("mi_modulo")),
    _cap  = Depends(require_capability("mi_modulo:inventario:write")),
):
    async with db.connection() as conn:
        row = await conn.fetchrow(
            'insert into mi_modulo.zona (...) values ($1, ...) returning *',
            payload.nombre, ...,
        )
        await audit(
            conn,
            actor_id=actor.actor_id,
            action="mi_modulo.zona.created",
            entity_type="mi_modulo.zona",
            entity_id=str(row["id"]),
            payload_despues=dict(row),
        )
        return dict(row)
```

### Qué te dan los `Depends`

| Depends | Hace | Si falta/falla |
|---------|------|----------------|
| `authenticate_request` | Resuelve JWT Auth0 → `request.state.actor_id`, `tenant_id`, `roles` | 401 |
| `require_module("mi_modulo")` | Lee `app.tenant_modules` con cache TTL 5min | 403 `module_not_enabled` |
| `require_capability("mi_modulo:x:y")` | Resuelve roles del actor → caps. `service:` bypass | 403 `capability_required` |
| `require_platform_owner` | Solo platform_owner rol | 403 |
| `require_mfa_for_privileged` | MFA verificada para roles privilegiados | 403 `mfa_required` |
| `require_service` | Service token M2M (workers internos) | 401 |

---

## 5. Schema SQL del módulo + migrations

Tu módulo **crea su propio schema** (no `app.*`):

```sql
-- mi_modulo/migrations/001_init.sql
create schema if not exists mi_modulo;

create table mi_modulo.zona (
  id          uuid primary key default gen_random_uuid(),
  tenant_id   uuid not null references app.tenants(id),
  nombre      text not null,
  created_at  timestamptz default now()
);

-- RLS multi-tenant — TODA tabla con tenant_id DEBE tenerlo.
alter table mi_modulo.zona enable row level security;
create policy rls_zona on mi_modulo.zona
  using (tenant_id = app.current_tenant_id());

create index ix_zona_tenant on mi_modulo.zona(tenant_id);
```

### Cuando una migration ya aplicada se modifica

El runner detecta y bloquea con `MigrationChecksumMismatchError`.
**Workflow correcto**: crear una migration nueva
(`002_alter_zona.sql`) en vez de editar la previa.

### Aplicar migrations en producción

```bash
python -m copiloto_core migrate --module=mi_modulo
```

Usa `DATABASE_ADMIN_URL` si está seteado (DDL necesita privilegios
mayores que `app_user`).

### En dev local

Las migrations se pueden auto-aplicar via el runner desde tu
deployment al startup. Más limpio: corré explícitamente con el CLI
como step del bootstrap.

---

## 6. Capabilities + permisos

Cada capability declarada en `CoreModule.capabilities` se **seedea
idempotentemente** en `app.capability` al primer arranque.

```python
capabilities=(
    "mi_modulo:inventario:read",
    "mi_modulo:inventario:write",
    "mi_modulo:ingest:write",
    "mi_modulo:admin:configure",
)
```

Después, desde el panel admin del core (`/admin → Roles & ACL`), el
platform_owner asigna esas capabilities a roles existentes o crea
roles nuevos. Es runtime, sin redeploy.

El `require_capability("...")` en tus handlers lee esa asignación con
cache TTL 5min.

### Capability vs role — separación de concerns

- **Capabilities**: acciones concretas que TU código verifica
  (`mi_modulo:ingest:write`). Las define el módulo.
- **Roles**: agrupaciones que el admin del tenant asigna a usuarios
  (`owner`, `operator`, `viewer`). Las define el platform_owner o
  vienen del template default.

---

## 7. Hook de activación por tenant

Cuando un platform_owner activa tu módulo en un tenant
(`PATCH /v1/platform/tenant-modules/{id}/{code}` con `enabled: true`),
el core invoca tu hook para que puedas seedear data default:

```python
# mi_modulo/service/tenant_seed.py
import asyncpg


async def seed_default_catalogs(
    tenant_id: str,
    conn: asyncpg.Connection,
    actor_id: str | None,
) -> None:
    """Se ejecuta una sola vez por (tenant, módulo) al activarse.

    Crea catálogos default (tipos de variables, plantillas, etc.) +
    asigna roles del módulo a quien lo activó (típicamente lo hace
    owner del tenant).
    """
    await conn.execute(
        '''
        insert into mi_modulo.variable (tenant_id, codigo, unidad) values
            ($1, 'temperatura', '°C'),
            ($1, 'humedad',     '%'),
            ($1, 'presion',     'hPa')
        on conflict do nothing
        ''',
        tenant_id,
    )
```

**Garantías**:
- Se llama DENTRO de la TX que cambia `tenant_modules.enabled=true`.
- Una excepción en el hook ABORTA la activación (transactional safety).
- Idempotente: si el tenant lo desactiva + reactiva, se llama de
  nuevo (responsabilidad del hook ser idempotente con `ON CONFLICT`).

---

## 8. Admin frontend con marca propia

El core sirve su propio admin en `/admin/*`. Tu módulo puede:

### Opción A — SPA propia separada bajo `/m/<code>`

```python
module = CoreModule(
    code="mi_modulo",
    router=router,
    static_mounts={
        "/m/mi-modulo": "mi_modulo/admin-spa/dist",  # tu Vite build
    },
)
```

Tu SPA puede:
1. Fetch `GET /v1/branding` al cargar para leer marca del deployment.
2. Usar la cookie session del BFF del core (ya seteada al login).
3. Llamar a `/v1/mi-modulo/*` para datos del módulo.
4. Hacer su propio routing client-side.

**Importante**: para fallback de rutas client-side (URLs como
`/m/mi-modulo/customers/123`), tu router debe agregar un catch-all
que sirva el `index.html`:

```python
from fastapi.responses import FileResponse
from pathlib import Path

@router.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    return FileResponse(Path("mi_modulo/admin-spa/dist/index.html"))
```

### Opción B — Servir solo APIs, sin frontend

Tu módulo expone solo `/v1/mi-modulo/*`. El cliente final usa el
admin del core para users/tenants/roles, y vos servís tu UI en otro
deployment (Vercel/Netlify/CDN separado).

---

## 9. Devices / IoT / webhooks firmados

Para endpoints que reciben telemetría de sensores físicos o webhooks
externos firmados con HMAC:

```python
from fastapi import APIRouter, Depends
from copiloto_core import verify_device_hmac
from copiloto_core.db.pool import db

router = APIRouter()


async def _lookup_device_secret(device_id: str) -> str | None:
    """Resuelve el secret del device. Acá puede ir un cache si el
    throughput lo justifica."""
    async with db.connection() as conn:
        row = await conn.fetchrow(
            'select hmac_secret from mi_modulo.device where id = $1',
            device_id,
        )
        return row['hmac_secret'] if row else None


@router.post("/ingest")
async def ingest_telemetry(
    request: Request,           # para acceso al raw body validado
    device = Depends(verify_device_hmac(_lookup_device_secret)),
):
    # device.device_id ya está verificado
    body_bytes = await request.body()
    payload = json.loads(body_bytes)
    # ...
```

El device envía:
- `X-Device-Id`: su identificador
- `X-Device-Signature`: `hex(hmac_sha256(secret, request_body))`

El core valida en constant-time. Si el device es desconocido o la
firma no matchea, 401 `device_unauthorized` (mismo error → anti-enum).

---

## 10. Composición en tu deployment

Tu repo del deployment (puede ser monorepo o separado) compose el
core + tus módulos:

```python
# my_saas/main.py
from copiloto_core import create_app, BrandingConfig
from mi_modulo import module as mi_modulo

app = create_app(
    modules=[mi_modulo],
    branding=BrandingConfig(
        product_name="Mi SaaS",
        logo_url="/static/logo.svg",
        primary_color="#0F1E33",
        support_email="soporte@misaas.com",
        copyright_holder="Mi SaaS S.A.S.",
    ),
)
```

```dockerfile
# my-saas/Dockerfile
FROM python:3.12-slim
RUN pip install copiloto-core mi-modulo my-saas  # vía git+ssh o PyPI privado
CMD ["uvicorn", "my_saas.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## 11. Versionado + upgrades del core

El core sigue **semver estricto** en su API pública (lo que se
importa de `copiloto_core` directo):

- **MAJOR** (1.x → 2.x): breaking change. Pre-anunciado con
  `DeprecationWarning` ≥ 2 minor versions antes.
- **MINOR** (1.0 → 1.1): añade símbolos. Tu código existente sigue
  funcionando.
- **PATCH** (1.0.0 → 1.0.1): bugfixes internos.

### Cómo pinear

```toml
[project]
dependencies = [
  "copiloto-core>=1.0,<2.0",   # acepta cualquier 1.x.y
]
```

Para git+ssh:
```toml
"copiloto-core @ git+ssh://git@github.com/.../copiloto-core.git@v1.0.0"
```

### Cuándo upgradear

- **Patch**: sin pensarlo (es bugfix interno).
- **Minor**: leé el CHANGELOG, valida que tus tests pasen.
- **Major**: leé la upgrade guide específica + tiempo para refactor.

### Multi-version simultánea

**NO soportado en el mismo container.** Si tenés módulos A y B en el
mismo deployment, ambos deben ser compatibles con la misma major.
Esto es un trade-off conocido del modelo "core como librería".

---

## 12. Boundary del core — qué NO podés hacer

Estas reglas las **debés respetar** para no romper garantías de
seguridad/correctness:

### 12.1 NO crear tu propio pool asyncpg

```python
# ❌ MAL — bypasses RLS
import asyncpg
pool = await asyncpg.create_pool(...)

# ✅ BIEN — usa el pool del core
from copiloto_core.db.pool import db
async with db.connection(tenant_id=...) as conn:
    ...
```

El pool del core setea `app.tenant_id` por transacción para que RLS
filtre automáticamente. Si abrís tu propio pool, los queries de tu
módulo IGNORAN RLS y pueden leak data entre tenants.

### 12.2 NO instanciar AI providers directamente

```python
# ❌ MAL — bypasses fallback + circuit breaker + audit
from copiloto_core.ai.providers.openai import OpenAIProvider
provider = OpenAIProvider(api_key="...")

# ✅ BIEN — vía dispatch
from copiloto_core import dispatch

async def call_fn(provider):
    return await provider.generate_text(prompt="...")

result = await dispatch(conn, modality="llm", call_fn=call_fn)
```

`dispatch` te da:
- Fallback chain configurada por platform_owner
- Circuit breaker per-provider
- Audit en `app.provider_dispatch`
- Backoff exponencial + Retry-After
- Métricas Prometheus

### 12.3 NO escribir en schema `app.*`

Tu módulo tiene su propio schema (`mi_modulo.*`). NO mutes tablas del
core (`app.tenants`, `app.users`, `app.audit_log`, etc.).

Excepciones explícitas:
- `audit(conn, action="...", ...)` — escribe en `app.audit_log` PERO
  usás la función del core, no SQL crudo.
- Foreign keys hacia `app.tenants(id)` son OK y recomendadas.

### 12.4 NO monkey-patch el core

```python
# ❌ MAL — frágil, rompe en upgrade
import copiloto_core.core.security as sec
sec.authenticate_request = mi_version_custom
```

Si necesitás auth custom, escribí tu propio `Depends` y úsalo en tus
rutas. NO sustituyas el del core.

---

## 13. Checklist de seguridad antes de prod

Antes de poner tráfico real en tu módulo:

- [ ] TODAS las tablas con `tenant_id` tienen RLS habilitado +
      policy correcta usando `app.current_tenant_id()`.
- [ ] TODOS los endpoints HTTP usan `authenticate_request` salvo los
      públicos justificados (telemetría con `verify_device_hmac`,
      webhooks firmados con HMAC, health checks).
- [ ] TODOS los endpoints con escritura usan `require_capability(...)`
      (no solo `authenticate_request`).
- [ ] El módulo usa el pool del core (`copiloto_core.db.pool.db`)
      en TODOS los queries — verificable con
      `grep -r "asyncpg.create_pool" mi_modulo/` → debe estar vacío.
- [ ] Las migrations son inmutables — nunca editar una aplicada.
- [ ] Los secrets (API keys, GPG keys) NO están hardcoded — usar
      `resolve_secret_ref()` del core.
- [ ] El módulo tiene tests con coverage ≥ 85% — gates CI.
- [ ] El módulo NO escribe a stdout/stderr (usa `structlog` o el
      logger del core).
- [ ] Cambios mutativos se loguean en `app.audit_log` via `audit(...)`.

---

## Referencias

- API pública del core: `copiloto_core/__init__.py` (re-exports)
- `CoreModule` dataclass + validaciones: `copiloto_core/extension.py`
- Gating helpers: `copiloto_core/auth/gating.py`
- Devices/HMAC: `copiloto_core/auth/devices.py`
- Migrations runner: `copiloto_core/migrations/`
- Branding: `copiloto_core/branding.py`
- Política semver: `copiloto_core/__init__.py` docstring

## Soporte

- Issues del core: https://github.com/agentecopilotoai-code/copiloto-core/issues
- Runbooks operativos: `docs/runbooks/`
