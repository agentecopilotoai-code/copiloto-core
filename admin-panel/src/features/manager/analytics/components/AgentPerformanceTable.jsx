import { Card, CardHeader, CardBody, StatusBadge } from '../../../../components/ui/index.js';
import {
  AGENT_SORT_OPTIONS,
  formatCurrency,
  formatNumber,
  formatRating,
  formatSeconds,
  sortAgents,
} from '../managerAnalyticsData.js';
import styles from '../ManagerAnalytics.module.css';

/**
 * Tabla de rendimiento por agente (feature-local). Extraída del markup +
 * lógica de orden del legacy `components/modules/analytics/AgentPerformance.jsx`,
 * pero como componente presentacional: recibe `agents` (respuesta de
 * `analytics_agents`), `sortBy` y `onSortChange` desde el hook orquestador.
 *
 * @param {Object} props
 * @param {object|null} props.agents respuesta de analytics_agents
 * @param {string} props.sortBy id de la columna de orden activa
 * @param {(value: string) => void} props.onSortChange
 */
export function AgentPerformanceTable({ agents, sortBy, onSortChange }) {
  const rows = sortAgents(agents?.items ?? [], sortBy);
  const topPerformerId = agents?.top_performer_user_id ?? null;

  return (
    <Card padding="md">
      <CardHeader
        title="Rendimiento por agente"
        subtitle="Ordenado por la métrica seleccionada"
        actions={
          <label className={styles.sortLabel}>
            Ordenar por
            <select
              className={styles.sortSelect}
              value={sortBy}
              onChange={(event) => onSortChange(event.target.value)}
            >
              {AGENT_SORT_OPTIONS.map((opt) => (
                <option key={opt.id} value={opt.id}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
        }
      />
      <CardBody>
        {rows.length === 0 ? (
          <p className={styles.muted}>
            No hay agentes con actividad registrada en el rango.
          </p>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th scope="col">Agente</th>
                  <th scope="col">Mensajes</th>
                  <th scope="col">Handoffs</th>
                  <th scope="col">Citas cerradas</th>
                  <th scope="col">Ingreso</th>
                  <th scope="col">1ª resp.</th>
                  <th scope="col">Rating</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.user_id}>
                    <td>
                      <div className={styles.agentCell}>
                        <strong>{row.display_name || row.email}</strong>
                        {row.user_id === topPerformerId ? (
                          <StatusBadge tone="accent">Top</StatusBadge>
                        ) : null}
                      </div>
                      <div className={styles.muted}>{row.email}</div>
                    </td>
                    <td className={styles.mono}>{formatNumber(row.messages_sent)}</td>
                    <td className={styles.mono}>{formatNumber(row.handoffs_resolved)}</td>
                    <td className={styles.mono}>
                      {formatNumber(row.appointments_confirmed)}
                    </td>
                    <td className={styles.mono}>
                      {formatCurrency(row.revenue_attributed)}
                    </td>
                    <td className={styles.mono}>
                      {formatSeconds(row.avg_response_time_seconds)}
                    </td>
                    <td>
                      {formatRating(row.feedback_avg_rating, row.feedback_ratings_count)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardBody>
    </Card>
  );
}
