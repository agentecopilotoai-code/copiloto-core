"""BUG-010 — `audit_durably` debe setear `app.tenant_id` en la connection
auxiliar antes del INSERT, sino la RLS policy `audit_logs_tenant_insert`
rechaza el INSERT con `InsufficientPrivilegeError` para cualquier audit
con `tenant_id != NULL`.

Síntoma observado en producción local (2026-05-17, runtime log):

    audit_durably failed (action=support_mode.activated entity=tenant/11111... \
        tenant=11111...) — request continues
    asyncpg.exceptions.InsufficientPrivilegeError: new row violates row-level
    security policy for table "audit_logs"

El handler `POST /v1/me/support-mode/{tenant_id}` retornó 201 (success) al
caller pero el audit log NUNCA se persistió — el peor caso para una acción
privilegiada (cross-tenant access del platform_owner). Sin audit durable,
no hay trail forense de quién activó support mode contra qué tenant cuándo.

Root cause: `audit_durably` (en `app/services/audit.py`) hacía
`db.pool.acquire()` para obtener una connection fresca (objetivo: que el
INSERT sobreviva al ROLLBACK del transaction context del request), PERO
nunca seteaba `app.tenant_id` en esa connection. Por eso:

- Policy `audit_logs_tenant_insert`:
    `tenant_id = app.current_tenant_id() OR app.support_mode()`
  Ambos lados son NULL/false en conn fresca → policy NO matchea cuando
  el INSERT pasa `tenant_id != NULL`.
- Policy `audit_logs_user_scope_insert`:
    `tenant_id IS NULL AND app.current_tenant_id() IS NULL`
  Solo matchea cuando ambos lados son NULL → falla para audits con
  tenant != NULL.

Fix: `audit_durably` ahora ejecuta `select set_config('app.tenant_id', $1, false)`
antes del INSERT. Cuando `tenant_id IS NULL`, setea string vacío
(reset defensive — asyncpg pool no garantiza fresh state per checkout).

Estos tests defienden el fix:
1. AST anchor del helper (firma, set_config call, orden).
2. Test dinámico con mock connection que registra las llamadas y verifica
   que set_config ocurre ANTES del INSERT con el tenant_id correcto.
3. Test dinámico para audit con tenant_id=None: set_config se llama con ''
   (no se omite — defensive reset).
"""
from __future__ import annotations

import asyncio
import inspect
import textwrap
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

from app.services import audit as audit_module


AUDIT = Path('app/services/audit.py')


def _handler_source(name: str) -> str:
    return textwrap.dedent(inspect.getsource(getattr(audit_module, name)))


# ───── AST: el fix está presente y ordenado ──────────────────────────────


def test_audit_durably_calls_set_config_before_insert():
    """El SET tiene que venir ANTES del INSERT. Si alguien refactoriza y
    los reordena, el INSERT vuelve a violar RLS."""
    src = _handler_source('audit_durably')
    set_pos = src.find("set_config('app.tenant_id'")
    insert_pos = src.find('insert into app.audit_logs')
    assert set_pos > 0, (
        'audit_durably no llama set_config(app.tenant_id, ...) — sin el SET, '
        'cualquier audit con tenant_id != NULL viola RLS '
        '(audit_logs_tenant_insert).'
    )
    assert insert_pos > 0
    assert set_pos < insert_pos, (
        'set_config DEBE ejecutarse ANTES del INSERT — sino la conn ya tiene '
        'el SQL pendiente sin el contexto RLS apropiado.'
    )


def test_audit_durably_set_config_uses_local_scope():
    """El tercer parámetro de `set_config(..., false)` define el scope: false
    = session-local (vive hasta el end-of-session). El pool reusa connections
    así que necesitamos al menos session scope; transaction scope (true)
    moriría al fin del statement implícito de `set_config` y no estaría
    para el INSERT siguiente."""
    src = _handler_source('audit_durably')
    assert "set_config('app.tenant_id', $1, false)" in src, (
        'set_config debe usar false (session scope) — true (transaction scope) '
        'no sobrevive entre statements en autocommit mode.'
    )


def test_audit_durably_handles_null_tenant_with_empty_string():
    """Cuando tenant_id es None, set_config recibe '' (no se omite). Esto
    es defense: si la conn del pool reciclara una con app.tenant_id
    seteado de un audit anterior, el siguiente audit user-scope necesitaría
    que tenga vacío para matchear policy audit_logs_user_scope_insert
    (`app.current_tenant_id() IS NULL`)."""
    src = _handler_source('audit_durably')
    # El patrón típico: `str(tenant_id) if tenant_id is not None else ''`
    # o equivalente.
    assert "''" in src, (
        'audit_durably no maneja explícitamente tenant_id=None — riesgo de '
        'leak de tenant entre audits si el pool recicla la connection.'
    )


def test_audit_durably_set_config_runs_inside_pool_acquire():
    """El set_config tiene que ejecutarse en la MISMA conn auxiliar que el
    INSERT — sino el INSERT corre en otra conn sin el contexto."""
    src = _handler_source('audit_durably')
    acquire_pos = src.find('db.pool.acquire()')
    set_pos = src.find("set_config('app.tenant_id'")
    assert acquire_pos > 0 and set_pos > acquire_pos, (
        'set_config debe estar DENTRO del `async with db.pool.acquire()` '
        'block para ejecutarse en la misma connection auxiliar.'
    )


# ───── Dinámico: mock connection registra orden de calls ─────────────────


