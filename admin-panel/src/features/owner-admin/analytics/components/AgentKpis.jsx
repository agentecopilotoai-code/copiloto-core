import { KpiTile } from '../../../../components/ui/index.js';
import { buildAgentKpis } from '../agentPerformanceData.js';
import styles from '../AgentPerformance.module.css';

/**
 * Strip de 4 KPIs superiores del feature "Rendimiento del equipo".
 * Mantiene el orden del HTML del diseñador:
 * Mensajes humanos · Handoffs cerrados · Ingreso atribuido · 1ª respuesta media.
 *
 * @param {{ agents: object|null }} props respuesta cruda de `analytics_agents`.
 */
export function AgentKpis({ agents }) {
  const kpis = buildAgentKpis(agents);
  return (
    <div className={styles.kpis} data-testid="agent-performance-kpis">
      {kpis.map((kpi) => (
        <KpiTile
          key={kpi.key}
          label={kpi.label}
          value={kpi.value}
          footnote={kpi.footnote}
        />
      ))}
    </div>
  );
}
