import { Card, CardHeader, DataTable, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import { describeServices, formatPrice } from '../packagesData.js';
import styles from '../Packages.module.css';

/**
 * Catalogue table for treatment packages. Columns mirror the HTML reference:
 * package (name + description + included services), price, sessions, validity,
 * status and the row actions (edit, deactivate). Reuses the `DataTable`
 * primitive.
 *
 * @param {{
 *   packages: Array<object>,
 *   serviceMap: Map<string, object>,
 *   loading: boolean,
 *   saving: boolean,
 *   onEdit: (pkg: object) => void,
 *   onDeactivate: (pkg: object) => void,
 * }} props
 */
export function PackagesTable({ packages, serviceMap, loading, saving, onEdit, onDeactivate }) {
  if (!loading && packages.length === 0) {
    return (
      <Card padding="md">
        <EmptyState
          title="Sin paquetes"
          description="Aún no hay paquetes en el catálogo. Crea el primero con «Nuevo paquete»."
        />
      </Card>
    );
  }

  const columns = [
    {
      key: 'name',
      header: 'Paquete',
      accessor: (row) => (
        <div className={styles.packageCell}>
          <span className={styles.packageName}>{row.name}</span>
          <span className={styles.packageServices}>
            {describeServices(row.includes_service_ids, serviceMap)}
          </span>
          {row.description ? (
            <span className={styles.packageDesc}>{row.description}</span>
          ) : null}
        </div>
      ),
    },
    {
      key: 'price',
      header: 'Precio',
      align: 'right',
      accessor: (row) => formatPrice(row.price_amount, row.price_currency),
    },
    {
      key: 'sessions',
      header: 'Sesiones',
      align: 'right',
      accessor: (row) => String(row.total_sessions ?? 0),
    },
    {
      key: 'validity',
      header: 'Vigencia',
      accessor: (row) => (row.validity_days ? `${row.validity_days} d` : 'Sin vencimiento'),
    },
    {
      key: 'status',
      header: 'Estado',
      accessor: (row) => (
        <StatusBadge tone={row.is_active ? 'success' : 'neutral'}>
          {row.is_active ? 'Activo' : 'Inactivo'}
        </StatusBadge>
      ),
    },
    {
      key: 'actions',
      header: 'Acciones',
      accessor: (row) => (
        <div className={styles.rowActions}>
          <button
            type="button"
            className={styles.secondaryButton}
            disabled={saving}
            onClick={() => onEdit(row)}
          >
            Editar
          </button>
          {row.is_active ? (
            <button
              type="button"
              className={styles.secondaryButton}
              disabled={saving}
              onClick={() => onDeactivate(row)}
            >
              Desactivar
            </button>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <Card padding="md">
      <CardHeader
        title="Catálogo de paquetes"
        subtitle="Planes multi-cita con saldo de sesiones"
      />
      <DataTable
        caption="Catálogo de paquetes del tenant"
        columns={columns}
        rows={packages}
        rowKey={(row) => row.id}
        loading={loading}
      />
    </Card>
  );
}
