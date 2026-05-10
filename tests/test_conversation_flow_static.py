"""Static and unit tests for the conversational booking flow."""
from pathlib import Path

CONV_FLOW = Path('app/services/conversation_flow.py')
ORCHESTRATOR = Path('app/services/rag_orchestrator.py')
LLM_ANSWER = Path('app/services/llm_answer.py')


# ── Stage constants ───────────────────────────────────────────────────────────

def test_all_booking_stages_defined():
    source = CONV_FLOW.read_text()
    for stage in (
        'STAGE_START', 'STAGE_SERVICE_SELECTION', 'STAGE_AVAILABILITY',
        'STAGE_PRICE_NEGOTIATION', 'STAGE_DATA_COLLECTION',
        'STAGE_CONFIRMATION', 'STAGE_BOOKED',
    ):
        assert stage in source, f'{stage} missing from conversation_flow.py'


def test_conversational_stages_set_excludes_start_and_booked():
    from app.services.conversation_flow import (
        CONVERSATIONAL_STAGES,
        STAGE_BOOKED,
        STAGE_START,
    )
    assert STAGE_START not in CONVERSATIONAL_STAGES
    assert STAGE_BOOKED not in CONVERSATIONAL_STAGES
    assert len(CONVERSATIONAL_STAGES) == 5


# ── ConversationContext ───────────────────────────────────────────────────────

def test_context_is_conversational_true_for_service_selection():
    from app.services.conversation_flow import ConversationContext, STAGE_SERVICE_SELECTION
    ctx = ConversationContext(stage=STAGE_SERVICE_SELECTION)
    assert ctx.is_conversational is True


def test_context_is_conversational_false_for_start():
    from app.services.conversation_flow import ConversationContext, STAGE_START
    ctx = ConversationContext(stage=STAGE_START)
    assert ctx.is_conversational is False


def test_context_booking_complete_requires_name_phone_service():
    from app.services.conversation_flow import ConversationContext
    ctx = ConversationContext(collected={'name': 'Ana', 'phone': '3001234567', 'service_name': 'Manicure'})
    assert ctx.booking_complete is True


def test_context_booking_incomplete_when_phone_missing():
    from app.services.conversation_flow import ConversationContext
    ctx = ConversationContext(collected={'name': 'Ana', 'service_name': 'Manicure'})
    assert ctx.booking_complete is False


def test_context_collected_summary_shows_service_and_price():
    from app.services.conversation_flow import ConversationContext
    ctx = ConversationContext(collected={
        'service_name': 'Manicure', 'service_price': 28000,
        'name': 'Ana', 'phone': '3001234567',
    })
    summary = ctx.collected_summary()
    assert 'Manicure' in summary
    assert '$28,000 COP' in summary
    assert 'Ana' in summary


# ── get_context factory ───────────────────────────────────────────────────────

def test_get_context_from_dict_metadata():
    from app.services.conversation_flow import get_context, STAGE_SERVICE_SELECTION
    ctx = get_context({'conv_stage': 'service_selection', 'collected': {'service_name': 'Pedicure'}})
    assert ctx.stage == STAGE_SERVICE_SELECTION
    assert ctx.collected['service_name'] == 'Pedicure'


def test_get_context_from_json_string():
    import json
    from app.services.conversation_flow import get_context, STAGE_AVAILABILITY
    meta_str = json.dumps({'conv_stage': 'availability_check', 'collected': {}})
    ctx = get_context(meta_str)
    assert ctx.stage == STAGE_AVAILABILITY


def test_get_context_defaults_to_start_on_empty():
    from app.services.conversation_flow import get_context, STAGE_START
    ctx = get_context(None)
    assert ctx.stage == STAGE_START
    assert ctx.collected == {}


def test_get_context_defaults_to_start_on_invalid_json():
    from app.services.conversation_flow import get_context, STAGE_START
    ctx = get_context('not-json')
    assert ctx.stage == STAGE_START


# ── has_booking_intent ────────────────────────────────────────────────────────

def test_has_booking_intent_detects_agendar():
    from app.services.conversation_flow import has_booking_intent
    assert has_booking_intent('quiero agendar una cita') is True


def test_has_booking_intent_detects_disponibilidad():
    from app.services.conversation_flow import has_booking_intent
    assert has_booking_intent('¿tienen disponibilidad el martes?') is True


