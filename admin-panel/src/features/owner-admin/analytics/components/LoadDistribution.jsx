import { Card, CardBody, CardHeader } from '../../../../components/ui/index.js';
import { buildLoadDistribution } from '../agentPerformanceData.js';
import styles from '../AgentPerformance.module.css';

/**
 * Sección "Distribución de carga" del HTML del diseñador: gráfica de barras
 * horizontales con `messages_sent` por agente, ordenado descendente. El ancho
 * de cada barra es el porcentaje sobre el máximo del grupo (no sobre el total,
 * que dramatiza la diferencia entre el agente más cargado y los demás).
 *
 * @param {{ agents: object|null }} props respuesta cruda de `analytics_agents`.
 */
export function LoadDistribution({ agents }) {
  const segments = buildLoadDistribution(agents);

  return (
    <Card padding="md">
      <CardHeader
        title="Distribución de carga"
        subtitle="Mensajes humanos atendidos por persona en el rango"
      />
      <CardBody>
        {segments.length === 0 ? (
          <p className={styles.muted}>Sin datos para distribuir.</p>
        ) : (
          <ul
            className={styles.loadList}
            aria-label="Distribución de carga por agente"
          >
            {segments.map((segment) => (
              <li key={segment.id} className={styles.loadRow}>
                <span className={styles.loadLabel}>{segment.label}</span>
                <span
                  className={styles.loadBar}
                  aria-hidden="true"
                >
                  <span
                    className={styles.loadBarFill}
                    style={{ width: `${segment.percent}%` }}
                  />
                </span>
                <span className={styles.loadValue}>{segment.formatted}</span>
              </li>
            ))}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}
