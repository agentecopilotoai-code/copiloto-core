"""SEC-010 sub-finding: `Cross-tenant conversation metadata logged on 404`.

El handler `get_conversation` corría un query diagnóstico siempre que
devolvía 404, logueando `actual_tenant_id` y `actual_status` de la
conversación pedida. Cuando el caller pegaba un `conversation_id` que
pertenecía a OTRO tenant (probando UUIDs random vía
`/v1/tenants/<su-tenant>/conversations/<uuid-ajeno>`), el log filtraba:

  - Si la conversación existe globalmente.
  - El tenant_id real dueño.
  - El estado actual de esa conversación.

Esa info fugaba a `docker logs` y al log aggregator. Operadores con
acceso a esos logs (legítimo para debugging) podían inadvertidamente
enumerar conversaciones de otros tenants.

Fix:
  1. Nueva flag `Settings.debug_cross_tenant_diagnostics` (env
     `DEBUG_CROSS_TENANT_DIAGNOSTICS`, default `false`).
  2. El bloque diagnóstico + el log con `actual_*` quedan gated al flag.
  3. Path por default (sin flag): log mínimo con solo info que el caller
     YA conoce (su tenant, su conversation_id pedido, su actor).

Si alguien revierte el gate o vuelve a poner el query sin condición,
este test falla loudly antes de merge.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

from app.api.v1 import routes as routes_module
from app.core import config as config_module
from tests._routes_aggregator import routes_aggregated_source

CONFIG = Path('app/core/config.py')


def _handler_source() -> str:
    return textwrap.dedent(inspect.getsource(routes_module.get_conversation))


# ───── Settings: flag opt-in con default seguro ──────────────────────────


def test_settings_exposes_debug_cross_tenant_diagnostics_default_false():
    """La flag debe estar en `Settings` con default `False`. Cualquier
    cambio del default a `True` re-abre el leak para todos los entornos.

    Verificamos a nivel de schema (model_fields) — no instanciamos Settings
    porque eso requiere muchos env vars que no son relevantes para este
    test. El default del field es la verdad ejecutable: es lo que aplica
    a deployments que no setean `DEBUG_CROSS_TENANT_DIAGNOSTICS` explícito.
    """
    fields = config_module.Settings.model_fields
    assert 'debug_cross_tenant_diagnostics' in fields, (
        'falta el field `debug_cross_tenant_diagnostics` en Settings'
    )
    field = fields['debug_cross_tenant_diagnostics']
    assert field.default is False, (
        f'el default debe ser False (cambiarlo re-abre el leak). Got: {field.default!r}'
    )
    # Type annotation debe ser bool — sin esto, valores extraños del env
    # podrían terminar como truthy strings.
    assert field.annotation is bool


def test_settings_field_is_documented_in_source():
    """La frase `SEC-010 fix` ancla la decisión al ticket; sin esto, un
    refactor accidental puede borrar la flag pensando que es noise.
    """
    src = CONFIG.read_text()
    assert 'debug_cross_tenant_diagnostics' in src
    assert 'SEC-010 fix' in src
    assert 'DEBUG_CROSS_TENANT_DIAGNOSTICS' in src


# ───── Handler: el diagnóstico está gated por la flag ────────────────────


def test_handler_gates_diagnostic_query_behind_flag():
    """El `fetchrow` que arma el `diagnostic` SOLO debe correr dentro de
    un `if settings.debug_cross_tenant_diagnostics:`. AST check para que
    un refactor accidental no lo saque del if.
    """
    src = _handler_source()
    tree = ast.parse(src)
    func_node = tree.body[0]

    # Localizar todos los `await conn.fetchrow(...)` con literal SQL que
    # contiene "exists_any_tenant" (el query diagnóstico cross-tenant).
    diagnostic_calls = []
    for node in ast.walk(func_node):
        if (
            isinstance(node, ast.Await)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Attribute)
            and node.value.func.attr == 'fetchrow'
        ):
            # Inspeccionar args para encontrar el SQL diagnóstico.
            for arg in node.value.args:
                if (
                    isinstance(arg, ast.Constant)
                    and isinstance(arg.value, str)
                    and 'exists_any_tenant' in arg.value
                ):
                    diagnostic_calls.append(node)
                    break

    assert diagnostic_calls, (
        'no encontré el query diagnóstico (exists_any_tenant) en el handler'
    )

    # Para cada call, verificar que su ancestor más cercano es un `if`
    # que evalúa `settings.debug_cross_tenant_diagnostics`.
    for call in diagnostic_calls:
        ancestors = _find_if_ancestors(func_node, call)
        flagged = any(
            _condition_references_flag(if_node.test, 'debug_cross_tenant_diagnostics')
            for if_node in ancestors
        )
        assert flagged, (
            f'el query diagnóstico en línea {call.lineno} NO está gated por '
            '`if settings.debug_cross_tenant_diagnostics` — esto re-abre el leak'
        )


def test_handler_logs_minimum_info_when_flag_off():
    """El path default (sin flag) debe loguear solo info que el caller
    YA conoce: su tenant_id, su conversation_id, su actor_id. NO debe
    referenciar `actual_tenant_id`, `actual_status`, `exists_any_tenant`
    en ese path.
    """
    src = _handler_source()
    # Localizar el branch `else:` (path sin flag) — buscamos "operations.conversation.detail_not_found"
    # dentro de un `log.info` (no `log.warning`).
    assert 'log.info(' in src
    assert "'operations.conversation.detail_not_found'" in src
    # El path mínimo NO debe tener `actual_tenant_id` o `actual_status`
    # como kwargs del `log.info` (sí pueden aparecer en el bloque flagged).
    # Verificamos AST: el `log.info` que recibe `'operations.conversation.detail_not_found'`
    # NO debe tener esos kwargs.
    tree = ast.parse(src)
    func_node = tree.body[0]
    info_calls = []
    for node in ast.walk(func_node):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == 'info'
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == 'log'
        ):
            info_calls.append(node)

    # Al menos un log.info con el event de "not found" debe existir.
    not_found_info = [
        call for call in info_calls
        if any(
            isinstance(arg, ast.Constant)
            and arg.value == 'operations.conversation.detail_not_found'
            for arg in call.args
        )
    ]
    assert not_found_info, (
        'falta `log.info` minimal para el path sin flag — sin esto el '
        'operador no tiene ningún audit del 404'
    )
    # Ese log.info NO debe leakear info cross-tenant.
    leak_kwargs = {'actual_tenant_id', 'actual_status', 'exists_any_tenant', 'exists_for_tenant'}
    for call in not_found_info:
        kwargs = {kw.arg for kw in call.keywords if kw.arg}
        leaked = kwargs & leak_kwargs
        assert not leaked, (
            f'log.info del path mínimo loguea {leaked} — debe ser solo '
            'tenant_id (del caller) + conversation_id (del request) + actor_id'
        )


def test_handler_marks_diagnostic_log_with_flag_name():
    """El log warning del path flagged debe incluir `diagnostic_flag` para
    que el operator que ve un log con `actual_tenant_id` sepa qué flag
    está activo y cómo desactivarlo.
    """
    src = _handler_source()
    assert "diagnostic_flag='DEBUG_CROSS_TENANT_DIAGNOSTICS'" in src


# ───── No quedan referencias raw al leak fuera del gate ──────────────────


def test_no_diagnostic_query_outside_gated_block():
    """Defensa final: el SQL diagnóstico (marcado por `exists_any_tenant`)
    solo aparece DENTRO del handler `get_conversation` y SOLO dentro de
    su bloque gated. Si alguien lo copia a otro handler o lo saca del
    `if settings.debug_cross_tenant_diagnostics:`, este test falla.
    """
    # Sólo `get_conversation` debe contener el marker — ningún otro
    # handler / módulo.
    handler_src = _handler_source()
    assert 'exists_any_tenant' in handler_src, (
        'el handler debe contener el SQL diagnóstico (gated)'
    )

    # En el resto de `routes.py` (todo lo que no sea el handler), `exists_any_tenant`
    # NO debe aparecer. Defensa contra que alguien copie el query.
    full_src = routes_aggregated_source()
    # Filtrar comentarios para evitar falsos positivos.
    executable_lines = [
        line for line in full_src.splitlines() if not line.lstrip().startswith('#')
    ]
    executable_src = '\n'.join(executable_lines)
    # Localizar el span del handler en el source.
    handler_marker = 'async def get_conversation('
    handler_start = executable_src.find(handler_marker)
    assert handler_start >= 0, 'no encontré get_conversation en routes.py'
    # El próximo `async def` después del handler marca el fin.
    handler_end = executable_src.find('\nasync def ', handler_start + len(handler_marker))
    if handler_end == -1:
        handler_end = len(executable_src)
    outside_handler = executable_src[:handler_start] + executable_src[handler_end:]
    assert 'exists_any_tenant' not in outside_handler, (
        'el SQL diagnóstico `exists_any_tenant` aparece FUERA de '
        'get_conversation — alguien lo copió a otro handler y re-abrió el leak'
    )

    # Y dentro del handler, todas las ocurrencias deben vivir dentro de
    # un `if` que evalúa `debug_cross_tenant_diagnostics` (el AST test
    # arriba ya cubre el caso del `fetchrow`; este check refuerza para
    # los kwargs del `log.warning`).
    tree = ast.parse(handler_src)
    func_node = tree.body[0]
    for node in ast.walk(func_node):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and 'exists_any_tenant' in node.value
        ):
            ancestors = _find_if_ancestors(func_node, node)
            assert any(
                _condition_references_flag(if_node.test, 'debug_cross_tenant_diagnostics')
                for if_node in ancestors
            ), (
                f'string literal `exists_any_tenant` en línea {node.lineno} '
                'NO está dentro del bloque gated por '
                '`debug_cross_tenant_diagnostics` — re-abre el leak'
            )


# ───── Helpers ────────────────────────────────────────────────────────────


def _find_if_ancestors(root: ast.AST, target: ast.AST) -> list[ast.If]:
    """Devuelve la cadena de `ast.If` ancestors del `target` dentro de `root`."""
    parents: dict[int, ast.AST] = {}

    def walk(node: ast.AST, parent: ast.AST | None) -> None:
        parents[id(node)] = parent
        for child in ast.iter_child_nodes(node):
            walk(child, node)

    walk(root, None)

    ancestors: list[ast.If] = []
    cur = parents.get(id(target))
    while cur is not None:
        if isinstance(cur, ast.If):
            ancestors.append(cur)
        cur = parents.get(id(cur))
    return ancestors


def _condition_references_flag(test_node: ast.AST, flag_name: str) -> bool:
    """True si la condición `test_node` evalúa la flag por nombre."""
    for node in ast.walk(test_node):
        if isinstance(node, ast.Attribute) and node.attr == flag_name:
            return True
        if isinstance(node, ast.Name) and node.id == flag_name:
            return True
    return False
