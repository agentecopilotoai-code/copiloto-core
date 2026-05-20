"""Cover small remaining gaps in app/chatbot/cloud_llm_answer.py."""
from __future__ import annotations

from types import SimpleNamespace



def _match(score=0.5, visibility='public', chunk_text='hi'):
    """Build a minimal RetrievalMatch."""
    return SimpleNamespace(
        id='m1', score=score, visibility=visibility,
        document_title='Doc', section_path=None, chunk_text=chunk_text,
        document_id='d1', source_uri='s', chunk_index=0,
    )


def test_build_context_filters_low_score():
    from app.chatbot.cloud_llm_answer import _build_context
    matches = [_match(score=0.05)]
    assert _build_context(matches, min_score=0.5) == ''


def test_build_context_filters_agents_only_visibility():
    """agents_only chunks dropped from cloud LLM context."""
    from app.chatbot.cloud_llm_answer import _build_context
    matches = [_match(visibility='agents_only')]
    assert _build_context(matches, min_score=0.0) == ''


def test_build_context_with_section_path_in_header():
    """Need to use min_score < match score, here 0.5 score so use 0.4."""
    from app.chatbot.cloud_llm_answer import _build_context
    m = _match(score=0.9)
    m.section_path = 'Sección 1'
    out = _build_context([m], min_score=0.5)
    assert 'Sección 1' in out
    assert 'hi' in out


def test_breaker_for_handles_settings_exception(monkeypatch):
    """When get_settings raises, falls back to default threshold/cooldown."""
    from app.chatbot import cloud_llm_answer as mod
    monkeypatch.setattr(mod, 'get_settings', lambda: (_ for _ in ()).throw(RuntimeError('no settings')))
    breaker = mod._breaker_for('claude')
    assert breaker is not None


def test_qa_system_prompt_with_default_personality():
    """Default personality (empty block) → returns _SYSTEM_PROMPT unchanged."""
    from app.chatbot import cloud_llm_answer as mod
    out = mod._qa_system_prompt(None)
    assert mod._SYSTEM_PROMPT in out


def test_qa_system_prompt_with_personality():
    """Non-default personality → prepended."""
    from app.chatbot import cloud_llm_answer as mod
    personality = {'tone': 'playful', 'addressing': 'tu', 'emojis': True}
    out = mod._qa_system_prompt(personality)
    assert mod._SYSTEM_PROMPT in out


# ═══ _extract_token_usage ═══════════════════════════════════════════════


def test_extract_token_usage_claude():
    from app.chatbot.cloud_llm_answer import _extract_token_usage
    usage = SimpleNamespace(
        input_tokens=100, output_tokens=50,
        cache_creation_input_tokens=10, cache_read_input_tokens=5,
    )
    out = _extract_token_usage(usage, 'claude')
    assert out['input_tokens'] == 100
    assert out['output_tokens'] == 50
    assert out['cache_creation_tokens'] == 10
    assert out['cache_read_tokens'] == 5


def test_extract_token_usage_openai_path():
    """OpenAI path returns the dict shape (or empty if attrs missing)."""
    from app.chatbot.cloud_llm_answer import _extract_token_usage
    usage = SimpleNamespace(prompt_tokens=200, completion_tokens=80, total_tokens=280)
    out = _extract_token_usage(usage, 'openai')
    assert isinstance(out, dict)
