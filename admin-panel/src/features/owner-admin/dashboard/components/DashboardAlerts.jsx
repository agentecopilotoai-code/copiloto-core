import { AlertBanner, Card, CardHeader } from '../../../../components/ui/index.js';
import { buildAlerts } from '../dashboardData.js';
import styles from '../Dashboard.module.css';

/**
 * Dashboard alerts section. Derives the alert list from the current
 * `analytics_overview` window (pending handoffs, low feedback rating, high
 * no-show rate). When nothing needs attention it shows an "all clear" banner.
 *
 * @param {{ overview: object|null, onNavigate: (moduleId: string) => void }} props
 */
export function DashboardAlerts({ overview, onNavigate }) {
  const alerts = buildAlerts(overview);

  return (
    <Card padding="md">
      <CardHeader
        title="Alertas"
        subtitle="Señales operativas derivadas de la analítica de la semana"
      />
      <div className={styles.alertList}>
        {alerts.length > 0 ? (
          alerts.map((alert) => (
            <AlertBanner
              key={alert.id}
              tone={alert.tone}
              title={alert.title}
              action={
                <button
                  type="button"
                  className={styles.alertAction}
                  onClick={() => onNavigate(alert.linkModule)}
                >
                  {alert.linkLabel}
                </button>
              }
            >
              {alert.description}
            </AlertBanner>
          ))
        ) : (
          <AlertBanner tone="success" title="Sin alertas">
            No hay handoffs pendientes, el feedback es saludable y el no-show está bajo control.
          </AlertBanner>
        )}
      </div>
    </Card>
  );
}
