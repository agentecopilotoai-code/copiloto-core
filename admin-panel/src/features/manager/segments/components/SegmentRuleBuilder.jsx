import {
  FIELD_OPTIONS,
  LIST_OPS,
  fieldKind,
  operatorsForField,
  ruleNeedsValue,
} from '../segmentsData.js';
import styles from '../SegmentsModule.module.css';

/**
 * Dynamic rule builder for a dynamic segment: the joiner selector
 * (Todas / Alguna) plus an editable list of rule rows (field + operator +
 * value), with add / remove. Presentational — all rule state and the
 * add/remove/update callbacks come from the `useSegmentsData` hook via props.
 * The field/operator catalogues, the value-casting and the comma-separated
 * list parsing are preserved verbatim from the legacy `SegmentsModule`.
 *
 * @param {{
 *   joiner: 'all_of' | 'any_of',
 *   items: Array<{ field: string, op: string, value: * }>,
 *   onJoinerChange: (joiner: string) => void,
 *   onAddRule: () => void,
 *   onRemoveRule: (index: number) => void,
 *   onFieldChange: (index: number, field: string) => void,
 *   onOpChange: (index: number, op: string) => void,
 *   onValueChange: (index: number, rawValue: string) => void,
 *   onListValueBlur: (index: number, rawValue: string) => void,
 * }} props
 */
export function SegmentRuleBuilder({
  joiner,
  items,
  onJoinerChange,
  onAddRule,
  onRemoveRule,
  onFieldChange,
  onOpChange,
  onValueChange,
  onListValueBlur,
}) {
  return (
    <fieldset className={styles.ruleFieldset}>
      <legend>Reglas</legend>

      <label className={styles.joinerLabel}>
        Combinador
        <select value={joiner} onChange={(event) => onJoinerChange(event.target.value)}>
          <option value="all_of">Todas (AND)</option>
          <option value="any_of">Alguna (OR)</option>
        </select>
      </label>

      <div className={styles.ruleList}>
        {items.map((rule, index) => {
          const kind = fieldKind(rule.field);
          const operators = operatorsForField(rule.field);
          const isListOp = LIST_OPS.includes(rule.op);
          const numericInput = kind === 'number' || rule.op?.endsWith('_days_ago');
          return (
            <div key={index} className={styles.ruleRow}>
              <select
                aria-label="Campo"
                value={rule.field}
                onChange={(event) => onFieldChange(index, event.target.value)}
              >
                {FIELD_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <select
                aria-label="Operador"
                value={rule.op}
                onChange={(event) => onOpChange(index, event.target.value)}
              >
                {operators.map((operator) => (
                  <option key={operator.value} value={operator.value}>
                    {operator.label}
                  </option>
                ))}
              </select>
              {ruleNeedsValue(rule.op) ? (
                <input
                  aria-label="Valor"
                  type={numericInput ? 'number' : 'text'}
                  value={rule.value ?? ''}
                  onChange={(event) => onValueChange(index, event.target.value)}
                  placeholder={isListOp ? 'separa con coma' : 'valor'}
                  onBlur={(event) => {
                    if (isListOp) onListValueBlur(index, event.target.value);
                  }}
                />
              ) : (
                <span className={styles.ruleNoValue}>—</span>
              )}
              <button
                type="button"
                className={styles.dangerButton}
                onClick={() => onRemoveRule(index)}
              >
                Quitar
              </button>
            </div>
          );
        })}
      </div>

      <button type="button" className={styles.secondaryButton} onClick={onAddRule}>
        Añadir regla
      </button>
    </fieldset>
  );
}
