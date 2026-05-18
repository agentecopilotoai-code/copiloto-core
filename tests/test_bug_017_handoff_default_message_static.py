"""BUG-017 — el bot debe enviar un mensaje al usuario antes del handoff
incluso si el operador no configuró un `escalation_policy.handoff_message`
custom.

Síntoma observado en runtime (2026-05-17):
  Contact pregunta "Depilacion" (servicio NO en service_catalog del tenant).
  Bot intent_classifier marca `out_of_scope`. Después de ~8 turnos del bot
  intentando responder con RAG, el policy_engine dispara
  `action='require_handoff'` con `reason='max_bot_turns_exceeded:8/8'`.
  PERO `has_handoff_message=false` → el bot crea el handoff (la conversación
  cambia a `waiting_agent` server-side) PERO NO ENVÍA NADA al usuario.
  El cliente ve que el bot "dejó de responder" y asume que el sistema se
  rompió, lo que destruye la confianza y la conversion del lead.

Root cause:
  En `app/services/rag_orchestrator.py::_do_handoff`, el bloque de
  `if handoff_message_text.strip()` solo entraba si el tenant había
  configurado `escalation_policy.handoff_message` (jsonb del tenant_settings).
  La mayoría de los tenants nuevos NO tienen ese campo seteado, así que
  el handoff era silencioso.

Fix:
  Si `policy.get('handoff_message')` está vacío/missing, usar un mensaje
  default en español que avisa al usuario que se pasa a un agente humano.
  El operador puede sobrescribir per-tenant via PATCH /v1/tenants/{id}/settings
  actualizando `escalation_policy.handoff_message`. El audit metadata
  incluye `handoff_message_is_default` para que el operador identifique
  qué tenants se beneficiarían de un mensaje propio.

Defienden:
  - El default existe en el código.
  - Reemplaza el vacío.
  - El audit incluye el flag para observabilidad.
  - El custom del operador SIGUE teniendo prioridad (no regresión).
"""
from __future__ import annotations

import inspect
import textwrap
from pathlib import Path

from app.services import rag_orchestrator

ORCH_PATH = Path('app/services/rag_orchestrator.py')


def _do_handoff_source() -> str:
    """Source de `_do_handoff`. Definida como nested function en algunos
    branches; la buscamos en el módulo y si no, leemos del file source."""
    func = getattr(rag_orchestrator, '_do_handoff', None)
    if func is not None:
        return textwrap.dedent(inspect.getsource(func))
    # Fallback: leemos del file y extraemos el bloque manualmente.
    src = ORCH_PATH.read_text()
    start = src.find('async def _do_handoff(')
    if start < 0:
        start = src.find('def _do_handoff(')
    assert start >= 0, '_do_handoff no encontrada en rag_orchestrator.py'
    # Tomamos hasta la próxima función a nivel del mismo indent.
    end = src.find('\nasync def ', start + 10)
    end_def = src.find('\ndef ', start + 10)
    if end_def > 0 and (end < 0 or end_def < end):
        end = end_def
    return src[start:end] if end > 0 else src[start:]


# ───── Default message existe + se aplica cuando falta el custom ──────────


def test_default_handoff_message_constant_exists():
    """Anti-regression: el módulo debe tener un mensaje default declarado
    (no inline en cada callsite — single source of truth)."""
    src = ORCH_PATH.read_text()
    assert '_DEFAULT_HANDOFF_MESSAGE' in src, (
        'BUG-017 regression: el módulo no define _DEFAULT_HANDOFF_MESSAGE. '
        'Sin esa constante, el handoff silencioso vuelve.'
    )


