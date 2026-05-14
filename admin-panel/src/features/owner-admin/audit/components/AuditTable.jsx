import { Card, CardHeader, DataTable, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import { formatDate } from '../auditData.js';
import styles from '../AuditPanel.module.css';

/**
 * Audit-log results table. Reuses `DataTable`; presentational — the log rows
 * come from the `useAuditData` hook. Renders nothing until the first query
 * (`loaded`).
 *
 * @param {{ logs: Array<object>, loaded: boolean }} props
 */
export function AuditTable({ logs, loaded }) {
  if (!loaded) return null;

  const columns = [
    {
      key: 'created_at',
      header: 'Fecha',
      accessor: (row) => <time>{formatDate(row.created_at)}</time>,
    },
    {
      key: 'actor_type',
      header: 'Actor',
      accessor: (row) => <StatusBadge tone="neutral">{row.actor_type}</StatusBadge>,
    },
    { key: 'action', header: 'Acción', accessor: (row) => <code>{row.action}</code> },
    { key: 'entity_type', header: 'Entidad', accessor: (row) => row.entity_type },
    {
      key: 'entity_id',
      header: 'ID entidad',
      accessor: (row) => <small className={styles.entityId}>{row.entity_id}</small>,
    },
  ];

  return (
    <Card padding="md">
      <CardHeader
        title={`Eventos (${logs.length})`}
        subtitle="Orden cronológico inverso."
      />
      {logs.length === 0 ? (
        <EmptyState
          title="Sin resultados"
          description="Ningún registro coincide con los filtros aplicados."
        />
      ) : (
        <div data-testid="audit-table">
          <DataTable
            caption="Registro de auditoría del tenant"
            columns={columns}
            rows={logs}
            rowKey={(row) => row.id}
          />
        </div>
      )}
    </Card>
  );
}
