"""Static tests para credits + pricing — TASK-INFLU-016."""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from app.influencer.credits_router import credits_router, pricing_router
from app.influencer import credits as credits_module
from app.influencer.credits import (
    InsufficientCreditsError,
    credit,
    debit,
    pricing_map,
)


SCHEMA = Path('infra/postgres/03-migrations.sql').read_text(encoding='utf-8')


def test_credit_ledger_table_with_balance_check():
    assert 'create table if not exists influencer.credit_ledger' in SCHEMA
    assert 'check (delta <> 0)' in SCHEMA
    assert 'check (balance_after >= 0)' in SCHEMA  # no overdraft


def test_credit_ledger_indices():
    assert 'ix_credit_ledger_tenant_created' in SCHEMA
    assert 'ix_credit_ledger_tenant_id_id' in SCHEMA


def test_credit_ledger_rls():
    assert 'credit_ledger_tenant_isolation' in SCHEMA


def test_generation_pricing_seeded_with_7_kinds():
    assert 'create table if not exists influencer.generation_pricing' in SCHEMA
    for kind in ('photo', 'reel', 'carousel', 'story', 'ad', 'face_variation', 'voice_sample'):
        assert f"('{kind}'," in SCHEMA


def test_generation_pricing_check_positive():
    """cost_credits > 0 — no se permite gratis (eso confunde el debit)."""
    assert 'check (cost_credits > 0)' in SCHEMA


def test_debit_signature():
    sig = inspect.signature(debit)
    assert 'amount' in sig.parameters
    assert 'reason' in sig.parameters


def test_credit_signature():
    sig = inspect.signature(credit)
    assert 'amount' in sig.parameters
    assert 'reason' in sig.parameters


def test_debit_uses_for_update():
    src = inspect.getsource(credits_module)
    assert 'for update' in src.lower()


def test_insufficient_credits_error_exists():
    assert issubclass(InsufficientCreditsError, Exception)


def test_endpoints_registered():
    paths = {(r.path, tuple(sorted(r.methods))) for r in credits_router.routes}
    assert any(p[0] == '/v1/influencer/credits/balance' and 'GET' in p[1] for p in paths)
    assert any(p[0] == '/v1/influencer/credits/topup' and 'POST' in p[1] for p in paths)

    paths2 = {(r.path, tuple(sorted(r.methods))) for r in pricing_router.routes}
    assert any(p[0] == '/v1/influencer/pricing' and 'GET' in p[1] for p in paths2)


def test_topup_requires_mfa():
    src = Path('app/influencer/credits_router.py').read_text(encoding='utf-8')
    topup_idx = src.find('async def topup')
    assert topup_idx > 0
    # require_mfa_for_privileged debe estar entre el decorador y la función.
    decorator_start = src.rfind('@credits_router.post', 0, topup_idx)
    assert 'require_mfa_for_privileged' in src[decorator_start:topup_idx]


def test_topup_validates_payment_ref_required():
    """payment_ref es required + min_length=1 — sin ref no se acreditan créditos."""
    src = Path('app/influencer/credits_router.py').read_text(encoding='utf-8')
    assert 'payment_ref' in src
    assert 'min_length=1' in src


def test_routers_mounted_in_main():
    src = Path('app/main.py').read_text(encoding='utf-8')
    assert 'influencer_credits_router' in src
    assert 'influencer_pricing_router' in src


@pytest.mark.parametrize('amount', [0, -1, -100])
def test_debit_rejects_non_positive_amount(amount):
    import asyncio
    from unittest.mock import AsyncMock
    conn = AsyncMock()
    with pytest.raises(ValueError):
        asyncio.run(debit(conn, tenant_id=__import__('uuid').uuid4(), amount=amount, reason='x'))


def test_pricing_map_helper_exists():
    """pricing_map(conn) → dict[kind, cost_credits] — usado por el dispatcher."""
    assert callable(pricing_map)
    sig = inspect.signature(pricing_map)
    assert 'conn' in sig.parameters
