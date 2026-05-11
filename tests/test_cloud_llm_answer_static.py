"""Static tests for cloud LLM answer service (Anthropic/OpenAI) and cascade integration."""
from pathlib import Path

CLOUD_LLM = Path('app/services/cloud_llm_answer.py')
ORCHESTRATOR = Path('app/services/rag_orchestrator.py')
CONFIG = Path('app/core/config.py')
ENV_EXAMPLE = Path('.env.example')


# ── Config ────────────────────────────────────────────────────────────────────

def test_config_exposes_cloud_llm_provider():
    source = CONFIG.read_text()
    assert 'cloud_llm_provider' in source
    assert 'cloud_llm_model' in source
    assert 'cloud_llm_api_key' in source
    assert 'cloud_llm_timeout_seconds' in source


def test_config_answer_engine_accepts_cloud_llm():
    source = CONFIG.read_text()
    assert 'cloud_llm' in source
    assert "'^(template|local_llm|cascade|cloud_llm)$'" in source


def test_config_cloud_llm_model_default_is_sonnet():
    source = CONFIG.read_text()
    assert 'claude-sonnet-4-6' in source


# ── Cloud LLM service: contrato de retorno ────────────────────────────────────

def test_cloud_llm_answer_exposes_build_cloud_llm_answer():
    source = CLOUD_LLM.read_text()
    assert 'async def build_cloud_llm_answer(' in source


def test_cloud_llm_answer_exposes_build_conversational_cloud_llm_answer():
    source = CLOUD_LLM.read_text()
    assert 'async def build_conversational_cloud_llm_answer(' in source


def test_cloud_llm_answer_returns_sufficient_context_and_status():
    source = CLOUD_LLM.read_text()
    assert "'sufficient_context': True" in source
    assert "'sufficient_context': False" in source
    assert "'status': 'answered'" in source
    assert "'status': 'escalate_to_human'" in source


def test_cloud_llm_answer_tracks_llm_used_and_model():
    source = CLOUD_LLM.read_text()
    assert "'llm_used': True" in source
    assert "'cloud_llm_used': True" in source
    assert "'llm_model': model" in source


def test_cloud_llm_answer_includes_token_usage_in_return():
    source = CLOUD_LLM.read_text()
    assert "'token_usage'" in source
    assert 'input_tokens' in source
    assert 'output_tokens' in source
    assert 'cache_read_tokens' in source
    assert 'cache_creation_tokens' in source


def test_cloud_llm_answer_escalates_when_no_info_signal():
    source = CLOUD_LLM.read_text()
    assert 'no tengo esa información' in source
    assert "'llm_no_information'" in source


def test_cloud_llm_answer_handoff_required_false_on_success():
    source = CLOUD_LLM.read_text()
    assert "'required': False" in source
    assert "'required': True" in source


# ── Anthropic prompt caching ──────────────────────────────────────────────────

def test_cloud_llm_uses_anthropic_sdk_with_cache_control():
    source = CLOUD_LLM.read_text()
    assert 'import anthropic' in source
    assert "cache_control" in source
    assert "'type': 'ephemeral'" in source


def test_cloud_llm_anthropic_uses_system_blocks():
    source = CLOUD_LLM.read_text()
    assert 'system_blocks' in source
    assert "client.messages.create(" in source


# ── OpenAI support ────────────────────────────────────────────────────────────

def test_cloud_llm_uses_openai_sdk():
    source = CLOUD_LLM.read_text()
    assert 'from openai import AsyncOpenAI' in source
    assert 'chat.completions.create(' in source


def test_cloud_llm_raises_on_unknown_provider():
    source = CLOUD_LLM.read_text()
    assert 'raise ValueError' in source
    assert 'Proveedor cloud LLM desconocido' in source


# ── Token usage normalization ─────────────────────────────────────────────────

def test_cloud_llm_normalizes_anthropic_token_usage():
    source = CLOUD_LLM.read_text()
    assert '_extract_token_usage' in source
    assert 'cache_creation_input_tokens' in source
    assert 'cache_read_input_tokens' in source


def test_cloud_llm_normalizes_openai_token_usage():
    source = CLOUD_LLM.read_text()
    assert 'prompt_tokens' in source
    assert 'completion_tokens' in source


# ── Orchestrator: cascade integra cloud LLM como tier-3 ──────────────────────

def test_orchestrator_imports_cloud_llm_answer():
    source = ORCHESTRATOR.read_text()
    assert 'from app.services.cloud_llm_answer import' in source
    assert 'build_cloud_llm_answer' in source
    assert 'build_conversational_cloud_llm_answer' in source


def test_orchestrator_has_is_cloud_llm_configured_helper():
    source = ORCHESTRATOR.read_text()
    assert '_is_cloud_llm_configured' in source
    assert 'cloud_llm_provider' in source
    assert 'cloud_llm_api_key' in source


def test_orchestrator_routes_cloud_llm_engine_standalone():
    source = ORCHESTRATOR.read_text()
    assert "engine == 'cloud_llm'" in source
    assert 'await build_cloud_llm_answer(' in source
    assert 'settings.cloud_llm_provider' in source
    assert 'settings.cloud_llm_model' in source
    assert 'settings.cloud_llm_api_key' in source


def test_orchestrator_cascade_tries_cloud_when_ollama_unavailable():
    source = ORCHESTRATOR.read_text()
    assert 'cascade.cloud_llm_attempt' in source
    assert 'cascade.cloud_llm_unavailable' in source
    assert 'cascade.cloud_llm_result' in source


def test_orchestrator_cascade_conversational_tries_cloud_when_ollama_unavailable():
    source = ORCHESTRATOR.read_text()
    assert 'cascade.cloud_llm_conv_attempt' in source
    assert 'cascade.cloud_llm_conv_unavailable' in source
    assert 'await build_conversational_cloud_llm_answer(' in source


def test_orchestrator_send_bot_reply_records_token_usage():
    source = ORCHESTRATOR.read_text()
    assert 'token_usage' in source
    assert "'token_usage'" in source
    assert 'cloud_llm_used' in source


def test_orchestrator_send_bot_reply_labels_engine_correctly():
    source = ORCHESTRATOR.read_text()
    assert "engine_label = 'cloud_llm'" in source
    assert "engine_label = 'local_llm'" in source
    assert "engine_label = 'template'" in source


# ── .env.example documenta cloud LLM ─────────────────────────────────────────

def test_env_example_documents_cloud_llm_vars():
    source = ENV_EXAMPLE.read_text()
    assert 'CLOUD_LLM_PROVIDER' in source
    assert 'CLOUD_LLM_MODEL' in source
    assert 'CLOUD_LLM_API_KEY' in source
    assert 'claude-sonnet-4-6' in source


def test_env_example_documents_cloud_llm_as_cascade_tier():
    source = ENV_EXAMPLE.read_text()
    assert 'cloud_llm' in source
    assert 'tier' in source.lower() or 'cloud' in source.lower()
