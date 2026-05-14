import styles from '../Incidents.module.css';

const STATUS_OPTIONS = [
  { value: '', label: 'Todos los estados' },
  { value: 'pending', label: 'Pendientes' },
  { value: 'failed', label: 'Fallidos' },
  { value: 'sent', label: 'Notificados' },
];

const KIND_OPTIONS = [
  { value: '', label: 'Todos los tipos' },
  { value: 'backup_failure', label: 'Fallo de backup' },
  { value: 'outbound_dlq_threshold', label: 'Umbral DLQ outbound' },
  { value: 'complaint', label: 'Queja' },
  { value: 'negative_feedback', label: 'Feedback negativo' },
];

/**
 * Filter bar for the Incidents view. The two selects map 1:1 to the `status`
 * and `kind` query parameters of `GET /v1/platform/incidents`. Dumb component —
 * the calling hook handles the refetch.
 *
 * @param {{
 *   filters: {status?: string, kind?: string},
 *   onChange: (next: object) => void,
 * }} props
 */
export function IncidentFilters({ filters, onChange }) {
  const update = (key) => (event) => onChange({ ...filters, [key]: event.target.value });

  return (
    <section className={styles.filters} aria-label="Filtros de incidentes">
      <label className={styles.filter}>
        <span className={styles.filterLabel}>Estado</span>
        <select value={filters.status || ''} onChange={update('status')}>
          {STATUS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label className={styles.filter}>
        <span className={styles.filterLabel}>Tipo</span>
        <select value={filters.kind || ''} onChange={update('kind')}>
          {KIND_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}
