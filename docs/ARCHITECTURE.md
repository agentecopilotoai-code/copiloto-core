# Arquitectura — módulos opt-in con core transversal

Este documento es la **fuente única de verdad** sobre cómo se compone el backend.
Actualizar este archivo cada vez que se agrega un módulo nuevo o se modifica el
core compartido.

## Principios

1. **Core transversal mínimo.** Solo lo que TODOS los módulos comparten vive
   en `app.core.*` y `infra/postgres/10-core.sql`: identidad/auth, tenants,
   sesiones, RLS helpers, IA platform-wide, activación de módulos. Nada
   product-specific.

2. **Módulos opt-in independientes.** Cada producto (chatbot base, influencer/
   Ravit Studio, gestión documental) vive aislado. Un módulo NUNCA importa
   código de otro módulo. Si necesita algo compartido, se promueve al core.

3. **Activación por tenant.** Un tenant ve un módulo solo si la fila
   `app.tenant_modules (tenant_id, module, enabled=true)` existe. Cada
   módulo tiene un gate `ensure_<name>_module_enabled` que retorna 404 (no
   403) cuando no está activo — esto evita filtrar la existencia del feature
   a tenants sin acceso.

4. **Auth y AI son los únicos servicios verdaderamente transversales.** Todo
   lo demás es responsabilidad del módulo que lo use.

## Layout del repositorio

```
app/
  core/                                ← TRANSVERSAL (auth + identity + AI + config)
    security.py                        ← authenticate_request, JWT, MFA gates
    identity.py                        ← resolve_user_id (Auth0 sub ↔ app.users.id)
    config.py
    logging.py
  ai/                                  ← TRANSVERSAL (proveedores LLM/image/etc)
    registry.py
    providers/
  db/
    pool.py                            ← asyncpg pool + RLS helpers
  api/v1/                              ← agregador de routers v1
  admin/                               ← BFF del admin-panel (proxy + auth cookies)

  influencer/                          ← MÓDULO OPT-IN
    __init__.py                        ← MODULE_NAME, ensure_module_enabled, cache
    router.py                          ← APIRouter(prefix='/v1/influencer')
    handlers/                          ← (si crece — por dominio)
    services/
    schemas/
    security.py                        ← gates específicos del módulo (opcional)

  gd/                                  ← MÓDULO OPT-IN (mismo layout)
    __init__.py
    routes.py
    handlers/
    schemas/
    security.py
    bootstrap.py                       ← seed automático al activar

infra/postgres/
  00-init-roles.sh                     ← roles Postgres
  10-core.sql                          ← schema app + RLS + tenant_modules + platform_ai_providers
  20-seed.sql                          ← tenants demo (Taller, Barbería, Mascotas)
  modules/                             ← SUBDIRECTORIO — NO lo carga el init de Postgres
    influencer.sql                     ← schema influencer + grants + activación dev
    gd.sql                             ← schema gd + grants + activación dev
```

## Servicios transversales

### Auth (`app.core.security`)

Toda request autenticada pasa por `authenticate_request` que:
1. Lee `Authorization: Bearer <jwt>` (típicamente del session cookie del BFF).
2. Lee `X-Tenant-Id` (header).
3. Resuelve support_mode (JWT claim permanente O cookie temporal opt-in).
4. Setea en `request.state`:
   - `actor_id` — el `sub` del JWT (string Auth0 como `'google-oauth2|...'`).
   - `tenant_id` — UUID del tenant activo.
   - `support_mode` — bool.
   - `roles` — lista de roles globales del JWT.

**No setea `request.state.user_id` por sí solo.** Los módulos que necesiten
el UUID interno de `app.users` lo resuelven via `app.core.identity`.

### Identity (`app.core.identity`)

```python
from app.core.identity import resolve_user_id_from_request

async def my_handler(request: Request, conn = Depends(get_db)):
    user_id = await resolve_user_id_from_request(request, conn)
    # ahora user_id es el UUID de app.users.id, cacheado en request.state.user_id
```

Mapea `actor_id` (Auth0 `sub`) → `app.users.id` (UUID). Cachea el resultado
en `request.state.user_id` para evitar re-consultas en el mismo request.

### AI (`app.ai`)

Proveedores LLM, image, video, TTS, STT configurados por `platform_owner` a
nivel plataforma (NO por tenant). Cualquier módulo (chatbot, influencer, gd)
los consume vía `app.ai.registry`.

## Anatomía de un módulo opt-in

Mínimo viable para que un módulo nuevo se "encienda":

### 1. `app/<module_name>/__init__.py`

