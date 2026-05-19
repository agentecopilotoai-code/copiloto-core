"""Fix-group 41: Codex Security MEDIUM — PII/logging hygiene.

- **BUG-215** (MEDIUM, `app/services/platform_incidents.py`): `_PII_PAYLOAD_KEYS`
  no incluía `inbound_body_excerpt`, `comment_preview`, `conversation_url`,
  `contact_id`, `feedback_id`, `appointment_id`. Estos campos pasaban
  tal cual al feed `/platform/incidents` que el platform_owner consulta
  cross-tenant — exponiendo customer-facing message excerpts, comments,
  y URLs/IDs que permiten pivotar al admin panel del tenant víctima.
- **BUG-216** (MEDIUM, `app/api/v1/routes.py:list_conversations`): el
  `digest_worker` escribe los KPIs semanales como messages outbound en
  una "conversación interna" marcada `metadata.kind = 'internal_digest'`.
  `list_conversations` (rol agent+) no filtraba esa key — cualquier agent
  podía listar conversaciones, abrir la interna, y leer analytics
  manager/admin-only (violando RBAC del módulo de digests).
- **BUG-217** (MEDIUM, `app/services/rag_orchestrator.py`): los logs
  `orchestrator.received` y `orchestrator.conversational_result` emitían
  `body_preview=body_text[:80]` y `answer_preview=answer[:120]` a INFO
  level — capturados por agregadores externos. El body/answer contiene
  nombres, direcciones, payment details, etc. Fix: solo loggear digest
  + length para correlación operativa sin exponer contenido.
"""
from __future__ import annotations

from pathlib import Path
from tests._routes_aggregator import routes_aggregated_source


PLATFORM_INCIDENTS = Path('app/services/platform_incidents.py')
ORCHESTRATOR = Path('app/services/rag_orchestrator.py')


# ───── BUG-215 — incidents redactor cubre body/url/IDs ─────────────────


def test_bug_215_pii_keys_include_inbound_body_excerpt():
    src = PLATFORM_INCIDENTS.read_text()
    fn_idx = src.find('_PII_PAYLOAD_KEYS = frozenset({')
    end = src.find('})', fn_idx)
    block = src[fn_idx:end]
    for key in (
        'inbound_body_excerpt',
        'comment_preview',
        'conversation_url',
        'contact_id',
        'feedback_id',
        'appointment_id',
    ):
        assert f"'{key}'" in block, (
            f'BUG-215: `_PII_PAYLOAD_KEYS` debe incluir `{key}` para '
            f'redactarlo del feed `/platform/incidents`.'
        )


# ───── BUG-216 — list_conversations excluye internal_digest ─────────────


def test_bug_216_list_conversations_excludes_internal_digest():
    src = routes_aggregated_source()
    fn_idx = src.find('@tenant_ops_router.get(\'/conversations\')\nasync def list_conversations(')
    assert fn_idx > 0
    next_fn = src.find('\n@tenant_ops_router', fn_idx + 10)
    block = src[fn_idx:next_fn]
    assert "coalesce(c.metadata->>'kind', '') <> 'internal_digest'" in block, (
        'BUG-216: el SELECT debe excluir conversations con '
        '`metadata.kind = internal_digest` (digest_worker las crea con KPIs '
        'manager-only que el agent NO debe ver).'
    )


# ───── BUG-217 — orchestrator logs digest no preview ───────────────────


def test_bug_217_orchestrator_received_log_redacts_body():
    src = ORCHESTRATOR.read_text()
    # Buscar el log call de orchestrator.received.
    idx = src.find("'orchestrator.received'")
    assert idx > 0
    # Bloque entre log.info y el close paren
    block_start = src.rfind('log.info(', 0, idx)
    # find the `,\n    )` close (multi-line log call).
    block_end = src.find('\n    )', block_start)
    block = src[block_start:block_end + 6]
    assert 'body_preview=' not in block, (
        'BUG-217: `orchestrator.received` ya NO debe loggear `body_preview` '
        '(primeros 80 chars del body) — el body puede contener PII.'
    )
    assert 'body_digest=' in block, (
        'BUG-217: `orchestrator.received` debe loggear `body_digest` (hash) '
        'para correlación operativa sin exponer contenido.'
    )


def test_bug_217_orchestrator_conversational_result_redacts_answer():
    src = ORCHESTRATOR.read_text()
    idx = src.find("'orchestrator.conversational_result'")
    assert idx > 0
    block_start = src.rfind('log.info(', 0, idx)
    # find the `,\n    )` close (multi-line log call).
    block_end = src.find('\n    )', block_start)
    block = src[block_start:block_end + 6]
    assert 'answer_preview=' not in block, (
        'BUG-217: `orchestrator.conversational_result` ya NO debe loggear '
        '`answer_preview` (primeros 120 chars del LLM answer).'
    )
    assert 'answer_digest=' in block, (
        'BUG-217: debe loggear `answer_digest` (hash) para correlación.'
    )
