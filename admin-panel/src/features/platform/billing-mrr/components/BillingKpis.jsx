import { KpiTile } from '../../../../components/ui/index.js';
import { formatMoney, formatPercent, sortByMrrDesc } from '../format.js';
import styles from '../BillingMrr.module.css';

/**
 * Billing & MRR KPI grid. Four tiles mirroring the HTML reference
 * (`docs/HTML DESIGN/Platform Owner/03 _ Billing _ MRR.html`): consolidated
 * MRR, active subscriptions, 30-day churn and failed payments.
 *
 * MRR is reported per currency (the fleet spans COP/USD/etc. and summing across
 * currencies would be wrong) — the largest currency leads the tile, the rest go
 * in the footnote.
 *
 * @param {{ data: object }} props
 */
export function BillingKpis({ data }) {
  const byCurrency = sortByMrrDesc(data?.mrr_by_currency || []);
  const churn = data?.churn || {};
  const failed = data?.failed_payments || {};

  const totalActive = (data?.mrr_by_currency || []).reduce(
    (sum, entry) => sum + (entry.active_subscriptions || 0),
    0,
  );
  const leadMrr = byCurrency[0];
  const restMrr = byCurrency.slice(1);

  return (
    <section className={styles.kpis} aria-label="Indicadores de facturación">
      <KpiTile
        label="MRR consolidado"
        value={leadMrr ? formatMoney(leadMrr.mrr, leadMrr.currency) : '—'}
        footnote={
          restMrr.length > 0
            ? restMrr.map((entry) => formatMoney(entry.mrr, entry.currency)).join(' · ')
            : 'Suscripciones anuales prorrateadas a base mensual'
        }
      />
      <KpiTile
        label="Suscripciones activas"
        value={String(totalActive)}
        footnote={`${churn.past_due_subscriptions ?? 0} en mora`}
      />
      <KpiTile
        label="Churn 30d"
        value={formatPercent(churn.churn_rate)}
        footnote={`${churn.cancelled ?? 0} canceladas · ${churn.active_subscriptions ?? 0} activas`}
      />
      <KpiTile
        label="Cobros fallidos"
        value={String(failed.count ?? 0)}
        footnote="suscripciones en estado past_due"
      />
    </section>
  );
}
