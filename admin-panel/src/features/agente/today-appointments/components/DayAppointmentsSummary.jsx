import { formatTime, statusLabel } from '../todayAppointmentsData.js';
import styles from '../TodayAppointments.module.css';

/**
 * Fila de KPIs de la vista "Citas del día". Solo pinta conteos derivables de la
 * lista real de citas (total del día, sin confirmar, atendidas, próxima cita).
 *
 * Diferencia intencional declarada: el HTML muestra además "Ocupación %" e
 * "Ingreso proyectado" — `listAppointments` devuelve registros planos y no
 * expone capacidad de agenda ni monto proyectado del día, así que se difieren
 * (no se inventan datos).
 *
 * @param {{ counts: { total: number, unconfirmed: number, attended: number,
 *   next: object|null } }} props
 */
export function DayAppointmentsSummary({ counts }) {
  const { total, unconfirmed, attended, next } = counts;
  const nextValue = next ? formatTime(next.starts_at) : '—';
  const nextHint = next
    ? `${next.service_name || next.service_code || 'Cita'} · ${next.resource_name || '—'}`
    : 'Sin citas próximas hoy';

  const tiles = [
    { key: 'total', label: 'Citas del día', value: String(total), hint: 'programadas en total' },
    {
      key: 'unconfirmed',
      label: 'Sin confirmar',
      value: String(unconfirmed),
      hint: 'esperan confirmación del cliente',
    },
    {
      key: 'attended',
      label: 'Atendidas',
      value: String(attended),
      hint: `estado ${statusLabel('completed').toLowerCase()}`,
    },
    { key: 'next', label: 'Próxima', value: nextValue, hint: nextHint },
  ];

  return (
    <section className={styles.summary} aria-label="Resumen de citas del día">
      {tiles.map((tile) => (
        <article key={tile.key} className={styles.tile}>
          <span className={styles.tileLabel}>{tile.label}</span>
          <strong className={styles.tileValue}>{tile.value}</strong>
          <span className={styles.tileHint}>{tile.hint}</span>
        </article>
      ))}
    </section>
  );
}
