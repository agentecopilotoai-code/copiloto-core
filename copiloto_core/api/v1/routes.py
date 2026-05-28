"""Copiloto Core — API v1 routes (sin productos).

Define los routers transversales del core y los incluye en el router
principal `/v1`. Cada router transversal usa decoradores
`@<router>.X(...)` en su archivo handler correspondiente para registrar
endpoints (carga side-effect: importar el handler basta para registrarlo).

Routers:
  - public_router      — `/v1/health`, `/v1/ai-providers/public`, etc.
  - system_router      — `/v1/system/*` (require service token).
  - me_router          — `/v1/me/*` (perfil del usuario autenticado).
  - tenant_signup_router — `/v1/tenant-signup`.
  - tenant_user_router — `/v1/me/tenants` (listar tenants del usuario).
  - platform_admin_router — gated por platform_owner + MFA. Cubre DOS
    "namespaces" de paths a propósito (sin prefix=`/platform`):
      * `/v1/tenants/*` (fleet CRUD — un platform_owner administrando
        tenants para terceros; el panel los llama "Fleet · Tenants").
      * `/v1/platform/*` (observability + config global: runbooks,
        feature flags, incidents, billing, etc.).
    Si querés moverlo a un único prefix, hay que cambiar AMBOS lados
    coordinadamente (handler decorators + admin-panel/.../coreApi.js).

Branch `core`: solo routers transversales. Cuando se instala un módulo
opt-in sobre el core, ese módulo agrega sus propios routers vía
`include_router` desde `app/main.py`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from copiloto_core.core.security import (
    authenticate_request,
    require_mfa_for_privileged,
    require_platform_owner,
    require_service,
)


# ─── Router raíz ────────────────────────────────────────────────────────────

router = APIRouter(prefix='/v1')


# ─── Sub-routers del core ──────────────────────────────────────────────────

public_router = APIRouter(tags=['public'])

platform_admin_router = APIRouter(
    tags=['platform-admin'],
    dependencies=[
        Depends(authenticate_request),
        Depends(require_platform_owner),
        Depends(require_mfa_for_privileged),
    ],
)

tenant_signup_router = APIRouter(
    tags=['tenant-signup'],
    dependencies=[Depends(authenticate_request)],
)

# Endpoints que cualquier usuario autenticado puede llamar (perfil propio,
# listado de tenants a los que pertenece, etc.).
tenant_user_router = APIRouter(
    tags=['tenant-user'],
    dependencies=[Depends(authenticate_request)],
)

# M55 — endpoints de gestión per-tenant (members, settings, etc) que
# pueden ser ejecutados POR:
#   - platform_owner (cualquier tenant)
#   - owner/admin del tenant del path (solo su propio tenant)
# La ACL específica vive en `require_tenant_management` que cada
# handler invoca como Depends, leyendo el `tenant_id` del path.
tenant_management_router = APIRouter(
    tags=['tenant-management'],
    dependencies=[
        Depends(authenticate_request),
        # SEC-001 (audit 2026-05-27) — exigir MFA igual que `platform_admin_router`.
        # Sin esto, un platform_owner con JWT robado y mfa_verified=false podía
        # mutar miembros cross-tenant via /v1/tenants/{tid}/members/* aunque la
        # ruta fleet equivalente exigía MFA. Inconsistencia cerrada.
        Depends(require_mfa_for_privileged),
    ],
)

system_router = APIRouter(
    tags=['system'],
    dependencies=[Depends(authenticate_request), Depends(require_service)],
)

# /v1/me/* — perfil, preferencias, notificaciones, sesiones.
me_router = APIRouter(
    tags=['me'],
    dependencies=[Depends(authenticate_request)],
)


# ─── Carga side-effect de handlers ──────────────────────────────────────────
# Importar el módulo del handler ejecuta los decoradores
# @<router>.X(...) que registran endpoints. DEBE pasar ANTES del
# `include_router` que copia las rutas al router raíz.

from copiloto_core.api.v1.handlers import public_handlers as _public_handlers  # noqa: F401, E402
from copiloto_core.api.v1.handlers import me_handlers as _me_handlers  # noqa: F401, E402
from copiloto_core.api.v1.handlers import tenant_user_handlers as _tenant_user_handlers  # noqa: F401, E402
from copiloto_core.api.v1.handlers import tenant_signup_handlers as _tenant_signup_handlers  # noqa: F401, E402
from copiloto_core.api.v1.handlers import platform_admin_handlers as _platform_admin_handlers  # noqa: F401, E402
from copiloto_core.api.v1.handlers import platform_roles_handlers as _platform_roles_handlers  # noqa: F401, E402
from copiloto_core.api.v1.handlers import invitation_handlers as _invitation_handlers  # noqa: F401, E402
# Endpoints platform admin adicionales (AI providers + tenant_modules CRUD).
from copiloto_core.platform_admin import admin_routes as _platform_admin_routes  # noqa: F401, E402

# ─── Composición final ─────────────────────────────────────────────────────

router.include_router(public_router)
router.include_router(platform_admin_router)
router.include_router(tenant_management_router)
router.include_router(tenant_signup_router)
router.include_router(tenant_user_router)
# system_router declarado pero sin handlers en el core. Lo dejamos
# disponible para que productos puedan registrar endpoints servicio-a-servicio.
router.include_router(system_router)
router.include_router(me_router)
