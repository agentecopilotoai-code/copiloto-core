/**
 * UI-010.1 — Lectura · Resumen (Viewer): pure data helpers.
 *
 * Shapes the period label shown next to the Viewer summary header. The KPIs
 * themselves are reused verbatim from the owner-admin dashboard (`buildKpis`
 * + `<DashboardKpis>`) — this module only adds the small bits that are
 * Viewer-specific so we don't fork the dashboard data layer.
 *
 * Kept pure so it is unit-testable without React or the network.
 */

import { buildKpis, formatMoney } from '../../owner-admin/dashboard/dashboardData.js';

// Re-export the dashboard helpers under the viewer/summary barrel so the
// rest of the feature has a single import surface. The Viewer summary KPIs
// are intentionally the same as the Owner/Admin dashboard KPIs (the backlog
// declares "Versión read-only de UI-007.1"); duplicating the helpers would
// drift them, so we re-export instead.
export { buildKpis, formatMoney };

const MONTH_NAMES_ES = [
  'Enero',
  'Febrero',
  'Marzo',
  'Abril',
  'Mayo',
  'Junio',
  'Julio',
  'Agosto',
  'Septiembre',
  'Octubre',
  'Noviembre',
  'Diciembre',
];

/**
 * Build the human-readable period label shown in the Viewer summary header.
 * The Viewer view follows the dashboard's 7-day window, so the label reads
 * "Últimos 7 días · <mes> <año>" using the month/year of the reference date.
 *
 * Pure (takes the date as a parameter so the test can pin it).
 *
 * @param {Date} [referenceDate] defaults to "now"
 * @returns {string}
 */
export function periodLabel(referenceDate = new Date()) {
  const date = referenceDate instanceof Date ? referenceDate : new Date();
  const month = MONTH_NAMES_ES[date.getMonth()] || '';
  const year = date.getFullYear();
  return `Últimos 7 días · ${month} ${year}`;
}

/**
 * The Viewer summary description shown under the page title. Surfaces the
 * "data se refresca cada 15 minutos" reassurance the HTML reference shows on
 * the period chip — Viewers can't trigger a manual refresh.
 */
export const SUMMARY_DESCRIPTION =
  'Resumen del negocio de la última semana — indicadores con variación respecto a la semana previa. Los datos se actualizan cada 15 minutos; no hay acciones de edición desde esta vista.';
