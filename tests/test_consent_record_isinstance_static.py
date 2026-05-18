"""BUG-016 — defienden el fix de consent.py contra asyncpg.Record vs dict.

Síntoma observado en producción local (2026-05-17 22:50:24):
  - Contact envía "Hola buenas noches" (text) → orchestrator emite
    consent.request_sent + consent_gate (correcto).
  - Contact clickea "Acepto" (interactive button) → orchestrator vuelve a
    emitir consent.request_sent + consent_gate (¡bug!).
  - Cualquier mensaje subsiguiente — incluso texto libre como "Que servicios
    ofrecen?" — recibe el mismo consent_gate.
  - El consent_ledger nunca recibe el evento 'granted', el contact queda
    con opt_in='unknown' para siempre, el bot está bloqueado para esa
    conversación.

Root cause:
  En `app/services/consent.py::enforce_inbound_consent`, las extracciones
  usaban `isinstance(obj, dict)` como guard:

    opt_in = (contact.get('opt_in_status') if isinstance(contact, dict) else None) or 'unknown'
    inbound_payload = _parse_payload(inbound_message.get('payload') if isinstance(inbound_message, dict) else None)

  PERO los rows que llegan del webhook (`await conn.fetchrow(...)`) son
  instancias de `asyncpg.Record`, NO de `dict`. Desde asyncpg >= 0.21,
  `Record` ya no es subclass de `dict` — `isinstance(record, dict)` retorna
  False. Resultado:
    - opt_in caía siempre a 'unknown' (default) → el check
      `if opt_in == 'unknown'` mandaba consent_request en cada mensaje.
    - inbound_payload caía siempre a {} → interactive_id siempre None →
      los checks `if interactive_id == CONSENT_BUTTON_YES/NO` nunca
      matcheaban → el "Acepto" del usuario nunca se procesaba.

Fix:
  Nuevo helper `_record_get(obj, key, default=None)` que usa subscript +
  try/except para extraer valores de cualquier objeto subscriptable
  (dict, asyncpg.Record). Reemplaza los `isinstance(obj, dict)` guards.

Si alguien revierte el fix (vuelve a usar `isinstance(obj, dict)` sin
defense para Records), el bot se rompe silenciosamente — este suite
falla loudly para evitarlo.
"""
from __future__ import annotations

import inspect
import textwrap
from pathlib import Path

from app.services import consent as consent_module

CONSENT_PY = Path('app/services/consent.py')


def _module_source() -> str:
    return CONSENT_PY.read_text()


def _function_source(name: str) -> str:
    return textwrap.dedent(inspect.getsource(getattr(consent_module, name)))


# ───── Helper _record_get existe y funciona para ambos tipos ──────────────


def test_record_get_helper_exists():
    """El helper compartido debe existir y aceptar (obj, key, default)."""
    assert hasattr(consent_module, '_record_get')
    sig = inspect.signature(consent_module._record_get)
    assert 'obj' in sig.parameters
    assert 'key' in sig.parameters
    assert 'default' in sig.parameters


def test_record_get_works_for_dict():
    """Sanity: dict input devuelve el valor."""
    assert consent_module._record_get({'foo': 'bar'}, 'foo') == 'bar'
    assert consent_module._record_get({'foo': 'bar'}, 'missing') is None
    assert consent_module._record_get({'foo': 'bar'}, 'missing', 'def') == 'def'


def test_record_get_works_for_record_like_object():
    """Caso central: un objeto subscriptable que NO es dict debe funcionar
    igual. Simulamos asyncpg.Record con un wrapper que implementa __getitem__
    pero NO hereda de dict.
    """

    class FakeRecord:
        def __init__(self, data: dict) -> None:
            self._data = data

        def __getitem__(self, key: str):
            return self._data[key]

        def __contains__(self, key: str) -> bool:
            return key in self._data

    # Verificamos primero que NO es dict (sino el test no prueba nada).
    fake = FakeRecord({'opt_in_status': 'granted'})
    assert not isinstance(fake, dict)
    # Y _record_get extrae el valor igual.
    assert consent_module._record_get(fake, 'opt_in_status') == 'granted'
    assert consent_module._record_get(fake, 'missing') is None
    assert consent_module._record_get(fake, 'missing', 'fallback') == 'fallback'


def test_record_get_handles_none_object():
    """None debe devolver default sin crash."""
    assert consent_module._record_get(None, 'anything') is None
    assert consent_module._record_get(None, 'anything', 'def') == 'def'


# ───── enforce_inbound_consent usa _record_get, NO isinstance(dict) ───────


def test_enforce_inbound_consent_uses_record_get_for_contact():
    """El bug original era `isinstance(contact, dict)` que retornaba False
    para Records → opt_in siempre 'unknown'. El fix debe usar _record_get."""
    src = _function_source('enforce_inbound_consent')
    assert '_record_get(contact, ' in src, (
        'enforce_inbound_consent debe usar _record_get(contact, ...) para '
        'soportar asyncpg.Record. Sin esto, opt_in cae a "unknown" siempre '
        'y el consent gate nunca se levanta.'
    )


def test_enforce_inbound_consent_uses_record_get_for_inbound_message():
    """Mismo bug para `inbound_message`. El fix debe usar _record_get."""
    src = _function_source('enforce_inbound_consent')
    assert '_record_get(inbound_message, ' in src, (
        'enforce_inbound_consent debe usar _record_get(inbound_message, ...) '
        'para extraer el payload. Sin esto, interactive_id es siempre None y '
        'el "Acepto" del usuario nunca se detecta.'
    )


def test_enforce_inbound_consent_does_not_isinstance_dict_for_record_inputs():
    """Anti-regression hard: si alguien re-introduce
    `isinstance(contact, dict)` o `isinstance(inbound_message, dict)`, el bug
    regresa silenciosamente. El guard correcto es duck typing via
    _record_get."""
    src = _function_source('enforce_inbound_consent')
    forbidden_patterns = [
        'isinstance(contact, dict)',
        'isinstance(inbound_message, dict)',
    ]
    for pattern in forbidden_patterns:
        assert pattern not in src, (
            f'enforce_inbound_consent re-introduce `{pattern}` que rompe el '
            'consent flow para asyncpg.Record. Usar _record_get(...) en su lugar.'
        )


def test_record_consent_event_for_opt_out_keyword_uses_record_get():
    """Segundo sitio con el mismo bug: `record_consent_event_for_opt_out_keyword`
    extraía body_text con isinstance(dict). Si el caller es el webhook (Record),
    el body queda '' y el ledger pierde el texto exacto del cliente.
    """
    src = _module_source()
    # El módulo NO debe tener `inbound_message['body_text'] if isinstance(`
    assert "inbound_message['body_text'] if isinstance(" not in src, (
        'record_consent_event_for_opt_out_keyword sigue usando isinstance(dict) '
        'guard — el body se pierde para inputs Record.'
    )
    # El módulo debe usar _record_get(inbound_message, 'body_text') o equivalente.
    assert "_record_get(inbound_message, 'body_text')" in src


# ───── Documentación: el bug está anclado al ticket ──────────────────────


def test_consent_module_docstring_mentions_bug_016():
    """Anti-regression soft: el comentario del fix debe mencionar BUG-016
    para que un contribuidor futuro entienda por qué _record_get existe."""
    src = _module_source()
    assert 'BUG-016' in src, (
        'consent.py debe mencionar BUG-016 en el código (helper o callsite) '
        'para que un futuro PR no "limpie" _record_get pensando que es legacy.'
    )
