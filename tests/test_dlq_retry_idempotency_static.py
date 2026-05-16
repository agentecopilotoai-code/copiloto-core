"""SEC-010 (DLQ retry idempotency) — defienden los invariantes del fix.

Antes del fix:
  - `outbound_dlq.requeue_message` hacía `SELECT status` → `UPDATE` no atómico
    → `INSERT INTO domain_events` con `idempotency_key = f'message-retry:{id}:{uuid4().hex}'`.
  - Dos requeues concurrentes del mismo mensaje (operator dobleclickea, bulk
    + manual race) ambos pasaban el `if status == 'queued'` early-return,
    ambos hacían UPDATE no-condicional, y ambos insertaban domain events
    con KEYS DIFERENTES (uuid4 random) → 2 eventos emitidos para 1 retry.
  - El worker entonces procesaba el mismo mensaje 2 veces.

Después del fix:
  1. UPDATE...WHERE status='failed' RETURNING retry_count: atómico — solo el
     winner del race transiciona; el loser obtiene `None` y reporta
     `already_queued` sin emitir evento.
  2. `idempotency_key = f'message-retry:{message_id}:{retry_count}'`:
     stable — un replay de la misma operación administrativa con el mismo
     retry_count produce la misma key y deduplicada via
     `on conflict (tenant_id, idempotency_key) do nothing`.
  3. Schema: `app.messages.retry_count integer not null default 0`.

Si alguno de estos invariantes se rompe, el bug regresa silenciosamente.
"""
from __future__ import annotations

import ast
import inspect
import textwrap
from pathlib import Path

from app.services import outbound_dlq

SCHEMA = Path('infra/postgres/01-schema.sql')
DLQ_MODULE = Path('app/services/outbound_dlq.py')


def _handler_source(name: str) -> str:
    return textwrap.dedent(inspect.getsource(getattr(outbound_dlq, name)))


# ───── Schema: retry_count en app.messages ───────────────────────────────


def test_messages_table_has_retry_count_column():
    """SEC-010 — el stable idempotency_key depende de un contador estable en
    la fila. Si la columna no existe, el helper crashearía en runtime."""
    schema = SCHEMA.read_text()
    # Busca el bloque `create table app.messages (` y verifica que dentro está
    # la declaración de retry_count antes del cierre del paréntesis.
    start = schema.find('create table app.messages (')
    assert start > 0, 'no se encontró `create table app.messages`'
    end = schema.find(');', start)
    table_block = schema[start:end]
    assert 'retry_count integer not null default 0' in table_block, (
        'app.messages.retry_count column missing — SEC-010 fix regresará'
    )


def test_schema_comments_link_retry_count_to_sec_010():
    """Sin el comentario, un futuro PR podría borrar la columna pensando que
    es legacy. El marcador ancla el invariante al ticket SEC-010."""
    schema = SCHEMA.read_text()
    start = schema.find('create table app.messages (')
    end = schema.find(');', start)
    table_block = schema[start:end]
    assert 'SEC-010' in table_block
    assert 'idempotency' in table_block.lower()


# ───── requeue_message: atomic UPDATE + stable key ────────────────────────


def test_requeue_message_does_not_import_uuid4():
    """Antes: `from uuid import UUID, uuid4`. Después: solo UUID. Si uuid4
    re-aparece, alguien está volviendo al patrón viejo de key aleatoria."""
    src = DLQ_MODULE.read_text()
    # `uuid4` no debe aparecer en imports ni en cuerpo del módulo.
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == 'uuid':
            imported = {alias.name for alias in node.names}
            assert 'uuid4' not in imported, (
                'outbound_dlq imports uuid4 — SEC-010 fix usa retry_count estable, '
                'uuid4 reintroduciría keys random.'
            )
        if isinstance(node, ast.Name) and node.id == 'uuid4':
            # `uuid4` no debe usarse en ninguna parte del módulo.
            raise AssertionError(
                'outbound_dlq referencia `uuid4` — SEC-010 fix prohibe keys random.'
            )


