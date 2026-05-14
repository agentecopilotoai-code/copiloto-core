import { Card, CardHeader, CardBody, StatusBadge } from '../../../../components/ui/index.js';
import { buildCampaignRows, formatCurrency, formatNumber } from '../managerAnalyticsData.js';
import styles from '../ManagerAnalytics.module.css';

const STATUS_META = {
  sent: { tone: 'success', label: 'Enviada' },
  completed: { tone: 'success', label: 'Enviada' },
  running: { tone: 'accent', label: 'En curso' },
  scheduled: { tone: 'warning', label: 'Programada' },
  draft: { tone: 'neutral', label: 'Borrador' },
  paused: { tone: 'warning', label: 'Pausada' },
  cancelled: { tone: 'danger', label: 'Cancelada' },
};

/**
 * Lista compacta de campañas recientes desde `analytics_campaigns`. Cada fila
 * muestra nombre, estado, envíos, citas atribuidas e ingreso atribuido.
 *
 * @param {{ campaigns: object|null }} props
 */
export function CampaignsSummary({ campaigns }) {
  const rows = buildCampaignRows(campaigns);

  return (
    <Card padding="md">
      <CardHeader title="Campañas" subtitle="Actividad en el rango seleccionado" />
      <CardBody>
        {rows.length === 0 ? (
          <p className={styles.muted}>No hay campañas con actividad en el rango.</p>
        ) : (
          <ul className={styles.campaignList}>
            {rows.map((row) => {
              const meta = STATUS_META[row.status] || {
                tone: 'neutral',
                label: row.status,
              };
              return (
                <li className={styles.campaignRow} key={row.id}>
                  <div className={styles.campaignMain}>
                    <div className={styles.campaignHead}>
                      <strong>{row.name}</strong>
                      <StatusBadge tone={meta.tone}>{meta.label}</StatusBadge>
                    </div>
                    <span className={styles.muted}>
                      {formatNumber(row.recipients)} envíos ·{' '}
                      {formatNumber(row.appointments)} citas atribuidas
                    </span>
                  </div>
                  <div className={styles.campaignRevenue}>
                    <span className={styles.mono}>{formatCurrency(row.revenue)}</span>
                    <span className={styles.muted}>atribuido</span>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </CardBody>
    </Card>
  );
}
