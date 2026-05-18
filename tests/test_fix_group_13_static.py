"""Fix-group 13: BUG-083..BUG-087.

- BUG-083: PENDING-MINOR-UX. Sidebar collapsed (4rem) overflow es un
  ajuste menor de CSS; deferido para no inflar este PR. Catalog
  documenta el estado.
- BUG-084: VIGENTE. `ReadOnlyShellRoute` usaba `ROLE_HOME.viewer`
  directo como fallback; ahora delega en `resolveSafeHomeModule(permissions)`.
- BUG-085: VIGENTE. `NoTenantRoute`, `OnboardingRoute`, `PlatformRoute`
  no chequeaban `session` → anon podía aterrizar. Fix: early-return a
  `/` si `!session`.
- BUG-086: NOT-APPLICABLE. El catalog se mantiene activo en esta
  marathon; los estados PENDING reflejan trabajo no resuelto al momento
  del mining.
- BUG-087: VIGENTE. `ShellBottomNav.flatItems.slice(0, MAX)` dropeaba
  Citas/Inbox/Contactos al overflow para roles cuyo sidebar lista esos
  items en posición >5. Fix: `pickMobilePrimary` surfacea
  `MOBILE_PRIMARY_PRIORITY` primero, luego rellena con orden literal.
"""
from __future__ import annotations

from pathlib import Path


ROUTER = Path('admin-panel/src/app/router.jsx')
BOTTOM_NAV = Path('admin-panel/src/app/shells/components/ShellBottomNav.jsx')


# ───── BUG-083 — PENDING (sidebar collapsed CSS) ────────────────────────


def test_bug_083_sidebar_collapsed_width_documented():
    """Doc-only marker. El fix de overflow del sidebar 4rem se posterga
    a una iteración futura — no bloquea uso normal (overflow afecta
    layouts edge cases en algunos viewports). Si alguien sube el ancho
    a 5rem+ o agrega overflow:visible, podemos cerrar BUG-083.
    """
    css = Path('admin-panel/src/app/shells/shell.module.css').read_text()
    assert '--shell-sidebar-width: 4rem' in css, (
        'BUG-083: el ancho colapsado sigue siendo 4rem (estado documentado). '
        'Si subís a 5rem+ o agregás overflow handling, actualizá el catalog.'
    )


# ───── BUG-084 — ReadOnlyShellRoute usa safeHome ───────────────────────


def test_bug_084_read_only_shell_route_uses_resolve_safe_home():
    src = ROUTER.read_text()
    # Buscar el bloque de ReadOnlyShellRoute.
    handler_idx = src.find('function ReadOnlyShellRoute()')
    assert handler_idx > 0, 'BUG-084: el handler debe existir.'
    block_end = src.find('\nfunction ', handler_idx + 1)
    block = src[handler_idx:block_end if block_end > 0 else handler_idx + 1500]
    assert 'resolveSafeHomeModule(permissions)' in block, (
        'BUG-084: el read-only shell debe usar `resolveSafeHomeModule(permissions)` '
        'como fallback (no `ROLE_HOME.viewer` directo) — sino el viewer puede '
        'aterrizar en una vista cuya cap no tiene.'
    )


# ───── BUG-085 — anon routes gateadas ───────────────────────────────────


def test_bug_085_no_tenant_route_redirects_anon_to_root():
    src = ROUTER.read_text()
    handler_idx = src.find('function NoTenantRoute()')
    assert handler_idx > 0
    block = src[handler_idx:handler_idx + 500]
    assert '!session' in block and "Navigate to=\"/\"" in block, (
        'BUG-085: `NoTenantRoute` debe early-return `<Navigate to="/" />` cuando '
        '`!session` para que anon no pueda ver el wizard.'
    )


def test_bug_085_onboarding_route_redirects_anon_to_root():
    src = ROUTER.read_text()
    handler_idx = src.find('function OnboardingRoute()')
    assert handler_idx > 0
    block = src[handler_idx:handler_idx + 500]
    assert '!session' in block, (
        'BUG-085: `OnboardingRoute` debe chequear `!session` antes de renderar '
        'el wizard.'
    )


def test_bug_085_platform_route_redirects_anon_to_root():
    src = ROUTER.read_text()
    handler_idx = src.find('function PlatformRoute()')
    assert handler_idx > 0
    # Tomamos un window grande porque el handler tiene un comentario JSDoc
    # extenso antes del if. Cortamos en el siguiente "function " para
    # acotar al handler concreto.
    next_fn = src.find('\nfunction ', handler_idx + 1)
    block = src[handler_idx:next_fn if next_fn > 0 else handler_idx + 2000]
    assert 'if (!session)' in block, (
        'BUG-085: `PlatformRoute` debe chequear `if (!session)` antes del role check.'
    )


# ───── BUG-086 — NOT-APPLICABLE (catalog vivo) ──────────────────────────


def test_bug_086_catalog_section_actively_maintained():
    """Doc-only marker. El catalog (`docs/UI_BACKLOG.md` sección 9) se
    está actualizando en cada fix-group de esta marathon. Si alguien
    detecta entradas obsoletas, abrir un fix-group dedicado a re-triage.
    """
    src = Path('docs/UI_BACKLOG.md').read_text()
    assert '## 9. Backlog de bugs derivados de review feedback' in src, (
        'BUG-086: la sección 9 del catalog debe existir (donde se trackea '
        'el estado de cada bug del mining).'
    )


# ───── BUG-087 — mobile primary surface ─────────────────────────────────


def test_bug_087_mobile_priority_list_includes_critical_items():
    """`MOBILE_PRIMARY_PRIORITY` debe incluir los items que el usuario
    necesita a 1 tap en mobile: Inbox, Citas, Contactos (y equivalentes
    Viewer).
    """
    src = BOTTOM_NAV.read_text()
    assert 'MOBILE_PRIMARY_PRIORITY' in src, (
        'BUG-087: la constante `MOBILE_PRIMARY_PRIORITY` debe existir como '
        'fuente de verdad de los items que surface primero en mobile rail.'
    )
    for item_id in ('operations-desk', 'appointments', 'contacts'):
        assert f"'{item_id}'" in src, (
            f'BUG-087: `MOBILE_PRIMARY_PRIORITY` debe incluir `{item_id}` '
            f'para que aparezca en el primary rail mobile (no overflow).'
        )


def test_bug_087_pick_mobile_primary_helper_exists():
    src = BOTTOM_NAV.read_text()
    assert 'function pickMobilePrimary(' in src, (
        'BUG-087: el helper `pickMobilePrimary(flatItems, count)` debe existir '
        '— surfacea priority items primero y rellena con orden literal.'
    )
    assert 'pickMobilePrimary(flatItems, primaryCount)' in src, (
        'BUG-087: el handler debe invocar `pickMobilePrimary` en vez del '
        'slice raw de `flatItems`.'
    )
