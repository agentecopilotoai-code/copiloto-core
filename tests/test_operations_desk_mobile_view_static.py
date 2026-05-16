"""UI-016.8-FU: state machine `mobileView` para OperationsDesk.

La lógica de "mostrar SOLO lista o SOLO detalle" en mobile vive en CSS
(`[data-mobile-view='list']` oculta `.conversation-detail`; viceversa).
La react-side maneja el state pero NO consulta `window.matchMedia` —
delegamos al CSS para que en desktop el atributo se ignore y en mobile
se aplique. Este test estático garantiza:

1. Las reglas `data-mobile-view` viven **dentro** del `@media (max-width:
   480px)` — si quedaran fuera del media query, ocultarían el panel en
   desktop también y romperían el side-by-side.
2. El botón back está oculto por default y solo se muestra a < 480px.
3. El JSX expone `data-mobile-view` en el wrapper `.operations-layout`.
4. El hook `useInboxData` expone el state + las dos acciones
   (`selectConversation`, `showMobileList`).

Si cualquiera de estos invariantes se desalinea, la UI mobile se rompe en
forma silenciosa (los paneles vuelven a aparecer encimados o el back
button se pierde en desktop).
"""
from pathlib import Path
import re

OPS_CSS = Path('admin-panel/src/features/agente/inbox/OperationsDesk.module.css')
OPS_JSX = Path('admin-panel/src/features/agente/inbox/OperationsDesk.jsx')
CONV_JSX = Path('admin-panel/src/features/agente/inbox/components/ConversationView.jsx')
INBOX_HOOK = Path('admin-panel/src/features/agente/inbox/hooks/useInboxData.js')

EXPECTED_MOBILE_BREAKPOINT_PX = 480


# ───── CSS: data-mobile-view rules MUST live inside @media 480px ──────────


def _extract_media_block(css: str, max_width_px: int) -> str:
    """Devuelve el cuerpo del primer `@media (max-width: Npx)` con balanceo de
    llaves. Usar regex puro sobre `{...}` falla porque hay queries anidadas.
    """
    pattern = re.compile(rf'@media\s*\(\s*max-width:\s*{max_width_px}px\s*\)\s*\{{')
    match = pattern.search(css)
    assert match is not None, f'no @media (max-width: {max_width_px}px) en CSS'
    start = match.end()
    depth = 1
    i = start
    while i < len(css) and depth > 0:
        ch = css[i]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
        i += 1
    assert depth == 0, 'media query @media no cerrado correctamente'
    return css[start : i - 1]


def test_mobile_view_rules_live_inside_480px_media_query():
    css = OPS_CSS.read_text()
    block = _extract_media_block(css, EXPECTED_MOBILE_BREAKPOINT_PX)
    # Las dos reglas data-mobile-view DEBEN estar dentro del media.
    assert "[data-mobile-view='list']" in block, (
        "regla data-mobile-view='list' fuera del @media 480px — "
        'ocultaría el detalle en desktop'
    )
    assert "[data-mobile-view='detail']" in block, (
        "regla data-mobile-view='detail' fuera del @media 480px — "
        'ocultaría la lista en desktop'
    )


def test_mobile_view_rules_target_correct_panel_globals():
    css = OPS_CSS.read_text()
    block = _extract_media_block(css, EXPECTED_MOBILE_BREAKPOINT_PX)
    # `list` view → oculta `.conversation-detail`. `detail` view → oculta
    # `.conversation-list`. Si se invirtiera, la UI mobile sería el opuesto
    # exacto (lista cuando debería detalle y viceversa).
    list_rule = re.search(
        r"\[data-mobile-view='list'\][^{]*:global\(\.conversation-detail\)[^{]*\{\s*display:\s*none",
        block,
    )
    detail_rule = re.search(
        r"\[data-mobile-view='detail'\][^{]*:global\(\.conversation-list\)[^{]*\{\s*display:\s*none",
        block,
    )
    assert list_rule is not None, "regla list-view debe hacer `display: none` al detail"
    assert detail_rule is not None, "regla detail-view debe hacer `display: none` al list"


def test_back_button_hidden_by_default_visible_only_on_mobile():
    css = OPS_CSS.read_text()
    # Regla base (fuera del @media): display: none.
    base_match = re.search(
        r'\.mobileBackButton\s*\{[^}]*display:\s*none', css, flags=re.DOTALL,
    )
    assert base_match is not None, (
        '.mobileBackButton debe arrancar oculto en desktop (display: none)'
    )
    block = _extract_media_block(css, EXPECTED_MOBILE_BREAKPOINT_PX)
    # Dentro del @media: display: inline-block (o equivalente no-none).
    assert re.search(
        r'\.mobileBackButton\s*\{[^}]*display:\s*(?!none)', block, flags=re.DOTALL,
    ), '.mobileBackButton debe volverse visible dentro del @media 480px'


