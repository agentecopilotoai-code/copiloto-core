/**
 * UI-016.3 — Negocio · Rendimiento del equipo: helpers puros para la vista
 * `AgentPerformance` (Owner / Admin).
 *
 * Da forma a la respuesta de `GET /v1/analytics/agents` hacia los descriptores
 * que pintan los componentes del feature: KPIs superiores, serie de
 * "Distribución de carga" y CSV exportable. Sin React ni red — unit-testable
 * en aislamiento. Reusa los formateadores de `manager/analytics/managerAnalyticsData.js`
 * (que ya estaban probados en UI-008.1) para no duplicar lógica.
 */

import {
  formatCurrency,
  formatNumber,
  formatSeconds,
} from '../../manager/analytics/managerAnalyticsData.js';

/** Presets de rango disponibles en la cabecera de la vista. */
export const RANGE_PRESETS = Object.freeze([
  { id: '7d', label: '7 días', days: 7 },
  { id: '30d', label: '30 días', days: 30 },
  { id: '90d', label: '90 días', days: 90 },
]);

/** Preset por defecto (el HTML del diseñador muestra "Rango: 30d"). */
export const DEFAULT_PRESET = '30d';

function num(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function isoDate(date) {
  return date.toISOString().slice(0, 10);
}

/**
 * Calcula el rango `{ fromDate, toDate }` ISO para el preset indicado, contado
 * hacia atrás desde hoy. Días inclusivos en ambos extremos.
 *
 * @param {string} presetId
 * @returns {{ fromDate: string, toDate: string }}
 */
export function rangeFromPreset(presetId) {
  const preset = RANGE_PRESETS.find((p) => p.id === presetId) || RANGE_PRESETS[1];
  const today = new Date();
  const from = new Date(today);
  from.setDate(from.getDate() - (preset.days - 1));
  return { fromDate: isoDate(from), toDate: isoDate(today) };
}

/**
 * Construye los 4 KPIs superiores que muestra el HTML.
 *
 * Diferencias declaradas con respecto al mockup:
 *   - "Mensajes humanos · mes" usa `totals.messages_sent` (mensajes salientes
 *     enviados por agentes humanos en el desk). El "% del total" del mockup
 *     requiere comparar contra los mensajes del bot, que no está expuesto por
 *     `analytics_agents` — el footnote se rellena con el total disponible.
 *   - "Handoffs cerrados" usa `totals.handoffs_resolved`. El delta vs el mes
 *     anterior NO se calcula porque `analytics_agents` no recibe la ventana
 *     previa — se omite el footnote de delta en lugar de fabricar un número.
 *   - "Ingreso atribuido" → `totals.revenue_attributed`. Mismo razonamiento
 *     para el delta vs mes anterior.
 *   - "1ª respuesta media" se calcula como el promedio simple de
 *     `avg_response_time_seconds` entre los agentes con muestras (>0). El
 *     endpoint no devuelve un agregado oficial, así que se computa client-side
 *     declarando la diferencia.
 *
 * @param {object|null} agents respuesta cruda de `analytics_agents`
 * @returns {Array<{key,label,value,footnote}>}
 */
export function buildAgentKpis(agents) {
  const totals = agents?.totals || {};
  const items = Array.isArray(agents?.items) ? agents.items : [];

  const responseSamples = items
    .map((row) => num(row.avg_response_time_seconds))
    .filter((value) => value > 0);
  const avgResponseSeconds = responseSamples.length
    ? responseSamples.reduce((sum, value) => sum + value, 0) / responseSamples.length
    : 0;

  const messagesSent = num(totals.messages_sent);
  const handoffsResolved = num(totals.handoffs_resolved);
  const handoffsAccepted = num(totals.handoffs_accepted);
  const revenueAttributed = num(totals.revenue_attributed);
  const appointmentsConfirmed = num(totals.appointments_confirmed);

  return [
    {
      key: 'messages_sent',
      label: 'Mensajes humanos · mes',
      value: formatNumber(messagesSent),
      footnote: messagesSent
        ? `${formatNumber(items.length)} agentes activos en el rango`
        : 'Sin mensajes humanos registrados en el rango',
    },
    {
      key: 'handoffs_resolved',
      label: 'Handoffs cerrados',
      value: formatNumber(handoffsResolved),
      footnote: handoffsAccepted
        ? `${formatNumber(handoffsAccepted)} aceptados`
        : 'Sin handoffs aceptados',
    },
    {
      key: 'revenue_attributed',
      label: 'Ingreso atribuido equipo',
      value: formatCurrency(revenueAttributed),
      footnote: appointmentsConfirmed
        ? `${formatNumber(appointmentsConfirmed)} citas confirmadas`
        : 'Sin citas confirmadas atribuidas',
    },
    {
      key: 'avg_response_time_seconds',
      label: '1ª respuesta media',
      value: avgResponseSeconds ? formatSeconds(avgResponseSeconds) : '-',
      footnote: responseSamples.length
        ? `Promedio sobre ${formatNumber(responseSamples.length)} agentes`
        : 'Sin muestras de tiempo de respuesta',
    },
  ];
}

/**
 * Construye los segmentos de la gráfica "Distribución de carga". Cada agente
 * aporta una barra cuyo valor es `messages_sent` (mensajes atendidos en el
 * rango). El porcentaje se calcula respecto al máximo para escalar las barras.
 *
 * Los agentes se ordenan descendente por mensajes para que el operador vea de
 * un vistazo quién soporta más conversaciones.
 *
 * @param {object|null} agents respuesta cruda de `analytics_agents`
 * @returns {Array<{ id: string, label: string, value: number, percent: number, formatted: string }>}
 */
export function buildLoadDistribution(agents) {
  const items = Array.isArray(agents?.items) ? agents.items : [];
  if (items.length === 0) return [];

  const rows = items.map((row) => ({
    id: row.user_id,
    label: row.display_name || row.email || 'Sin nombre',
    value: num(row.messages_sent),
  }));

  const max = Math.max(1, ...rows.map((row) => row.value));
  return rows
    .map((row) => ({
      ...row,
      percent: max > 0 ? (row.value / max) * 100 : 0,
      formatted: formatNumber(row.value),
    }))
    .sort((a, b) => b.value - a.value);
}

/**
 * Construye el CSV exportable con una fila por agente. Incluye un BOM UTF-8 al
 * inicio para que Excel detecte la codificación, y `tenant_id` + ventana en
 * cabecera comentada. Mismo patrón que `buildChecklistCsv` (UI-016.1).
 *
 * @param {object|null} agents respuesta cruda de `analytics_agents`
 * @param {{ tenantId?: string, fromDate?: string, toDate?: string }} meta
 */
export function buildAgentsCsv(agents, meta = {}) {
  const items = Array.isArray(agents?.items) ? agents.items : [];
  const header = [
    'persona',
    'mensajes',
    'handoffs_resueltos',
    'handoffs_aceptados',
    'citas_confirmadas',
    'ingreso_atribuido',
    'primer_respuesta_seg',
    'rating',
    'rating_count',
  ];
  const lines = [header.join(',')];
  for (const row of items) {
    const name = (row.display_name || row.email || '').replace(/"/g, '""');
    const values = [
      `"${name}"`,
      num(row.messages_sent),
      num(row.handoffs_resolved),
      num(row.handoffs_accepted),
      num(row.appointments_confirmed),
      num(row.revenue_attributed),
      num(row.avg_response_time_seconds),
      row.feedback_avg_rating !== null && row.feedback_avg_rating !== undefined
        ? Number(row.feedback_avg_rating).toFixed(2)
        : '',
      num(row.feedback_ratings_count),
    ];
    lines.push(values.join(','));
  }
  const headerMeta = [
    `# tenant_id=${meta.tenantId || ''}`,
    `# from_date=${meta.fromDate || ''}`,
    `# to_date=${meta.toDate || ''}`,
  ];
  // BOM UTF-8 (U+FEFF) para que Excel detecte la codificación al abrir el CSV.
  return '﻿' + headerMeta.join('\n') + '\n' + lines.join('\n');
}
