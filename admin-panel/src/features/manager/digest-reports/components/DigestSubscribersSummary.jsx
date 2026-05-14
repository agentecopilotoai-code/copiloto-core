import { Card } from '../../../../components/ui/index.js';
import styles from '../DigestReports.module.css';

/**
 * Glance-level header for the Reportes · Digest view: total digest
 * destinations and the split by cadence (diarios / semanales) and by state
 * (activos / pausados). Reads the derived summary from `useDigestReportsData`.
 *
 * @param {{ summary: { total: number, daily: number, weekly: number, enabled: number, paused: number } }} props
 */
export function DigestSubscribersSummary({ summary }) {
  const stats = [
    { label: 'Destinos', value: summary.total },
    { label: 'Diarios', value: summary.daily },
    { label: 'Semanales', value: summary.weekly },
    { label: 'Activos', value: summary.enabled },
    { label: 'Pausados', value: summary.paused },
  ];

  return (
    <Card padding="md">
      <ul className={styles.summaryGrid}>
        {stats.map((stat) => (
          <li key={stat.label} className={styles.summaryItem}>
            <span className={styles.summaryValue}>{stat.value}</span>
            <span className={styles.summaryLabel}>{stat.label}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
