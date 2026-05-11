"""Static tests for TASK-0025: real embedding provider dispatcher and helpers.

These tests run without any API keys or network access.  They validate:
  (a) local_hash works without API key
  (b) dispatcher selects the correct provider based on config
  (c) vector dimensions are consistent with the schema
  (d) build_indexing_result falls back to local_hash in the sync path
  (e) async path accepts precomputed embeddings correctly
  (f) ANN retrieval helpers expose correct SQL and helpers
"""

import asyncio

import pytest

_run = asyncio.get_event_loop().run_until_complete

from app.services.rag_indexing import (
    SUPPORTED_REAL_PROVIDERS,
    _PROVIDER_DEFAULT_DIMS,
    build_indexing_result,
    build_indexing_result_async,
    chunk_document_text,
    deterministic_embedding,
    is_semantic_provider,
    real_embedding_async,
    vector_literal,
)
from app.services.rag_retrieval import (
    _ANN_CHUNK_SQL,
    _LEXICAL_CHUNK_SQL,
    ann_rows_to_matches,
    get_chunk_retrieval_sql,
)


# ── (a) local_hash works without API key ──────────────────────────────────────

def test_local_hash_produces_correct_dimension():
    vec = deterministic_embedding('hola mundo', dimensions=1536)
    assert len(vec) == 1536


def test_local_hash_produces_correct_dimension_custom():
    for dims in (8, 64, 1024, 1536):
        vec = deterministic_embedding('prueba', dimensions=dims)
        assert len(vec) == dims


def test_local_hash_is_normalized():
    vec = deterministic_embedding('texto de prueba', dimensions=32)
    norm_sq = sum(v * v for v in vec)
    assert abs(norm_sq - 1.0) < 1e-4


def test_local_hash_is_deterministic():
    a = deterministic_embedding('texto', dimensions=16)
    b = deterministic_embedding('texto', dimensions=16)
    assert a == b


def test_build_indexing_result_sync_uses_local_hash():
    doc = {'content': 'Hola. Esto es una prueba de indexación.', 'metadata': {}}
    result = build_indexing_result(doc, embedding_dimensions=16)
    assert result.embedding_provider == 'local_hash'
    assert all(len(c.embedding) == 16 for c in result.chunks)


# ── (b) dispatcher selects correct provider ───────────────────────────────────

def test_is_semantic_provider_returns_false_for_local_hash():
    assert is_semantic_provider('local_hash') is False


@pytest.mark.parametrize('provider', ['openai', 'anthropic', 'ollama'])
def test_is_semantic_provider_returns_true_for_real_providers(provider):
    assert is_semantic_provider(provider) is True


def test_supported_real_providers_list_is_complete():
    assert set(SUPPORTED_REAL_PROVIDERS) == {'openai', 'anthropic', 'ollama'}


def test_provider_default_dims_cover_all_providers():
    for provider in [*SUPPORTED_REAL_PROVIDERS, 'local_hash']:
        assert provider in _PROVIDER_DEFAULT_DIMS
        assert _PROVIDER_DEFAULT_DIMS[provider] > 0


def test_build_indexing_result_sync_falls_back_to_local_hash_for_real_providers():
    # Sync path cannot make API calls; must fall back transparently.
    doc = {'content': 'Contenido de prueba para provider real.', 'metadata': {}}
    for provider in SUPPORTED_REAL_PROVIDERS:
        result = build_indexing_result(
            doc,
            embedding_provider=provider,
            embedding_model='test-model',
            embedding_dimensions=16,
        )
        # Sync path silently uses local_hash
        assert result.embedding_provider == 'local_hash'
        assert all(len(c.embedding) == 16 for c in result.chunks)


# ── (c) vector dimensions are consistent with schema ─────────────────────────

def test_chunk_document_text_with_precomputed_embeddings():
    text = 'Primera oración del documento. Segunda oración con más contenido.'
    fake_embedding = [0.1, 0.2, 0.3, 0.4]
    chunks = chunk_document_text(
        text,
        max_tokens=10,
        overlap_tokens=2,
        embedding_dimensions=4,
        precomputed_embeddings=[fake_embedding, fake_embedding],
    )
    assert len(chunks) >= 1
    # First chunk uses the precomputed embedding
    assert chunks[0].embedding == fake_embedding


def test_chunk_document_text_falls_back_when_precomputed_exhausted():
    text = 'Primera parte. Segunda parte. Tercera parte con más tokens adicionales para forzar un chunk.'
    fake_embedding = [0.5, 0.5, 0.5, 0.5]
    # Provide only one precomputed embedding; extra chunks must use deterministic_embedding
    chunks = chunk_document_text(
        text,
        max_tokens=8,
        overlap_tokens=1,
        embedding_dimensions=4,
        precomputed_embeddings=[fake_embedding],
    )
    # First chunk matches precomputed
    assert chunks[0].embedding == fake_embedding
    # Subsequent chunks still have correct dimension
    for chunk in chunks[1:]:
        assert len(chunk.embedding) == 4