def test_default_handoff_message_is_spanish_and_actionable():
    """El default debe estar en español (idioma del producto) y debe
    decirle al usuario QUÉ está pasando (que se pasa a un agente humano).
    Mensaje vago tipo "Espera por favor" no soluciona el bug original.
    """
    src = ORCH_PATH.read_text()
    # Localiza la constante.
    start = src.find('_DEFAULT_HANDOFF_MESSAGE')
    end = src.find(')', start)
    block = src[start:end + 1]
    # El default debe mencionar explícitamente que se pasa a humano.
    # Tokens razonables: "persona", "equipo", "agente", "alguien".
    has_human_signal = any(
        token in block.lower() for token in ('persona', 'equipo', 'agente', 'alguien')
    )
    assert has_human_signal, (
        'El default handoff_message debe decirle al usuario que se pasa a '
        'un humano. Mensajes vagos no resuelven el bug original (usuario '
        'piensa que el sistema se rompió).'
    )


def test_do_handoff_uses_default_when_policy_handoff_message_empty():
    """Patrón central del fix: si policy.handoff_message es vacío/missing,
    usar el default. ANTES había un `if handoff_message_text.strip()` solo,
    que silenciaba cuando policy.get devolvía None o ''."""
    src = _do_handoff_source()
    # El fix debe asignar el default cuando el policy.handoff_message vacío.
    # Patrón típico: `if not handoff_message_text.strip(): handoff_message_text = _DEFAULT_HANDOFF_MESSAGE`
    assert '_DEFAULT_HANDOFF_MESSAGE' in src, (
        '_do_handoff no referencia _DEFAULT_HANDOFF_MESSAGE — el default '
        'no se usa, el handoff sigue siendo silencioso.'
    )
    assert 'if not handoff_message_text.strip():' in src, (
        'El patrón de fallback (asignar default cuando string vacío) '
        'no está en _do_handoff. BUG-017 puede regresar.'
    )


def test_do_handoff_audit_includes_is_default_flag():
    """El audit metadata debe incluir `handoff_message_is_default` para
    que el operador identifique qué tenants se beneficiarían de un
    mensaje custom."""
    src = _do_handoff_source()
    assert "'handoff_message_is_default'" in src, (
        'El audit no incluye handoff_message_is_default — el operador no '
        'puede identificar qué tenants están usando el default vs custom.'
    )


def test_do_handoff_custom_policy_message_still_wins():
    """No regresión: el comportamiento existente (custom message del
    operador) sigue ganando sobre el default. El default SOLO aplica
    cuando policy.handoff_message está vacío."""
    src = _do_handoff_source()
    # Buscamos la línea de asignación inicial: `handoff_message_text = policy.get('handoff_message') or ''`
    # Eso garantiza que el custom se lee PRIMERO.
    assert "policy.get('handoff_message')" in src, (
        'El custom del operador (policy.handoff_message) ya no se lee. '
        'Eso rompería tenants que tienen mensajes propios.'
    )
    # Y el default se aplica solo después de un check de strip().
    custom_idx = src.find("policy.get('handoff_message')")
    default_idx = src.find('_DEFAULT_HANDOFF_MESSAGE')
    assert custom_idx > 0 and default_idx > custom_idx, (
        'El default debe aplicarse DESPUÉS de leer el custom — sino '
        'ganaría sobre el custom y se rompería la per-tenant config.'
    )


def test_default_handoff_message_explains_what_happens_next():
    """El mensaje debe dar contexto sobre el timing/expectativa. Cliente
    debe saber que tiene que ESPERAR (vs. asumir que ya no le responden)."""
    src = ORCH_PATH.read_text()
    start = src.find('_DEFAULT_HANDOFF_MESSAGE')
    end = src.find(')', start)
    block = src[start:end + 1].lower()
    # Tokens que comunican timing: "minutos", "pronto", "en unos", "responde".
    has_timing = any(
        token in block for token in ('minuto', 'pronto', 'en unos', 'responde', 'momento')
    )
    assert has_timing, (
        'El default no comunica timing/expectativa. Cliente puede asumir '
        'que el sistema se rompió y abandonar la conversación.'
    )
