from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import Request


class Database:
    def __init__(self) -> None:
        self.pool: asyncpg.Pool | None = None

    async def connect(self, dsn: str) -> None:
        # AUDIT-46 (speed quick win #1, 2026-05-18): pool config viene de
        # settings (defaults conservadores idénticos a los hardcoded previos).
        # Permite tunear por entorno sin tocar código. Fail-safe: si
        # `get_settings()` falla (test env minimal sin envvars), caemos a
        # los defaults históricos 1/10/30.
        try:
            from copiloto_core.core.config import get_settings  # noqa: PLC0415

            settings = get_settings()
            min_size = settings.db_pool_min_size
            max_size = settings.db_pool_max_size
            command_timeout = settings.db_pool_command_timeout_seconds
        except Exception:  # noqa: BLE001
            min_size, max_size, command_timeout = 1, 10, 30.0
        self.pool = await asyncpg.create_pool(
            dsn,
            min_size=min_size,
            max_size=max_size,
            command_timeout=command_timeout,
        )

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()
            self.pool = None

    @asynccontextmanager
    async def connection(
        self, tenant_id: UUID | None = None, support_mode: bool = False,
        user_id: UUID | None = None,
    ) -> AsyncIterator[asyncpg.Connection]:
        if not self.pool:
            raise RuntimeError('Database pool is not initialized')
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                if tenant_id:
                    await conn.execute("select set_config('app.tenant_id', $1, true)", str(tenant_id))
                await conn.execute(
                    "select set_config('app.support_mode', $1, true)",
                    'true' if support_mode else 'false',
                )
                # P1-1 (audit 2026-05-27) — `app.user_id` lo lee
                # `app.current_user_id()` desde las RLS policies de
                # user_preferences/auth_sessions. Si no se setea, queda
                # vacío → policy permissive (compat con queries legacy).
                if user_id:
                    await conn.execute(
                        "select set_config('app.user_id', $1, true)", str(user_id),
                    )
                yield conn


db = Database()


async def get_db(request: Request) -> AsyncIterator[asyncpg.Connection]:
    tenant_id = getattr(request.state, 'tenant_id', None)
    support_mode = getattr(request.state, 'support_mode', False)
    # P1-1 — `user_id` se cache en request.state DESPUÉS de la primera
    # llamada a `current_user_id_from_request`. Acá leemos lo que esté
    # disponible (probablemente None en la primera query, no None en
    # subsiguientes si el handler ya lo resolvió en la misma request).
    # Para RLS enforcement REAL, el handler debe llamar el helper ANTES
    # de las queries protegidas.
    user_id = getattr(request.state, 'user_id', None)
    async with db.connection(
        tenant_id=tenant_id, support_mode=support_mode, user_id=user_id,
    ) as conn:
        yield conn


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {key: _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_json_safe_value(item) for item in value)
    return value


def record_to_dict(record: asyncpg.Record | None) -> dict[str, Any] | None:
    if not record:
        return None
    return {key: _json_safe_value(value) for key, value in dict(record).items()}
