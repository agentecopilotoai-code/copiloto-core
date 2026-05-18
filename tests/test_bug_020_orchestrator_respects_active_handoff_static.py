"""BUG-020 CRITICAL — el bot debe silenciarse mientras un agente humano
está activo en la conversación.

Síntoma observado en runtime (2026-05-17 23:41:29):
  1. Contact pide "agente" → orchestrator → handoff (risk_keyword).
  2. Agente acepta handoff → conversation.status='human_active'. ✓
  3. Agente envía mensaje vía POST /v1/conversations/{id}/messages →
     el handler flipea unconditionally status='waiting_user'.
  4. Contact responde → orchestrator recibe el mensaje.
  5. orchestrator chequea `if status == 'human_active'` → False
     (porque ahora es 'waiting_user') → continue_bot → BOT RESPONDE
     PISANDO AL AGENTE HUMANO.

Root cause: dos bugs simultáneos:
  - POST /messages flipea status=waiting_user sin chequear si hay un
    agente activo.
  - orchestrator solo skipea con status='human_active', no con
    "handoff.status='accepted' AND assigned_to no-null".

Fix (defense en profundidad):
  1. POST /messages: si hay handoff con status='accepted' + assigned_to,
     mantener status='human_active' (no flipear a waiting_user).
  2. orchestrator: agregar check adicional ANTES de evaluar policy —
     si hay handoff accepted + assigned_to, skip con reason
     'active_human_handoff', sin importar conversation.status.

Si cualquiera de los dos checks regresa, el bot vuelve a pisar al
agente. Estos tests defienden ambos invariantes.
"""
from __future__ import annotations

import inspect
import textwrap
from pathlib import Path

from app.services import rag_orchestrator

ROUTES_PATH = Path('app/api/v1/routes.py')


def _orchestrator_source() -> str:
    """Source del entry point del orchestrator (_orchestrate_inbound_message_impl)."""
    func = getattr(rag_orchestrator, '_orchestrate_inbound_message_impl', None)
    if func is None:
        # Algunos refactors lo llaman distinto — buscamos cualquier impl que
        # tenga el patrón de los early checks.
        for name in dir(rag_orchestrator):
            obj = getattr(rag_orchestrator, name)
            if callable(obj) and 'orchestrate_inbound' in name:
                func = obj
                break
    assert func is not None, 'No se encontró el entry point del orchestrator'
    return textwrap.dedent(inspect.getsource(func))


# ───── Fix 1: POST /messages chequea handoff activo antes de flipear status ─


def test_routes_create_message_checks_active_human_handoff_before_status_flip():
    """El handler POST /v1/conversations/{id}/messages NO debe flipear
    status='waiting_user' unconditionally — debe primero chequear si hay
    un handoff con status='accepted' y assigned_to no-null.
    """
    src = ROUTES_PATH.read_text()
    # Buscamos el handler `create_message` y verificamos que tenga el query
    # de handoffs antes del UPDATE de conversations.
    create_msg_pos = src.find("@tenant_ops_router.post('/conversations/{conversation_id}/messages'")
    assert create_msg_pos > 0, 'no se encontró el handler create_message'
    # Tomamos el bloque hasta el próximo handler (siguiente @decorator).
    next_handler_pos = src.find('@tenant_ops_router', create_msg_pos + 50)
    block = src[create_msg_pos:next_handler_pos] if next_handler_pos > 0 else src[create_msg_pos:]

    # Patron del fix: select de handoffs ANTES del update de conversations.
    # Aceptamos cualquier variante razonable del query.
    handoff_check_idx = block.find("from app.handoffs")
    assert handoff_check_idx > 0, (
        'BUG-020 regression: create_message no chequea app.handoffs antes de '
        "flipear conversation.status='waiting_user'. Sin el chequeo, cualquier "
        'mensaje del agente humano hace que el bot vuelva a entrar en el '
        'próximo mensaje del usuario, pisando al agente.'
    )

    # El select debe filtrar por status='accepted' AND assigned_to not null
    # (signal de "agente activo en la conversación").
    assert "status='accepted'" in block, (
        "El check de handoff activo debe filtrar status='accepted'"
    )
    assert "assigned_to is not null" in block, (
        'El check debe exigir assigned_to no-null (agente concreto asignado)'
    )

    # El check DEBE preceder al UPDATE de status.
    status_update_idx = block.find("update app.conversations set status=")
    assert status_update_idx > handoff_check_idx, (
        'El UPDATE de status debe ir DESPUÉS del check de handoff activo.'
    )


