"""Fix-group 10: BUG-068..BUG-072.

- BUG-068: `assign_auth0_role_by_name` puede devolver
  `{'error': 'auth0_role_not_found:...'}` como VALOR (no raise). Antes el
  caller solo capturaba httpx.HTTPError y el error se tragaba en silencio
  → invite reportaba `invited:True` pero el usuario no tenía rol.
- BUG-069: `safe_auth0` no copiaba `propagation_errors` de
  `auth0_result`. La UI no podía mostrar warnings de role assignment
  fallido.
- BUG-070: NOT-APPLICABLE. El handler DELETE support-mode ya devuelve
  `response` mutado (con Set-Cookie del delete_cookie). Fix codex P2
  línea 11555-11556.
- BUG-071: NOT-APPLICABLE. INSTALL.md línea 235 ya dice `create:user_tickets`
  (no `read:tickets`).
- BUG-072: la sección troubleshooting de INSTALL.md (línea 1068) seguía
  pidiendo `read:tickets`, contradiciendo la sección principal. Fix:
  apuntar a `create:user_tickets`.
"""
from __future__ import annotations

import inspect
import textwrap
from pathlib import Path

from app.services import auth0_admin


INSTALL_MD = Path('INSTALL.md')
ROUTES = Path('app/api/v1/routes.py')


# ───── BUG-068 — auth0_role_not_found agregado a propagation_errors ─────


def test_bug_068_invite_user_checks_role_assignment_error_value():
    """El `try/except` debe tener un `else:` que chequea
    `role_result.get('error')` para agregar al `propagation_errors`.
    """
    src = textwrap.dedent(inspect.getsource(auth0_admin.invite_user))
    assert 'role_result = await assign_auth0_role_by_name' in src, (
        'BUG-068: `invite_user` debe capturar el return de '
        '`assign_auth0_role_by_name` en `role_result` para chequear errors '
        'devueltos como valor.'
    )
    assert "role_result.get('error')" in src, (
        "BUG-068: el caller debe chequear `role_result.get('error')` "
        "(que es el caso `auth0_role_not_found`) y agregar al "
        "`propagation_errors`."
    )
    assert 'auth0_admin.invite_user_role_assign_unresolved' in src, (
        'BUG-068: debe loguear `invite_user_role_assign_unresolved` cuando '
        'el role lookup falla.'
    )


# ───── BUG-069 — propagation_errors en safe_auth0 ───────────────────────


def test_bug_069_safe_auth0_includes_propagation_errors():
    src = ROUTES.read_text()
    assert "if auth0_result.get('propagation_errors'):" in src, (
        'BUG-069: `safe_auth0` debe incluir `propagation_errors` cuando '
        '`auth0_result` los reporta — sin esto, la UI no muestra warnings.'
    )
    assert "safe_auth0['propagation_errors'] = list(auth0_result['propagation_errors'])" in src, (
        'BUG-069: copiar la lista (no la referencia) para no mutar el '
        'dict original si el caller la modifica.'
    )


# ───── BUG-070 — NOT-APPLICABLE (cookie deletion ya correcto) ───────────


def test_bug_070_deactivate_support_mode_returns_injected_response():
    """El handler DELETE debe MUTAR el `response` inyectado por FastAPI,
    NO retornar un nuevo Response (que descarta el Set-Cookie).
    """
    src = ROUTES.read_text()
    # Buscar el bloque de deactivate_support_mode
    handler_idx = src.find('async def deactivate_support_mode(')
    assert handler_idx > 0, 'BUG-070: handler debe existir.'
    block_end = src.find('\n\n\n', handler_idx)
    block = src[handler_idx:block_end if block_end > 0 else handler_idx + 1500]
    assert 'response.status_code = status.HTTP_204_NO_CONTENT' in block, (
        'BUG-070: el handler debe mutar `response.status_code`, no devolver '
        'un Response nuevo.'
    )
    assert 'return response' in block, (
        'BUG-070: debe `return response` (el response inyectado con el '
        'Set-Cookie del `delete_cookie`), no `return Response(...)`.'
    )


# ───── BUG-071 — NOT-APPLICABLE (docs principales correctas) ────────────


def test_bug_071_install_md_says_create_user_tickets_in_main_section():
    src = INSTALL_MD.read_text()
    # La sección principal del Paso 2 debe decir create:user_tickets.
    main_section_idx = src.find('Contra `AUTH0_API_IDENTIFIER`')
    assert main_section_idx > 0, 'BUG-071: sección principal debe existir.'
    main_block = src[main_section_idx:main_section_idx + 1500]
    assert 'create:user_tickets' in main_block, (
        'BUG-071: la sección principal del Paso 2 debe pedir '
        '`create:user_tickets`, no `read:tickets`.'
    )


# ───── BUG-072 — INSTALL.md troubleshooting actualizado ─────────────────


def test_bug_072_install_md_troubleshooting_says_create_user_tickets():
    src = INSTALL_MD.read_text()
    # La sección troubleshooting es la segunda referencia a m2m + scopes,
    # típicamente "Si las credenciales están pero el invite sigue fallando".
    troubleshooting_anchor = 'Si las credenciales están pero el invite sigue fallando'
    troubleshooting_idx = src.find(troubleshooting_anchor)
    assert troubleshooting_idx > 0, (
        'BUG-072: la sección troubleshooting debe existir como anchor.'
    )
    troubleshooting_block = src[troubleshooting_idx:troubleshooting_idx + 800]
    assert 'create:user_tickets' in troubleshooting_block, (
        'BUG-072: la sección troubleshooting debe mencionar '
        '`create:user_tickets`, no `read:tickets`.'
    )
    assert 'BUG-072' in troubleshooting_block, (
        'BUG-072: la nota explicativa debe estar etiquetada para forzar '
        'revisión si alguien vuelve a poner `read:tickets`.'
    )
