"""copiloto_core — sistema operativo multi-tenant para SaaS verticales.

# Uso típico

```python
from copiloto_core import create_app

app = create_app()  # API completa con auth + RLS + observabilidad
```

Y para extender el core con un módulo propio (a partir de Fase 3 — ver
`docs/EXTENDING.md`):

```python
from copiloto_core import create_app, CoreModule
from mi_modulo.routers import router as mi_router

mi_modulo = CoreModule(
    code="mi_modulo",
    router=mi_router,
    capabilities=["mi_modulo:read", "mi_modulo:write"],
    sql_migrations=["mi_modulo/migrations/001_init.sql"],
)
app = create_app(modules=[mi_modulo])
```

# API pública

Esto es **el contrato semver** del core. Cualquier símbolo importado de
`copiloto_core` (raíz del paquete) tiene compromiso de estabilidad
dentro de la misma major version. Lo demás (`copiloto_core.services.*`,
`copiloto_core.core.*`, etc.) es **interno** — puede romperse en
minor/patch releases sin aviso.

## Categorías expuestas

| Categoría | Símbolos | Para qué |
|-----------|----------|----------|
| App factory + extensión | `create_app`, `CoreModule`, `BrandingConfig` | Bootstrap del FastAPI + contrato para módulos + marca del deployment |
| Scaffolding (v1.1.0) | `generate_project`, `GenerationResult`, `ScaffoldingError` | Bootstrappear un nuevo proyecto consumer (también vía `python -m copiloto_core new-project`) |
| Auth | `authenticate_request`, `require_platform_owner`, `require_service`, `require_mfa_for_privileged`, `require_tenant_management`, `require_min_role` | `Depends(...)` para handlers |
| Identity | `current_user_id_from_request` | sub Auth0 → UUID interno |
| DB | `get_db`, `record_to_dict` (singleton `db` se importa de `copiloto_core.db.pool`) | Pool asyncpg con RLS por TX |
| Audit | `audit` | Log de eventos de negocio |
| AI | `dispatch` | Fallback chain + circuit breaker |
| Secrets | `resolve_secret_ref`, `secret_ref_is_configured` | Lookup opaco de credenciales |
| Excepciones | `ProviderError`, `ProviderTimeoutError`, `ProviderRateLimited`, `ProviderContentRejected`, `ProviderUnavailable` | Catch-by-type en módulos consumidores |

## Política de versionado

- **MAJOR** (1.x → 2.x): breaking change en cualquier símbolo de esta
  API pública. Pre-anunciado con `DeprecationWarning` ≥ 2 minor
  releases antes.
- **MINOR** (1.0 → 1.1): añade símbolos nuevos. Símbolos existentes
  conservan firma compatible.
- **PATCH** (1.0.0 → 1.0.1): bugfixes internos. Sin cambios visibles
  en la API.

Módulos consumidores **deben pinear el rango compatible**:
```toml
dependencies = ["copiloto-core>=1.0,<2.0"]
```
"""
from __future__ import annotations

# ─── Version (sincronizado con pyproject.toml) ────────────────────────────

__version__ = '1.3.2'

# ─── App factory + modelo de extensión ──────────────────────────────────

from copiloto_core.branding import BrandingConfig
from copiloto_core.extension import CoreModule
from copiloto_core.main import create_app

# ─── Auth (Depends para handlers) ────────────────────────────────────────

from copiloto_core.auth.gating import (
    invalidate_gate_caches,
    require_capability,
    require_module,
)
from copiloto_core.core.security import (
    authenticate_request,
    require_platform_owner,
    require_service,
    require_mfa_for_privileged,
    require_tenant_management,
    require_min_role,
)

# ─── Identity (sub Auth0 → UUID interno) ─────────────────────────────────

from copiloto_core.api.v1._helpers.me_utils import current_user_id_from_request

# ─── Devices / IoT (HMAC auth para sensores, webhooks firmados) ─────────

from copiloto_core.auth.devices import (
    DeviceIdentity,
    verify_device_hmac,
)

# ─── DB (pool asyncpg con RLS por TX) ────────────────────────────────────
#
# NOTA: el singleton del pool (`db`) NO se re-exporta acá porque
# sombrearía el sub-package `copiloto_core.db`. El patrón canónico para
# módulos consumidores es:
#
#   from copiloto_core.db.pool import db
#   async with db.connection(tenant_id=...) as conn:
#       ...
#
# Acá solo exportamos los helpers que NO chocan con el sub-package.

from copiloto_core.db.pool import get_db, record_to_dict

# ─── Audit (log de eventos de negocio) ───────────────────────────────────

from copiloto_core.services.audit import audit

# ─── AI dispatch (fallback chain + circuit breaker) ──────────────────────

from copiloto_core.ai.dispatcher import dispatch

# ─── Secret resolver ─────────────────────────────────────────────────────

from copiloto_core.services.secret_resolver import (
    resolve_secret_ref,
    secret_ref_is_configured,
)

# ─── Excepciones tipadas (catch-by-type en módulos) ──────────────────────

from copiloto_core.ai.providers.base import (
    ProviderError,
    ProviderTimeoutError,
    ProviderRateLimited,
    ProviderContentRejected,
    ProviderUnavailable,
)

# ─── Migrations runner ───────────────────────────────────────────────────

from copiloto_core.migrations import (
    MigrationChecksumMismatchError,
    MigrationError,
    apply_module_migrations,
)

# ─── Platform bootstrap (v1.2.0) ─────────────────────────────────────────
#
# Aplica el schema platform del core (`app.*`) en una DB consumer.
# Necesario antes de `apply_module_migrations` en una DB fresca.
# También expuesto via CLI: `python -m copiloto_core bootstrap`.

from copiloto_core.bootstrap import (
    BootstrapError,
    apply_platform_schema,
)

# ─── Scaffolding (v1.1.0) ────────────────────────────────────────────────
#
# Permite que un consumer del core arranque un nuevo proyecto via:
#   python -m copiloto_core new-project mi-saas
# O programáticamente:
#   from copiloto_core import generate_project
#   generate_project("mi-saas", target_dir=Path("/tmp/mi-saas"))

from copiloto_core.scaffolding import (
    GenerationResult,
    ScaffoldingError,
    generate_project,
)


__all__ = [
    # version
    '__version__',
    # app factory + modelo de extensión
    'create_app',
    'CoreModule',
    'BrandingConfig',
    # auth
    'authenticate_request',
    'require_platform_owner',
    'require_service',
    'require_mfa_for_privileged',
    'require_tenant_management',
    'require_min_role',
    # gating (módulos + capabilities por tenant/actor)
    'require_module',
    'require_capability',
    'invalidate_gate_caches',
    # identity
    'current_user_id_from_request',
    # devices/IoT
    'verify_device_hmac',
    'DeviceIdentity',
    # db (db singleton se importa de copiloto_core.db.pool — ver nota arriba)
    'get_db',
    'record_to_dict',
    # audit
    'audit',
    # ai
    'dispatch',
    # secrets
    'resolve_secret_ref',
    'secret_ref_is_configured',
    # excepciones IA
    'ProviderError',
    'ProviderTimeoutError',
    'ProviderRateLimited',
    'ProviderContentRejected',
    'ProviderUnavailable',
    # migrations runner
    'apply_module_migrations',
    'MigrationError',
    'MigrationChecksumMismatchError',
    # platform bootstrap (v1.2.0)
    'apply_platform_schema',
    'BootstrapError',
    # scaffolding (v1.1.0)
    'generate_project',
    'GenerationResult',
    'ScaffoldingError',
]