def test_routes_create_message_keeps_human_active_when_agent_assigned():
    """Cuando hay handoff activo, el handler debe setear status='human_active'
    (no 'waiting_user'). 'human_active' es el status que el orchestrator
    skipea por el check de línea ~250."""
    src = ROUTES_PATH.read_text()
    create_msg_pos = src.find("@tenant_ops_router.post('/conversations/{conversation_id}/messages'")
    next_handler_pos = src.find('@tenant_ops_router', create_msg_pos + 50)
    block = src[create_msg_pos:next_handler_pos] if next_handler_pos > 0 else src[create_msg_pos:]
    # El path "agente activo" hace update status='human_active'.
    assert "status='human_active'" in block, (
        "El path 'hay handoff activo' debe setear status='human_active' "
        "(que el orchestrator ya skipea). Sin esto, el status queda en algo "
        "que el orchestrator interpreta como 'flow normal del bot'."
    )


# ───── Fix 2: orchestrator skipea si handoff activo (defense en profundidad) ─


def test_orchestrator_skips_when_active_human_handoff_exists():
    """El orchestrator DEBE skipear si hay un handoff con status='accepted'
    y assigned_to no-null, sin importar conversation.status. Esto cierra el
    gap exacto del bug observado en runtime: aunque el endpoint /messages
    tuviera un bug y flipeara mal el status, el orchestrator NUNCA debe
    pisar al agente humano.
    """
    src = _orchestrator_source()
    # El check debe consultar app.handoffs con status='accepted' AND assigned_to.
    assert "from app.handoffs" in src, (
        "BUG-020 regression: el orchestrator no consulta app.handoffs para "
        "validar si hay agente humano activo."
    )
    assert "status='accepted'" in src, (
        "El check del orchestrator debe filtrar handoff.status='accepted'"
    )
    assert "assigned_to is not null" in src, (
        "El check del orchestrator debe exigir assigned_to no-null"
    )
    # Y debe terminar en un return con reason 'active_human_handoff'.
    assert "'active_human_handoff'" in src, (
        "El skip debe usar reason='active_human_handoff' para que el log "
        "permita distinguir este caso de los otros skips (waiting_agent_handoff_pending, "
        "non_text_message, human_active, etc.)."
    )


def test_orchestrator_handoff_check_runs_before_policy_evaluation():
    """El check de handoff activo debe correr ANTES de cargar settings y de
    evaluar policy. Sino, gastamos tiempo de LLM (intent_classifier) +
    queries de RAG para terminar respondiendo cuando ya no debemos.
    """
    src = _orchestrator_source()
    handoff_check_idx = src.find("'active_human_handoff'")
    # El intent classifier corre via `classify_intent` o similar.
    policy_idx = src.find('policy_evaluated')
    settings_load_idx = src.find('settings_loaded')

    assert handoff_check_idx > 0
    if policy_idx > 0:
        assert handoff_check_idx < policy_idx, (
            'El skip de handoff debe correr ANTES de policy_evaluated — sino '
            'pagamos el LLM call del intent classifier para nada.'
        )
    if settings_load_idx > 0:
        assert handoff_check_idx < settings_load_idx, (
            'El skip debe correr ANTES de settings_loaded (early return).'
        )


def test_orchestrator_logs_handoff_id_in_skip_for_observability():
    """Cuando se skipea por handoff activo, el log debe incluir el handoff_id
    para que el operador pueda correlar con app.handoffs y saber qué agente
    está atendiendo."""
    src = _orchestrator_source()
    # Buscamos el bloque del log.info que reporta el skip por
    # active_human_handoff.
    skip_block_idx = src.find("'active_human_handoff'")
    assert skip_block_idx > 0
    # Ventana de ~600 chars alrededor del log para revisar kwargs.
    window_start = max(0, skip_block_idx - 600)
    window_end = min(len(src), skip_block_idx + 600)
    window = src[window_start:window_end]
    assert 'handoff_id' in window, (
        'El log de skip debe incluir handoff_id para observabilidad.'
    )