def test_has_booking_intent_false_for_generic_question():
    from app.services.conversation_flow import has_booking_intent
    assert has_booking_intent('cuánto cuesta el manicure') is False


# ── build_system_prompt ───────────────────────────────────────────────────────

def test_build_system_prompt_contains_stage_label():
    from app.services.conversation_flow import ConversationContext, STAGE_DATA_COLLECTION, build_system_prompt
    ctx = ConversationContext(stage=STAGE_DATA_COLLECTION)
    prompt = build_system_prompt(ctx, 'Manicure: $28,000', business_name='Salón Bella')
    assert 'Salón Bella' in prompt
    assert 'Recolección de datos' in prompt
    assert 'Manicure' in prompt


def test_build_system_prompt_contains_json_format():
    from app.services.conversation_flow import ConversationContext, STAGE_START, build_system_prompt
    ctx = ConversationContext(stage=STAGE_START)
    prompt = build_system_prompt(ctx, '')
    assert '"message"' in prompt
    assert '"next_stage"' in prompt
    assert '"action"' in prompt
    assert '"collected"' in prompt


def test_build_system_prompt_includes_valid_stages():
    from app.services.conversation_flow import ConversationContext, STAGE_START, build_system_prompt
    ctx = ConversationContext(stage=STAGE_START)
    prompt = build_system_prompt(ctx, '')
    assert 'service_selection' in prompt
    assert 'data_collection' in prompt
    assert 'confirmation' in prompt
    assert 'booked' in prompt


# ── format_history ────────────────────────────────────────────────────────────

def test_format_history_formats_inbound_as_cliente():
    from app.services.conversation_flow import format_history
    msgs = [{'direction': 'inbound', 'body_text': 'Hola, quiero una cita'}]
    result = format_history(msgs)
    assert 'Cliente: Hola, quiero una cita' in result


def test_format_history_formats_outbound_as_bot():
    from app.services.conversation_flow import format_history
    msgs = [{'direction': 'outbound', 'body_text': 'Claro, ¿qué servicio?'}]
    result = format_history(msgs)
    assert 'Bot: Claro, ¿qué servicio?' in result


def test_format_history_limits_to_max_turns():
    from app.services.conversation_flow import format_history
    msgs = [
        {'direction': 'inbound', 'body_text': f'msg {i}'}
        for i in range(20)
    ]
    result = format_history(msgs, max_turns=3)
    lines = [line for line in result.split('\n') if line.strip()]
    assert len(lines) <= 6  # max_turns * 2 messages


def test_format_history_skips_empty_body():
    from app.services.conversation_flow import format_history
    msgs = [
        {'direction': 'inbound', 'body_text': ''},
        {'direction': 'outbound', 'body_text': 'Hola'},
    ]
    result = format_history(msgs)
    assert 'Bot: Hola' in result
    assert 'Cliente: ' not in result


# ── parse_llm_response ────────────────────────────────────────────────────────

def test_parse_llm_response_parses_valid_json():
    import json
    from app.services.conversation_flow import ConversationContext, STAGE_START, parse_llm_response
    ctx = ConversationContext(stage=STAGE_START)
    raw = json.dumps({
        'message': 'Hola, ¿en qué te puedo ayudar?',
        'next_stage': 'service_selection',
        'action': None,
        'collected': {'service_name': 'Manicure'},
    })
    result = parse_llm_response(raw, ctx)
    assert result['message'] == 'Hola, ¿en qué te puedo ayudar?'
    assert result['next_stage'] == 'service_selection'
    assert result['collected']['service_name'] == 'Manicure'


def test_parse_llm_response_merges_existing_collected():
    import json
    from app.services.conversation_flow import ConversationContext, STAGE_SERVICE_SELECTION, parse_llm_response
    ctx = ConversationContext(
        stage=STAGE_SERVICE_SELECTION,
        collected={'name': 'Ana', 'service_name': None},
    )
    raw = json.dumps({
        'message': 'Perfecto.',
        'next_stage': 'availability_check',
        'action': None,
        'collected': {'service_name': 'Pedicure', 'name': None},
    })
    result = parse_llm_response(raw, ctx)
    # LLM null doesn't overwrite existing value
    assert result['collected']['name'] == 'Ana'
    # LLM value updates null
    assert result['collected']['service_name'] == 'Pedicure'