def test_requeue_message_uses_atomic_update_with_where_failed():
    """El UPDATE debe filtrar por `status='failed'` Y devolver `retry_count`.
    Sin el filtro, dos concurrencias ambas UPDATE-ean (no-op para el segundo
    pero el INSERT del domain event corre igual)."""
    src = _handler_source('requeue_message')
    # Atomic transition + RETURNING.
    assert "status='failed'" in src
    assert 'returning retry_count' in src
    # El UPDATE debe incrementar retry_count atomicamente, no en un segundo
    # round-trip que crearía otra ventana de race.
    assert 'retry_count = retry_count + 1' in src


def test_requeue_message_idempotency_key_is_stable_not_random():
    """La key debe construirse SOLO con (message_id, retry_count). Si aparece
    `uuid`, `random`, `time.time`, `epoch`, o `.hex` en la construcción de
    la key, el bug regresó."""
    src = _handler_source('requeue_message')
    # Patrón estable correcto.
    assert "f'message-retry:{message_id}:{retry_count}'" in src
    # Patrones prohibidos (anti-regression).
    forbidden_substrings = [
        'uuid4()',
        '.hex',
        'time.time()',
        'epoch',
        'datetime.now',
    ]
    # Busca solo en la línea de construcción de `idem`, para no falsos-positivos
    # con logs/comentarios que mencionan los términos.
    for line in src.splitlines():
        stripped = line.strip()
        if stripped.startswith('idem ='):
            for forbidden in forbidden_substrings:
                assert forbidden not in stripped, (
                    f'idem key contains forbidden token `{forbidden}` — '
                    'SEC-010 requires stable (message_id, retry_count) key.'
                )


def test_requeue_message_does_not_collide_raise_on_conflict():
    """Antes del fix: `raise RuntimeError('requeue_event_collision')` cuando
    `on conflict do nothing` no devolvía id. Eso rompía idempotencia desde
    la perspectiva del caller (replay legítimo → error). Ahora debe loguear
    y reportar éxito con marker `event_replayed=True`."""
    src = _handler_source('requeue_message')
    assert "raise RuntimeError('requeue_event_collision')" not in src
    assert "raise RuntimeError(\"requeue_event_collision\")" not in src
    # El log informativo del replay debe existir.
    assert "'outbound_dlq.requeue_event_already_emitted'" in src
    assert "'event_replayed': True" in src


def test_requeue_message_returns_retry_count_in_result():
    """Para que el frontend pueda mostrar 'Reintento #N' y para que la
    auditoría operacional pueda correlar el resultado con el domain event."""
    src = _handler_source('requeue_message')
    assert "'retry_count': retry_count" in src


def test_requeue_message_payload_includes_retry_count_for_consumers():
    """El payload del domain event debe llevar retry_count para que el worker
    pueda loguearlo y métricas puedan agruparlo."""
    src = _handler_source('requeue_message')
    assert "'retry_count': retry_count" in src
    # El payload es un dict pasado a json.dumps.
    assert 'json.dumps(' in src


# ───── No regression del bulk handler ────────────────────────────────────


def test_requeue_tenant_dlq_still_delegates_to_requeue_message():
    """El bulk handler debe seguir invocando requeue_message en loop — la
    nueva semántica de idempotencia se hereda gratis."""
    src = _handler_source('requeue_tenant_dlq')
    assert 'await requeue_message(' in src
    # Pasa los kwargs correctos.
    assert 'tenant_id=tenant_id' in src
    assert 'message_id=message_id' in src


# ───── SELECT inicial trae retry_count (necesario para el guard temprano) ─


def test_initial_select_fetches_retry_count():
    """El SELECT antes del UPDATE debe traer retry_count para que el path
    `not_outbound` / `invalid_status` no haga round-trip extra después."""
    src = _handler_source('requeue_message')
    assert 'select id, status, direction, retry_count' in src
