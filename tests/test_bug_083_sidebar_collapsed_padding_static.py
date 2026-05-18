"""BUG-083: sidebar colapsada (4rem) deja ~32px content → header controls
overflow con `overflow: hidden`.

El padding base del sidebar es `var(--space-4)` = 16px por lado (32px
horizontal). Cuando `data-collapsed='true'` la columna mide 64px → solo
quedan 32px internos, menor que el `.brandMark` (2.5rem = 40px). El
`overflow: hidden` recortaba el branding y los íconos quedaban truncados.

Fix: aplicar `padding-left/right: var(--space-2)` (8px por lado → 48px
internos) cuando `data-collapsed='true'`.
"""
from __future__ import annotations

from pathlib import Path


SIDEBAR_CSS = Path('admin-panel/src/app/shells/components/ShellSidebar.module.css')
TOKENS_CSS = Path('admin-panel/src/styles/tokens.css')


def test_collapsed_sidebar_tightens_horizontal_padding():
    src = SIDEBAR_CSS.read_text()
    # La regla específica del collapsed debe existir.
    assert ".sidebar[data-collapsed='true'] {" in src, (
        "BUG-083: debe existir una regla `[data-collapsed='true']` que "
        "ajuste el padding del rail colapsado."
    )
    # Y debe reducir el padding horizontal a `--space-2` (8px).
    collapsed_idx = src.find(".sidebar[data-collapsed='true'] {")
    next_close = src.find('}', collapsed_idx)
    block = src[collapsed_idx:next_close]
    assert 'padding-left: var(--space-2)' in block, (
        "BUG-083: el rail colapsado debe usar `padding-left: var(--space-2)` "
        "para que el `.brandMark` (40px) no se recorte en los 64px de ancho."
    )
    assert 'padding-right: var(--space-2)' in block, (
        "BUG-083: el rail colapsado debe usar `padding-right: var(--space-2)` "
        "simétrico al `padding-left`."
    )


def test_collapsed_sidebar_inner_width_fits_brand_mark():
    """Defensa cruzada: confirma que las constantes del cálculo siguen alineadas.

    - `--space-2 = 8px` (padding horizontal del collapsed)
    - `--shell-sidebar-width: 4rem = 64px` cuando colapsado
    - `.brandMark` width = `2.5rem = 40px`

    Inner area = 64 - 2*8 = 48px > 40px ✓
    """
    tokens = TOKENS_CSS.read_text()
    assert '--space-2:' in tokens and '8px;' in tokens.split('--space-2:')[1][:20], (
        "Si `--space-2` deja de ser 8px, la math del fix cambia. Re-evaluar "
        "el cálculo `64px - 2*<padding> >= 40px (brandMark)`."
    )
    # `.brandMark` width sigue siendo 2.5rem.
    sidebar = SIDEBAR_CSS.read_text()
    bm_idx = sidebar.find('.brandMark {')
    assert bm_idx > 0
    next_close = sidebar.find('}', bm_idx)
    bm_block = sidebar[bm_idx:next_close]
    assert 'width: 2.5rem' in bm_block, (
        "Si `.brandMark.width` cambia, re-evaluar si el padding collapsed "
        "sigue cabiendo en el rail."
    )
