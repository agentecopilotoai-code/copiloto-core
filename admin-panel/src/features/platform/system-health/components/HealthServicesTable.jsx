import { Card, CardHeader, DataTable, StatusBadge } from '../../../../components/ui/index.js';

const STATUS_TONE = {
  ok: 'success',
  warn: 'warning',
  down: 'danger',
};

const STATUS_LABEL = {
  ok: 'OK',
  warn: 'WARN',
  down: 'DOWN',
};

/**
 * Per-service health table: API, Postgres, workers and provider circuit
 * breakers, synthesised server-side from the metrics snapshot + a live DB
 * probe. Columns mirror the HTML reference's "Servicios" block.
 *
 * @param {{ services: Array<object> }} props
 */
export function HealthServicesTable({ services }) {
  const columns = [
    {
      key: 'label',
      header: 'Servicio',
      accessor: (row) => row.label,
    },
    {
      key: 'status',
      header: 'Estado',
      accessor: (row) => (
        <StatusBadge tone={STATUS_TONE[row.status] || 'neutral'}>
          {STATUS_LABEL[row.status] || row.status}
        </StatusBadge>
      ),
    },
    {
      key: 'detail',
      header: 'Detalle',
      accessor: (row) => row.detail || '—',
    },
  ];

  return (
    <Card padding="md">
      <CardHeader
        title="Servicios"
        subtitle="API · base de datos · workers · breakers de proveedores"
      />
      <DataTable
        caption="Estado por servicio de la plataforma"
        columns={columns}
        rows={services || []}
        rowKey={(row) => row.key}
      />
    </Card>
  );
}
