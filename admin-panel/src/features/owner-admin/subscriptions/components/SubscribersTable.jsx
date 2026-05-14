import { Card, CardHeader, DataTable, StatusBadge, Tabs } from '../../../../components/ui/index.js';
import {
  SUBSCRIBER_TABS,
  formatBillingDate,
  subscriptionStatusLabel,
  subscriptionStatusTone,
} from '../subscriptionsData.js';
import styles from '../Subscriptions.module.css';

/**
 * Subscribers panel: a tabbed `DataTable` of contact subscriptions. The
 * past-due tab carries a count badge and the row's last-attempt cell surfaces
 * the provider retry link so ops can reconcile a failed charge.
 *
 * @param {{
 *   subscribers: Array<object>,
 *   allSubscribers: Array<object>,
 *   tab: string,
 *   loading: boolean,
 *   saving: boolean,
 *   onTabChange: (tab: string) => void,
 *   onCancel: (sub: object) => void,
 * }} props
 */
export function SubscribersTable({
  subscribers,
  allSubscribers,
  tab,
  loading,
  saving,
  onTabChange,
  onCancel,
}) {
  const pastDueCount = allSubscribers.filter((s) => s.status === 'past_due').length;
  const tabItems = SUBSCRIBER_TABS.map((item) => ({
    value: item.value,
    label:
      item.value === 'past_due' && pastDueCount > 0
        ? `${item.label} (${pastDueCount})`
        : item.label,
  }));

  const columns = [
    {
      key: 'contact',
      header: 'Cliente',
      accessor: (row) =>
        row.contact_display_name || row.contact_phone_e164 || row.contact_id,
    },
    {
      key: 'plan',
      header: 'Plan',
      accessor: (row) => row.plan_name || '—',
    },
    {
      key: 'next_billing',
      header: 'Próximo cobro',
      accessor: (row) => formatBillingDate(row.next_billing_at),
    },
    {
      key: 'status',
      header: 'Estado',
      accessor: (row) => (
        <StatusBadge tone={subscriptionStatusTone(row.status)}>
          {subscriptionStatusLabel(row.status)}
        </StatusBadge>
      ),
    },
    {
      key: 'last_attempt',
      header: 'Último intento',
      accessor: (row) =>
        row.retry_payment_link ? (
          <a
            className={styles.retryLink}
            href={row.retry_payment_link}
            target="_blank"
            rel="noreferrer"
          >
            Reintentar cobro
          </a>
        ) : (
          formatBillingDate(row.last_invoice_at)
        ),
    },
    {
      key: 'actions',
      header: 'Acciones',
      accessor: (row) =>
        row.status === 'cancelled' ? (
          <span className={styles.hint}>—</span>
        ) : (
          <button
            type="button"
            className={styles.secondaryButton}
            disabled={saving}
            onClick={() => onCancel(row)}
          >
            Cancelar
          </button>
        ),
    },
  ];

  return (
    <Card padding="md">
      <CardHeader
        title="Suscriptores"
        subtitle="El webhook reconcilia los eventos de pago de Stripe y MercadoPago"
      />
      <Tabs items={tabItems} value={tab} onChange={onTabChange} />
      <DataTable
        caption="Suscriptores del tenant"
        columns={columns}
        rows={subscribers}
        rowKey={(row) => row.id}
        loading={loading}
      />
    </Card>
  );
}
