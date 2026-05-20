"""Static tests for TASK-0078: agents_only filter must not leak to end users.

Covers BUG10 (cloud LLM payload), BUG12 (multi-chunk template concatenation) and
BUG13 (WhatsApp inbound response). Tests assert two layers of defense:
  1. SQL retrieval excludes agents_only via ``WHERE kd.visibility = ANY($N)``.
  2. Builders (``build_grounded_answer``, ``_build_context`` for cloud + local
     LLM) defensively skip any ``agents_only`` chunk that slips through.
"""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.chatbot.cloud_llm_answer import _build_context as cloud_build_context
from app.chatbot.llm_answer import _build_context as local_build_context
from app.services.rag_retrieval import (
    ALL_VISIBILITY,
    END_USER_VISIBILITY,
    RetrievalMatch,
    _ANN_CHUNK_SQL,
    _LEXICAL_CHUNK_SQL,
    build_grounded_answer,
    filter_end_user_matches,
    rank_chunks,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
ROUTES = REPO_ROOT / 'app' / 'api' / 'v1' / 'routes.py'
ORCH = REPO_ROOT / 'app' / 'services' / 'rag_orchestrator.py'


def _match(text: str, *, visibility: str, score: float = 0.95) -> RetrievalMatch:
    return RetrievalMatch(
        id=uuid4(),
        document_id=uuid4(),
        document_title=f'Doc-{visibility}',
        source_uri=None,
        source_type='manual',
        document_type='reference',
        visibility=visibility,
        chunk_index=0,
        section_path=None,
        chunk_text=text,
        token_count=20,
        score=score,
        matched_terms=['x'],
        metadata={},
    )


# ── BUG13: end-user response path drops agents_only chunks ────────────────────


def test_build_grounded_answer_drops_agents_only_chunk_ranked_first():
    """BUG13: el chunk #1 es agents_only → la respuesta saliente NO lo incluye."""
    matches = [
        _match('CONFIDENCIAL: descuento staff 50%.', visibility='agents_only', score=0.92),
        _match('La garantía dura 30 días calendario.', visibility='tenant', score=0.88),
    ]

    answer = build_grounded_answer('garantía', matches)

    assert answer['status'] == 'answered'
    assert 'CONFIDENCIAL' not in (answer['answer'] or '')
    assert 'staff 50%' not in (answer['answer'] or '')
    assert '30 días' in answer['answer']


def test_build_grounded_answer_escalates_when_only_agents_only_matches():
    matches = [_match('Solo personal interno: protocolo X.', visibility='agents_only', score=0.99)]

    answer = build_grounded_answer('protocolo', matches)

    assert answer['status'] == 'escalate_to_human'
    assert answer['sufficient_context'] is False
    assert answer['answer'] is None


# ── BUG12: even when concatenating multiple chunks, agents_only is excluded ──


def test_build_grounded_answer_filters_agents_only_when_ranked_second():
    """BUG12: chunk public #1 + chunk agents_only #2 → respuesta NO trae el #2."""
    matches = [
        _match('La garantía es 30 días.', visibility='public', score=0.91),
        _match('NOTA INTERNA: clientes premium reciben 90 días.', visibility='agents_only', score=0.80),
    ]

    answer = build_grounded_answer('garantía', matches)

    assert answer['status'] == 'answered'
    assert 'NOTA INTERNA' not in answer['answer']
    assert 'premium' not in answer['answer']


# ── BUG10: cloud LLM context never receives agents_only text ─────────────────


def test_cloud_llm_context_excludes_agents_only_chunks():
    """BUG10: el payload enviado al SDK Anthropic/OpenAI no debe contener agents_only."""
    matches = [
        _match('SECRETO STAFF: política interna de devoluciones.', visibility='agents_only', score=0.95),
        _match('La garantía pública es 30 días.', visibility='tenant', score=0.85),
    ]

    context = cloud_build_context(matches, min_score=0.12)

    assert 'SECRETO STAFF' not in context
    assert 'política interna' not in context
    assert 'garantía pública' in context


def test_local_llm_context_excludes_agents_only_chunks():
    matches = [
        _match('INTERNO: comisión vendedor 12%.', visibility='agents_only', score=0.95),
        _match('Horario de atención: 8 a 18.', visibility='tenant', score=0.85),
    ]

    context = local_build_context(matches, min_score=0.12)

    assert 'INTERNO' not in context
    assert 'comisión' not in context
    assert 'Horario de atención' in context


# ── Admin override: include_agents_only=True keeps the chunks visible ────────


def test_admin_override_includes_agents_only_chunks_in_answer():
    matches = [
        _match('Protocolo interno detallado.', visibility='agents_only', score=0.95),
    ]

    answer = build_grounded_answer(
        'protocolo',
        matches,
        allow_agents_only=True,
    )

    assert answer['status'] == 'answered'
    assert 'Protocolo interno' in answer['answer']


def test_intent_evaluate_request_schema_defaults_include_agents_only_false():
    from app.api.v1.schemas import IntentEvaluateRequest

    payload = IntentEvaluateRequest(question='¿garantía?')
    assert payload.include_agents_only is False

    opted_in = IntentEvaluateRequest(question='¿protocolo interno?', include_agents_only=True)
    assert opted_in.include_agents_only is True


# ── SQL retrieval layer: visibility allowlist enforced as ANY($N::text[]) ────


def test_ann_chunk_sql_filters_visibility_allowlist():
    assert 'kd.visibility = ANY($4::text[])' in _ANN_CHUNK_SQL


def test_lexical_chunk_sql_filters_visibility_allowlist():
    assert 'kd.visibility = ANY($2::text[])' in _LEXICAL_CHUNK_SQL


def test_orchestrator_inline_retrieval_sql_filters_visibility():
    """The orchestrator's own inline SQL (not the helpers) must also filter."""
    source = ORCH.read_text()
    # Find the retrieval block after the `Retrieve active knowledge chunks` comment.
    anchor = 'Retrieve active knowledge chunks'
    assert anchor in source
    block = source[source.index(anchor): source.index(anchor) + 1500]
    assert 'kd.visibility = ANY($2::text[])' in block
    assert 'END_USER_VISIBILITY' in source


def test_readiness_retrieval_sql_filters_visibility():
    source = ROUTES.read_text()
    # The tenant readiness check around `knowledge_retrieval`.
    idx = source.index("'knowledge_retrieval'")
    block = source[max(0, idx - 1500): idx + 1500]
    assert 'kd.visibility = ANY($2::text[])' in block
    assert 'END_USER_VISIBILITY' in block


def test_intent_evaluate_endpoint_respects_include_agents_only_flag():
    # Refactor phase 3: tenant_admin handlers live in
    # app/api/v1/handlers/tenant_admin_handlers.py — use the aggregated source.
    from tests._routes_aggregator import routes_aggregated_source

    source = routes_aggregated_source()
    start = source.index("@tenant_admin_router.post('/intents/evaluate')")
    end = source.index("@tenant_admin_router.post('/knowledge/documents'", start)
    block = source[start:end]
    assert 'payload.include_agents_only' in block
    assert 'visibility_filter' in block
    assert 'ALL_VISIBILITY' in block
    assert 'END_USER_VISIBILITY' in block
    assert 'kd.visibility = ANY($2::text[])' in block


# ── Constants sanity ─────────────────────────────────────────────────────────


def test_end_user_visibility_excludes_agents_only():
    assert 'agents_only' not in END_USER_VISIBILITY
    assert 'tenant' in END_USER_VISIBILITY
    assert 'public' in END_USER_VISIBILITY


def test_all_visibility_includes_agents_only():
    assert set(ALL_VISIBILITY) == {'tenant', 'public', 'agents_only'}


def test_filter_end_user_matches_helper_strips_agents_only():
    matches = [
        _match('public text', visibility='public'),
        _match('agents only text', visibility='agents_only'),
        _match('tenant text', visibility='tenant'),
    ]

    filtered = filter_end_user_matches(matches)

    visibilities = {m.visibility for m in filtered}
    assert visibilities == {'public', 'tenant'}


# ── End-to-end via rank_chunks + build_grounded_answer ───────────────────────


def test_rank_chunks_then_grounded_answer_blocks_agents_only_end_to_end():
    chunks = [
        {
            'id': uuid4(),
            'document_id': uuid4(),
            'document_title': 'Interno staff',
            'source_uri': None,
            'source_type': 'manual',
            'document_type': 'reference',
            'visibility': 'agents_only',
            'chunk_index': 0,
            'section_path': None,
            'chunk_text': 'Descuento STAFF aplicar código X42.',
            'token_count': 10,
            'metadata': {},
        },
        {
            'id': uuid4(),
            'document_id': uuid4(),
            'document_title': 'FAQ pública',
            'source_uri': None,
            'source_type': 'manual',
            'document_type': 'faq',
            'visibility': 'tenant',
            'chunk_index': 0,
            'section_path': None,
            'chunk_text': 'El descuento promocional vigente es del 10%.',
            'token_count': 10,
            'metadata': {},
        },
    ]

    matches = rank_chunks('descuento', chunks)
    answer = build_grounded_answer('descuento', matches)

    assert answer['status'] == 'answered'
    assert 'X42' not in (answer['answer'] or '')
    assert 'STAFF' not in (answer['answer'] or '')
