import styles from '../Runbooks.module.css';

/**
 * Filter bar for the Runbooks catalogue: a free-text search and a category
 * select. Both filter client-side — the catalogue is small (one file per
 * incident type). Dumb component; the view owns the filter state.
 *
 * @param {{
 *   search: string,
 *   category: string,
 *   categories: Array<string>,
 *   onSearchChange: (value: string) => void,
 *   onCategoryChange: (value: string) => void,
 * }} props
 */
export function RunbookFilters({ search, category, categories, onSearchChange, onCategoryChange }) {
  return (
    <section className={styles.filters} aria-label="Filtros de runbooks">
      <label className={`${styles.filter} ${styles.filterGrow}`}>
        <span className={styles.filterLabel}>Buscar</span>
        <input
          type="search"
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="título o slug del runbook"
          maxLength={120}
        />
      </label>
      <label className={styles.filter}>
        <span className={styles.filterLabel}>Categoría</span>
        <select value={category} onChange={(event) => onCategoryChange(event.target.value)}>
          <option value="">Todas las categorías</option>
          {categories.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}
