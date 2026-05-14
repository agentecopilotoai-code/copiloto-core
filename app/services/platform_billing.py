"""UI-006.3 — Platform-level billing / MRR aggregation helpers.

The platform "MRR" here is the recurring revenue flowing through the fleet,
computed from the per-tenant subscription model of TASK-0075
(`app.subscription_plans` + `app.contact_subscriptions`) aggregated across all
tenants. It is NOT a SaaS billing ledger of each tenant's plan with CopilotoIA —
that data is not modelled in the schema (see `docs/UI_BACKLOG.md` UI-006.1 note).

These helpers are pure: the SQL aggregation lives in the route, which hands the
granular per-(tenant, currency, billing_period) rows here for monthly
normalisation and folding into the response shape. Kept pure so they are
unit-testable without a database.
"""

from __future__ import annotations

# A plan's price is charged once per billing period; to compare plans on a
# single axis we normalise every price to a monthly figure.
MRR_MONTHLY_DIVISOR = {'monthly': 1, 'quarterly': 3, 'yearly': 12}


def normalize_mrr(billing_period: str | None, amount: float | int | None) -> float:
    """Normalise a billing-period amount to a monthly figure.

    `quarterly` divides by 3, `yearly` by 12, `monthly` is unchanged. Unknown
    periods or a missing amount yield 0.0 — never raises, since the caller
    aggregates many rows and one bad row must not break the snapshot.
    """
    divisor = MRR_MONTHLY_DIVISOR.get(billing_period)
    if divisor is None or amount is None:
        return 0.0
    return round(float(amount) / divisor, 2)


def summarize_mrr_by_currency(rows: list[dict]) -> list[dict]:
    """Sum monthly-normalised MRR + active subscription counts per currency.

    `rows` are the granular per-(tenant, currency, billing_period) aggregate
    rows — each carrying `currency`, `billing_period`, `price_sum` and
    `active_subscriptions`. Returns one entry per currency sorted by currency.
    """
    by_currency: dict[str, dict] = {}
    for row in rows:
        currency = row.get('currency') or 'UNK'
        bucket = by_currency.setdefault(
            currency, {'currency': currency, 'mrr': 0.0, 'active_subscriptions': 0}
        )
        bucket['mrr'] += normalize_mrr(row.get('billing_period'), row.get('price_sum'))
        bucket['active_subscriptions'] += row.get('active_subscriptions', 0) or 0
    return [
        {**bucket, 'mrr': round(bucket['mrr'], 2)}
        for bucket in sorted(by_currency.values(), key=lambda b: b['currency'])
    ]


def fold_tenant_rows(rows: list[dict]) -> list[dict]:
    """Fold per-(tenant, currency, billing_period) aggregate rows into one entry
    per tenant with a `mrr_by_currency` breakdown.

    Each input row carries the tenant identity columns plus `currency`,
    `billing_period`, `price_sum` (sum of plan prices for active subscriptions
    in that group), `active_subscriptions`, `past_due_subscriptions` and
    `next_billing_at`. Output rows are sorted by total monthly MRR descending.
    """
    tenants: dict[str, dict] = {}
    for row in rows:
        tenant_id = str(row['tenant_id'])
        entry = tenants.get(tenant_id)
        if entry is None:
            entry = {
                'tenant_id': tenant_id,
                'slug': row.get('slug'),
                'display_name': row.get('display_name') or row.get('legal_name'),
                'country_code': row.get('country_code'),
                'active_subscriptions': 0,
                'past_due_subscriptions': 0,
                'next_billing_at': None,
                '_by_currency': {},
            }
            tenants[tenant_id] = entry
        entry['active_subscriptions'] += row.get('active_subscriptions', 0) or 0
        entry['past_due_subscriptions'] += row.get('past_due_subscriptions', 0) or 0
        next_billing = row.get('next_billing_at')
        if next_billing is not None and (
            entry['next_billing_at'] is None or next_billing < entry['next_billing_at']
        ):
            entry['next_billing_at'] = next_billing
        currency = row.get('currency') or 'UNK'
        mrr = normalize_mrr(row.get('billing_period'), row.get('price_sum'))
        entry['_by_currency'][currency] = round(
            entry['_by_currency'].get(currency, 0.0) + mrr, 2
        )

    folded: list[dict] = []
    for entry in tenants.values():
        by_currency = [
            {'currency': currency, 'mrr': mrr}
            for currency, mrr in sorted(entry.pop('_by_currency').items())
        ]
        entry['mrr_by_currency'] = by_currency
        entry['mrr_total'] = round(sum(item['mrr'] for item in by_currency), 2)
        folded.append(entry)
    folded.sort(key=lambda item: item['mrr_total'], reverse=True)
    return folded
