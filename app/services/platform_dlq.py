"""UI-006.5 — Platform-wide Outbound DLQ aggregation helpers.

The fleet DLQ view is the cross-tenant aggregate of `app.messages` rows that
ended `status='failed'` / `direction='outbound'` (TASK-0065). Per-tenant
operators keep their own detailed DLQ panel; this platform view only needs
counts grouped by tenant and by error_code — no message bodies, no contact PII.

These helpers are pure: the SQL aggregation lives in the route, which hands the
granular per-(tenant, error_code) rows here for folding and runbook derivation.
"""

from __future__ import annotations

# Only error codes with a clearly matching published runbook in `docs/runbooks/`
# are mapped; the rest return None rather than guessing.
RUNBOOK_BY_ERROR_CODE = {
    '190': 'meta-token-expired.md',
    '80007': 'rate-limit-meta-hit.md',
}


def runbook_for_error_code(error_code: str | None) -> str | None:
    """Return the published runbook filename for an error code, or None."""
    return RUNBOOK_BY_ERROR_CODE.get(error_code or '')


def fold_dlq_by_tenant(rows: list[dict]) -> list[dict]:
    """Fold per-(tenant, error_code) DLQ count rows into one entry per tenant.

    Each input row carries `tenant_id`, `slug`, `display_name`, `error_code`
    and `count`. Output rows carry the total failure count plus the dominant
    error code, sorted by total descending.
    """
    tenants: dict[str, dict] = {}
    for row in rows:
        tenant_id = str(row['tenant_id'])
        entry = tenants.get(tenant_id)
        if entry is None:
            entry = {
                'tenant_id': tenant_id,
                'slug': row.get('slug'),
                'display_name': row.get('display_name') or row.get('slug'),
                'total': 0,
                'top_error_code': None,
                'top_error_count': 0,
            }
            tenants[tenant_id] = entry
        count = int(row.get('count', 0) or 0)
        entry['total'] += count
        if count > entry['top_error_count']:
            entry['top_error_count'] = count
            entry['top_error_code'] = row.get('error_code')
    folded = list(tenants.values())
    folded.sort(key=lambda item: item['total'], reverse=True)
    return folded


def summarize_by_error_code(rows: list[dict]) -> list[dict]:
    """Sum DLQ counts per error code across the fleet, attaching a runbook.

    Returns one entry per error code sorted by count descending.
    """
    by_code: dict[str, int] = {}
    for row in rows:
        code = row.get('error_code') or 'transport_error'
        by_code[code] = by_code.get(code, 0) + int(row.get('count', 0) or 0)
    summary = [
        {'error_code': code, 'count': count, 'runbook': runbook_for_error_code(code)}
        for code, count in by_code.items()
    ]
    summary.sort(key=lambda item: item['count'], reverse=True)
    return summary


def summarize_fleet_dlq(rows: list[dict]) -> dict:
    """Top-level KPI counters for the fleet DLQ: total failures, affected
    tenant count and the dominant error code across the window."""
    total = 0
    affected: set[str] = set()
    by_code: dict[str, int] = {}
    for row in rows:
        count = int(row.get('count', 0) or 0)
        total += count
        if count > 0 and row.get('tenant_id'):
            affected.add(str(row['tenant_id']))
        code = row.get('error_code') or 'transport_error'
        by_code[code] = by_code.get(code, 0) + count
    top_error_code = None
    top_error_count = 0
    for code, count in by_code.items():
        if count > top_error_count:
            top_error_count = count
            top_error_code = code
    return {
        'total': total,
        'affected_tenants': len(affected),
        'top_error_code': top_error_code,
        'top_error_count': top_error_count,
    }
