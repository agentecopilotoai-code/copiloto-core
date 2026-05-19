"""SEC-010 sub-finding: `Rejected payment webhook audits are rolled back`.

`app/db/pool.py:29` envuelve cada connection inyectada por `get_db` en
`async with conn.transaction():`. Si un handler ejecuta `await audit(conn, ...)`
y luego `raise HTTPException(...)`, el ROLLBACK del transaction context
borra el INSERT del audit — la forensia del rechazo se pierde.

Este test estático garantiza que los 4 sitios de rechazo de webhooks de
pago (2 en `receive_payment_webhook`, 2 en `receive_subscription_webhook`)
usan `audit_durably(...)` en lugar de `audit(conn, ...)`. `audit_durably`
adquiere una connection ad-hoc del pool, fuera de la transacción del
request, y el INSERT sobrevive al ROLLBACK.

Si alguien revierte la migración (vuelve a `await audit(conn, ...)` en un
sitio de rechazo de pago), este test falla loudly antes de que llegue a
prod sin que nadie note la pérdida silenciosa de audits.
"""
from __future__ import annotations

import ast
import inspect
import re
import textwrap
from pathlib import Path

from app.api.v1 import routes as routes_module
from app.services import audit as audit_module
from tests._routes_aggregator import routes_aggregated_source

AUDIT = Path('app/services/audit.py')


# ───── audit_durably exposed ──────────────────────────────────────────────


def test_audit_module_exposes_audit_durably():
    assert hasattr(audit_module, 'audit_durably'), (
        'app.services.audit debe exponer `audit_durably` para webhooks rechazados'
    )
    sig = inspect.signature(audit_module.audit_durably)
    # Sin parámetro `conn` posicional — el helper resuelve su propia conn.
    assert 'conn' not in sig.parameters, (
        'audit_durably NO debe aceptar conn — debe adquirir su propia del pool'
    )
    # Mismos campos del audit normal (kwargs-only).
    for required_kw in (
        'tenant_id',
        'actor_type',
        'actor_id',
        'action',
        'entity_type',
        'entity_id',
        'metadata',
    ):
        assert required_kw in sig.parameters, (
            f'audit_durably falta el kwarg `{required_kw}`'
        )


def test_audit_durably_acquires_own_connection_from_pool():
    src = inspect.getsource(audit_module.audit_durably)
    # Acquire del pool global (no recibe conn por parámetro).
    assert 'db.pool.acquire()' in src
    # Insert directo via execute (no llama a `audit()` recursivamente —
    # eso volvería a meter la lógica en una transacción del caller si la
    # firma cambia).
    assert 'insert into app.audit_logs' in src


def test_audit_durably_does_not_open_a_transaction_block():
    """El INSERT debe correr en autocommit. Si abrimos `conn.transaction()`,
    desperdiciamos el propósito del helper (un rollback dentro de ese block
    sería igual de letal que en el caller). El `async with pool.acquire()`
    devuelve una conn sin transacción abierta — asyncpg autocommittea
    cada statement individual en ese modo.

    Parseamos el AST y buscamos llamadas reales a `.transaction()` en el
    cuerpo de la función (ignorando docstrings y comentarios, donde el
    texto explica POR QUÉ se evita y aparece literal).
    """
    src = textwrap.dedent(inspect.getsource(audit_module.audit_durably))
    tree = ast.parse(src)
    # La función parseada es el único top-level node.
    func_node = tree.body[0]
    assert isinstance(func_node, (ast.AsyncFunctionDef, ast.FunctionDef))

    # Recorrer todas las llamadas a método y rechazar `<algo>.transaction()`
    # cuando aparece como expresión ejecutable. ast.walk ignora strings
    # (que son Constant nodes con .value str, no Call nodes).
    transaction_calls = [
        node
        for node in ast.walk(func_node)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == 'transaction'
    ]
    assert not transaction_calls, (
        f'audit_durably abre una transacción explícita: '
        f'{[ast.unparse(c) for c in transaction_calls]} — debe ser autocommit'
    )


