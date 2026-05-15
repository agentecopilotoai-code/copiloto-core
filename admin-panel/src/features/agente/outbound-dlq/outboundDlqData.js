/**
 * UI-009.4 — Operación · Outbound DLQ: pure data helpers.
 *
 * Date formatting and the Meta error-code label catalogue — extracted from the
 * legacy `OutboundDLQ` so the chips / table / detail modal share them and they
 * stay unit-testable without React.
 */

/** Human-readable labels for the common Meta / transport error codes. */
export const ERROR_CODE_LABELS = {
  '131026': 'Mensaje no entregable',
  '190': 'Token de acceso caducado',
  '80007': 'Rate limit excedido',
  '131047': 'Fuera de la ventana de 24 h',
  '131051': 'Tipo de mensaje no soportado',
  '100': 'Parámetro inválido',
  transport: 'Red / timeout',
};

/** Friendly label for an error code, falling back to the raw code. */
export function errorCodeLabel(code) {
  if (!code) return '—';
  return ERROR_CODE_LABELS[String(code)] || String(code);
}

/** Locale-aware short date/time formatter for DLQ timestamps. */
export function formatDate(value) {
  if (!value) return '-';
  return new Intl.DateTimeFormat('es-CO', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(new Date(value));
}

/** Short id form for display (first 8 chars + ellipsis). */
export function shortId(id) {
  if (!id) return '—';
  return `${String(id).slice(0, 8)}…`;
}

/** Total failed-message count across all error-code groups. */
export function totalFailures(totals) {
  return (totals || []).reduce((sum, group) => sum + (group.count || 0), 0);
}
