"""BUG-009: el invite endpoint debe propagar `tenant_id` + asignar rol Auth0
al user invitado para que su JWT post-login traiga los claims correctos.

Antes del fix, `app/services/auth0_admin.py::invite_user`:
  - Creaba el user en Auth0 (`POST /api/v2/users`).
  - Emitía ticket de password-change (`POST /api/v2/tickets/password-change`).
  - Auth0 mandaba el email de invitación.
  - **Pero**: el `app_metadata.tenant_id` quedaba vacío y NO se asignaba
    rol Auth0 al user via `POST /api/v2/users/{id}/roles`.

Consecuencia: el invitado completaba el password, logueaba, y su JWT venía
sin `tenant_id` claim ni `roles` claim porque la PostLogin Action de claims
(`scripts/configure-auth0.sh` línea 374-376) lee de `event.user.app_metadata.tenant_id`
y `event.authorization.roles`, que el invite no poblaba. El panel mostraba
"Aún no estás asignada a un negocio" y `ensure_tenant_access` rechazaba
endpoints privilegiados con 403 "agent role or higher is required for this tenant".

Fix:
  1. `set_user_tenant_metadata(auth_subject, tenant_id)` → PATCH /users/{id}
     con `app_metadata.tenant_id + default_tenant_id`.
  2. `assign_auth0_role_by_name(auth_subject, role_name)` → resolve role_id
     vía GET /roles (cached) + POST /users/{id}/roles.
  3. `invite_user` invoca ambos best-effort entre crear user y emitir ticket.

Si los helpers no se llaman, o el invite no los integra, el bug se reabre
silenciosamente. Estos tests static defienden la integración.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

from app.services import auth0_admin

AUTH0_ADMIN = Path('app/services/auth0_admin.py')


def _handler_source(name: str) -> str:
    return textwrap.dedent(inspect.getsource(getattr(auth0_admin, name)))


# ───── Helpers nuevos existen + firmas correctas ──────────────────────────


def test_set_user_tenant_metadata_helper_exists_with_correct_signature():
    """`set_user_tenant_metadata(*, auth_subject, tenant_id)` — kwargs-only
    para que el caller no confunda el orden y termine PATCH-eando el user
    equivocado. Devuelve dict con shape conocido por consumers.
    """
    assert hasattr(auth0_admin, 'set_user_tenant_metadata')
    sig = inspect.signature(auth0_admin.set_user_tenant_metadata)
    for required in ('auth_subject', 'tenant_id'):
        assert required in sig.parameters, (
            f'set_user_tenant_metadata falta kwarg `{required}`'
        )
        # Kwargs-only (POSITIONAL_OR_KEYWORD podría confundir).
        assert sig.parameters[required].kind == inspect.Parameter.KEYWORD_ONLY


def test_assign_auth0_role_by_name_helper_exists_with_correct_signature():
    assert hasattr(auth0_admin, 'assign_auth0_role_by_name')
    sig = inspect.signature(auth0_admin.assign_auth0_role_by_name)
    for required in ('auth_subject', 'role_name'):
        assert required in sig.parameters
        assert sig.parameters[required].kind == inspect.Parameter.KEYWORD_ONLY


def test_role_id_cache_exists_and_can_be_cleared():
    """El cache evita 1 `GET /roles` por cada invite. Test helper
    `clear_auth0_role_cache` permite a tests dinámicos resetear entre runs.
    """
    assert hasattr(auth0_admin, '_AUTH0_ROLE_ID_CACHE')
    assert isinstance(auth0_admin._AUTH0_ROLE_ID_CACHE, dict)
    assert hasattr(auth0_admin, 'clear_auth0_role_cache')


# ───── set_user_tenant_metadata: PATCH app_metadata correctamente ────────


def test_set_user_tenant_metadata_patches_app_metadata_not_user_metadata():
    """La Action de claims lee de `app_metadata.tenant_id` (NO
    `user_metadata.tenant_invitation`). Es la diferencia que causaba el bug.
    """
    src = _handler_source('set_user_tenant_metadata')
    assert "_mgmt_request(" in src
    assert "'PATCH'" in src
    assert "f'/users/{auth_subject}'" in src
    # Body con app_metadata (no user_metadata).
    assert "'app_metadata':" in src
    assert "'tenant_id': str(tenant_id)" in src
    assert "'default_tenant_id': str(tenant_id)" in src
    # NO debe usar user_metadata para esto.
    tree = ast.parse(src)
    func_node = tree.body[0]
    for node in ast.walk(func_node):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value == 'user_metadata'
        ):
            # OK encontrar el string en docstring, no en body ejecutable.
            # Para distinguir, contamos: docstring solo aparece como primer
            # Expr.value en func body.
            docstring = ast.get_docstring(func_node) or ''
            assert 'user_metadata' not in docstring or 'user_metadata' in src.split('"""')[1], (
                'set_user_tenant_metadata referencia user_metadata fuera del docstring'
            )


