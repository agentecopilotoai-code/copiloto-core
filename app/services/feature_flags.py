"""UI-006.8 — Platform feature-flags catalogue.

There is no feature-flag *system* in the backend yet (no schema table, no
rollout engine, no per-tenant override store). The UI backlog explicitly flags
that building one is a separate backend ticket to confirm with the team before
wiring ("Requiere endpoint backend si no existe — confirmar con el equipo antes
de cablear").

What this module *does* provide is the honest, read-only catalogue of the
product's actual feature flags: a static registry of shipped capabilities, each
mapped to the TASK that introduced it, with its flag type and current global
default. It is the same pattern as `platform_runbooks` (a static catalogue
exposed read-only) — no DB, no writes, no migration.

Deferred to the backend ticket: live toggling, gradual rollout percentages and
per-tenant overrides. Those are the parts that change production behaviour and
need the real, audited, writable system.
"""

from __future__ import annotations

# Flag types mirror the HTML reference (`08 _ Feature flags.html`):
#   - feature    : a shipped product capability, on/off.
#   - kill       : a kill-switch for a critical dependency (flip off to degrade).
#   - rollout    : a capability rolled out gradually (needs the rollout engine).
#   - experiment : a not-GA proof of concept.
FLAG_TYPES = ('feature', 'kill', 'rollout', 'experiment')

# Static registry of the product's real feature flags. Every entry maps to a
# shipped TASK — there are no fabricated experiment rows. `default` reflects the
# current shipped reality; `rollout_pct` is informational only (the rollout
# engine itself is deferred).
FEATURE_FLAGS = (
    {
        'key': 'cloud_llm_primary',
        'description': 'Usar el LLM cloud (Claude) como primario, con fallback a Ollama local.',
        'type': 'kill',
        'default': 'on',
        'rollout_pct': 100,
        'related_task': 'TASK-0024 / TASK-0025 / TASK-0078',
    },
    {
        'key': 'instagram_messenger',
        'description': 'Canales sociales Instagram DM y Facebook Messenger.',
        'type': 'feature',
        'default': 'on',
        'rollout_pct': 100,
        'related_task': 'TASK-0074',
    },
    {
        'key': 'web_widget',
        'description': 'Widget web embebible para conversaciones desde el sitio del tenant.',
        'type': 'feature',
        'default': 'on',
        'rollout_pct': 100,
        'related_task': 'TASK-0070 / TASK-0081',
    },
    {
        'key': 'subscriptions_billing',
        'description': 'Membresías con cobro recurrente vía Stripe y MercadoPago.',
        'type': 'feature',
        'default': 'on',
        'rollout_pct': 100,
        'related_task': 'TASK-0075',
    },
    {
        'key': 'multilang_i18n',
        'description': 'Locale, moneda y timezone para los 7 países LatAm soportados.',
        'type': 'feature',
        'default': 'on',
        'rollout_pct': 100,
        'related_task': 'TASK-0073',
    },
    {
        'key': 'payments_fail_closed',
        'description': 'Pagos fail-closed: un webhook de pago no verificable nunca confirma la cita.',
        'type': 'kill',
        'default': 'on',
        'rollout_pct': 100,
        'related_task': 'TASK-0040 / TASK-0083 / TASK-0084',
    },
    {
        'key': 'observability_metrics',
        'description': 'Métricas Prometheus + alertas operativas con runbooks.',
        'type': 'feature',
        'default': 'on',
        'rollout_pct': 100,
        'related_task': 'TASK-0060',
    },
    {
        'key': 'outbound_dlq',
        'description': 'Dead-letter queue de mensajes outbound con reintento manual.',
        'type': 'feature',
        'default': 'on',
        'rollout_pct': 100,
        'related_task': 'TASK-0065',
    },
    {
        'key': 'branches_multisite',
        'description': 'Multi-sede: sedes con dirección, horario y contacto propios.',
        'type': 'feature',
        'default': 'on',
        'rollout_pct': 100,
        'related_task': 'TASK-0050',
    },
    {
        'key': 'treatment_packages',
        'description': 'Paquetes y planes de tratamiento multi-cita con saldo de sesiones.',
        'type': 'feature',
        'default': 'on',
        'rollout_pct': 100,
        'related_task': 'TASK-0051',
    },
)


def list_feature_flags() -> list[dict]:
    """Return the feature-flag catalogue as a list of plain dicts (copies)."""
    return [dict(flag) for flag in FEATURE_FLAGS]


def summarize_feature_flags(flags: list[dict]) -> dict:
    """Aggregate KPI counters for the feature-flag catalogue.

    Returns the total, the count of `on` defaults and a breakdown by flag type.
    """
    by_type: dict[str, int] = {}
    on_count = 0
    for flag in flags:
        flag_type = flag.get('type', 'feature')
        by_type[flag_type] = by_type.get(flag_type, 0) + 1
        if flag.get('default') == 'on':
            on_count += 1
    return {
        'total': len(flags),
        'on': on_count,
        'off': len(flags) - on_count,
        'by_type': by_type,
    }
