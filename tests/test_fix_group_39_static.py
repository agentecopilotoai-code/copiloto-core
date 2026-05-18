"""Fix-group 39: Codex Security HIGH+MEDIUM — RAG/indexing DoS + leaks.

Cierra 3 findings (BUG-42 cloud LLM no_train queda diferido a fix-group-44
por scope — el orchestrator necesita threading de tenant_settings que
afecta varios call sites del cascade):

- **BUG-210** (HIGH, `app/api/v1/routes.py:9655 / 9846`): `index_knowledge_document`
  e `reindex_all_knowledge_documents` usaban `Depends(get_db)` que mantiene
  una conn de la pool (`max_size=10`) durante TODO el handler, incluida la
  llamada `build_indexing_result_async(...)` que hace 1 request al provider
  de embeddings (OpenAI / Voyage / Ollama) por chunk. Para docs grandes
  esto duraba 30s+. Admin malicioso con 10 reindexes concurrentes podía
  agotar la pool global y DoSear TODOS los tenants. Fix: drop de
  `Depends(get_db)` en ambos handlers; acquire conn ad-hoc en 2 fases
  (SELECT corto → embedding sin conn → INSERT transaccional corto).
- **BUG-211** (MEDIUM, `app/api/v1/routes.py:9701 / 9874`): el `detail=str(exc)`
  expuesto al cliente leakeaba errores raw del provider (API key prefixes,
  account/project IDs, request IDs, URLs de fallback). Tenant admin podía
  triggerear indexing y leer estos errores. Fix: log full server-side
  + audit metadata; cliente recibe mensaje genérico `'Embedding provider
  unavailable'`. ValueErrors (validation) siguen exponiendo el detalle.
- **BUG-212** (MEDIUM, `app/api/v1/routes.py:9281`): `evaluate_intent_retrieval`
  removió el `LIMIT 1000` en TASK-0079 — la consulta cargaba TODOS los
  chunks activos para que el filtro Python aplicara `min_score`. Tenant
  admin con catálogo grande podía consumir memoria/CPU. Fix: restablecer
  `LIMIT 1000` (mismo cap pre-TASK-0079) — el filtro Python sigue siendo
  necesario porque pgvector no enforce min_score del caller.
"""
from __future__ import annotations

from pathlib import Path


ROUTES = Path('app/api/v1/routes.py')


# ───── BUG-210 — pool DoS via indexing ───────────────────────────────────


def test_bug_210_index_knowledge_document_drops_get_db_dependency():
    src = ROUTES.read_text()
    fn_idx = src.find('async def index_knowledge_document(')
    assert fn_idx > 0
    next_def = src.find('\n@tenant_admin_router.post(\'/knowledge/reindex-all\')', fn_idx)
    block = src[fn_idx:next_def]
    # NO debe tener `Depends(get_db)` en el signature.
    sig_block = block.split('):')[0]
    assert 'Depends(get_db)' not in sig_block, (
        'BUG-210: `index_knowledge_document` ya NO debe usar `Depends(get_db)` '
        'en su signature — la conn se acquire ad-hoc en 2 fases para evitar '
        'retener pool slot durante el embedding call.'
    )
    # Debe usar `db.pool.acquire()` al menos 2 veces (Phase 1 + Phase 3).
    assert block.count('db.pool.acquire()') >= 2, (
        'BUG-210: el handler debe acquire conn ad-hoc en al menos 2 fases.'
    )


def test_bug_210_reindex_all_drops_get_db_dependency():
    src = ROUTES.read_text()
    fn_idx = src.find('async def reindex_all_knowledge_documents(')
    assert fn_idx > 0
    next_def = src.find('\n@tenant_admin_router.delete(\'/knowledge/documents/{document_id}\'', fn_idx)
    block = src[fn_idx:next_def]
    sig_block = block.split('):')[0]
    assert 'Depends(get_db)' not in sig_block, (
        'BUG-210: `reindex_all_knowledge_documents` ya NO debe usar `Depends(get_db)`.'
    )
    assert 'db.pool.acquire()' in block, (
        'BUG-210: el reindex-all handler debe acquire conn ad-hoc.'
    )


def test_bug_210_db_pool_is_imported():
    src = ROUTES.read_text()
    assert 'from app.db.pool import db, get_db, record_to_dict' in src, (
        'BUG-210: `db` debe estar importado desde `app.db.pool` para que '
        'los handlers refactoreados puedan usar `db.pool.acquire()`.'
    )


# ───── BUG-211 — embedding error leak ────────────────────────────────────


def test_bug_211_index_handler_returns_generic_502_message():
    src = ROUTES.read_text()
    fn_idx = src.find('async def index_knowledge_document(')
    assert fn_idx > 0
    next_def = src.find('\n@tenant_admin_router.post(\'/knowledge/reindex-all\')', fn_idx)
    block = src[fn_idx:next_def]
    # El cliente recibe el mensaje genérico cuando RuntimeError (provider).
    assert "client_detail = (\n                'Embedding provider unavailable." in block, (
        'BUG-211: el cliente debe recibir el mensaje genérico '
        '`Embedding provider unavailable` para errores del provider.'
    )
    # ValueError SÍ puede exponer el detalle (validation feedback).
    assert "if isinstance(exc, ValueError):\n            status_code = 422\n            client_detail = full_error" in block, (
        'BUG-211: ValueError (validation feedback) sí puede exponer el '
        'detalle al cliente.'
    )


def test_bug_211_reindex_all_redacts_provider_errors_in_array():
    src = ROUTES.read_text()
    fn_idx = src.find('async def reindex_all_knowledge_documents(')
    assert fn_idx > 0
    next_def = src.find('\n@tenant_admin_router.delete(\'/knowledge/documents/{document_id}\'', fn_idx)
    block = src[fn_idx:next_def]
    assert "'error': 'embedding_provider_unavailable'" in block, (
        'BUG-211: el array `errors` del reindex-all debe usar el code '
        '`embedding_provider_unavailable` (no `str(exc)` raw) para errores '
        'del provider. ValueErrors sí exponen detalle.'
    )


# ───── BUG-212 — intent eval candidate LIMIT ────────────────────────────


def test_bug_212_intent_evaluate_caps_candidate_chunks():
    src = ROUTES.read_text()
    fn_idx = src.find('async def evaluate_intent_retrieval(')
    assert fn_idx > 0
    next_def = src.find('\n@tenant_admin_router', fn_idx + 1)
    block = src[fn_idx:next_def] if next_def > 0 else src[fn_idx:fn_idx + 3000]
    # El SELECT de candidates debe tener un LIMIT — buscar limit 1000 explícito
    # dentro del SELECT de knowledge_chunks.
    select_idx = block.find('from app.knowledge_chunks kc')
    assert select_idx > 0
    select_block = block[select_idx:select_idx + 700]
    assert 'limit 1000' in select_block, (
        'BUG-212: el SELECT de `evaluate_intent_retrieval` debe terminar con '
        '`limit 1000` para bound el conjunto de candidatos que el ranker '
        'Python procesa.'
    )
