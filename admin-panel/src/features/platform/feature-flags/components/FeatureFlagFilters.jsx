import { TYPE_LABEL } from '../meta.js';
import styles from '../FeatureFlags.module.css';

/**
 * Filter bar for the Feature flags catalogue: a free-text search and a flag-type
 * select. Both filter client-side — the catalogue is a small static registry.
 * Dumb component; the view owns the filter state.
 *
 * @param {{
 *   search: string,
 *   type: string,
 *   types: Array<string>,
 *   onSearchChange: (value: string) => void,
 *   onTypeChange: (value: string) => void,
 * }} props
 */
export function FeatureFlagFilters({ search, type, types, onSearchChange, onTypeChange }) {
  return (
    <section className={styles.filters} aria-label="Filtros de feature flags">
      <label className={`${styles.filter} ${styles.filterGrow}`}>
        <span className={styles.filterLabel}>Buscar</span>
        <input
          type="search"
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="key o descripción del flag"
          maxLength={120}
        />
      </label>
      <label className={styles.filter}>
        <span className={styles.filterLabel}>Tipo</span>
        <select value={type} onChange={(event) => onTypeChange(event.target.value)}>
          <option value="">Todos los tipos</option>
          {types.map((item) => (
            <option key={item} value={item}>
              {TYPE_LABEL[item] || item}
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}