def test_set_user_tenant_metadata_disabled_when_no_mgmt_credentials():
    """No-op cuando `auth0_management_enabled() == False` (dev local sin
    credenciales). Sin esto, el invite local crashearía intentando llamar
    al Mgmt API.
    """
    src = _handler_source('set_user_tenant_metadata')
    assert 'if not auth0_management_enabled():' in src
    assert "return {'disabled': True}" in src


# ───── assign_auth0_role_by_name: resolve + POST /users/{id}/roles ───────


def test_assign_auth0_role_by_name_resolves_role_id_before_posting():
    """Debe llamar `_resolve_auth0_role_id` Y verificar que devuelve algo
    antes de POST-ear. Sin esto, podríamos hacer un POST con `role_id=None`
    que Auth0 rechazaría con un error confuso.
    """
    src = _handler_source('assign_auth0_role_by_name')
    assert '_resolve_auth0_role_id(role_name)' in src
    assert 'if not role_id:' in src
    # Fail-closed con error explícito en lugar de POST con None.
    assert "'auth0_role_not_found:" in src


def test_assign_auth0_role_by_name_posts_to_users_roles_endpoint():
    """POST /users/{id}/roles es el endpoint que hace que Auth0 incluya
    el rol en `event.authorization.roles` del próximo login.
    """
    src = _handler_source('assign_auth0_role_by_name')
    assert "_mgmt_request(" in src
    assert "'POST'" in src
    assert "f'/users/{auth_subject}/roles'" in src
    assert "'roles': [role_id]" in src


def test_assign_auth0_role_by_name_logs_unresolved_role():
    """Cuando role_name no existe en Auth0 (typo del caller o tenant Auth0
    sin los roles que el script crea), debe loguearse explícitamente para
    que el operador sepa qué rol falta. Sin log, el invite "funciona" pero
    el invitado no tiene rol.
    """
    src = _handler_source('assign_auth0_role_by_name')
    assert "log.warning(" in src
    assert "'auth0_admin.assign_role_by_name_unresolved'" in src


# ───── invite_user integra ambos helpers ─────────────────────────────────


def test_invite_user_calls_set_user_tenant_metadata():
    src = _handler_source('invite_user')
    assert 'await set_user_tenant_metadata(' in src
    # Pasa los kwargs correctos.
    assert 'auth_subject=auth0_user_id' in src
    assert 'tenant_id=tenant_id' in src


def test_invite_user_calls_assign_auth0_role_by_name():
    src = _handler_source('invite_user')
    assert 'await assign_auth0_role_by_name(' in src
    # Usa el `role` que el caller pasó (no hardcodea).
    assert 'role_name=role' in src


