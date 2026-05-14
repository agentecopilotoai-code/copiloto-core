import { Card, CardHeader, DataTable } from '../../../../components/ui/index.js';
import { formatMoney } from '../format.js';

const PERIOD_LABEL = {
  monthly: 'Mensual',
  quarterly: 'Trimestral',
  yearly: 'Anual',
};

/**
 * "Composición del MRR" — recurring revenue broken down by subscription plan.
 * Mirrors the HTML reference's plan composition block.
 *
 * @param {{ plans: Array<object> }} props
 */
export function MrrByPlanTable({ plans }) {
  const columns = [
    {
      key: 'plan_name',
      header: 'Plan',
      accessor: (row) => row.plan_name || '—',
    },
    {
      key: 'billing_period',
      header: 'Período',
      accessor: (row) => PERIOD_LABEL[row.billing_period] || row.billing_period,
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
      accessor: (row) => formatMoney(row.mrr, row.currency),
    },
  ];

  return (
    <Card padding="md">
      <CardHeader
        title="Composición del MRR"
        subtitle="Ingreso recurrente mensual-normalizado por plan"
      />
      <DataTable
        caption="MRR por plan de suscripción"
        columns={columns}
        rows={plans || []}
        rowKey={(row, index) => `${row.plan_name}-${row.billing_period}-${row.currency}-${index}`}
      />
    </Card>
  );
}
