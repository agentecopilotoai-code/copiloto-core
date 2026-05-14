import styles from './StatusBadge.module.css';

const TONES = ['neutral', 'accent', 'success', 'warning', 'danger'];

/**
 * StatusBadge — small pill used for statuses (active, churn, dlq, etc.).
 *
 * @param {Object} props
 * @param {'neutral'|'accent'|'success'|'warning'|'danger'} [props.tone='neutral']
 * @param {'solid'|'soft'|'outline'} [props.variant='soft']
 * @param {React.ReactNode} [props.icon]
 * @param {React.ReactNode} props.children
 */
export function StatusBadge({
  tone = 'neutral',
  variant = 'soft',
  icon,
  className = '',
  children,
  ...rest
}) {
  const safeTone = TONES.includes(tone) ? tone : 'neutral';
  const classes = [
    styles.badge,
    styles[`badge--${variant}`],
    styles[`badge--${safeTone}`],
    className,
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <span className={classes} {...rest}>
      {icon ? <span className={styles.dot} aria-hidden="true">{icon}</span> : <span className={styles.dot} aria-hidden="true" />}
      <span>{children}</span>
    </span>
  );
}
