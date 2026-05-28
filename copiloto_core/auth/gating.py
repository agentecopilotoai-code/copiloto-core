"""Gating helpers — `require_module` y `require_capability`.

# `require_module(code: str)`

Verifica que el tenant del request tiene activo el módulo `code` en
`app.tenant_modules`. Si no, rechaza 403 `module_not_enabled`.

```python
from fastapi import APIRouter, Depends
from copiloto_core.auth.gating import require_module

router = APIRouter()

@router.get("/items")
async def list_items(
    _gate = Depends(require_module("mi_modulo")),
):
    ...
```

# `require_capability(cap: str)`

Verifica que el actor (usuario o service) tiene la capability
`cap` asignada vía alguno de sus roles en `app.role_capability`. Si
no, rechaza 403 `capability_required`.

```python
from copiloto_core.auth.gating import require_capability

@router.post("/items")
async def create_item(
    _cap = Depends(require_capability("mi_modulo:items:write")),
):
    ...
```

# Diseño del cache

Ambas consultas se cachean per-process con TTL 5min para no martillar
la DB en cada request. El cache es **soft** — al activar/desactivar un
módulo o cambiar role assignments via los endpoints del core, los
caches viejos se invalidan vía `invalidate_gate_caches()`. Las
invalidaciones cross-worker se propagan vía TTL natural (≤5min de
inconsistencia tolerable para gates UI).

Para tests, usar `_reset_gate_caches()` en setup/teardown.
"""
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from fastapi import Depends, HTTPException, Request, status

if TYPE_CHECKING:
    import asyncpg


# TTL del cache de gates (segundos). Trade-off: más corto = más fresh
# cross-worker pero más carga DB; más largo = lo opuesto. 5min es el
# balance estándar para gates de UI.
_GATE_CACHE_TTL_SECONDS: float = 300.0


# Cache: clave `(tenant_id_str, module_code)` → (expira_en_monotonic, enabled_bool).
_module_gate_cache: dict[tuple[str, str], tuple[float, bool]] = {}

# Cache: clave `(actor_id_str, capability_code)` → (expira_en_monotonic, granted_bool).
_capability_cache: dict[tuple[str, str], tuple[float, bool]] = {}


def invalidate_gate_caches() -> None:
    """Invalida los caches de gating. Llamar tras cualquier mutación
    de `app.tenant_modules` o `app.role_capability`.

    Es safe-no-op si los caches están vacíos. NO bloquea — la siguiente
    consulta repuebla bajo demanda.
    """
    _module_gate_cache.clear()
    _capability_cache.clear()


def _reset_gate_caches() -> None:
    """Test-only. Mismo efecto que `invalidate_gate_caches` pero con
    nombre explícito que documenta uso en setUp/tearDown."""
    invalidate_gate_caches()


# ─── require_module ──────────────────────────────────────────────────────


async def _is_module_enabled(
    conn: 'asyncpg.Connection',
    tenant_id: str,
    code: str,
) -> bool:
    """Lee `app.tenant_modules` con cache TTL. Soft — fail-closed si la
    query falla (caller decide 503/500 vs 403)."""
    key = (tenant_id, code)
    now = time.monotonic()
    cached = _module_gate_cache.get(key)
    if cached is not None and cached[0] > now:
        return cached[1]
    row = await conn.fetchrow(
        'select enabled from app.tenant_modules '
        'where tenant_id = $1 and module = $2',
        tenant_id, code,
    )
    enabled = bool(row and row['enabled'])
    _module_gate_cache[key] = (now + _GATE_CACHE_TTL_SECONDS, enabled)
    return enabled


