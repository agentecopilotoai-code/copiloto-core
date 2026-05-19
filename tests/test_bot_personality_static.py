"""TASK-0071: tono / personalidad del bot configurable por tenant.

Cobertura mínima requerida por el backlog (≥ 6 tests):
1. Schema: tenant_settings.bot_personality jsonb con default esperado.
2. _normalize_personality acepta valores fuera del catálogo y los coerce al default.
3. _normalize_personality tolera string JSON y entradas inválidas.
4. build_personality_block es vacío cuando la config es la default (no infla prompt).
5. build_personality_block inyecta secciones (tono, trato, emojis, persona) cuando hay overrides.
6. build_system_prompt antepone el bloque de voz al template RAG y respeta el orden.
7. build_system_prompt para tone=playful difiere notoriamente vs tone=formal (mismo input).
8. La API admin PATCH acepta el campo bot_personality en la lista de keys permitidas.
9. La UI del admin panel registra el tab 'Voz del bot' en wizardTabs.
10. El orchestrator carga bot_personality del SELECT y lo pasa a _resolve_conversational.
"""
from pathlib import Path
from tests._routes_aggregator import routes_aggregated_source

CONV_FLOW = Path('app/services/conversation_flow.py')
SCHEMA = Path('infra/postgres/01-schema.sql')
ORCH = Path('app/services/rag_orchestrator.py')
TENANT_SETUP_FEATURE = Path('admin-panel/src/features/owner-admin/tenant-setup')
LLM_ANSWER = Path('app/services/llm_answer.py')
CLOUD_LLM = Path('app/services/cloud_llm_answer.py')


def _tenant_setup_source() -> str:
    # BUG-108: `rglob('*.js*')` también matchea `.test.jsx` y `.test.js`, así que
    # los aserts del static test pasaban si la cadena buscada vivía en un test
    # (no en código de prod). Filtramos `.test.` para mirar solo fuentes.
    paths = sorted(
        p for p in TENANT_SETUP_FEATURE.rglob('*.js*')
        if '.test.' not in p.name
    )
    return '\n'.join(p.read_text() for p in paths)


# 1 ── Schema
def test_schema_has_bot_personality_column_with_default():
    src = SCHEMA.read_text()
    assert 'bot_personality jsonb' in src
    # default debe incluir las cuatro claves del contrato.
    assert '"tone":"neutral"' in src
    assert '"formality":"tu"' in src
    assert '"emoji_level":"moderate"' in src
    assert '"custom_persona":""' in src


# 2 ── Normalize: valores fuera de catálogo → default
def test_normalize_personality_rejects_unknown_values():
    from app.services.conversation_flow import _normalize_personality
    result = _normalize_personality({
        'tone': 'angry_pirate',
        'formality': 'klingon',
        'emoji_level': 'extreme',
        'custom_persona': '  hola  ',
    })
    assert result['tone'] == 'neutral'
    assert result['formality'] == 'tu'
    assert result['emoji_level'] == 'moderate'
    assert result['custom_persona'] == 'hola'


# 3 ── Normalize: entradas inválidas y string JSON
def test_normalize_personality_accepts_json_string_and_handles_none():
    from app.services.conversation_flow import (
        DEFAULT_BOT_PERSONALITY,
        _normalize_personality,
    )
    assert _normalize_personality(None) == DEFAULT_BOT_PERSONALITY
    assert _normalize_personality('not-json') == DEFAULT_BOT_PERSONALITY
    parsed = _normalize_personality('{"tone":"playful","formality":"vos","emoji_level":"high","custom_persona":"X"}')
    assert parsed['tone'] == 'playful'
    assert parsed['formality'] == 'vos'
    assert parsed['emoji_level'] == 'high'
    assert parsed['custom_persona'] == 'X'


# 4 ── Bloque vacío cuando es default (no infla prompt)
def test_build_personality_block_empty_for_default():
    from app.services.conversation_flow import build_personality_block
    assert build_personality_block(None) == ''
    assert build_personality_block({}) == ''
    assert build_personality_block({
        'tone': 'neutral', 'formality': 'tu', 'emoji_level': 'moderate', 'custom_persona': '',
    }) == ''


# 5 ── Bloque incluye las secciones esperadas con overrides
def test_build_personality_block_renders_all_sections():
    from app.services.conversation_flow import build_personality_block
    block = build_personality_block({
        'tone': 'playful',
        'formality': 'usted',
        'emoji_level': 'high',
        'custom_persona': 'Eres recepcionista de spa premium.',
    })
    assert '== VOZ DEL BOT' in block
    assert 'Tono: playful' in block
    assert 'Trato: usted' in block
    assert 'Emojis: high' in block
    assert 'recepcionista de spa premium' in block


# 6 ── build_system_prompt antepone el bloque voz al template RAG
def test_build_system_prompt_inserts_personality_before_template():
    from app.services.conversation_flow import (
        ConversationContext, STAGE_START, build_system_prompt,
    )
    ctx = ConversationContext(stage=STAGE_START)
    personality = {'tone': 'friendly', 'formality': 'usted', 'emoji_level': 'low', 'custom_persona': ''}
    prompt = build_system_prompt(ctx, '', business_name='Spa Bella', bot_personality=personality)
    idx_voice = prompt.find('== VOZ DEL BOT')
    idx_temporal = prompt.find('== CONTEXTO TEMPORAL ==')
    assert idx_voice != -1, 'el bloque de voz debe aparecer en el prompt'
    assert idx_temporal != -1
    assert idx_voice < idx_temporal, 'la voz debe ir antes del template RAG'