# ───── JSX: data-mobile-view attribute + callbacks ────────────────────────


def test_operations_desk_sets_data_mobile_view_on_layout_wrapper():
    jsx = OPS_JSX.read_text()
    # El atributo va en el div con clase `operations-layout` (legacy global),
    # consumiendo `state.mobileView` del hook. Sin este atributo el CSS
    # nunca puede decidir qué panel mostrar.
    assert 'className="operations-layout"' in jsx
    assert 'data-mobile-view={state.mobileView}' in jsx


def test_operations_desk_uses_select_conversation_action_not_raw_setter():
    jsx = OPS_JSX.read_text()
    # `selectConversation` envuelve a `setSelectedConversationId` y dispara
    # el switch a 'detail'. Si la UI usara el setter crudo, el state
    # quedaría desincronizado (selección hecha pero mobileView en 'list').
    assert 'onSelectConversation={actions.selectConversation}' in jsx
    # `setSelectedConversationId` NO debe usarse directamente desde el JSX
    # de OperationsDesk para selecciones de UI (sí se sigue exponiendo en
    # actions para tests / casos especiales).
    assert 'onSelectConversation={actions.setSelectedConversationId}' not in jsx


def test_operations_desk_wires_mobile_back_to_conversation_view():
    jsx = OPS_JSX.read_text()
    assert 'onMobileBack={actions.showMobileList}' in jsx


def test_conversation_view_renders_back_button_with_accessible_label():
    jsx = CONV_JSX.read_text()
    # Acepta la prop, la usa para gating ({onMobileBack ? ... : null}) y
    # expone aria-label para lectores de pantalla (el `←` es decorativo).
    assert 'onMobileBack' in jsx
    assert 'aria-label="Volver a la lista de conversaciones"' in jsx
    assert 'className={styles.mobileBackButton}' in jsx


# ───── Hook: state + actions ──────────────────────────────────────────────


def test_inbox_hook_exposes_mobile_view_state():
    src = INBOX_HOOK.read_text()
    # Default `list` es importante: el HTML T4 mockup muestra lista al
    # entrar, no un detalle vacío.
    assert "useState('list')" in src
    assert 'mobileView' in src
    # Expuesto en `state.mobileView` (no `actions.mobileView`).
    assert 'mobileView,\n    },\n    actions,' in src or (
        'mobileView' in src
        and re.search(r'state:\s*\{[^}]*mobileView', src, flags=re.DOTALL) is not None
    )


def test_inbox_hook_exposes_select_conversation_and_show_mobile_list_actions():
    src = INBOX_HOOK.read_text()
    # `selectConversation(id)` debe llamar a setSelectedConversationId Y
    # además poner mobileView en 'detail' (cuando id no es null).
    assert 'function selectConversation(' in src
    assert "setMobileView('detail')" in src
    # `showMobileList()` vuelve a 'list' SIN limpiar el id seleccionado
    # (el usuario puede volver al mismo detalle re-seleccionándolo).
    assert 'function showMobileList(' in src
    assert "setMobileView('list')" in src
    # Ambas expuestas en `actions`.
    assert 'selectConversation,' in src
    assert 'showMobileList,' in src


def test_start_conversation_also_switches_to_detail_view():
    """Codex P2 follow-up (PR #206): `handleStartConversation` setea
    `selectedConversationId` directamente sin pasar por `selectConversation`.
    Sin un `setMobileView('detail')` explícito en ese branch, en mobile el
    detalle recién creado quedaría oculto por el CSS `data-mobile-view='list'`
    y el usuario se quedaría mirando la lista sin ver su conversación nueva.
    """
    src = INBOX_HOOK.read_text()
    # Localizar el handler.
    handler_match = re.search(
        r'async function handleStartConversation\([^{]*\{(.*?)\n  \}',
        src,
        flags=re.DOTALL,
    )
    assert handler_match is not None, (
        'no pude localizar handleStartConversation — verificar formato del archivo'
    )
    handler_body = handler_match.group(1)
    assert "setMobileView('detail')" in handler_body, (
        "handleStartConversation debe llamar a setMobileView('detail') tras "
        "setSelectedConversationId(conversation.id), si no en mobile el "
        "detalle recién creado queda oculto por el CSS."
    )
    # Sanity: el switch ocurre en el success path (después del start exitoso),
    # no en el branch de error (donde setea notice y termina).
    assert 'setSelectedConversationId(conversation.id)' in handler_body
