"""Credit ledger helpers + pricing — TASK-INFLU-016.

`debit` y `credit` son atómicos: leen el último `balance_after` con
`for update`, calculan el nuevo, y insertan la nueva row. Una transacción
serializa los writes; el CHECK constraint `balance_after >= 0` impide
overdraft a nivel DB (defense-in-depth si el helper falla).
"""
from __future__ import annotations

import logging
from typing import Final
from uuid import UUID

import asyncpg

logger = logging.getLogger(__name__)


class InsufficientCreditsError(Exception):
    """Lanzada por `debit` cuando el balance < amount."""


async def current_balance(
    conn: asyncpg.Connection, tenant_id: UUID,
) -> int:
    """Devuelve el balance actual (último `balance_after` o 0)."""
    row = await conn.fetchrow(
        '''
        select balance_after
        from influencer.credit_ledger
        where tenant_id = $1
        order by id desc
        limit 1
        ''',
        tenant_id,
    )
    return int(row['balance_after']) if row else 0


async def debit(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    amount: int,
    reason: str,
    ref: str | None = None,
    actor_id: UUID | None = None,
) -> int:
    """Debita `amount` créditos del tenant. amount > 0.

    Lee el último balance con `FOR UPDATE` (lock la última fila del
    ledger) → calcula nuevo balance → si < 0 lanza ``InsufficientCreditsError``
    → inserta nueva fila con `delta = -amount`.

    Returns: nuevo balance_after.
    """
    if amount <= 0:
        raise ValueError('amount must be positive')

    row = await conn.fetchrow(
        '''
        select balance_after
        from influencer.credit_ledger
        where tenant_id = $1
        order by id desc
        limit 1
        for update
        ''',
        tenant_id,
    )
    prev = int(row['balance_after']) if row else 0
    new_balance = prev - amount
    if new_balance < 0:
        raise InsufficientCreditsError(
            f'tenant {tenant_id} balance {prev} < amount {amount} (reason={reason})',
        )
    await conn.execute(
        '''
        insert into influencer.credit_ledger
          (tenant_id, delta, balance_after, reason, ref, actor_id)
        values ($1, $2, $3, $4, $5, $6)
        ''',
        tenant_id, -amount, new_balance, reason, ref, actor_id,
    )
    return new_balance


async def credit(
    conn: asyncpg.Connection,
    *,
    tenant_id: UUID,
    amount: int,
    reason: str,
    ref: str | None = None,
    actor_id: UUID | None = None,
) -> int:
    """Acredita `amount` créditos al tenant (top-up o refund). amount > 0."""
    if amount <= 0:
        raise ValueError('amount must be positive')

    row = await conn.fetchrow(
        '''
        select balance_after from influencer.credit_ledger
        where tenant_id = $1 order by id desc limit 1 for update
        ''',
        tenant_id,
    )
    prev = int(row['balance_after']) if row else 0
    new_balance = prev + amount
    await conn.execute(
        '''
        insert into influencer.credit_ledger
          (tenant_id, delta, balance_after, reason, ref, actor_id)
        values ($1, $2, $3, $4, $5, $6)
        ''',
        tenant_id, amount, new_balance, reason, ref, actor_id,
    )
    return new_balance


async def pricing_map(conn: asyncpg.Connection) -> dict[str, int]:
    """Lee la tabla `generation_pricing` y devuelve `{kind: cost_credits}`."""
    rows = await conn.fetch(
        'select kind, cost_credits from influencer.generation_pricing',
    )
    return {r['kind']: int(r['cost_credits']) for r in rows}


__all__: Final = [
    'InsufficientCreditsError',
    'current_balance',
    'debit',
    'credit',
    'pricing_map',
]
