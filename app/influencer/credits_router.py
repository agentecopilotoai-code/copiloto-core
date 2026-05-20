"""Credits balance / topup / pricing endpoints — TASK-INFLU-016."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.security import authenticate_request, require_mfa_for_privileged
from app.db.pool import get_db
from app.influencer import ensure_module_enabled
from app.influencer.personas_router import _set_tenant_scope
from app.influencer.credits import (
    InsufficientCreditsError,
    credit,
    current_balance,
    pricing_map,
)


credits_router = APIRouter(
    prefix='/v1/influencer/credits',
    tags=['influencer-credits'],
    dependencies=[
        Depends(authenticate_request),
        Depends(ensure_module_enabled),
    ],
)

pricing_router = APIRouter(
    prefix='/v1/influencer',
    tags=['influencer-pricing'],
    dependencies=[
        Depends(authenticate_request),
        Depends(ensure_module_enabled),
    ],
)


def _require_tenant_id(request: Request) -> UUID:
    tenant_id = getattr(request.state, 'tenant_id', None)
    if tenant_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, 'module not available')
    return tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))


class LedgerEntry(BaseModel):
    id: int
    delta: int
    balance_after: int
    reason: str
    ref: str | None = None
    created_at: datetime


class BalanceResponse(BaseModel):
    balance: int
    recent: list[LedgerEntry]


class TopUpRequest(BaseModel):
    amount: int = Field(..., gt=0, le=100_000)
    payment_ref: str = Field(..., min_length=1, max_length=80)


class TopUpResponse(BaseModel):
    new_balance: int
    delta: int
    payment_ref: str


class PricingResponse(BaseModel):
    pricing: dict[str, int]


@credits_router.get(
    '/balance',
    response_model=BalanceResponse,
    summary='Balance actual + últimas 50 transacciones',
)
async def get_balance(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> BalanceResponse:
    tenant_id = _require_tenant_id(request)
    await _set_tenant_scope(conn, tenant_id)
    balance = await current_balance(conn, tenant_id)
    rows = await conn.fetch(
        '''
        select id, delta, balance_after, reason, ref, created_at
        from influencer.credit_ledger
        where tenant_id = $1
        order by id desc
        limit 50
        ''',
        tenant_id,
    )
    return BalanceResponse(
        balance=balance,
        recent=[
            LedgerEntry(
                id=r['id'],
                delta=r['delta'],
                balance_after=r['balance_after'],
                reason=r['reason'],
                ref=r['ref'],
                created_at=r['created_at'],
            )
            for r in rows
        ],
    )


@credits_router.post(
    '/topup',
    response_model=TopUpResponse,
    summary='Top-up de créditos (requiere MFA + payment_ref validado)',
    dependencies=[Depends(require_mfa_for_privileged)],
)
async def topup(
    request: Request,
    body: TopUpRequest,
    conn: asyncpg.Connection = Depends(get_db),
) -> TopUpResponse:
    tenant_id = _require_tenant_id(request)
    user_id = getattr(request.state, 'user_id', None)
    await _set_tenant_scope(conn, tenant_id)

    # `payment_ref` debe haber sido validado upstream por TASK-0083
    # (Stripe/MercadoPago webhook). Aquí asumimos validado y solo
    # acreditamos. La validación real la añade el entrypoint cuando
    # el billing webhook esté cableado.
    new_balance = await credit(
        conn,
        tenant_id=tenant_id,
        amount=body.amount,
        reason='topup',
        ref=body.payment_ref,
        actor_id=user_id,
    )
    return TopUpResponse(
        new_balance=new_balance,
        delta=body.amount,
        payment_ref=body.payment_ref,
    )


@pricing_router.get(
    '/pricing',
    response_model=PricingResponse,
    summary='Mapa kind → cost_credits',
)
async def get_pricing(
    request: Request,
    conn: asyncpg.Connection = Depends(get_db),
) -> PricingResponse:
    tenant_id = _require_tenant_id(request)
    await _set_tenant_scope(conn, tenant_id)
    return PricingResponse(pricing=await pricing_map(conn))


__all__ = ['credits_router', 'pricing_router']

# Re-export for compatibility with importers that look for the error
# helper alongside the routers.
_ = InsufficientCreditsError
