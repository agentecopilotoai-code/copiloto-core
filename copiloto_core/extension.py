"""CoreModule — el contrato que cada módulo declara para enchufarse al core.

Diseño tipo "Django app" o "Flask blueprint": el módulo no toca
`create_app()` ni el routing del core; solo declara un `CoreModule(...)`
y el extender lo pasa a `create_app(modules=[mi_modulo, ...])`.

# Ejemplo mínimo

```python
# mi_modulo/__init__.py
from fastapi import APIRouter, Depends
from copiloto_core import CoreModule, authenticate_request, require_capability
from copiloto_core.db.pool import db

router = APIRouter()

@router.get("/items")
async def list_items(
    actor = Depends(authenticate_request),
    _cap  = Depends(require_capability("mi_modulo:read")),
):
    async with db.connection() as conn:
        rows = await conn.fetch("select * from mi_modulo.items")
        return [dict(r) for r in rows]


module = CoreModule(
    code="mi_modulo",
    router=router,
    capabilities=["mi_modulo:read", "mi_modulo:write"],
    sql_migrations=["mi_modulo/migrations/001_init.sql"],
)
```

Y en el deployment:

```python
# my_saas/main.py
from copiloto_core import create_app
from mi_modulo import module as mi_modulo
app = create_app(modules=[mi_modulo])
```

# Reglas y convenciones

- **`code`** debe ser `^[a-z][a-z0-9_]{1,31}$` — usado como:
  - prefix de rutas: `/v1/<code-with-dashes>/...` (underscores → dashes)
  - schema postgres del módulo: `<code>.<tabla>`
  - key en `app.tenant_modules.module`
- **`router`** se monta en `/v1/<code>` con todos sus prefix internos.
- **`capabilities`** se seedean idempotentemente en `app.capability` al
  startup. Cada módulo debe namespacearlas como `<code>:<accion>`
  (ej. `crm:contacts:read`, no `contacts:read` a secas).
- **`sql_migrations`** son paths relativos al paquete del módulo (no
  absolutos). El runner (Fase 6) los aplica en orden y trackea version.
- **`on_tenant_activate`** se invoca cuando un platform_owner activa
  el módulo en un tenant via `/v1/platform/tenant-modules/{id}/{code}`.
  Útil para seedear catálogos por tenant (ej. roles defaults).
- **`static_mounts`** monta directorios estáticos. Caso típico: el
  módulo trae su propio SPA con marca → `{"/admin": "mi_modulo/spa/dist"}`.

# Lo que el módulo NO puede hacer (boundary del core)

1. **NO crear su propio pool asyncpg.** Debe usar `db.connection(...)`
   del core. Sino bypasses RLS multi-tenant.
2. **NO instanciar AI providers directamente.** Debe ir vía
   `dispatch(conn, modality, call_fn)`. Sino bypassa fallback chain +
   circuit breaker + audit.
3. **NO escribir en tablas `app.*`** del schema del core. El módulo
   tiene su propio schema `<code>.*`. Cross-references por FK están
   permitidas.
4. **NO modificar comportamiento del core via monkeypatch.** La API
   pública es solo lectura/composición.

Ver `docs/EXTENDING.md` para la guía completa.
"""
from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter


# `code` debe ser snake_case válido — usado como nombre de schema
# postgres + key en `app.tenant_modules.module`. Restricción: empieza
# con letra, solo lowercase + dígitos + underscore, 2-32 chars.
_CODE_RE = re.compile(r'^[a-z][a-z0-9_]{1,31}$')


# Hook firma: `async def hook(tenant_id, conn, actor_id) -> None`.
# Se llama dentro de la TX que activa `tenant_modules.enabled=true`.
TenantActivateHook = Callable[[str, Any, str | None], Awaitable[None]]


