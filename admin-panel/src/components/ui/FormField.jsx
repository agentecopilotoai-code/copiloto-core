import { forwardRef, useId } from 'react';
import styles from './FormField.module.css';

/**
 * FormField — label + input wrapper with optional hint and error.
 *
 * @param {Object} props
 * @param {string} props.label
 * @param {string} [props.hint]
 * @param {string} [props.error]
 * @param {boolean} [props.required=false]
 * @param {React.ReactNode} [props.children] Custom control. If omitted, renders a native input.
 */
export const FormField = forwardRef(function FormField(
  { label, hint, error, required = false, id, className = '', children, ...rest },
  ref,
) {
  const autoId = useId();
  const fieldId = id || `field-${autoId}`;
  const hintId = hint ? `${fieldId}-hint` : undefined;
  const errorId = error ? `${fieldId}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(' ') || undefined;

  const control = children
    ? wrapControl(children, { id: fieldId, 'aria-describedby': describedBy, 'aria-invalid': Boolean(error), required })
    : (
      <input
        ref={ref}
        id={fieldId}
        className={styles.input}
        aria-describedby={describedBy}
        aria-invalid={Boolean(error) || undefined}
        required={required}
        {...rest}
      />
    );

  return (
    <div className={[styles.field, error ? styles['field--error'] : '', className].filter(Boolean).join(' ')}>
      <label htmlFor={fieldId} className={styles.label}>
        {label}
        {required ? <span className={styles.required} aria-hidden="true"> *</span> : null}
      </label>
      {control}
      {hint && !error ? (
        <p id={hintId} className={styles.hint}>{hint}</p>
      ) : null}
      {error ? (
        <p id={errorId} className={styles.error} role="alert">{error}</p>
      ) : null}
    </div>
  );
});

function wrapControl(child, extraProps) {
  if (!child || typeof child !== 'object' || Array.isArray(child)) return child;
  const merged = { ...extraProps };
  const existingClass = child.props?.className || '';
  if (!existingClass.includes('formfield-keep')) {
    merged.className = [existingClass, styles.input].filter(Boolean).join(' ');
  }
  return { ...child, props: { ...child.props, ...merged } };
}
