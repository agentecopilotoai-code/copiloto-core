import { APPLIES_WHEN_OPS, LIST_OPS, VALUELESS_OPS } from '../servicesData.js';
import styles from '../Services.module.css';

/**
 * Eligibility-rule builder of the service form (TASK-0054). Each rule is a
 * `{key, op, value}` predicate; the service is only offered when *all* rules
 * match the contact's qualification answers. An empty list means "always
 * applies". Presentational — `onAdd`/`onUpdate`/`onRemove` come from the hook.
 *
 * @param {{
 *   rules: Array<object>,
 *   qualificationKeys: Array<{key: string, label: string}>,
 *   onAdd: () => void,
 *   onUpdate: (index: number, patch: object) => void,
 *   onRemove: (index: number) => void,
 * }} props
 */
export function AppliesWhenBuilder({ rules, qualificationKeys, onAdd, onUpdate, onRemove }) {
  const list = rules || [];

  return (
    <fieldset className={styles.fieldset} data-testid="applies-when-builder">
      <legend className={styles.legend}>Reglas de elegibilidad (calificación)</legend>
      <p className={styles.hint}>
        El servicio sólo se ofrece cuando todas las reglas se cumplen contra las respuestas de
        calificación del cliente. Sin reglas aplica siempre.
      </p>

      {list.length === 0 ? (
        <p className={styles.hint}>No hay reglas — el servicio aplica a todos los clientes.</p>
      ) : null}

      {list.map((rule, index) => {
        const valueless = VALUELESS_OPS.has(rule.op);
        const listOp = LIST_OPS.has(rule.op);
        return (
          <div key={`rule-${index}`} data-testid="applies-when-rule" className={styles.ruleRow}>
            <select
              aria-label="Clave de calificación"
              value={rule.key}
              onChange={(event) => onUpdate(index, { key: event.target.value })}
            >
              <option value="">— Selecciona una clave —</option>
              {qualificationKeys.map((entry) => (
                <option key={entry.key} value={entry.key}>
                  {entry.key} · {entry.label}
                </option>
              ))}
              {rule.key && !qualificationKeys.some((entry) => entry.key === rule.key) ? (
                <option value={rule.key}>{rule.key}</option>
              ) : null}
            </select>
            <select
              aria-label="Operador"
              value={rule.op}
              onChange={(event) => onUpdate(index, { op: event.target.value, value: '' })}
            >
              {APPLIES_WHEN_OPS.map((entry) => (
                <option key={entry.value} value={entry.value}>
                  {entry.label}
                </option>
              ))}
            </select>
            {!valueless ? (
              <input
                type="text"
                aria-label="Valor"
                value={rule.value ?? ''}
                placeholder={
                  listOp ? 'valores separados por coma' : 'valor (true/false/número/texto)'
                }
                onChange={(event) => onUpdate(index, { value: event.target.value })}
              />
            ) : null}
            <button
              type="button"
              className={styles.secondaryButton}
              onClick={() => onRemove(index)}
            >
              Eliminar
            </button>
          </div>
        );
      })}

      <div className={styles.ruleActions}>
        <button
          type="button"
          className={styles.secondaryButton}
          onClick={onAdd}
          disabled={qualificationKeys.length === 0}
        >
          Agregar regla
        </button>
        {qualificationKeys.length === 0 ? (
          <span className={styles.hint}>
            Configura claves en Calificación antes de armar reglas.
          </span>
        ) : null}
      </div>
    </fieldset>
  );
}
