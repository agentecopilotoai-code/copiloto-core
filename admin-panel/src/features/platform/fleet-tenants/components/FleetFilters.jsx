import styles from '../FleetTenants.module.css';

const STATUS_OPTIONS = [
  { value: '', label: 'Todos los status' },
  { value: 'active', label: 'Activos' },
  { value: 'trial', label: 'Trials' },
  { value: 'suspended', label: 'Suspendidos' },
  { value: 'churned', label: 'Churned' },
];

const COUNTRY_OPTIONS = [
  { value: '', label: 'Todos los países' },
  { value: 'CO', label: 'Colombia' },
  { value: 'MX', label: 'México' },
  { value: 'AR', label: 'Argentina' },
  { value: 'CL', label: 'Chile' },
  { value: 'PE', label: 'Perú' },
  { value: 'EC', label: 'Ecuador' },
  { value: 'UY', label: 'Uruguay' },
];

/**
 * Filter bar for the Fleet · Tenants view. The 4 inputs map 1:1 to the query
 * parameters of `GET /v1/tenants`. Changes are debounced by the calling hook
 * via `filtersKey` — keep this component dumb.
 *
 * @param {{
 *   filters: {status?: string, country?: string, vertical?: string, search?: string},
 *   onChange: (next: object) => void,
 * }} props
 */
export function FleetFilters({ filters, onChange }) {
  const update = (key) => (event) => onChange({ ...filters, [key]: event.target.value });

  return (
    <section className={styles.filters} aria-label="Filtros de flota">
      <label className={styles.filter}>
        <span className={styles.filterLabel}>Status</span>
        <select value={filters.status || ''} onChange={update('status')}>
          {STATUS_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label className={styles.filter}>
        <span className={styles.filterLabel}>País</span>
        <select value={filters.country || ''} onChange={update('country')}>
          {COUNTRY_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label className={styles.filter}>
        <span className={styles.filterLabel}>Vertical</span>
        <input
          type="text"
          value={filters.vertical || ''}
          onChange={update('vertical')}
          placeholder="ej. dental"
          maxLength={64}
        />
      </label>
      <label className={`${styles.filter} ${styles.filterGrow}`}>
        <span className={styles.filterLabel}>Buscar</span>
        <input
          type="search"
          value={filters.search || ''}
          onChange={update('search')}
          placeholder="slug, nombre o razón social"
          maxLength={160}
        />
      </label>
    </section>
  );
}
