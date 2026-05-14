import styles from '../FleetDlq.module.css';

const WINDOW_OPTIONS = [
  { value: 60, label: 'Última hora' },
  { value: 360, label: 'Últimas 6 horas' },
  { value: 1440, label: 'Últimas 24 horas' },
  { value: 10080, label: 'Últimos 7 días' },
];

/**
 * Filter bar for the Fleet DLQ view. The window select and the error-code input
 * map 1:1 to the `window_minutes` / `error_code` query parameters of
 * `GET /v1/platform/outbound-dlq`. Dumb component — the hook handles refetch.
 *
 * @param {{
 *   filters: {windowMinutes?: number, errorCode?: string},
 *   onChange: (next: object) => void,
 * }} props
 */
export function DlqFilters({ filters, onChange }) {
  return (
    <section className={styles.filters} aria-label="Filtros del DLQ">
      <label className={styles.filter}>
        <span className={styles.filterLabel}>Ventana</span>
        <select
          value={filters.windowMinutes || 60}
          onChange={(event) =>
            onChange({ ...filters, windowMinutes: Number(event.target.value) })
          }
        >
          {WINDOW_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label className={`${styles.filter} ${styles.filterGrow}`}>
        <span className={styles.filterLabel}>Error code</span>
        <input
          type="text"
          value={filters.errorCode || ''}
          onChange={(event) => onChange({ ...filters, errorCode: event.target.value })}
          placeholder="ej. 80007, 190, transport_error"
          maxLength={64}
        />
      </label>
    </section>
  );
}
