/**
 * UI-007.1 — Owner/Admin Dashboard: pure data helpers.
 *
 * Shapes the `analytics_overview` responses (current + previous 7-day window)
 * into the KPI cards and the alert list the dashboard renders. Kept pure so it
 * is unit-testable without React or the network.
 */

/**
 * Format an amount as a whole-number COP-ish currency string. The dashboard
 * shows estimated revenue, not a precise ledger, so cents are dropped.
 *
 * @param {number} amount
 */
export function formatMoney(amount) {
  const value = Number(amount) || 0;
  try {
    return new Intl.NumberFormat('es-CO', {
      style: 'currency',
      currency: 'COP',
      maximumFractionDigits: 0,
    }).format(value);
  } catch {
    return `$${value.toFixed(0)}`;
  }
}

function num(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

/**
 * Build the KPI card descriptors from the current and previous overview windows.
 * Each descriptor feeds a `<KpiCardWithDelta>` — `current`/`previous` drive the
 * trend delta, `value` is the pre-formatted display string.
 *
 * @param {object|null} current  analytics_overview for the current 7d window
 * @param {object|null} previous analytics_overview for the prior 7d window
 * @returns {Array<{key,label,value,current,previous,invertTrend,footnote}>}
 */
export function buildKpis(current, previous) {
  const cur = current || {};
  const prev = previous || {};
  const curAppt = cur.appointments || {};
  const prevAppt = prev.appointments || {};
  const curConv = cur.conversations || {};
  const prevConv = prev.conversations || {};
  const curMsg = cur.messages || {};
  const prevMsg = prev.messages || {};
  const curRev = cur.revenue || {};
  const prevRev = prev.revenue || {};

  return [
    {
      key: 'appointments_confirmed',
      label: 'Citas confirmadas (7d)',
      value: String(num(curAppt.confirmed)),
      current: num(curAppt.confirmed),
      previous: num(prevAppt.confirmed),
      invertTrend: false,
      footnote: `${num(curAppt.created)} creadas · ${num(curAppt.completed)} completadas`,
    },
    {
      key: 'no_show_rate',
      label: 'No-show rate (7d)',
      value: `${num(curAppt.no_show_rate_pct).toFixed(1)}%`,
      current: num(curAppt.no_show_rate_pct),
      previous: num(prevAppt.no_show_rate_pct),
      invertTrend: true,
      footnote: `${num(curAppt.no_shows)} no-shows`,
    },
    {
      key: 'conversations_open',
      label: 'Conversaciones abiertas',
      value: String(num(curConv.open)),
      current: num(curConv.open),
      previous: num(prevConv.open),
      invertTrend: true,
      footnote: `${num(curConv.handoff)} requieren handoff`,
    },
    {
      key: 'messages_inbound',
      label: 'Mensajes recibidos (7d)',
      value: String(num(curMsg.inbound)),
      current: num(curMsg.inbound),
      previous: num(prevMsg.inbound),
      invertTrend: false,
      footnote: `${num(curMsg.outbound)} enviados`,
    },
    {
      key: 'revenue',
      label: 'Ingresos estimados (7d)',
      value: formatMoney(curRev.estimated_amount),
      current: num(curRev.estimated_amount),
      previous: num(prevRev.estimated_amount),
      invertTrend: false,
      footnote: 'citas completadas × precio de servicio',
    },
  ];
}

/**
 * Derive the dashboard alert list from the current overview window. Returns an
 * empty array when nothing needs attention (the view then shows an "all clear"
 * banner). Each alert names the module it links to.
 *
 * @param {object|null} overview analytics_overview for the current window
 * @returns {Array<{id,tone,title,description,linkModule,linkLabel}>}
 */
export function buildAlerts(overview) {
  const data = overview || {};
  const conv = data.conversations || {};
  const appt = data.appointments || {};
  const feedback = data.feedback || {};
  const alerts = [];

  const handoff = num(conv.handoff);
  if (handoff > 0) {
    alerts.push({
      id: 'handoffs',
      tone: 'warning',
      title: `${handoff} conversaciones requieren handoff`,
      description: 'Hay clientes esperando a un agente humano. Revísalas en el Operations Desk.',
      linkModule: 'operations-desk',
      linkLabel: 'Abrir Operations Desk',
    });
  }

  const ratingsCount = num(feedback.ratings_count);
  const avgRating = num(feedback.average_rating);
  if (ratingsCount > 0 && avgRating > 0 && avgRating < 4) {
    alerts.push({
      id: 'feedback',
      tone: avgRating < 3 ? 'danger' : 'warning',
      title: `Rating promedio bajo: ${avgRating.toFixed(1)} ★`,
      description: `${ratingsCount} valoraciones en la ventana. Revisa el feedback negativo reciente.`,
      linkModule: 'operations-desk',
      linkLabel: 'Ver conversaciones',
    });
  }

  const noShowRate = num(appt.no_show_rate_pct);
  if (noShowRate > 10) {
    alerts.push({
      id: 'no_show',
      tone: 'warning',
      title: `No-show alto: ${noShowRate.toFixed(1)}%`,
      description: 'La tasa de inasistencia superó el 10%. Revisa los recordatorios y la confirmación.',
      linkModule: 'analytics',
      linkLabel: 'Ver analítica',
    });
  }

  return alerts;
}
