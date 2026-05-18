"""Fix-group 16: BUG-098..BUG-102.

- BUG-098: VIGENTE. `ViewerConversations` montaba `useViewerConversationsData`
  antes de `<RequirePermission>`. Fix: split en outer (gate) + Body.
- BUG-099: VIGENTE. `viewerAppointmentsData.STATUS_FILTER_OPTIONS` exponía
  `pending` y `canceled` (1L), valores que el backend no tiene. Fix:
  alineado al enum del schema (`scheduled/confirmed/completed/cancelled/no_show`).
- BUG-100: VIGENTE. `ContactProfile` montaba `useContactProfileData` antes
  de `<RequirePermission>`. Fix: split en outer + Body.
- BUG-101: NOT-APPLICABLE. `MyHandoffs.onTakeHandoff` ya llama
  `actions.acceptHandoff(id)` (línea 104).
- BUG-102: VIGENTE. `test_operations_desk_static._operations_desk_source()`
  usaba `rglob('*.js*')` que matchea `*.test.jsx` → static asserts podían
  pasar por strings que viven en tests, no en producción. Fix: filtrar
  `.test.` del rglob.
"""
from __future__ import annotations

from pathlib import Path


VIEWER_CONVERSATIONS = Path('admin-panel/src/features/viewer/conversations/ViewerConversations.jsx')
VIEWER_APPT_DATA = Path('admin-panel/src/features/viewer/appointments/viewerAppointmentsData.js')
CONTACT_PROFILE = Path('admin-panel/src/features/agente/contact-profile/ContactProfile.jsx')
MY_HANDOFFS = Path('admin-panel/src/features/agente/my-handoffs/MyHandoffs.jsx')
OPS_DESK_TEST = Path('tests/test_operations_desk_static.py')


# ───── BUG-098 — ViewerConversations split ──────────────────────────────


def test_bug_098_viewer_conversations_gates_before_data_hook():
    src = VIEWER_CONVERSATIONS.read_text()
    assert 'ViewerConversationsBody' in src, (
        'BUG-098: el split debe introducir `ViewerConversationsBody` para que '
        'el outer pueda gatear `<RequirePermission>` antes del hook.'
    )
    outer_idx = src.find('export function ViewerConversations(props)')
    body_idx = src.find('function ViewerConversationsBody(')
    assert outer_idx >= 0 and body_idx > outer_idx, (
        'BUG-098: el outer debe declararse antes del body.'
    )
    outer_block = src[outer_idx:body_idx]
    assert 'useViewerConversationsData' not in outer_block, (
        'BUG-098: el outer NO debe invocar `useViewerConversationsData` — el '
        'hook vive en el body para que el RequirePermission lo gatee.'
    )
    assert '<RequirePermission' in outer_block, (
        'BUG-098: el outer debe envolver el body en `<RequirePermission>`.'
    )


# ───── BUG-099 — appointment status alineado al schema ─────────────────


def test_bug_099_status_filter_options_match_schema_enum():
    src = VIEWER_APPT_DATA.read_text()
    # Las 5 opciones canónicas del schema.
    for value in ('scheduled', 'confirmed', 'completed', 'cancelled', 'no_show'):
        assert f"value: '{value}'" in src, (
            f'BUG-099: STATUS_FILTER_OPTIONS debe incluir `{value}` (enum del schema).'
        )
    # Los valores incorrectos NO deben aparecer.
    for forbidden in ("value: 'pending'", "value: 'canceled'"):
        assert forbidden not in src, (
            f'BUG-099: regresión — el valor inválido `{forbidden}` reaparece. '
            'El backend NO acepta esos enum values.'
        )


# ───── BUG-100 — ContactProfile split ──────────────────────────────────


def test_bug_100_contact_profile_gates_before_data_hook():
    src = CONTACT_PROFILE.read_text()
    assert 'ContactProfileBody' in src, (
        'BUG-100: split debe introducir `ContactProfileBody`.'
    )
    outer_idx = src.find('export function ContactProfile()')
    body_idx = src.find('function ContactProfileBody(')
    assert outer_idx >= 0 and body_idx > outer_idx
    outer_block = src[outer_idx:body_idx]
    assert 'useContactProfileData' not in outer_block, (
        'BUG-100: el outer NO debe invocar `useContactProfileData` antes del gate.'
    )
    assert '<RequirePermission' in outer_block, (
        'BUG-100: el outer debe envolver el body en `<RequirePermission>`.'
    )


# ───── BUG-101 — NOT-APPLICABLE (Take ya llama acceptHandoff) ──────────


def test_bug_101_my_handoffs_take_calls_accept_handoff():
    src = MY_HANDOFFS.read_text()
    assert 'actions.acceptHandoff(id)' in src, (
        'BUG-101: regresión — el handler `onTakeHandoff` ya no llama '
        '`actions.acceptHandoff(id)`. El click en "Tomar" vuelve a ser '
        'puramente cosmético (no acepta el handoff).'
    )


# ───── BUG-102 — Operations Desk static excluye tests ──────────────────


def test_bug_102_operations_desk_source_excludes_test_files():
    src = OPS_DESK_TEST.read_text()
    assert "'.test.' not in p.name" in src, (
        'BUG-102: regresión — `_operations_desk_source()` ya no filtra '
        'test files; static asserts pueden pasar por strings que viven '
        'en `*.test.jsx` y no en producción.'
    )


def test_bug_102_static_check_uses_filtered_helper():
    """Smoke-test del helper: importarlo y verificar que NO incluye contenido
    de tests fixtures (ej. el string `'mock data'` o `'expect('` que serían
    típicos del test runner).
    """
    import importlib  # noqa: PLC0415
    mod = importlib.import_module('tests.test_operations_desk_static')
    helper = getattr(mod, '_operations_desk_source')
    source = helper()
    # Los archivos de test típicamente importan vitest:
    assert "from 'vitest'" not in source, (
        "BUG-102: regresión — el helper sigue incluyendo test files (encontró "
        "`from 'vitest'` en el output, que solo aparece en .test.jsx)."
    )
    assert source, 'BUG-102: el helper no debe devolver string vacío después del filter.'
