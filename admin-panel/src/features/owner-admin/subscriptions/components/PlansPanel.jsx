import { Card, CardHeader, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import { billingPeriodLabel, formatPrice, subscriptionStatusLabel } from '../subscriptionsData.js';
import styles from '../Subscriptions.module.css';

/**
 * Plans panel: the catalogue of subscription plans with the price, billing
 * period, status badge and the row actions (edit, archive). Presentational —
 * state and mutations come from the `useSubscriptionsData` hook via props.
 *
 * @param {{
 *   plans: Array<object>,
 *   loading: boolean,
 *   saving: boolean,
 *   onEdit: (plan: object) => void,
 *   onArchive: (plan: object) => void,
 * }} props
 */
export function PlansPanel({ plans, loading, saving, onEdit, onArchive }) {
  return (
    <Card padding="md">
      <CardHeader
        title="Planes"
        subtitle="Cobros recurrentes vía Stripe y MercadoPago"
      />
      {loading ? (
        <p className={styles.hint}>Cargando…</p>
      ) : plans.length === 0 ? (
        <EmptyState
          title="Sin planes"
          description="Aún no hay planes de suscripción. Crea el primero con «Nuevo plan»."
        />
      ) : (
        <ul className={styles.planList}>
          {plans.map((plan) => (
            <li key={plan.id} className={styles.planRow}>
              <div className={styles.planInfo}>
                <span className={styles.planName}>{plan.name}</span>
                <span className={styles.planMeta}>
                  {formatPrice(plan.price_amount, plan.currency)} ·{' '}
                  {billingPeriodLabel(plan.billing_period)}
                </span>
                {plan.description ? (
                  <span className={styles.planDesc}>{plan.description}</span>
                ) : null}
              </div>
              <div className={styles.planAside}>
                <StatusBadge tone={plan.status === 'active' ? 'success' : 'neutral'}>
                  {subscriptionStatusLabel(plan.status)}
                </StatusBadge>
                <div className={styles.rowActions}>
                  <button
                    type="button"
                    className={styles.secondaryButton}
                    disabled={saving}
                    onClick={() => onEdit(plan)}
                  >
                    Editar
                  </button>
                  {plan.status === 'active' ? (
                    <button
                      type="button"
                      className={styles.secondaryButton}
                      disabled={saving}
                      onClick={() => onArchive(plan)}
                    >
                      Archivar
                    </button>
                  ) : null}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
