"""Fix-group 02: BUG-028..BUG-032.

- BUG-028: NOT-APPLICABLE — la FK `fk_contacts_referrer` ya quedó con
  `(referrer_contact_id)` en BUG-027 (fix-group-01). Mismo bug, mismo fix.
- BUG-029: VIGENTE. `_send_whatsapp_channel` insertaba `conversation_id=null`
  en `app.messages` (NOT NULL) → todo WhatsApp alert fallaba.
- BUG-030: NOT-APPLICABLE — `digest_worker._ensure_internal_digest_conversation`
  ya crea synthetic contact+conversation antes del insert.
- BUG-031: NOT-APPLICABLE — `require_platform_owner` ya chequea
  `'platform_owner' not in roles` (no `'owner'`).
- BUG-032: NOT-APPLICABLE — `scripts/configure-auth0.sh` ya crea
  `platform_owner` rol en `role_names=(...)`.

Tests AST/source-grep para defender vigencia post-fix.
"""
from __future__ import annotations

import inspect
import textwrap
from pathlib import Path

from app.services import operator_alerts


SCHEMA = Path('infra/postgres/01-schema.sql')
CONFIGURE_AUTH0 = Path('scripts/configure-auth0.sh')


def _source_of_alerts(name: str) -> str:
    return textwrap.dedent(inspect.getsource(getattr(operator_alerts, name)))


# ───── BUG-028 — NOT-APPLICABLE (re-defensa post fix-group-01) ───────────


def test_bug_028_referrer_fk_specifies_column():
    """BUG-028 dup de BUG-027. La FK debe seguir con `(referrer_contact_id)`."""
    src = SCHEMA.read_text()
    assert 'on delete set null (referrer_contact_id)' in src, (
        'BUG-028/027: regresión — la FK `fk_contacts_referrer` perdió el '
        'column specifier; borrar referrer vuelve a fallar por tenant_id NOT NULL.'
    )


# ───── BUG-029 — alerts WhatsApp con conversación real ───────────────────


def test_bug_029_helper_ensures_alert_conversation_exists():
    """`_ensure_operator_alert_conversation` debe existir y devolver UUID."""
    assert hasattr(operator_alerts, '_ensure_operator_alert_conversation'), (
        'BUG-029: el helper `_ensure_operator_alert_conversation` debe existir '
        'en app/services/operator_alerts.py — sin él, el insert sigue con '
        'conversation_id=null y falla.'
    )


def test_bug_029_send_whatsapp_no_longer_inserts_null_conversation():
    """`_send_whatsapp_channel` NO debe pasar `null` como conversation_id en
    el INSERT. Debe llamar a `_ensure_operator_alert_conversation` antes y
    pasar el UUID resultante.
    """
    source = _source_of_alerts('_send_whatsapp_channel')
    assert '_ensure_operator_alert_conversation' in source, (
        'BUG-029: `_send_whatsapp_channel` debe invocar '
        '`_ensure_operator_alert_conversation` para obtener un conversation_id '
        'válido antes del INSERT.'
    )
    # El INSERT debe usar $2 (conversation_id), no `null`.
    assert "values ($1, null" not in source, (
        'BUG-029: regresión — el INSERT volvió a hardcodear `null` como '
        'conversation_id. Esto rompe `app.messages.conversation_id NOT NULL`.'
    )
    assert "values ($1, $2, 'outbound'" in source, (
        'BUG-029: el INSERT debe pasar el conversation_id real como $2.'
    )


def test_bug_029_helper_uses_kind_marker_to_avoid_pollution():
    """El conversation lookup debe filtrar por `metadata->>'kind' =
    'internal_operator_alert'` — sin esto, cada tick crearía una nueva
    conversación (acumulación de basura) o reutilizaría conversaciones de
    clientes reales (cross-contamination).
    """
    source = _source_of_alerts('_ensure_operator_alert_conversation')
    assert "metadata->>'kind' = 'internal_operator_alert'" in source, (
        'BUG-029: el helper debe filtrar conversación por '
        "`metadata->>'kind' = 'internal_operator_alert'` para reutilización "
        'segura.'
    )
    assert "'source', 'internal_operator_alert'" in source or "source, metadata" in source, (
        'BUG-029: el contacto interno debe marcarse con '
        "source='internal_operator_alert' para no contaminar funnel/analytics."
    )


# ───── BUG-030 — NOT-APPLICABLE (digest ya tiene helper) ─────────────────


def test_bug_030_digest_worker_ensures_internal_conversation():
    """Defensa contra que alguien quite el helper del digest worker."""
    from app.workers import digest_worker  # noqa: PLC0415
    assert hasattr(digest_worker, '_ensure_internal_digest_conversation'), (
        'BUG-030: el helper `_ensure_internal_digest_conversation` del '
        'digest worker desapareció — los digests WhatsApp vuelven a fallar.'
    )


# ───── BUG-031 — NOT-APPLICABLE (require_platform_owner ya correcto) ────


def test_bug_031_require_platform_owner_checks_platform_owner_role():
    """El check debe ser `'platform_owner' not in roles`, no `'owner'`."""
    from app.core import security  # noqa: PLC0415
    source = textwrap.dedent(inspect.getsource(security.require_platform_owner))
    assert "'platform_owner' not in" in source, (
        'BUG-031: `require_platform_owner` debe chequear `platform_owner` '
        'literal, no `owner` (que es el rol del tenant, no de plataforma).'
    )


# ───── BUG-032 — NOT-APPLICABLE (configure-auth0.sh ya crea el rol) ─────


def test_bug_032_configure_auth0_creates_platform_owner_role():
    """El script debe declarar `platform_owner` en el array `role_names`."""
    src = CONFIGURE_AUTH0.read_text()
    assert 'role_names=(platform_owner' in src, (
        'BUG-032: regresión — `configure-auth0.sh` no incluye `platform_owner` '
        'en `role_names=(...)`. Sin esto el rol nunca se crea y '
        '`require_platform_owner` rechaza a todos los operadores.'
    )
