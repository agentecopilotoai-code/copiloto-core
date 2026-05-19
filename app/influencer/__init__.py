"""Módulo Influencer / Ravit Studio — TASK-INFLU-001.

Este paquete contiene el módulo *opcional* "influencer" (plataforma de
influencers de IA Ravit Studio). El módulo se activa **por tenant** vía
``app.tenant_modules`` y vive en el schema Postgres separado ``influencer.*``
para que su activación/desactivación sea quirúrgica.

Política de activación (decisión D2 del backlog):
    - Si el tenant NO tiene la fila en ``app.tenant_modules`` con
      ``module='influencer'`` y ``enabled=true``, los endpoints del módulo
      responden **404 Not Found** — NO 403 — para no filtrar la existencia
      del feature a tenants sin acceso.
    - Solo ``platform_owner`` con MFA puede activar el módulo (gateado en
      el endpoint dedicado de ``platform_admin_router``; TASK-INFLU-002).
    - Las tablas del módulo (TASK-INFLU-008+) viven todas en el schema
      ``influencer`` y heredan RLS por ``tenant_id``.

Helpers de este __init__:
    - :func:`ensure_module_enabled` — dependency FastAPI que valida la
      activación del módulo para el tenant del request, con cache en memoria
      TTL 5 min. Levanta ``HTTPException(404)`` si no está activo.
    - :data:`MODULE_NAME` — string canónico del módulo (``'influencer'``).

Ver ``docs/BACKLOG.md`` sección "Módulo Influencer" para el roadmap completo
y ``docs/UI_BACKLOG.md`` sección 10 para las tareas de UI.
"""
from __future__ import annotations

import time
from typing import Final

import asyncpg
from fastapi import Depends, HTTPException, Request, status

from app.core.security import authenticate_request
from app.db.pool import get_db

# Nombre canónico del módulo. Si en el futuro se agregan más módulos opt-in
# (e.g. ``analytics_pro``, ``whitelabel``), cada uno define su propia
# constante en su paquete y reusa el helper ``ensure_module_enabled`` con
# ese nombre. La columna ``app.tenant_modules.module`` tiene un CHECK
# constraint con la lista de módulos válidos.
MODULE_NAME: Final[str] = 'influencer'

# Cache TTL — 5 min es suficiente: la activación/desactivación es una
# operación rara (manual del platform_owner) y un staleness de 5 min en
# el peor caso es aceptable.
_CACHE_TTL_SECONDS: Final[float] = 300.0

# Cache simple en memoria. Key = (tenant_id, module); value = (expires_at,
# enabled). NO usamos ``functools.lru_cache`` porque queremos invalidación
# por TTL, no por LRU. NO es thread-safe entre workers — cada uvicorn worker
# tiene su propia copia; aceptable porque la fuente de verdad sigue siendo
# Postgres y el cache solo evita un round-trip dentro de la misma replica.
_MODULE_GATE_CACHE: dict[tuple[str, str], tuple[float, bool]] = {}


def _cache_invalidate() -> None:
    """Limpia el cache de activación. Test-only / admin-only.

    Los tests lo usan entre casos para garantizar fresh reads. En producción
    la invalidación ocurre por TTL natural; un toggle de módulo se propaga
    en ≤5 min sin necesidad de coordinación entre workers.
    """
    _MODULE_GATE_CACHE.clear()


async def _is_module_enabled(
    conn: asyncpg.Connection,
    tenant_id: str,
    module: str,
) -> bool:
    """SELECT directo a ``app.tenant_modules``.

    Usa el rol DB ``copiloto_app`` con RLS activa — el SELECT solo verá la
    fila si ``app.tenant_id`` está seteado al tenant del caller (lo que
    ``authenticate_request`` hace antes de invocar este dependency). Si el
    caller es platform_owner con ``support_mode`` activo, también ve la
    fila (policy ``tenant_modules_tenant_select``).
    """
    row = await conn.fetchrow(
        'select enabled from app.tenant_modules where tenant_id=$1 and module=$2',
        tenant_id,
        module,
    )
    if row is None:
        return False
    return bool(row['enabled'])


async def ensure_module_enabled(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
    _auth: None = Depends(authenticate_request),
) -> None:
    """Dependency FastAPI: 404 si el módulo no está habilitado para el tenant.

    Diseño:
        - Levanta 404 (no 403) cuando el módulo está desactivado o no tiene
          fila — la decisión D2 evita filtrar la existencia del feature a
          tenants sin acceso.
        - Si el caller no tiene tenant resuelto (e.g. ``platform_owner``
          actuando globalmente sin support_mode), retorna 404. Las acciones
          de plataforma sobre el módulo viven en endpoints separados que
          NO usan este gate; pasan por ``require_platform_owner`` directo.
        - Cache en memoria con TTL 5 min para no hacer SELECT en cada
          request del módulo.

    Args:
        request: Starlette request, leemos ``request.state.tenant_id``
            (poblado por ``authenticate_request``).
        conn: conexión asyncpg del pool — RLS activa ya tiene
            ``app.tenant_id`` seteado al del caller.
        _auth: solo para encadenar la dependency de auth; el resultado
            se descarta porque ya está en ``request.state``.

    Raises:
        HTTPException(404): cuando el módulo no está activo (o el caller
            no tiene tenant scope).
    """
    tenant_id = getattr(request.state, 'tenant_id', None)
    if not tenant_id:
        # Sin tenant scope no se puede activar/usar el módulo.
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
    'ensure_module_enabled',
    '_cache_invalidate',
]
