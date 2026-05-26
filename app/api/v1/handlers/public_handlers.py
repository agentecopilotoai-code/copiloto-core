"""Handlers públicos del core.

Endpoints sin auth, transversales (no específicos de ningún producto).
Branch `core`: reducido a `/v1/health`. Los módulos opt-in declaran sus
propios endpoints públicos cuando se instalan sobre el core.
"""
from __future__ import annotations

import asyncpg
from fastapi import Depends

from app.api.v1.routes import public_router
from app.db.pool import get_db


@public_router.get('/health')
async def health(conn: asyncpg.Connection = Depends(get_db)) -> dict:
    """Liveness probe — verifica que el pool de DB responda."""
    await conn.fetchval('select 1')
    return {'status': 'ok'}
