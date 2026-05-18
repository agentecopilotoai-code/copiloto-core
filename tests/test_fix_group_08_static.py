"""Fix-group 08: BUG-058..BUG-062.

- BUG-058: VIGENTE. event_worker.process_once carecía de
  `FOR UPDATE SKIP LOCKED` → escalar horizontal duplicaba sends.
  Fix: wrappear el batch en transacción + `for update of e skip locked`.
- BUG-059: NOT-APPLICABLE — `short_circuit_triage` ya implementado en
  qualification_flow.py.
- BUG-060: NOT-APPLICABLE — `_list_questions` ya selecciona la columna
  `key` (línea 107).
- BUG-061: NOT-APPLICABLE — `tests/conftest_e2e.py` ya documenta que
  `service_catalog` no tiene columna `code` y trabaja-around.
- BUG-062: NOT-APPLICABLE — ninguna referencia a `AdminLayout` en tests/
  (UI-015 borró el archivo viejo).
"""
from __future__ import annotations

import inspect
import textwrap
from pathlib import Path

from app.workers import event_worker
from app.services import qualification_flow


CONFTEST_E2E = Path('tests/conftest_e2e.py')


# ───── BUG-058 — event_worker SKIP LOCKED ────────────────────────────────


def test_bug_058_process_once_holds_transaction_for_lock():
    """`process_once` debe envolver el SELECT en una transacción para que
    `FOR UPDATE SKIP LOCKED` retenga el lock hasta que la transacción cierre.
    """
    src = textwrap.dedent(inspect.getsource(event_worker.process_once))
    assert 'async with conn.transaction():' in src, (
        'BUG-058: `process_once` debe estar dentro de `async with '
        'conn.transaction()` — sin transacción, FOR UPDATE no aplica.'
    )


def test_bug_058_select_uses_for_update_skip_locked():
    """El SELECT que dequeue eventos debe usar `for update of e skip locked`
    para que dos workers concurrentes nunca dequeue las mismas filas.
    """
    src = textwrap.dedent(inspect.getsource(event_worker))
    assert 'for update of e skip locked' in src, (
        'BUG-058: regresión — el SELECT del event worker NO usa '
        '`FOR UPDATE OF e SKIP LOCKED`. Dos workers concurrentes vuelven '
        'a dequeue las mismas filas → WhatsApps duplicados.'
    )


# ───── BUG-059 — NOT-APPLICABLE (urgency triage) ─────────────────────────


def test_bug_059_urgency_short_circuit_implemented():
    src = textwrap.dedent(inspect.getsource(qualification_flow))
    assert 'short_circuit_triage' in src, (
        'BUG-059: regresión — `short_circuit_triage` desapareció. '
        'Urgency triage vuelve a esperar todas las preguntas → demora '
        'handoff de emergencias.'
    )


# ───── BUG-060 — NOT-APPLICABLE (key in select) ──────────────────────────


def test_bug_060_list_questions_selects_key_column():
    src = textwrap.dedent(inspect.getsource(qualification_flow._list_questions))
    # El SELECT debe incluir la columna `key`.
    assert ' key' in src or ', key' in src or 'preset, key' in src, (
        'BUG-060: regresión — `_list_questions` ya no selecciona `key`. '
        'Las reglas `applies_when` vuelven a fallar por keys faltantes.'
    )


# ───── BUG-061 — NOT-APPLICABLE (service_catalog.code documented) ───────


def test_bug_061_conftest_e2e_documents_no_code_column():
    src = CONFTEST_E2E.read_text()
    assert "service_catalog` doesn't have a `code` column" in src, (
        'BUG-061: regresión — el comentario que documenta el workaround '
        'desapareció. Si alguien re-introduce el insert con `code`, el '
        'suite E2E vuelve a fallar con UndefinedColumn.'
    )


# ───── BUG-062 — NOT-APPLICABLE (AdminLayout removido) ──────────────────


def test_bug_062_no_admin_layout_references_in_tests():
    """`AdminLayout` fue borrado por UI-015. Si vuelve a referenciarse en
    tests, marca un regression hacia el monolito viejo.

    Excluimos este file de la búsqueda — la docstring menciona el componente
    como anchor del comentario, no como uso real.
    """
    test_dir = Path('tests')
    self_path = Path(__file__).resolve()
    for path in test_dir.rglob('*.py'):
        if path.resolve() == self_path:
            continue
        content = path.read_text()
        assert 'AdminLayout' not in content, (
            f'BUG-062: regresión — {path} referencia `AdminLayout` (borrado '
            'por UI-015). Reabrir solo si el componente vuelve.'
        )
