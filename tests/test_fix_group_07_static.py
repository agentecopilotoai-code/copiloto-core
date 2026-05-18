"""Fix-group 07: BUG-053..BUG-057.

- BUG-053, 054: NOT-APPLICABLE — el feature `admin-panel/src/features/widget`
  fue removido del repo. Cualquier widget que vuelva debe traer su propio
  fix.
- BUG-055: NOT-APPLICABLE — `app/services/retention.py` tiene un
  `ENTITY_AGE_COLUMN` map que mapea `domain_events → occurred_at`,
  `webhook_events_raw → received_at`, etc. El fix ya está.
- BUG-056: VIGENTE. `INVOICE_FAILED_TEMPLATE` se usaba como `payload['purpose']`
  pero el schema enum solo permite `'subscription_payment_failed'` (sin `_v1`).
  Fix: separar `INVOICE_FAILED_TEMPLATE` (Meta API) de `INVOICE_FAILED_PURPOSE`
  (DB enum).
- BUG-057: NOT-APPLICABLE-FOR-NOW — el web widget no existe como UI; el
  consent gate WhatsApp-only no recibe tráfico web, así que el bug no se
  manifiesta hasta que se reintroduzca el widget.
"""
from __future__ import annotations

from pathlib import Path

from app.services import subscriptions


WIDGET_DIR = Path('admin-panel/src/features/widget')
RETENTION = Path('app/services/retention.py')
ROUTES = Path('app/api/v1/routes.py')


# ───── BUG-053 / 054 — NOT-APPLICABLE (no widget) ────────────────────────


def test_bug_053_054_widget_feature_not_in_admin_panel():
    """El feature widget fue removido del admin-panel. Si vuelve, tiene
    que traer sus propios fixes para CSS injection y apiBase routing.
    """
    assert not WIDGET_DIR.exists(), (
        'BUG-053/054: regresión — el feature widget volvió al admin-panel. '
        'Revisar que el snippet inyecte CSS y que apiBase apunte al API '
        'origin, no al CDN, antes de mergear.'
    )


# ───── BUG-055 — NOT-APPLICABLE (ENTITY_AGE_COLUMN) ──────────────────────


def test_bug_055_retention_per_entity_age_column_present():
    src = RETENTION.read_text()
    assert "'domain_events': 'occurred_at'" in src, (
        'BUG-055: regresión — retention worker ya no mapea '
        '`domain_events → occurred_at`. Vuelve a fallar con '
        'UndefinedColumnError("created_at").'
    )
    assert "'webhook_events_raw': 'received_at'" in src, (
        'BUG-055: regresión — `webhook_events_raw → received_at` desapareció.'
    )
    assert 'ENTITY_AGE_COLUMN' in src, (
        'BUG-055: el map `ENTITY_AGE_COLUMN` debe existir como anchor.'
    )


# ───── BUG-056 — Subscription template vs purpose ────────────────────────


def test_bug_056_invoice_failed_purpose_constant_exists():
    """`INVOICE_FAILED_PURPOSE` debe existir y ser el enum del schema
    (`subscription_payment_failed`, sin `_v1`).
    """
    assert hasattr(subscriptions, 'INVOICE_FAILED_PURPOSE'), (
        'BUG-056: la constante `INVOICE_FAILED_PURPOSE` debe existir en '
        'app/services/subscriptions.py — separa el enum de DB del template '
        'name de Meta.'
    )
    assert subscriptions.INVOICE_FAILED_PURPOSE == 'subscription_payment_failed', (
        f'BUG-056: `INVOICE_FAILED_PURPOSE` debe ser exactamente '
        f"'subscription_payment_failed' (el enum del schema), no "
        f"'{subscriptions.INVOICE_FAILED_PURPOSE}'."
    )
    assert subscriptions.INVOICE_FAILED_TEMPLATE == 'subscription_payment_failed_v1', (
        'BUG-056: `INVOICE_FAILED_TEMPLATE` debe seguir siendo el name '
        'aprobado en Meta (con `_v1`).'
    )


def test_bug_056_reminder_payload_uses_purpose_not_template_name():
    """`payload['purpose']` para reminder_jobs debe ser
    `INVOICE_FAILED_PURPOSE` (enum) no `INVOICE_FAILED_TEMPLATE` (name).
    """
    src = ROUTES.read_text()
    assert "'purpose': INVOICE_FAILED_PURPOSE" in src, (
        'BUG-056: regresión — `payload[\'purpose\']` volvió a usar '
        'INVOICE_FAILED_TEMPLATE (que termina en `_v1`), lo cual NO matchea '
        'el enum `whatsapp_templates.purpose` y todo retry queda en '
        '`template_not_approved`.'
    )
    assert "'purpose': INVOICE_FAILED_TEMPLATE" not in src, (
        'BUG-056: regresión — `purpose` mapeado a `INVOICE_FAILED_TEMPLATE` '
        'vuelve a producir mismatch con el enum del schema.'
    )


# ───── BUG-057 — NOT-APPLICABLE (no web widget UI) ──────────────────────


def test_bug_057_web_widget_consent_only_relevant_with_widget():
    """El bug original era sobre el consent gate WhatsApp-only que tampoco
    reconocía `interactive_id` web. Sin UI de web widget, no hay tráfico
    web entrante; el bug no se manifiesta. Marker para forzar revisión si
    el widget vuelve.
    """
    assert not WIDGET_DIR.exists(), (
        'BUG-057: regresión — el widget volvió. Reabrir BUG-057 y agregar '
        'soporte de consent para channel=web en `consent.enforce_inbound_consent`.'
    )
