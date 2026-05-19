"""Tests for `app/services/conversation_flow.py`."""
from __future__ import annotations



# ───── _safe_price_int ───────────────────────────────────────────────────


def test_safe_price_int_none():
    from app.services.conversation_flow import _safe_price_int
    assert _safe_price_int(None) is None


def test_safe_price_int_native_int():
    from app.services.conversation_flow import _safe_price_int
    assert _safe_price_int(35000) == 35000


def test_safe_price_int_native_float():
    from app.services.conversation_flow import _safe_price_int
    assert _safe_price_int(35000.5) == 35000


def test_safe_price_int_formatted_string():
    from app.services.conversation_flow import _safe_price_int
    assert _safe_price_int('$35.000 COP') == 35000
    assert _safe_price_int('  $1,500.00  ') == 150000


def test_safe_price_int_no_digits_returns_none():
    from app.services.conversation_flow import _safe_price_int
    assert _safe_price_int('free') is None
    assert _safe_price_int('') is None


# ───── ConversationContext ───────────────────────────────────────────────


def test_conversation_context_defaults():
    from app.services.conversation_flow import ConversationContext, STAGE_START
    ctx = ConversationContext()
    assert ctx.stage == STAGE_START
    assert ctx.collected == {}


def test_conversation_context_is_conversational():
    from app.services.conversation_flow import (
        CONVERSATIONAL_STAGES,
        ConversationContext,
    )
    for stage in CONVERSATIONAL_STAGES:
        ctx = ConversationContext(stage=stage)
        assert ctx.is_conversational is True


def test_conversation_context_not_conversational():
    from app.services.conversation_flow import ConversationContext
    ctx = ConversationContext(stage='completely_random_stage')
    assert ctx.is_conversational is False


def test_conversation_context_booking_complete_true():
    from app.services.conversation_flow import ConversationContext
    ctx = ConversationContext(
        collected={'name': 'Maria', 'phone': '+57300', 'service_name': 'Corte'},
    )
    assert ctx.booking_complete is True


def test_conversation_context_booking_complete_false():
    from app.services.conversation_flow import ConversationContext
    ctx = ConversationContext(collected={'name': 'M', 'service_name': 'X'})
    # missing phone
    assert ctx.booking_complete is False


def test_collected_summary_empty():
    from app.services.conversation_flow import ConversationContext
    ctx = ConversationContext()
    assert 'sin datos' in ctx.collected_summary()


def test_collected_summary_full():
    from app.services.conversation_flow import ConversationContext
    ctx = ConversationContext(
        collected={
            'service_name': 'Corte', 'service_price': 35000,
            'preferred_day': 'lunes', 'preferred_time': '10am',
            'name': 'Maria', 'phone': '+57300', 'notes': 'puntual',
        },
    )
    summary = ctx.collected_summary()
    assert 'Corte' in summary
    assert 'Maria' in summary
    assert '+57300' in summary


def test_collected_summary_partial():
    from app.services.conversation_flow import ConversationContext
    ctx = ConversationContext(collected={'service_name': 'X'})
    summary = ctx.collected_summary()
    assert 'X' in summary


# ───── get_context ───────────────────────────────────────────────────────


def test_get_context_from_dict():
    from app.services.conversation_flow import get_context
    ctx = get_context({'conv_stage': 'data_collection', 'collected': {'name': 'X'}})
    assert ctx.stage == 'data_collection'
    assert ctx.collected['name'] == 'X'


def test_get_context_from_json_string():
    from app.services.conversation_flow import get_context
    ctx = get_context('{"conv_stage": "confirmation", "collected": {}}')
    assert ctx.stage == 'confirmation'


def test_get_context_invalid_json_falls_back_to_start():
    from app.services.conversation_flow import STAGE_START, get_context
    ctx = get_context('garbage')
    assert ctx.stage == STAGE_START


def test_get_context_none_falls_back_to_start():
    from app.services.conversation_flow import STAGE_START, get_context
    ctx = get_context(None)
    assert ctx.stage == STAGE_START


def test_get_context_collected_none_becomes_empty():
    from app.services.conversation_flow import get_context
    ctx = get_context({'conv_stage': 'start', 'collected': None})
    assert ctx.collected == {}