```python
from typing import Final
import asyncpg
from fastapi import Depends, HTTPException, Request, status
from app.core.security import authenticate_request
from app.db.pool import get_db

MODULE_NAME: Final[str] = 'mi_modulo'  # debe matchear el CHECK constraint de app.tenant_modules
_CACHE_TTL_SECONDS: Final[float] = 300.0
_GATE_CACHE: dict[tuple[str, str], tuple[float, bool]] = {}

def _cache_invalidate() -> None:
    _GATE_CACHE.clear()

async def ensure_module_enabled(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    _auth: None = Depends(authenticate_request),
) -> None:
    tenant_id = getattr(request.state, 'tenant_id', None)
    if not tenant_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'Not Found')
    # ... lookup en app.tenant_modules con cache TTL, 404 si no activo
```

### 2. `app/<module_name>/router.py`

```python
from fastapi import APIRouter, Depends
from app.core.security import authenticate_request
from . import ensure_module_enabled

router = APIRouter(
    prefix='/v1/<module_name>',  # convención: /v1/<module> SIN /api
    tags=['<module_name>'],
    dependencies=[
        Depends(authenticate_request),    # ANTES de ensure — orden importa
        Depends(ensure_module_enabled),
    ],
)

@router.get('/_health')
async def health() -> dict[str, str]:
    return {'module': '<module_name>', 'status': 'active'}
```

### 3. Wiring en `app/main.py`

```python
from app.<module_name>.router import router as <module_name>_router
# ...
api.include_router(<module_name>_router)
```

### 4. Schema en `infra/postgres/modules/<module_name>.sql`

```sql
-- Schema aislado del core
create schema if not exists <module_name>;
grant usage on schema <module_name> to copiloto_app;
grant select, insert, update, delete on all tables in schema <module_name> to copiloto_app;
alter default privileges in schema <module_name>
  grant select, insert, update, delete on tables to copiloto_app;

-- Tablas del módulo con RLS
create table if not exists <module_name>.algo (
  id uuid primary key default gen_random_uuid(),
  tenant_id uuid not null references app.tenants(id) on delete restrict,
  -- ...
);
alter table <module_name>.algo enable row level security;
create policy algo_tenant_isolation on <module_name>.algo
  for all
  using (tenant_id = app.current_tenant_id() or app.support_mode())
  with check (tenant_id = app.current_tenant_id() or app.support_mode());

-- Activación automática para Demo Taller (dev local)
insert into app.tenant_modules (tenant_id, module, enabled, activated_at)
values ('11111111-1111-1111-1111-111111111111', '<module_name>', true, now())
on conflict (tenant_id, module) do nothing;
```

### 5. CHECK constraint del catálogo

Agregar el `<module_name>` literal al CHECK de `app.tenant_modules.module`
en `infra/postgres/10-core.sql`. Sino el INSERT falla con
`CheckViolationError`.

### 6. Cargar el módulo

```bash
./scripts/bootstrap.sh --reset --yes --module=<module_name>
# o bien
./scripts/bootstrap.sh --reset --yes   # carga TODOS los módulos disponibles
```

## Reglas de aislamiento

- **NUNCA** importes `app.gd.*` desde `app.influencer.*` (y viceversa). Si
  necesitás algo compartido, promovelo a `app.core.*`.
- **NUNCA** referencies tablas de otro módulo en SQL con un JOIN duro. Si
  necesitás datos, exponé una función/view en el módulo dueño.
- **NUNCA** asumas que otro módulo está cargado. Cada módulo debe funcionar
  con SOLO core + sí mismo.
- El frontend respeta el mismo aislamiento: `admin-panel/src/features/gd/`
  no importa de `features/influencer/` y viceversa. El único shared es
  `src/services/coreApi.js`, `src/components/ui/*`, `src/app/*`.

## Cómo agregar un módulo nuevo (checklist)

1. ⏳ Crear directorio `app/<module>/` con el layout de arriba.
2. ⏳ Crear schema en `infra/postgres/modules/<module>.sql`.
3. ⏳ Agregar `<module>` al CHECK constraint en `10-core.sql` →
   `app.tenant_modules.module`.
4. ⏳ Wirear `include_router` en `app/main.py`.
5. ⏳ Crear `admin-panel/src/features/<module>/` con el shell del módulo.
6. ⏳ Wirear en el router del admin-panel.
7. ⏳ Tests: pytest backend + vitest frontend. Mínimo `_health` endpoint
   debe responder 200 cuando activo, 404 cuando no.
8. ⏳ Bootstrap: `./scripts/bootstrap.sh --reset --yes --module=<module>`
   debe levantar todo desde cero.
9. ⏳ Actualizar este documento — agregar el módulo al diagrama.

## Convención de rutas

Todos los módulos exponen endpoints bajo `/v1/<module_name>/*`. **Nunca**
`/api/v1/*` — ese prefix fue un error histórico del módulo GD ya corregido.
El BFF del admin-panel (`app.admin.routes.admin_core_api_proxy`) reescribe
`/admin/api/core/v1/*` → `/v1/*` upstream, así que las rutas del backend
no necesitan el prefix `/api`.

