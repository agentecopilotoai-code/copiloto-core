"""Módulo Gestión Documental (GD).

Implementa la plataforma institucional de Ventanilla Única, PQRSD, correspondencia
y gestión documental progresiva. Vive bajo el prefijo `gd_*` (schema SQL, rutas,
módulos Python) y reutiliza la identidad/auth/tenancy del producto principal
(`app.users`, `app.tenants`, Auth0, RLS, `app.current_tenant_id()`).

Documentación funcional: docs/gestion documental/{BACKLOG.md, UI_BACKLOG.md,
integracion/, PROGRESO_IMPLEMENTACION.md}.

Schema SQL: infra/postgres/04-gd-schema.sql (y futuros 05-gd-seed.sql, etc.).
"""
from __future__ import annotations

import time
from typing import Final

import asyncpg
from fastapi import Depends, HTTPException, Request, status

from app.core.security import authenticate_request
from app.db.pool import get_db


# Nombre canónico del módulo en `app.tenant_modules.module`. Mirror del
# patrón usado por `app/influencer/__init__.py`: cada módulo opt-in
# tiene su propio gate `ensure_*_module_enabled` que retorna 404 cuando
# el tenant no contrató/activó el módulo.
MODULE_NAME: Final[str] = 'gestion_documental'

# Cache TTL — 5 min (mismo que influencer). Activación/desactivación es
# operación rara (manual del platform_owner) y staleness aceptable.
_CACHE_TTL_SECONDS: Final[float] = 300.0

# Cache simple en memoria. Key = (tenant_id, module); value = (expires_at, enabled).
_MODULE_GATE_CACHE: dict[tuple[str, str], tuple[float, bool]] = {}


def _cache_invalidate() -> None:
    """Limpia el cache de activación. Test-only / admin-only."""
    _MODULE_GATE_CACHE.clear()


async def _is_module_enabled(
    conn: asyncpg.Connection,
    tenant_id: str,
    module: str,
) -> bool:
    """SELECT a `app.tenant_modules` respetando RLS (rol `copiloto_app`)."""
    row = await conn.fetchrow(
        'select enabled from app.tenant_modules where tenant_id=$1 and module=$2',
        tenant_id,
        module,
    )
    if row is None:
        return False
    return bool(row['enabled'])


async def ensure_gd_module_enabled(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    _auth: None = Depends(authenticate_request),
) -> None:
    """Dependency FastAPI: 404 si Gestión Documental no está activa para el tenant.

    Diseño espejo del gate de influencer (D2): 404 (no 403) para no filtrar
    la existencia del feature a tenants sin acceso. Cache 5 min.

    Raises:
        HTTPException(404): cuando el módulo no está activo o el caller
            no tiene tenant scope.
    """
    tenant_id = getattr(request.state, 'tenant_id', None)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Not Found',
        )

    cache_key = (str(tenant_id), MODULE_NAME)
    now = time.monotonic()
    cached = _MODULE_GATE_CACHE.get(cache_key)
    if cached is not None and cached[0] > now:
        if cached[1]:
            return
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Not Found',
        )

    enabled = await _is_module_enabled(conn, str(tenant_id), MODULE_NAME)
    _MODULE_GATE_CACHE[cache_key] = (now + _CACHE_TTL_SECONDS, enabled)
    if not enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Not Found',
        )


__all__ = [
    'MODULE_NAME',
    'ensure_gd_module_enabled',
    '_cache_invalidate',
]