def test_parse_llm_response_extracts_json_from_markdown_block():
    import json
    from app.services.conversation_flow import ConversationContext, STAGE_START, parse_llm_response
    ctx = ConversationContext(stage=STAGE_START)
    payload = {'message': 'Ok', 'next_stage': 'service_selection', 'action': None, 'collected': {}}
    raw = f'```json\n{json.dumps(payload)}\n```'
    result = parse_llm_response(raw, ctx)
    assert result['message'] == 'Ok'


def test_parse_llm_response_falls_back_to_plain_text():
    from app.services.conversation_flow import ConversationContext, STAGE_START, parse_llm_response
    ctx = ConversationContext(stage=STAGE_START)
    raw = 'Lo siento, no entendí tu mensaje.'
    result = parse_llm_response(raw, ctx)
    assert result['message'] == raw
    assert result['next_stage'] == STAGE_START
    assert result['action'] is None


def test_parse_llm_response_keeps_stage_when_next_stage_missing():
    import json
    from app.services.conversation_flow import ConversationContext, STAGE_CONFIRMATION, parse_llm_response
    ctx = ConversationContext(stage=STAGE_CONFIRMATION)
    raw = json.dumps({'message': 'Confirmado.', 'collected': {}})
    result = parse_llm_response(raw, ctx)
    assert result['next_stage'] == STAGE_CONFIRMATION


# ── Orchestrator integration ──────────────────────────────────────────────────

def test_orchestrator_imports_conversation_flow():
    source = ORCHESTRATOR.read_text()
    assert 'from app.services.conversation_flow import' in source
    assert 'get_context' in source
    assert 'has_booking_intent' in source
    assert 'format_history' in source


def test_orchestrator_imports_build_conversational_llm_answer():
    source = ORCHESTRATOR.read_text()
    assert 'build_conversational_llm_answer' in source


def test_orchestrator_routes_to_conversational_when_booking_intent():
    source = ORCHESTRATOR.read_text()
    assert 'use_conversational' in source
    assert "engine != 'template'" in source
    assert 'has_booking_intent' in source
    assert 'ctx.is_conversational' in source


def test_orchestrator_routes_to_conversational_on_stage_start():
    # First message ("hola") must go to LLM even without booking keywords
    source = ORCHESTRATOR.read_text()
    assert 'STAGE_START' in source
    assert 'ctx.stage == STAGE_START' in source


def test_orchestrator_persists_stage_after_conversational_turn():
    source = ORCHESTRATOR.read_text()
    assert '_update_conversation_metadata' in source
    assert 'conv_stage' in source
    assert 'new_stage' in source
    assert 'new_collected' in source


def test_orchestrator_creates_service_request_on_appointment_action():
    source = ORCHESTRATOR.read_text()
    assert '_handle_appointment_created' in source
    assert "action == 'create_appointment'" in source
    assert 'service_requests' in source


def test_orchestrator_handoffs_on_request_human_action():
    source = ORCHESTRATOR.read_text()
    assert "action == 'request_human'" in source
    assert '_do_handoff' in source


def test_orchestrator_falls_back_to_qa_when_conversational_llm_fails():
    source = ORCHESTRATOR.read_text()
    assert '_resolve_conversational' in source
    assert 'cascade.conversational_llm_unavailable' in source
    assert '_resolve_answer' in source


def test_orchestrator_fetches_tenant_business_name():
    source = ORCHESTRATOR.read_text()
    assert 'display_name as business_name' in source
    assert 'business_name' in source


# ── llm_answer conversational function ───────────────────────────────────────

def test_llm_answer_has_conversational_function():
    source = LLM_ANSWER.read_text()
    assert 'async def build_conversational_llm_answer' in source
    assert 'ctx: ConversationContext' in source
    assert 'history: str' in source


def test_llm_answer_conversational_sends_history_as_context():
    source = LLM_ANSWER.read_text()
    assert 'HISTORIAL' in source
    assert 'messages_payload' in source


def test_llm_answer_conversational_returns_next_stage_and_collected():
    source = LLM_ANSWER.read_text()
    assert "'next_stage'" in source
    assert "'collected'" in source
    assert "'action'" in source


def test_llm_answer_conversational_escalates_on_request_human():
    source = LLM_ANSWER.read_text()
    assert "action == 'request_human'" in source
    assert 'escalate_to_human' in source
