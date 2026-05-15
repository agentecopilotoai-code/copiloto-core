import { Card, CardHeader } from '../../../../components/ui/index.js';
import { errorCodeLabel } from '../outboundDlqData.js';
import styles from '../OutboundDLQ.module.css';

/**
 * Error-code totals as filter chips. Clicking a chip toggles the active
 * error-code filter. Presentational — the totals + active filter come from the
 * `useOutboundDlqData` hook via props.
 *
 * @param {{
 *   totals: Array<{ error_code: string, count: number }>,
 *   activeFilter: string,
 *   onToggle: (code: string) => void,
 * }} props
 */
export function DlqErrorChips({ totals, activeFilter, onToggle }) {
  return (
    <Card padding="md">
      <CardHeader
        title="Errores agrupados"
        subtitle="Filtra la cola por código de error de Meta."
      />
      {totals.length === 0 ? (
        <p className={styles.hint}>Sin fallos registrados en este tenant.</p>
      ) : (
        <ul className={styles.chipList}>
          {totals.map((group) => (
            <li key={group.error_code}>
              <button
                type="button"
                className={`${styles.chip} ${
                  activeFilter === group.error_code ? styles.chipActive : ''
                }`}
                onClick={() => onToggle(group.error_code)}
                data-error-code={group.error_code}
                aria-pressed={activeFilter === group.error_code}
              >
                <strong>{group.error_code}</strong>
                <span className={styles.chipLabel}>{errorCodeLabel(group.error_code)}</span>
                <span className={styles.chipCount}>{group.count}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
