/**
 * UI-007.3 — Conversaciones · Contactos: pure formatting helpers.
 *
 * Date formatting and qualification-answer rendering, extracted from the legacy
 * `ContactsModule` so they are shared by the split panels and unit-testable
 * without React.
 */

/** Format an ISO timestamp as a short localized date-time, or '—' when missing. */
export function formatDate(value) {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat('es-CO', {
      dateStyle: 'short',
      timeStyle: 'short',
    }).format(new Date(value));
  } catch {
    return value;
  }
}

/** Format an ISO timestamp as a medium localized date, or '—' when missing. */
export function formatDateShort(value) {
  if (!value) return '—';
  try {
    return new Intl.DateTimeFormat('es-CO', { dateStyle: 'medium' }).format(new Date(value));
  } catch {
    return value;
  }
}

/**
 * Render a contact's answer to a qualification question for display.
 *
 * Handles `yes_no` (true/false → Sí/No), `single_choice` / `multi_choice`
 * (value → option label), and free-form answers. Returns '—' when there is no
 * answer.
 *
 * @param {object} question qualification question ({ kind, options })
 * @param {*} raw the contact's raw answer
 * @returns {string}
 */
export function renderQualificationAnswer(question, raw) {
  if (!question) return '—';
  if (question.kind === 'yes_no') {
    if (raw === true) return 'Sí';
    if (raw === false) return 'No';
    return '—';
  }
  if (question.kind === 'single_choice' || question.kind === 'multi_choice') {
    const options = Array.isArray(question.options) ? question.options : [];
    const lookup = (value) => {
      const found = options.find((option) => option.value === value);
      return found?.label || value;
    };
    if (Array.isArray(raw)) return raw.map(lookup).join(', ') || '—';
    if (typeof raw === 'string' && raw) return lookup(raw);
    return '—';
  }
  if (raw != null && raw !== '') return String(raw);
  return '—';
}
