"""Static tests for TASK-0084: contact-package mutation is admin-only and
``payment_status`` is server-only (BUG02).

The bug allowed any role >= ``agent`` (the tenant_ops scope) to:
  1. assign a paid package with ``payment_status='paid'`` and
     ``payment_amount=0`` — a free paid bundle;
  2. PATCH ``payment_status='paid'`` on an existing unpaid package;
  3. DELETE/refund a package (financial side-effect).

The fix:
  - Pydantic schemas reject ``paid``, ``failed`` and ``refunded`` as
    client-writable values (they only come from the signed payment webhook
    or the admin refund endpoint).
  - All three mutation endpoints move to ``tenant_admin_router`` (admin+).
  - The list endpoint stays on ``tenant_ops_router`` so agents keep
    read access to plan their day.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.api.v1.schemas import (
    CLIENT_PACKAGE_PAYMENT_STATUS_PATTERN,
    PACKAGE_PAYMENT_STATUS_PATTERN,
    ContactPackageAssign,
    ContactPackagePatch,
)
from tests._routes_aggregator import routes_aggregated_source

# ── Schema: client-writable subset excludes financial transitions ───────────


def test_client_pattern_excludes_paid_failed_refunded():
    assert 'paid' not in CLIENT_PACKAGE_PAYMENT_STATUS_PATTERN
    assert 'failed' not in CLIENT_PACKAGE_PAYMENT_STATUS_PATTERN
    assert 'refunded' not in CLIENT_PACKAGE_PAYMENT_STATUS_PATTERN
    # Server-side pattern still accepts all six values for webhook + audit
    # write paths.
    for terminal in ('paid', 'failed', 'refunded'):
        assert terminal in PACKAGE_PAYMENT_STATUS_PATTERN


def test_contact_package_assign_rejects_paid_status():
    with pytest.raises(Exception):
        ContactPackageAssign(
            package_id='00000000-0000-0000-0000-000000000001',
            payment_status='paid',
        )


def test_contact_package_assign_rejects_refunded_status():
    with pytest.raises(Exception):
        ContactPackageAssign(
            package_id='00000000-0000-0000-0000-000000000001',
            payment_status='refunded',
        )


def test_contact_package_assign_accepts_pending_link_sent_not_required():
    for status in ('pending', 'link_sent', 'not_required'):
        payload = ContactPackageAssign(
            package_id='00000000-0000-0000-0000-000000000001',
            payment_status=status,
        )
        assert payload.payment_status == status


def test_contact_package_patch_rejects_paid_status():
    with pytest.raises(Exception):
        ContactPackagePatch(payment_status='paid')


def test_contact_package_patch_rejects_refunded_status_value():
    with pytest.raises(Exception):
        ContactPackagePatch(status='refunded')


def test_contact_package_patch_accepts_active_exhausted_expired():
    for s in ('active', 'exhausted', 'expired'):
        payload = ContactPackagePatch(status=s)
        assert payload.status == s


# ── Endpoint wiring: mutations on admin router, list stays on ops router ────


def _router_decorator_for(source: str, fn_name: str) -> str:
    fn_idx = source.index(f'async def {fn_name}(')
    # The closest ``@..._router.`` line above the function definition.
    head = source[max(0, fn_idx - 600):fn_idx]
    return head[head.rindex('@'):]


def test_assign_contact_package_uses_tenant_admin_router():
    source = routes_aggregated_source()
    decorator = _router_decorator_for(source, 'assign_contact_package')
    assert '@tenant_admin_router.post' in decorator
    assert '/contacts/{contact_id}/packages' in decorator
    assert 'tenant_ops_router' not in decorator


def test_update_contact_package_uses_tenant_admin_router():
    source = routes_aggregated_source()
    decorator = _router_decorator_for(source, 'update_contact_package')
    assert '@tenant_admin_router.patch' in decorator
    assert '/contacts/{contact_id}/packages/{contact_package_id}' in decorator
    assert 'tenant_ops_router' not in decorator


def test_refund_contact_package_uses_tenant_admin_router():
    source = routes_aggregated_source()
    decorator = _router_decorator_for(source, 'refund_contact_package')
    assert '@tenant_admin_router.delete' in decorator
    assert '/contacts/{contact_id}/packages/{contact_package_id}' in decorator
    assert 'tenant_ops_router' not in decorator


def test_list_contact_packages_stays_on_tenant_ops_router_for_agents():
    """Read access remains available to agents — only the mutations escalate."""
    source = routes_aggregated_source()
    decorator = _router_decorator_for(source, 'list_contact_packages')
    assert '@tenant_ops_router.get' in decorator


# ── Audit invariants for the refund flow ───────────────────────────────────


def test_refund_contact_package_emits_audit():
    source = routes_aggregated_source()
    start = source.index('async def refund_contact_package(')
    end = source.index('\n@', start + 1)
    block = source[start:end]
    assert "action='contact_package.refunded'" in block
    assert "status='refunded'" in block
    assert "payment_status='refunded'" in block


# ── UI hint surfaces the new RBAC contract ─────────────────────────────────


def test_contacts_module_documents_admin_only_packages_and_webhook_status():
    # UI-007.3: the contacts module was split — the packages panel now lives in
    # the conversations-contacts feature directory.
    feature_dir = Path('admin-panel/src/features/owner-admin/conversations-contacts')
    ui = '\n'.join(path.read_text() for path in sorted(feature_dir.rglob('*.js*')))
    assert 'admin' in ui.lower()
    assert 'webhook' in ui.lower()
    # The hint must mention that payment_status is server-only by listing the
    # specific webhook-owned values.
    assert 'paid' in ui
    assert 'failed' in ui
    assert 'refunded' in ui