def require_module(code: str) -> Callable[..., Awaitable[None]]:
    """Factory que devuelve un `Depends` validando que el tenant del
    request tiene el módulo `code` activo.

    Reglas de evaluación:
      1. Request DEBE tener `request.state.tenant_id` seteado (por
         `authenticate_request` upstream). Si no, 403
         `tenant_required`.
      2. Si la fila `(tenant_id, code)` no existe o `enabled=false`,
         403 `module_not_enabled`.
      3. Si la query a `app.tenant_modules` falla, 503
         `module_check_failed` (fail-closed — preferimos rechazar a
         servir sin validar).

    Args:
      code: identificador snake_case del módulo (matcheable contra
        `app.tenant_modules.module`).

    Returns:
      Función async usable como `Depends(...)` en un handler FastAPI.
    """
    if not isinstance(code, str) or not code:
        raise ValueError('require_module(code) requiere code no vacío')

    async def _gate(request: Request) -> None:
        tenant_id = getattr(request.state, 'tenant_id', None)
        if tenant_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={'error': 'tenant_required',
                        'message': 'gate require_module requiere tenant_id resuelto'},
            )
        # Late import para no contaminar el namespace + evitar import
        # circular con copiloto_core.db.pool.
        from copiloto_core.db.pool import db  # noqa: PLC0415

        try:
            async with db.connection(tenant_id=tenant_id) as conn:
                enabled = await _is_module_enabled(conn, str(tenant_id), code)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={'error': 'module_check_failed',
                        'message': f'tenant_modules query failed: {type(exc).__name__}'},
            ) from exc
        if not enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={'error': 'module_not_enabled',
                        'module': code,
                        'message': f'tenant has no active module={code!r}'},
            )

    return _gate


# ─── require_capability ──────────────────────────────────────────────────


async def _has_capability(
    conn: 'asyncpg.Connection',
    actor_id: str,
    cap: str,
) -> bool:
    """Lee join `role_capability` + `user_tenant_roles` con cache TTL.

    Una capability se considera granted si el actor tiene AL MENOS un
    rol que la tenga asignada. Reusa los roles del actor cualquiera sea
    el tenant — el `require_capability` se compone con
    `require_module` y/o filtros en el handler para narrow scope.
    """
    key = (actor_id, cap)
    now = time.monotonic()
    cached = _capability_cache.get(key)
    if cached is not None and cached[0] > now:
        return cached[1]
    # Para actores tipo `service:` no aplica RBAC por roles — el
    # `require_service` upstream ya validó el service token.
    if actor_id.startswith('service:'):
        _capability_cache[key] = (now + _GATE_CACHE_TTL_SECONDS, True)
        return True
    row = await conn.fetchrow(
        '''
        select exists (
          select 1
            from app.users u
            join app.user_tenant_roles utr on utr.user_id = u.id
            join app.role_capability rc on rc.role_code = utr.role
            join app.capability c on c.code = rc.capability_code
           where u.auth0_sub = $1 and c.code = $2
        ) as granted
        ''',
        actor_id, cap,
    )
    granted = bool(row and row['granted'])
    _capability_cache[key] = (now + _GATE_CACHE_TTL_SECONDS, granted)
    return granted


def require_capability(cap: str) -> Callable[..., Awaitable[None]]:
    """Factory que devuelve un `Depends` validando que el actor del
    request tiene la capability `cap` asignada.

    Reglas:
      1. Request DEBE tener `request.state.actor_id`. Si no, 401
         `actor_required` (auth no resuelta).
      2. Si el actor es `service:*`, pasa (el `require_service`
         upstream ya validó el service token).
      3. Si el actor no tiene rol asignado con esta cap, 403
         `capability_required`.
      4. Si la query falla, 503 `capability_check_failed` (fail-closed).

    Args:
      cap: capability code en formato `<modulo>:<accion>`. Debe coincidir
        EXACTO con `app.capability.code`.

    Returns:
      Función async usable como `Depends(...)` en un handler FastAPI.
    """
    if not isinstance(cap, str) or ':' not in cap:
        raise ValueError(
            f'require_capability(cap) requiere formato `<modulo>:<accion>` — got {cap!r}',
        )

    async def _gate(request: Request) -> None:
        actor_id = getattr(request.state, 'actor_id', None)
        if actor_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={'error': 'actor_required',
                        'message': 'require_capability requiere actor autenticado'},
            )
        # Service actors no pasan por RBAC. Short-circuit ANTES de abrir
        # conn DB — el `require_service` upstream ya validó el token.
        if str(actor_id).startswith('service:'):
            return
        from copiloto_core.db.pool import db  # noqa: PLC0415

        try:
            async with db.connection() as conn:
                granted = await _has_capability(conn, str(actor_id), cap)
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={'error': 'capability_check_failed',
                        'message': f'role_capability query failed: {type(exc).__name__}'},
            ) from exc
        if not granted:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={'error': 'capability_required',
                        'capability': cap,
                        'message': f'actor lacks required capability={cap!r}'},
            )

    return _gate


__all__ = [
    'invalidate_gate_caches',
    'require_capability',
    'require_module',
]
