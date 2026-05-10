"""Static tests for the dual answer engine (template vs local_llm) and CSV chunking."""
from pathlib import Path

ORCHESTRATOR = Path('app/services/rag_orchestrator.py')
LLM_ANSWER = Path('app/services/llm_answer.py')
RAG_INDEXING = Path('app/services/rag_indexing.py')
CONFIG = Path('app/core/config.py')


# ── Config settings ───────────────────────────────────────────────────────────

def test_config_exposes_answer_engine_flag():
    source = CONFIG.read_text()
    assert "answer_engine: str" in source
    assert "'template'" in source
    assert "'^(template|local_llm|cascade)$'" in source
    assert 'cascade_template_min_score' in source
    assert 'cascade_llm_min_score' in source


def test_config_exposes_local_llm_settings():
    source = CONFIG.read_text()
    assert 'local_llm_base_url' in source
    assert 'local_llm_model' in source
    assert 'local_llm_timeout_seconds' in source
    assert '11434' in source


# ── Orchestrator flag routing ─────────────────────────────────────────────────

def test_orchestrator_imports_llm_answer_service():
    source = ORCHESTRATOR.read_text()
    assert 'from app.services.llm_answer import' in source
    assert 'build_llm_answer' in source


def test_orchestrator_routes_to_llm_when_engine_is_local_llm():
    source = ORCHESTRATOR.read_text()
    assert "engine == 'local_llm'" in source
    assert 'await build_llm_answer(' in source
    assert 'settings.local_llm_base_url' in source
    assert 'settings.local_llm_model' in source
    assert 'settings.local_llm_timeout_seconds' in source


def test_orchestrator_falls_back_to_template_when_engine_is_template():
    source = ORCHESTRATOR.read_text()
    assert "engine == 'template'" in source
    assert 'build_grounded_answer(question, matches)' in source


def test_orchestrator_cascade_tries_template_then_llm_then_handoff():
    source = ORCHESTRATOR.read_text()
    assert 'async def _resolve_answer' in source
    assert 'cascade_template_min_score' in source
    assert 'cascade_llm_min_score' in source
    assert 'cascade.llm_unavailable' in source
    assert 'cascade_exhausted' in source
    assert 'cascade.exhausted_to_handoff' in source


def test_orchestrator_cascade_llm_failure_does_not_raise():
    source = ORCHESTRATOR.read_text()
    assert 'except Exception' in source
    assert 'log.warning(' in source


def test_orchestrator_traces_answer_engine_and_llm_model_in_payload():
    source = ORCHESTRATOR.read_text()
    assert "'answer_engine'" in source
    assert "'llm_model'" in source
    assert 'llm_used' in source


# ── Local LLM service ─────────────────────────────────────────────────────────

def test_llm_answer_uses_ollama_chat_api():
    source = LLM_ANSWER.read_text()
    assert '/api/chat' in source
    assert "'stream': False" in source
    assert "'temperature'" in source


def test_llm_answer_sends_system_and_user_messages():
    source = LLM_ANSWER.read_text()
    assert '_SYSTEM_PROMPT' in source
    assert "'role': 'system'" in source
    assert "'role': 'user'" in source
    assert '_USER_TEMPLATE' in source


def test_llm_answer_escalates_when_ollama_says_no_information():
    source = LLM_ANSWER.read_text()
    assert 'no tengo esa información' in source
    assert "'llm_no_information'" in source
    assert 'escalate_to_human' in source


def test_llm_answer_tracks_source_document():
    source = LLM_ANSWER.read_text()
    assert '_source_document' in source


def test_llm_answer_handles_timeout_and_http_errors():
    source = LLM_ANSWER.read_text()
    assert 'TimeoutException' in source
    assert 'HTTPStatusError' in source
    assert 'log.warning' in source


def test_llm_answer_returns_llm_used_flag_and_model():
    source = LLM_ANSWER.read_text()
    assert "'llm_used': True" in source
    assert "'llm_model': model" in source


# ── CSV-aware indexing ────────────────────────────────────────────────────────

def test_indexing_detects_csv_content_heuristically():
    source = RAG_INDEXING.read_text()
    assert 'def is_csv_content' in source
    assert "first_commas < 2" in source


def test_indexing_converts_csv_rows_to_natural_language():
    source = RAG_INDEXING.read_text()
    assert 'def csv_rows_to_natural_language' in source
    assert 'csv.DictReader' in source
    assert '_format_csv_value' in source


def test_indexing_formats_price_columns_as_cop():
    source = RAG_INDEXING.read_text()
    assert '_PRICE_COLS' in source
    assert 'Precio:' in source
    assert 'COP' in source


def test_indexing_formats_duration_columns():
    source = RAG_INDEXING.read_text()
    assert '_DURATION_COLS' in source
    assert 'Duración:' in source


def test_indexing_applies_csv_conversion_in_build_indexing_result():
    source = RAG_INDEXING.read_text()
    assert 'is_csv_content' in source
    assert 'csv_rows_to_natural_language' in source
    assert "mime_type == 'text/csv'" in source


# ── CSV conversion unit tests ─────────────────────────────────────────────────

def test_csv_to_natural_language_converts_price_csv():
    from app.services.rag_indexing import csv_rows_to_natural_language

    csv_text = (
        'categoria,procedimiento,descripcion,precio_cop,duracion_minutos\n'
        'Manicuria,Manicure tradicional,Limpieza y limado,28000,35\n'
        'Manicuria,Manicure semipermanente,Con esmalte semipermanente,48000,55\n'
    )
    result = csv_rows_to_natural_language(csv_text)

    assert 'Manicure tradicional' in result
    assert 'Precio: $28,000 COP' in result
    assert 'Duración: 35 min' in result
    assert 'Manicure semipermanente' in result
    assert 'Precio: $48,000 COP' in result


def test_csv_to_natural_language_includes_category_in_entity_name():
    from app.services.rag_indexing import csv_rows_to_natural_language

    csv_text = (
        'procedimiento,categoria,precio_cop\n'
        'Corte dama,Peluquería,45000\n'
    )
    result = csv_rows_to_natural_language(csv_text)

    assert 'categoría: Peluquería' in result


def test_is_csv_content_detects_valid_csv():
    from app.services.rag_indexing import is_csv_content

    csv_text = (
        'col1,col2,col3\n'
        'val1,val2,val3\n'
        'val4,val5,val6\n'
    )
    assert is_csv_content(csv_text) is True


def test_is_csv_content_rejects_plain_text():
    from app.services.rag_indexing import is_csv_content

    assert is_csv_content('Este es un párrafo normal de texto plano.') is False
    assert is_csv_content('') is False
