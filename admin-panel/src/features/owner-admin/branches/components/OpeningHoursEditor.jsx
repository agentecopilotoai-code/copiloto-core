import { WEEKDAYS } from '../branchesData.js';
import styles from '../Branches.module.css';

/**
 * Per-day opening-hours editor. Each weekday holds zero or more time ranges
 * (`franjas`); presentational — all state and the franja mutators come from the
 * `useBranchesData` hook via props. Logic preserved verbatim from the legacy
 * `BranchesModule`.
 *
 * @param {{
 *   openingHours: Record<string, Array<{start: string, end: string}>>,
 *   onAddFranja: (dayKey: string) => void,
 *   onRemoveFranja: (dayKey: string, index: number) => void,
 *   onUpdateFranja: (dayKey: string, index: number, field: string, value: string) => void,
 * }} props
 */
export function OpeningHoursEditor({ openingHours, onAddFranja, onRemoveFranja, onUpdateFranja }) {
  return (
    <fieldset className={styles.hoursFieldset} data-testid="branches-hours">
      <legend className={styles.legend}>Horarios de atención por día</legend>
      {WEEKDAYS.map((day) => {
        const franjas = (openingHours || {})[day.key] || [];
        return (
          <div className={styles.hoursDay} key={day.key}>
            <strong className={styles.hoursDayLabel}>{day.label}</strong>
            <div className={styles.hoursFranjas}>
              {franjas.map((franja, index) => (
                // eslint-disable-next-line react/no-array-index-key
                <span className={styles.franja} key={index}>
                  <input
                    type="time"
                    value={franja.start || ''}
                    onChange={(event) => onUpdateFranja(day.key, index, 'start', event.target.value)}
                  />
                  <span aria-hidden="true">–</span>
                  <input
                    type="time"
                    value={franja.end || ''}
                    onChange={(event) => onUpdateFranja(day.key, index, 'end', event.target.value)}
                  />
                  <button
                    type="button"
                    className={styles.secondaryButton}
                    onClick={() => onRemoveFranja(day.key, index)}
                  >
                    Quitar
                  </button>
                </span>
              ))}
              <button
                type="button"
                className={styles.secondaryButton}
                onClick={() => onAddFranja(day.key)}
              >
                + franja
              </button>
            </div>
          </div>
        );
      })}
    </fieldset>
  );
}
