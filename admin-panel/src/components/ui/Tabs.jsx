import { useCallback, useId, useState } from 'react';
import styles from './Tabs.module.css';

/**
 * Tabs — accessible tablist. Uncontrolled by default; pass `value` for controlled mode.
 *
 * @param {Object} props
 * @param {Array<{value: string, label: React.ReactNode, content?: React.ReactNode, badge?: React.ReactNode, disabled?: boolean}>} props.items
 * @param {string} [props.value]
 * @param {string} [props.defaultValue]
 * @param {(value: string) => void} [props.onChange]
 * @param {'underline'|'pill'} [props.variant='underline']
 */
export function Tabs({
  items,
  value,
  defaultValue,
  onChange,
  variant = 'underline',
  className = '',
}) {
  const baseId = useId();
  const [internal, setInternal] = useState(defaultValue || items[0]?.value);
  const isControlled = value !== undefined;
  const current = isControlled ? value : internal;

  const select = useCallback(
    (next) => {
      if (!isControlled) setInternal(next);
      onChange?.(next);
    },
    [isControlled, onChange],
  );

  const activeItem = items.find((item) => item.value === current);

  return (
    <div className={[styles.tabs, styles[`tabs--${variant}`], className].filter(Boolean).join(' ')}>
      <div role="tablist" className={styles.list} aria-label="Pestañas">
        {items.map((item) => {
          const selected = item.value === current;
          return (
            <button
              key={item.value}
              type="button"
              role="tab"
              id={`${baseId}-tab-${item.value}`}
              aria-selected={selected}
              aria-controls={`${baseId}-panel-${item.value}`}
              tabIndex={selected ? 0 : -1}
              disabled={item.disabled}
              className={[styles.tab, selected ? styles['tab--active'] : ''].filter(Boolean).join(' ')}
              onClick={() => select(item.value)}
            >
              <span>{item.label}</span>
              {item.badge ? <span className={styles.badge}>{item.badge}</span> : null}
            </button>
          );
        })}
      </div>
      {activeItem?.content !== undefined ? (
        <div
          role="tabpanel"
          id={`${baseId}-panel-${activeItem.value}`}
          aria-labelledby={`${baseId}-tab-${activeItem.value}`}
          className={styles.panel}
        >
          {activeItem.content}
        </div>
      ) : null}
    </div>
  );
}
