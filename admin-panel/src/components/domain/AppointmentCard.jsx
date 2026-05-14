import { StatusBadge } from '../ui/StatusBadge.jsx';
import { PaymentBadge } from './PaymentBadge.jsx';
import styles from './AppointmentCard.module.css';

const STATUS_TONE = {
  confirmed: 'success',
  completed: 'success',
  pending: 'warning',
  rescheduled: 'warning',
  no_show: 'danger',
  canceled: 'danger',
  cancelled: 'danger',
};

/**
 * Mapea el estado de una cita a un tono de `StatusBadge`.
 * @param {string} status
 * @returns {'neutral'|'accent'|'success'|'warning'|'danger'}
 */
export function appointmentStatusTone(status) {
  return STATUS_TONE[status] || 'neutral';
}

/**
 * AppointmentCard — resumen de una cita (historial de contacto, citas del día).
 *
 * No hace fetch: recibe la cita y los textos ya formateados por props.
 *
 * @param {Object} props
 * @param {Object} props.appointment Cita con `service_name`/`service_code`, `status`,
 *   `resource_name`, `payment_status`.
 * @param {React.ReactNode} [props.dateText] Fecha/hora ya formateada.
 * @param {boolean} [props.showPayment=false] Muestra el `PaymentBadge`.
 * @param {React.ReactNode} [props.actions] Slot de acciones (botones).
 */
export function AppointmentCard({ appointment, dateText, showPayment = false, actions }) {
  if (!appointment) return null;
  const title = appointment.service_name || appointment.service_code || 'Cita';
  return (
    <article className={styles.card}>
      <header className={styles.head}>
        <strong className={styles.title}>{title}</strong>
        <StatusBadge tone={appointmentStatusTone(appointment.status)}>
          {appointment.status}
        </StatusBadge>
        {showPayment && appointment.payment_status ? (
          <PaymentBadge status={appointment.payment_status} />
        ) : null}
      </header>
      <p className={styles.meta}>
        {dateText || '—'} · {appointment.resource_name || '—'}
      </p>
      {actions ? <div className={styles.actions}>{actions}</div> : null}
    </article>
  );
}
