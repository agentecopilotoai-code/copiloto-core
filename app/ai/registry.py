"""Registry transversal de proveedores IA del core.

Resuelve qué proveedor + modelo está activo para cada modalidad
(``llm``/``image``/``video``/``tts``/``stt``). La fuente de verdad es la
tabla ``app.platform_ai_providers``; este módulo:

1. Cachea las 5 filas en memoria con TTL 5 min por worker (PROVIDER_CACHE_TTL_SECONDS)
   para que la resolución sea O(1) en el hot path.
2. Si la fila tiene ``provider='unset'`` o no existe, cae a la env var
   ``AI_DEFAULT_{MODALITY}_PROVIDER`` — útil para dev local sin tener que
   poblar la tabla.
3. NO devuelve el valor en claro del secret: solo el ``secret_ref`` opaco
   y el ``hint`` (últimos 4 chars). El adapter es responsable de resolver
   el ``secret_ref`` contra el backend correcto (env / AWS Secrets
   Manager / Vault) cuando hace la llamada real.

Política: este módulo NO acepta parámetro ``tenant_id``. La config IA
es global a la plataforma; el tenant nunca decide qué proveedor se usa.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Final

import asyncpg

logger = logging.getLogger(__name__)

# Cache TTL — alineado con el de `ensure_module_enabled` (TASK-INFLU-001).
PROVIDER_CACHE_TTL_SECONDS: Final[float] = 300.0

# Modalidades reconocidas. Sincronizado con el CHECK de
# `app.platform_ai_providers.modality` en `01-schema.sql` / `03-migrations.sql`.
MODALITIES: Final[tuple[str, ...]] = ('llm', 'image', 'video', 'tts', 'stt')


@dataclass(frozen=True)
class ResolvedProvider:
    """Snapshot de la configuración resuelta para una modalidad.

    ``secret_ref`` puede ser ``None`` si el provider local no requiere key
    (e.g. Ollama en localhost). ``model`` y ``params`` pueden estar vacíos
    si el provider tiene defaults razonables. ``source='db'`` significa
    que la fila viene de ``platform_ai_providers``; ``source='env'``
    significa fallback a env var (sin secret_ref) — útil para dev local.
    """
    modality: str
    provider: str
    secret_ref: str | None
    model: str | None
    params: dict
    source: str  # 'db' | 'env' | 'unset'


_PROVIDER_CACHE: dict[str, tuple[float, ResolvedProvider]] = {}


def _cache_invalidate() -> None:
    """Limpia el cache. Test-only / admin-only.

    Producción se basa en TTL natural; un PATCH del platform_owner se
    propaga en ≤5 min a todos los workers sin coordinación.
    """
    _PROVIDER_CACHE.clear()


def _env_fallback(modality: str) -> ResolvedProvider:
    """Resuelve la modalidad contra ``AI_DEFAULT_{MODALITY}_PROVIDER``.

    Si la env var no está seteada, devuelve un ``ResolvedProvider`` con
    ``provider='unset'`` y ``source='unset'`` — el caller debe decidir
    si lanza un error o cae a un mock (e.g. en tests).
    """
    env_key = f'AI_DEFAULT_{modality.upper()}_PROVIDER'
    provider = os.environ.get(env_key, '').strip()
    if not provider:
        return ResolvedProvider(
            modality=modality,
            provider='unset',
            secret_ref=None,
            model=None,
            params={},
            source='unset',
        )
    return ResolvedProvider(
        modality=modality,
        provider=provider,
        secret_ref=None,
        model=os.environ.get(f'AI_DEFAULT_{modality.upper()}_MODEL') or None,
        params={},
        source='env',
    )


async def resolve_provider(
    conn: asyncpg.Connection,
    modality: str,
) -> ResolvedProvider:
    """Resuelve el proveedor activo para una modalidad.

    Lookup order:
        1. Cache in-memory (TTL 5 min).
        2. SELECT en ``app.platform_ai_providers`` por ``modality``.
        3. Si la fila no existe o tiene ``provider='unset'``, fallback a
           env var ``AI_DEFAULT_{MODALITY}_PROVIDER``.
        4. Si la env var tampoco está seteada, devuelve ``provider='unset'``
           — el caller decide si lanza error.

    Args:
        conn: conexión asyncpg con permisos para leer ``platform_ai_providers``.
        modality: una de :data:`MODALITIES`.

    Returns:
        :class:`ResolvedProvider` con la configuración activa.

    Raises:
        ValueError: si ``modality`` no está en :data:`MODALITIES`.
    """
    if modality not in MODALITIES:
        raise ValueError(
            f'modality {modality!r} not in {MODALITIES}; check schema CHECK constraint',
        )

    now = time.monotonic()
    cached = _PROVIDER_CACHE.get(modality)
    if cached is not None and cached[0] > now:
        return cached[1]

    row = await conn.fetchrow(
        'select provider, secret_ref, model, params'
        ' from app.platform_ai_providers where modality = $1',
        modality,
    )
    if row is None or row['provider'] == 'unset':
        resolved = _env_fallback(modality)
    else:
        resolved = ResolvedProvider(
            modality=modality,
            provider=row['provider'],
            secret_ref=row['secret_ref'],
            model=row['model'],
            # `params` viene como dict ya parseado de asyncpg cuando la
            # columna es jsonb. Defensa por si el driver no decodifica.
            params=row['params'] if isinstance(row['params'], dict) else {},
            source='db',
        )

    _PROVIDER_CACHE[modality] = (now + PROVIDER_CACHE_TTL_SECONDS, resolved)
    return resolved


__all__ = [
    'MODALITIES',
    'PROVIDER_CACHE_TTL_SECONDS',
    'ResolvedProvider',
    '_cache_invalidate',
    'resolve_provider',
]
