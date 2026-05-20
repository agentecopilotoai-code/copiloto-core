import asyncio
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.services.conversation_flow import ConversationContext, build_system_prompt
from app.services.rag_orchestrator import (
    _SPANISH_WEEKDAYS,
    _current_datetime_label,
    _load_active_resources_context,
)

ORCHESTRATOR = Path('app/services/rag_orchestrator.py')
CONVERSATION_FLOW = Path('app/services/conversation_flow.py')
LLM_ANSWER = Path('app/chatbot/llm_answer.py')
CLOUD_LLM_ANSWER = Path('app/chatbot/cloud_llm_answer.py')


def test_current_datetime_label_uses_tenant_timezone():
    label, tz_used = _current_datetime_label('America/Bogota')
    assert tz_used == 'America/Bogota'
    # Format is "<weekday> DD/MM/YYYY HH:MM" in Spanish.
    assert re.match(r'^(lunes|martes|miércoles|jueves|viernes|sábado|domingo) \d{2}/\d{2}/\d{4} \d{2}:\d{2}$', label), label

    # Same instant but rendered in two different timezones should produce
    # different labels (e.g., Asia/Tokyo is ~14 hours ahead of Bogotá).
    bogota = datetime.now(ZoneInfo('America/Bogota'))
    tokyo = datetime.now(ZoneInfo('Asia/Tokyo'))
    if bogota.hour != tokyo.hour:
        label_tokyo, _ = _current_datetime_label('Asia/Tokyo')
        label_bogota, _ = _current_datetime_label('America/Bogota')
        assert label_tokyo != label_bogota


def test_current_datetime_label_falls_back_on_unknown_timezone():
    label, tz_used = _current_datetime_label('Mars/Olympus_Mons')
    assert tz_used == 'America/Bogota'
    assert any(weekday in label for weekday in _SPANISH_WEEKDAYS)


def test_build_system_prompt_includes_temporal_and_resource_blocks():
    ctx = ConversationContext(stage='service_selection', collected={})
    prompt = build_system_prompt(
        ctx,
        services_context='- Manicure 50000 COP',
        business_name='Demo',
        current_datetime_label='lunes 11/05/2026 18:15',
        timezone='America/Bogota',
        resources_context='- María (stylist)\n- Carlos (stylist)',
    )
    assert '== CONTEXTO TEMPORAL ==' in prompt
    assert 'lunes 11/05/2026 18:15' in prompt
    assert 'America/Bogota' in prompt
    assert '== PROFESIONALES / RECURSOS DISPONIBLES ==' in prompt
    assert 'María (stylist)' in prompt
    assert 'Carlos (stylist)' in prompt
    # Default fallbacks still work when nothing is passed.
    default_prompt = build_system_prompt(ctx, services_context='', business_name='Demo')
    assert 'no disponible' in default_prompt
    assert 'No hay profesionales activos configurados todavía.' in default_prompt


def test_orchestrator_threads_temporal_context_into_llm_calls():
    source = ORCHESTRATOR.read_text()
    assert 'from zoneinfo import ZoneInfo' in source
    assert 'def _current_datetime_label' in source
    assert 'async def _load_active_resources_context' in source
    assert 'tenant_timezone' in source
    assert 'current_datetime_label=current_datetime_label' in source
    assert 'resources_context=resources_context' in source
    assert 't.timezone' in source


def test_llm_answer_modules_accept_temporal_kwargs():
    llm = LLM_ANSWER.read_text()
    cloud = CLOUD_LLM_ANSWER.read_text()
    for source in (llm, cloud):
        assert 'current_datetime_label' in source
        assert 'resources_context' in source
        assert "timezone: str = 'America/Bogota'" in source


def test_system_prompt_template_advertises_temporal_block():
    text = CONVERSATION_FLOW.read_text()
    assert '== CONTEXTO TEMPORAL ==' in text
    assert '{current_datetime_label}' in text
    assert '{timezone}' in text
    assert '== PROFESIONALES / RECURSOS DISPONIBLES ==' in text
    assert '{resources_context}' in text
    # The availability-check instructions now explicitly mention temporal grounding
    # and multi-resource selection.
    assert 'resuelve la fecha REAL usando el contexto temporal' in text
    assert 'más de un profesional' in text


class FakeConn:
    def __init__(self, rows):
        self.rows = rows

    async def fetch(self, _query, *_args):
        return [dict(r) for r in self.rows]


def test_load_active_resources_context_formats_lines():
    rows = [
        {'name': 'María', 'resource_type': 'stylist'},
        {'name': 'Carlos', 'resource_type': 'stylist'},
        {'name': 'Sala 1', 'resource_type': ''},
    ]
    result = asyncio.run(_load_active_resources_context(FakeConn(rows), uuid4()))
    assert '- María (stylist)' in result
    assert '- Carlos (stylist)' in result
    assert '- Sala 1' in result


def test_load_active_resources_context_empty_returns_placeholder():
    result = asyncio.run(_load_active_resources_context(FakeConn([]), uuid4()))
    assert 'No hay profesionales activos' in result
