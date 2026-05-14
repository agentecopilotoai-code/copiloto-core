import { Card, CardHeader, DataTable, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import { formatDuration, formatPrice } from '../servicesData.js';
import { ServiceReorder } from './ServiceReorder.jsx';
import styles from '../Services.module.css';

function activePromosFor(service, promotions) {
  return (promotions || []).filter(
    (promo) =>
      promo.is_active &&
      (!promo.applies_to_service_ids ||
        promo.applies_to_service_ids.length === 0 ||
        promo.applies_to_service_ids.includes(service.id)),
  );
}

/**
 * Service catalogue table. Columns mirror the HTML reference: name (+
 * description + active-promo badges), category, price, duration, recall, status
 * and the row actions (reorder, edit, deactivate). Reuses the `DataTable`
 * primitive; the reorder control is the `ServiceReorder` component.
 *
 * @param {{
 *   services: Array<object>,
 *   promotions: Array<object>,
 *   isBusy: boolean,
 *   loading: boolean,
 *   onEdit: (service: object) => void,
 *   onDeactivate: (service: object) => void,
 *   onMove: (index: number, direction: number) => void,
 * }} props
 */
export function ServicesTable({ services, promotions, isBusy, loading, onEdit, onDeactivate, onMove }) {
  if (!loading && services.length === 0) {
    return (
      <Card padding="md">
        <EmptyState
          title="Sin servicios"
          description="Aún no hay servicios cargados. Crea el primero con el formulario."
        />
      </Card>
    );
  }

  const columns = [
    {
      key: 'name',
      header: 'Servicio',
      accessor: (row) => {
        const promos = activePromosFor(row, promotions);
        return (
          <div className={styles.serviceCell}>
            <span className={styles.serviceName}>{row.name}</span>
            {row.description ? (
              <span className={styles.serviceDesc}>{row.description}</span>
            ) : null}
            {promos.length > 0 ? (
              <span className={styles.promoRow}>
                {promos.map((promo) => (
                  <StatusBadge key={promo.id} tone="accent">{`🎁 ${promo.name}`}</StatusBadge>
                ))}
              </span>
            ) : null}
          </div>
        );
      },
    },
    { key: 'category', header: 'Categoría', accessor: (row) => row.category || '—' },
    {
      key: 'price',
      header: 'Precio',
      align: 'right',
      accessor: (row) => formatPrice(row.price_amount, row.price_currency),
    },
    {
      key: 'duration',
      header: 'Duración',
      accessor: (row) => formatDuration(row.duration_minutes),
    },
    {
      key: 'recall',
      header: 'Recall',
      accessor: (row) =>
        row.recall_interval_days ? `cada ${row.recall_interval_days} d` : '—',
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
      accessor: (row) => {
        const index = services.indexOf(row);
        return (
          <div className={styles.rowActions}>
            <ServiceReorder
              index={index}
              total={services.length}
              disabled={isBusy}
              onMove={(direction) => onMove(index, direction)}
            />
            <button
              type="button"
              className={styles.secondaryButton}
              disabled={isBusy}
              onClick={() => onEdit(row)}
            >
              Editar
            </button>
            {row.is_active ? (
              <button
                type="button"
                className={styles.secondaryButton}
                disabled={isBusy}
                onClick={() => onDeactivate(row)}
              >
                Desactivar
              </button>
            ) : null}
          </div>
        );
      },
    },
  ];

  return (
    <Card padding="md">
      <CardHeader title="Servicios" subtitle="Catálogo que el bot ofrece al cliente" />
      <DataTable
        caption="Catálogo de servicios del tenant"
        columns={columns}
        rows={services}
        rowKey={(row) => row.id}
        loading={loading}
      />
    </Card>
  );
}
