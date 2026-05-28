"""Handlers públicos del core.

Endpoints sin auth, transversales (no específicos de ningún producto).

# Health checks (v2.1.0)

Tres endpoints con semánticas distintas, alineados con la convención
k8s/AWS ALB/Cloud Run:

- **`GET /v1/livez`** — *liveness*: el proceso está vivo y respondiendo
  HTTP. NO toca DB ni Redis. Si esto falla el orchestrator REINICIA
  el container. Debe ser barato (< 1ms) para no aumentar la carga del
  servidor durante incidentes.

- **`GET /v1/readyz`** — *readiness*: el proceso está listo para
  aceptar tráfico. Hace ping a DB (siempre) y a Redis (si está
  configurado). Si esto falla el orchestrator DEJA DE MANDARLE
  tráfico — pero NO reinicia (el proceso sigue vivo, solo no puede
  cumplir requests). Devuelve 503 con detalle por dependencia para
  facilitar debugging desde dashboards.

- **`GET /v1/health`** — alias legacy de `/v1/livez` con check de DB
  embebido. Mantenido por back-compat para módulos consumidores que
  ya lo invocan. Nuevos consumers deberían usar `livez`/`readyz`
  explícitamente.

Branch `core`: estos son los únicos endpoints públicos. Los módulos
opt-in declaran los suyos cuando se instalan sobre el core.
"""
from __future__ import annotations

import os

import asyncpg
from fastapi import Depends
from fastapi.responses import JSONResponse

from copiloto_core.api.v1.routes import public_router
from copiloto_core.db.pool import get_db


@public_router.get('/livez')
async def livez() -> dict:
    """Liveness probe — el proceso está vivo.

    NO toca DB, NO toca Redis. Si esto falla, el container está
    realmente roto (deadlock, OOM cerca, asyncio loop colgado) y el
    orchestrator debe reiniciar. Costo: ~µs.
    """
    return {'status': 'ok'}


async def _check_postgres() -> dict:
    """Subcheck para readyz: 1 query trivial al pool.
    Extraído como función para mockear fácil desde tests (vs `from
    copiloto_core.db.pool import db` inline en el handler que pelea
    con sys.modules en suites grandes)."""
    try:
        from copiloto_core.db.pool import db  # noqa: PLC0415
        async with db.connection() as conn:
            await conn.fetchval('select 1')
        return {'ok': True}
    except Exception as exc:  # noqa: BLE001 — surface to clients
        return {'ok': False, 'error': str(exc)[:200]}


async def _check_redis(redis_url: str) -> dict:
    """Subcheck para readyz: PING al broker. Si redis no está
    configurado (`REDIS_URL` vacío), el caller hace skip — esta
    función asume url no vacía."""
    try:
        import redis.asyncio as redis_lib  # noqa: PLC0415
        client = redis_lib.from_url(
            redis_url, socket_connect_timeout=2, socket_timeout=2,
        )
        try:
            pong = await client.ping()
            return {'ok': bool(pong)}
        finally:
            await client.aclose()
    except Exception as exc:  # noqa: BLE001
        return {'ok': False, 'error': str(exc)[:200]}


@public_router.get('/readyz')
async def readyz() -> JSONResponse:
    """Readiness probe — la app está lista para servir tráfico.

    Verifica dependencias críticas: Postgres (siempre) + Redis (si
    `REDIS_URL` está configurado). Devuelve 200 con `{ok: true,
    checks: {...}}` cuando todas pasan, o 503 con el detalle de
    qué falló — el orchestrator deja de rutear pero NO reinicia.

    Costo: 1 query trivial a postgres + 1 PING a redis = ~5-20ms
    típico. Configurar period del probe ≥ 10s para no saturar.
    """
    checks: dict[str, dict] = {}
    overall_ok = True

    pg = await _check_postgres()
    checks['postgres'] = pg
    if not pg['ok']:
        overall_ok = False

    redis_url = os.environ.get('REDIS_URL')
    if redis_url:
        r = await _check_redis(redis_url)
        checks['redis'] = r
        if not r['ok']:
            overall_ok = False
    else:
        # Redis no configurado: el core funciona con InMemorySessionStore
        # (single-process). Reportamos `skipped` para que el operator
        # sepa que no se verificó pero no marca el probe como fallido.
        checks['redis'] = {'ok': True, 'skipped': True}

    body = {'ok': overall_ok, 'checks': checks}
    return JSONResponse(status_code=200 if overall_ok else 503, content=body)


@public_router.get('/health')
async def health(conn: asyncpg.Connection = Depends(get_db)) -> dict:
    """Liveness+DB probe (legacy alias, v1.x).

    Pre-v2.1.0 era el único probe — combinaba liveness con check de
    DB. Nuevos consumers deberían usar `/v1/livez` + `/v1/readyz`
    explícitos. Mantenido por back-compat con módulos que ya lo
    invocan o monitoring que apunta a esta URL.
    """
    await conn.fetchval('select 1')
    return {'status': 'ok'}
