import { StatusBadge } from '../ui/StatusBadge.jsx';

const STATUSES = {
  paid: { label: 'Pagado', tone: 'success' },
  pending: { label: 'Pendiente', tone: 'warning' },
  processing: { label: 'Procesando', tone: 'warning' },
  failed: { label: 'Fallido', tone: 'danger' },
  refunded: { label: 'Reembolsado', tone: 'neutral' },
  canceled: { label: 'Cancelado', tone: 'neutral' },
};

/**
 * PaymentBadge — estado de pago de una cita / paquete / suscripción.
 *
 * El estado de pago lo escribe únicamente el webhook firmado del proveedor
 * (fail-closed, ver `docs/DONE.md` TASK-0083/0084); este badge sólo lo refleja.
 *
 * @param {Object} props
 * @param {'paid'|'pending'|'processing'|'failed'|'refunded'|'canceled'|string} props.status
 */
export function PaymentBadge({ status }) {
  const meta = STATUSES[status] || { label: status || 'Sin pago', tone: 'neutral' };
  return <StatusBadge tone={meta.tone}>{meta.label}</StatusBadge>;
}
