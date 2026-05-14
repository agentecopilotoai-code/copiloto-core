import { Card, CardHeader, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import { formatMoney } from '../format.js';
import styles from '../BillingMrr.module.css';

const PROVIDER_LABEL = {
  stripe: 'Stripe',
  mercadopago: 'MercadoPago',
};

/**
 * "Cobros fallidos" — past-due subscriptions grouped per (tenant, provider).
 * Mirrors the HTML reference's failed-payments block. Aggregated only — no
 * contact PII; the retry flow itself lives in the tenant-scoped Subscriptions
 * module (TASK-0075), this view is read-only fleet visibility.
 *
 * @param {{ failedPayments: object }} props
 */
export function FailedPaymentsPanel({ failedPayments }) {
  const items = failedPayments?.items || [];

  return (
    <Card padding="md">
      <CardHeader
        title="Cobros fallidos"
        subtitle={`${failedPayments?.count ?? 0} suscripciones en mora · agregado por tenant y proveedor`}
      />
      {items.length > 0 ? (
        <ul className={styles.list}>
          {items.map((item) => (
            <li
              key={`${item.tenant_id}-${item.payment_provider}-${item.currency}`}
              className={styles.listItem}
            >
              <div className={styles.listMain}>
                <span className={styles.listName}>{item.display_name || item.slug}</span>
                <span className={styles.listMeta}>
                  {PROVIDER_LABEL[item.payment_provider] || item.payment_provider}
                </span>
              </div>
              <div className={styles.listSide}>
                <StatusBadge tone="danger">{`${item.failed_count} fallido(s)`}</StatusBadge>
                <span className={styles.listAmount}>
                  {formatMoney(item.amount_pending, item.currency)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <EmptyState
          title="Sin cobros fallidos"
          description="Ninguna suscripción de la flota está en estado past_due."
        />
      )}
    </Card>
  );
}