def test_vector_literal_format():
    vec = [0.1, -0.2, 0.3]
    literal = vector_literal(vec)
    assert literal.startswith('[') and literal.endswith(']')
    assert ',' in literal


# ── (d) build_indexing_result_async uses precomputed path ────────────────────

def test_build_indexing_result_async_local_hash_path():
    doc = {'content': 'Texto asíncrono de prueba para el path local.', 'metadata': {}}
    result = _run(build_indexing_result_async(
        doc,
        embedding_dimensions=8,
        embedding_provider='local_hash',
        embedding_model='copilotoia-local-hash-v1',
    ))
    assert result.embedding_provider == 'local_hash'
    assert len(result.chunks) >= 1
    assert all(len(c.embedding) == 8 for c in result.chunks)


def test_build_indexing_result_async_real_provider_falls_back_on_network_error():
    # With no API key the real_embedding_async call will fail; the async indexer
    # catches RuntimeError and substitutes a deterministic_embedding fallback.
    doc = {'content': 'Texto de prueba para proveedor real sin API key.', 'metadata': {}}
    result = _run(build_indexing_result_async(
        doc,
        embedding_dimensions=16,
        embedding_provider='openai',
        embedding_model='text-embedding-3-small',
        embedding_api_key=None,
    ))
    # Provider label stays 'openai'; embeddings fall back to local_hash dimension.
    assert result.embedding_provider == 'openai'
    assert all(len(c.embedding) == 16 for c in result.chunks)


# ── real_embedding_async raises for unknown provider ─────────────────────────

def test_real_embedding_async_raises_for_unknown_provider():
    with pytest.raises(ValueError, match='Unknown embedding provider'):
        _run(real_embedding_async(
            'texto',
            provider='unknown_provider',
            model='model',
            api_key=None,
            dimensions=16,
        ))


# ── (e) ANN retrieval SQL helpers ─────────────────────────────────────────────

def test_get_chunk_retrieval_sql_returns_ann_for_real_providers():
    for provider in SUPPORTED_REAL_PROVIDERS:
        sql = get_chunk_retrieval_sql(provider)
        assert sql == _ANN_CHUNK_SQL
        assert '<=>` ' in sql or '<=>' in sql


def test_get_chunk_retrieval_sql_returns_lexical_for_local_hash():
    sql = get_chunk_retrieval_sql('local_hash')
    assert sql == _LEXICAL_CHUNK_SQL
    assert '<=>' not in sql


def test_ann_rows_to_matches_converts_cosine_similarity():
    from uuid import uuid4
    rows = [
        {
            'id': uuid4(),
            'document_id': uuid4(),
            'document_title': 'Doc A',
            'source_uri': None,
            'source_type': 'manual',
            'document_type': 'faq',
            'visibility': 'tenant',
            'chunk_index': 0,
            'section_path': 'Sección',
            'chunk_text': 'Texto relevante sobre el tema.',
            'token_count': 10,
            'metadata': {},
            'cosine_similarity': 0.87,
        }
    ]
    matches = ann_rows_to_matches(rows)
    assert len(matches) == 1
    assert matches[0].score == 0.87
    assert matches[0].matched_terms == []


def test_ann_rows_to_matches_filters_zero_score():
    from uuid import uuid4
    rows = [
        {
            'id': uuid4(),
            'document_id': uuid4(),
            'document_title': 'Doc B',
            'source_uri': None,
            'source_type': 'manual',
            'document_type': 'faq',
            'visibility': 'tenant',
            'chunk_index': 0,
            'section_path': None,
            'chunk_text': 'Texto.',
            'token_count': 5,
            'metadata': {},
            'cosine_similarity': 0.0,
        }
    ]
    matches = ann_rows_to_matches(rows)
    assert len(matches) == 0


def test_ann_rows_to_matches_respects_max_chunks():
    from uuid import uuid4
    rows = [
        {
            'id': uuid4(),
            'document_id': uuid4(),
            'document_title': f'Doc {i}',
            'source_uri': None,
            'source_type': 'manual',
            'document_type': 'faq',
            'visibility': 'tenant',
            'chunk_index': i,
            'section_path': None,
            'chunk_text': f'Texto {i}.',
            'token_count': 5,
            'metadata': {},
            'cosine_similarity': 0.9 - i * 0.01,
        }
        for i in range(10)
    ]
    matches = ann_rows_to_matches(rows, max_chunks=3)
    assert len(matches) == 3