@dataclass(frozen=True)
class CoreModule:
    """Contrato declarativo de un módulo opt-in que el core monta.

    Args:
      code: identificador snake_case del módulo. Ver `_CODE_RE` para
        restricciones. Se usa como:
          - prefix de rutas (`/v1/<code-with-dashes>/...`)
          - nombre de schema postgres (`<code>.<tabla>`)
          - key en `app.tenant_modules.module`
      router: `fastapi.APIRouter` con los endpoints del módulo. El core
        lo monta en `/v1/<code-with-dashes>` con los `Depends` que ya
        traiga el router (no inyecta auth automático — el módulo decide).
      sql_migrations: paths a archivos .sql relativos al paquete Python
        del módulo. Ej: `["migrations/001_init.sql"]`. El runner los
        aplica en orden y trackea en `app.schema_migrations`. Sin cap
        de tamaño individual (el extender es responsable de mantener
        cada migration < 1MB).
      capabilities: lista de capability codes (`"<code>:<accion>"`) que
        el módulo introduce. Se seedean idempotentemente en
        `app.capability` al startup. Cada uno opcionalmente asignable
        a roles via `app.role_capability` desde la UI admin.
      on_tenant_activate: hook async invocado cuando un platform_owner
        activa el módulo para un tenant. Recibe `(tenant_id_str, conn,
        actor_id)`. Útil para seedear datos default (catálogos, roles
        del módulo). NULL = sin hook (caso por defecto). La excepción
        en el hook ABORTA la activación.
      static_mounts: directorios estáticos a montar bajo URL prefixes.
        Ej: `{"/admin": "mi_modulo/spa/dist"}` para que el módulo
        sirva su propio SPA. Los paths son relativos al paquete Python
        del módulo. El core los monta con `StaticFiles(html=True)`
        para SPA fallback.

    Raises:
      ValueError: si `code` no matchea `_CODE_RE`, o alguna capability
        no respeta el namespace `<code>:...`, o `static_mounts` tiene
        URL prefix duplicado.
    """

    code: str
    router: APIRouter
    sql_migrations: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    on_tenant_activate: TenantActivateHook | None = None
    static_mounts: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Validación del code.
        if not isinstance(self.code, str) or not _CODE_RE.match(self.code):
            raise ValueError(
                f'CoreModule.code inválido: {self.code!r}. Debe matchear '
                f'{_CODE_RE.pattern!r} (snake_case, 2-32 chars).',
            )
        # Validación del router.
        if not isinstance(self.router, APIRouter):
            raise ValueError(
                f'CoreModule.router debe ser fastapi.APIRouter, '
                f'no {type(self.router).__name__}.',
            )
        # Capabilities deben respetar el namespace `<code>:...`.
        for cap in self.capabilities:
            if not isinstance(cap, str) or ':' not in cap:
                raise ValueError(
                    f'CoreModule.capabilities[{cap!r}] inválido. '
                    f'Cada capability debe ser `<code>:<accion>`.',
                )
            ns = cap.split(':', 1)[0]
            if ns != self.code:
                raise ValueError(
                    f'CoreModule.capabilities[{cap!r}] usa namespace '
                    f'{ns!r} pero el módulo es {self.code!r}. '
                    f'Cada capability debe empezar con el code del módulo '
                    f'para evitar colisiones cross-módulo.',
                )
        # static_mounts URL prefixes deben ser únicos + empezar con `/`.
        seen_prefixes: set[str] = set()
        for url_prefix in self.static_mounts:
            if not isinstance(url_prefix, str) or not url_prefix.startswith('/'):
                raise ValueError(
                    f'CoreModule.static_mounts: URL prefix {url_prefix!r} '
                    f'debe empezar con `/`.',
                )
            if url_prefix in seen_prefixes:
                raise ValueError(
                    f'CoreModule.static_mounts: URL prefix {url_prefix!r} '
                    f'duplicado.',
                )
            seen_prefixes.add(url_prefix)

    @property
    def url_prefix(self) -> str:
        """Prefix HTTP donde el core monta el router del módulo.

        Convierte el `code` snake_case a kebab-case para URLs más
        idiomáticas (`mi_modulo` → `/v1/mi-modulo`).
        """
        return f'/v1/{self.code.replace("_", "-")}'


__all__ = ['CoreModule', 'TenantActivateHook']
