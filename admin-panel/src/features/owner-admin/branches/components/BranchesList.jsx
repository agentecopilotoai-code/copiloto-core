import { Card, EmptyState, StatusBadge } from '../../../../components/ui/index.js';
import { formatLocation, summarizeHours } from '../branchesData.js';
import styles from '../Branches.module.css';

/**
 * Branch cards grid. Each card mirrors the HTML reference: avatar initial +
 * name + "Principal" badge + location/phone + edit/deactivate actions, and a
 * stats row with the data the `/branches` endpoint actually returns (schedule,
 * timezone, status). Presentational — state and mutations come from the
 * `useBranchesData` hook via props.
 *
 * @param {{
 *   branches: Array<object>,
 *   loading: boolean,
 *   saving: boolean,
 *   onEdit: (branch: object) => void,
 *   onDeactivate: (branch: object) => void,
 * }} props
 */
export function BranchesList({ branches, loading, saving, onEdit, onDeactivate }) {
  if (loading && branches.length === 0) {
    return (
      <Card padding="md">
        <p className={styles.hint}>Cargando…</p>
      </Card>
    );
  }

  if (branches.length === 0) {
    return (
      <Card padding="md">
        <EmptyState
          title="Sin sedes"
          description="Aún no hay sedes configuradas. Crea la primera con «Nueva sede»."
        />
      </Card>
    );
  }

  return (
    <div className={styles.branchGrid}>
      {branches.map((branch) => {
        const isPrincipal = (branch.code || '').toLowerCase() === 'principal';
        const initial = (branch.name || '?').trim().charAt(0).toUpperCase();
        const phone = (branch.phone_e164 || '').trim();
        return (
          <Card key={branch.id} padding="md" className={styles.branchCard}>
            <div className={styles.branchHead}>
              <span className={styles.avatar} aria-hidden="true">
                {initial}
              </span>
              <div className={styles.branchHeadText}>
                <div className={styles.branchNameRow}>
                  <span className={styles.branchName}>{branch.name}</span>
                  {isPrincipal ? <StatusBadge tone="accent">Principal</StatusBadge> : null}
                  {branch.is_active ? null : (
                    <StatusBadge tone="neutral">Inactiva</StatusBadge>
                  )}
                </div>
                <p className={styles.branchMeta}>
                  {formatLocation(branch)}
                  {phone ? ` · ${phone}` : ''}
                </p>
              </div>
              <div className={styles.rowActions}>
                <button
                  type="button"
                  className={styles.secondaryButton}
                  disabled={saving}
                  onClick={() => onEdit(branch)}
                >
                  Editar
                </button>
                {branch.is_active ? (
                  <button
                    type="button"
                    className={styles.secondaryButton}
                    disabled={saving}
                    onClick={() => onDeactivate(branch)}
                  >
                    Desactivar
                  </button>
                ) : null}
              </div>
            </div>
            <dl className={styles.branchStats}>
              <div className={styles.stat}>
                <dt>Horario</dt>
                <dd>{summarizeHours(branch.opening_hours)}</dd>
              </div>
              <div className={styles.stat}>
                <dt>Zona horaria</dt>
                <dd>{branch.timezone || '—'}</dd>
              </div>
              <div className={styles.stat}>
                <dt>Código</dt>
                <dd>{branch.code || '—'}</dd>
              </div>
            </dl>
          </Card>
        );
      })}
    </div>
  );
}
