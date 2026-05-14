/**
 * Shared formatting helpers for the Billing & MRR feature. Kept in one module
 * so the KPI grid, tables and panels never re-implement currency/percent
 * formatting (UI mandate: cero duplicación).
 */

/**
 * Format a monetary amount with its ISO currency code. Falls back to a plain
 * `<amount> <currency>` string if the runtime rejects the currency code.
 *
 * @param {number} amount
 * @param {string} currency ISO-4217 code (e.g. 'COP', 'USD')
 */
export function formatMoney(amount, currency) {
  const value = Number(amount) || 0;
  try {
    return new Intl.NumberFormat('es-CO', {
      style: 'currency',
      currency: currency || 'COP',
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return `${value.toFixed(0)} ${currency || ''}`.trim();
  }
}

/**
 * Format a 0..1 rate as a one-decimal percentage. Returns '—' for nullish input.
 *
 * @param {number|null|undefined} rate
 */
export function formatPercent(rate) {
  if (rate === null || rate === undefined) return '—';
  return `${(Number(rate) * 100).toFixed(1)}%`;
}

/**
 * Return a copy of a `[{ currency, mrr }]` list sorted by MRR descending.
 *
 * @param {Array<{mrr?: number}>} list
 */
export function sortByMrrDesc(list) {
  return [...(list || [])].sort((a, b) => (b.mrr || 0) - (a.mrr || 0));
}

/**
 * Render a `mrr_by_currency` list as a single human string, e.g.
 * "COP 580 · USD 50". Returns '—' for an empty list.
 *
 * @param {Array<{currency: string, mrr: number}>} list
 */
export function formatMrrByCurrency(list) {
  if (!list || list.length === 0) return '—';
  return sortByMrrDesc(list)
    .map((entry) => formatMoney(entry.mrr, entry.currency))
    .join(' · ');
}
