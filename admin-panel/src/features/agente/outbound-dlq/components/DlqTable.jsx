import { Card, CardHeader, DataTable, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import { errorCodeLabel, formatDate, shortId, totalFailures } from '../outboundDlqData.js';
import styles from '../OutboundDLQ.module.css';

/**
 * Failed-message table. Reuses `DataTable`; each row exposes "Ver" (detail) and
 * "Reintentar" actions. Presentational — list + retry state come from the
 * `useOutboundDlqData` hook via props.
 *
 * @param {{
 *   items: Array<object>,
 *   totals: Array<object>,
 *   isLoading: boolean,
 *   retryingId: string | null,
 *   onViewDetail: (item: object) => void,
 *   onRetry: (item: object) => void,
 * }} props
 */
export function DlqTable({ items, totals, isLoading, retryingId, onViewDetail, onRetry }) {
  const columns = [
    {
      key: 'id',
      header: 'Mensaje',
      accessor: (row) => (
        <button
          type="button"
          className={styles.linkButton}
          onClick={() => onViewDetail(row)}
        >
          {shortId(row.id)}
        </button>
      ),
    },
    {
      key: 'error',
      header: 'Error',
      accessor: (row) => (
        <div className={styles.errorCell}>
          <StatusBadge tone="danger">{row.error_code}</StatusBadge>
          <span className={styles.errorLabel}>{errorCodeLabel(row.error_code)}</span>
        </div>
      ),
    },
    { key: 'message_type', header: 'Tipo', accessor: (row) => row.message_type || '—' },
    {
      key: 'body_preview',
      header: 'Preview',
      accessor: (row) => <span className={styles.preview}>{row.body_preview || '—'}</span>,
    },
    { key: 'failed_at', header: 'Cuándo', accessor: (row) => formatDate(row.failed_at) },
    {
      key: 'actions',
      header: 'Acciones',
      accessor: (row) => (
        <div className={styles.rowActions}>
          <button
            type="button"
            className={styles.secondaryButton}
            onClick={() => onViewDetail(row)}
          >
            Ver
          </button>
          <button
            type="button"
            className={styles.primaryButton}
            onClick={() => onRetry(row)}
            disabled={retryingId === row.id}
            data-action="retry"
          >
            {retryingId === row.id ? 'Reintentando…' : 'Reintentar'}
          </button>
        </div>
      ),
    },
  ];

  return (
    <Card padding="md">
      <CardHeader
        title="Mensajes fallidos"
        subtitle={`${totalFailures(totals)} fallos agrupados · ${items.length} en vista`}
      />
      {isLoading && items.length === 0 ? (
        <p className={styles.hint}>Cargando…</p>
      ) : items.length === 0 ? (
        <EmptyState
          title="Sin mensajes en la DLQ"
          description="El worker no tiene mensajes outbound fallidos para los filtros aplicados."
        />
      ) : (
        <DataTable
          caption="Mensajes outbound fallidos"
          columns={columns}
          rows={items}
          rowKey={(row) => row.id}
        />
      )}
    </Card>
  );
}
