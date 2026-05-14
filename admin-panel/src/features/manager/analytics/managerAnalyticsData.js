/**
 * UI-008.1 — Manager · Analítica ("Cómo va el negocio"): helpers puros.
 *
 * Da forma a las respuestas de `analytics_overview` / `analytics_funnel` /
 * `analytics_agents` / `analytics_campaigns` hacia los descriptores que pintan
 * los componentes del feature. Sin React ni red — unit-testable en aislamiento.
 */

/** Opciones de orden para la tabla de rendimiento por agente. */
export const AGENT_SORT_OPTIONS = Object.freeze([
  { id: 'revenue_attributed', label: 'Ingreso atribuido' },
  { id: 'appointments_confirmed', label: 'Citas confirmadas' },
  { id: 'handoffs_resolved', label: 'Handoffs resueltos' },
  { id: 'avg_response_time_seconds', label: 'Tiempo de respuesta (asc)' },
  { id: 'feedback_avg_rating', label: 'Rating' },
  { id: 'messages_sent', label: 'Mensajes enviados' },
]);

const CHANNEL_LABELS = Object.freeze({
  whatsapp: 'WhatsApp',
  instagram: 'Instagram',
  messenger: 'Messenger',
  web: 'Web widget',
  web_widget: 'Web widget',
});

function num(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

/** Formatea un entero con separadores es-CO. Devuelve `-` para valores vacíos. */
export function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return new Intl.NumberFormat('es-CO').format(Number(value));
}

/** Formatea un monto como moneda COP sin decimales. */
export function formatCurrency(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  try {
    return new Intl.NumberFormat('es-CO', {
      style: 'currency',
      currency: 'COP',
      maximumFractionDigits: 0,
    }).format(Number(value));
  } catch {
    return `$${num(value).toFixed(0)}`;
  }
}

/** Formatea un porcentaje (recibe el número ya en escala 0-100). */
export function formatPercent(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '-';
  return `${num(value).toFixed(1)}%`;
}

/** Formatea una duración en segundos a `s` / `min` / `h`. */
export function formatSeconds(value) {
  if (!value || value <= 0) return '-';
  if (value < 60) return `${Math.round(value)} s`;
  const minutes = value / 60;
  if (minutes < 60) return `${minutes.toFixed(1)} min`;
  return `${(minutes / 60).toFixed(1)} h`;
}

/** Formatea un rating promedio con su conteo de calificaciones. */
export function formatRating(value, count) {
  if (!count || value === null || value === undefined) return '-';
  return `${num(value).toFixed(2)} ★ (${formatNumber(count)})`;
}

/**
 * Ordena la lista de agentes según `sortBy`. El tiempo de respuesta se ordena
 * ascendente (menos es mejor); el resto descendente. No muta el array recibido.
 *
 * @param {Array<object>} items
 * @param {string} sortBy
 * @returns {Array<object>}
 */
export function sortAgents(items, sortBy) {
  const list = Array.isArray(items) ? [...items] : [];
  list.sort((a, b) => {
    if (sortBy === 'avg_response_time_seconds') {
      const av = a.avg_response_time_seconds || Number.POSITIVE_INFINITY;
      const bv = b.avg_response_time_seconds || Number.POSITIVE_INFINITY;
      return av - bv;
    }
    return num(b[sortBy]) - num(a[sortBy]);
  });
  return list;
}

/**
 * Construye los descriptores de KPI desde el `overview` actual y el previo.
 * Solo se incluyen KPIs respaldados por campos reales del endpoint: ingreso
 * estimado, citas completadas, retención 90d y tasa de no-show. El "ingreso
 * atribuido" / "CAC por canal" del HTML no los expone `analytics_overview`,
 * así que se omiten (ver diferencias declaradas en docs).
 *
 * @param {object|null} current  analytics_overview de la ventana actual
 * @param {object|null} previous analytics_overview de la ventana previa
 * @returns {Array<{key,label,value,current,previous,invertTrend,footnote}>}
 */