class _RecordingConn:
    """Mock asyncpg connection que registra todas las llamadas a `execute`
    en orden, para verificar que set_config viene antes del INSERT."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []

    async def execute(self, query: str, *args) -> None:
        self.calls.append((query, args))


class _FakePool:
    def __init__(self, conn: _RecordingConn) -> None:
        self._conn = conn

    def acquire(self):
        conn = self._conn

        @asynccontextmanager
        async def _cm():
            yield conn

        return _cm()


def test_audit_durably_sets_tenant_then_inserts_with_real_uuid():
    """End-to-end con un mock connection: cuando tenant_id es un UUID real,
    set_config recibe el string del UUID, y el INSERT subsequente recibe
    el UUID original (no string)."""
    conn = _RecordingConn()
    fake_pool = _FakePool(conn)
    fake_db = MagicMock()
    fake_db.pool = fake_pool
    tenant_uuid = uuid4()

    with patch.object(audit_module, 'audit_durably', wraps=audit_module.audit_durably):
        with patch('app.db.pool.db', fake_db):
            asyncio.run(
                audit_module.audit_durably(
                    tenant_id=tenant_uuid,
                    actor_type='user',
                    actor_id='u-platform',
                    action='support_mode.activated',
                    entity_type='tenant',
                    entity_id=str(tenant_uuid),
                    metadata={'ttl_seconds': 3600},
                )
            )

    assert len(conn.calls) == 2, (
        f'audit_durably debe hacer 2 calls (set_config + INSERT); hizo {len(conn.calls)}'
    )
    # Primera call: set_config con el UUID como STRING.
    set_query, set_args = conn.calls[0]
    assert "set_config('app.tenant_id'" in set_query
    assert set_args[0] == str(tenant_uuid), (
        f'set_config debe recibir el UUID como string, no {type(set_args[0])}'
    )
    # Segunda call: INSERT con el UUID nativo (asyncpg lo serializa).
    insert_query, insert_args = conn.calls[1]
    assert 'insert into app.audit_logs' in insert_query
    assert insert_args[0] == tenant_uuid, (
        'El INSERT debe recibir el UUID nativo (no string) — asyncpg maneja '
        'la coerción para que el tipo postgres uuid matchee.'
    )


def test_audit_durably_with_null_tenant_passes_empty_string_to_set_config():
    """El path user-scope (audit sin tenant): set_config debe recibir ''
    para resetear el setting si la conn fue reusada del pool."""
    conn = _RecordingConn()
    fake_pool = _FakePool(conn)
    fake_db = MagicMock()
    fake_db.pool = fake_pool

    with patch('app.db.pool.db', fake_db):
        asyncio.run(
            audit_module.audit_durably(
                tenant_id=None,
                actor_type='public',
                actor_id=None,
                action='webhook.whatsapp_rejected',
                entity_type='webhook',
                entity_id=None,
                metadata={'reason': 'invalid_signature'},
            )
        )

    assert len(conn.calls) == 2
    set_query, set_args = conn.calls[0]
    assert "set_config('app.tenant_id'" in set_query
    assert set_args[0] == '', (
        f'set_config con tenant_id=None debe pasar string vacío, recibió {set_args[0]!r}'
    )
    insert_query, insert_args = conn.calls[1]
    assert 'insert into app.audit_logs' in insert_query
    assert insert_args[0] is None  # tenant_id se pasa al INSERT como None tal cual


def test_audit_durably_skips_silently_when_pool_uninitialized():
    """Comportamiento previo preservado: si db.pool es None, log warning
    y return sin raise."""
    fake_db = MagicMock()
    fake_db.pool = None

    with patch('app.db.pool.db', fake_db):
        # No raise.
        asyncio.run(
            audit_module.audit_durably(
                tenant_id=None,
                actor_type='user',
                actor_id='u',
                action='test',
                entity_type='test',
                entity_id=None,
            )
        )


def test_audit_durably_catches_set_config_failure_silently():
    """Best-effort: si set_config falla por cualquier razón (conn rota,
    nombre de setting cambió en una migration futura), el error se loguea
    pero el caller NO ve excepción.

    Verifica el contrato de docstring: "Best-effort por diseño". Es
    crítico — sino, audits durables podrían tumbar el handler que están
    auditando, defeating su propósito.
    """

    class _RaisingConn:
        async def execute(self, query: str, *args) -> None:
            raise RuntimeError('boom: set_config failed')

    fake_pool = _FakePool(_RaisingConn())
    fake_db = MagicMock()
    fake_db.pool = fake_pool

    with patch('app.db.pool.db', fake_db):
        # No raise — best-effort por diseño.
        asyncio.run(
            audit_module.audit_durably(
                tenant_id=uuid4(),
                actor_type='user',
                actor_id='u',
                action='support_mode.activated',
                entity_type='tenant',
                entity_id='t',
            )
        )


# ───── Anti-regression: la docstring explica el RLS context ──────────────


def test_audit_durably_docstring_mentions_rls_context_fix():
    """Si alguien borra el set_config pensando que es legacy, leer el
    docstring debe disuadir — explica explícitamente el bug que cierra."""
    doc = inspect.getdoc(audit_module.audit_durably) or ''
    assert 'RLS' in doc or 'rls' in doc or 'row-level security' in doc.lower(), (
        'docstring debe mencionar RLS para que el contexto del fix no se '
        'pierda en un refactor descuidado.'
    )
    assert 'app.tenant_id' in doc, (
        'docstring debe mencionar app.tenant_id para anclar el fix BUG-010.'
    )
