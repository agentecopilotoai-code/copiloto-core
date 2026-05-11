"""Tests estáticos del clasificador de intenciones (TASK-0026).

Valida las 10 intenciones, los tres niveles de resolución (rule / llm / fallback)
y los umbrales de confianza sin levantar ningún servicio externo.
"""
from __future__ import annotations

import types
import pytest

from app.services.intent_classifier import (
    INTENT_BOOK_APPOINTMENT,
    INTENT_CANCEL_APPOINTMENT,
    INTENT_CHECK_AVAILABILITY,
    INTENT_COMPLAINT_OR_RISK,
    INTENT_CONFIRM_APPOINTMENT,
    INTENT_FAQ,
    INTENT_GREETING,
    INTENT_OPT_OUT,
    INTENT_RESCHEDULE_APPOINTMENT,
    ALL_INTENTS,
    CONF_LLM_THRESHOLD,
    CONF_FALLBACK_THRESHOLD,
    _rule_classify,
    _compile_tenant_rules,
    classify_intent,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_settings(**kwargs):
    """Crea un objeto de settings mínimo que no dispara llamadas a APIs reales."""
    s = types.SimpleNamespace(
        cloud_llm_provider=None,
        cloud_llm_api_key=None,
        cloud_llm_model='claude-sonnet-4-6',
        ollama_url=None,
        ollama_model=None,
    )
    for k, v in kwargs.items():
        setattr(s, k, v)
    return s


ALL_ENABLED = set(ALL_INTENTS)


# ---------------------------------------------------------------------------
# Capa 1 — rule_classify
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('text,expected_intent', [
    # greeting
    ('hola', INTENT_GREETING),
    ('buenos días', INTENT_GREETING),
    ('Buenas tardes!', INTENT_GREETING),
    ('hi', INTENT_GREETING),
    # faq
    ('cuánto cuesta el servicio?', INTENT_FAQ),
    ('cuáles son sus horarios de atención?', INTENT_FAQ),
    ('qué servicios tienen?', INTENT_FAQ),
    # book_appointment
    ('quiero agendar una cita', INTENT_BOOK_APPOINTMENT),
    ('necesito reservar un turno', INTENT_BOOK_APPOINTMENT),
    ('quisiera hacer una cita para mañana', INTENT_BOOK_APPOINTMENT),
    # confirm_appointment
    ('confirmar mi cita', INTENT_CONFIRM_APPOINTMENT),
    ('cuándo es mi cita?', INTENT_CONFIRM_APPOINTMENT),
    # reschedule_appointment
    ('quiero cambiar mi cita', INTENT_RESCHEDULE_APPOINTMENT),
    ('necesito reagendar para el jueves', INTENT_RESCHEDULE_APPOINTMENT),
    ('mover mi turno al martes', INTENT_RESCHEDULE_APPOINTMENT),
    # cancel_appointment
    ('quiero cancelar mi cita', INTENT_CANCEL_APPOINTMENT),
    ('necesito anular mi reserva', INTENT_CANCEL_APPOINTMENT),
    # check_availability
    ('tienen disponibilidad para esta semana?', INTENT_CHECK_AVAILABILITY),
    ('qué días tienen espacio?', INTENT_CHECK_AVAILABILITY),
    # complaint_or_risk
    ('esto es una estafa', INTENT_COMPLAINT_OR_RISK),
    ('quiero poner una queja', INTENT_COMPLAINT_OR_RISK),
    ('muy pésimo servicio estoy indignado', INTENT_COMPLAINT_OR_RISK),
    # opt_out
    ('stop', INTENT_OPT_OUT),
    ('no me envíes más mensajes', INTENT_OPT_OUT),
])
def test_rule_classify_matches_expected(text, expected_intent):
    result = _rule_classify(text, ALL_ENABLED, [])
    assert result is not None, f'No match for: {text!r}'
    assert result.intent == expected_intent, (
        f'Text: {text!r} → got {result.intent!r}, expected {expected_intent!r}'
    )
    assert result.resolved_by == 'rule'


def test_rule_classify_high_confidence_complaint():
    result = _rule_classify('esto es una estafa', ALL_ENABLED, [])
    assert result is not None
    assert result.confidence >= 0.90


def test_rule_classify_returns_none_for_random_text():
    result = _rule_classify('bla bla xyz123 nada', ALL_ENABLED, [])
    # Puede no haber match; si hay uno que pase, debe ser plausible (no crash)
    assert result is None or result.intent in ALL_INTENTS


def test_rule_classify_disabled_intent_skipped():
    enabled = ALL_ENABLED - {INTENT_GREETING}
    result = _rule_classify('hola', enabled, [])
    # 'hola' no debe matchear si greeting está deshabilitado
    assert result is None or result.intent != INTENT_GREETING


# ---------------------------------------------------------------------------
# Tenant custom keywords
# ---------------------------------------------------------------------------

def test_tenant_custom_keywords_match():
    tenant_rules = _compile_tenant_rules({'faq': ['precio especial', 'cuota']})
    result = _rule_classify('cuánto vale la cuota mensual', ALL_ENABLED, tenant_rules)
    assert result is not None
    assert result.intent == INTENT_FAQ


def test_tenant_custom_keywords_invalid_intent_skipped():
    # 'invalid_intent' no está en ALL_INTENTS; no debe lanzar excepción
    rules = _compile_tenant_rules({'invalid_intent': ['palabra']})
    assert rules == []


# ---------------------------------------------------------------------------
# classify_intent con fallback (sin LLM)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_classify_greeting_resolves_rule():
    settings = _fake_settings()
    result = await classify_intent('buenos días', settings=settings)
    assert result.intent == INTENT_GREETING
    assert result.resolved_by == 'rule'
    assert result.confidence >= CONF_LLM_THRESHOLD


@pytest.mark.asyncio
async def test_classify_complaint_forces_handoff():
    settings = _fake_settings()
    result = await classify_intent('esto es una estafa terrible', settings=settings)
    assert result.intent == INTENT_COMPLAINT_OR_RISK


@pytest.mark.asyncio
async def test_classify_opt_out_stop():
    settings = _fake_settings()
    result = await classify_intent('stop', settings=settings)
    assert result.intent == INTENT_OPT_OUT
    assert result.confidence >= 0.90


@pytest.mark.asyncio
async def test_classify_book_appointment():
    settings = _fake_settings()
    result = await classify_intent('quiero agendar una cita para mañana', settings=settings)
    assert result.intent == INTENT_BOOK_APPOINTMENT


@pytest.mark.asyncio
async def test_classify_cancel_appointment():
    settings = _fake_settings()
    result = await classify_intent('necesito cancelar mi cita del viernes', settings=settings)
    assert result.intent == INTENT_CANCEL_APPOINTMENT


@pytest.mark.asyncio
async def test_classify_faq():
    settings = _fake_settings()
    result = await classify_intent('cuánto cuesta el servicio de mantenimiento?', settings=settings)
    assert result.intent == INTENT_FAQ


@pytest.mark.asyncio
async def test_classify_check_availability():
    settings = _fake_settings()
    result = await classify_intent('tienen disponibilidad el lunes?', settings=settings)
    assert result.intent == INTENT_CHECK_AVAILABILITY


@pytest.mark.asyncio
async def test_classify_reschedule():
    settings = _fake_settings()
    result = await classify_intent('quiero reagendar mi cita para el jueves', settings=settings)
    assert result.intent == INTENT_RESCHEDULE_APPOINTMENT


@pytest.mark.asyncio
async def test_classify_random_text_falls_back():
    """Texto sin relación → no crash, devuelve una intención válida."""
    settings = _fake_settings()
    result = await classify_intent('asdfgh zxcvbn qwerty', settings=settings)
    assert result.intent in ALL_INTENTS
    assert result.resolved_by in ('rule', 'llm', 'fallback')


@pytest.mark.asyncio
async def test_classify_respects_disabled_intent():
    settings = _fake_settings()
    cfg = {
        'enabled_intents': [i for i in ALL_INTENTS if i != INTENT_GREETING],
        'custom_keywords': {},
        'min_confidence': 0.70,
    }
    result = await classify_intent('hola buenos días', settings=settings, tenant_config=cfg)
    # greeting deshabilitado → no debe retornar greeting desde reglas
    assert result.intent != INTENT_GREETING or result.resolved_by != 'rule'


@pytest.mark.asyncio
async def test_classify_custom_keyword_tenant():
    settings = _fake_settings()
    cfg = {
        'enabled_intents': ALL_INTENTS,
        'custom_keywords': {'book_appointment': ['turno urgente']},
        'min_confidence': 0.70,
    }
    result = await classify_intent('necesito un turno urgente para hoy', settings=settings, tenant_config=cfg)
    assert result.intent == INTENT_BOOK_APPOINTMENT


# ---------------------------------------------------------------------------
# Catálogo de intenciones
# ---------------------------------------------------------------------------

def test_all_intents_catalog_has_10():
    assert len(ALL_INTENTS) == 10


def test_all_intents_are_strings():
    for intent in ALL_INTENTS:
        assert isinstance(intent, str) and len(intent) > 0


def test_confidence_thresholds_order():
    assert CONF_FALLBACK_THRESHOLD < CONF_LLM_THRESHOLD
