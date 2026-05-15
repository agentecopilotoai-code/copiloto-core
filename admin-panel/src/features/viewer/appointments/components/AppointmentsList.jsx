import { AppointmentCard } from '../../../../components/domain/index.js';
import { Card, EmptyState, Pagination } from '../../../../components/ui/index.js';
import { formatDateRange } from '../viewerAppointmentsData.js';
import styles from '../ViewerAppointments.module.css';

/**
 * UI-010.3 — Listado paginado de citas en modo solo lectura.
 *
 * Reusa el componente de dominio `AppointmentCard` con `dateText` ya formateado
 * y sin slot `actions` (los Viewers no obtienen acciones de fila — criterio
 * global UI-010). `showPayment` queda en `false` porque la columna de pago no
 * pertenece a la vista de lectura; el listado se mantiene minimalista. La
 * paginación se delega al primitivo `Pagination`. Estados de carga y vacío
 * usan `EmptyState`.
 *
 * @param {{
 *   appointments: object[],
 *   isLoading: boolean,
 *   page: number,
 *   totalPages: number,
 *   onPageChange: (page: number) => void,
 * }} props
 */
export function AppointmentsList({
  appointments,
  isLoading,
  page,
  totalPages,
  onPageChange,
}) {
  if (isLoading && appointments.length === 0) {
    return (
      <Card padding="md">
        <EmptyState
          title="Cargando citas…"
          description="Consultando el listado de citas del tenant."
        />
      </Card>
    );
  }

  if (appointments.length === 0) {
    return (
      <Card padding="md">
        <EmptyState
          title="Sin citas en este filtro"
          description="Ajusta los filtros o limpia la selección para ver más resultados."
        />
      </Card>
    );
  }

  return (
    <section className={styles.list} aria-label="Listado de citas">
      <ul className={styles.cards}>
        {appointments.map((appointment) => (
          <li key={appointment.id} className={styles.cardItem}>
            <AppointmentCard
              appointment={appointment}
              dateText={formatDateRange(appointment)}
              showPayment={false}
            />
          </li>
        ))}
      </ul>
      <Pagination
        page={page}
        pageCount={totalPages}
        onPageChange={onPageChange}
      />
    </section>
  );
}
