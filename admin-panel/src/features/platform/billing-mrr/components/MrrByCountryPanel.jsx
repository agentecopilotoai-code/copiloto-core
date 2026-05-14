import { Card, CardHeader, EmptyState } from '../../../../components/ui/index.js';
import { formatMrrByCurrency } from '../format.js';
import styles from '../BillingMrr.module.css';

/**
 * "Países · MRR por geografía" — recurring revenue grouped by tenant country.
 * Mirrors the HTML reference's geography block.
 *
 * @param {{ countries: Array<object> }} props
 */
export function MrrByCountryPanel({ countries }) {
  const rows = countries || [];

  return (
    <Card padding="md">
      <CardHeader
        title="Países · MRR por geografía"
        subtitle="Ingreso recurrente por país del tenant"
      />
      {rows.length > 0 ? (
        <ul className={styles.list}>
          {rows.map((row) => (
            <li key={row.country_code} className={styles.listItem}>
              <div className={styles.listMain}>
                <span className={styles.listName}>{row.country_code}</span>
                <span className={styles.listMeta}>
                  {row.tenant_count} tenants · {row.active_subscriptions} activas
                </span>
              </div>
              <span className={styles.listAmount}>
                {formatMrrByCurrency(row.mrr_by_currency)}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState
          title="Sin datos de geografía"
          description="Ningún tenant de la flota tiene suscripciones activas todavía."
        />
      )}
    </Card>
  );
}
