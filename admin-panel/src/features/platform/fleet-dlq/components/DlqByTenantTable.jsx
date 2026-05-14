import { DataTable, EmptyState } from '../../../../components/ui/index.js';
import { RequirePermission } from '../../../../permissions/index.js';
import styles from '../FleetDlq.module.css';

/**
 * "Por tenant" — failed-message counts grouped by tenant, with the dominant
 * error code and the bulk-retry / "enter tenant" actions. Mirrors the HTML
 * reference's per-tenant table.
 *
 * The bulk-retry button is gated behind `platform.outbound_dlq.retry`; the
 * "enter tenant" action support-modes into the tenant (TASK-0077).
 *
 * @param {{
 *   rows: Array<object>,
 *   loading: boolean,
 *   error: string|null,
 *   permissions: object,
 *   onRetry: (tenant: object) => void,
 *   onEnterTenant: (tenant: object) => void,
 *   onReload: () => void,
 * }} props
 */
export function DlqByTenantTable({ rows, loading, error, permissions, onRetry, onEnterTenant, onReload }) {
  if (error) {
    return (
      <EmptyState
        title="No se pudo cargar el DLQ de la flota"
        description={error}
        action={
          <button type="button" className={styles.linkButton} onClick={onReload}>
            Reintentar
          </button>
        }
      />
    );
  }

  const columns = [
    {
      key: 'tenant',
      header: 'Tenant',
      accessor: (row) => row.display_name || row.slug,
    },
    {
      key: 'total',
      header: 'Fallos',
      align: 'right',
      accessor: (row) => String(row.total ?? 0),
    },
    {
      key: 'top_error',
      header: 'Top error',
      accessor: (row) =>
        row.top_error_code ? (
          <span className={styles.code}>
            {row.top_error_code} · {row.top_error_count}
          </span>
        ) : (
          '—'
        ),
    },
    {
      key: 'actions',
      header: 'Acciones',
      accessor: (row) => (
        <div className={styles.rowActions}>
          <RequirePermission
            permissions={permissions}
            capability="platform.outbound_dlq.retry"
            mode="RW"
            hidden
          >
            <button
              type="button"
              className={styles.linkButton}
              onClick={() => onRetry(row)}
            >
              Reintentar
            </button>
          </RequirePermission>
          <button
            type="button"
            className={styles.linkButton}
            onClick={() => onEnterTenant(row)}
          >
            Entrar al tenant
          </button>
        </div>
      ),
    },
  ];

  return (
    <DataTable
      caption="Fallos del DLQ agrupados por tenant"
      columns={columns}
      rows={rows}
      rowKey={(row) => row.tenant_id}
      loading={loading}
    />
  );
}