# ───── has_booking_intent ────────────────────────────────────────────────


def test_has_booking_intent_true():
    from app.services.conversation_flow import has_booking_intent
    # Use any keyword from _BOOKING_KEYWORDS
    assert has_booking_intent('quiero agendar una cita') is True


def test_has_booking_intent_false():
    from app.services.conversation_flow import has_booking_intent
    assert has_booking_intent('xyz nothing here') is False


# ───── stage_followup_prompt ────────────────────────────────────────────


def test_stage_followup_prompt_unknown_returns_empty():
    from app.services.conversation_flow import stage_followup_prompt
    assert stage_followup_prompt('unknown_stage') == ''


# ───── _normalize_personality ────────────────────────────────────────────


def test_normalize_personality_defaults_for_none():
    from app.services.conversation_flow import (
        DEFAULT_BOT_PERSONALITY,
        _normalize_personality,
    )
    out = _normalize_personality(None)
    assert out == dict(DEFAULT_BOT_PERSONALITY)


def test_normalize_personality_from_json_string():
    from app.services.conversation_flow import _normalize_personality
    out = _normalize_personality('{"tone": "playful", "formality": "tu"}')
    assert out['tone'] == 'playful'
    assert out['formality'] == 'tu'


def test_normalize_personality_invalid_json_returns_defaults():
    from app.services.conversation_flow import (
        DEFAULT_BOT_PERSONALITY,
        _normalize_personality,
    )
    assert _normalize_personality('not json') == dict(DEFAULT_BOT_PERSONALITY)


def test_normalize_personality_unknown_tone_falls_to_neutral():
    from app.services.conversation_flow import _normalize_personality
    out = _normalize_personality({'tone': 'crazy', 'formality': 'usted'})
    assert out['tone'] == 'neutral'
    assert out['formality'] == 'usted'


def test_normalize_personality_unknown_formality_falls_to_tu():
    from app.services.conversation_flow import _normalize_personality
    out = _normalize_personality({'formality': 'royal'})
    assert out['formality'] == 'tu'


def test_normalize_personality_unknown_emoji_level():
    from app.services.conversation_flow import _normalize_personality
    out = _normalize_personality({'emoji_level': 'extreme'})
    assert out['emoji_level'] == 'moderate'


def test_normalize_personality_truncates_custom_persona():
    from app.services.conversation_flow import _normalize_personality
    out = _normalize_personality({'custom_persona': 'x' * 1000})
    assert len(out['custom_persona']) <= 601  # 600 + ellipsis
    assert out['custom_persona'].endswith('…')


# ───── build_personality_block ───────────────────────────────────────────


def test_build_personality_block_default_returns_empty():
    """The default personality should produce no block (saves prompt budget)."""
    from app.services.conversation_flow import build_personality_block
    assert build_personality_block(None) == ''
    assert build_personality_block({}) == ''


def test_build_personality_block_custom_persona_renders():
    from app.services.conversation_flow import build_personality_block
    out = build_personality_block({'custom_persona': 'Eres un asistente eco-friendly'})
    assert 'VOZ DEL BOT' in out
    assert 'eco-friendly' in out


def test_build_personality_block_non_default_tone():
    from app.services.conversation_flow import build_personality_block
    out = build_personality_block({'tone': 'playful'})
    assert 'VOZ DEL BOT' in out
    assert 'playful' in out


# ───── build_system_prompt ───────────────────────────────────────────────


def test_build_system_prompt_default_personality_no_voz_block():
    from app.services.conversation_flow import (
        ConversationContext,
        build_system_prompt,
    )
    ctx = ConversationContext()
    out = build_system_prompt(ctx, 'Servicios disponibles')
    assert 'VOZ DEL BOT' not in out
    assert 'Servicios disponibles' in out


def test_build_system_prompt_with_personality_prepends_voz_block():
    from app.services.conversation_flow import (
        ConversationContext,
        build_system_prompt,
    )
    ctx = ConversationContext()
    out = build_system_prompt(
        ctx, 'Servicios', bot_personality={'tone': 'formal'},
    )
    # VOZ section comes first
    assert out.index('VOZ DEL BOT') < out.index('Servicios')


