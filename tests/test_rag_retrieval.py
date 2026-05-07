from uuid import uuid4

from app.services.rag_retrieval import build_grounded_answer, rank_chunks, retrieval_match_to_dict


def chunk(text, **overrides):
    document_id = uuid4()
    data = {
        'id': uuid4(),
        'document_id': document_id,
        'document_title': 'FAQ garantías',
        'source_uri': 'https://example.test/faq',
        'source_type': 'url',
        'document_type': 'faq',
        'visibility': 'tenant',
        'chunk_index': 0,
        'section_path': 'Garantías',
        'chunk_text': text,
        'token_count': 20,
        'metadata': {'category': 'postventa'},
    }
    data.update(overrides)
    return data


def test_rank_chunks_returns_traceable_sources_ordered_by_score():
    matches = rank_chunks(
        '¿Cuánto dura la garantía del servicio?',
        [
            chunk('La garantía del servicio dura 30 días calendario.'),
            chunk('Atendemos de lunes a viernes.', document_title='Horarios', section_path='Horarios'),
        ],
    )

    assert len(matches) == 1
    assert matches[0].document_title == 'FAQ garantías'
    assert matches[0].visibility == 'tenant'
    assert matches[0].source_uri == 'https://example.test/faq'
    assert matches[0].score >= 0.12
    assert {'garantia', 'servicio'} <= set(matches[0].matched_terms)


def test_build_grounded_answer_requires_minimum_evidence_before_answering():
    matches = rank_chunks('precio de instalación', [chunk('La garantía dura 30 días.')])

    answer = build_grounded_answer('precio de instalación', matches)

    assert answer['status'] == 'escalate_to_human'
    assert answer['sufficient_context'] is False
    assert answer['answer'] is None
    assert answer['handoff']['required'] is True


def test_build_grounded_answer_uses_best_chunk_when_context_is_sufficient():
    matches = rank_chunks('garantía servicio', [chunk('La garantía del servicio dura 30 días calendario.')])

    answer = build_grounded_answer('garantía servicio', matches)
    serialized_chunk = retrieval_match_to_dict(matches[0])

    assert answer['status'] == 'answered'
    assert answer['sufficient_context'] is True
    assert 'FAQ garantías' in answer['answer']
    assert '30 días' in answer['answer']
    assert serialized_chunk['score'] == matches[0].score
    assert serialized_chunk['excerpt']

