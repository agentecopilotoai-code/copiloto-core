import { useEffect, useMemo, useState } from 'react';

import { getAnalyticsAgents } from '../../../services/coreApi.js';

const SORT_OPTIONS = [
  { id: 'revenue_attributed', label: 'Ingreso atribuido' },
  { id: 'appointments_confirmed', label: 'Citas confirmadas' },
  { id: 'handoffs_resolved', label: 'Handoffs resueltos' },
  { id: 'avg_response_time_seconds', label: 'Tiempo de respuesta (asc)' },
  { id: 'feedback_avg_rating', label: 'Rating' },
  { id: 'messages_sent', label: 'Mensajes enviados' },
];

function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  return new Intl.NumberFormat('es-CO').format(value);
}

function formatCurrency(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return '-';
  return new Intl.NumberFormat('es-CO', {
    style: 'currency',
    currency: 'COP',
    maximumFractionDigits: 0,
  }).format(value);
}

function formatSeconds(value) {
  if (!value || value <= 0) return '-';
  if (value < 60) return `${Math.round(value)} s`;
  const minutes = value / 60;
  if (minutes < 60) return `${minutes.toFixed(1)} min`;
  return `${(minutes / 60).toFixed(1)} h`;
}

function formatRating(value, count) {
  if (!count) return '-';
  return `${value.toFixed(2)} ★ (${count})`;
}

export function AgentPerformance({ session, tenantId, range, isLoading: parentLoading }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sortBy, setSortBy] = useState('revenue_attributed');

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!tenantId) return;
      setLoading(true);
      setError(null);
      try {
        const result = await getAnalyticsAgents(session, tenantId, range);
        if (!cancelled) setData(result);
      } catch (err) {
        if (!cancelled) setError(err.message || 'No se pudieron cargar las métricas.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [session, tenantId, range]);

  const items = useMemo(() => {
    const list = data?.items ?? [];
    const copy = [...list];
    copy.sort((a, b) => {
      if (sortBy === 'avg_response_time_seconds') {
        const av = a.avg_response_time_seconds || Number.POSITIVE_INFINITY;
        const bv = b.avg_response_time_seconds || Number.POSITIVE_INFINITY;
        return av - bv;
      }
      const av = a[sortBy] ?? 0;
      const bv = b[sortBy] ?? 0;
      return bv - av;
    });
    return copy;
  }, [data, sortBy]);

  const topPerformerId = data?.top_performer_user_id ?? null;
  const totals = data?.totals ?? {};

  if (!tenantId) {
    return <p className="hint">Selecciona un tenant para ver el rendimiento por agente.</p>;
  }

  return (
    <div className="analytics-grid analytics-agents">
      <div className="analytics-kpis">
        <div className="kpi-card">
          <p className="kpi-label">Agentes activos</p>
          <p className="kpi-value">{formatNumber(totals.agents)}</p>
        </div>
        <div className="kpi-card">
          <p className="kpi-label">Mensajes enviados</p>
          <p className="kpi-value">{formatNumber(totals.messages_sent)}</p>
        </div>
        <div className="kpi-card">
          <p className="kpi-label">Handoffs resueltos</p>
          <p className="kpi-value">{formatNumber(totals.handoffs_resolved)}</p>
          <p className="kpi-hint">{formatNumber(totals.handoffs_accepted)} aceptados</p>
        </div>
        <div className="kpi-card">
          <p className="kpi-label">Citas confirmadas por el desk</p>
          <p className="kpi-value">{formatNumber(totals.appointments_confirmed)}</p>
          <p className="kpi-hint">{formatNumber(totals.appointments_completed)} completadas</p>
        </div>
        <div className="kpi-card">
          <p className="kpi-label">Ingreso atribuido</p>
          <p className="kpi-value">{formatCurrency(totals.revenue_attributed)}</p>
          <p className="kpi-hint">Citas completadas cerradas por agentes</p>
        </div>
      </div>

      <div className="analytics-card">
        <div className="analytics-card-header">
          <h3>Rendimiento por agente</h3>
          <label className="analytics-sort">
            Ordenar por
            <select onChange={(e) => setSortBy(e.target.value)} value={sortBy}>
              {SORT_OPTIONS.map((opt) => (
                <option key={opt.id} value={opt.id}>{opt.label}</option>
              ))}
            </select>
          </label>
        </div>

        {error && <p className="notice error">{error}</p>}
        {(loading || parentLoading) && !data && <p className="hint">Cargando rendimiento…</p>}

        {data && items.length === 0 && (
          <p className="hint">
            No hay agentes con rol <code>agent</code> registrados en este tenant.
          </p>
        )}

        {items.length > 0 && (
          <table className="analytics-table">
            <thead>
              <tr>
                <th>Agente</th>
                <th>Mensajes</th>
                <th>Handoffs aceptados</th>
                <th>Handoffs resueltos</th>
                <th>Tiempo medio respuesta</th>
                <th>Citas confirmadas</th>
                <th>Ingreso atribuido</th>
                <th>Rating</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.user_id}>
                  <td>
                    <strong>{row.display_name || row.email}</strong>
                    {row.user_id === topPerformerId && (
                      <span className="analytics-badge analytics-badge-top">top performer</span>
                    )}
                    <div className="hint">{row.email}</div>
                  </td>
                  <td>{formatNumber(row.messages_sent)}</td>
                  <td>{formatNumber(row.handoffs_accepted)}</td>
                  <td>{formatNumber(row.handoffs_resolved)}</td>
                  <td>{formatSeconds(row.avg_response_time_seconds)}</td>
                  <td>
                    {formatNumber(row.appointments_confirmed)}
                    {row.appointments_completed > 0 && (
                      <span className="hint"> ({formatNumber(row.appointments_completed)} compl.)</span>
                    )}
                  </td>
                  <td>{formatCurrency(row.revenue_attributed)}</td>
                  <td>{formatRating(row.feedback_avg_rating, row.feedback_ratings_count)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="hint">
          La atribución de citas e ingresos usa <code>appointments.metadata.closed_by_user_id</code>,
          que se setea cuando un agente crea o confirma la cita desde el Operations Desk.
        </p>
      </div>
    </div>
  );
}
