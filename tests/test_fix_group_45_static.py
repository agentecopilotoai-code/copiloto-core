"""Fix-group 45: Codex Reviews follow-up sobre PRs antiguos (#16, #18, #19).

Reviews del bot Codex sobre PRs ya cerrados que quedaron sin atender porque
llegaron post-merge. Los 5 reviews detectados en PRs #16..#20:

- PR #16 (P2) → **BUG-233** — regex `TASK_CODE_RE` solo matcheaba con `(`
  antes; `"para medir TASK-0039"` pasaba. Fix: `\\b` word boundary +
  reescritura de 4 strings visibles que ahora violan.
- PR #17 (P1) — ya ADDRESSED por BUG-195 + BUG-228.
- PR #18 (P1) → **BUG-231** — `sign_export_bundle` firma `default=str`
  output mientras FastAPI serializa con ISO `T`. Cliente no podía verificar
  externamente. Fix: devolver el `data_canonical` (string crudo) firmado,
  además del `data` parseado.
- PR #19 (P2) → **BUG-232** — `acceptHandoff(id)` con targetId explícito
  caía al guard `if !selectedConversationId` en `runAction`. Fix: param
  `requireConversation=false` cuando el caller pasa un id explícito.
- PR #20 (P2) — docs cosmetic (UI_BACKLOG count drift); skip por scope.
"""
from __future__ import annotations

from pathlib import Path


ROUTES = Path('app/api/v1/routes.py')
INBOX_HOOK = Path('admin-panel/src/features/agente/inbox/hooks/useInboxData.js')
TASK_CODE_TEST = Path('admin-panel/src/__tests__/no-internal-refs-in-ui.test.js')


# ───── BUG-231 — export bundle signature matches what client receives ───


def test_bug_231_export_response_includes_data_canonical():
    src = ROUTES.read_text()
    fn_idx = src.find('async def export_contact_data(')
    assert fn_idx > 0, 'export_contact_data handler must exist'
    next_fn = src.find('\n# ─────', fn_idx)
    block = src[fn_idx:next_fn]
    assert "'data_canonical': bundle_canonical," in block, (
        'BUG-231: el response debe incluir `data_canonical` (string crudo) '
        'para que el cliente pueda verificar la firma sobre EXACTAMENTE los '
        'mismos bytes que el server firmó.'
    )
    assert "'signature': signature" in block, (
        'BUG-231: el response sigue incluyendo la firma.'
    )


# ───── BUG-232 — runAction honors explicit targetId ────────────────────


def test_bug_232_run_action_accepts_optional_conversation_guard():
    src = INBOX_HOOK.read_text()
    fn_idx = src.find('async function runAction(action, successText')
    assert fn_idx > 0
    next_fn = src.find('\n  async function handleStartConversation', fn_idx)
    block = src[fn_idx:next_fn]
    assert '{ requireConversation = true } = {}' in block, (
        'BUG-232: `runAction` debe aceptar el option `requireConversation` '
        '(default true para back-compat).'
    )
    assert 'if (requireConversation && !selectedConversationId) return;' in block, (
        'BUG-232: el guard original solo aplica cuando el caller no opta out.'
    )


def test_bug_232_accept_handoff_opts_out_of_conversation_guard():
    src = INBOX_HOOK.read_text()
    fn_idx = src.find('acceptHandoff: (conversationId) =>')
    assert fn_idx > 0
    block = src[fn_idx:fn_idx + 800]
    assert '{ requireConversation: false }' in block, (
        'BUG-232: `acceptHandoff` debe pasar `requireConversation: false` '
        'porque tiene un targetId explícito del card click.'
    )
    assert 'if (!targetId) return;' in block, (
        'BUG-232: el handler debe early-return si targetId quedó vacío.'
    )


# ───── BUG-233 — regex catches unparenthesized internal codes ──────────


def test_bug_233_task_code_regex_uses_word_boundary_not_paren():
    src = TASK_CODE_TEST.read_text()
    assert "const TASK_CODE_RE = /\\b(?:TASK|BUG|SEC|UI)-\\d+/i;" in src, (
        'BUG-233: el regex debe usar `\\b` (word boundary) en vez de `\\(` '
        'para catchear códigos sin paréntesis como `"para medir TASK-0039"`.'
    )
