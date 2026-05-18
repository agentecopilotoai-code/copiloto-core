"""Fix-group 26: BUG-148..BUG-152.

- BUG-148: NOT-APPLICABLE. `cloud-llm-rate-limited.md` ya aclara que
  `answer_engine`/`cloud_llm_provider` son env vars del servidor
  (`app.tenant_settings` no las tiene). El SQL de diagnóstico usa
  `payload->>'answer_engine'` correctamente.
- BUG-149: NOT-APPLICABLE. La idempotency key en
  `outbound_dlq.py::requeue_message` es `message-retry:{id}:{retry_count}`,
  no epoch-second. Dos retries concurrentes están serializados por el
  UPDATE atómico sobre `status='failed'`.
- BUG-150: NOT-APPLICABLE. `operator_alerts._render_email_for_kind` y
  `_render_template_components_for_kind` rutean por
  `_resolve_alert_kind(payload) == ALERT_KIND_OUTBOUND_DLQ_THRESHOLD`
  a builders dedicados (`_build_outbound_dlq_*`), no al builder de
  negative_feedback.
- BUG-151: VIGENTE. `docker-compose.yml` defaulteaba
  `BACKUP_S3_ENDPOINT=http://minio:9000`, lo que silently rutaba los
  backups de prod al MinIO local cuando la env var no estaba seteada.
  Fix: default a empty (el aws-cli usa el endpoint AWS real si vacío).
  Para correr local, el operador setea la var explícitamente.
- BUG-152: NOT-APPLICABLE. `docs/ARCHITECTURE.md` no existe en el repo
  actual (fue removido / nunca commiteado); el conflicto reportado por
  el review-bot ya no aplica.
"""
from __future__ import annotations

from pathlib import Path


DOCKER_COMPOSE = Path('docker-compose.yml')
OUTBOUND_DLQ = Path('app/services/outbound_dlq.py')
OPERATOR_ALERTS = Path('app/services/operator_alerts.py')
RB_CLOUD_LLM = Path('docs/runbooks/cloud-llm-rate-limited.md')
ARCH_DOC = Path('docs/ARCHITECTURE.md')


# ───── BUG-148 — runbook usa columnas/paths reales ──────────────────────


def test_bug_148_cloud_llm_runbook_uses_payload_jsonb_path():
    src = RB_CLOUD_LLM.read_text()
    # El SQL de diagnóstico debe acceder via `payload->>'answer_engine'`
    # (las settings vienen del payload del mensaje, no de tenant_settings).
    assert "payload->>'answer_engine'" in src, (
        "BUG-148: el runbook debe usar `payload->>'answer_engine'` para "
        "extraer la marca del engine del mensaje (no `tenant_settings.*`)."
    )
    # Debe haber un disclaimer explicando que son env vars del server.
    assert 'settings' in src.lower() and ('env var' in src.lower() or 'variable' in src.lower()), (
        "BUG-148: el runbook debe aclarar que `answer_engine`/"
        "`cloud_llm_provider` son env vars del server, no columnas."
    )


# ───── BUG-149 — idempotency key estable por retry_count ─────────────────


def test_bug_149_outbound_dlq_idempotency_key_uses_retry_count():
    src = OUTBOUND_DLQ.read_text()
    assert "f'message-retry:{message_id}:{retry_count}'" in src, (
        "BUG-149: la idempotency key debe ser `message-retry:{id}:{retry_count}`, "
        "no incluir epoch-second (dos retries en el mismo segundo colisionarían)."
    )


# ───── BUG-150 — dispatcher rutea por alert kind ─────────────────────────


def test_bug_150_operator_alerts_dispatches_outbound_dlq_kind_separately():
    src = OPERATOR_ALERTS.read_text()
    # Constante para el kind.
    assert "ALERT_KIND_OUTBOUND_DLQ_THRESHOLD = 'outbound_dlq_threshold'" in src, (
        "BUG-150: debe existir la constante "
        "`ALERT_KIND_OUTBOUND_DLQ_THRESHOLD` para el kind del DLQ alert."
    )
    # El switch del email builder rutea por kind.
    assert '_resolve_alert_kind(payload) == ALERT_KIND_OUTBOUND_DLQ_THRESHOLD' in src, (
        "BUG-150: los builders de email y template deben switch por "
        "`_resolve_alert_kind(payload)`, no producir formato de "
        "negative_feedback para el kind DLQ."
    )


# ───── BUG-151 — docker-compose default no rutea a MinIO local ───────────


def test_bug_151_docker_compose_backup_endpoint_defaults_to_empty():
    src = DOCKER_COMPOSE.read_text()
    assert 'BACKUP_S3_ENDPOINT: ${BACKUP_S3_ENDPOINT:-}' in src, (
        "BUG-151: el default de `BACKUP_S3_ENDPOINT` debe ser empty (no "
        "`http://minio:9000`). Sino, instalaciones de prod que olvidan "
        "setear la var rutean los backups al MinIO local del compose y "
        "corrompen la pipeline."
    )
    assert 'http://minio:9000' not in src or '# ' in src.split('BACKUP_S3_ENDPOINT')[0][-200:], (
        "BUG-151: no usar `http://minio:9000` como default activo en "
        "docker-compose.yml. Si aparece, debe estar comentado como ejemplo."
    )


# ───── BUG-152 — referenced file no existe ───────────────────────────────


def test_bug_152_architecture_doc_absence_documented():
    """Si alguien crea docs/ARCHITECTURE.md y mete un warning singleton que
    contradice la sección "todos usan FOR UPDATE SKIP LOCKED", BUG-152
    vuelve a aplicar — el reviewer debe alinear los dos.
    """
    # El review-bot reportó el conflicto cuando el archivo existía. Hoy no
    # existe, así que el conflicto no aplica. Este test solo deja constancia.
    if ARCH_DOC.exists():
        src = ARCH_DOC.read_text()
        # Si existe, NO debe mencionar singleton + FOR UPDATE SKIP LOCKED en
        # forma contradictoria. Defensa simple: si menciona ambos términos,
        # debe explicarlos como compatibles, no como mutuamente excluyentes.
        if 'singleton' in src.lower() and 'FOR UPDATE SKIP LOCKED' in src:
            assert 'NOT' not in src.split('singleton')[1][:200].upper() or (
                'compatible' in src.lower()
            ), (
                "BUG-152: si ARCHITECTURE.md menciona singleton + FOR UPDATE "
                "SKIP LOCKED, ambos conceptos deben describirse como "
                "compatibles (workers múltiples + selector ordenado)."
            )
