import styles from '../Services.module.css';

/**
 * Up/down reorder control for a service row. Disabled at the ends of the list
 * and while a mutation is in flight. `onMove(direction)` receives -1 / +1.
 *
 * @param {{
 *   index: number,
 *   total: number,
 *   disabled: boolean,
 *   onMove: (direction: number) => void,
 * }} props
 */
export function ServiceReorder({ index, total, disabled, onMove }) {
  return (
    <span className={styles.reorder}>
      <button
        type="button"
        className={styles.iconButton}
        aria-label="Subir orden"
        disabled={disabled || index === 0}
        onClick={() => onMove(-1)}
      >
        ↑
      </button>
      <button
        type="button"
        className={styles.iconButton}
        aria-label="Bajar orden"
        disabled={disabled || index === total - 1}
        onClick={() => onMove(1)}
      >
        ↓
      </button>
    </span>
  );
}
