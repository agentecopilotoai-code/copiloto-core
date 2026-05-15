"""BUG-004: el breakpoint mobile que controla cuándo se oculta el sidebar
y se muestra ShellBottomNav vive en TRES archivos CSS distintos. Si quedan
desalineados, el sidebar puede esconderse sin el reemplazo (o viceversa),
dejando al usuario sin nav primaria. Este test asegura que los tres usan
el mismo valor.
"""
from pathlib import Path
import re

SHELL = Path('admin-panel/src/app/shells/shell.module.css')
SIDEBAR = Path('admin-panel/src/app/shells/components/ShellSidebar.module.css')
BOTTOM_NAV = Path('admin-panel/src/app/shells/components/ShellBottomNav.module.css')

# BUG-004 history:
#   480px (UI-016.8): solo phones portrait estricto.
#   768px (BUG-004 v1): bumped, pero codex P2 notó que phones modernos
#       en landscape llegan a 932px (iPhone Pro Max), 915px (Pixel 7)
#       y seguían sin tabs.
#   1024px (BUG-004 v2): cubre TODOS los phones (cualquier orientación)
#       + tablets en portrait. ≥ 1024px = sidebar desktop.
EXPECTED_BREAKPOINT_PX = 1024


def _max_width_pxs(text: str) -> list[int]:
    return [int(m.group(1)) for m in re.finditer(r'@media \(max-width:\s*(\d+)px\)', text)]


def test_shell_module_uses_expected_mobile_breakpoint():
    # `shell.module.css` puede tener varias media queries (e.g. para topbar).
    # La que define `grid-template-columns: 1fr` (la del swap de layout) debe
    # apuntar al breakpoint global mobile.
    src = SHELL.read_text()
    # Buscar la query inmediatamente antes del bloque `.shell { grid-template-columns: 1fr; }`.
    match = re.search(
        r'@media \(max-width:\s*(\d+)px\)\s*\{\s*\.shell\s*\{\s*grid-template-columns:\s*1fr',
        src,
    )
    assert match is not None, 'No encontré la media query que colapsa el grid del shell'
    assert int(match.group(1)) == EXPECTED_BREAKPOINT_PX, (
        f'shell.module.css usa breakpoint {match.group(1)}px; '
        f'esperado {EXPECTED_BREAKPOINT_PX}px'
    )


def test_sidebar_hide_breakpoint_matches_shell():
    src = SIDEBAR.read_text()
    # La regla que oculta el sidebar vive en una única media query mobile.
    match = re.search(
        r'@media \(max-width:\s*(\d+)px\)\s*\{[^}]*\.sidebar\s*\{\s*display:\s*none',
        src,
        flags=re.DOTALL,
    )
    assert match is not None, 'No encontré la regla que oculta el sidebar en mobile'
    assert int(match.group(1)) == EXPECTED_BREAKPOINT_PX, (
        f'ShellSidebar.module.css esconde el sidebar a {match.group(1)}px '
        f'(esperado {EXPECTED_BREAKPOINT_PX}px — sincronizar con shell.module.css)'
    )


def test_bottom_nav_activation_breakpoint_matches_shell():
    src = BOTTOM_NAV.read_text()
    # La activación del bottom-nav vive en una media query con `.bottomNav { display: block }`.
    match = re.search(
        r'@media \(max-width:\s*(\d+)px\)\s*\{[^}]*\.bottomNav\s*\{\s*display:\s*block',
        src,
        flags=re.DOTALL,
    )
    assert match is not None, 'No encontré la regla que activa el bottom-nav en mobile'
    assert int(match.group(1)) == EXPECTED_BREAKPOINT_PX, (
        f'ShellBottomNav.module.css activa la nav a {match.group(1)}px '
        f'(esperado {EXPECTED_BREAKPOINT_PX}px — sincronizar con shell.module.css)'
    )


def test_three_shell_files_use_identical_breakpoint():
    """Cualquier desalineamiento entre los 3 archivos crea un viewport gap
    donde el sidebar se esconde pero el bottom-nav no aparece (o viceversa).
    Este test es la defensa frontal contra esa regresión."""
    shell_widths = _max_width_pxs(SHELL.read_text())
    sidebar_widths = _max_width_pxs(SIDEBAR.read_text())
    bottom_widths = _max_width_pxs(BOTTOM_NAV.read_text())
    # El breakpoint del swap debe aparecer en los tres archivos (al menos una
    # vez cada uno — pueden existir otras media queries para ajustes finos).
    assert EXPECTED_BREAKPOINT_PX in shell_widths
    assert EXPECTED_BREAKPOINT_PX in sidebar_widths
    assert EXPECTED_BREAKPOINT_PX in bottom_widths
