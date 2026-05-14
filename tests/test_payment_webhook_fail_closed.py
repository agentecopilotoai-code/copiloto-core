"""Static tests for TASK-0083: payment webhook fail-closed with audit.

Covers BUG04: ``POST /v1/webhooks/payments/{provider}`` used to default
``signature_ok = True`` when the tenant had no secret configured, so a forged
event with a known appointment UUID could flip ``payment_status='paid'``. The
fix in this branch:

  1. Server rejects missing-secret with HTTP 503 + audit ``payment.webhook_rejected``
     reason=missing_secret.
  2. Server rejects bad-signature with HTTP 401 + audit ``payment.webhook_rejected``
     reason=bad_signature.
  3. Same gates apply to the subscription webhook (``contact_subscriptions``).
  4. Admin endpoint refuses to enable a non-``none`` provider without a
     ``webhook_secret`` (HTTP 422).
"""
from __future__ import annotations

import re
from pathlib import Path

ROUTES = Path('app/api/v1/routes.py')
TENANT_SETUP_FEATURE = Path('admin-panel/src/features/owner-admin/tenant-setup')

def _tenant_setup_source() -> str:
    return '\n'.join(p.read_text() for p in sorted(TENANT_SETUP_FEATURE.rglob('*.js*')))

def _payments_webhook_block() -> str:
    source = ROUTES.read_text()
    # The appointment-payments webhook lives above the subscription one; the
    # block we care about ends at the first ``return`` after the update of
    # ``app.appointments``.
    start = source.index('extract_external_ref(normalized_provider, payload)')
    # Look forward for the second occurrence of ``payment_settings = await``
    # so we capture only the appointments-payments handler.
    next_block = source.index('subscription = await conn.fetchrow', start)
    return source[start:next_block]


def _subscription_webhook_block() -> str:
    source = ROUTES.read_text()
    start = source.index('subscription = await conn.fetchrow')
    end = source.index('@', start + 1)
    return source[start:end]


# ── Server fail-closed: missing secret → 503 + audit ─────────────────────────


def test_payments_webhook_returns_503_when_secret_missing():
    block = _payments_webhook_block()
    assert "if not secret:" in block
    # Match the 503 raise after the missing-secret branch.
    missing_idx = block.index("if not secret:")
    branch = block[missing_idx:missing_idx + 1500]
    assert 'status_code=503' in branch
    assert "'payment.webhook_unconfigured'" in branch
    # Older 401 status MUST be gone from this branch.
    assert 'status_code=401' not in branch[:branch.index('raise HTTPException(')]


def test_payments_webhook_audits_missing_secret_rejection():
    block = _payments_webhook_block()
    missing_idx = block.index("if not secret:")
    branch = block[missing_idx:missing_idx + 2000]
    assert "action='payment.webhook_rejected'" in branch
    assert "'reason': 'missing_secret'" in branch


# ── Server fail-closed: bad signature → 401 + audit ─────────────────────────


def test_payments_webhook_returns_401_when_signature_invalid():
    block = _payments_webhook_block()
    assert 'if not signature_ok:' in block
    sig_idx = block.index('if not signature_ok:')
    branch = block[sig_idx:sig_idx + 1500]
    assert 'status_code=401' in branch
    assert 'Invalid payment webhook signature' in branch


def test_payments_webhook_audits_bad_signature_rejection():
    block = _payments_webhook_block()
    sig_idx = block.index('if not signature_ok:')
    branch = block[sig_idx:sig_idx + 1500]
    assert "action='payment.webhook_rejected'" in branch
    assert "'reason': 'bad_signature'" in branch


def test_payments_webhook_does_not_mark_paid_when_secret_missing():
    """Regression: the missing-secret rejection must short-circuit BEFORE the
    update on app.appointments runs."""
    block = _payments_webhook_block()
    missing_idx = block.index("if not secret:")
    update_idx = block.index('update app.appointments')
    assert missing_idx < update_idx


# ── Subscription webhook gets the same treatment ────────────────────────────


def test_subscription_webhook_returns_503_when_secret_missing():
    block = _subscription_webhook_block()
    assert "if not secret:" in block
    missing_idx = block.index("if not secret:")
    branch = block[missing_idx:missing_idx + 1500]
    assert 'status_code=503' in branch
    assert "'payment.webhook_unconfigured'" in branch


def test_subscription_webhook_audits_both_rejection_reasons():
    block = _subscription_webhook_block()
    missing_idx = block.index("if not secret:")
    sig_idx = block.index('if not signature_ok:')
    branch_missing = block[missing_idx:missing_idx + 2000]
    branch_sig = block[sig_idx:sig_idx + 2000]
    assert "'reason': 'missing_secret'" in branch_missing
    assert "'flow': 'subscription'" in branch_missing
    assert "'reason': 'bad_signature'" in branch_sig
    assert "'flow': 'subscription'" in branch_sig


# ── Admin endpoint refuses to enable provider without secret (already in HEAD)


def test_admin_payments_settings_refuses_provider_without_secret():
    source = ROUTES.read_text()
    start = source.index('async def update_tenant_payment_settings(')
    end = source.index('\n@', start + 1)
    block = source[start:end]
    # The original guard remains untouched; this test pins it as a regression.
    pattern = re.compile(
        r"if payload\.provider != 'none' and not next_settings\.get\('webhook_secret_ref'\):",
    )
    assert pattern.search(block) is not None
    assert 'status_code=422' in block
    assert 'Webhook signing secret is required' in block


# ── UI hint surfaces the new 503/audit contract ─────────────────────────────


def test_wizard_payments_hint_mentions_503_and_audit():
    source = _tenant_setup_source()
    assert '503 payment.webhook_unconfigured' in source.replace('<code>', '').replace('</code>', '')
    assert 'payment.webhook_rejected' in source
