import { DataTable, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import { STATE_LABEL, STATE_TONE, TYPE_LABEL, TYPE_TONE } from '../meta.js';
import styles from '../FeatureFlags.module.css';

/**
 * Read-only feature-flag catalogue table. Columns mirror the HTML reference:
 * flag (key + description), default state, rollout %, type and the TASK that
 * introduced it.
 *
 * There is no toggle column — live toggling, rollout and per-tenant overrides
 * are deferred to a backend ticket (the writable feature-flag system does not
 * exist yet). The view is honest about being read-only.
 *
 * @param {{ flags: Array<object>, loading: boolean }} props
 */
export function FeatureFlagsTable({ flags, loading }) {
  if (!loading && (!flags || flags.length === 0)) {
    return (
      <EmptyState
        title="Sin flags"
        description="Ningún feature flag coincide con la búsqueda o el tipo seleccionado."
      />
    );
  }

  const columns = [
    {
      key: 'flag',
      header: 'Flag',
      accessor: (row) => (
        <div className={styles.flagCell}>
          <span className={styles.flagKey}>{row.key}</span>
          <span className={styles.flagDesc}>{row.description}</span>
        </div>
      ),
    },
    {
      key: 'default',
      header: 'Default',
      accessor: (row) => (
        <StatusBadge tone={STATE_TONE[row.default] || 'neutral'}>
          {STATE_LABEL[row.default] || row.default}
        </StatusBadge>
      ),
    },
    {
      key: 'rollout_pct',
      header: 'Rollout',
      align: 'right',
      accessor: (row) => `${row.rollout_pct ?? 0}%`,
    },
    {
      key: 'type',
      header: 'Tipo',
      accessor: (row) => (
        <StatusBadge tone={TYPE_TONE[row.type] || 'neutral'}>
          {TYPE_LABEL[row.type] || row.type}
        </StatusBadge>
      ),
    },
    {
      key: 'related_task',
      header: 'Origen',
      accessor: (row) => <span className={styles.flagTask}>{row.related_task}</span>,
    },
  ];

  return (
    <DataTable
      caption="Catálogo de feature flags del producto"
      columns={columns}
      rows={flags}
      rowKey={(row) => row.key}
      loading={loading}
    />
  );
}
