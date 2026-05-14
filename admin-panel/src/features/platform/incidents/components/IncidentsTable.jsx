import { DataTable, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import { formatDateTime, KIND_LABEL, SEVERITY_TONE, STATUS_LABEL, STATUS_TONE } from '../meta.js';
import styles from '../Incidents.module.css';

/**
 * Incidents list as a `<DataTable>`. Columns mirror the HTML reference: severity,
 * type, affected tenant, status, detected time and runbook. Clicking a row opens
 * the detail drawer.
 *
 * @param {{
 *   rows: Array<object>,
 *   loading: boolean,
 *   error: string|null,
 *   onSelect: (row: object) => void,
 *   onRetry: () => void,
 * }} props
 */
export function IncidentsTable({ rows, loading, error, onSelect, onRetry }) {
  if (error) {
    return (
      <EmptyState
        title="No se pudo cargar Incidentes"
        description={error}
        action={
          <button type="button" className={styles.linkButton} onClick={onRetry}>
            Reintentar
          </button>
        }
      />
    );
  }

  const columns = [
    {
      key: 'severity',
      header: 'Severidad',
      accessor: (row) => (
        <StatusBadge tone={SEVERITY_TONE[row.severity] || 'neutral'}>
          {row.severity}
        </StatusBadge>
      ),
    },
    {
      key: 'kind',
      header: 'Tipo',
      accessor: (row) => KIND_LABEL[row.kind] || row.kind,
    },
    {
      key: 'tenant',
      header: 'Tenant',
      accessor: (row) =>
        row.tenant_name || <span className={styles.muted}>Sistema (sin tenant)</span>,
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
      key: 'created_at',
      header: 'Detectado',
      accessor: (row) => formatDateTime(row.created_at),
    },
    {
      key: 'runbook',
      header: 'Runbook',
      accessor: (row) =>
        row.runbook ? (
          <span className={styles.runbook}>{row.runbook}</span>
        ) : (
          <span className={styles.muted}>—</span>
        ),
    },
  ];

  return (
    <DataTable
      caption="Feed de incidentes de la plataforma"
      columns={columns}
      rows={rows}
      rowKey={(row) => row.id}
      loading={loading}
      onRowClick={onSelect}
    />
  );
}
