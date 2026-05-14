import { Card, CardHeader, DataTable, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import { ROLES } from '../../../../permissions/index.js';
import { ACCESS_LABEL, ACCESS_TONE, ROLE_LABEL } from '../rolesAclData.js';
import styles from '../RolesAcl.module.css';

function AccessCell({ level }) {
  if (!level) return <span className={styles.muted}>—</span>;
  return (
    <StatusBadge tone={ACCESS_TONE[level] || 'neutral'}>
      {ACCESS_LABEL[level] || level}
    </StatusBadge>
  );
}

const ROLE_COLUMNS = ROLES.map((role) => ({
  key: role,
  header: ROLE_LABEL[role] || role,
  accessor: (row) => <AccessCell level={row.access[role]} />,
}));

const COLUMNS = [
  {
    key: 'capability',
    header: 'Capacidad',
    accessor: (row) => <span className={styles.capKey}>{row.capability}</span>,
  },
  ...ROLE_COLUMNS,
];

/**
 * Read-only capability × role matrix, rendered one `<DataTable>` per capability
 * group. The data is the `PERMISSIONS` matrix of UI-005 — this view is the
 * matrix made visible, never a second source of truth.
 *
 * @param {{ groups: Array<{ group: string, rows: Array<object> }> }} props
 */
export function RolesAclMatrix({ groups }) {
  if (!groups || groups.length === 0) {
    return (
      <Card padding="md">
        <EmptyState
          title="Sin capacidades"
          description="Ninguna capacidad coincide con la búsqueda."
        />
      </Card>
    );
  }

  return (
    <div className={styles.groups}>
      {groups.map(({ group, rows }) => (
        <Card key={group} padding="md">
          <CardHeader title={group} subtitle={`${rows.length} capacidades`} />
          <DataTable
            caption={`Matriz de permisos · ${group}`}
            columns={COLUMNS}
            rows={rows}
            rowKey={(row) => row.capability}
          />
        </Card>
      ))}
    </div>
  );
}
