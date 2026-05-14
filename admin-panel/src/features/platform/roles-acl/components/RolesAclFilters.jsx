import { ACCESS_LABEL, ACCESS_TONE } from '../rolesAclData.js';
import { StatusBadge } from '../../../../components/ui/index.js';
import styles from '../RolesAcl.module.css';

const LEGEND = ['RW', 'R', 'partial', 'own_only'];

/**
 * Filter bar for the Roles · ACL matrix: a free-text capability search plus the
 * access-level legend. Search filters client-side — the matrix is static data.
 *
 * @param {{ search: string, onSearchChange: (value: string) => void }} props
 */
export function RolesAclFilters({ search, onSearchChange }) {
  return (
    <section className={styles.filters} aria-label="Filtros de la matriz de permisos">
      <label className={`${styles.filter} ${styles.filterGrow}`}>
        <span className={styles.filterLabel}>Buscar capacidad</span>
        <input
          type="search"
          value={search}
          onChange={(event) => onSearchChange(event.target.value)}
          placeholder="ej. platform, contacts.write, analytics"
          maxLength={120}
        />
      </label>
      <div className={styles.legend} aria-label="Leyenda de niveles de acceso">
        {LEGEND.map((level) => (
          <span key={level} className={styles.legendItem}>
            <StatusBadge tone={ACCESS_TONE[level]}>{ACCESS_LABEL[level]}</StatusBadge>
          </span>
        ))}
        <span className={styles.legendItem}>
          <span className={styles.muted}>— sin acceso</span>
        </span>
      </div>
    </section>
  );
}
