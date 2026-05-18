from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    import asyncpg


logger = logging.getLogger(__name__)


async def audit(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID | None,
    actor_type: str,
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    metadata: dict | None = None,
) -> None:
    await conn.execute(
        """
        insert into app.audit_logs (tenant_id, actor_type, actor_id, action, entity_type, entity_id, metadata)
        values ($1, $2, $3, $4, $5, $6, $7::jsonb)
        """,
        tenant_id,
        actor_type,
        actor_id,
        action,
        entity_type,
        entity_id,
        # BUG-041: `default=str` para que UUIDs, datetimes y otros tipos
        # no-JSON-native se serialicen como strings en lugar de revientar
        # con TypeError. Antes, `go-live` auditaba metadata con `checks`
        # que incluían UUIDs y el primer go-live exitoso reventaba el
        # audit log (sin rollback porque la TX ya había commiteado el
        # update, dejando auditoría incompleta).
        json.dumps(metadata or {}, default=str),
    )


async def audit_durably(
    *,
    tenant_id: UUID | None,
    actor_type: str,
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    metadata: dict | None = None,
) -> None:
    """SEC-010 fix — audit que sobrevive a un rollback de la request.

    El helper `audit(conn, ...)` ejecuta el INSERT en la connection que la
    request inyecta vía `get_db`. Esa connection está envuelta en
    `async with conn.transaction():` (ver `app/db/pool.py:29`), por lo que
    cualquier `raise HTTPException(...)` que escape al handler dispara
    ROLLBACK y BORRA el audit log junto con el resto de la transacción.

    Para webhooks rechazados (firma inválida, secret faltante) esto rompe
    la forensia: el operador NO ve en `audit_logs` que alguien intentó
    abusar del endpoint — solo aparece el 401/503 del access log, sin
    contexto del payload ni del provider.

    `audit_durably` adquiere una connection NUEVA del pool y la usa para
    el INSERT del audit. Como no abre `conn.transaction()`, el insert se
    autocommittea inmediatamente y queda independiente de cualquier
    rollback que ocurra en la transacción de la request. La connection
    auxiliar se devuelve al pool al salir del `async with`.

    Best-effort por diseño: si la pool está caída o el INSERT falla, el
    error se loguea pero NO se propaga — un audit perdido es mucho menos
    grave que romper el handler que está intentando rechazar correctamente
    una request maliciosa.

    Usar solo para audits que DEBEN persistir tras un rollback (webhooks
    rechazados, intentos de cross-tenant access, etc.). Para audits de
    flujos exitosos (que se commitean con el resto de la request) seguir
    usando `audit(conn, ...)` — más barato (sin acquire extra) y la
    transacción de la request ya garantiza durabilidad.

    RLS context (BUG-010): la connection que acquired del pool NO viene con
    `app.tenant_id` configurado (el helper `get_db` setea el setting en
    cada checkout, pero esta connection auxiliar bypassea ese path). Sin
    el setting:
      - audits con `tenant_id IS NOT NULL` fallan `audit_logs_tenant_insert`
        (la policy exige `tenant_id = app.current_tenant_id()` o
        `app.support_mode()` — ambas son NULL/false en una conn fresca).
      - audits con `tenant_id IS NULL` SI pasan (matchean
        `audit_logs_user_scope_insert` que exige ambos NULL).
    El síntoma original era `support_mode.activated` (tenant != NULL)
    devolviendo 201 al caller pero el INSERT levantando
    `InsufficientPrivilegeError: new row violates row-level security policy`
    dentro del try/except — el audit se perdía silenciosamente,
    rompiendo el trail durable que es justo el motivo de usar este helper.

    Fix: setear `app.tenant_id` en la conn auxiliar antes del INSERT.
    Setea STRING vacío cuando `tenant_id IS NULL` para limpiar cualquier
    setting heredado de la connection si el pool reciclara la misma conn
    para audits con tenant + sin tenant en ráfaga (defensa, no comportamiento
    observado — asyncpg pool no garantiza fresh state per checkout).
    """
    # Import perezoso para evitar ciclo (app.db.pool importa este módulo
    # indirectamente vía sus consumidores).
    from app.db.pool import db  # noqa: PLC0415

    if not db.pool:
        logger.warning(
            'audit_durably skipped — db.pool not initialized (action=%s entity=%s/%s)',
            action,
            entity_type,
            entity_id,
        )
        return
    try:
        async with db.pool.acquire() as audit_conn:
            # BUG-010: setear RLS context ANTES del INSERT. Sin esto, audits
            # con tenant_id != NULL violan `audit_logs_tenant_insert` policy
            # porque `app.current_tenant_id()` retorna NULL en la conn fresca.
            await audit_conn.execute(
                "select set_config('app.tenant_id', $1, false)",
                str(tenant_id) if tenant_id is not None else '',
            )
            await audit_conn.execute(
                """
                insert into app.audit_logs (tenant_id, actor_type, actor_id, action, entity_type, entity_id, metadata)
                values ($1, $2, $3, $4, $5, $6, $7::jsonb)
                """,
                tenant_id,
                actor_type,
                actor_id,
                action,
                entity_type,
                entity_id,
                # BUG-041: `default=str` para que UUIDs, datetimes y otros tipos
        # no-JSON-native se serialicen como strings en lugar de revientar
        # con TypeError. Antes, `go-live` auditaba metadata con `checks`
        # que incluían UUIDs y el primer go-live exitoso reventaba el
        # audit log (sin rollback porque la TX ya había commiteado el
        # update, dejando auditoría incompleta).
        json.dumps(metadata or {}, default=str),
            )
    except Exception:  # noqa: BLE001 — best-effort durably-audit; no debe romper el caller
        logger.exception(
            'audit_durably failed (action=%s entity=%s/%s tenant=%s) — request continues',
            action,
            entity_type,
            entity_id,
            tenant_id,
        )
