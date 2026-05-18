"""Fix-group 34: BUG-191 (P1 real) + BUG-192 (NOT-APPLICABLE).

- BUG-191 (codex P1 sobre BUG-177): el fix de BUG-177 hizo que
  `ShellTopbar` acepte `session` como prop y la forwardee a
  `TenantBrandLogo` para fetchear el proxy con auth. PERO los routes
  reales `TenantShellRoute` y `ReadOnlyShellRoute` nunca leían `session`
  de `useTenantContext` ni lo pasaban a las shells. Resultado: el
  wiring estaba dead — `TenantBrandLogo` siempre recibía `session=null`
  y caía a iniciales aunque el tenant tuviera `brand_logo_url`
  apuntando al proxy interno. Fix: extraer `session` del contexto y
  pasarlo por prop hasta el componente que lo usa.
- BUG-192 (codex P2 sobre BUG-180): NOT-APPLICABLE — el follow-up
  commit de fix-group-32 ya actualizó el test legacy de BUG-044 al
  nuevo shape `(a.starts_at at time zone t.timezone)::date`.
"""
from __future__ import annotations

from pathlib import Path


ROUTER = Path('admin-panel/src/app/router.jsx')
TENANT_SHELL = Path('admin-panel/src/app/shells/TenantShell.jsx')
READONLY_SHELL = Path('admin-panel/src/app/shells/ReadOnlyShell.jsx')
TEST_FIX_GROUP_05 = Path('tests/test_fix_group_05_static.py')


# ───── BUG-191 — session threaded a través del shell chain ───────────────


def test_bug_191_tenant_shell_route_extracts_session_from_context():
    src = ROUTER.read_text()
    fn_idx = src.find('function TenantShellRoute() {')
    assert fn_idx > 0
    next_fn = src.find('\nfunction ReadOnlyShellRoute', fn_idx)
    block = src[fn_idx:next_fn]
    # Debe extraer session del destructure de useTenantContext.
    # El patrón: `const { ..., session } = useTenantContext()`.
    assert 'session } = useTenantContext()' in block or 'session, ' in block.split('= useTenantContext()')[0], (
        'BUG-191: `TenantShellRoute` debe incluir `session` en el destructure '
        'de `useTenantContext()`.'
    )
    # Debe pasar session={session} a <TenantShell>.
    assert 'session={session}' in block, (
        'BUG-191: `<TenantShell ... session={session}>` debe estar presente.'
    )


def test_bug_191_readonly_shell_route_extracts_session_from_context():
    src = ROUTER.read_text()
    fn_idx = src.find('function ReadOnlyShellRoute() {')
    assert fn_idx > 0
    next_block = src.find('\n}\n', fn_idx)
    block = src[fn_idx:next_block + 5] if next_block > 0 else src[fn_idx:]
    assert 'session } = useTenantContext()' in block or 'session, ' in block.split('= useTenantContext()')[0], (
        'BUG-191: `ReadOnlyShellRoute` también debe incluir `session` en el '
        'destructure de `useTenantContext()`.'
    )
    assert 'session={session}' in block, (
        'BUG-191: `<ReadOnlyShell ... session={session}>` debe estar presente.'
    )


def test_bug_191_tenant_shell_accepts_and_forwards_session():
    src = TENANT_SHELL.read_text()
    # Prop session declarada en destructure.
    assert 'session,' in src, (
        'BUG-191: `TenantShell` debe aceptar `session` en su signature.'
    )
    # Forwarded al ShellTopbar.
    assert 'session={session}' in src, (
        'BUG-191: `TenantShell` debe forwardear `session` a `ShellTopbar` '
        'para que llegue a `TenantBrandLogo`.'
    )


def test_bug_191_readonly_shell_accepts_and_forwards_session():
    src = READONLY_SHELL.read_text()
    assert 'session,' in src, (
        'BUG-191: `ReadOnlyShell` debe aceptar `session` en su signature.'
    )
    assert 'session={session}' in src, (
        'BUG-191: `ReadOnlyShell` debe forwardear `session` a `ShellTopbar`.'
    )


# ───── BUG-192 — NOT-APPLICABLE (test ya flippeado en fix-group-32) ──────


def test_bug_192_fix_group_05_test_asserts_tenant_tz_filter():
    src = TEST_FIX_GROUP_05.read_text()
    # El nuevo patrón debe estar presente.
    assert '(a.starts_at at time zone t.timezone)::date >= $5::date' in src, (
        'BUG-192: `tests/test_fix_group_05_static.py` debe asertar el patrón '
        'tenant-tz aware (`(a.starts_at AT TIME ZONE t.timezone)::date`). '
        'El follow-up de fix-group-32 ya lo flippeó.'
    )
    # El patrón legacy NO debe estar como assertion activa.
    assert "assert 'a.starts_at >= $5::date'" not in src, (
        'BUG-192: la assertion legacy `a.starts_at >= $5::date` debe '
        'haberse removido.'
    )
