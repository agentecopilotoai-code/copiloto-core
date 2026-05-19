"""BUG-007: el response del `POST /v1/tenant-signup` debe traer `roles`
(plural array) además del legacy `user_role` (singular string).

## Síntoma del bug

Tras un `POST /v1/tenant-signup` exitoso (201), el frontend invoca
`handleTenantCreated(tenant)` (`admin-panel/src/app/TenantProvider.jsx`)
que agrega el tenant a `tenantOptions` con `...createdTenant`. El user
luego navega a `/admin/t/{slug}`, y el `useTenantOptions` lookup encuentra
el tenant pero `resolveActiveRoles({profile, tenant})`
(`admin-panel/src/permissions/matrix.js`) lo lee así:

```js
const tenantRoles = Array.isArray(tenant?.roles)
  ? tenant.roles
  : tenant?.role
    ? [tenant.role]
    : [];
```

El response tenía SOLO `user_role: 'owner'` — clave distinta a las que
espera `resolveActiveRoles` → `tenantRoles = []` → "Sin acceso a ningún
módulo" hasta que el siguiente `GET /v1/me/tenants` se ejecuta (que SÍ
trae `roles: ['owner']` correctamente, via `array_agg(utr.role)`).

## Fix

El response del `/v1/tenant-signup` ahora incluye `roles: ['owner']`
matcheando el shape de `/v1/me/tenants`. `user_role` se mantiene por
back-compat con consumers viejos. La row en `app.user_tenant_roles` ya
se insertaba con `role='owner'` desde el principio (el bug era solo el
shape del response, no la persistencia).

Este test estático garantiza que el shape no regrese a la versión vieja
(solo `user_role` singular). Si alguien quita la línea
`response['roles'] = ['owner']`, el test falla loudly antes del merge.
"""
from __future__ import annotations

import ast
import inspect
import textwrap

from app.api.v1 import routes as routes_module

def _handler_source() -> str:
    return textwrap.dedent(inspect.getsource(routes_module.create_own_tenant))


def test_tenant_signup_response_includes_roles_array():
    """El response DEBE incluir `roles` como list con al menos 'owner'.

    Cualquier consumer del endpoint (frontend `handleTenantCreated`,
    integraciones externas) puede asumir esta key y este shape.
    """
    src = _handler_source()
    assert "response['roles'] = ['owner']" in src, (
        "el response de /v1/tenant-signup debe incluir `roles: ['owner']` "
        "(plural array) para matchear el shape de /v1/me/tenants y que el "
        "frontend pueda leerlo via resolveActiveRoles sin re-fetch"
    )


def test_tenant_signup_response_keeps_user_role_for_back_compat():
    """`user_role` (singular string) se mantiene por back-compat — algún
    consumer viejo del endpoint puede estar dependiendo de esa key. El
    test garantiza que el fix no rompió consumers existentes.
    """
    src = _handler_source()
    assert "response['user_role'] = 'owner'" in src, (
        "el response debe mantener `user_role: 'owner'` por back-compat — "
        "no quitar esta línea sin auditar consumers"
    )


def test_tenant_signup_returns_dict_response_not_orm_row():
    """El response debe ser un dict mutable (para poder agregar
    `user_role` y `roles`), NO directamente la row de asyncpg.
    `record_to_dict(row)` hace la conversión.
    """
    src = _handler_source()
    assert 'response = record_to_dict(row)' in src, (
        'el response debe construirse desde record_to_dict(row) para que '
        'sea un dict mutable al que se puedan agregar keys'
    )


def test_tenant_signup_handler_inserts_owner_role_in_user_tenant_roles():
    """La row en `app.user_tenant_roles` con `role='owner'` se sigue
    insertando — el bug era solo el shape del response, NO la persistencia.
    Si alguien revierte este insert por error, el fix del response queda
    inconsistente con la realidad de la DB.
    """
    src = _handler_source()
    # El insert literal vive en el handler; verificamos los pedazos clave.
    assert 'insert into app.user_tenant_roles' in src
    assert "values ($1, $2, 'owner', true)" in src, (
        'el INSERT en user_tenant_roles debe seguir asignando role=owner '
        'al user creador del tenant'
    )


# ───── AST-based: ambas keys aparecen como string constants asignados ─────


def test_response_keys_are_string_constants_via_ast():
    """Verifica via AST que las dos asignaciones (`response['user_role']`
    y `response['roles']`) usan string constants explícitos como key, no
    variables computadas. Esto previene una refactorización que mueva la
    key a una constante module-level y termine con un name mismatch
    distinto.
    """
    tree = ast.parse(_handler_source())
    func_node = tree.body[0]
    # Buscamos Subscript assignments al `response`.
    subscript_assigns: list[tuple[str, str]] = []
    for node in ast.walk(func_node):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Subscript)
            and isinstance(node.targets[0].value, ast.Name)
            and node.targets[0].value.id == 'response'
            and isinstance(node.targets[0].slice, ast.Constant)
        ):
            key = node.targets[0].slice.value
            value_repr = ast.unparse(node.value)
            subscript_assigns.append((key, value_repr))

    keys = {key for key, _ in subscript_assigns}
    assert 'user_role' in keys, (
        f"falta asignación literal `response['user_role'] = ...` (encontradas: {keys})"
    )
    assert 'roles' in keys, (
        f"falta asignación literal `response['roles'] = ...` (encontradas: {keys})"
    )
