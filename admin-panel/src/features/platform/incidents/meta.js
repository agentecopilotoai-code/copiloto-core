/**
 * Shared label / tone maps for the Incidents feature. Kept in one module so the
 * table and the detail drawer never re-implement them (UI mandate: cero
 * duplicación).
 */

export const SEVERITY_TONE = { P1: 'danger', P2: 'warning', P3: 'accent' };

export const STATUS_TONE = { pending: 'warning', failed: 'danger', sent: 'success' };

export const STATUS_LABEL = {
  pending: 'Pendiente',
  failed: 'Fallido',
  sent: 'Notificado',
};

export const KIND_LABEL = {
  backup_failure: 'Fallo de backup',
  outbound_dlq_threshold: 'Umbral DLQ outbound',
  complaint: 'Queja',
  negative_feedback: 'Feedback negativo',
};

/**
 * Format an ISO timestamp as a short localized date-time, or '—' when missing.
 *
 * @param {string|null|undefined} value
 */
export function formatDateTime(value) {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleString('es-CO', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '—';
  }
}
