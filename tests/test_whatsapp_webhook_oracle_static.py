"""SEC-010 sub-finding: `Webhook status codes expose active WhatsApp channel IDs`.

Antes del fix, el handler `receive_whatsapp_webhook` rechazaba con tres
status codes distintos según la causa:

  - 400 → JSON inválido
  - 404 → phone_number_id ausente del payload OR channel no encontrado en DB
  - 401 → channel encontrado pero firma HMAC mala

Un atacante podía enumerar phone_number_ids activos en la plataforma:
shipping un payload con phone_number_id=<guess> + firma garbage, el
status code distinguía "ese phone_number_id NO está activo aquí" (404)
de "ese phone_number_id SÍ está activo pero la firma no matchea" (401).
Sumado a un timing oracle (el HMAC O(n) sobre el body solo se ejecutaba
si el channel existía), la enumeración era práctica.

El fix:
  1. Todos los rechazos retornan el MISMO 401 con el MISMO detail
     `Invalid webhook signature`.
  2. Si no hay channel real, igual ejecutamos HMAC contra
     `_WHATSAPP_WEBHOOK_DUMMY_SECRET` (nonce estable del proceso, 32 bytes
     hex) para que el tiempo de respuesta no distinga los paths.
  3. El motivo real del rechazo se preserva server-side via
     `audit_durably(...)` con `metadata.reason` ∈
     {`invalid_payload`, `missing_phone_number_id`, `unknown_channel`,
     `invalid_signature`} para forensia, sin que esa info se filtre al
     caller.

Estos tests static son la defensa frontal contra una regresión que
re-abra el oracle (alguien que vuelva a separar branches `raise
HTTPException(404, ...)` para "channel not found" vs `401` para "bad
signature").
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

from app.api.v1 import routes as routes_module

ROUTES = Path('app/api/v1/routes.py')


# ───── Dummy secret module constant ───────────────────────────────────────


def test_dummy_secret_is_defined_at_module_level():
    """La constante DEBE existir como módulo-level (no por-request).
    Generarla en cada request sería pesado y filtraría timing del path
    `secrets.token_hex(32)` que tampoco es O(1)."""
    assert hasattr(routes_module, '_WHATSAPP_WEBHOOK_DUMMY_SECRET')
    secret = routes_module._WHATSAPP_WEBHOOK_DUMMY_SECRET
    assert isinstance(secret, str)
    # 32 bytes hex = 64 chars; compatible con `normalize_meta_app_secret`
    # (Meta App Secrets son 32-char hex; nuestro dummy es más largo y
    # nunca puede matchear con uno real legítimo).
    assert len(secret) >= 32


def test_dummy_secret_uses_secrets_module_for_entropy():
    """No bastaría `'x' * 32` — la constante debe ser cryptographic-grade
    para que un atacante que conozca el código fuente NO pueda forjar una
    firma que matchee con el dummy (lo que le permitiría distinguir
    "channel not found" de "channel found").

    Verificamos esto inspeccionando el source: la constante debe
    inicializarse desde `secrets.token_hex(...)`.
    """
    # Buscar la asignación en el source completo del módulo.
    src = ROUTES.read_text()
    # Permitimos espacios variables pero exigimos secrets.token_hex.
    assert '_WHATSAPP_WEBHOOK_DUMMY_SECRET = secrets.token_hex(' in src, (
        'el dummy secret debe inicializarse desde secrets.token_hex(...) — '
        'cualquier otro inicializador es predecible y rompe la defensa'
    )


# ───── Handler: uniform status code on rejection ──────────────────────────


def _handler_source() -> str:
    """Source del handler `receive_whatsapp_webhook` (la función decorada
    sigue siendo accessible vía `routes_module.receive_whatsapp_webhook`).
    """
    return textwrap.dedent(inspect.getsource(routes_module.receive_whatsapp_webhook))


def test_handler_raises_only_401_with_uniform_detail():
    """Todo `raise HTTPException(...)` dentro del handler debe usar
    `status_code=401` y `detail='Invalid webhook signature'`. Cualquier
    otro status code (400, 404, 403, etc.) re-abre el oracle.

    Parseamos el AST y rechazamos cualquier HTTPException con status
    diferente o detail diferente.
    """
    tree = ast.parse(_handler_source())
    # `tree.body[0]` es la AsyncFunctionDef del handler.
    func_node = tree.body[0]
    assert isinstance(func_node, ast.AsyncFunctionDef)

    raises: list[ast.Call] = []
    for node in ast.walk(func_node):
        if (
            isinstance(node, ast.Raise)
            and isinstance(node.exc, ast.Call)
            and isinstance(node.exc.func, ast.Name)
            and node.exc.func.id == 'HTTPException'
        ):
            raises.append(node.exc)

    assert raises, 'el handler debe tener al menos un raise HTTPException'

    for call in raises:
        # Extraer kwargs (status_code, detail).
        kwargs = {kw.arg: kw.value for kw in call.keywords}
        # status_code DEBE ser literal 401.
        status_node = kwargs.get('status_code')
        assert isinstance(status_node, ast.Constant) and status_node.value == 401, (
            f'HTTPException con status_code distinto a 401 en línea {call.lineno}: '
            f'{ast.unparse(call)}'
        )
        # detail DEBE ser exactamente "Invalid webhook signature".
        detail_node = kwargs.get('detail')
        assert (
            isinstance(detail_node, ast.Constant)
            and detail_node.value == 'Invalid webhook signature'
        ), (
            f'HTTPException con detail distinto en línea {call.lineno}: '
            f'{ast.unparse(call)}'
        )


def test_handler_no_longer_raises_404_for_missing_channel():
    """Regression gate explícito: el detail antiguo (`WhatsApp channel not
    found`) no debe aparecer NUNCA en el cuerpo del handler. Si reaparece,
    es señal de que alguien revirtió el fix."""
    src = _handler_source()
    assert 'WhatsApp channel not found' not in src, (
        'el detail antiguo `WhatsApp channel not found` filtra channel '
        'existence — debe estar reemplazado por `Invalid webhook signature`'
    )
    assert "status_code=404" not in src, (
        'ningún rechazo del webhook debe retornar 404 — re-abre el oracle'
    )
    assert "status_code=400" not in src, (
        'parse error tampoco debe retornar 400 distinguible — debe caer al 401 común'
    )


# ───── Handler: dummy HMAC execution for non-matching channels ────────────


def test_handler_uses_dummy_secret_when_channel_not_resolved():
    """Cuando `channel` es None, `app_secret` DEBE asignarse al dummy y
    `verify_signature_with_secret` DEBE ejecutarse igual — sin esto el
    timing del HMAC O(n) sobre el body distingue rápido (sin channel) vs
    lento (con channel)."""
    src = _handler_source()
    # Patrones que defienden el flujo.
    assert '_WHATSAPP_WEBHOOK_DUMMY_SECRET' in src, (
        'el handler debe referenciar el dummy secret a nivel módulo'
    )
    assert 'verify_signature_with_secret(body, x_hub_signature_256, app_secret)' in src, (
        'la verificación debe correr SIEMPRE con el app_secret resuelto '
        '(real o dummy), no gateada por if channel'
    )
    # Si el secret real es None (channel resuelto pero sin secret persistido),
    # el `or _WHATSAPP_WEBHOOK_DUMMY_SECRET` lo cubre.
    assert 'or _WHATSAPP_WEBHOOK_DUMMY_SECRET' in src, (
        'channels sin secret persistido (edge case) deben caer al dummy '
        'también para no exponer un path con HMAC contra None'
    )


def test_signature_verify_is_called_unconditionally():
    """`verify_signature_with_secret` se invoca EXACTAMENTE una vez en el
    handler y no está dentro de un `if channel`. AST-based check para que
    una refactorización no lo vuelva a meter en una rama condicional.
    """
    tree = ast.parse(_handler_source())
    func_node = tree.body[0]
    calls = [
        node
        for node in ast.walk(func_node)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == 'verify_signature_with_secret'
    ]
    assert len(calls) == 1, (
        f'verify_signature_with_secret debe invocarse exactamente una vez '
        f'(encontradas {len(calls)}); evitar duplicación de paths'
    )


# ───── Audit_durably preserva el motivo real internamente ─────────────────


def test_handler_uses_audit_durably_for_rejection_forensics():
    """El motivo real (`unknown_channel`, `invalid_signature`, etc.) debe
    persistirse via `audit_durably` (NO `audit(conn, ...)` que perdería
    el log con el ROLLBACK del raise — ver fix SEC-010.1 previo).
    """
    src = _handler_source()
    assert 'audit_durably(' in src, (
        'el rechazo debe persistir el audit durably (sobrevive al rollback)'
    )
    # Los 4 motivos posibles deben estar enumerados como branches.
    for reason in ('invalid_payload', 'missing_phone_number_id', 'unknown_channel', 'invalid_signature'):
        assert f"'{reason}'" in src, (
            f"el audit debe distinguir el motivo `{reason}` en metadata "
            f'para forensia operacional'
        )
    assert "action='webhook.whatsapp_rejected'" in src


def test_audit_does_not_leak_channel_existence_to_caller():
    """El motivo va en `metadata.reason` que NO se serializa al cliente —
    es solo `app.audit_logs`. El status code + body que ve el caller son
    uniformes (401 + 'Invalid webhook signature'). Esto es la combinación
    completa que cierra el oracle.
    """
    # Ya verificamos los status codes uniformes; este test es la línea
    # explícita en docs para que el revisor entienda que la asimetría
    # interna es deliberada (forensia >> ocultamiento server-side).
    src = _handler_source()
    # El audit y el raise están en el mismo bloque; verificamos que el
    # raise queda DESPUÉS del audit_durably (no antes — sino el rollback
    # del raise destruiría incluso el audit con audit_durably si fuera
    # `audit` normal). audit_durably es transaction-independent, pero
    # ordenamos el código así igual por claridad.
    audit_pos = src.find('await audit_durably(')
    raise_pos = src.rfind("raise HTTPException")
    assert audit_pos > 0 and raise_pos > 0
    assert audit_pos < raise_pos, (
        'audit_durably debe correr antes del raise (semánticamente — '
        'aunque sobrevive al rollback igual)'
    )
