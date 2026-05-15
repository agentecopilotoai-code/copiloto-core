import { AppointmentCard } from '../../../../components/domain/index.js';
import { Card, EmptyState } from '../../../../components/ui/index.js';
import { formatDateTime, formatTime } from '../todayAppointmentsData.js';
import styles from '../TodayAppointments.module.css';

/**
 * Listado de las citas del día, ordenadas por hora. Cada fila reusa el
 * componente de dominio `AppointmentCard` (que a su vez reusa `StatusBadge`),
 * con el `dateText` ya formateado y el `PaymentBadge` activado. La etiqueta de
 * hora `HH:MM` se renderiza como columna izquierda de la fila.
 *
 * @param {object} props
 * @param {object[]} props.appointments — citas del día ya filtradas y ordenadas
 * @param {boolean} props.isLoading
 * @param {string} props.dayLabel — etiqueta legible del día seleccionado
 */
export function TodayAppointmentsList({ appointments, isLoading, dayLabel }) {
  if (isLoading && appointments.length === 0) {
    return (
      <Card padding="md">
        <EmptyState
          title="Cargando citas…"
          description="Consultando la agenda del tenant."
        />
      </Card>
    );
  }

  if (appointments.length === 0) {
    return (
      <Card padding="md">
        <EmptyState
          title="Sin citas para este día"
          description={`No hay citas programadas para ${dayLabel}.`}
        />
      </Card>
    );
  }

  return (
    <section className={styles.list} aria-label={`Listado de citas — ${dayLabel}`}>
      {appointments.map((appointment) => (
        <div key={appointment.id} className={styles.listRow}>
          <span className={styles.slotTime} aria-hidden="true">
            {formatTime(appointment.starts_at)}
          </span>
          <div className={styles.listCard}>
            <AppointmentCard
              appointment={appointment}
              dateText={formatDateTime(appointment.starts_at)}
              showPayment
            />
          </div>
        </div>
      ))}
    </section>
  );
}
