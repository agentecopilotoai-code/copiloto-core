import { KpiTile } from '../../../../components/ui/index.js';
import { formatPrice } from '../subscriptionsData.js';
import styles from '../Subscriptions.module.css';

/**
 * KPI grid for the Suscripciones view. The MRR tile is derived from the active
 * subscribers × their plan price normalised to a month; the HTML reference's
 * "Churn 30d" tile is intentionally replaced by "Cancelados" because no churn
 * snapshot is modelled — no data is fabricated.
 *
 * @param {{ kpis: {
 *   mrr: number, currency: string, activeCount: number, pastDueCount: number,
 *   cancelledCount: number, activePlanCount: number,
 * } }} props
 */
export function SubscriptionsKpis({ kpis }) {
  return (
    <div className={styles.kpiGrid}>
      <KpiTile
        label="MRR del tenant"
        value={formatPrice(kpis.mrr, kpis.currency)}
        footnote="Suscriptores activos × precio del plan normalizado a mes"
      />
      <KpiTile
        label="Suscriptores activos"
        value={String(kpis.activeCount)}
        footnote={`${kpis.activePlanCount} ${kpis.activePlanCount === 1 ? 'plan activo' : 'planes activos'}`}
      />
      <KpiTile
        label="Past-due"
        value={String(kpis.pastDueCount)}
        footnote="Cobros fallidos en reintento"
      />
      <KpiTile
        label="Cancelados"
        value={String(kpis.cancelledCount)}
        footnote="Quedan en el historial para auditoría"
      />
    </div>
  );
}
