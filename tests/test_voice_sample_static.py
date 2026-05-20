"""Static tests para voice sample + captions preview — TASK-INFLU-013."""
from __future__ import annotations

from pathlib import Path

from app.influencer.voice_router import (
    SAMPLE_DEFAULT_TEXT,
    build_caption_system_prompt,
    voice_router,
)


def test_two_endpoints_registered():
    paths = {(r.path, tuple(sorted(r.methods))) for r in voice_router.routes}
    base = '/v1/influencer/personas/{persona_id}/voice'
    assert any(p[0] == f'{base}/sample' and 'POST' in p[1] for p in paths)
    assert any(p[0] == f'{base}/captions-preview' and 'POST' in p[1] for p in paths)


def test_sample_default_text_matches_design_html():
    """El texto fijo del paso 4 del wizard debe ser consistente con el HTML."""
    assert 'Hola chicas' in SAMPLE_DEFAULT_TEXT
    assert 'verano' in SAMPLE_DEFAULT_TEXT


def test_build_caption_prompt_includes_voice_traits():
    voice = {'tone': 'cálida', 'formality': 'informal', 'energy_level': 7}
    prompt = build_caption_system_prompt(voice)
    assert 'cálida' in prompt
    assert 'informal' in prompt
    assert '7/10' in prompt


def test_prompt_differs_per_tone():
    """Snapshot: 'cálida' produce un prompt distinto a 'aspiracional'."""
    p1 = build_caption_system_prompt({'tone': 'cálida', 'energy_level': 5})
    p2 = build_caption_system_prompt({'tone': 'aspiracional', 'energy_level': 5})
    assert p1 != p2
    assert 'cálida' in p1
    assert 'aspiracional' in p2


def test_prompt_handles_empty_voice():
    prompt = build_caption_system_prompt({})
    assert 'neutral' in prompt  # default tone + formality


def test_sample_endpoint_uses_generations_queue():
    """Voice sample reusa la cola generations con kind='voice_sample'."""
    src = Path('app/influencer/voice_router.py').read_text(encoding='utf-8')
    assert "kind='voice_sample'" in src or "'voice_sample'" in src
    assert 'influencer.generations' in src


def test_voice_traits_passed_in_params():
    """El params jsonb del generation debe incluir el voice traits para
    que el worker arme PersonaAnchor."""
    src = Path('app/influencer/voice_router.py').read_text(encoding='utf-8')
    assert 'voice_traits' in src


def test_router_mounted_in_main():
    main_src = Path('app/main.py').read_text(encoding='utf-8')
    assert 'influencer_voice_router' in main_src
