from pathlib import Path

ROUTES = Path('app/api/v1/routes.py')


def _intent_evaluate_source() -> str:
    source = ROUTES.read_text()
    start = source.index("@tenant_admin_router.post('/intents/evaluate')")
    end = source.index("@tenant_admin_router.post('/knowledge/documents'", start)
    return source[start:end]


def test_intent_evaluate_does_not_cap_chunks_before_question_aware_ranking():
    source = _intent_evaluate_source()
    sql = source[source.index('select kc.id'):source.index('"""', source.index('select kc.id'))]

    assert 'limit 1000' not in sql.lower()
    assert 'rank_chunks(' in source
