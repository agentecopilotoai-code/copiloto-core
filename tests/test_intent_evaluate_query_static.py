from tests._routes_aggregator import routes_aggregated_source

def _intent_evaluate_source() -> str:
    source = routes_aggregated_source()
    start = source.index("@tenant_admin_router.post('/intents/evaluate')")
    end = source.index("@tenant_admin_router.post('/knowledge/documents'", start)
    return source[start:end]


def test_intent_evaluate_does_not_cap_chunks_before_question_aware_ranking():
    """Ranker sees all candidates the query returns (up to the DoS cap).

    BUG-212 (fix-group-39, 2026-05-18): el SELECT antes era unbounded — un
    tenant admin con catálogo grande podía consumir memoria/CPU del worker
    pumping miles de chunks. El cap inicial pre-TASK-0079 era 1000 rows;
    restablecido como techo de DoS. El ranker Python sigue viendo todo lo
    que la query devuelve (hasta el cap); tenants realistas tienen <1000
    chunks activos.
    """
    source = _intent_evaluate_source()
    sql = source[source.index('select kc.id'):source.index('"""', source.index('select kc.id'))]

    # BUG-212: el `LIMIT 1000` ahora ES esperado (techo de DoS).
    assert 'limit 1000' in sql.lower(), (
        'BUG-212: el SELECT debe terminar con `limit 1000` como techo de DoS.'
    )
    assert 'rank_chunks(' in source
