import { Card, CardHeader, DataTable, StatusBadge } from '../../../../components/ui/index.js';
import { formatMrrByCurrency } from '../format.js';

function formatDate(value) {
  if (!value) return '—';
  try {
    return new Date(value).toLocaleDateString('es-CO', {
      day: '2-digit',
      month: 'short',
      year: 'numeric',
    });
  } catch {
    return '—';
  }
}

/**
 * "Tenants por plan" — per-tenant recurring revenue, active subscription count,
 * next charge date and past-due count. Mirrors the HTML reference's tenant
 * table. No contact PII — tenant identities and aggregates only.
 *
 * @param {{ tenants: Array<object> }} props
 */
export function BillingTenantsTable({ tenants }) {
  const columns = [
    {
      key: 'tenant',
      header: 'Tenant',
      accessor: (row) => row.display_name || row.slug,
    },
    {
      key: 'country',
      header: 'País',
      accessor: (row) => row.country_code || '—',
    },
    {
      key: 'active_subscriptions',
      header: 'Activas',
      align: 'right',
      accessor: (row) => String(row.active_subscriptions ?? 0),
    },
    {
      key: 'mrr',
      header: 'MRR mensual',
      align: 'right',
      accessor: (row) => formatMrrByCurrency(row.mrr_by_currency),
    },
    {
      key: 'next_billing_at',
      header: 'Próximo cobro',
      accessor: (row) => formatDate(row.next_billing_at),
    },
    {
      key: 'past_due',
      header: 'Estado',
      accessor: (row) =>
        row.past_due_subscriptions > 0 ? (
          <StatusBadge tone="danger">{`${row.past_due_subscriptions} en mora`}</StatusBadge>
        ) : (
          <StatusBadge tone="success">Al día</StatusBadge>
        ),
    },
  ];

  return (
    <Card padding="md">
      <CardHeader
        title="Tenants por plan"
        subtitle="Ingreso recurrente por tenant · ordenado por MRR"
      />
      <DataTable
        caption="MRR por tenant de la flota"
        columns={columns}
        rows={tenants || []}
        rowKey={(row) => row.tenant_id}
      />
    </Card>
  );
}