export function buildManagerKpis(current, previous) {
  const cur = current || {};
  const prev = previous || {};
  const curAppt = cur.appointments || {};
  const prevAppt = prev.appointments || {};
  const curRev = cur.revenue || {};
  const prevRev = prev.revenue || {};
  const curRet = cur.retention || {};
  const prevRet = prev.retention || {};
  const curConv = cur.conversations || {};

  return [
    {
      key: 'revenue',
      label: 'Ingreso estimado',
      value: formatCurrency(curRev.estimated_amount),
      current: num(curRev.estimated_amount),
      previous: num(prevRev.estimated_amount),
      invertTrend: false,
      footnote: 'Citas completadas × precio de servicio',
    },
    {
      key: 'appointments_completed',
      label: 'Citas asistidas',
      value: formatNumber(curAppt.completed),
      current: num(curAppt.completed),
      previous: num(prevAppt.completed),
      invertTrend: false,
      footnote: `${formatNumber(curAppt.confirmed)} confirmadas`,
    },
    {
      key: 'retention',
      label: 'Retención 90d',
      value: formatPercent(curRet.retention_rate_pct),
      current: num(curRet.retention_rate_pct),
      previous: num(prevRet.retention_rate_pct),
      invertTrend: false,
      footnote: `${formatNumber(curRet.recurring_contacts)} contactos recurrentes`,
    },
    {
      key: 'no_show_rate',
      label: 'Tasa de no-show',
      value: formatPercent(curAppt.no_show_rate_pct),
      current: num(curAppt.no_show_rate_pct),
      previous: num(prevAppt.no_show_rate_pct),
      invertTrend: true,
      footnote: `${formatNumber(curConv.handoff)} conversaciones con handoff`,
    },
  ];
}

/**
 * Etiqueta legible para un canal de captación.
 * @param {string} channel
 */
export function channelLabel(channel) {
  return CHANNEL_LABELS[channel] || channel || '—';
}

/**
 * Deriva los segmentos del `FunnelChart` ("conversión por canal") desde la
 * respuesta de `analytics_funnel`. Cada canal aporta su conteo de citas
 * agendadas y el % que representa sobre el total de citas de todos los canales.
 *
 * @param {object|null} funnel respuesta de analytics_funnel
 * @returns {Array<{ label: string, value: number, percent: number, count: number }>}
 */
export function buildFunnelSegments(funnel) {
  const byChannel = funnel?.by_channel;
  if (!Array.isArray(byChannel) || byChannel.length === 0) return [];

  const rows = byChannel.map((row) => {
    const steps = Array.isArray(row.steps) ? row.steps : [];
    const scheduled = steps.find((s) => s.step === 'appointments_scheduled');
    const count = num(scheduled?.count);
    return { channel: row.channel, count };
  });

  const total = rows.reduce((sum, row) => sum + row.count, 0);
  return rows
    .map((row) => ({
      label: channelLabel(row.channel),
      value: row.count,
      count: row.count,
      percent: total > 0 ? (row.count / total) * 100 : 0,
    }))
    .sort((a, b) => b.value - a.value);
}

/**
 * Da forma a la lista de campañas recientes desde `analytics_campaigns`.
 * Solo se exponen los campos reales del endpoint.
 *
 * @param {object|null} campaigns respuesta de analytics_campaigns
 * @returns {Array<{ id, name, status, recipients, appointments, revenue }>}
 */
export function buildCampaignRows(campaigns) {
  const items = campaigns?.items;
  if (!Array.isArray(items)) return [];
  return items.map((row) => ({
    id: row.campaign_id,
    name: row.name || 'Campaña sin nombre',
    status: row.status || 'unknown',
    recipients: num(row.recipients),
    appointments: num(row.appointments_attributed),
    revenue: num(row.revenue_attributed),
  }));
}