## Estado actual de los módulos

| Módulo               | Schema SQL                         | Code             | Estado     |
| -------------------- | ---------------------------------- | ---------------- | ---------- |
| Core (chatbot base)  | `10-core.sql` (schema `app.*`)     | `app/api/v1/`    | ✅ stable  |
| Influencer / Ravit   | `modules/influencer.sql`           | `app/influencer/`| ✅ stable  |
| Gestión Documental   | `modules/gd.sql`                   | `app/gd/`        | ✅ stable  |

## Branches del repositorio (modelo de deployment)

El proyecto soporta **deployments parciales** vía branches dedicados que
"montan" un subset de módulos sobre el core. La idea: el `core` es el
**sistema operativo** sobre el cual cualquier producto se construye,
sin que ningún producto modifique al core.

| Branch              | Contiene                                                                 | Use case                                |
| ------------------- | ------------------------------------------------------------------------ | --------------------------------------- |
| `develop`           | Core + Chatbot + Influencer + GD (todos los módulos activos)             | Desarrollo full-stack                   |
| `core`              | **Solo core** (auth, tenants, platform admin, AI providers, runbooks…)   | Baseline para futuros productos         |
| `gestion-documental`| Core + GD (Chatbot/Influencer removidos)                                 | Deployment GD-only para gobierno        |
| `chatbot-only`      | (futuro) Core + Chatbot                                                  | Deployment chatbot legacy               |
| `influencer-only`   | (futuro) Core + Influencer (Ravit Studio)                                | Deployment Ravit Studio standalone      |

### Branch `core` — qué contiene

**Conserva** (sistema operativo):
- `app/core/`, `app/db/`, `app/ai/`, `app/admin/`, `app/i18n/` — transversales.
- `app/api/v1/handlers/{public, system, me, tenant_signup, tenant_user,
   tenant_catalog, tenant_ops, tenant_manager, tenant_analytics,
   platform_admin, public}_handlers.py` — endpoints transversales del core.
- `app/platform_admin/admin_routes.py` — endpoints platform_owner para
   AI providers y tenant_modules.
- `admin-panel/src/features/platform/*` — TODO el panel del platform_owner.
- `admin-panel/src/features/owner-admin/{tenant-setup, team, legal, audit}`
   — transversales del tenant.
- `admin-panel/src/features/account/` — "Mi cuenta".

**Elimina** (productos):
- `app/gd/`, `app/influencer/router*.py`, `app/chatbot/*.py` (excepto
   utils LLM).
- `admin-panel/src/features/{gd, influencer, agente, manager, viewer,
   owner-admin/{services, contacts, …}}/` — todo lo de productos.

### Cómo agregar un módulo sobre el core (Fase 2 — module discovery)

Mientras la **carga dinámica de módulos** (TODO) no esté lista, agregar
un módulo se hace así:

1. **Backend**:
   - Crear `app/<module>/` con `__init__.py` (con `MODULE_NAME`,
     `ensure_module_enabled`), `router.py` (APIRouter con prefix
     `/v1/<module>`), schemas, services, bootstrap.
   - Agregar `<module>` al CHECK constraint de `app.tenant_modules.module`
     en `infra/postgres/10-core.sql`.
   - Crear `infra/postgres/modules/<module>.sql` con schema + RLS.
   - En `app/main.py` agregar `from app.<module>.router import router as
     <module>_router; api.include_router(<module>_router)`.

2. **Frontend**:
   - Crear `admin-panel/src/features/<module>/` con shells, pages,
     services, hooks.
   - Agregar entries a `admin-panel/src/app/modules.js` y
     `admin-panel/src/app/moduleRegistry.js`.
   - Agregar la sección al `TENANT_NAV` en `admin-panel/src/app/nav.js`.
   - Si el módulo tiene su propio shell, agregar route en
     `admin-panel/src/app/router.jsx` (mismo patrón que `GdShellRoute`).

3. **Tests**: pytest backend + vitest frontend. Mínimo `_health`
   endpoint debe responder 200 cuando activo, 404 cuando no.

4. **Bootstrap**: `./scripts/bootstrap.sh --reset --yes --module=<module>`
   debe levantar todo desde cero.

### Fase 2 (futuro) — module discovery automático

El objetivo es que agregar un módulo NO requiera tocar `main.py`,
`modules.js`, `moduleRegistry.js` ni `nav.js`. Cada módulo declara su
manifesto en `app/<module>/manifest.json` y un hook al arranque escanea
`app/*/manifest.json` para auto-registrar routers + sidebar items.

Pendiente de diseñar.
