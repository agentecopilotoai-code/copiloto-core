/**
 * UI-009.3 — Operación · Ficha de contacto: pure helpers for the focused
 * contact-profile deep-link view. Date formatting and qualification-answer
 * rendering are reused from the conversations-contacts feature
 * (`contactsFormat.js`); this module only holds derivations specific to the
 * focused view (display identity, initials, summary stats).
 *
 * Pure and unit-testable — no React, no fetch.
 */

/** Resolve the contact's best display name from the available fields. */
export function contactDisplayName(contact) {
  if (!contact) return 'Contacto';
  return contact.display_name || contact.phone_e164 || contact.wa_id || 'Contacto';
}

/**
 * Two-letter uppercase initials for the avatar. Falls back to the first two
 * characters of the resolved display name when there is a single word.
 */
export function contactInitials(contact) {
  const name = contactDisplayName(contact);
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return '··';
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return (words[0][0] + words[words.length - 1][0]).toUpperCase();
}

/**
 * Derive the headline summary stats shown in the focused header from the
 * `stats` block of the `getContactProfile` response. Returns an array of
 * `{ key, label, value }` so the component stays declarative.
 *
 * @param {object|null|undefined} stats `profile.stats`
 * @returns {Array<{ key: string, label: string, value: string }>}
 */
export function summaryStats(stats) {
  const s = stats || {};
  const rating =
    typeof s.average_rating === 'number'
      ? `${s.average_rating.toFixed(2)} ★ (${s.ratings_count || 0})`
      : '—';
  return [
    { key: 'total', label: 'Citas totales', value: String(s.total_appointments ?? 0) },
    {
      key: 'completed',
      label: 'Completadas',
      value: String(s.completed_appointments ?? 0),
    },
    { key: 'rating', label: 'Calificación promedio', value: rating },
  ];
}

/** Count of internal notes recorded for the contact. */
export function notesCount(profile) {
  return Array.isArray(profile?.notes) ? profile.notes.length : 0;
}

/**
 * Resolve the consent status label, preferring the dedicated consent ledger
 * payload and falling back to the contact record. Mirrors the logic baked into
 * the reused `ContactTimeline` so the header and timeline stay consistent.
 */
export function consentStatusLabel(profile, consent) {
  return (
    consent?.contact?.opt_in_status ||
    profile?.contact?.opt_in_status ||
    '—'
  );
}
