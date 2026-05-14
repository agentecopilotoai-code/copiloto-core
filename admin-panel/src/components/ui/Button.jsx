import { forwardRef } from 'react';
import styles from './Button.module.css';

/**
 * Button primitive aligned to the design system (`docs/HTML DESIGN/`).
 *
 * @param {Object} props
 * @param {'primary'|'secondary'|'ghost'|'danger'} [props.variant='secondary']
 * @param {'sm'|'md'|'lg'} [props.size='md']
 * @param {boolean} [props.loading=false] Shows spinner and disables the button.
 * @param {boolean} [props.fullWidth=false]
 * @param {React.ReactNode} [props.leadingIcon]
 * @param {React.ReactNode} [props.trailingIcon]
 * @param {React.ReactNode} props.children
 * @param {'button'|'submit'|'reset'} [props.type='button']
 */
export const Button = forwardRef(function Button(
  {
    variant = 'secondary',
    size = 'md',
    loading = false,
    fullWidth = false,
    leadingIcon,
    trailingIcon,
    className = '',
    children,
    disabled,
    type = 'button',
    ...rest
  },
  ref,
) {
  const classes = [
    styles.btn,
    styles[`btn--${variant}`],
    styles[`btn--${size}`],
    fullWidth ? styles['btn--block'] : '',
    loading ? styles['btn--loading'] : '',
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <button
      ref={ref}
      type={type}
      className={classes}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <span className={styles.spinner} aria-hidden="true" /> : leadingIcon}
      <span className={styles.label}>{children}</span>
      {!loading && trailingIcon ? <span className={styles.icon}>{trailingIcon}</span> : null}
    </button>
  );
});