def test_audit_durably_is_best_effort_and_logs_on_failure():
    """Si la DB está caída cuando llega un webhook hostil, queremos rechazar
    correctamente (raise HTTPException), no que el handler crashee porque
    el audit no pudo persistir. Best-effort: log + return."""
    src = inspect.getsource(audit_module.audit_durably)
    assert 'try:' in src
    # Catch genérico (BLE001 silenciado en el código con noqa) — un audit
    # perdido nunca debe romper el endpoint que rechaza una request hostil.
    assert 'except Exception' in src
    assert 'logger.exception' in src


def test_audit_durably_skips_when_pool_not_initialized():
    """En tests/CLI donde la pool no está conectada, `db.pool` es None.
    El helper debe loguear y retornar — no crashear con AttributeError."""
    src = inspect.getsource(audit_module.audit_durably)
    assert 'if not db.pool' in src
    assert 'logger.warning' in src


# ───── 4 call sites in routes.py migrated ────────────────────────────────


def _function_source(name: str) -> str:
    return inspect.getsource(getattr(routes_module, name))


def test_payment_webhook_rejection_paths_use_audit_durably():
    """`receive_payment_webhook` tiene dos rejection paths (missing_secret +
    bad_signature). AMBOS deben usar `audit_durably` para sobrevivir al
    rollback del raise HTTPException posterior."""
    src = _function_source('receive_payment_webhook')

    # Ambos rejection paths deben aparecer con audit_durably.
    # Cuenta ocurrencias para garantizar que NO quedó ninguno con `audit(`.
    durably_count = src.count('audit_durably(')
    assert durably_count >= 2, (
        f'receive_payment_webhook tiene {durably_count} audit_durably; '
        'esperamos ≥ 2 (missing_secret + bad_signature)'
    )

    # No deben quedar `await audit(conn,` en las rejection paths.
    # Capturamos el bloque desde `if not secret:` hasta el segundo raise.
    rejection_pattern = re.compile(
        r'if not secret:.*?raise HTTPException.*?if not signature_ok:.*?raise HTTPException',
        flags=re.DOTALL,
    )
    rejection_block = rejection_pattern.search(src)
    assert rejection_block is not None, (
        'no pude localizar los rejection paths del payment webhook'
    )
    assert 'await audit(' not in rejection_block.group(0), (
        'rejection path de payment webhook tiene `await audit(conn, ...)` — '
        'debe ser `audit_durably` para sobrevivir al rollback'
    )


def test_subscription_webhook_rejection_paths_use_audit_durably():
    """Mismo invariante para `receive_subscription_webhook`."""
    src = _function_source('receive_subscription_webhook')

    durably_count = src.count('audit_durably(')
    assert durably_count >= 2, (
        f'receive_subscription_webhook tiene {durably_count} audit_durably; '
        'esperamos ≥ 2 (missing_secret + bad_signature)'
    )

    rejection_pattern = re.compile(
        r'if not secret:.*?raise HTTPException.*?if not signature_ok:.*?raise HTTPException',
        flags=re.DOTALL,
    )
    rejection_block = rejection_pattern.search(src)
    assert rejection_block is not None, (
        'no pude localizar los rejection paths del subscription webhook'
    )
    assert 'await audit(' not in rejection_block.group(0), (
        'rejection path de subscription webhook tiene `await audit(conn, ...)` — '
        'debe ser `audit_durably`'
    )


def test_routes_imports_audit_durably():
    src = routes_aggregated_source()
    assert 'from app.services.audit import audit, audit_durably' in src, (
        'app/api/v1/routes.py debe importar audit_durably junto a audit'
    )


# ───── audit() normal sigue funcionando (no rompemos consumers) ──────────


def test_normal_audit_still_used_for_successful_flows():
    """`audit_durably` es para rejection paths. Los flujos exitosos
    (commiteables con la transacción del request) deben seguir usando
    `audit(conn, ...)` — más barato (sin acquire extra) y la transacción
    del request ya garantiza durabilidad."""
    routes_src = routes_aggregated_source()
    # El módulo sigue usando `await audit(` en muchos sitios (tests anteriores
    # como test_user_preferences_static.py los cuentan). Asegurarnos que
    # esa función no se borró por accidente.
    assert hasattr(audit_module, 'audit')
    # Y que routes.py sigue llamándola para los happy paths.
    assert 'await audit(' in routes_src
