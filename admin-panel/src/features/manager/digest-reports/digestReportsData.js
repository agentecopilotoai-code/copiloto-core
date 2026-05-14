/**
 * Pure helpers for the Manager · Reportes · Digest view (UI-008.4).
 *
 * Stateless, unit-testable derivations shared by the orchestrator, the
 * `useDigestReportsData` hook and the relocated `DigestSubscriptionsPanel`.
 */

/** Cadence options offered by the "Suscribir destinatario" form. */
export const CADENCE_OPTIONS = Object.freeze([
  { value: 'daily', label: 'Diario (todos los días a las 08:00 del tenant)' },
  { value: 'weekly', label: 'Semanal (lunes 08:00)' },
]);

/** Short, human labels for a cadence value. */
const CADENCE_LABELS = Object.freeze({
  daily: 'Diaria',
  weekly: 'Semanal',
});

/** Returns a readable cadence label, falling back to the raw value. */
export function cadenceLabel(cadence) {
  return CADENCE_LABELS[cadence] || cadence || '—';
}

/** Empty shape for the create-subscription form. */
export function emptyForm() {
  return {
    recipient_email: '',
    recipient_whatsapp: '',
    cadence: 'daily',
    enabled: true,
  };
}

/** Best display label for a subscription recipient (email, else whatsapp). */
export function recipientLabel(sub) {
  if (!sub) return '—';
  return sub.recipient_email || sub.recipient_whatsapp || '—';
}

/** Two-letter initials derived from a recipient label. */
export function recipientInitials(sub) {
  const label = recipientLabel(sub);
  if (!label || label === '—') return '··';
  const local = label.split('@')[0] || label;
  const parts = local.split(/[.\-_+\s]+/).filter(Boolean);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase();
  }
  return local.slice(0, 2).toUpperCase();
}

/** Formats `last_sent_at` for display; `Nunca` when never sent. */
export function formatLastSent(value) {
  if (!value) return 'Nunca';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Nunca';
  return date.toLocaleString();
}

/**
 * Derives a summary of a subscriptions list: total destinos and the split by
 * cadence and enabled/paused state.
 *
 * @param {Array<object>} subscriptions
 * @returns {{ total: number, daily: number, weekly: number, enabled: number, paused: number }}
 */
export function summarizeSubscriptions(subscriptions) {
  const list = Array.isArray(subscriptions) ? subscriptions : [];
  let daily = 0;
  let weekly = 0;
  let enabled = 0;
  for (const sub of list) {
    if (sub?.cadence === 'weekly') weekly += 1;
    else if (sub?.cadence === 'daily') daily += 1;
    if (sub?.enabled) enabled += 1;
  }
  return {
    total: list.length,
    daily,
    weekly,
    enabled,
    paused: list.length - enabled,
  };
}