# 7 ── Tonos distintos producen prompts diferenciables
def test_build_system_prompt_playful_vs_formal_differ():
    from app.services.conversation_flow import (
        ConversationContext, STAGE_START, build_system_prompt,
    )
    ctx = ConversationContext(stage=STAGE_START)
    playful = build_system_prompt(
        ctx, '', bot_personality={'tone': 'playful', 'formality': 'tu', 'emoji_level': 'high', 'custom_persona': ''},
    )
    formal = build_system_prompt(
        ctx, '', bot_personality={'tone': 'formal', 'formality': 'usted', 'emoji_level': 'none', 'custom_persona': ''},
    )
    assert playful != formal
    assert 'playful' in playful and 'formal' in formal
    assert 'NO uses emojis' in formal
    assert 'NO uses emojis' not in playful


# 8 ── API admin PATCH lista bot_personality
def test_patch_settings_accepts_bot_personality_key():
    src = routes_aggregated_source()
    # La tupla de claves permitidas debe incluir bot_personality.
    assert "'bot_personality'" in src
    # El UPDATE debe persistir bot_personality como jsonb.
    assert 'bot_personality=$8::jsonb' in src


# 9 ── Wizard UI: existe tab "Voz del bot" y opciones de tono
def test_wizard_registers_voz_tab():
    src = _tenant_setup_source()
    assert "id: 'voz'" in src
    assert "label: 'Voz del bot'" in src
    # Las cuatro opciones de tono deben existir.
    for tone in ('neutral', 'formal', 'friendly', 'playful'):
        assert f"value: '{tone}'" in src
    # La preview se renderiza con 3 muestras (saludo, disponibilidad, objeción).
    assert 'PERSONALITY_PREVIEW_SAMPLES' in src
    assert "id: 'greeting'" in src and "id: 'availability'" in src and "id: 'objection'" in src


# 10 ── Orchestrator selecciona bot_personality y lo propaga
def test_orchestrator_threads_bot_personality():
    src = ORCH.read_text()
    assert 'ts.bot_personality' in src, 'la query debe traer bot_personality'
    assert "bot_personality_raw" in src
    assert 'bot_personality=bot_personality' in src
    # Llega también al cloud LLM y al ollama llm_answer.
    llm = LLM_ANSWER.read_text()
    cloud = CLOUD_LLM.read_text()
    assert 'bot_personality' in llm
    assert 'bot_personality' in cloud


# 11 ── bot_personality vive en el CREATE TABLE (no como migración incremental)
def test_schema_defines_bot_personality_inline_on_create_table():
    src = SCHEMA.read_text()
    # El esquema es la única fuente de verdad: bot_personality se declara en el
    # CREATE TABLE de tenant_settings, no como ALTER TABLE ADD COLUMN para
    # deployments existentes (no hay producción que migrar).
    assert 'add column if not exists bot_personality' not in src
    assert 'alter table app.tenant_settings\n  add column' not in src
    create_block_start = src.index('create table app.tenant_settings')
    create_block_end = src.index(');', create_block_start)
    create_block = src[create_block_start:create_block_end]
    assert 'bot_personality jsonb' in create_block


# 12 ── Q&A path también recibe la voz del bot (P2 review)
def test_qa_cascade_receives_bot_personality():
    # _resolve_answer y los Q&A builders aceptan bot_personality y lo
    # antepuestan al system prompt cuando no es default.
    llm = LLM_ANSWER.read_text()
    cloud = CLOUD_LLM.read_text()
    orch = ORCH.read_text()
    # Las firmas exponen el kwarg.
    assert 'bot_personality: Any = None' in llm
    assert 'bot_personality: Any = None' in cloud
    # build_llm_answer y build_cloud_llm_answer construyen el system prompt vía helper dedicado.
    assert '_qa_system_prompt' in llm
    assert '_qa_system_prompt' in cloud
    # El orchestrator pasa bot_personality en los dos call sites del Q&A cascade.
    occurrences = orch.count('_resolve_answer(')
    threads = orch.count('bot_personality=bot_personality')
    assert occurrences >= 2
    # Espera al menos un threading por cada llamada cascada + el conversational.
    assert threads >= 4, f'esperaba >=4 threading de bot_personality, encontré {threads}'


# 13 ── Q&A helper antepone bloque sólo cuando hay overrides (cache-friendly)
def test_qa_helper_preserves_default_prompt():
    # No importamos los módulos (require httpx); inspeccionamos el código fuente.
    llm = LLM_ANSWER.read_text()
    cloud = CLOUD_LLM.read_text()
    for src in (llm, cloud):
        # El helper devuelve el system prompt original cuando block está vacío,
        # preservando el cache hit en Anthropic y la huella estable en Ollama.
        assert 'if not block:' in src
        assert 'return _SYSTEM_PROMPT' in src
        # Y antepone el bloque al SYSTEM_PROMPT cuando hay overrides.
        assert 'f\'{block}\\n\\n{_SYSTEM_PROMPT}\'' in src
    # build_personality_block sigue devolviendo cadena vacía con la default
    # (smoke check directo en conversation_flow, que no requiere httpx).
    from app.services.conversation_flow import build_personality_block
    assert build_personality_block(None) == ''
    assert '== VOZ DEL BOT' in build_personality_block(
        {'tone': 'formal', 'formality': 'usted', 'emoji_level': 'none', 'custom_persona': ''},
    )
