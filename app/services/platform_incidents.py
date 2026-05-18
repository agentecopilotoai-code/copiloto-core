"""UI-006.4 — Platform incidents aggregation helpers.

The platform "incidents" feed is the cross-tenant view of `app.operator_alerts`
(TASK-0057 / TASK-0064 / TASK-0065): negative-feedback, complaint, outbound-DLQ
and backup-failure alerts that fired across the fleet. There is no dedicated
incident-management schema (assignee, MTTR, postmortem link, comments) — that
would be a separate backend ticket; this module derives what the alert rows
already carry.

These helpers are pure so they are unit-testable without a database: the SQL
read lives in the route, which hands the alert rows here for severity / runbook
derivation and KPI summarisation.
"""

from __future__ import annotations

# Severity is derived from the alert `kind`. `backup_failure` is a system-wide
# data-integrity alert (P1); delivery/customer-facing alerts are P2; a single
# low rating is a quality signal (P3).
SEVERITY_BY_KIND = {
    'backup_failure': 'P1',
    'outbound_dlq_threshold': 'P2',
    'complaint': 'P2',
    'negative_feedback': 'P3',
}

# Only `outbound_dlq_threshold` maps cleanly to a published runbook in
# `docs/runbooks/`; the rest have no dedicated runbook yet — left as None
# rather than guessing.
RUNBOOK_BY_KIND = {
    'outbound_dlq_threshold': 'rate-limit-meta-hit.md',
}

# operator_alerts.status ∈ {pending, sent, failed}. `sent` means the operator
# was notified; `pending`/`failed` still need attention, so they count as open.
OPEN_STATUSES = frozenset({'pending', 'failed'})


def severity_for_kind(kind: str | None) -> str:
    """Map an alert `kind` to a severity label. Unknown kinds fall back to P3."""
    return SEVERITY_BY_KIND.get(kind or '', 'P3')


def runbook_for_kind(kind: str | None) -> str | None:
    """Return the published runbook filename for an alert `kind`, or None."""
    return RUNBOOK_BY_KIND.get(kind or '')


def is_open(status: str | None) -> bool:
    """True when an alert still needs operator attention (`pending` / `failed`)."""
    return (status or '') in OPEN_STATUSES


# BUG-119: keys del payload de `operator_alerts` que pueden cargar PII de
# contactos o canales de notificación. Se enmascaran antes de servir el feed
# al platform_owner (que tiene MFA pero NO debería ver PII de clientes ni
# emails/whatsapp de operadores fuera de su scope inmediato).
_PII_PAYLOAD_KEYS = frozenset({
    'contact_phone',
    'contact_phone_e164',
    'contact_name',
    'contact_display_name',
    'contact_email',
    'recipient_email',
    'recipient_whatsapp',
    'recipient_phone',
    'phone',
    'email',
    'whatsapp',
})


def _redact_value(value: object) -> str:
    """Sustituye un valor sensible por un placeholder con su longitud original
    (útil para que el operador sepa que había data, sin exponer el contenido).
    """
    if value is None:
        return '[redacted]'
    text = str(value)
    if not text:
        return '[redacted]'
    return f'[redacted len={len(text)}]'


def redact_incident_payload(payload: dict | None) -> dict:
    """Enmascara PII y canales de notificación del payload de un operator_alert
    antes de devolverlo en el feed `/platform/incidents`.

    Reglas:
    - Cualquier key en `_PII_PAYLOAD_KEYS` se reemplaza por `[redacted len=N]`.
    - `channels` se reduce a `{'email_count': N, 'whatsapp_count': M}` para no
      exponer los emails/whatsapp del operador.
    - Se recurse en dicts anidados; listas se mapean elemento a elemento.
    - Otros tipos pasan tal cual.
    """
    if not isinstance(payload, dict):
        return {}
    redacted: dict = {}
    for key, value in payload.items():
        if key == 'channels' and isinstance(value, dict):
            email_count = len(value.get('emails') or [])
            whatsapp_count = len(value.get('whatsapps') or [])
            redacted[key] = {
                'email_count': email_count,
                'whatsapp_count': whatsapp_count,
            }
            continue
        if key in _PII_PAYLOAD_KEYS:
            redacted[key] = _redact_value(value)
            continue
        if isinstance(value, dict):
            redacted[key] = redact_incident_payload(value)
        elif isinstance(value, list):
            redacted[key] = [
                redact_incident_payload(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            redacted[key] = value
    return redacted


def summarize_incidents(incidents: list[dict]) -> dict:
    """Aggregate KPI counters from a list of incident dicts.

    Each incident carries `severity`, `status`, `is_open` and `tenant_id`.
    Returns open/total counts, breakdowns by severity and status, and the
    count of distinct affected tenants (NULL tenant = system-level alert).
    """
    by_severity: dict[str, int] = {}
    by_status: dict[str, int] = {}
    affected_tenants: set[str] = set()
    open_count = 0
    for incident in incidents:
        severity = incident.get('severity') or 'P3'
        status = incident.get('status') or 'unknown'
        by_severity[severity] = by_severity.get(severity, 0) + 1
        by_status[status] = by_status.get(status, 0) + 1
        if incident.get('is_open'):
            open_count += 1
        tenant_id = incident.get('tenant_id')
        if tenant_id:
            affected_tenants.add(str(tenant_id))
    return {
        'total': len(incidents),
        'open': open_count,
        'resolved': len(incidents) - open_count,
        'by_severity': by_severity,
        'by_status': by_status,
        'affected_tenants': len(affected_tenants),
    }