def test_build_system_prompt_renders_business_name():
    from app.services.conversation_flow import (
        ConversationContext,
        build_system_prompt,
    )
    out = build_system_prompt(
        ConversationContext(), 'X', business_name='MyClinic',
    )
    assert 'MyClinic' in out


def test_build_system_prompt_renders_timezone_and_resources():
    from app.services.conversation_flow import (
        ConversationContext,
        build_system_prompt,
    )
    out = build_system_prompt(
        ConversationContext(), 'svc',
        current_datetime_label='lunes 18/05/2026 10:30',
        timezone='America/Mexico_City',
        resources_context='- Dr. Smith (general)',
    )
    assert 'lunes 18/05/2026' in out
    assert 'America/Mexico_City' in out
    assert 'Dr. Smith' in out


# ───── format_history ────────────────────────────────────────────────────


def test_format_history_empty():
    from app.services.conversation_flow import format_history
    assert format_history([]) == ''


def test_format_history_basic():
    from app.services.conversation_flow import format_history
    messages = [
        {'direction': 'inbound', 'body_text': 'Hola'},
        {'direction': 'outbound', 'body_text': 'Qué tal'},
    ]
    out = format_history(messages)
    assert 'Cliente: Hola' in out
    assert 'Bot: Qué tal' in out


def test_format_history_skips_empty_body():
    from app.services.conversation_flow import format_history
    messages = [
        {'direction': 'inbound', 'body_text': ''},
        {'direction': 'inbound', 'body_text': 'real msg'},
    ]
    out = format_history(messages)
    assert 'real msg' in out


def test_format_history_truncates_to_max_turns():
    from app.services.conversation_flow import format_history
    messages = [
        {'direction': 'inbound', 'body_text': f'msg{i}'} for i in range(100)
    ]
    out = format_history(messages, max_turns=2)
    # max_turns * 2 = 4 entries kept
    lines = [ln for ln in out.split('\n') if ln]
    assert len(lines) == 4


# ───── parse_llm_response ────────────────────────────────────────────────


def test_parse_llm_response_pure_json():
    from app.services.conversation_flow import ConversationContext, parse_llm_response
    text = '{"message": "Hola", "next_stage": "data_collection", "action": null, "collected": {"name": "Maria"}}'
    out = parse_llm_response(text, ConversationContext())
    assert out['message'] == 'Hola'
    assert out['next_stage'] == 'data_collection'
    assert out['collected']['name'] == 'Maria'


def test_parse_llm_response_in_code_block():
    from app.services.conversation_flow import ConversationContext, parse_llm_response
    text = 'Some preamble.\n```json\n{"message": "Hi", "next_stage": "start"}\n```\nAnd trailing notes.'
    out = parse_llm_response(text, ConversationContext())
    assert out['message'] == 'Hi'


def test_parse_llm_response_inline_object():
    from app.services.conversation_flow import ConversationContext, parse_llm_response
    text = 'Mucho ruido {"message": "X", "next_stage": "start"} luego.'
    out = parse_llm_response(text, ConversationContext())
    assert out['message'] == 'X'


def test_parse_llm_response_invalid_returns_raw_as_message():
    from app.services.conversation_flow import ConversationContext, parse_llm_response
    out = parse_llm_response('not json at all', ConversationContext(stage='start'))
    assert out['message'] == 'not json at all'
    assert out['next_stage'] == 'start'
    assert out['action'] is None


def test_parse_llm_response_merges_collected():
    """When LLM returns null for an existing key, the existing value is preserved."""
    from app.services.conversation_flow import ConversationContext, parse_llm_response
    ctx = ConversationContext(collected={'name': 'Maria', 'phone': '+57300'})
    text = '{"message": "ok", "collected": {"phone": null, "service_name": "Corte"}}'
    out = parse_llm_response(text, ctx)
    assert out['collected']['name'] == 'Maria'  # preserved
    assert out['collected']['phone'] == '+57300'  # null in LLM → keep existing
    assert out['collected']['service_name'] == 'Corte'  # new
