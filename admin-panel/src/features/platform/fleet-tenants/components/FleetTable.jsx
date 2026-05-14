import { DataTable, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import styles from '../FleetTenants.module.css';

const STATUS_TONE = {
  active: 'success',
  trial: 'accent',
  suspended: 'warning',
  churned: 'danger',
};

const STATUS_LABEL = {
  active: 'Activo',
  trial: 'Trial',
  suspended: 'Suspendido',
  churned: 'Churned',
};

function initials(name) {
  if (!name) return '··';
  const trimmed = name.trim();
  if (!trimmed) return '··';
  const parts = trimmed.split(/\s+/).slice(0, 2);
  return parts.map((part) => part[0]?.toUpperCase() || '').join('') || '··';
}

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

function TenantCell({ row }) {
  return (
    <div className={styles.tenantCell}>
      <span className={styles.avatar} aria-hidden="true">
        {initials(row.display_name || row.legal_name)}
      </span>
      <div className={styles.tenantText}>
        <span className={styles.tenantName}>{row.display_name || row.legal_name}</span>
        <span className={styles.tenantMeta}>
          {row.slug} · {row.country_code}
        </span>
      </div>
    </div>
  );
}

/**
 * Tenant list as a `<DataTable>`. Columns mirror the HTML reference
 * (`docs/HTML DESIGN/Platform Owner/01 _ Fleet _ Tenants.html`): tenant +
 * slug + country, status, vertical, member count, last activity, owner email.
 *
 * MRR / "Conv. agendamiento %" / sparkline columns from the HTML are deferred
 * to UI-006.3 (Billing) and UI-006.2 (System Health) where the data lives.
 *
 * @param {{
 *   rows: Array<object>,
 *   loading: boolean,
 *   error: string|null,
 *   onSelect: (row: object) => void,
 *   onRetry: () => void,
 * }} props
 */
export function FleetTable({ rows, loading, error, onSelect, onRetry }) {
  if (error) {
    return (
      <EmptyState
        title="No se pudo cargar la flota"
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
      key: 'tenant',
      header: 'Tenant',
      accessor: (row) => <TenantCell row={row} />,
    },
    {
      key: 'status',
      header: 'Status',
      accessor: (row) => (
        <StatusBadge tone={STATUS_TONE[row.status] || 'neutral'}>
          {STATUS_LABEL[row.status] || row.status}
        </StatusBadge>
      ),
    },
    {
      key: 'vertical',
      header: 'Vertical',
      accessor: (row) => row.vertical_code || '—',
    },
    {
      key: 'member_count',
      header: 'Miembros',
      align: 'right',
      accessor: (row) => String(row.member_count ?? 0),
    },
    {
      key: 'last_activity',
      header: 'Última actividad',
      accessor: (row) => formatDate(row.last_activity_at || row.updated_at),
    },
    {
      key: 'owner',
      header: 'Owner',
      accessor: (row) => row.owner_email || <span className={styles.muted}>Sin owner</span>,
    },
  ];

  return (
    <DataTable
      caption="Listado de tenants de la flota"
      columns={columns}
      rows={rows}
      rowKey={(row) => row.id}
      loading={loading}
      onRowClick={onSelect}
    />
  );
}