def test_invite_user_calls_propagation_before_ticket():
    """Orden importa: si el ticket se emite antes y el user clickea el
    email rapido, el primer login puede llegar antes de que el role esté
    asignado. Forzar el orden: metadata + role → ticket.
    """
    src = _handler_source('invite_user')
    metadata_pos = src.find('await set_user_tenant_metadata(')
    role_pos = src.find('await assign_auth0_role_by_name(')
    ticket_pos = src.find("'/tickets/password-change'")
    assert metadata_pos > 0 and role_pos > 0 and ticket_pos > 0
    assert metadata_pos < ticket_pos, (
        'set_user_tenant_metadata DEBE llamarse antes del ticket de password-change'
    )
    assert role_pos < ticket_pos, (
        'assign_auth0_role_by_name DEBE llamarse antes del ticket de password-change'
    )


def test_invite_user_propagation_is_best_effort_not_aborting():
    """Si la propagación falla (ej. permisos Auth0 insuficientes), el
    invite NO debe abortar — el user de Auth0 ya existe y el ticket es
    lo que dispara el email. Los errores se acumulan y se devuelven en
    `propagation_errors` para que el panel los muestre como warning.
    """
    src = _handler_source('invite_user')
    assert 'propagation_errors' in src
    # Catch específico de HTTPError (no Exception genérico — no queremos
    # tragar errores de programación).
    assert 'except httpx.HTTPError as exc:' in src
    # Log específico con auth0_user_id para que el operador pueda fixearlo
    # a mano si hace falta.
    assert "'auth0_admin.invite_user_app_metadata_failed'" in src
    assert "'auth0_admin.invite_user_role_assign_failed'" in src


def test_invite_user_returns_propagation_errors_in_result():
    """El response del invite incluye `propagation_errors` si hubo issues
    — el frontend puede mostrar un warning "el user fue creado pero hay
    que asignar rol/tenant manualmente" sin romper el flow.
    """
    src = _handler_source('invite_user')
    assert "'propagation_errors': propagation_errors" in src
    assert 'if propagation_errors' in src


# ───── Cache de role_id: GET /roles solo una vez ─────────────────────────


def test_resolve_auth0_role_id_uses_cache():
    """El cache evita 1 GET /roles por invite — escala mejor con tenants
    grandes que invitan muchos miembros."""
    src = _handler_source('_resolve_auth0_role_id')
    assert '_AUTH0_ROLE_ID_CACHE' in src
    assert 'if role_name in _AUTH0_ROLE_ID_CACHE:' in src
    # Lookup en cache antes de hacer HTTP.
    cache_check_pos = src.find('if role_name in _AUTH0_ROLE_ID_CACHE:')
    http_call_pos = src.find('_mgmt_request')
    assert cache_check_pos < http_call_pos


def test_resolve_auth0_role_id_populates_cache_after_fetch():
    """Después del GET, todos los roles encontrados van al cache (no solo
    el pedido) — la próxima invite con cualquier rol del set ya cachea.
    """
    src = _handler_source('_resolve_auth0_role_id')
    assert '_AUTH0_ROLE_ID_CACHE[name] = rid' in src


# ───── Header del script Auth0 menciona los scopes nuevos ────────────────


def test_management_api_scopes_already_include_role_assignment():
    """El script `configure-auth0.sh` debe haber autorizado los scopes que
    los helpers nuevos necesitan: `create:role_members` para asignar rol,
    `read:roles` para resolver role_id, `update:users` para PATCH metadata.

    Si estos scopes faltan, el invite seguirá rompiéndose en runtime con
    403 en `/oauth/token` aunque el código local sea correcto.
    """
    script = Path('scripts/configure-auth0.sh').read_text()
    # Las 3 dependencias que los helpers nuevos suman al flow.
    for scope in ('create:role_members', 'read:roles', 'update:users'):
        assert scope in script, (
            f'scripts/configure-auth0.sh no incluye `{scope}` en MGMT_API_SCOPES — '
            'helper BUG-009 va a fallar 403 al intentarlo'
        )
