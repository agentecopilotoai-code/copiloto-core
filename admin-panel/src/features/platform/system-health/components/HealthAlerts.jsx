import { Card, CardHeader, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import styles from '../SystemHealth.module.css';

const SEVERITY_TONE = {
  page: 'danger',
  warning: 'warning',
};

/**
 * Active Prometheus-style alerts derived from the health snapshot
 * (`evaluate_health_alerts`). Each row carries the alert name, severity badge,
 * summary and a runbook reference. Mirrors the "Alertas Prometheus activas"
 * block of the HTML reference.
 *
 * @param {{ alerts: Array<object> }} props
 */
export function HealthAlerts({ alerts }) {
  return (
    <Card padding="md">
      <CardHeader
        title="Alertas activas"
        subtitle="Derivadas del snapshot · la SLA real vive en Prometheus + Alertmanager"
      />
      {alerts && alerts.length > 0 ? (
        <ul className={styles.alertList}>
          {alerts.map((alert) => (
            <li key={alert.name} className={styles.alertItem}>
              <div className={styles.alertHead}>
                <span className={styles.alertName}>{alert.name}</span>
                <StatusBadge tone={SEVERITY_TONE[alert.severity] || 'neutral'}>
                  {alert.severity}
                </StatusBadge>
              </div>
              <p className={styles.alertSummary}>{alert.summary}</p>
              <span className={styles.alertRunbook}>{alert.runbook_url}</span>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState
          title="Sin alertas activas"
          description="Ningún umbral de salud está disparando en este snapshot."
        />
      )}
    </Card>
  );
}
